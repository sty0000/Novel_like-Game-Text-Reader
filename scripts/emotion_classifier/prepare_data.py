"""从已解析的 JSONL 文件中提取对白，生成训练标注数据。

输出的 CSV 包含以下列::

    text        — 对白文本（去除换行，单行）
    emotion     — 情感标签（规则预标注，需人工审核）
    speaker     — 说话人名称
    source_file — 来源文件名
    segment_id  — 原始段 id（方便回溯）

用法::

    # 从单个文件生成
    python -m scripts.emotion_classifier.prepare_data parsed/story.segments.jsonl

    # 从目录批量生成，合并为一个文件
    python -m scripts.emotion_classifier.prepare_data parsed/ -o train_data.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from scripts.emotion_classifier.rules import EMOTION_LABELS, detect_emotion


def iter_dialogues(path: Path) -> list[dict]:
    """从 JSONL 文件中提取所有对白段。"""
    dialogues: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            seg = json.loads(line)
            if seg.get("role") != "dialogue":
                continue
            text = (seg.get("text") or "").replace("\n", " ").strip()
            if not text:
                continue
            dialogues.append(
                {
                    "text": text,
                    "speaker": seg.get("speaker", ""),
                    "source_file": seg.get("source_file", path.name),
                    "segment_id": seg.get("segment_id", 0),
                }
            )
    return dialogues


def label_dialogues(dialogues: list[dict]) -> list[dict]:
    """用规则给每条对白打上情感标签。"""
    for d in dialogues:
        d["emotion"] = detect_emotion(d["text"])
    return dialogues


def write_csv(rows: list[dict], output_path: Path) -> None:
    """写入 CSV 文件。"""
    fieldnames = ["text", "emotion", "speaker", "source_file", "segment_id"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从已解析的 JSONL 提取对白并预标注情感标签"
    )
    parser.add_argument(
        "input",
        help="输入的 .segments.jsonl 文件或包含此类文件的目录",
    )
    parser.add_argument(
        "-o", "--output",
        default="training_data.csv",
        help="输出的 CSV 文件路径（默认 training_data.csv）",
    )
    args = parser.parse_args()

    input_path = Path(args.input)

    if input_path.is_dir():
        jsonl_files = sorted(input_path.glob("*.segments.jsonl"))
        if not jsonl_files:
            jsonl_files = sorted(input_path.glob("*.jsonl"))
        if not jsonl_files:
            print(f"错误: 目录 {input_path} 中未找到 JSONL 文件", file=sys.stderr)
            return 1
        all_dialogues: list[dict] = []
        for f in jsonl_files:
            all_dialogues.extend(iter_dialogues(f))
    else:
        all_dialogues = iter_dialogues(input_path)

    if not all_dialogues:
        print("错误: 未提取到任何对白", file=sys.stderr)
        return 1

    label_dialogues(all_dialogues)

    output_path = Path(args.output)
    write_csv(all_dialogues, output_path)

    # 打印标签分布
    counts: dict[str, int] = {label: 0 for label in EMOTION_LABELS}
    for d in all_dialogues:
        counts[d["emotion"]] = counts.get(d["emotion"], 0) + 1

    print(f"已从 {len(all_dialogues)} 条对白生成标注数据 -> {output_path}", file=sys.stderr)
    print("标签分布:", file=sys.stderr)
    for label in EMOTION_LABELS:
        bar = "█" * (counts[label] * 40 // max(len(all_dialogues), 1))
        print(f"  {label:16s} {counts[label]:4d}  {bar}", file=sys.stderr)
    print(
        "\n请人工审核 CSV 中的 emotion 列，修正错误标签后即可用于训练。",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
