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
