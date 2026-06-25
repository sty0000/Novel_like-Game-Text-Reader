from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from get_text import CrawlError, fetch_story_text, fetch_text
from scripts.parse_story import extract_segments, write_jsonl
from scripts.tts_edge import load_input_text, synthesize


DEFAULT_API = "https://prts.wiki/api.php"
DEFAULT_OVERVIEW_TITLE = "\u5267\u60c5\u4e00\u89c8"
DEFAULT_TXT_DIR = "txt"
DEFAULT_PARSED_DIR = "parsed"
DEFAULT_AUDIO_DIR = "audio"
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


@dataclass(frozen=True)
class StoryEntry:
    title: str
    section: str = ""


__all__ = [
    "StoryEntry",
    "CrawlError",
    "load_story_catalog",
    "choose_story_entry",
    "save_story_bundle",
    "run_selected_story",
    "main",
]


def is_story_title(title: str) -> bool:
    return bool(re.search(r"/(BEG|END|NBT|AFTER|BEFORE|STORY)$", title, flags=re.IGNORECASE))


def story_section(title: str) -> str:
    if "/" in title:
        return title.rsplit("/", 1)[0]
    return ""


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name)
    cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")
    return cleaned or "story"


def load_story_catalog(overview_title: str = DEFAULT_OVERVIEW_TITLE) -> list[StoryEntry]:
    query = urlencode(
        {
            "action": "parse",
            "page": overview_title,
            "prop": "links",
            "format": "json",
            "formatversion": "2",
        }
    )
    payload = fetch_text(f"{DEFAULT_API}?{query}")
    data = json.loads(payload)
    links = data.get("parse", {}).get("links", [])

    entries: list[StoryEntry] = []
    seen_titles: set[str] = set()
    for link in links:
        title = link.get("title", "").strip()
        if link.get("ns") != 0 or not title or not link.get("exists"):
            continue
        if not is_story_title(title):
            continue
        key = title.casefold()
        if key in seen_titles:
            continue
        entries.append(StoryEntry(title=title, section=story_section(title)))
        seen_titles.add(key)

    if not entries:
        raise CrawlError("\u672a\u80fd\u4ece\u5267\u60c5\u4e00\u89c8\u4e2d\u89e3\u6790\u51fa\u53ef\u9009\u5267\u60c5")
    return entries


def format_entry(entry: StoryEntry, index: int) -> str:
    section = f" [{entry.section}]" if entry.section else ""
    return f"{index:>3}. {entry.title}{section}"


def filter_entries(entries: list[StoryEntry], keyword: str) -> list[StoryEntry]:
    normalized = keyword.casefold()
    return [
        entry
        for entry in entries
        if normalized in entry.title.casefold() or normalized in entry.section.casefold()
    ]


def choose_story_entry(entries: list[StoryEntry]) -> StoryEntry:
    print(f"\u5df2\u8f7d\u5165 {len(entries)} \u6761\u5267\u60c5\u3002")
    print("\u8f93\u5165\u5173\u952e\u8bcd\u7b5b\u9009\uff0c\u4f8b\u5982\uff1a\u5e8f\u7ae0\u30010-1\u3001\u5760\u6b7b\u3001SS\u3001ZT\u3001BEG\u3002")
    print("\u8f93\u5165 all \u663e\u793a\u5168\u90e8\uff1b\u8f93\u5165 q \u9000\u51fa\u3002")

    filtered = entries
    while True:
        if filtered:
            print("\n\u5f53\u524d\u5339\u914d\uff1a")
            for index, entry in enumerate(filtered[:80], start=1):
                print(format_entry(entry, index))
            if len(filtered) > 80:
                print(f"\u2026\u2026\u8fd8\u6709 {len(filtered) - 80} \u6761\uff0c\u8bf7\u7ee7\u7eed\u7f29\u5c0f\u8303\u56f4\u3002")

        choice = input("\n\u8bf7\u8f93\u5165\u5173\u952e\u8bcd\u6216\u5e8f\u53f7\uff1a").strip()
        if not choice or choice.casefold() == "q":
            raise CrawlError("\u672a\u9009\u62e9\u4efb\u4f55\u5267\u60c5")

        if choice.casefold() == "all":
            filtered = entries
            continue

        if choice.isdigit() and filtered:
            index = int(choice)
            if 1 <= index <= min(len(filtered), 80):
                return filtered[index - 1]
            print("\u5e8f\u53f7\u65e0\u6548\uff0c\u8bf7\u91cd\u8bd5\u3002")
            continue

        matches = filter_entries(entries, choice)
        if not matches:
            print("\u6ca1\u6709\u627e\u5230\u5339\u914d\u9879\uff0c\u8bf7\u91cd\u8bd5\u3002")
            continue
        if len(matches) == 1:
            return matches[0]
        filtered = matches


def save_story_bundle(
    title: str,
    raw_text: str,
    txt_path: Path,
    parsed_path: Path,
    audio_path: Path,
    voice: str,
    rate: str,
    volume: str,
    text_field: str,
    speak_speaker_prefix: bool,
) -> None:
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(raw_text, encoding="utf-8")

    segments = extract_segments(raw_text, title, txt_path.name)
    if not segments:
        raise CrawlError("\u672a\u80fd\u4ece\u5267\u60c5\u6e90\u7801\u4e2d\u89e3\u6790\u51fa\u6709\u6548\u7247\u6bb5")
    write_jsonl(segments, parsed_path)

    tts_text = load_input_text(parsed_path, "jsonl", text_field, speak_speaker=speak_speaker_prefix)
    if not tts_text.strip():
        raise CrawlError("\u89e3\u6790\u540e\u7684\u6587\u672c\u4e3a\u7a7a\uff0c\u65e0\u6cd5\u751f\u6210\u97f3\u9891")

    asyncio.run(synthesize(tts_text, audio_path, voice, rate, volume))


def run_selected_story(
    title: str,
    timeout: int,
    txt_dir: str,
    parsed_dir: str,
    audio_dir: str,
    voice: str,
    rate: str,
    volume: str,
    text_field: str,
    speak_speaker_prefix: bool,
) -> None:
    raw_text = fetch_story_text(title, timeout=timeout)
    base_name = sanitize_filename(title)

    txt_path = Path(txt_dir) / f"{base_name}.txt"
    parsed_path = Path(parsed_dir) / f"{base_name}.segments.jsonl"
    audio_path = Path(audio_dir) / f"{base_name}.mp3"

    save_story_bundle(
        title=title,
        raw_text=raw_text,
        txt_path=txt_path,
        parsed_path=parsed_path,
        audio_path=audio_path,
        voice=voice,
        rate=rate,
        volume=volume,
        text_field=text_field,
        speak_speaker_prefix=speak_speaker_prefix,
    )

    print(f"\u5df2\u4fdd\u5b58\u6e90\u7801\uff1a{txt_path}", file=sys.stderr)
    print(f"\u5df2\u4fdd\u5b58\u7ed3\u6784\u5316\u6587\u6863\uff1a{parsed_path}", file=sys.stderr)
    print(f"\u5df2\u4fdd\u5b58\u97f3\u9891\uff1a{audio_path}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="\u4ece PRTS wiki \u9009\u62e9\u5267\u60c5\u5e76\u5bfc\u51fa\u6e90\u7801\u3001\u7ed3\u6784\u5316\u6587\u6863\u548c\u97f3\u9891")
    parser.add_argument("source", nargs="?", help="\u5df2\u77e5\u5267\u60c5\u6807\u9898\u6216\u5267\u60c5 URL\uff1b\u4e0d\u63d0\u4f9b\u5219\u8fdb\u5165\u9009\u62e9\u6a21\u5f0f")
    parser.add_argument("--overview-title", default=DEFAULT_OVERVIEW_TITLE, help="\u5267\u60c5\u4e00\u89c8\u9875\u9762\u6807\u9898")
    parser.add_argument("--timeout", type=int, default=20, help="\u7f51\u7edc\u8d85\u65f6\u79d2\u6570")
    parser.add_argument("--list", action="store_true", help="\u4ec5\u5217\u51fa\u53ef\u9009\u5267\u60c5")
    parser.add_argument("--txt-dir", default=DEFAULT_TXT_DIR, help="\u6e90\u7801\u8f93\u51fa\u76ee\u5f55")
    parser.add_argument("--parsed-dir", default=DEFAULT_PARSED_DIR, help="\u7ed3\u6784\u5316\u6587\u6863\u8f93\u51fa\u76ee\u5f55")
    parser.add_argument("--audio-dir", default=DEFAULT_AUDIO_DIR, help="\u97f3\u9891\u8f93\u51fa\u76ee\u5f55")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Edge TTS voice \u540d\u79f0")
    parser.add_argument("--rate", default="+0%", help="\u8bed\u901f\uff0c\u4f8b\u5982 +0%%\u3001-10%%\u3001+15%%")
    parser.add_argument("--volume", default="+0%", help="\u97f3\u91cf\uff0c\u4f8b\u5982 +0%%")
    parser.add_argument("--text-field", default="text", help="JSONL \u8f93\u5165\u4e2d\u7528\u4e8e\u5408\u6210\u7684\u5b57\u6bb5\u540d")
    parser.add_argument("--no-speaker-prefix", action="store_true", help="\u5173\u95ed\u5bf9\u8bdd\u524d\u7684\u201cxxx\u8bf4\uff1a\u201d\u524d\u7f00")
    args = parser.parse_args()

    try:
        if args.source:
            run_selected_story(
                args.source,
                args.timeout,
                args.txt_dir,
                args.parsed_dir,
                args.audio_dir,
                args.voice,
                args.rate,
                args.volume,
                args.text_field,
                not args.no_speaker_prefix,
            )
            return 0

        catalog = load_story_catalog(args.overview_title)
        if args.list:
            for index, entry in enumerate(catalog, start=1):
                print(format_entry(entry, index))
            return 0

        selected = choose_story_entry(catalog)
        print(f"\u5df2\u9009\u62e9\uff1a{selected.title}", file=sys.stderr)
        run_selected_story(
            selected.title,
            args.timeout,
            args.txt_dir,
            args.parsed_dir,
            args.audio_dir,
            args.voice,
            args.rate,
            args.volume,
            args.text_field,
            not args.no_speaker_prefix,
        )
        return 0
    except CrawlError as error:
        print(f"\u9519\u8bef: {error}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as error:
        print(f"\u9519\u8bef: API \u8fd4\u56de\u7684\u4e0d\u662f\u6709\u6548 JSON: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
