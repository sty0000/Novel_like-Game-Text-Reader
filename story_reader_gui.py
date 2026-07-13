"""PRTS 剧情语音生成器 — GUI。

搜索、选择剧情，一键生成语音。支持 Edge TTS / CosyVoice 切换。
"""

from __future__ import annotations

import asyncio
import json
import subprocess
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
DEFAULT_COSY_PYTHON = "D:/Anaconda/envs/cosy/python.exe"
DEFAULT_COSY_MODEL = "CosyVoice/pretrained_models/CosyVoice2-0.5B"
DEFAULT_COSY_MAP = "voice_map.json"
DEFAULT_NARRATOR_VOICE = "zh-CN-YunjianNeural"
DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"


# ── 后台处理线程 ──────────────────────────────────────

class PipelineThread(threading.Thread):
    """在后台执行 fetch → parse → enrich → TTS 流水线。"""

    def __init__(
        self,
        entry: StoryEntry,
        tts_engine: str,
        edge_voice: str,
        edge_rate: str,
        edge_volume: str,
        cosy_python: str,
        cosy_model: str,
        cosy_map: str,
        narrator_voice: str,
        narrator_pause: int,
        callback_step: callable,
        callback_done: callable,
        callback_error: callable,
    ):
        super().__init__(daemon=True)
        self.entry = entry
        self.tts_engine = tts_engine
        self.edge_voice = edge_voice
        self.edge_rate = edge_rate
        self.edge_volume = edge_volume
        self.cosy_python = cosy_python
        self.cosy_model = cosy_model
        self.cosy_map = cosy_map
        self.narrator_voice = narrator_voice
        self.narrator_pause = narrator_pause
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

            audio_dir.mkdir(parents=True, exist_ok=True)
            audio_path = audio_dir / f"{base}.mp3"

            if self.tts_engine == "skip":
                self._done(audio_path, skipped=True)
                return

            if self.tts_engine == "edge":
                self._step("正在合成语音（Edge TTS）…")
                tts_text = load_input_text(parsed_path, "jsonl", "text")
                if not tts_text.strip():
                    raise CrawlError("解析后的文本为空，无法生成音频")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(
                        synthesize(tts_text, audio_path,
                                   self.edge_voice, self.edge_rate, self.edge_volume)
                    )
                finally:
                    loop.close()
                self._done(audio_path)
                return

            if self.tts_engine == "cosyvoice":
                self._step("正在合成语音（CosyVoice）…")
                cosy_exe = Path(self.cosy_python)
                if not cosy_exe.exists():
                    raise CrawlError(f"未找到 CosyVoice 环境: {cosy_exe}")

                script = Path(__file__).resolve().parent / "scripts" / "tts_cosyvoice.py"
                result = subprocess.run(
                    [str(cosy_exe), str(script),
                     "--input", str(parsed_path),
                     "--output", str(audio_path),
                     "--voice-map", self.cosy_map,
                     "--model-dir", self.cosy_model,
                     "--narrator-voice", self.narrator_voice,
                     "--narrator-pause", str(self.narrator_pause),
                     "--edge-voice", self.edge_voice,
                     "--edge-rate", self.edge_rate,
                     "--edge-volume", self.edge_volume],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    raise CrawlError(f"CosyVoice 合成失败:\n{result.stderr}")
                self._done(audio_path)
                return

            raise CrawlError(f"未知 TTS 引擎: {self.tts_engine}")

        except (CrawlError, OSError, json.JSONDecodeError) as exc:
            self._error(str(exc))
        except Exception as exc:
            self._error(f"未预期的错误: {exc}")


# ── 主界面 ────────────────────────────────────────────

class StoryReaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PRTS 剧情语音生成器")
        self.root.geometry("750x620")
        self.root.minsize(520, 440)

        self._entries: list[StoryEntry] = []
        self._filtered: list[StoryEntry] = []
        self._processing = False

        self._build_ui()
        self._load_catalog()

    # ── UI ──────────────────────────────────────────

    def _build_ui(self):
        # 顶部：搜索 + 刷新
        top_bar = ttk.Frame(self.root)
        top_bar.pack(fill=tk.X, padx=10, pady=(10, 0))

        ttk.Label(top_bar, text="🔍").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        ttk.Entry(top_bar, textvariable=self._search_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8))
        ttk.Button(top_bar, text="刷新列表", command=self._load_catalog).pack(side=tk.RIGHT)

        # 中部：剧情列表
        list_frame = ttk.Frame(self.root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        self._tree = ttk.Treeview(
            list_frame, columns=("#", "title", "section"),
            show="headings", selectmode="browse")
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
        self._tree.bind("<Double-1>", lambda _: self._start_pipeline())

        # 底部设置面板
        bottom = ttk.Frame(self.root)
        bottom.pack(fill=tk.X, padx=10, pady=(0, 10))

        # TTS 引擎 + 语音设置
        engine_row = ttk.Frame(bottom)
        engine_row.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(engine_row, text="TTS:").pack(side=tk.LEFT)
        self._tts_var = tk.StringVar(value="cosyvoice")
        ttk.Combobox(engine_row, textvariable=self._tts_var,
                     values=["cosyvoice", "edge", "skip"],
                     width=10, state="readonly").pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(engine_row, text="旁白:").pack(side=tk.LEFT)
        self._narrator_var = tk.StringVar(value=DEFAULT_NARRATOR_VOICE)
        ttk.Combobox(engine_row, textvariable=self._narrator_var,
                     values=["zh-CN-YunjianNeural", "zh-CN-YunxiNeural"],
                     width=20).pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(engine_row, text="角色回退:").pack(side=tk.LEFT)
        self._edge_var = tk.StringVar(value=DEFAULT_EDGE_VOICE)
        ttk.Combobox(engine_row, textvariable=self._edge_var,
                     values=["zh-CN-XiaoxiaoNeural", "zh-CN-YunyangNeural",
                             "zh-CN-YunjianNeural", "zh-CN-YunxiNeural"],
                     width=20).pack(side=tk.LEFT, padx=(2, 12))

        # 语速 + 音量 + 停顿
        param_row = ttk.Frame(bottom)
        param_row.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(param_row, text="语速:").pack(side=tk.LEFT)
        self._rate_var = tk.StringVar(value="+0%")
        ttk.Combobox(param_row, textvariable=self._rate_var,
                     values=["-20%", "-10%", "+0%", "+10%", "+20%"],
                     width=6).pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(param_row, text="音量:").pack(side=tk.LEFT)
        self._vol_var = tk.StringVar(value="+0%")
        ttk.Combobox(param_row, textvariable=self._vol_var,
                     values=["-20%", "-10%", "+0%", "+10%", "+20%"],
                     width=6).pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(param_row, text="旁白停顿(ms):").pack(side=tk.LEFT)
        self._pause_var = tk.StringVar(value="250")
        ttk.Spinbox(param_row, textvariable=self._pause_var,
                    from_=0, to=2000, increment=50,
                    width=5).pack(side=tk.LEFT, padx=(2, 12))

        # CosyVoice 设置（折叠）
        self._cosy_frame = ttk.LabelFrame(bottom, text="CosyVoice 设置", padding=4)
        self._cosy_frame.pack(fill=tk.X, pady=(0, 4))

        cosy_inner = ttk.Frame(self._cosy_frame)
        cosy_inner.pack(fill=tk.X)

        ttk.Label(cosy_inner, text="Python:").pack(side=tk.LEFT)
        self._cosy_python_var = tk.StringVar(value=DEFAULT_COSY_PYTHON)
        ttk.Entry(cosy_inner, textvariable=self._cosy_python_var,
                  width=35).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        cosy_inner2 = ttk.Frame(self._cosy_frame)
        cosy_inner2.pack(fill=tk.X, pady=(2, 0))

        ttk.Label(cosy_inner2, text="模型:").pack(side=tk.LEFT)
        self._cosy_model_var = tk.StringVar(value=DEFAULT_COSY_MODEL)
        ttk.Entry(cosy_inner2, textvariable=self._cosy_model_var,
                  width=30).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        ttk.Label(cosy_inner2, text="voice_map:").pack(side=tk.LEFT)
        self._cosy_map_var = tk.StringVar(value=DEFAULT_COSY_MAP)
        ttk.Entry(cosy_inner2, textvariable=self._cosy_map_var,
                  width=12).pack(side=tk.LEFT, padx=2)

        # 进度 + 按钮
        self._progress = ttk.Progressbar(bottom, mode="indeterminate")

        action_row = ttk.Frame(bottom)
        action_row.pack(fill=tk.X)

        self._status_label = ttk.Label(action_row, text="")
        self._status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._generate_btn = ttk.Button(
            action_row, text="▶ 生成语音", command=self._start_pipeline)
        self._generate_btn.pack(side=tk.RIGHT, padx=(8, 0))

        self._open_btn = ttk.Button(
            action_row, text="打开音频目录",
            command=lambda: Path(DEFAULT_AUDIO_DIR).mkdir(parents=True, exist_ok=True)
                or __import__("os").startfile(str(Path(DEFAULT_AUDIO_DIR).resolve())))
        self._open_btn.pack(side=tk.RIGHT)

    # ── 数据 ─────────────────────────────────────────

    def _load_catalog(self):
        self._set_status("正在从 PRTS wiki 加载剧情目录…")
        self._generate_btn.configure(state=tk.DISABLED)
        threading.Thread(target=self._do_load_catalog, daemon=True).start()

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

    def _on_load_success(self, entries):
        self._entries = entries
        self._filtered = entries
        self._refresh_list()
        self._generate_btn.configure(state=tk.NORMAL)
        self._set_status(f"已加载 {len(entries)} 条，双击或选中 → ▶ 生成语音")

    def _on_load_error(self, msg):
        self._generate_btn.configure(state=tk.NORMAL)
        self._set_status(f"加载失败: {msg}")
        messagebox.showerror("加载失败", f"无法加载剧情目录：\n{msg}")

    def _apply_filter(self):
        kw = self._search_var.get().strip()
        self._filtered = filter_entries(self._entries, kw) if kw else self._entries
        self._refresh_list()

    def _refresh_list(self):
        self._tree.delete(*self._tree.get_children())
        for i, entry in enumerate(self._filtered, start=1):
            self._tree.insert("", tk.END, iid=str(i),
                              values=(i, entry.title, entry.section or "—"))
        n = len(self._filtered)
        self._set_status(f"共 {n} 条匹配" if n else "无匹配，更换关键词")

    # ── 流水线 ───────────────────────────────────────

    def _start_pipeline(self):
        if self._processing:
            return
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("提示", "请先在列表中选择一条剧情")
            return
        idx = int(sel[0]) - 1
        if idx < 0 or idx >= len(self._filtered):
            return
        entry = self._filtered[idx]

        self._processing = True
        self._generate_btn.configure(state=tk.DISABLED, text="⏳ 处理中…")
        self._progress.pack(fill=tk.X, pady=(0, 4))
        self._progress.start()

        thread = PipelineThread(
            entry=entry,
            tts_engine=self._tts_var.get(),
            edge_voice=self._edge_var.get(),
            edge_rate=self._rate_var.get(),
            edge_volume=self._vol_var.get(),
            cosy_python=self._cosy_python_var.get(),
            cosy_model=self._cosy_model_var.get(),
            cosy_map=self._cosy_map_var.get(),
            narrator_voice=self._narrator_var.get(),
            narrator_pause=int(self._pause_var.get() or 250),
            callback_step=lambda msg: self.root.after(0, self._set_status, msg),
            callback_done=lambda path, skipped=False:
                self.root.after(0, self._on_done, path, skipped),
            callback_error=lambda msg: self.root.after(0, self._on_error, msg),
        )
        thread.start()

    def _on_done(self, audio_path, skipped=False):
        self._processing = False
        self._progress.stop()
        self._progress.pack_forget()
        self._generate_btn.configure(state=tk.NORMAL, text="▶ 生成语音")
        if skipped:
            self._set_status(f"✅ 已解析（跳过合成）: {audio_path}")
        else:
            self._set_status(f"✅ 已生成: {audio_path}")
            messagebox.showinfo("完成", f"语音已保存到:\n{audio_path}")

    def _on_error(self, msg):
        self._processing = False
        self._progress.stop()
        self._progress.pack_forget()
        self._generate_btn.configure(state=tk.NORMAL, text="▶ 生成语音")
        self._set_status(f"❌ 失败: {msg}")
        messagebox.showerror("生成失败", msg)

    def _set_status(self, text):
        self._status_label.configure(text=text)


def main():
    root = tk.Tk()
    StoryReaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
