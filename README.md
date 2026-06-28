# Novel Like Game Text Reader

## Goal

本项目目标是构建一条面向《明日方舟》剧情的语料处理流水线：从 [PRTS wiki](https://prts.wiki/w/%E9%A6%96%E9%A1%B5) 获取剧情对话源码，对角色对白、旁白、舞台提示等内容做结构化预处理，再通过 TTS 将视觉文字转换为适合收听的有声文本。

当前阶段聚焦三件事：

1. 抓取 PRTS wiki 中单个剧情页面或剧情目录中的 raw source。
2. 设计面向 TTS 的清洗、分段和结构化输出格式。
3. 提供一个轻量 TTS 示例脚本，先打通“文本 → 音频”的最小闭环。

```text
PRTS wiki → get_text.py / story_reader.py → raw story source → preprocessing → TTS-ready segments → audio
```

## Requirements

- Python 3.10+
- 抓取剧情需要联网访问 `https://prts.wiki/`
- 核心抓取脚本仅使用 Python 标准库
- TTS 示例脚本需要额外安装 `edge-tts`

```bash
python -m pip install edge-tts
```

## Story Source Fetcher

`get_text.py` 是底层抓取器，用于从 PRTS wiki 获取一个剧情页面的原始 wiki 源码。

### Command Line

```powershell
python get_text.py "W2G/BEG" -o beg.txt
python get_text.py "https://prts.wiki/index.php?title=W2G/BEG&action=edit" -o beg.txt
```

如果省略 `-o`，`get_text.py` 会把 raw source 输出到 stdout。

### Python Interface

```python
from get_text import fetch_story_text

raw_text = fetch_story_text("W2G/BEG")
```

`fetch_story_text(source)` 接受页面标题、普通 wiki URL 或编辑页 URL，并返回原始剧情源码字符串。抓取逻辑优先使用 MediaWiki API；当传输或 API 解析失败时，会回退到编辑页源码文本框。

## Story Picker App

`story_reader.py` 是面向用户的剧情选择入口。它从 PRTS wiki 的“剧情一览”页面载入候选剧情，允许通过关键词筛选和序号选择，然后导出选中页面的 raw source。

### Interactive Mode

```powershell
python story_reader.py
```

### List Mode

```powershell
python story_reader.py --list
```

### Direct Mode

如果已经知道剧情标题或 URL，可以绕过交互选择：

```powershell
python story_reader.py "W2G/BEG"
python story_reader.py "W2G/BEG" -o samples/W2G_BEG.raw.txt
```

未指定 `-o` 时，`story_reader.py` 会根据标题生成默认 `.txt` 文件名。

## 语料预处理设计

PRTS 页面返回的是 MediaWiki 源码，不建议直接输入 TTS。推荐保留 raw source，并生成独立的结构化中间格式，方便后续调试、回溯和替换 TTS 引擎。

### 推荐流水线

```text
raw wikitext
  → normalize
  → line/block split
  → classify blocks
  → extract speaker / text / narration / stage direction
  → merge and split TTS units
  → JSONL or TXT for synthesis
```

### 推荐 JSONL 字段

```json
{
  "story_title": "W2G/BEG",
  "segment_id": 1,
  "speaker": "旁白",
  "role": "narration",
  "text": "……",
  "source_kind": "prts_raw",
  "original_text": "……"
}
```

### 分类建议

- `scene_title`：章节、场景或转场标题。
- `dialogue`：角色对白，尽量保留 `speaker`。
- `narration`：无明确说话人的叙述文本。
- `stage_direction`：动作、音效、表情、停顿等舞台提示；默认不直接朗读，或用旁白音色弱化处理。
- `meta`：导航模板、分类、站点链接、注释等不适合朗读的元信息。
- `unknown`：暂时无法稳定判断的内容，保留给人工检查。

### TTS 分段原则

- 场景切换、说话人切换、旁白/对白切换时断开。
- 同一说话人连续短句可以合并，减少机械停顿。
- 单段目标长度建议为 80–180 个中文字符。
- 单段上限建议为 220–280 个中文字符，超过后按 `。！？；，、……——` 等中文标点二次切分。
- 不要无差别删除 `{{...}}` 模板和 `[[...]]` 链接；它们可能包含角色、剧情结构或显示文本。

## TTS 方案

| 方案 | 适合阶段 | 优点 | 注意事项 |
| --- | --- | --- | --- |
| [Edge TTS](https://github.com/rany2/edge-tts) | 第一阶段 demo | 接入简单、无需本地模型、中文 voice 可用 | 依赖在线服务，不适合完全离线 |
| [ChatTTS](https://github.com/2noise/ChatTTS) | 对话实验 | 面向中英文对话，适合探索自然对白 | 本地环境和生成稳定性需要单独验证 |
| [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) | 后续高质量本地化 | 多语种、零样本能力，适合角色音色探索 | 推理环境较重 |
| [Fish Speech](https://github.com/fishaudio/fish-speech) | 后续本地流水线 | 开源多语种 TTS/语音生成能力强 | 需要模型与推理资源 |
| [IndexTTS](https://github.com/index-tts/index-tts) | 后续中文高质量候选 | 面向中文/英文的高质量 TTS 方向 | 接入方式需按官方项目更新验证 |
| [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) | 后续候选 | 多语种和自然语言控制潜力 | 需确认具体 API 或本地部署流程 |

建议优先用 Edge TTS 打通工程闭环，再根据质量、离线需求和角色音色需求接入本地模型。

## Edge TTS 示例脚本

`scripts/tts_edge.py` 可以把普通文本或 JSONL 中的 `text` 字段合成为音频。

### TXT 输入

```powershell
python scripts/tts_edge.py --input samples/W2G_BEG.raw.txt --output audio/W2G_BEG.mp3 --voice zh-CN-XiaoxiaoNeural
```

### JSONL 输入

```powershell
python scripts/tts_edge.py --format jsonl --input segments/W2G_BEG.jsonl --output audio/W2G_BEG.mp3 --voice zh-CN-YunjianNeural
```

常用参数：

- `--voice`：Edge TTS voice 名称。
- `--rate`：语速，例如 `-10%` 或 `+15%`。
- `--volume`：音量，例如 `+0%`。
- `--text-field`：JSONL 中要合成的字段名，默认 `text`。

## 完整流水线

当前端到端流水线如下：

```text
PRTS wiki（MediaWiki 源码）
  │
  └─ get_text.py          → 原始 wiki 源码 (.txt)
       │
       └─ parse_story.py  → 结构化段 (.segments.jsonl)
            │               角色 / 旁白 / 场景 / 情绪
            │
            └─ speech_modifier.py → 说书脚本 (.enriched.jsonl)
                 │                  语境前缀、动作叙述、
                 │                  身份描述、轻声/沉默处理
                 │
                 └─ tts_edge.py → 音频 (.mp3)
```

实际使用时可以直接用 `story_reader.py` 一键走完全程：

```powershell
python story_reader.py "W2G/BEG"
```

## 剧情解析（parse_story.py）

`scripts/parse_story.py` 将 wiki 源码解析为结构化的 JSONL 段。

### 解析能力

- **角色对白**：识别 `[name="xxx"]` 格式的对话，提取说话人和内容
- **旁白叙述**：无标记的纯文本归为旁白
- **场景切换**：检测 `[Header]`、`[Background]`、`[Image]` 等场景控制指令
- **模板过滤**：自动跳过 `{{...}}` 模板控制行

### 输出字段

```json
{
  "story_title": "10-5 城市的呼吸/BEG",
  "segment_id": 1,
  "role": "dialogue",
  "speaker": "推进之王",
  "text": "我们已经来到伦蒂尼姆城内了。",
  "scene_id": 4,
  "scene_kind": "Background",
  "scene_label": "27_g7_subway",
  "source_file": "10-5_城市的呼吸_BEG.txt",
  "line_start": 83,
  "line_end": 83
}
```

### 命令行

```powershell
# 单个文件
python scripts/parse_story.py input.txt -o parsed/story.segments.jsonl

# 批量处理目录
python scripts/parse_story.py txt/ --output-dir parsed/
```

## 语音修饰：说书脚本（speech_modifier.py）

`scripts/speech_modifier.py` 是整个流水线的核心转换层。它把结构化的 JSONL 段转成适合 TTS 朗读的**说书人脚本**，而非机械的"聊天记录转文字"。

### 转换规则总览

| 原始文本特征 | 转换结果 | 示例 |
| --- | --- | --- |
| 同一说话人连续发言 | 合并，只保留首段前缀 | "阿米娅说：……"（一整段） |
| 说话人切换 | 生成语境前缀 | "推进之王回应道："、"因陀罗反驳：" |
| 场景切换 | 第一人用"开口道" | "曼弗雷德开口道：" |
| 括号动作 `(砸入地面)` | **插入旁白段**，叙述动作 | 旁白："盾卫将盾牌狠狠砸入地面。" |
| 括号悄声 `（低声讨论）` | 轻声修饰前缀 | "盾卫低声惊呼：" |
| 说话人 `？？？` | 身份描述 | "神秘人说：" |
| 说话人 `name？` | 不确定身份描述 | "那个像是战士比尔的人说：" |
| 纯 `......` 沉默 | 标记跳过，TTS 不念 | — |

### 语境前缀规则

`speech_modifier` 根据对话上下文自动选择五种基础语式：

| 基础语式 | 触发条件 | 中性示例 |
| --- | --- | --- |
| `speak` | 默认，说话人切换 | "推进之王说：" |
| `continue` | 同说话人不同情绪 | "推进之王接着说：" |
| `scene_first` | 场景切换后首句 | "推进之王开口道：" |
| `respond` | 回应前一人 | "推进之王回应道：" |
| `retort` | A→B→A 且有反驳信号 | "推进之王反驳道：" |
| `aside` | 括号轻声/内心独白 | "推进之王轻声说：" |

每种基础语式 × 20 种情绪 = **120 种前缀组合**，例如：

- "推进之王愤怒的反驳："
- "阿米娅低声惊呼："
- "曼弗雷德沉吟道："

### 情绪标签（20 类）

| 标签 | 含义 | 触发示例 |
| --- | --- | --- |
| `neutral` | 平静/中性 | 默认 |
| `question` | 疑问 | ？结尾 |
| `shock_question` | 震惊质问 | ？！ |
| `shocked` | 震惊 | ！+ 震惊关键词 |
| `angry` | 愤怒 | ！+ 愤怒关键词 |
| `happy` | 开心 | ！+ 喜悦关键词 |
| `sad` | 悲伤 | 悲伤关键词 |
| `fearful` | 恐惧 | ！+ 恐惧关键词 |
| `ponder` | 思索 | 思索关键词 |
| `hesitate` | 犹豫 | ……开头 / 呃开头 |
| `sigh` | 叹息 | 唉/咳开头 |
| `laugh` | 笑 | 哈哈/呵呵 |
| `determined` | 坚定/决心 | 交给我吧 / 我绝不会 |
| `arrogant` | 傲慢/自负 | 哼 / 就凭你 / 不过如此 |
| `gentle` | 温柔/安慰 | 没事的 / 有我在 |
| `urgent` | 急切/紧迫 | 快走 / 来不及了 |
| `desperate` | 绝望 | 一切都完了 / 没救了 |
| `relieved` | 释然/松了口气 | 幸好 / 终于 / 放心了 |
| `serious` | 严肃/庄重 | 我以…起誓 / 郑重 |
| `disgusted` | 厌恶/反感 | 恶心 / 别碰我 |

### 命令行（speech_modifier）

```powershell
# 给已解析的 JSONL 加上说书前缀
python scripts/speech_modifier.py parsed/story.segments.jsonl -o parsed/story.enriched.jsonl
```

### 输出新增字段

```json
{
  "speech_prefix": "推进之王反驳道：",
  "emotion": "angry",
  "tts_text": "我们不是来谈判的。",
  "speaker_display": "推进之王",
  "identity": "known",
  "has_paren": false,
  "paren_type": null,
  "is_silence": false
}
```

## 情感分类器（emotion_classifier/）

`scripts/emotion_classifier/` 提供可插拔的情感检测后端。当前包含规则版 fallback 和 ML 模型训练/推理的完整基础设施。

### 模块结构

```text
scripts/emotion_classifier/
├── __init__.py         # 对外接口 EmotionClassifier, detect_emotion
├── rules.py            # 规则版 detect_emotion（12 标签 + 关键词匹配）
├── classifier.py       # 推理引擎：自动加载模型，无模型时回退规则
├── prepare_data.py     # 从 parsed JSONL 提取对白 → CSV 标注格式
├── train.py            # 微调 bert-base-chinese 并导出 ONNX
└── model/              # 训练好的模型文件（ONNX / safetensors）
```

### 使用模型

```python
from scripts.emotion_classifier import EmotionClassifier

clf = EmotionClassifier()           # 有模型用模型，没有回退规则
clf = EmotionClassifier(model_dir=None)  # 强制只用规则
emotion = clf.predict("你这说的是什么话？！")  # → "shock_question"
```

默认自动查找 `scripts/emotion_classifier/model/` 下的 ONNX 或 PyTorch 模型。找不到时回退到 `rules.py` 的规则检测。

### 训练自己的模型

```bash
# 1. 生成标注数据
python -m scripts.emotion_classifier.prepare_data parsed/ -o train_data.csv

# 2. 人工审核修正 CSV 中的 emotion 列

# 3. 训练（国内自动走 hf-mirror 镜像）
python -m scripts.emotion_classifier.train -i train_data.csv --epochs 5 --export-onnx

# 4. 训练完成后 speech_modifier.py 自动切换为 ML 模式
```

训练参数：

- `--model`：预训练模型名，默认 `bert-base-chinese`（约 400MB），轻量可选 `voidful/albert_chinese_tiny`（约 16MB）
- `--epochs`：训练轮数，默认 5
- `--batch-size`：批次大小，默认 16
- `--export-onnx`：训练完成后导出 ONNX 格式（推荐，推理更快且不需要 PyTorch）

## GUI 界面（story_reader_gui.py）

`story_reader_gui.py` 提供一个简洁的图形界面，用于浏览、搜索剧情并一键生成语音。

```powershell
python story_reader_gui.py
```

功能：

- 启动时自动从 PRTS wiki 加载剧情目录
- 关键词实时搜索过滤
- 双击或点击按钮一键走完抓取→解析→说书脚本→语音合成的完整流水线
- 可调节语音、语速、音量
- 后台处理，界面不卡顿

依赖：`tkinter`（Python 自带，无需额外安装）。

## Validation

基础检查：

```bash
python -m compileall get_text.py story_reader.py scripts/tts_edge.py
python get_text.py --help
python story_reader.py --help
python scripts/tts_edge.py --help
```

联网抓取检查：

```bash
python story_reader.py --list
python get_text.py "W2G/BEG" -o samples/W2G_BEG.raw.txt
python story_reader.py "W2G/BEG" -o samples/W2G_BEG.reader.txt
```

错误路径检查：

```bash
python get_text.py "不存在的标题"
```

期望行为：输出明确的中文错误信息，不生成空白成功文件。
