# investigation/scripts 使用说明

这些脚本用于把 TTS 模型调研流程固化为可复现的文件资产。它们默认不下载模型、不安装依赖、不提交音频，只生成环境记录、benchmark 文本集、执行命令清单、模板和报告。

## 推荐运行顺序

```bash
python investigation/scripts/00_env_check.py --output-dir investigation/docs/generated/env
python investigation/scripts/01_build_benchmark_corpus.py --output-dir investigation/docs/generated/corpus
python investigation/scripts/02_plan_edge_tts_run.py --corpus investigation/docs/generated/corpus/benchmark_cases.jsonl --output-dir investigation/docs/generated/edge_tts
python investigation/scripts/03_plan_gpt_sovits_run.py --output-dir investigation/docs/generated/gpt_sovits
python investigation/scripts/04_plan_model_comparison.py --output-dir investigation/docs/generated/comparison
python investigation/scripts/05_generate_report_assets.py --generated-dir investigation/docs/generated --output-dir investigation/docs/generated/report
```

## 输出约定

- 环境信息：`investigation/docs/generated/env/`
- benchmark 文本：`investigation/docs/generated/corpus/`
- Edge TTS 执行计划：`investigation/docs/generated/edge_tts/`
- GPT-SoVITS 执行计划：`investigation/docs/generated/gpt_sovits/`
- 候选模型对比计划：`investigation/docs/generated/comparison/`
- 汇总报告：`investigation/docs/generated/report/`

## 注意

- 真实语音样本、模型权重和大音频文件不要提交到仓库。
- 每次真实模型实验后，请把命令、输入路径、输出路径和评分写回 `investigation/docs/08-实验记录模板.md` 的复制记录中。
