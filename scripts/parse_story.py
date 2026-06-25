from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional


DEFAULT_NARRATOR = "\u65c1\u767d"
BRACKET_SPEECH_RE = re.compile(
    r'^\[(?:name|character)\s*=\s*"(?P<speaker>[^"]+)"[^\]]*\]\s*(?P<text>.*)$',
    re.IGNORECASE,
)
DIRECTIVE_RE = re.compile(r'^\[(?P<kind>[A-Za-z]+)(?:\((?P<params>.*)\))?\]\s*(?P<trailing>.*)$')
PARAM_RE = re.compile(r'(\w+)\s*=\s*(?:"(?P<quoted>[^"]*)"|(?P<bare>[^,\)]+))')
SCENE_SWITCH_KINDS = {"header", "background", "image"}


@dataclass
class SceneState:
    scene_id: int = 0
    scene_kind: str = ""
    scene_label: str = ""
    scene_ref: str = ""
    scene_start_line: int = 0


@dataclass
class Segment:
    story_title: str
    segment_id: int
    role: str
    speaker: str
    text: str
    source_file: str
    line_start: int
    line_end: int
    scene_id: int
    scene_kind: str
    scene_label: str
    scene_ref: str
    scene_start_line: int
    source_kind: str = "prts_raw"


def iter_input_files(inputs: list[str]):
    for raw_input in inputs:
        path = Path(raw_input)
        if path.is_dir():
            yield from sorted(path.glob("*.txt"))
        else:
            yield path


def is_template_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("{{") or stripped.startswith("}}")


def normalize_text(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


def parse_directive(line: str) -> Optional[dict[str, str]]:
    match = DIRECTIVE_RE.match(line)
    if not match:
        return None

    kind = match.group("kind")
    params_text = match.group("params") or ""
    trailing = normalize_text(match.group("trailing"))

    params: dict[str, str] = {}
    for param_match in PARAM_RE.finditer(params_text):
        key = param_match.group(1)
        value = param_match.group("quoted")
        if value is None:
            value = normalize_text(param_match.group("bare") or "")
        params[key] = value

    return {
        "kind": kind,
        "kind_lower": kind.lower(),
        "trailing": trailing,
        "params_json": json.dumps(params, ensure_ascii=False),
    }


def directive_params(params_json: str) -> dict[str, str]:
    try:
        return json.loads(params_json)
    except json.JSONDecodeError:
        return {}


def update_scene_state(scene: SceneState, line: str, line_number: int) -> bool:
    directive = parse_directive(line)
    if not directive:
        return False

    kind_lower = directive["kind_lower"]
    if kind_lower not in SCENE_SWITCH_KINDS:
        return False

    params = directive_params(directive["params_json"])
    scene.scene_id += 1
    scene.scene_kind = directive["kind"]
    scene.scene_start_line = line_number

    if kind_lower == "header":
        if directive["trailing"]:
            scene.scene_label = directive["trailing"]
        scene.scene_ref = params.get("key") or params.get("name") or scene.scene_ref
    elif kind_lower == "background":
        scene.scene_ref = params.get("image") or params.get("key") or params.get("name") or ""
        scene.scene_label = scene.scene_ref or scene.scene_label
    elif kind_lower == "image":
        scene.scene_ref = params.get("image") or params.get("key") or params.get("name") or ""
        scene.scene_label = scene.scene_ref or scene.scene_label

    return True


def flush_segment(
    segments: list[Segment],
    story_title: str,
    segment_id: int,
    role: Optional[str],
    speaker: Optional[str],
    lines: list[str],
    line_start: Optional[int],
    line_end: Optional[int],
    source_file: str,
    scene: SceneState,
) -> int:
    if not role or not speaker or not lines or line_start is None or line_end is None:
        lines.clear()
        return segment_id

    cleaned_lines = [normalize_text(line) for line in lines]
    text = "\n".join(line for line in cleaned_lines if line)
    if not text:
        lines.clear()
        return segment_id

    segments.append(
        Segment(
            story_title=story_title,
            segment_id=segment_id,
            role=role,
            speaker=speaker,
            text=text,
            source_file=source_file,
            line_start=line_start,
            line_end=line_end,
            scene_id=scene.scene_id,
            scene_kind=scene.scene_kind,
            scene_label=scene.scene_label,
            scene_ref=scene.scene_ref,
            scene_start_line=scene.scene_start_line,
        )
    )
    lines.clear()
    return segment_id + 1


def extract_segments(text: str, story_title: str, source_file: str) -> list[Segment]:
    segments: list[Segment] = []
    pending_lines: list[str] = []
    pending_role: Optional[str] = None
    pending_speaker: Optional[str] = None
    pending_start: Optional[int] = None
    pending_end: Optional[int] = None
    scene = SceneState()

    def flush() -> None:
        nonlocal pending_role, pending_speaker, pending_start, pending_end
        flush_segment(
            segments,
            story_title,
            len(segments) + 1,
            pending_role,
            pending_speaker,
            pending_lines,
            pending_start,
            pending_end,
            source_file,
            scene,
        )
        pending_role = None
        pending_speaker = None
        pending_start = None
        pending_end = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line:
            flush()
            continue

        if is_template_line(line):
            flush()
            continue

        bracket_match = BRACKET_SPEECH_RE.match(line)
        if bracket_match:
            flush()
            speaker = normalize_text(bracket_match.group("speaker")) or DEFAULT_NARRATOR
            content = normalize_text(bracket_match.group("text"))
            if content:
                pending_role = "dialogue"
                pending_speaker = speaker
                pending_start = line_number
                pending_end = line_number
                pending_lines.append(content)
                flush()
            continue

        if update_scene_state(scene, line, line_number):
            flush()
            continue

        if line.startswith("["):
            flush()
            continue

        if pending_role == "dialogue" and pending_speaker:
            pending_lines.append(normalize_text(line))
            pending_end = line_number
            continue

        if pending_role is None:
            pending_role = "narration"
            pending_speaker = DEFAULT_NARRATOR
            pending_start = line_number
            pending_end = line_number
            pending_lines.append(normalize_text(line))
            continue

        pending_lines.append(normalize_text(line))
        pending_end = line_number

    flush()
    return segments


def write_jsonl(segments: Iterable[Segment], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for segment in segments:
            handle.write(json.dumps(asdict(segment), ensure_ascii=False) + "\n")


def default_output_path(input_path: Path, output_dir: Path) -> Path:
    return output_dir / f"{input_path.stem}.segments.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract narration, speaker, dialogue, and scene state from raw story text")
    parser.add_argument("inputs", nargs="+", help="Input .txt files or directories containing .txt files")
    parser.add_argument("-o", "--output", help="Output JSONL file when processing one input file")
    parser.add_argument("--output-dir", default="segments", help="Output directory when processing multiple inputs")
    args = parser.parse_args()

    input_paths = list(iter_input_files(args.inputs))
    if not input_paths:
        print("Error: no input files found", file=sys.stderr)
        return 1

    if args.output:
        if len(input_paths) != 1:
            print("Error: --output can only be used with one input file", file=sys.stderr)
            return 1
        output_paths = [Path(args.output)]
    else:
        output_dir = Path(args.output_dir)
        output_paths = [default_output_path(path, output_dir) for path in input_paths]

    try:
        for input_path, output_path in zip(input_paths, output_paths):
            raw_text = input_path.read_text(encoding="utf-8")
            segments = extract_segments(raw_text, input_path.stem, input_path.name)
            if not segments:
                raise ValueError(f"{input_path.name} produced no valid segments")
            write_jsonl(segments, output_path)
            print(f"processed {input_path.name} -> {output_path}", file=sys.stderr)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
