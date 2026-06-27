"""PRTS 剧情语音生成器 — 简易 GUI。

搜索、选择剧情，一键生成语音。
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from get_text import CrawlError, fetch_story_text
from scripts.parse_story import extract_segments
from scripts.speech_modifier import enrich_segments, write_jsonl
from scripts.tts_edge import load_input_text, synthesize
from story_reader import (
    load_story_catalog,
    sanitize_filename,
    filter_entries,
    StoryEntry,
)

# ── 默认配置 ──────────────────────────────────────────

DEFAULT_TXT_DIR = "txt"
DEFAULT_PARSED_DIR = "parsed"
DEFAULT_AUDIO_DIR = "audio"
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


# ── 后台处理线程 ──────────────────────────────────────


class PipelineThread(threading.Thread):
    """在后台执行 fetch → parse → enrich → TTS 流水线。"""

    def __init__(
        self,
        entry: StoryEntry,
        voice: str,
        rate: str,
        volume: str,
        callback_step: callable,
        callback_done: callable,
        callback_error: callable,
    ):
        super().__init__(daemon=True)
        self.entry = entry
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self._step = callback_step
        self._done = callback_done
        self._error = callback_error

    def run(self):
        title = self.entry.title
        base = sanitize_filename(title)

        txt_dir = Path(DEFAULT_TXT_DIR)
        parsed_dir = Path(DEFAULT_PARSED_DIR)
        audio_dir = Path(DEFAULT_AUDIO_DIR)

        try:
            self._step("正在抓取剧情源码…")
            raw_text = fetch_story_text(title)

            txt_dir.mkdir(parents=True, exist_ok=True)
            txt_path = txt_dir / f"{base}.txt"
            txt_path.write_text(raw_text, encoding="utf-8")

            self._step("正在解析对白与场景…")
            raw_segments = extract_segments(raw_text, title, txt_path.name)
            if not raw_segments:
                raise CrawlError("未能从剧情源码中解析出有效片段")

            self._step("正在生成说书脚本…")
            segment_dicts = [asdict(seg) for seg in raw_segments]
            enriched = enrich_segments(segment_dicts)

            parsed_dir.mkdir(parents=True, exist_ok=True)
            parsed_path = parsed_dir / f"{base}.segments.jsonl"
            write_jsonl(enriched, parsed_path)

            self._step("正在合成语音（可能需要几十秒）…")
            tts_text = load_input_text(parsed_path, "jsonl", "text")
            if not tts_text.strip():
                raise CrawlError("解析后的文本为空，无法生成音频")

            audio_dir.mkdir(parents=True, exist_ok=True)
            audio_path = audio_dir / f"{base}.mp3"

            # 在新线程的独立事件循环中运行 asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    synthesize(tts_text, audio_path, self.voice, self.rate, self.volume)
                )
            finally:
                loop.close()

            self._done(audio_path)

        except (CrawlError, OSError, json.JSONDecodeError) as exc:
            self._error(str(exc))
        except Exception as exc:
            self._error(f"未预期的错误: {exc}")


# ── 主界面 ────────────────────────────────────────────


class StoryReaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PRTS 剧情语音生成器")
        self.root.geometry("720x560")
        self.root.minsize(500, 400)

        self._entries: list[StoryEntry] = []
        self._filtered: list[StoryEntry] = []
        self._processing = False

        self._build_ui()
        self._load_catalog()

    # ── UI 构建 ─────────────────────────────────────

    def _build_ui(self):
        # 顶部：搜索 + 刷新
        top_bar = ttk.Frame(self.root)
        top_bar.pack(fill=tk.X, padx=10, pady=(10, 0))

        ttk.Label(top_bar, text="🔍").pack(side=tk.LEFT)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        search_entry = ttk.Entry(top_bar, textvariable=self._search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))

        refresh_btn = ttk.Button(top_bar, text="刷新列表", command=self._load_catalog)
        refresh_btn.pack(side=tk.RIGHT)

        # 中部：剧情列表
        list_frame = ttk.Frame(self.root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        columns = ("#", "title", "section")
        self._tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self._tree.heading("#", text="#")
        self._tree.heading("title", text="剧情标题")
        self._tree.heading("section", text="所属章节")

        self._tree.column("#", width=40, minwidth=30, anchor=tk.CENTER)
        self._tree.column("title", width=400, minwidth=150)
        self._tree.column("section", width=180, minwidth=80)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 双击触发生成
        self._tree.bind("<Double-1>", lambda _: self._start_pipeline())

        # 底部：设置 + 状态 + 按钮
        bottom = ttk.Frame(self.root)
        bottom.pack(fill=tk.X, padx=10, pady=(0, 10))

        # 设置行
        settings = ttk.Frame(bottom)
        settings.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(settings, text="语音:").pack(side=tk.LEFT)
        self._voice_var = tk.StringVar(value=DEFAULT_VOICE)
        voice_combo = ttk.Combobox(
            settings,
            textvariable=self._voice_var,
            values=["zh-CN-XiaoxiaoNeural", "zh-CN-YunjianNeural",
                    "zh-CN-YunxiNeural", "zh-CN-YunyangNeural"],
            width=22,
        )
        voice_combo.pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(settings, text="语速:").pack(side=tk.LEFT)
        self._rate_var = tk.StringVar(value="+0%")
        rate_combo = ttk.Combobox(
            settings,
            textvariable=self._rate_var,
            values=["-20%", "-10%", "+0%", "+10%", "+20%"],
            width=6,
        )
        rate_combo.pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(settings, text="音量:").pack(side=tk.LEFT)
        self._volume_var = tk.StringVar(value="+0%")
        vol_combo = ttk.Combobox(
            settings,
            textvariable=self._volume_var,
            values=["-20%", "-10%", "+0%", "+10%", "+20%"],
            width=6,
        )
        vol_combo.pack(side=tk.LEFT, padx=(2, 12))

        # 进度条
        self._progress = ttk.Progressbar(bottom, mode="indeterminate")

        # 状态 + 按钮行
        action_row = ttk.Frame(bottom)
        action_row.pack(fill=tk.X)

        self._status_label = ttk.Label(action_row, text="")
        self._status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._generate_btn = ttk.Button(
            action_row,
            text="▶ 生成语音",
            command=self._start_pipeline,
        )
        self._generate_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self._open_btn = ttk.Button(
            action_row,
            text="打开音频目录",
            command=lambda: Path(DEFAULT_AUDIO_DIR).mkdir(parents=True, exist_ok=True)
                or __import__("os").startfile(str(Path(DEFAULT_AUDIO_DIR).resolve())),
        )
        self._open_btn.pack(side=tk.RIGHT)

    # ── 数据加载 ─────────────────────────────────────

    def _load_catalog(self):
        """后台加载剧情目录。"""
        self._set_status("正在从 PRTS wiki 加载剧情目录…")
        self._generate_btn.configure(state=tk.DISABLED)
        thread = threading.Thread(target=self._do_load_catalog, daemon=True)
        thread.start()

    def _do_load_catalog(self):
        try:
            entries = load_story_catalog()
        except (CrawlError, json.JSONDecodeError) as exc:
            self.root.after(0, lambda: self._on_load_error(str(exc)))
            return
        except Exception as exc:
            self.root.after(0, lambda: self._on_load_error(f"网络错误: {exc}"))
            return

        self.root.after(0, lambda: self._on_load_success(entries))

    def _on_load_success(self, entries: list[StoryEntry]):
        self._entries = entries
        self._filtered = entries
        self._refresh_list()
        self._generate_btn.configure(state=tk.NORMAL)
        self._set_status(f"已加载 {len(entries)} 条剧情，双击或选中后点击按钮生成语音")

    def _on_load_error(self, msg: str):
        self._generate_btn.configure(state=tk.NORMAL)
        self._set_status(f"加载失败: {msg}")
        messagebox.showerror("加载失败", f"无法加载剧情目录：\n{msg}")

    # ── 搜索过滤 ─────────────────────────────────────

    def _apply_filter(self):
        keyword = self._search_var.get().strip()
        if keyword:
            self._filtered = filter_entries(self._entries, keyword)
        else:
            self._filtered = self._entries
        self._refresh_list()

    def _refresh_list(self):
        self._tree.delete(*self._tree.get_children())
        for i, entry in enumerate(self._filtered, start=1):
            self._tree.insert(
                "",
                tk.END,
                iid=str(i),
                values=(i, entry.title, entry.section or "—"),
            )
        n = len(self._filtered)
        self._set_status(f"共 {n} 条匹配" if n else "无匹配结果，尝试更换关键词")

    # ── 流水线 ───────────────────────────────────────

    def _start_pipeline(self):
        if self._processing:
            return

        selection = self._tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先在列表中选择一条剧情")
            return

        idx = int(selection[0]) - 1
        if idx < 0 or idx >= len(self._filtered):
            return
        entry = self._filtered[idx]

        self._processing = True
        self._generate_btn.configure(state=tk.DISABLED, text="⏳ 处理中…")
        self._progress.pack(fill=tk.X, pady=(0, 4))
        self._progress.start()

        thread = PipelineThread(
            entry=entry,
            voice=self._voice_var.get(),
            rate=self._rate_var.get(),
            volume=self._volume_var.get(),
            callback_step=lambda msg: self.root.after(0, self._set_status, msg),
            callback_done=lambda path: self.root.after(0, self._on_done, path),
            callback_error=lambda msg: self.root.after(0, self._on_error, msg),
        )
        thread.start()

    def _on_done(self, audio_path: Path):
        self._processing = False
        self._progress.stop()
        self._progress.pack_forget()
        self._generate_btn.configure(state=tk.NORMAL, text="▶ 生成语音")
        self._set_status(f"✅ 已生成: {audio_path}")
        messagebox.showinfo("完成", f"语音已保存到:\n{audio_path}")

    def _on_error(self, msg: str):
        self._processing = False
        self._progress.stop()
        self._progress.pack_forget()
        self._generate_btn.configure(state=tk.NORMAL, text="▶ 生成语音")
        self._set_status(f"❌ 失败: {msg}")
        messagebox.showerror("生成失败", msg)

    def _set_status(self, text: str):
        self._status_label.configure(text=text)


# ── 入口 ──────────────────────────────────────────────


def main():
    root = tk.Tk()
    app = StoryReaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
