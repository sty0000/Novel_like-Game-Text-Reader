"""CosyVoice zero-shot 多角色语音合成。

根据 voice_map.json 为每个角色选择参考音频，zero-shot 克隆音色。
旁白或无参考音频的角色回退到 edge-tts。

用法::

    python scripts/tts_cosyvoice.py \\
        --input parsed/story.enriched.jsonl \\
        --output audio/story.mp3 \\
        --voice-map voice_map.json \\
        --model-dir CosyVoice/pretrained_models/CosyVoice2-0.5B
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import tempfile
from pathlib import Path
from typing import Optional

DEFAULT_MODEL_DIR = "CosyVoice/pretrained_models/CosyVoice2-0.5B"
DEFAULT_VOICE_MAP = "voice_map.json"
DEFAULT_NARRATOR_VOICE = "zh-CN-YunjianNeural"  # 旁白音色
DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"      # 角色回退音色
MAX_RETRIES = 3  # TTS 调用失败重试次数

# 确保 CosyVoice 可导入
_COSY_DIR = Path(__file__).resolve().parent.parent / "CosyVoice"
if str(_COSY_DIR) not in sys.path:
    sys.path.insert(0, str(_COSY_DIR))


def load_cosyvoice(model_dir: str):
    """延迟加载 CosyVoice 模型（首次调用时加载）。"""
    from cosyvoice.cli.cosyvoice import AutoModel
    return AutoModel(model_dir=model_dir)


def load_voice_map(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def pick_ref_audio(speaker: str, voice_map: dict) -> Optional[tuple[str, str]]:
    """根据 speaker 找到参考音频路径和文本。

    Returns: (wav_path, prompt_text) or None"""
    cfg = voice_map.get(speaker, {})
    if cfg.get("engine") != "cosyvoice":
        return None

    voice_dir = Path(cfg.get("voice_dir", ""))
    csv_path = voice_dir / "transcripts.csv"
    if not csv_path.exists():
        print(f"  [cosyvoice] {speaker}: 缺少 transcripts.csv", file=sys.stderr)
        return None

    with csv_path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return None

    # 取第一句作为参考（可扩展为按情绪选择）
    row = rows[0]
    wav = voice_dir / "wavs" / row["file"]
    text = row["text"].strip()
    if not wav.exists() or not text:
        return None
    return str(wav.resolve()), text


async def synthesize_segments(
    jsonl_path: Path,
    output_path: Path,
    voice_map: dict,
    model_dir: str,
    narrator_voice: str,
    edge_voice: str,
    narrator_pause_ms: int = 250,
    edge_rate: str = "+0%",
    edge_volume: str = "+0%",
):
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError("需要 pydub。运行: pip install pydub")

    segments = []
    with jsonl_path.open(encoding="utf-8") as f:
        lines = [json.loads(l) for l in f if l.strip()]

    # 延迟加载 CosyVoice
    cosyvoice = None
    cosyvoice_refs: dict[str, tuple[str, str]] = {}
    for seg in lines:
        speaker = seg.get("speaker", "旁白")
        if speaker not in cosyvoice_refs and voice_map.get(speaker, {}).get("engine") == "cosyvoice":
            ref = pick_ref_audio(speaker, voice_map)
            if ref:
                cosyvoice_refs[speaker] = ref

    if cosyvoice_refs:
        print(f"加载 CosyVoice 模型 ({model_dir})...", file=sys.stderr)
        cosyvoice = load_cosyvoice(model_dir)

    print(f"正在合成 {len(lines)} 段...", file=sys.stderr)

    for i, seg in enumerate(lines):
        if seg.get("is_silence"):
            segments.append(AudioSegment.silent(duration=800))
            continue

        prefix = seg.get("speech_prefix", "")
        text = (seg.get("tts_text") or seg.get("text", "")).strip()
        speaker = seg.get("speaker", "旁白")
        if not text:
            continue

        # ── 合成本段：前缀（旁白）+ 对白（角色）──
        chunk: list = []

        if prefix:
            prefix_wav = None
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    prefix_wav = await _edge_tts(prefix, narrator_voice, edge_rate, edge_volume)
                    break
                except Exception as e:
                    print(f"  [narrator] 第{attempt}次失败: {e}", file=sys.stderr)
                    if attempt == MAX_RETRIES:
                        print(f"  [narrator] 已达最大重试次数，跳过本段前缀", file=sys.stderr)
            if prefix_wav:
                prefix_audio = _bytes_to_audio(prefix_wav)
                if prefix_audio:
                    chunk.append(prefix_audio)
                    chunk.append(AudioSegment.silent(duration=narrator_pause_ms))

        ref = cosyvoice_refs.get(speaker)
        wav_data = None
        failed = False

        if ref and cosyvoice:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    wav_path, prompt_text = ref
                    wav_data = _cosyvoice_tts(cosyvoice, text, wav_path, prompt_text)
                    if wav_data:
                        break
                except Exception as e:
                    print(f"  [cosyvoice] {speaker} 第{attempt}次失败: {e}", file=sys.stderr)
                if attempt == MAX_RETRIES:
                    print(f"  [cosyvoice] {speaker} 已达最大重试次数，回退 edge-tts", file=sys.stderr)

        if wav_data is None:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    char_voice = voice_map.get(speaker, {}).get("voice", edge_voice)
                    wav_data = await _edge_tts(text, char_voice, edge_rate, edge_volume)
                    if wav_data:
                        break
                except Exception as e:
                    print(f"  [edge] {speaker} 第{attempt}次失败: {e}", file=sys.stderr)
                if attempt == MAX_RETRIES:
                    print(f"  [edge] {speaker} 已达最大重试次数，跳过本段", file=sys.stderr)
                    failed = True

        if failed:
            continue

        char_audio = _bytes_to_audio(wav_data)
        if char_audio:
            chunk.append(char_audio)

        segments.extend(chunk)

        if (i + 1) % 20 == 0:
            print(f"  {i + 1}/{len(lines)}", file=sys.stderr)

    if not segments:
        raise ValueError("没有生成任何音频片段")

    combined = segments[0]
    for s in segments[1:]:
        combined += s

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.export(str(output_path), format="mp3")
    print(f"已保存到 {output_path}", file=sys.stderr)


def _cosyvoice_tts(model, text: str, ref_wav: str, prompt_text: str) -> bytes | None:
    """CosyVoice zero-shot 合成，返回 WAV bytes。"""
    import tempfile
    import torchaudio

    for result in model.inference_zero_shot(
        text, prompt_text, ref_wav, stream=False
    ):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        torchaudio.save(str(tmp_path), result["tts_speech"], model.sample_rate)
        data = tmp_path.read_bytes()
        tmp_path.unlink(missing_ok=True)
        return data
    return None


async def _edge_tts(text: str, voice: str, rate: str, volume: str) -> bytes:
    import edge_tts
    from pydub import AudioSegment
    import io

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, volume=volume)
        await communicate.save(str(tmp_path))
        audio = AudioSegment.from_mp3(str(tmp_path))
        buf = io.BytesIO()
        audio.export(buf, format="wav")
        return buf.getvalue()
    finally:
        tmp_path.unlink(missing_ok=True)


def _bytes_to_audio(data: bytes):
    from pydub import AudioSegment
    import io
    return AudioSegment.from_wav(io.BytesIO(data))


def main() -> int:
    p = argparse.ArgumentParser(description="CosyVoice zero-shot 多角色语音合成")
    p.add_argument("--input", required=True, help="enriched .jsonl")
    p.add_argument("--output", required=True, help="输出 mp3")
    p.add_argument("--voice-map", default=DEFAULT_VOICE_MAP)
    p.add_argument("--model-dir", default=DEFAULT_MODEL_DIR)
    p.add_argument("--narrator-voice", default=DEFAULT_NARRATOR_VOICE, help="旁白音色")
    p.add_argument("--edge-voice", default=DEFAULT_EDGE_VOICE, help="角色回退音色")
    p.add_argument("--narrator-pause", type=int, default=250, help="旁白与对白间停顿(ms)")
    p.add_argument("--edge-rate", default="+0%")
    p.add_argument("--edge-volume", default="+0%")
    args = p.parse_args()

    voice_map = load_voice_map(Path(args.voice_map))
    try:
        asyncio.run(synthesize_segments(
            Path(args.input), Path(args.output), voice_map,
            args.model_dir, args.narrator_voice,
            args.edge_voice, args.narrator_pause,
            args.edge_rate, args.edge_volume,
        ))
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
