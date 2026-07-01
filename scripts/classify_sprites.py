"""角色差分图情绪分类器（纯图片 → 情绪，带缓存）。

输出 sprite_emotions.csv 作为映射表。重复图片直接读缓存，不重复推理。

用法::

    # 一次性分类全部图片（推荐先跑这个）
    python scripts/classify_sprites.py --all

    # 从单个剧情源码提取差分码
    python scripts/classify_sprites.py txt/0-10_困境_BEG.txt

    # 对已下载图片分类
    python scripts/classify_sprites.py --classify-only
"""

from __future__ import annotations

import csv
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from get_text import fetch_text

# ── 路径 ─────────────────────────────────────────────

DATA_CHAR_URL = "https://prts.wiki/index.php?title=Widget:Data_Char&action=raw"
SPRITE_DIR = Path("sprites")
CHAR_MAP_FILE = Path("char_expression_map.csv")
CACHE_FILE = Path("sprite_emotions.csv")

EMOTIONS = [
    "neutral", "angry", "happy", "sad", "fearful", "shocked",
    "serious", "gentle", "arrogant", "determined", "ponder",
    "hesitate", "laugh", "sigh", "urgent", "desperate",
    "shock_question",
]

# ── 缓存读写 ─────────────────────────────────────────


def load_cache() -> dict[str, tuple[str, float]]:
    """加载 sprite_emotions.csv → {sprite_code: (emotion, confidence)}。"""
    if not CACHE_FILE.exists():
        return {}
    cache: dict[str, tuple[str, float]] = {}
    with CACHE_FILE.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = row.get("code", "").strip()
            emo = row.get("emotion", "").strip()
            conf = float(row.get("confidence", 0))
            if code and (emo in _FER_LABELS or emo in EMOTIONS):
                cache[code] = (emo, conf)
    return cache


def save_cache(cache: dict[str, tuple[str, float]]) -> None:
    """保存映射表（含置信度）。"""
    with CACHE_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "emotion", "confidence"])
        w.writeheader()
        for code, (emo, conf) in sorted(cache.items()):
            w.writerow({"code": code, "emotion": emo, "confidence": f"{conf:.4f}"})


# ── URL 映射 ─────────────────────────────────────────


def build_url_map() -> dict[str, str]:
    """从 Data_Char 构建 sprite_code → image_url 映射。"""
    if CHAR_MAP_FILE.exists():
        url_map: dict[str, str] = {}
        with CHAR_MAP_FILE.open(encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) == 2:
                    url_map[row[0]] = row[1]
        if url_map:
            return url_map

    print("从 PRTS wiki 获取 Data_Char ...", file=sys.stderr)
    text = fetch_text(DATA_CHAR_URL)
    url_map = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("char_"):
            continue
        parts = line.split(",", 1)
        if len(parts) == 2 and parts[1].startswith("http"):
            url_map[parts[0].strip()] = parts[1].strip()

    with CHAR_MAP_FILE.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(url_map.items())
    print(f"  缓存 {len(url_map)} 条 URL 映射", file=sys.stderr)
    return url_map


def resolve_url(code: str, url_map: dict[str, str]) -> str | None:
    """char_148_nearl_1#4 → image URL。"""
    search = code.replace("#", "-")
    for candidate in (search, search + "$1",
                       search.rsplit("-", 1)[0],
                       search.rsplit("-", 1)[0] + "$1"):
        if candidate in url_map:
            return url_map[candidate]
    return None


# ── 下载 ─────────────────────────────────────────────


def download_image(code: str, url: str) -> Path | None:
    """下载并返回本地路径。"""
    SPRITE_DIR.mkdir(exist_ok=True)
    safe = code.replace("#", "_").replace("$", "_").replace("/", "_")
    path = SPRITE_DIR / f"{safe}.png"
    if path.exists():
        return path
    try:
        urllib.request.urlretrieve(url, str(path))
        return path
    except Exception as e:
        print(f"  下载失败 {code}: {e}", file=sys.stderr)
        return None


# ── 表情识别分类 ──────────────────────────────────────

# FER 模型支持的 7 类基础表情（直接存入缓存）
_FER_LABELS = {"angry", "disgust", "fear", "happy", "neutral", "sad", "surprise"}


def classify_images(
    items: list[tuple[str, Path]],
    cache: dict[str, tuple[str, float]],
    model_name: str = "dima806/facial_emotions_image_detection",
) -> dict[str, tuple[str, float]]:
    """用人脸表情识别模型分类，更新 cache。

    输出的是 7 类 FER 标签（angry/disgust/fear/happy/neutral/sad/surprise），
    不加映射。speech_modifier 会根据相容度表做加权融合。

    Args:
        model_name: HuggingFace 模型名。
           - ``"dima806/facial_emotions_image_detection"`` (默认, ~100MB)
    """
    try:
        import torch
        from PIL import Image
        from transformers import pipeline
    except ImportError:
        raise ImportError("pip install transformers torch pillow")

    new_items = [(c, p) for c, p in items if c not in cache]
    if not new_items:
        print("所有图片已缓存", file=sys.stderr)
        return cache

    print(f"加载表情识别模型 {model_name} ({len(new_items)} 张新图)...", file=sys.stderr)
    device = 0 if torch.cuda.is_available() else -1
    pipe = pipeline("image-classification", model=model_name, device=device)

    for code, path in new_items:
        try:
            image = Image.open(path).convert("RGB")
        except Exception:
            print(f"  无法读取 {code}", file=sys.stderr)
            continue

        results = pipe(image)
        best_label = results[0]["label"].lower()
        confidence = results[0]["score"]

        # 只接受已知的 7 类标签
        if best_label not in _FER_LABELS:
            best_label = "neutral"

        cache[code] = (best_label, confidence)
        print(f"  {code}: {best_label} ({confidence:.2f})", file=sys.stderr)

    return cache


# ── 主入口 ───────────────────────────────────────────


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="角色差分图 → 情绪分类（带缓存）")
    p.add_argument("source", nargs="?", help="剧情 .txt 源码")
    p.add_argument("--all", action="store_true",
                   help="下载并分类 char_expression_map.csv 中全部图片")
    p.add_argument("--classify-only", action="store_true",
                   help="只对已下载的 sprites/ 目录图片分类")
    args = p.parse_args()

    cache = load_cache()
    url_map = build_url_map()

    # ── --classify-only: 分类已下载图片 ──
    if args.classify_only:
        items = []
        for f in sorted(SPRITE_DIR.glob("*.png")):
            code = f.stem.replace("_", "#", 1).replace("_", "$", 1)
            items.append((code, f))
        cache = classify_images(items, cache)
        save_cache(cache)
        print(f"完成，共 {len(cache)} 条映射", file=sys.stderr)
        return 0

    # ── --all: 处理 char_expression_map 中全部图片 ──
    if args.all:
        if not CHAR_MAP_FILE.exists():
            print("char_expression_map.csv 不存在，先运行 fetch_char_data.py",
                  file=sys.stderr)
            return 1
        codes: list[str] = []
        with CHAR_MAP_FILE.open(encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if len(row) >= 1:
                    codes.append(row[0].strip())
        print(f"从映射表加载 {len(codes)} 个差分码", file=sys.stderr)

        to_classify: list[tuple[str, Path]] = []
        skipped, not_found = 0, 0
        for code in codes:
            if code in cache:
                skipped += 1
                continue
            url = resolve_url(code, url_map)
            if not url:
                not_found += 1
                continue
            path = download_image(code, url)
            if path:
                to_classify.append((code, path))

        print(f"下载: {len(to_classify)} 新图, 跳过(已缓存): {skipped}, 未找到: {not_found}",
              file=sys.stderr)

        if to_classify:
            cache = classify_images(to_classify, cache)
            save_cache(cache)
        else:
            print("没有新图片需要分类", file=sys.stderr)
        return 0

    # ── 从单个剧情源码提取 ──
    if not args.source:
        p.print_help()
        return 1

    import re
    text = Path(args.source).read_text(encoding="utf-8")
    codes_set: set[str] = set()
    for m in re.finditer(r'\[Character\(name="([^"]+)"\)', text):
        codes_set.add(m.group(1))
    source_codes = sorted(codes_set)
    print(f"提取 {len(source_codes)} 个差分码", file=sys.stderr)

    to_classify: list[tuple[str, Path]] = []
    not_found = 0
    for code in source_codes:
        if code in cache:
            continue
        url = resolve_url(code, url_map)
        if not url:
            not_found += 1
            continue
        path = download_image(code, url)
        if path:
            to_classify.append((code, path))

    print(f"下载: {len(to_classify)} 新图, 已缓存: {len(cache)}, 未找到: {not_found}",
          file=sys.stderr)

    if to_classify:
        cache = classify_images(to_classify, cache)
        save_cache(cache)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
