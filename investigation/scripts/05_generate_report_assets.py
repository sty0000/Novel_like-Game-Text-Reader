from __future__ import annotations

import argparse
import html
from pathlib import Path


SECTIONS = [
    ("env/env.md", "环境检查"),
    ("corpus/benchmark_cases.md", "Benchmark Corpus"),
    ("edge_tts/edge_tts_commands.md", "Edge TTS 执行计划"),
    ("gpt_sovits/gpt_sovits_runbook.md", "GPT-SoVITS 执行规划"),
    ("comparison/model_comparison_plan.md", "候选模型对比计划"),
]


def read_optional(path: Path) -> str:
    if not path.exists():
        return f"_未找到 `{path.as_posix()}`，请先运行对应脚本。_\n"
    return path.read_text(encoding="utf-8")


def markdown_to_simple_html(markdown: str, title: str) -> str:
    escaped = html.escape(markdown)
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; line-height: 1.7; max-width: 960px; margin: 40px auto; padding: 0 24px; color: #1f2937; }}
    pre {{ white-space: pre-wrap; background: #f3f4f6; padding: 16px; border-radius: 6px; }}
  </style>
</head>
<body>
  <pre>{escaped}</pre>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="汇总 investigation 生成资产为 Markdown/HTML 报告")
    parser.add_argument("--generated-dir", default="investigation/docs/generated", help="生成资产根目录")
    parser.add_argument("--output-dir", default="investigation/docs/generated/report", help="报告输出目录")
    args = parser.parse_args()

    generated_dir = Path(args.generated_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# TTS 模型调研资产汇总报告",
        "",
        "本报告由 `05_generate_report_assets.py` 根据 generated 目录自动汇总。",
        "",
    ]
    for relative, heading in SECTIONS:
        lines.extend([f"## {heading}", ""])
        lines.append(read_optional(generated_dir / relative))
        lines.append("")

    markdown = "\n".join(lines)
    (output_dir / "investigation_summary.md").write_text(markdown, encoding="utf-8")
    (output_dir / "investigation_summary.html").write_text(
        markdown_to_simple_html(markdown, "TTS 模型调研资产汇总报告"), encoding="utf-8"
    )
    print(f"已生成报告：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
