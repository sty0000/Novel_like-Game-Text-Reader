"""基于规则的语气检测，作为 ML 模型训练前的 fallback。

支持 18 种情感标签。
"""

from __future__ import annotations

import re

# ── 所有可能的语气标签 ─────────────────────────────────

EMOTION_LABELS = [
    "neutral",         # 平静 / 中性
    "question",        # 疑问（？）
    "shock_question",  # 震惊质问（？！）
    "shocked",         # 震惊 / 惊讶（！+ 震惊词）
    "angry",           # 愤怒 / 生气
    "happy",           # 开心 / 喜悦
    "sad",             # 悲伤 / 难过
    "fearful",         # 恐惧 / 害怕
    "ponder",          # 思索 / 沉吟
    "hesitate",        # 犹豫 / 迟疑
    "sigh",            # 叹息 / 感叹
    "laugh",           # 笑
    "determined",      # 坚定 / 决心
    "arrogant",        # 傲慢 / 自负
    "gentle",          # 温柔 / 安慰
    "urgent",          # 急切 / 紧迫
    "desperate",       # 绝望
    "serious",         # 严肃 / 庄重
]

# ── 情感关键词集合 ────────────────────────────────────

_ANGRY_KW = (
    "混账", "混蛋", "该死", "可恶", "岂有此理",
    "闭嘴", "放肆", "别以为", "你敢", "住口",
    "找死", "王八蛋", "滚开", "滚", "少废话",
    "胡说", "荒谬", "荒唐", "不知好歹", "狂妄",
    "放肆", "无礼", "不客气", "别怪", "不识好歹",
    "任你", "给你脸", "欠揍", "宰了你", "饶不了你",
)

_SHOCKED_KW = (
    "什么", "怎么", "竟然", "居然", "难道",
    "不可能", "怎么会", "天啊", "天哪", "难以置信",
    "不可思议", "怎会", "这是", "真的假的",
)

_HAPPY_KW = (
    "太好了", "真棒", "好极了", "太好了", "高兴",
    "开心", "太棒了", "真好", "好样的", "漂亮",
    "厉害", "了不起", "恭喜", "庆祝", "欢呼",
    "真不错", "不错嘛", "有意思", "有趣",
)

_FEARFUL_KW = (
    "不要", "别过来", "救命", "快跑", "快走",
    "不好", "糟了", "完了", "糟糕",
    "可怕", "恐怖", "危险", "小心",
    "别杀我", "饶命", "放过我", "别伤害",
    "怎么办", "这下惨了",
)

_SAD_KW = (
    "对不起", "遗憾", "可惜", "再也", "永别",
    "离别", "难过", "伤心", "痛苦", "悲伤",
    "哭泣", "眼泪", "泪", "不舍", "失去",
    "回不来", "来不及", "晚了", "无法挽回",
    "终究", "徒劳", "惋惜", "抱歉", "怪我",
)

_PONDER_KW = (
    "嗯", "也许", "或许", "大概", "可能吧",
    "让我想想", "等等", "姑且", "难不成",
    "难道说", "莫非", "按说", "按理说",
    "琢磨", "思考", "考虑", "思量",
    "想来", "看来", "这么说", "也就是说",
)

# 新增 ──────────────────────────────────────────────

_DETERMINED_KW = (
    "我一定会", "我一定能", "我绝不会", "我决不",
    "交给我", "相信我", "说到做到",
    "誓", "必", "必定", "决不", "绝不",
    "不管怎样", "无论如何", "豁出去了",
)

_ARROGANT_KW = (
    "就凭你", "就凭你们", "不过如此", "也配",
    "不自量力", "区区", "算什么东西",
    "你算老几", "轮不到你", "你也敢",
    "本", "老子", "大爷我",
)

_GENTLE_KW = (
    "没事的", "有我在", "别怕",
    "乖", "好孩子", "乖乖",
    "你已经做得很好了", "不用勉强",
    "慢慢来", "不要紧的", "没关系",
    "好好休息", "辛苦了",
)

_URGENT_KW = (
    "快走", "快跑", "快撤", "快",
    "来不及", "来不及了", "赶紧", "立刻",
    "马上", "赶快", "迅速",
    "时间不多了", "刻不容缓", "再不走",
    "别磨蹭", "别犹豫了",
)

_DESPERATE_KW = (
    "一切都完了", "没办法了", "没救了",
    "我做不到", "做不到了", "注定",
    "认命吧", "放弃吧", "到此为止了",
    "无力回天", "任人宰割", "走投无路",
    "天要亡我", "谁也救不了",
)

_RELIEVED_KW = (
    "幸好", "还好", "好在", "幸亏",
    "终于", "可算", "总算是",
    "松了一口气", "如释重负", "放心了",
    "虚惊一场", "只是虚惊",
    "没问题了", "没事就好",
)

_SERIOUS_KW = (
    "我以", "起誓", "发誓", "郑重",
    "庄严", "宣誓", "宣誓",
    "以此", "在此宣告", "宣告",
    "认真", "严肃",
)

_DISGUSTED_KW = (
    "恶心", "真恶心", "好恶心",
    "脏", "脏死了", "恶臭", "臭死了",
    "别碰我", "离我远点", "滚开",
    "令人作呕", "反胃",
    "龌龊", "污秽",
)


# ── 检测函数 ──────────────────────────────────────────


def detect_emotion(text: str) -> str:
    """从对白文本中检测情感语气。

    Returns one of the 18 labels in :data:`EMOTION_LABELS`.
    """
    trimmed = text.strip()
    if not trimmed:
        return "neutral"

    has_exclaim = bool(re.search(r"[！!]", trimmed))
    has_question = bool(re.search(r"[？?]", trimmed))

    # 1) 震惊质问：？！同时出现
    if has_exclaim and has_question:
        return "shock_question"

    # 2) 疑问句
    if has_question:
        if _contains_any(trimmed, _SAD_KW):
            return "sad"
        if _contains_any(trimmed, _FEARFUL_KW):
            return "fearful"
        if _contains_any(trimmed, _DESPERATE_KW):
            return "desperate"
        if _contains_any(trimmed, _PONDER_KW):
            return "ponder"
        return "question"

    # 3) 感叹句：根据关键词细分
    if has_exclaim:
        if _contains_any(trimmed, _ANGRY_KW):
            return "angry"
        if _contains_any(trimmed, _DETERMINED_KW):
            return "determined"
        if _contains_any(trimmed, _URGENT_KW):
            return "urgent"
        if _contains_any(trimmed, _DESPERATE_KW):
            return "desperate"
        if _contains_any(trimmed, _SHOCKED_KW):
            return "shocked"
        if _contains_any(trimmed, _FEARFUL_KW):
            return "fearful"
        if _contains_any(trimmed, _HAPPY_KW):
            return "happy"
        if _contains_any(trimmed, _RELIEVED_KW):
            return "happy"
        if _contains_any(trimmed, _DISGUSTED_KW):
            return "angry"
        if _contains_any(trimmed, _SAD_KW):
            return "sad"
        # 默认感叹 → 愤怒（最常见的感叹情绪）
        return "angry"

    # 4) 无标点，检查句首和关键词特征
    if trimmed.startswith("......") or trimmed.startswith("……"):
        return "hesitate"

    if trimmed.startswith("唉") or trimmed.startswith("咳"):
        return "sigh"

    if "哈" in trimmed[:6] or trimmed.startswith("呵呵"):
        return "laugh"

    if trimmed.startswith("呃"):
        return "hesitate"

    if trimmed.startswith("哼"):
        return "arrogant"

    if trimmed.startswith("乖") or trimmed.startswith("好孩子"):
        return "gentle"

    # 5) 无标点但含情感关键词
    if _contains_any(trimmed, _DESPERATE_KW):
        return "desperate"
    if _contains_any(trimmed, _SAD_KW):
        return "sad"
    if _contains_any(trimmed, _FEARFUL_KW):
        return "fearful"
    if _contains_any(trimmed, _URGENT_KW):
        return "urgent"
    if _contains_any(trimmed, _DISGUSTED_KW):
        return "angry"
    if _contains_any(trimmed, _ANGRY_KW):
        return "angry"
    if _contains_any(trimmed, _DETERMINED_KW):
        return "determined"
    if _contains_any(trimmed, _ARROGANT_KW):
        return "arrogant"
    if _contains_any(trimmed, _HAPPY_KW):
        return "happy"
    if _contains_any(trimmed, _RELIEVED_KW):
        return "happy"
    if _contains_any(trimmed, _SHOCKED_KW):
        return "shocked"
    if _contains_any(trimmed, _GENTLE_KW):
        return "gentle"
    if _contains_any(trimmed, _SERIOUS_KW):
        return "serious"
    if _contains_any(trimmed, _PONDER_KW):
        return "ponder"

    return "neutral"


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    """检查文本是否包含任一关键词。"""
    for kw in keywords:
        if kw in text:
            return True
    return False
