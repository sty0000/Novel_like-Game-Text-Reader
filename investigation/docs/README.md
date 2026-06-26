# TTS 模型调研目录

本目录用于沉淀《明日方舟》剧情朗读项目的 TTS 模型调研、执行手册、评估标准和可复现实验脚本。

## 基础结论

基于上一轮 deep-research，当前路线固定为：

1. **短期闭环：Edge TTS**  
   用于快速验证“结构化剧情文本 → 多角色分段 → 音频文件 → 记录归档”的工程流程。它不支持训练特定声音。
2. **核心路线：GPT-SoVITS**  
   最贴近“用总时长不超过约 1 分钟的多段一句话文字-语音对照语料，训练或复刻特定声音”的需求。
3. **后续横评：CosyVoice / IndexTTS / Fish Speech**  
   作为 zero-shot / voice cloning 候选，用相同文本集、相同记录格式横向比较。
4. **实验边界：ChatTTS**  
   适合对话风格实验，但不作为当前特定声音训练主线。

## 文档阅读顺序

1. [00-总览与路线图](00-总览与路线图.md)
2. [01-模型选型结论](01-模型选型结论.md)
3. [02-评估维度与验收标准](02-评估维度与验收标准.md)
4. [03-执行手册](03-执行手册.md)
5. [04-Edge-TTS-短期闭环](04-Edge-TTS-短期闭环.md)
6. [05-GPT-SoVITS-核心路线](05-GPT-SoVITS-核心路线.md)
7. [06-候选模型对比-CosyVoice-IndexTTS-FishSpeech](06-候选模型对比-CosyVoice-IndexTTS-FishSpeech.md)
8. [07-ChatTTS-实验边界](07-ChatTTS-实验边界.md)
9. [08-实验记录模板](08-实验记录模板.md)
10. [09-结果固化指南](09-结果固化指南.md)
11. [10-情绪标注与多角色演绎方案](10-情绪标注与多角色演绎方案.md)

## 脚本入口

脚本位于 `investigation/scripts/`。推荐先运行：

```bash
python investigation/scripts/00_env_check.py --output-dir investigation/docs/generated/env
python investigation/scripts/01_build_benchmark_corpus.py --output-dir investigation/docs/generated/corpus
python investigation/scripts/02_plan_edge_tts_run.py --corpus investigation/docs/generated/corpus/benchmark_cases.jsonl --output-dir investigation/docs/generated/edge_tts
python investigation/scripts/03_plan_gpt_sovits_run.py --output-dir investigation/docs/generated/gpt_sovits
python investigation/scripts/04_plan_model_comparison.py --output-dir investigation/docs/generated/comparison
python investigation/scripts/05_generate_report_assets.py --generated-dir investigation/docs/generated --output-dir investigation/docs/generated/report
```

这些脚本默认只生成计划、模板、记录和报告资产，不下载模型权重，也不提交音频文件。

## HTML 阅读版

- [README.html](html/README.html)
- [执行手册.html](html/执行手册.html)

HTML 是阅读增强版，Markdown 是源文档。
