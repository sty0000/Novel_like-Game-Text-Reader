"""训练中文对白情感分类模型。

输入：由 prepare_data.py 生成并人工审核过的 CSV 文件。
输出：model/ 目录，可直接被 EmotionClassifier 加载。

用法::

    # 基本训练（bert-base-chinese，国内自动走 hf-mirror）
    python -m scripts.emotion_classifier.train -i train_data.csv

    # 指定模型和参数
    python -m scripts.emotion_classifier.train -i train_data.csv \\
        --model bert-base-chinese --epochs 5 --batch-size 32

    # 训练完成后导出 ONNX 加速推理
    python -m scripts.emotion_classifier.train -i train_data.csv --export-onnx

依赖::
    pip install transformers torch datasets scikit-learn onnxruntime onnx
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from scripts.emotion_classifier.rules import EMOTION_LABELS

# 标签 ↔ id 映射
LABEL2ID = {label: i for i, label in enumerate(EMOTION_LABELS)}
ID2LABEL = {i: label for i, label in enumerate(EMOTION_LABELS)}


def load_data(csv_path: Path):
    """加载 CSV 标注数据，返回 texts 和 labels。"""
    texts: list[str] = []
    labels: list[int] = []

    with csv_path.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = (row.get("text") or "").strip()
            label = (row.get("emotion") or "").strip()
            if not text or label not in LABEL2ID:
                continue
            texts.append(text)
            labels.append(LABEL2ID[label])

    if not texts:
        raise ValueError(f"CSV 中没有有效标注数据。期望列: text, emotion")

    return texts, np.array(labels)


def compute_class_weights(labels: np.ndarray):
    """计算类别权重以应对不均衡数据。"""
    from collections import Counter

    counts = Counter(labels.tolist())
    total = len(labels)
    num_classes = len(EMOTION_LABELS)
    weights = np.zeros(num_classes, dtype=np.float32)
    for i in range(num_classes):
        weights[i] = total / (num_classes * counts.get(i, 1))
    return weights


def train_model(
    train_texts: list[str],
    train_labels: np.ndarray,
    val_texts: list[str],
    val_labels: np.ndarray,
    model_name: str,
    output_dir: Path,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    max_length: int,
    export_onnx: bool,
):
    """训练并保存模型。"""
    try:
        import torch
        from datasets import Dataset
        from transformers import (
            AutoConfig,
            AutoModelForSequenceClassification,
            AutoTokenizer,
            Trainer,
            TrainingArguments,
            DataCollatorWithPadding,
        )
    except ImportError:
        raise ImportError(
            "训练需要 transformers, datasets, torch。运行："
            "pip install transformers datasets torch"
        )

    # ── 加载 tokenizer 和模型（国内自动走 HF 镜像） ──
    import os as _os
    _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

    print(f"加载预训练模型: {model_name}", file=sys.stderr)
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    config = AutoConfig.from_pretrained(
        model_name,
        num_labels=len(EMOTION_LABELS),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, config=config
    )

    # ── 构建 HuggingFace Dataset ──
    def tokenize_fn(examples):
        return tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
        )

    train_dataset = Dataset.from_dict(
        {"text": train_texts, "label": train_labels.tolist()}
    )
    train_dataset = train_dataset.map(tokenize_fn, batched=True)
    train_dataset.set_format(
        type="torch", columns=["input_ids", "attention_mask", "label"]
    )

    val_dataset = Dataset.from_dict(
        {"text": val_texts, "label": val_labels.tolist()}
    )
    val_dataset = val_dataset.map(tokenize_fn, batched=True)
    val_dataset.set_format(
        type="torch", columns=["input_ids", "attention_mask", "label"]
    )

    # ── 类别权重（处理不均衡） ──
    class_weights = compute_class_weights(train_labels)
    print(f"类别权重: {dict(zip(EMOTION_LABELS, class_weights))}", file=sys.stderr)

    class WeightedTrainer(Trainer):
        def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None, **kwargs):
            # BatchEncoding doesn't support pop; extract labels explicitly
            labels = inputs.get("label", inputs.get("labels"))
            model_inputs = {k: v for k, v in inputs.items() if k not in ("label", "labels")}
            outputs = model(**model_inputs)
            loss_fn = torch.nn.CrossEntropyLoss(
                weight=torch.tensor(class_weights, device=model.device)
            )
            loss = loss_fn(outputs.logits, labels)
            return (loss, outputs) if return_outputs else loss

    # ── 训练配置 ──
    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=learning_rate,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size * 2,
        num_train_epochs=epochs,
        weight_decay=0.01,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        logging_dir=str(output_dir / "logs"),
        logging_steps=10,
        report_to="none",
    )

    trainer = WeightedTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=DataCollatorWithPadding(tokenizer),
    )

    # ── 训练 ──
    print(f"开始训练 (epochs={epochs}, batch={batch_size}, lr={learning_rate})", file=sys.stderr)
    trainer.train()

    # ── 评估 ──
    eval_results = trainer.evaluate()
    print(f"验证集评估: {eval_results}", file=sys.stderr)

    # ── 保存模型 ──
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    # 同时保存 config 覆盖
    config.save_pretrained(str(output_dir))

    print(f"模型已保存到: {output_dir}", file=sys.stderr)

    # ── 导出 ONNX ──
    if export_onnx:
        export_to_onnx(model, tokenizer, output_dir, max_length)


def export_to_onnx(model, tokenizer, output_dir: Path, max_length: int):
    """将 PyTorch 模型导出为 ONNX 格式。"""
    try:
        import torch
        import onnx
    except ImportError:
        print("导出 ONNX 需要 onnx 库。运行: pip install onnx", file=sys.stderr)
        return

    onnx_path = output_dir / "model.onnx"
    device = torch.device("cpu")
    model.to(device)
    model.eval()

    # 构造一个虚拟输入
    dummy_text = "你好"
    dummy_inputs = tokenizer(
        dummy_text,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )

    input_names = ["input_ids", "attention_mask"]

    # 动态轴：batch 和 sequence 都是可变的
    dynamic_axes = {
        "input_ids": {0: "batch", 1: "sequence"},
        "attention_mask": {0: "batch", 1: "sequence"},
        "logits": {0: "batch"},
    }

    with torch.no_grad():
        torch.onnx.export(
            model,
            (dummy_inputs["input_ids"], dummy_inputs["attention_mask"]),
            str(onnx_path),
            input_names=input_names,
            output_names=["logits"],
            dynamic_axes=dynamic_axes,
            opset_version=14,
        )

    # 验证 ONNX 模型
    onnx_model = onnx.load(str(onnx_path))
    onnx.checker.check_model(onnx_model)
    print(f"ONNX 模型已导出: {onnx_path}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="训练中文对白情感分类模型"
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="标注好的训练数据 CSV 文件",
    )
    parser.add_argument(
        "--model",
        default="bert-base-chinese",
        help="预训练模型名称。轻量可选: voidful/albert_chinese_tiny (~16MB)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=5,
        help="训练轮数（默认 5）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="批次大小（默认 16）",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-5,
        help="学习率（默认 2e-5）",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=128,
        help="最大 token 长度（默认 128）",
    )
    parser.add_argument(
        "--val-split",
        type=float,
        default=0.15,
        help="验证集比例（默认 0.15）",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="输出目录（默认为 scripts/emotion_classifier/model/）",
    )
    parser.add_argument(
        "--export-onnx",
        action="store_true",
        help="训练完成后导出 ONNX 格式",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="随机种子",
    )
    args = parser.parse_args()

    # 设置随机种子
    try:
        import torch
        torch.manual_seed(args.seed)
    except ImportError:
        pass

    # 加载数据
    csv_path = Path(args.input)
    if not csv_path.exists():
        print(f"错误: 找不到文件 {csv_path}", file=sys.stderr)
        return 1

    try:
        texts, labels = load_data(csv_path)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    print(f"已加载 {len(texts)} 条标注数据", file=sys.stderr)
    print(f"标签分布:", file=sys.stderr)
    for label in EMOTION_LABELS:
        count = (labels == LABEL2ID[label]).sum()
        print(f"  {label}: {count}", file=sys.stderr)

    # 划分验证集
    indices = np.random.RandomState(args.seed).permutation(len(texts))
    val_size = max(1, int(len(texts) * args.val_split))
    train_indices = indices[val_size:]
    val_indices = indices[:val_size]

    train_texts = [texts[i] for i in train_indices]
    train_labels = labels[train_indices]
    val_texts = [texts[i] for i in val_indices]
    val_labels = labels[val_indices]

    print(
        f"训练集: {len(train_texts)} 条, 验证集: {len(val_texts)} 条",
        file=sys.stderr,
    )

    # 输出目录
    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path(__file__).resolve().parent / "model"
    )

    # 训练
    try:
        train_model(
            train_texts=train_texts,
            train_labels=train_labels,
            val_texts=val_texts,
            val_labels=val_labels,
            model_name=args.model,
            output_dir=output_dir,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            max_length=args.max_length,
            export_onnx=args.export_onnx,
        )
    except ImportError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
