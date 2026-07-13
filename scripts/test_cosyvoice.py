"""CosyVoice 零样本克隆诊断。

分别用 CosyVoice 和 Edge TTS 合成同一句话，保存对比音频。
"""

import sys
import csv
import io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "CosyVoice"))

VOICE_MAP_PATH = Path("voice_map.json")
REF_TEXT = "博士，今天的作战计划已经准备好了。"
TEST_SPEAKER = "陈"  # 用有参考音频的角色测试


def test_cosyvoice_directly():
    """直接调 CosyVoice API 合成。"""
    import json
    from cosyvoice.cli.cosyvoice import AutoModel

    voice_map = json.loads(VOICE_MAP_PATH.read_text(encoding="utf-8"))
    cfg = voice_map[TEST_SPEAKER]
    voice_dir = Path(cfg["voice_dir"])

    # 读第一句参考音频
    with (voice_dir / "transcripts.csv").open(encoding="utf-8-sig") as f:
        row = list(csv.DictReader(f))[0]
    ref_wav = str((voice_dir / "wavs" / row["file"]).resolve())
    ref_text = row["text"].strip()

    print(f"参考音频: {ref_wav}")
    print(f"参考文本: {ref_text}")
    print(f"合成文本: {REF_TEXT}")

    model = AutoModel(model_dir="CosyVoice/pretrained_models/CosyVoice2-0.5B")

    import torchaudio

    for result in model.inference_zero_shot(
        REF_TEXT, ref_text, ref_wav, stream=False
    ):
        out = Path("audio/diag_cosyvoice.wav")
        out.parent.mkdir(exist_ok=True)
        torchaudio.save(str(out), result["tts_speech"], model.sample_rate)
        print(f"\n✅ CosyVoice 已保存: {out}")
        return


def test_edge_comparison():
    """Edge TTS 对比版。"""
    import asyncio
    import edge_tts
    from pydub import AudioSegment

    async def run():
        out = Path("audio/diag_edge.wav")
        communicate = edge_tts.Communicate(
            text=REF_TEXT,
            voice="zh-CN-XiaoxiaoNeural",
        )
        await communicate.save(str(out.with_suffix(".mp3")))
        audio = AudioSegment.from_mp3(str(out.with_suffix(".mp3")))
        audio.export(str(out), format="wav")
        out.with_suffix(".mp3").unlink()
        print(f"✅ Edge TTS 已保存: {out}")

    asyncio.run(run())


def main():
    import sys
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("mode", nargs="?", default="both",
                   choices=["cosyvoice", "edge", "both"])
    args = p.parse_args()

    if not VOICE_MAP_PATH.exists():
        print("❌ voice_map.json 不存在", file=sys.stderr)
        return 1

    print("=" * 50)
    print(f"CosyVoice 零样本克隆诊断")
    print(f"测试角色: {TEST_SPEAKER}")
    print(f"测试文本: {REF_TEXT}")
    print("=" * 50)

    if args.mode in ("cosyvoice", "both"):
        print("\n── CosyVoice ──")
        try:
            test_cosyvoice_directly()
        except Exception as e:
            print(f"❌ CosyVoice 失败: {e}")

    if args.mode in ("edge", "both"):
        print("\n── Edge TTS 对比 ──")
        try:
            test_edge_comparison()
        except Exception as e:
            print(f"❌ Edge TTS 失败: {e}")

    print("\n对比 audio/diag_cosyvoice.wav 和 audio/diag_edge.wav")
    print("如果两者音色完全不同 → CosyVoice 克隆成功 ✓")
    print("如果两者音色一样 → 可能回退到了 Edge TTS ✗")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
