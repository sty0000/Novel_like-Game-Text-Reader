"""从 PRTS wiki 获取角色差分映射表。

从 Widget:Data_Char 提取所有 char_XXX 代码及其对应的图片 URL。
输出 CSV，方便后续做差分→情绪标注。
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from get_text import fetch_text

DATA_CHAR_URL = "https://prts.wiki/index.php?title=Widget:Data_Char&action=raw"

# 匹配格式: char_148_nearl_1-4$1,https://media.prts.wiki/.../xxx.png
# 或旧格式: char_148_nearl_1,https://...
CHAR_LINE_RE = re.compile(
    r"^(char_\d+_\w+(?:-\d+(?:\$\d+)?)?)\s*,\s*(https://[^\s]+)",
    re.MULTILINE,
)


def main() -> int:
    print("正在从 PRTS wiki 获取 Data_Char ...", file=sys.stderr)
    try:
        text = fetch_text(DATA_CHAR_URL)
    except Exception as e:
        print(f"获取失败: {e}", file=sys.stderr)
        return 1

    mappings: list[tuple[str, str]] = []
    for match in CHAR_LINE_RE.finditer(text):
        code = match.group(1)
        url = match.group(2)
        mappings.append((code, url))

    if not mappings:
        # 尝试更宽松的匹配
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("{{") or line.startswith("|"):
                continue
            if "char_" in line and "http" in line:
                parts = line.split(",", 1)
                if len(parts) == 2:
                    mappings.append((parts[0].strip(), parts[1].strip()))

    print(f"找到 {len(mappings)} 条映射", file=sys.stderr)

    # 分析差分编号分布
    variations: dict[str, set[str]] = {}
    for code, _ in mappings:
        # 提取基础角色名和差分号
        # 格式: char_148_nearl_1-4$1 或 char_148_nearl_1
        match = re.match(r"(char_\d+_\w+_\d+)(?:-(\d+))?", code)
        if match:
            base = match.group(1)
            var = match.group(2) or "base"
            variations.setdefault(base, set()).add(var)

    print("\n各角色差分数量:")
    for base, varset in sorted(variations.items(), key=lambda x: -len(x[1])):
        if len(varset) >= 2:
            print(f"  {base}: {sorted(varset, key=lambda x: int(x) if x != 'base' else 0)}")

    # 保存
    out = Path("char_expression_map.csv")
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["code", "url"])
        writer.writerows(mappings)
    print(f"\n已保存 {len(mappings)} 条 → {out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())