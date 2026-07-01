from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Iterable, Optional

from scripts.emotion_classifier.rules import detect_emotion

# 可选：如果训练了 ML 模型，取消下面这行注释即可使用
#from scripts.emotion_classifier import EmotionClassifier
#_classifier = EmotionClassifier()
#def detect_emotion(text: str) -> str:
    #return _classifier.predict(text)


# ── 差分图情绪缓存 ──────────────────────────────────────

_SPRITE_CACHE: dict[str, tuple[str, float]] = {}
_SPRITE_CACHE_LOADED = False


def _load_sprite_cache() -> None:
    global _SPRITE_CACHE_LOADED
    if _SPRITE_CACHE_LOADED:
        return
    path = Path("sprite_emotions.csv")
    if path.exists():
        with path.open(encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                code = row.get("code", "").strip()
                emo = row.get("emotion", "").strip()
                conf = float(row.get("confidence", 0))
                if code and emo:
                    _SPRITE_CACHE[code] = (emo, conf)
        print(f"已加载 {len(_SPRITE_CACHE)} 条差分图情绪缓存", file=sys.stderr)
    _SPRITE_CACHE_LOADED = True


def _sprite_emotion(sprite_code: str) -> Optional[tuple[str, float]]:
    """查 sprite_emotions.csv 获取 (图片情绪, 置信度)。"""
    if not sprite_code:
        return None
    _load_sprite_cache()
    return _SPRITE_CACHE.get(sprite_code)


# 7 类 FER 面部表情 → 相容的 18 类文本情绪
# neutral 面部表情：所有情绪都可能，不加任何权重
# 非 neutral 面部表情：只对"说得通"的情绪给加成
_FACE_COMPATIBLE: dict[str, set[str]] = {
    "neutral":   set(),  # 中性脸 → 不加成，文本说了算
    "happy":     {"happy", "laugh", "gentle", "relieved"},
    "sad":       {"sad", "sigh", "desperate", "gentle"},
    "angry":     {"angry", "determined", "arrogant", "serious"},
    "surprise":  {"shocked", "shock_question", "fearful"},
    "fear":      {"fearful", "desperate", "urgent"},
    "disgust":   {"angry", "arrogant", "serious"},
}


def _combine_emotions(text_emo: str, sprite_emo: Optional[str],
                      confidence: float = 0.0) -> str:
    """文本情绪 + 差分图面部表情 + 置信度 → 加权融合。

    规则（按优先级）：
    - 无差分图或置信度 < 0.35 → 文本决定（脸不可靠）
    - 面部中性 → 不加成，文本决定
    - 高置信度 (≥0.6) + 相容 → 用图片信号（脸很明显）
    - 高置信度 (≥0.6) + 文本中性 → 用图片信号
    - 面部与文本相容 → 确认，用文本
    - 冲突 → 文本优先
    """
    if not sprite_emo or confidence < 0.35:
        return text_emo

    # 中性脸不加成任何情绪
    if sprite_emo == "neutral":
        return text_emo

    # 高置信度：图片信号比文本更有参考价值
    if confidence >= 0.6:
        # 文本中性 → 采纳图片
        if text_emo == "neutral":
            return sprite_emo
        # 相容 → 用图片
        if text_emo == sprite_emo or text_emo in _FACE_COMPATIBLE.get(sprite_emo, set()):
            return sprite_emo

    # 中置信度 (0.5-0.8)：相容则确认，冲突则文本优先
    if text_emo == sprite_emo or text_emo in _FACE_COMPATIBLE.get(sprite_emo, set()):
        return text_emo

    if text_emo == "neutral":
        return sprite_emo

    return text_emo


# ── Constants ──────────────────────────────────────────────

DEFAULT_SPEECH_SUFFIX = "："


# ── Modifier table ─────────────────────────────────────────

# Map: (base, emotion) → modifier phrase (without speaker or colon)
_MODIFIER_MAP: dict[tuple[str, str], str] = {
    # ── speak (default, speaker changes) ──
    ("speak", "neutral"): "说",
    ("speak", "question"): "问道",
    ("speak", "shock_question"): "质问道",
    ("speak", "shocked"): "震惊的说",
    ("speak", "angry"): "愤怒的说",
    ("speak", "happy"): "开心的说",
    ("speak", "sad"): "悲伤的说",
    ("speak", "fearful"): "恐惧的说",
    ("speak", "ponder"): "思索着说",
    ("speak", "hesitate"): "迟疑的说",
    ("speak", "sigh"): "叹道",
    ("speak", "laugh"): "笑道",
    ("speak", "determined"): "坚定的说",
    ("speak", "arrogant"): "傲慢的说",
    ("speak", "gentle"): "温柔的说",
    ("speak", "urgent"): "急切的说",
    ("speak", "desperate"): "绝望的说",
    ("speak", "relieved"): "松了口气说",
    ("speak", "serious"): "严肃的说",
    ("speak", "disgusted"): "厌恶的说",
    # ── continue (same speaker speaks again) ──
    ("continue", "neutral"): "接着说",
    ("continue", "question"): "接着问道",
    ("continue", "shock_question"): "接着质问道",
    ("continue", "shocked"): "接着震惊的说",
    ("continue", "angry"): "接着愤怒的说",
    ("continue", "happy"): "接着开心的说",
    ("continue", "sad"): "接着悲伤的说",
    ("continue", "fearful"): "接着恐惧的说",
    ("continue", "ponder"): "接着思索道",
    ("continue", "hesitate"): "接着迟疑的说",
    ("continue", "sigh"): "接着叹道",
    ("continue", "laugh"): "接着笑道",
    ("continue", "determined"): "接着坚定的说",
    ("continue", "arrogant"): "接着傲慢的说",
    ("continue", "gentle"): "接着温柔的说",
    ("continue", "urgent"): "接着急切的说",
    ("continue", "desperate"): "接着绝望的说",
    ("continue", "relieved"): "接着松了口气说",
    ("continue", "serious"): "接着严肃的说",
    ("continue", "disgusted"): "接着厌恶的说",
    # ── scene_first (first dialogue after scene change) ──
    ("scene_first", "neutral"): "开口道",
    ("scene_first", "question"): "开口问道",
    ("scene_first", "shock_question"): "开口质问道",
    ("scene_first", "shocked"): "震惊的开口",
    ("scene_first", "angry"): "愤怒的开口",
    ("scene_first", "happy"): "开心的开口",
    ("scene_first", "sad"): "悲伤的开口",
    ("scene_first", "fearful"): "恐惧的开口",
    ("scene_first", "ponder"): "沉吟道",
    ("scene_first", "hesitate"): "迟疑的开口",
    ("scene_first", "sigh"): "叹着气开口",
    ("scene_first", "laugh"): "开口笑道",
    ("scene_first", "determined"): "坚定的开口",
    ("scene_first", "arrogant"): "傲慢的开口",
    ("scene_first", "gentle"): "温柔的开口",
    ("scene_first", "urgent"): "急切的开口",
    ("scene_first", "desperate"): "绝望的开口",
    ("scene_first", "relieved"): "如释重负的开口",
    ("scene_first", "serious"): "严肃的开口",
    ("scene_first", "disgusted"): "厌恶的开口",
    # ── retort (A→B→A, A replies back sharply) ──
    ("retort", "neutral"): "反驳道",
    ("retort", "question"): "反问",
    ("retort", "shock_question"): "震惊的反问",
    ("retort", "shocked"): "震惊的反驳",
    ("retort", "angry"): "愤怒的反驳",
    ("retort", "happy"): "笑着反驳",
    ("retort", "sad"): "悲伤的反驳",
    ("retort", "fearful"): "恐惧的反驳",
    ("retort", "ponder"): "沉吟着反驳",
    ("retort", "hesitate"): "迟疑的反驳",
    ("retort", "sigh"): "叹着气反驳",
    ("retort", "laugh"): "笑着反驳",
    ("retort", "determined"): "坚定的反驳",
    ("retort", "arrogant"): "傲慢的反驳",
    ("retort", "gentle"): "温柔的反驳",
    ("retort", "urgent"): "急切的驳斥",
    ("retort", "desperate"): "绝望的反驳",
    ("retort", "relieved"): "松了口气反驳",
    ("retort", "serious"): "严肃的反驳",
    ("retort", "disgusted"): "厌恶的反驳",
    # ── respond (new speaker replies to someone) ──
    ("respond", "neutral"): "回应道",
    ("respond", "question"): "回应着问道",
    ("respond", "shock_question"): "震惊的回应",
    ("respond", "shocked"): "震惊的回应",
    ("respond", "angry"): "愤怒的回应",
    ("respond", "happy"): "开心的回应",
    ("respond", "sad"): "悲伤的回应",
    ("respond", "fearful"): "恐惧的回应",
    ("respond", "ponder"): "思索着回应",
    ("respond", "hesitate"): "迟疑的回应",
    ("respond", "sigh"): "叹着气回应",
    ("respond", "laugh"): "笑着回应",
    ("respond", "determined"): "坚定的回应",
    ("respond", "arrogant"): "傲慢的回应",
    ("respond", "gentle"): "温柔的回应",
    ("respond", "urgent"): "急切的回应",
    ("respond", "desperate"): "绝望的回应",
    ("respond", "relieved"): "松了口气回应",
    ("respond", "serious"): "严肃的回应",
    ("respond", "disgusted"): "厌恶的回应",
    # ── aside (parenthetical whisper / inner thought) ──
    ("aside", "neutral"): "轻声说",
    ("aside", "question"): "轻声问道",
    ("aside", "shock_question"): "低声惊呼",
    ("aside", "shocked"): "低声惊呼",
    ("aside", "angry"): "低声怒道",
    ("aside", "happy"): "轻声笑道",
    ("aside", "sad"): "低声叹道",
    ("aside", "fearful"): "声音发颤的说",
    ("aside", "ponder"): "低声沉吟",
    ("aside", "hesitate"): "欲言又止",
    ("aside", "sigh"): "轻叹一声",
    ("aside", "laugh"): "轻笑一声",
    ("aside", "determined"): "暗暗下定决心",
    ("aside", "arrogant"): "傲慢的冷哼",
    ("aside", "gentle"): "柔声说",
    ("aside", "urgent"): "急促的低语",
    ("aside", "desperate"): "绝望的低喃",
    ("aside", "relieved"): "舒了口气",
    ("aside", "serious"): "严肃的低语",
    ("aside", "disgusted"): "厌恶的低声",
}


def build_speech_prefix(speaker: str, base: str, emotion: str) -> str:
    """Build the full speech prefix, e.g. '推进之王反驳道：'."""
    modifier = _MODIFIER_MAP.get(
        (base, emotion),
        _MODIFIER_MAP.get((base, "neutral"), "说"),
    )
    return f"{speaker}{modifier}{DEFAULT_SPEECH_SUFFIX}"


# ── Context analysis helpers ───────────────────────────────


def _find_prev_dialogue(segments: list[dict], before_idx: int) -> Optional[dict]:
    """Find the most recent dialogue segment before *before_idx*."""
    for i in range(before_idx - 1, -1, -1):
        if segments[i].get("role") == "dialogue":
            return segments[i]
    return None


def _find_nth_prev_dialogue(segments: list[dict], before_idx: int, n: int) -> Optional[dict]:
    """Find the n-th most recent dialogue segment (1 = immediate previous)."""
    count = 0
    for i in range(before_idx - 1, -1, -1):
        if segments[i].get("role") == "dialogue":
            count += 1
            if count == n:
                return segments[i]
    return None


def _looks_like_retort(text: str, emotion: str) -> bool:
    """Check whether the text content signals the speaker is pushing back.

    ``emotion`` is the pre-computed emotional tone from
    :func:`~scripts.emotion_classifier.rules.detect_emotion`.
    """
    # Strong confrontational emotions are retort-like by nature
    if emotion in ("angry", "shock_question", "arrogant", "disgusted"):
        return True

    # Text-level disagreement / push-back markers
    _RETORT_MARKERS = (
        "不，", "不对", "不可能", "不是", "不，不是",
        "没有", "别", "胡说", "荒谬", "荒唐",
        "你怎么知道", "你凭什么", "你才", "你在说什么",
        "闭嘴", "住口",
        "我不同意", "我反对", "我不能接受",
        "你说反了", "搞错了", "误会了",
        "怎么", "凭什么", "为什么是",
        "我才不", "我可不",
    )
    trimmed = text.strip()
    for marker in _RETORT_MARKERS:
        if marker in trimmed[:20]:
            return True

    return False


def _classify_back_and_forth(
    segments: list[dict],
    current_idx: int,
    current_speaker: str,
    current_text: str,
    current_emotion: str,
) -> Optional[str]:
    """Decide whether a speaker-change is a retort, simple respond, or fresh.

    Returns ``"retort"`` only when there is evidence that the speaker is
    pushing back (angry tone, explicit disagreement markers).
    Otherwise returns ``"respond"`` for a natural reply in an exchange,
    or ``None`` for the opening move of a conversation.
    """
    prev_dialogue = _find_prev_dialogue(segments, current_idx)
    if prev_dialogue is None:
        return None  # First dialogue in the whole story

    prev_speaker = prev_dialogue.get("speaker", "")

    # Same speaker — not a back-and-forth (handled by 'continue' branch)
    if prev_speaker == current_speaker:
        return None

    # Look two dialogues back to detect A→B→A
    prev_prev_dialogue = _find_nth_prev_dialogue(segments, current_idx, 2)
    if prev_prev_dialogue is None:
        # Only one prior dialogue speaker — this is a reply, not a retort
        return "respond"

    prev_prev_speaker = prev_prev_dialogue.get("speaker", "")

    if prev_prev_speaker == current_speaker:
        # A → B → A pattern — check if A is really pushing back
        if _looks_like_retort(current_text, current_emotion):
            return "retort"
        return "respond"

    # New speaker entering a conversation
    return "respond"


# ── Text / speaker pre-processing ────────────────────────

import re as _re

_PAREN_RE = _re.compile(r"[（(][^）)]*[）)]")


def _classify_parenthetical(paren_text: str) -> str:
    """Classify a parenthetical's content: ``"direction"`` or ``"aside"``.

    * **direction** — stage direction / physical action; should NOT be spoken.
    * **aside** — whispered remark, inner thought, or asides; should be spoken
      with a softer / thinking tone.
    """
    inner = paren_text.strip("()（）").strip()
    if not inner:
        return "direction"

    # Stage directions: no emotional punctuation, describe physical actions
    has_emotional_punct = bool(_re.search(r"[！!？?…….]", inner))
    if not has_emotional_punct:
        # Short action descriptions
        _ACTION_VERBS = ("将", "把", "砸", "拉", "推", "走", "跑", "跳", "举",
                         "放", "拿", "抓", "打", "踢", "踩", "拔", "砍", "射",
                         "冲", "撞", "转", "抬", "挥", "扔", "丢", "掏")
        if any(inner.startswith(v) for v in _ACTION_VERBS):
            return "direction"
        if len(inner) <= 8:
            return "direction"

    # Anything with emotional content → aside (whisper / inner thought)
    return "aside"


def _extract_parentheticals(text: str) -> dict:
    """Detect parenthetical content and return analysis + clean text.

    Returns::

        {
            "has_paren": bool,
            "paren_type": "direction" | "aside" | None,
            "paren_text": str | None,
            "clean_text": str,          # text with parens stripped
        }
    """
    matches = _PAREN_RE.findall(text)
    if not matches:
        return {
            "has_paren": False,
            "paren_type": None,
            "paren_text": None,
            "clean_text": text,
        }

    # Classify each parenthetical; use the most "significant" type
    types = [_classify_parenthetical(m) for m in matches]
    paren_type = "aside" if "aside" in types else "direction"

    # Remove all parentheticals for clean TTS text
    clean = _PAREN_RE.sub("", text).strip()
    # Collapse multiple spaces left by removed parens
    clean = _re.sub(r" {2,}", " ", clean)

    # If the ENTIRE text was inside parens, clean_text will be empty;
    # in that case keep the inner text (it IS the dialogue — an aside)
    if not clean:
        inner = text.strip("()（）").strip()
        if inner:
            clean = inner
            paren_type = "aside"

    return {
        "has_paren": True,
        "paren_type": paren_type,
        "paren_text": " | ".join(matches),
        "clean_text": clean,
    }


def _is_silence(text: str) -> bool:
    """Return True if the text represents silence rather than speech."""
    cleaned = text.strip().replace(" ", "").replace("\n", "")
    if not cleaned:
        return True
    # Only dots, ellipsis, or dashes → silence
    if all(c in "......……——-—" for c in cleaned):
        return True
    return False


def _analyze_speaker(raw_speaker: str) -> dict:
    """Analyse the raw speaker field and return a *descriptive* display name
    suitable for a storyteller / 说书人 narration.

    Returns::

        {
            "display_name": str,   # ready-to-speak descriptive label
            "identity": str,       # "known" | "unknown" | "uncertain" | "title"
        }
    """
    speaker = raw_speaker.strip()

    # ？？？ → mysterious unknown speaker
    if speaker == "？？？" or speaker == "???":
        return {"display_name": "神秘人", "identity": "unknown"}

    # Name ending with ？ or ? → uncertain identity
    if speaker.endswith("？") or speaker.endswith("?"):
        clean = speaker.rstrip("？?")
        return {"display_name": f"那个像是{clean}的人", "identity": "uncertain"}

    # Quoted title/epithet (e.g. "皇帝的利刃")
    if speaker.startswith('"') and speaker.endswith('"'):
        return {"display_name": speaker, "identity": "title"}

    return {"display_name": speaker, "identity": "known"}


# ── Stage direction → narration helper ──────────────────


def _direction_to_narration(paren_text: str, attributed_speaker: str) -> str:
    """Convert a parenthetical stage direction to a narration sentence.

    e.g. ``"(将盾牌狠狠砸入地面)"`` + ``"盾卫"``
      → ``"盾卫将盾牌狠狠砸入地面。"``
    """
    inner = paren_text.strip("()（）").strip()
    if not inner:
        return ""
    # Use the attributed speaker as the subject when available
    if attributed_speaker and attributed_speaker not in ("旁白", "？？？", "???"):
        return f"{attributed_speaker}{inner}。"
    return f"{inner}。"


# ── Main enrichment entry point ────────────────────────────


def enrich_segments(segments: list[dict]) -> list[dict]:
    """Add a ``speech_prefix`` field to every segment, handling the text
    as a story-telling / 说书人 script.

    Transformations applied:

    * **Stage directions** ``(动作)`` → inserted as standalone narration
      segments so the narrator *describes* the action.
    * **Parenthetical asides** ``（轻声讨论）`` → spoken with a
      whispered / thinking modifier (``"轻声说"`` etc.).
    * **Unknown speakers** ``？？？`` → narrated as ``"一个声音说："``.
    * **Uncertain speakers** ``name？`` → ``"那个像是name的人说："``.
    * **Silence** ``......`` → marked ``is_silence`` so TTS can skip
      (the surrounding narration already carries the story).

    The output list may be *longer* than the input because stage
    directions are expanded into separate narration segments.
    """
    enriched: list[dict] = []

    prev_speaker: Optional[str] = None
    prev_scene_id: Optional[int] = None
    speaker_continue_count = 0
    last_real_speaker = ""  # track last known speaker for action attribution

    for i, seg in enumerate(segments):
        seg = dict(seg)  # shallow copy
        role = seg.get("role", "")
        speaker = seg.get("speaker", "")
        text = seg.get("text", "")
        scene_id = seg.get("scene_id")

        if role != "dialogue":
            seg["speech_prefix"] = ""
            enriched.append(seg)
            prev_speaker = None
            speaker_continue_count = 0
            continue

        # ── Silence ──────────────────────────────────────
        if _is_silence(text):
            seg["speech_prefix"] = ""
            seg["is_silence"] = True
            enriched.append(seg)
            continue

        seg["is_silence"] = False

        # ── Parenthetical analysis ───────────────────────
        paren_info = _extract_parentheticals(text)
        seg["has_paren"] = paren_info["has_paren"]
        seg["paren_type"] = paren_info["paren_type"]
        working_text = paren_info["clean_text"]

        # ── Speaker identity ─────────────────────────────
        spkr_info = _analyze_speaker(speaker)
        seg["speaker_display"] = spkr_info["display_name"]
        seg["identity"] = spkr_info["identity"]

        # Track the "real" speaker for action attribution
        if spkr_info["identity"] in ("known", "uncertain", "title"):
            last_real_speaker = spkr_info["display_name"]

        # ── Stage direction → narration ──────────────────
        if paren_info["has_paren"] and paren_info["paren_type"] == "direction":
            direction_text = _direction_to_narration(
                paren_info["paren_text"],
                last_real_speaker or prev_speaker or "",
            )
            if direction_text:
                # Insert a narration segment *before* the dialogue
                enriched.append({
                    "role": "narration",
                    "speaker": "旁白",
                    "text": direction_text,
                    "speech_prefix": "",
                    "story_title": seg.get("story_title", ""),
                    "segment_id": f"{seg.get('segment_id', '')}-dir",
                    "source_file": seg.get("source_file", ""),
                    "scene_id": seg.get("scene_id"),
                    "is_generated": True,
                })

            # If the entire text WAS the direction, skip dialogue
            if not working_text:
                prev_speaker = None
                speaker_continue_count = 0
                continue

        # ── Emotion: text + sprite fusion ────────────────
        emotion = detect_emotion(working_text)
        # 如果有差分图情绪，加权融合
        sprite_code = seg.get("sprite_code", "")
        if sprite_code:
            result = _sprite_emotion(sprite_code)
            if result:
                sprite_emo, confidence = result
                emotion = _combine_emotions(emotion, sprite_emo, confidence)

        is_scene_change = scene_id is not None and scene_id != prev_scene_id

        if paren_info["paren_type"] == "aside":
            # Override: parenthetical speech → whispered / thinking
            base = "aside"
            speaker_continue_count = 1
        elif is_scene_change:
            base = "scene_first"
            speaker_continue_count = 1
        elif speaker == prev_speaker:
            speaker_continue_count += 1
            base = "continue"
        else:
            baf = _classify_back_and_forth(
                enriched, len(enriched), speaker, working_text, emotion
            )
            base = baf or "speak"
            speaker_continue_count = 1

        seg["speech_prefix"] = build_speech_prefix(
            spkr_info["display_name"], base, emotion
        )
        seg["emotion"] = emotion
        seg["tts_text"] = working_text

        prev_speaker = speaker
        prev_scene_id = scene_id

        # ── Merge consecutive same-speaker + same-emotion ──
        if (
            enriched
            and not is_scene_change
            and paren_info["paren_type"] != "aside"
        ):
            last = enriched[-1]
            if (
                last.get("role") == "dialogue"
                and not last.get("is_generated")
                and last.get("speaker") == speaker
                and last.get("emotion") == emotion
            ):
                # Merge into previous segment
                last["tts_text"] = last["tts_text"] + "\n" + working_text
                last["text"] = last.get("text", "") + "\n" + working_text
                last["line_end"] = seg.get("line_end", last.get("line_end", 0))
                continue

        enriched.append(seg)

    return enriched


# ── File I/O helpers (re-usable from parse_story / tts_edge) ──


def load_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file into a list of dicts."""
    segments: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                segments.append(json.loads(line))
    return segments


def write_jsonl(segments: Iterable[dict], path: Path) -> None:
    """Write enriched segments to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for seg in segments:
            handle.write(json.dumps(seg, ensure_ascii=False) + "\n")


# ── CLI ────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add context-aware speech prefixes to parsed story segments"
    )
    parser.add_argument("input", help="Input .segments.jsonl file")
    parser.add_argument("-o", "--output", help="Output enriched JSONL file")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else None

    try:
        segments = load_jsonl(input_path)
        if not segments:
            raise ValueError("输入 JSONL 为空")

        enriched = enrich_segments(segments)
        out = output_path or input_path.with_suffix(".enriched.jsonl")
        write_jsonl(enriched, out)
        print(f"已保存到 {out}", file=sys.stderr)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
