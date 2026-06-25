from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


VOICE_MAP_TEMPLATE = {
    "阿米娅": {
        "engine": "gpt-sovits",
        "voice_dir": "local_voice_data/amiya",
        "profile": "amiya_v1",
        "notes": "填入阿米娅参考音频目录和模型配置",
    },
    "凯尔希": {
        "engine": "gpt-sovits",
        "voice_dir": "local_voice_data/kaltsit",
        "profile": "kaltsit_v1",
        "notes": "填入凯尔希参考音频目录和模型配置",
    },
    "旁白": {
        "engine": "edge-tts",
        "voice": "zh-CN-YunjianNeural",
        "notes": "旁白可先用通用 TTS 兜底",
    },
}


MANIFEST_ROWS = [
    ["file", "speaker", "language", "text", "seconds", "quality_note"],
    ["001.wav", "阿米娅", "zh", "博士，博士！", "2.0", "示例：干净、无 BGM"],
    ["002.wav", "阿米娅", "zh", "那就……拜托你了！", "3.0", "示例：轻微混响"],
]


def write_manifest(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(MANIFEST_ROWS)


def write_runbook(path: Path) -> None:
    content = """# GPT-SoVITS 执行规划

## 目标

用每个角色 30–60 秒的多段文字-语音对照样本，验证 GPT-SoVITS 是否能生成可用角色声音。

## 1. 准备角色样本

建议目录：

```text
local_voice_data/
  amiya/
    wavs/
      001.wav
      002.wav
    transcripts.csv
```

要求：无 BGM、无重叠人声、文本严格对齐。

## 2. 填写样本清单

复制 `gpt_sovits_sample_manifest.template.csv`，为每个角色填写真实音频、文本、时长和质量备注。

## 3. 填写 voice map

复制 `gpt_sovits_voice_map.template.json`，把角色名映射到真实 voice_dir 和 profile。

## 4. 运行 GPT-SoVITS

本仓库不直接封装 GPT-SoVITS 命令，因为不同安装方式和版本差异较大。实际命令应记录在实验记录中，至少包含：

```text
模型路径、参考音频、参考文本、待合成文本、输出路径、随机种子或推理参数
```

## 5. 保存结果

建议输出：

```text
investigation/docs/generated/gpt_sovits/audio/
investigation/docs/generated/gpt_sovits/runlog.json
investigation/docs/generated/gpt_sovits/runlog.md
```

## 6. 固化到文档

将关键结论更新到：

- `investigation/docs/05-GPT-SoVITS-核心路线.md`
- `investigation/docs/08-实验记录模板.md` 的复制记录
"""
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 GPT-SoVITS 调研执行规划和模板")
    parser.add_argument("--output-dir", default="investigation/docs/generated/gpt_sovits", help="输出目录")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "gpt_sovits_voice_map.template.json").write_text(
        json.dumps(VOICE_MAP_TEMPLATE, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_manifest(output_dir / "gpt_sovits_sample_manifest.template.csv")
    write_runbook(output_dir / "gpt_sovits_runbook.md")
    print(f"已生成 GPT-SoVITS 执行规划：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
