from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from get_text import CrawlError, fetch_story_text, fetch_text


DEFAULT_API = "https://prts.wiki/api.php"
DEFAULT_OVERVIEW_TITLE = "剧情一览"


@dataclass(frozen=True)
class StoryEntry:
    title: str
    section: str = ""


__all__ = [
    "StoryEntry",
    "CrawlError",
    "load_story_catalog",
    "choose_story_entry",
    "default_output_path",
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


def default_output_path(title: str) -> str:
    return f"{sanitize_filename(title)}.txt"


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
        raise CrawlError("未能从剧情一览中解析出可选剧情")
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
    print(f"已载入 {len(entries)} 条剧情。")
    print("输入关键词筛选，例如：序章、0-1、坍塌、SS、ZT、BEG。")
    print("输入 all 显示全部；输入 q 退出。")

    filtered = entries
    while True:
        if filtered:
            print("\n当前匹配：")
            for index, entry in enumerate(filtered[:80], start=1):
                print(format_entry(entry, index))
            if len(filtered) > 80:
                print(f"……还有 {len(filtered) - 80} 条，请继续缩小范围。")

        choice = input("\n请输入关键词或序号：").strip()
        if not choice or choice.casefold() == "q":
            raise CrawlError("未选择任何剧情")

        if choice.casefold() == "all":
            filtered = entries
            continue

        if choice.isdigit() and filtered:
            index = int(choice)
            if 1 <= index <= min(len(filtered), 80):
                return filtered[index - 1]
            print("序号无效，请重试。")
            continue

        matches = filter_entries(entries, choice)
        if not matches:
            print("没有找到匹配项，请重试。")
            continue
        if len(matches) == 1:
            return matches[0]
        filtered = matches


def write_output(text: str, output: str) -> None:
    Path(output).write_text(text, encoding="utf-8")


def run_selected_story(title: str, output: Optional[str], timeout: int) -> None:
    resolved_output = output or default_output_path(title)
    text = fetch_story_text(title, timeout=timeout)
    write_output(text, resolved_output)
    print(f"已保存到 {resolved_output}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="从 PRTS wiki 选择并导出单个剧情源码")
    parser.add_argument("source", nargs="?", help="已知剧情标题或剧情 URL；不提供则进入选择模式")
    parser.add_argument("-o", "--output", help="保存到文件")
    parser.add_argument("--overview-title", default=DEFAULT_OVERVIEW_TITLE, help="剧情一览页面标题")
    parser.add_argument("--timeout", type=int, default=20, help="网络超时秒数")
    parser.add_argument("--list", action="store_true", help="仅列出可选剧情")
    args = parser.parse_args()

    try:
        if args.source:
            run_selected_story(args.source, args.output, args.timeout)
            return 0

        catalog = load_story_catalog(args.overview_title)
        if args.list:
            for index, entry in enumerate(catalog, start=1):
                print(format_entry(entry, index))
            return 0

        selected = choose_story_entry(catalog)
        print(f"已选择：{selected.title}", file=sys.stderr)
        run_selected_story(selected.title, args.output, args.timeout)
        return 0
    except CrawlError as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as error:
        print(f"错误: API 返回的不是有效 JSON: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
