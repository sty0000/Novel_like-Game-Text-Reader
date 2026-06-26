# 05-GPT-SoVITS-核心路线

## 定位

GPT-SoVITS 是当前 TTS 调研的核心路线，因为它最贴近以下需求：

- 每个声音只有多段一句话语音。
- 总长度约 1 分钟以内。
- 需要训练或复刻特定声音。
- 最终按角色切换声音演绎剧情对白。

## 数据准备

每个角色建议建立独立目录：

```text
local_voice_data/
  amiya/
    wavs/
      001.wav
      002.wav
      003.wav
    transcripts.csv
    notes.md
  kaltsit/
    wavs/
      001.wav
      002.wav
    transcripts.csv
    notes.md
```

`transcripts.csv` 推荐字段：

```csv
file,speaker,language,text,seconds,quality_note
001.wav,阿米娅,zh,博士，博士！,2.1,干净无背景音
002.wav,阿米娅,zh,那就……拜托你了！,3.0,轻微混响
```

## 样本质量要求

优先选择：

- 无 BGM。
- 无其他人声。
- 无明显混响。
- 文本和音频严格对齐。
- 每句 2–8 秒。
- 总时长 30–60 秒。

避免：

- 游戏内 BGM 明显的语音。
- 两个角色重叠说话。
- 爆音、削波、音量变化过大。
- 文本缺字或转写不准。

## voice map

后续剧情 JSONL 可以通过 speaker 映射 voice profile：

```json
{
  "阿米娅": {
    "engine": "gpt-sovits",
    "voice_dir": "local_voice_data/amiya",
    "profile": "amiya_v1"
  },
  "凯尔希": {
    "engine": "gpt-sovits",
    "voice_dir": "local_voice_data/kaltsit",
    "profile": "kaltsit_v1"
  },
  "旁白": {
    "engine": "edge-tts",
    "voice": "zh-CN-YunjianNeural"
  }
}
```

## 执行规划生成

生成 GPT-SoVITS 执行文档和模板：

```bash
python investigation/scripts/03_plan_gpt_sovits_run.py --output-dir investigation/docs/generated/gpt_sovits
```

输出：

- `gpt_sovits_voice_map.template.json`
- `gpt_sovits_sample_manifest.template.csv`
- `gpt_sovits_runbook.md`

## 实验记录重点

每个角色至少记录：

- 样本总时长。
- 样本数量。
- 样本噪声情况。
- 是否使用微调。
- 推理文本。
- 输出音频路径。
- 音色相似度评分。
- 发音准确度评分。
- 失败样本和原因。

## 验收标准

第一轮只要求：

- 一个角色能跑通。
- 至少 5 条 benchmark 文本有输出。
- 短句不明显吞字或错读。
- 输出和参数完整记录。

后续再提高到：

- 2–3 个角色可切换。
- 同一角色多句音色稳定。
- 与 Edge TTS demo 的工程流程兼容。
