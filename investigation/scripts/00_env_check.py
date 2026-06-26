from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


COMMANDS = ["git", "python", "ffmpeg", "nvidia-smi"]


def run_command(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"不可用: {error}"
    output = (completed.stdout or completed.stderr).strip()
    return output.splitlines()[0] if output else f"退出码 {completed.returncode}"


def collect_env() -> dict[str, object]:
    command_status = {}
    for command in COMMANDS:
        path = shutil.which(command)
        command_status[command] = {
            "path": path,
            "version": run_command([command, "--version"]) if path and command != "nvidia-smi" else None,
        }
    if shutil.which("nvidia-smi"):
        command_status["nvidia-smi"]["version"] = run_command(["nvidia-smi"])

    return {
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "commands": command_status,
    }


def write_markdown(env: dict[str, object], output: Path) -> None:
    commands = env["commands"]
    lines = [
        "# 环境检查结果",
        "",
        f"- Python: `{env['python'].splitlines()[0]}`",
        f"- Python executable: `{env['executable']}`",
        f"- Platform: `{env['platform']}`",
        f"- Machine: `{env['machine']}`",
        f"- Processor: `{env['processor']}`",
        "",
        "## 命令可用性",
        "",
        "| 命令 | 路径 | 版本/状态 |",
        "| --- | --- | --- |",
    ]
    for name, info in commands.items():
        path = info.get("path") or "不可用"
        version = info.get("version") or "未检测"
        lines.append(f"| `{name}` | `{path}` | `{str(version).replace('|', '/')}` |")
    lines.extend(
        [
            "",
            "## 如何固化到文档",
            "",
            "将本文件摘要复制到具体实验记录中，尤其是 Python 版本、GPU/ffmpeg 可用性和模型相关依赖状态。",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="收集 TTS 调研环境信息")
    parser.add_argument("--output-dir", default="investigation/docs/generated/env", help="输出目录")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    env = collect_env()
    (output_dir / "env.json").write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(env, output_dir / "env.md")
    print(f"已生成：{output_dir / 'env.json'}")
    print(f"已生成：{output_dir / 'env.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
