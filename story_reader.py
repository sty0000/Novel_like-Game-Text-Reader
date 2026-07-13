from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from get_text import CrawlError, fetch_story_text, fetch_text
from scripts.parse_story import extract_segments
from scripts.speech_modifier import enrich_segments, write_jsonl as write_enriched_jsonl
from scripts.tts_edge import load_input_text, synthesize


DEFAULT_API = "https://prts.wiki/api.php"
DEFAULT_OVERVIEW_TITLE = "剧情一览"
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


def load_story_catalog(overview_title: str = DEFAULT_OVERVIEW_TITLE, timeout: int = 20) -> list[StoryEntry]:
    query = urlencode(
        {
            "action": "parse",
            "page": overview_title,
            "prop": "links",
            "format": "json",
            "formatversion": "2",
        }
    )
    payload = fetch_text(f"{DEFAULT_API}?{query}", timeout=timeout)
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
    print("输入关键词筛选，例如：序章、0-1、坠死、SS、ZT、BEG。")
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
    tts_engine: str = "cosyvoice",
    cosyvoice_model_dir: str = "CosyVoice/pretrained_models/CosyVoice2-0.5B",
    cosyvoice_map: str = "voice_map.json",
    cosy_python: str = "D:/Anaconda/envs/cosy/python.exe",
    narrator_voice: str = "zh-CN-YunjianNeural",
    narrator_pause_ms: int = 250,
) -> None:
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(raw_text, encoding="utf-8")

    # 1. Parse raw wiki text into structured segments
    raw_segments = extract_segments(raw_text, title, txt_path.name)
    if not raw_segments:
        raise CrawlError("未能从剧情源码中解析出有效片段")

    # 2. Enrich with context-aware speech prefixes
    from dataclasses import asdict
    segment_dicts = [asdict(seg) for seg in raw_segments]
    enriched = enrich_segments(segment_dicts)
    write_enriched_jsonl(enriched, parsed_path)

    if tts_engine == "skip":
        return

    # 3. Build TTS text from enriched segments
    tts_text = load_input_text(parsed_path, "jsonl", text_field)
    if not tts_text.strip():
        raise CrawlError("解析后的文本为空，无法生成音频")

    if tts_engine == "edge":
        asyncio.run(synthesize(tts_text, audio_path, voice, rate, volume))
    elif tts_engine == "cosyvoice":
        _run_cosyvoice_subprocess(
            parsed_path, audio_path, cosyvoice_model_dir,
            cosyvoice_map, cosy_python,
            narrator_voice=narrator_voice,
            edge_voice=voice,
            narrator_pause_ms=narrator_pause_ms)
    else:
        raise CrawlError(f"未知的 TTS 引擎: {tts_engine}")


def _run_cosyvoice_subprocess(
    parsed_path: Path,
    audio_path: Path,
    model_dir: str,
    voice_map: str,
    cosy_python: str,
    narrator_voice: str = "zh-CN-YunjianNeural",
    edge_voice: str = "zh-CN-XiaoxiaoNeural",
    narrator_pause_ms: int = 250,
) -> None:
    """用 subprocess 调 cosy 环境的 Python 执行 CosyVoice 合成。"""
    cosy_exe = Path(cosy_python)
    if not cosy_exe.exists():
        raise CrawlError(
            f"未找到 CosyVoice 环境 Python: {cosy_exe}\n"
            f"请用 --cosy-python 指定路径，或运行: conda create -n cosy python=3.10"
        )

    script = Path(__file__).resolve().parent / "scripts" / "tts_cosyvoice.py"
    print(f"正在用 CosyVoice 合成语音...", file=sys.stderr)
    result = subprocess.run(
        [str(cosy_exe), str(script),
         "--input", str(parsed_path),
         "--output", str(audio_path),
         "--voice-map", voice_map,
         "--model-dir", model_dir,
         "--narrator-voice", narrator_voice,
         "--narrator-pause", str(narrator_pause_ms),
         "--edge-voice", edge_voice],
        capture_output=True, text=True,
    )
    # 打印进度日志
    if result.stderr:
        for line in result.stderr.strip().splitlines():
            print(f"  {line}", file=sys.stderr)
    if result.returncode != 0:
        # 展示完整错误信息
        detail = result.stderr + "\n" + result.stdout
        raise CrawlError(f"CosyVoice 合成失败:\n{detail}")


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
    tts_engine: str = "cosyvoice",
    cosyvoice_model_dir: str = "CosyVoice/pretrained_models/CosyVoice2-0.5B",
    cosyvoice_map: str = "voice_map.json",
    cosy_python: str = "D:/Anaconda/envs/cosy/python.exe",
    narrator_voice: str = "zh-CN-YunjianNeural",
    narrator_pause_ms: int = 250,
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
        tts_engine=tts_engine,
        cosyvoice_model_dir=cosyvoice_model_dir,
        cosyvoice_map=cosyvoice_map,
        cosy_python=cosy_python,
        narrator_voice=narrator_voice,
        narrator_pause_ms=narrator_pause_ms,
    )

    print(f"已保存源码：{txt_path}", file=sys.stderr)
    print(f"已保存结构化文档：{parsed_path}", file=sys.stderr)
    if tts_engine in ("edge", "cosyvoice"):
        print(f"已保存音频：{audio_path}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="从 PRTS wiki 选择剧情并导出源码、结构化文档和音频")
    parser.add_argument("source", nargs="?", help="已知剧情标题或剧情 URL；不提供则进入选择模式")
    parser.add_argument("--overview-title", default=DEFAULT_OVERVIEW_TITLE, help="剧情一览页面标题")
    parser.add_argument("--timeout", type=int, default=20, help="网络超时秒数")
    parser.add_argument("--list", action="store_true", help="仅列出可选剧情")
    parser.add_argument("--txt-dir", default=DEFAULT_TXT_DIR, help="源码输出目录")
    parser.add_argument("--parsed-dir", default=DEFAULT_PARSED_DIR, help="结构化文档输出目录")
    parser.add_argument("--audio-dir", default=DEFAULT_AUDIO_DIR, help="音频输出目录")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Edge TTS voice 名称")
    parser.add_argument("--rate", default="+0%", help="语速，例如 +0%%、-10%%、+15%%")
    parser.add_argument("--volume", default="+0%", help="音量，例如 +0%%")
    parser.add_argument("--text-field", default="text", help="JSONL 输入中用于合成的字段名")
    parser.add_argument("--tts", default="cosyvoice", choices=["cosyvoice", "edge", "skip"],
                        help="TTS 引擎：edge=Edge TTS, cosyvoice=CosyVoice, skip=只解析不合成")
    parser.add_argument("--cosyvoice-model-dir", default="CosyVoice/pretrained_models/CosyVoice2-0.5B",
                        help="CosyVoice 模型目录")
    parser.add_argument("--cosyvoice-map", default="voice_map.json",
                        help="CosyVoice voice_map.json 路径")
    parser.add_argument("--cosy-python", default="D:/Anaconda/envs/cosy/python.exe",
                        help="CosyVoice 环境的 Python 路径")
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
                tts_engine=args.tts,
                cosyvoice_model_dir=args.cosyvoice_model_dir,
                cosyvoice_map=args.cosyvoice_map,
                cosy_python=args.cosy_python,
            )
            return 0

        catalog = load_story_catalog(args.overview_title, timeout=args.timeout)
        if args.list:
            for index, entry in enumerate(catalog, start=1):
                print(format_entry(entry, index))
            return 0

        selected = choose_story_entry(catalog)
        print(f"已选择：{selected.title}", file=sys.stderr)
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
            tts_engine=args.tts,
            cosyvoice_model_dir=args.cosyvoice_model_dir,
            cosyvoice_map=args.cosyvoice_map,
            cosy_python=args.cosy_python,
        )
        return 0
    except CrawlError as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as error:
        print(f"错误: API 返回的不是有效 JSON: {error}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError) as error:
        print(f"错误: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
