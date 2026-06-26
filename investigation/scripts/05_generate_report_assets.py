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
    body = render_markdown(markdown)
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; line-height: 1.7; max-width: 960px; margin: 40px auto; padding: 0 24px; color: #1f2937; }}
    h1, h2, h3 {{ color: #111827; }}
    code, pre {{ background: #f3f4f6; border-radius: 6px; }}
    code {{ padding: 0.1em 0.3em; }}
    pre {{ padding: 16px; overflow-x: auto; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px; text-align: left; }}
    th {{ background: #f9fafb; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    parts = escaped.split("`")
    for index in range(1, len(parts), 2):
        parts[index] = f"<code>{parts[index]}</code>"
    return "".join(parts)


def render_table(rows: list[str]) -> str:
    parsed = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in rows]
    if len(parsed) >= 2 and all(set(cell) <= {"-", ":", " "} for cell in parsed[1]):
        header, body_rows = parsed[0], parsed[2:]
        header_html = "".join(f"<th>{inline_markdown(cell)}</th>" for cell in header)
        body_html = "".join(
            "<tr>" + "".join(f"<td>{inline_markdown(cell)}</td>" for cell in row) + "</tr>" for row in body_rows
        )
        return f"<table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table>"
    return "\n".join(f"<p>{inline_markdown(row)}</p>" for row in rows)


def render_markdown(markdown: str) -> str:
    html_lines: list[str] = []
    table_rows: list[str] = []
    in_code = False
    code_lines: list[str] = []

    def flush_table() -> None:
        nonlocal table_rows
        if table_rows:
            html_lines.append(render_table(table_rows))
            table_rows = []

    for line in markdown.splitlines():
        if line.startswith("```"):
            if in_code:
                html_lines.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = []
                in_code = False
            else:
                flush_table()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if line.startswith("|") and line.endswith("|"):
            table_rows.append(line)
            continue
        flush_table()
        if line.startswith("# "):
            html_lines.append(f"<h1>{inline_markdown(line[2:])}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{inline_markdown(line[3:])}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3>{inline_markdown(line[4:])}</h3>")
        elif line.startswith("- "):
            html_lines.append(f"<p>• {inline_markdown(line[2:])}</p>")
        elif line.strip():
            html_lines.append(f"<p>{inline_markdown(line)}</p>")
        else:
            html_lines.append("")
    flush_table()
    if in_code:
        html_lines.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(html_lines)


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
