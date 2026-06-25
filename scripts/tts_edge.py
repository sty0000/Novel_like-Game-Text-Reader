from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Iterable


DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
DEFAULT_SPEAKER_SUFFIX = "说："


def iter_jsonl_text(path: Path, text_field: str, speak_speaker: bool = True) -> Iterable[str]:
    previous_speaker = None
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"JSONL 第 {line_number} 行不是有效 JSON: {error}") from error

        text = payload.get(text_field, "")
        if not isinstance(text, str):
            raise ValueError(f"JSONL 第 {line_number} 行的 {text_field!r} 字段不是字符串")
        text = text.strip()
        if not text:
            continue

        role = payload.get("role", "")
        speaker = payload.get("speaker", "")
        if speak_speaker and role == "dialogue" and isinstance(speaker, str) and speaker.strip():
            current_speaker = speaker.strip()
            if current_speaker != previous_speaker:
                text = f"{current_speaker}{DEFAULT_SPEAKER_SUFFIX}{text}"
            previous_speaker = current_speaker
        else:
            previous_speaker = None

        yield text


def load_input_text(path: Path, input_format: str, text_field: str, speak_speaker: bool) -> str:
    if input_format == "jsonl":
        return "\n".join(iter_jsonl_text(path, text_field, speak_speaker=speak_speaker))
    return path.read_text(encoding="utf-8").strip()


async def synthesize(text: str, output: Path, voice: str, rate: str, volume: str) -> None:
    try:
        import edge_tts
    except ImportError as error:
        raise RuntimeError("缺少依赖 edge-tts，请先运行：python -m pip install edge-tts") from error

    output.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, volume=volume)
    await communicate.save(str(output))


def main() -> int:
    parser = argparse.ArgumentParser(description="使用 edge-tts 将文本或 JSONL 片段合成为语音文件")
    parser.add_argument("--input", required=True, help="输入 .txt 或 .jsonl 文件")
    parser.add_argument("--output", required=True, help="输出音频文件，例如 audio/story.mp3")
    parser.add_argument("--format", choices=["txt", "jsonl"], default="txt", help="输入格式")
    parser.add_argument("--text-field", default="text", help="JSONL 输入中用于合成的字段名")
    parser.add_argument("--no-speaker-prefix", action="store_true", help="关闭对白前的“xxx说：”前缀")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="edge-tts voice 名称")
    parser.add_argument("--rate", default="+0%", help="语速，例如 +0%%、-10%%、+15%%")
    parser.add_argument("--volume", default="+0%", help="音量，例如 +0%%、-10%%、+15%%")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        text = load_input_text(input_path, args.format, args.text_field, speak_speaker=not args.no_speaker_prefix)
        if not text:
            raise ValueError("输入文本为空")
        asyncio.run(synthesize(text, output_path, args.voice, args.rate, args.volume))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1

    print(f"已保存到 {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
