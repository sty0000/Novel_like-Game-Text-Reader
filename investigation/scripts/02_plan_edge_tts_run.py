from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path


DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


def load_cases(path: Path) -> list[dict[str, str]]:
    cases = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                cases.append(json.loads(line))
    return cases


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in value)


def quote_arg(value: str) -> str:
    return shlex.quote(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="根据 benchmark corpus 生成 Edge TTS 执行计划")
    parser.add_argument("--corpus", required=True, help="benchmark_cases.jsonl 路径")
    parser.add_argument("--output-dir", default="investigation/docs/generated/edge_tts", help="输出目录")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="默认 Edge TTS voice")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    input_dir = output_dir / "input"
    audio_dir = output_dir / "audio"
    input_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases(Path(args.corpus))
    commands = [
        "# Edge TTS 执行命令清单",
        "",
        "这些命令用于真实调用仓库现有 `scripts/tts_edge.py`。运行前请安装 `edge-tts`。",
        "",
        "```bash",
        "python -m pip install edge-tts",
        "```",
        "",
    ]
    run_template = []

    used_names: dict[str, str] = {}

    for item in cases:
        case_id = safe_name(item["case_id"])
        previous_case = used_names.get(case_id)
        if previous_case is not None:
            raise ValueError(f"case_id {item['case_id']!r} 与 {previous_case!r} 生成了相同文件名 {case_id!r}")
        used_names[case_id] = item["case_id"]
        input_path = input_dir / f"{case_id}.txt"
        output_path = audio_dir / f"{case_id}.mp3"
        input_path.write_text(item["text"] + "\n", encoding="utf-8")
        command = (
            f"python {quote_arg('scripts/tts_edge.py')} --input {quote_arg(input_path.as_posix())} "
            f"--output {quote_arg(output_path.as_posix())} --voice {quote_arg(args.voice)}"
        )
        commands.extend([f"## {case_id}", "", f"说话人：{item['speaker']}", "", "```bash", command, "```", ""])
        run_template.append(
            {
                "case_id": item["case_id"],
                "speaker": item["speaker"],
                "text": item["text"],
                "voice": args.voice,
                "command": command,
                "input_path": input_path.as_posix(),
                "output_path": output_path.as_posix(),
                "status": "pending",
                "notes": "",
            }
        )

    (output_dir / "edge_tts_commands.md").write_text("\n".join(commands), encoding="utf-8")
    (output_dir / "edge_tts_run_template.json").write_text(
        json.dumps(run_template, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已生成 Edge TTS 执行计划：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
