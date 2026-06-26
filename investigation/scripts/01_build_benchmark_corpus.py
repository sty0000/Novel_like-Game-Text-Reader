from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


CASES = [
    {
        "case_id": "case_001_short_dialogue",
        "category": "短对白",
        "speaker": "阿米娅",
        "text": "博士，博士！你终于醒了。",
        "purpose": "测试短句、称呼和急切语气。",
    },
    {
        "case_id": "case_002_narration",
        "category": "旁白",
        "speaker": "旁白",
        "text": "医疗室内，仪器发出规律的声响，窗外的天色仍旧阴沉。",
        "purpose": "测试稳定叙述和自然停顿。",
    },
    {
        "case_id": "case_003_emotion",
        "category": "情绪句",
        "speaker": "凯尔希",
        "text": "如果你已经决定继续前进，就不要再用沉默逃避答案。",
        "purpose": "测试严肃语气和长句控制。",
    },
    {
        "case_id": "case_004_terms",
        "category": "术语",
        "speaker": "医疗干员",
        "text": "罗德岛的源石感染监测结果已经同步给 PRTS。",
        "purpose": "测试明日方舟术语和中英混读。",
    },
    {
        "case_id": "case_005_punctuation",
        "category": "标点压力",
        "speaker": "？？？",
        "text": "等等……你听见了吗？那不是风声——有人正在靠近！",
        "purpose": "测试省略号、问号、破折号和感叹号。",
    },
    {
        "case_id": "case_006_long_dialogue",
        "category": "长对白",
        "speaker": "阿米娅",
        "text": "我知道现在还不能停下来，但至少在出发之前，请让我确认你的身体状况。",
        "purpose": "测试较长对白的流畅度和断句。",
    },
]


def write_jsonl(cases: list[dict[str, str]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as file:
        for item in cases:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")


def write_csv(cases: list[dict[str, str]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["case_id", "category", "speaker", "text", "purpose"])
        writer.writeheader()
        writer.writerows(cases)


def write_markdown(cases: list[dict[str, str]], path: Path) -> None:
    lines = [
        "# Benchmark Corpus",
        "",
        "这组文本用于 TTS 模型统一评估，覆盖短对白、旁白、情绪句、术语、中英混读和标点压力。",
        "",
        "| case_id | 类型 | 说话人 | 文本 | 目的 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in cases:
        lines.append(
            f"| `{item['case_id']}` | {item['category']} | {item['speaker']} | {item['text']} | {item['purpose']} |"
        )
    lines.extend(
        [
            "",
            "## 如何使用",
            "",
            "所有模型都应使用这份 corpus，不要为某个模型单独挑选更容易的句子。真实实验后，将每个 case 的输出路径和评分写入实验记录。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 TTS 调研统一 benchmark corpus")
    parser.add_argument("--output-dir", default="investigation/docs/generated/corpus", help="输出目录")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(CASES, output_dir / "benchmark_cases.jsonl")
    write_csv(CASES, output_dir / "benchmark_cases.csv")
    write_markdown(CASES, output_dir / "benchmark_cases.md")
    print(f"已生成 benchmark corpus：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
