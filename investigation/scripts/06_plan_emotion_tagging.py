from __future__ import annotations

import argparse
import json
from pathlib import Path


EMOTION_TAGS = {
    "neutral": {"label": "中性", "speech_verb": "说", "edge_rate": "+0%", "edge_volume": "+0%"},
    "urgent": {"label": "急切", "speech_verb": "急切地说", "edge_rate": "+10%", "edge_volume": "+0%"},
    "angry": {"label": "生气", "speech_verb": "生气地说", "edge_rate": "+5%", "edge_volume": "+10%"},
    "sad": {"label": "低落", "speech_verb": "低落地说", "edge_rate": "-10%", "edge_volume": "-5%"},
    "fearful": {"label": "害怕", "speech_verb": "害怕地说", "edge_rate": "+5%", "edge_volume": "-5%"},
    "surprised": {"label": "惊讶", "speech_verb": "惊讶地说", "edge_rate": "+10%", "edge_volume": "+5%"},
    "hesitant": {"label": "迟疑", "speech_verb": "迟疑地说", "edge_rate": "-10%", "edge_volume": "+0%"},
    "whisper": {"label": "低声", "speech_verb": "低声说", "edge_rate": "-5%", "edge_volume": "-15%"},
    "determined": {"label": "坚定", "speech_verb": "坚定地说", "edge_rate": "+0%", "edge_volume": "+5%"},
    "apologetic": {"label": "歉疚", "speech_verb": "歉疚地说", "edge_rate": "-5%", "edge_volume": "-5%"},
    "confused": {"label": "困惑", "speech_verb": "困惑地说", "edge_rate": "-5%", "edge_volume": "+0%"},
    "relieved": {"label": "放松", "speech_verb": "松了一口气说", "edge_rate": "-5%", "edge_volume": "+0%"},
}


RULES = [
    {"signal": "包含感叹号或重复称呼", "emotion": "urgent", "weight": 0.3, "evidence": "感叹号/重复称呼"},
    {"signal": "包含问号或 ?!", "emotion": "confused", "weight": 0.25, "evidence": "疑问标点"},
    {"signal": "包含省略号", "emotion": "hesitant", "weight": 0.35, "evidence": "省略号"},
    {"signal": "包含 快、小心、住手、别过来", "emotion": "urgent", "weight": 0.45, "evidence": "急迫关键词"},
    {"signal": "包含 可恶、混蛋", "emotion": "angry", "weight": 0.55, "evidence": "愤怒关键词"},
    {"signal": "包含 抱歉、对不起", "emotion": "apologetic", "weight": 0.55, "evidence": "道歉关键词"},
    {"signal": "包含 太好了、谢谢", "emotion": "relieved", "weight": 0.45, "evidence": "缓和关键词"},
    {"signal": "上文场景包含 [Delay]", "emotion": "hesitant", "weight": 0.2, "evidence": "剧情停顿指令"},
]


EXAMPLES = [
    {
        "segment_id": 1,
        "speaker": "阿米娅",
        "role": "dialogue",
        "text": "博士，博士！你终于醒了。",
        "emotion": "urgent",
        "intensity": 0.8,
        "speech_verb": "急切地说",
        "narration_prefix": "阿米娅急切地说：",
        "evidence": ["重复称呼", "感叹号"],
    },
    {
        "segment_id": 2,
        "speaker": "阿米娅",
        "role": "dialogue",
        "text": "啊......抱，抱歉。",
        "emotion": "apologetic",
        "intensity": 0.7,
        "speech_verb": "歉疚地说",
        "narration_prefix": "阿米娅歉疚地说：",
        "evidence": ["省略号", "抱歉"],
    },
    {
        "segment_id": 3,
        "speaker": "凯尔希",
        "role": "dialogue",
        "text": "如果你已经决定继续前进，就不要再用沉默逃避答案。",
        "emotion": "determined",
        "intensity": 0.55,
        "speech_verb": "坚定地说",
        "narration_prefix": "凯尔希坚定地说：",
        "evidence": ["命令式语气", "严肃上下文"],
    },
]


VOICE_MAP_TEMPLATE = {
    "阿米娅": {
        "neutral": {"engine": "gpt-sovits", "reference_audio": "voices/amiya/neutral/ref.wav"},
        "urgent": {"engine": "gpt-sovits", "reference_audio": "voices/amiya/urgent/ref.wav"},
        "sad": {"engine": "gpt-sovits", "reference_audio": "voices/amiya/sad/ref.wav"},
    },
    "凯尔希": {
        "neutral": {"engine": "gpt-sovits", "reference_audio": "voices/kaltsit/neutral/ref.wav"},
        "determined": {"engine": "gpt-sovits", "reference_audio": "voices/kaltsit/determined/ref.wav"},
    },
    "旁白": {
        "neutral": {"engine": "edge-tts", "voice": "zh-CN-YunjianNeural", "rate": "+0%", "volume": "+0%"},
        "tense": {"engine": "edge-tts", "voice": "zh-CN-YunjianNeural", "rate": "-5%", "volume": "+0%"},
    },
}


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_rules_markdown(path: Path) -> None:
    lines = [
        "# 情绪标注规则草案",
        "",
        "本文件由 `06_plan_emotion_tagging.py` 生成，用于规划剧情对白的情绪标注策略。",
        "",
        "## 标签",
        "",
        "| emotion | 中文 | 默认表达 | Edge rate | Edge volume |",
        "| --- | --- | --- | --- | --- |",
    ]
    for emotion, item in EMOTION_TAGS.items():
        lines.append(
            f"| `{emotion}` | {item['label']} | {item['speech_verb']} | `{item['edge_rate']}` | `{item['edge_volume']}` |"
        )
    lines.extend(["", "## 规则", "", "| 信号 | emotion | 权重 | 证据 |", "| --- | --- | --- | --- |"])
    for rule in RULES:
        lines.append(f"| {rule['signal']} | `{rule['emotion']}` | {rule['weight']} | {rule['evidence']} |")
    lines.extend(
        [
            "",
            "## 固化方式",
            "",
            "1. 自动规则只生成初始 emotion、intensity、speech_verb 和 evidence。",
            "2. LLM 标注只补充不确定样本，不直接改写原始 text。",
            "3. 人工 override 单独保存，并在 TTS 前覆盖自动结果。",
            "4. Edge TTS 使用 narration_prefix、rate、volume；GPT-SoVITS 使用 speaker + emotion 选择 reference audio。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成情绪标注与多角色演绎规划资产")
    parser.add_argument("--output-dir", default="investigation/docs/generated/emotion", help="输出目录")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "emotion_tags.json", EMOTION_TAGS)
    write_json(output_dir / "speaker_emotion_voice_map.template.json", VOICE_MAP_TEMPLATE)
    write_jsonl(output_dir / "emotion_annotation_examples.jsonl", EXAMPLES)
    write_rules_markdown(output_dir / "emotion_rules.md")
    print(f"已生成情绪标注规划资产：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
