# 04-Edge-TTS-短期闭环

## 定位

Edge TTS 是短期工程闭环工具，用来验证：

- benchmark 文本是否适合朗读。
- 分段、命名、输出目录是否合理。
- 后续多角色调度流程是否能落盘和记录。

它不解决特定声音训练，也不能替代 GPT-SoVITS 的角色音色路线。

## 适用范围

适合：

- 旁白 demo。
- 临时角色声音。
- 检查预处理文本是否自然。
- 检查音频文件生成和拼接流程。

不适合：

- 克隆阿米娅、凯尔希等特定声音。
- 用 1 分钟语料训练角色模型。

## 推荐命令生成流程

先生成 benchmark corpus：

```bash
python investigation/scripts/01_build_benchmark_corpus.py --output-dir investigation/docs/generated/corpus
```

再生成 Edge TTS 命令清单：

```bash
python investigation/scripts/02_plan_edge_tts_run.py --corpus investigation/docs/generated/corpus/benchmark_cases.jsonl --output-dir investigation/docs/generated/edge_tts
```

查看输出：

```text
investigation/docs/generated/edge_tts/edge_tts_commands.md
investigation/docs/generated/edge_tts/edge_tts_run_template.json
```

## 实际合成建议

如果要真实调用现有 `scripts/tts_edge.py`，建议把单条文本保存为临时 txt，再执行：

```bash
python scripts/tts_edge.py --input investigation/docs/generated/edge_tts/input/case_001_short_dialogue.txt --output investigation/docs/generated/edge_tts/audio/case_001_short_dialogue.mp3 --voice zh-CN-XiaoxiaoNeural
```

## 结果记录

每条样本记录：

- case_id
- 输入文本
- voice
- 命令
- 输出音频路径
- 是否成功
- 主观问题：断句、语气、误读、音量

## 验收标准

通过条件：

- 每个 case 都有可复制命令。
- 输出路径统一。
- 失败信息可记录。
- 能人工播放检查。

不通过条件：

- 命令缺少输入路径或输出路径。
- 输出文件命名无法追踪到 case_id。
- 结果没有记录模板。
