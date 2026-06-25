from __future__ import annotations

import argparse
import csv
from pathlib import Path


MODELS = [
    {
        "model": "CosyVoice",
        "position": "zero-shot voice cloning 候选",
        "input": "prompt_wav + prompt_text + tts_text",
        "output_dir": "investigation/docs/generated/comparison/cosyvoice",
        "decision_rule": "音色自然度或部署体验显著优于 GPT-SoVITS 时进入主线候选",
    },
    {
        "model": "IndexTTS",
        "position": "controllable zero-shot TTS 候选",
        "input": "reference audio + tts_text",
        "output_dir": "investigation/docs/generated/comparison/indextts",
        "decision_rule": "中文术语、拼音控制或音色稳定性显著更好时进入主线候选",
    },
    {
        "model": "Fish Speech",
        "position": "多语种 voice cloning 候选",
        "input": "reference audio + prompt + tts_text",
        "output_dir": "investigation/docs/generated/comparison/fish_speech",
        "decision_rule": "多角色生成质量与工程成本达到可接受水平时进入主线候选",
    },
]


def write_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["model", "position", "input", "output_dir", "decision_rule"])
        writer.writeheader()
        writer.writerows(MODELS)


def write_plan(path: Path) -> None:
    lines = [
        "# 候选模型对比执行计划",
        "",
        "所有候选模型必须使用同一份 benchmark corpus 和同一套评分表。",
        "",
        "## 模型清单",
        "",
        "| 模型 | 定位 | 输入 | 输出目录 | 决策规则 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in MODELS:
        lines.append(
            f"| {item['model']} | {item['position']} | {item['input']} | `{item['output_dir']}` | {item['decision_rule']} |"
        )
    lines.extend(
        [
            "",
            "## 每个模型需要保存",
            "",
            "```text",
            "audio/",
            "runlog.json",
            "runlog.md",
            "score.csv",
            "notes.md",
            "```",
            "",
            "## 评分字段",
            "",
            "- pronunciation_score：中文发音 1–5",
            "- similarity_score：音色相似度 1–5",
            "- stability_score：稳定性 1–5",
            "- deployment_score：部署体验 1–5",
            "- issue：问题描述",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成候选 TTS 模型对比计划")
    parser.add_argument("--output-dir", default="investigation/docs/generated/comparison", help="输出目录")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "model_comparison_matrix.csv")
    write_plan(output_dir / "model_comparison_plan.md")
    print(f"已生成候选模型对比计划：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
