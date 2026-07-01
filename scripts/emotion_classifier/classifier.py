"""情感分类推理模块。

用已训练的本地 NLP 模型对对话文本进行情感分类；
没有模型时自动回退到 :mod:`~scripts.emotion_classifier.rules` 规则。

模型文件约定
------------
模型目录下需要两个文件::

    model/
    ├── model.safetensors   (或 pytorch_model.bin)
    ├── config.json
    └── tokenizer.json      (或 tokenizer_config.json + vocab.txt 等)

可以使用 :func:`load` 加载，或直接创建 :class:`EmotionClassifier` 实例。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Sequence

from scripts.emotion_classifier.rules import EMOTION_LABELS, detect_emotion

# 推理中会用到的全局变量
_MODEL = None
_TOKENIZER = None
_MODEL_DIR: Optional[Path] = None
_BACKEND: Optional[str] = None


def _find_model_dir() -> Optional[Path]:
    """自动查找模型目录。"""
    candidate = Path(__file__).resolve().parent / "model"
    if candidate.is_dir() and any(candidate.iterdir()):
        return candidate
    return None


def _load_transformers(model_dir: Path):
    """尝试加载 transformers 模型和分词器。"""
    global _MODEL, _TOKENIZER, _MODEL_DIR, _BACKEND

    try:
        from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer
    except ImportError:
        raise ImportError(
            "需要安装 transformers 库。运行：pip install transformers torch"
        )

    config = AutoConfig.from_pretrained(
        str(model_dir),
        num_labels=len(EMOTION_LABELS),
        id2label={i: label for i, label in enumerate(EMOTION_LABELS)},
        label2id={label: i for i, label in enumerate(EMOTION_LABELS)},
    )
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(
        str(model_dir), config=config
    )

    _MODEL = model
    _TOKENIZER = tokenizer
    _MODEL_DIR = model_dir
    _BACKEND = "transformers"


def _load_onnx(model_dir: Path):
    """尝试加载 ONNX 模型（轻量推理，不需要 PyTorch）。"""
    global _MODEL, _TOKENIZER, _MODEL_DIR, _BACKEND

    try:
        import onnxruntime as ort
        from transformers import AutoTokenizer
    except ImportError:
        raise ImportError(
            "需要安装 onnxruntime 和 transformers。运行：pip install onnxruntime transformers"
        )

    onnx_path = model_dir / "model.onnx"
    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX 模型文件不存在: {onnx_path}")

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    session = ort.InferenceSession(
        str(onnx_path),
        providers=["CPUExecutionProvider"],
    )

    _MODEL = session
    _TOKENIZER = tokenizer
    _MODEL_DIR = model_dir
    _BACKEND = "onnx"


def load(model_dir: Optional[str] = None, prefer_onnx: bool = True) -> bool:
    """加载模型并置为全局推理实例。

    Args:
        model_dir: 模型目录路径，为 None 时自动查找。
        prefer_onnx: 优先使用 ONNX 格式（更快、依赖更少）。

    Returns:
        是否成功加载了 ML 模型。返回 ``False`` 表示将使用规则 fallback。

    Raises:
        ImportError: 缺少必要的依赖库。
        FileNotFoundError: 指定目录不存在或缺少模型文件。
    """
    global _MODEL, _TOKENIZER, _MODEL_DIR, _BACKEND

    if model_dir is None:
        found = _find_model_dir()
        if found is None:
            _MODEL = None
            _TOKENIZER = None
            _MODEL_DIR = None
            _BACKEND = None
            return False
        model_dir = str(found)

    path = Path(model_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"模型目录不存在: {model_dir}")

    # 优先尝试 ONNX
    if prefer_onnx and (path / "model.onnx").exists():
        _load_onnx(path)
    else:
        _load_transformers(path)

    return True


def _predict_transformers(texts: list[str]) -> list[str]:
    """用 PyTorch transformers 模型推理。"""
    import torch

    global _MODEL, _TOKENIZER

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    _MODEL.to(device)
    _MODEL.eval()

    inputs = _TOKENIZER(
        texts,
        padding=True,
        truncation=True,
        max_length=128,
        return_tensors="pt",
    ).to(device)

    with torch.no_grad():
        outputs = _MODEL(**inputs)
        predictions = torch.argmax(outputs.logits, dim=-1)

    return [EMOTION_LABELS[p.item()] for p in predictions]


def _predict_onnx(texts: list[str]) -> list[str]:
    """用 ONNX Runtime 推理。"""
    import numpy as np

    global _MODEL, _TOKENIZER

    encoded = _TOKENIZER(
        texts,
        padding=True,
        truncation=True,
        max_length=128,
        return_tensors="np",
    )

    inputs = {
        "input_ids": encoded["input_ids"].astype(np.int64),
        "attention_mask": encoded["attention_mask"].astype(np.int64),
    }
    # token_type_ids 在某些模型中可选
    if "token_type_ids" in encoded:
        inputs["token_type_ids"] = encoded["token_type_ids"].astype(np.int64)

    logits = _MODEL.run(None, inputs)[0]
    predictions = np.argmax(logits, axis=-1)

    return [EMOTION_LABELS[p] for p in predictions]


def predict(texts: str | Sequence[str]) -> str | list[str]:
    """对一条或多条文本进行情感分类。

    Args:
        texts: 单条文本或文本列表。

    Returns:
        单个标签（输入为字符串时）或标签列表（输入为列表时）。
        标签值见 :data:`~scripts.emotion_classifier.rules.EMOTION_LABELS`。
    """
    single_input = isinstance(texts, str)
    batch = [texts] if single_input else list(texts)

    global _MODEL, _TOKENIZER, _BACKEND

    if _MODEL is not None and _TOKENIZER is not None:
        if _BACKEND == "onnx":
            results = _predict_onnx(batch)
        elif _BACKEND == "transformers":
            results = _predict_transformers(batch)
        else:
            results = [detect_emotion(t) for t in batch]
    else:
        # 回退到规则
        results = [detect_emotion(t) for t in batch]

    return results[0] if single_input else results


# ── 便捷类 ─────────────────────────────────────────────


class EmotionClassifier:
    """情感分类器，自动加载模型或回退到规则。

    Usage::

        # 自动模式：有模型用模型，没有用规则
        clf = EmotionClassifier()

        # 强制指定模型
        clf = EmotionClassifier(model_dir="scripts/emotion_classifier/model")

        # 强制只用规则
        clf = EmotionClassifier(model_dir=None)

        emotion = clf.predict("你这说的是什么话？！")
    """

    def __init__(self, model_dir: Optional[str] = None):
        """
        Args:
            model_dir: 模型目录路径。
                - ``None``（默认）：自动查找 ``model/`` 子目录，
                  找不到则回退规则。
                - 路径字符串：加载指定目录下的模型。
                - 空字符串 ``""``：强制使用规则。
        """
        self._use_ml = False
        if model_dir is None:
            found = _find_model_dir()
            if found is not None:
                model_dir = str(found)

        if model_dir:
            try:
                self._use_ml = load(model_dir)
            except (ImportError, FileNotFoundError, OSError):
                self._use_ml = False

    def predict(self, text: str) -> str:
        """对单条文本进行情感分类。"""
        if self._use_ml:
            return predict(text)  # type: ignore[return-value]
        return detect_emotion(text)

    def predict_batch(self, texts: Sequence[str]) -> list[str]:
        """对多条文本进行情感分类。"""
        if self._use_ml:
            return predict(texts)  # type: ignore[return-value]
        return [detect_emotion(t) for t in texts]

    @property
    def using_ml(self) -> bool:
        """当前是否在使用 ML 模型（而非规则）。"""
        return self._use_ml
