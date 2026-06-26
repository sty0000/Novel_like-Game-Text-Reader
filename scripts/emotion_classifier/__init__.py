"""本地机器学习模块，用于识别对白的情感语气。

用法::

    from scripts.emotion_classifier import EmotionClassifier

    # 自动加载已训练的模型，没有模型时回退到规则
    clf = EmotionClassifier()
    emotion = clf.predict("你这说的是什么话？！")
    # -> "shock_question"

    # 强制只使用规则（不加载模型）
    clf = EmotionClassifier(model_dir=None)
"""

from __future__ import annotations

from scripts.emotion_classifier.classifier import EmotionClassifier
from scripts.emotion_classifier.rules import detect_emotion

__all__ = ["EmotionClassifier", "detect_emotion"]
