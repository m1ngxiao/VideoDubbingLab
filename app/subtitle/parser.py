from __future__ import annotations

import re
from pathlib import Path

from app.schemas import Segment
from app.subtitle.normalize import normalize_subtitle_text
from app.utils.timecode import parse_srt_time

_TIMING_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*"
    r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)
_VTT_TIMING_RE = re.compile(
    r"(?P<start>(?:\d{2}:)?\d{2}:\d{2}\.\d{3})\s*-->\s*"
    r"(?P<end>(?:\d{2}:)?\d{2}:\d{2}\.\d{3})"
)


def parse_subtitle(path: str | Path) -> list[Segment]:
    subtitle_path = Path(path)
    suffix = subtitle_path.suffix.lower()
    if suffix == ".srt":
        return parse_srt(subtitle_path)
    if suffix == ".vtt":
        return parse_vtt(subtitle_path)
    raise ValueError(f"Unsupported subtitle format: {subtitle_path.suffix}")


def parse_srt(path: str | Path) -> list[Segment]:
    subtitle_path = Path(path)
    text = subtitle_path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip())
    segments: list[Segment] = []
    fallback_id = 1
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        segment_id = fallback_id
        timing_index = 0
        if lines[0].isdigit():
            segment_id = int(lines[0])
            timing_index = 1

        if timing_index >= len(lines):
            continue
        timing = _TIMING_RE.search(lines[timing_index])
        if timing is None:
            continue

        start = parse_srt_time(timing.group("start"))
        end = parse_srt_time(timing.group("end"))
        content = normalize_subtitle_text("\n".join(lines[timing_index + 1 :]))
        if not content:
            continue
        segments.append(
            Segment(
                id=segment_id,
                start=start,
                end=end,
                duration=max(0.0, end - start),
                source_text=content,
            )
        )
        fallback_id += 1
    return segments


def parse_vtt(path: str | Path) -> list[Segment]:
    subtitle_path = Path(path)
    text = subtitle_path.read_text(encoding="utf-8-sig")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    segments: list[Segment] = []
    fallback_id = 1
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if lines[0].startswith("WEBVTT") or lines[0].startswith("NOTE") or lines[0].startswith("STYLE"):
            continue

        timing_index = 0
        if "-->" not in lines[0] and len(lines) > 1:
            timing_index = 1
        if timing_index >= len(lines):
            continue

        timing = _VTT_TIMING_RE.search(lines[timing_index])
        if timing is None:
            continue
        start = _parse_vtt_time(timing.group("start"))
        end = _parse_vtt_time(timing.group("end"))
        content = normalize_subtitle_text("\n".join(lines[timing_index + 1 :]))
        if not content:
            continue
        segments.append(
            Segment(
                id=fallback_id,
                start=start,
                end=end,
                duration=max(0.0, end - start),
                source_text=content,
            )
        )
        fallback_id += 1
    return segments


def _parse_vtt_time(value: str) -> float:
    parts = value.split(":")
    if len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds_text = parts[1]
    elif len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_text = parts[2]
    else:
        raise ValueError(f"Invalid VTT timecode: {value}")
    seconds, milliseconds = seconds_text.split(".")
    return hours * 3600 + minutes * 60 + int(seconds) + int(milliseconds) / 1000
