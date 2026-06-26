# 06-候选模型对比：CosyVoice / IndexTTS / Fish Speech

## 目标

在 GPT-SoVITS 主线之外，保留一套统一横评框架，用于比较 CosyVoice、IndexTTS、Fish Speech 是否更适合后续阶段。

## 候选定位

| 模型 | 关注点 | 本项目使用方式 |
| --- | --- | --- |
| CosyVoice | zero-shot voice cloning，多语种生成 | 参考音频 + prompt text + 待合成文本 |
| IndexTTS | controllable zero-shot TTS，中文/英文 | 单参考音频、中文术语和拼音控制表现 |
| Fish Speech | 多语种 TTS / voice cloning | 参考音频驱动的角色声音生成 |

## 统一输入

所有候选模型必须使用同一份 benchmark corpus：

```text
investigation/docs/generated/corpus/benchmark_cases.jsonl
```

不要为某个模型单独挑更容易的文本。

## 统一输出目录

```text
investigation/docs/generated/comparison/
  cosyvoice/
  indextts/
  fish_speech/
```

每个模型目录下建议保存：

```text
audio/
runlog.json
runlog.md
score.csv
notes.md
```

## 统一评分字段

| 字段 | 说明 |
| --- | --- |
| model | 模型名 |
| case_id | benchmark 样本 ID |
| success | 是否生成成功 |
| pronunciation_score | 中文发音 1–5 |
| similarity_score | 音色相似度 1–5 |
| stability_score | 稳定性 1–5 |
| latency_note | 速度或耗时备注 |
| issue | 问题描述 |

## 生成对比计划

```bash
python investigation/scripts/04_plan_model_comparison.py --output-dir investigation/docs/generated/comparison
```

输出：

- `model_comparison_matrix.csv`
- `model_comparison_plan.md`

## 决策规则

候选模型只有满足以下条件，才考虑进入主线：

1. 能稳定运行相同 benchmark corpus。
2. 音色相似度明显优于 GPT-SoVITS 或部署成本明显更低。
3. 多角色调度不需要大幅改造现有 JSONL 结构。
4. 实验记录可复现。

否则保留为候选，不投入主线工程化。
