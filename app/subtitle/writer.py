from __future__ import annotations

from pathlib import Path

from app.schemas import Segment
from app.utils.timecode import format_srt_time


def write_srt(segments: list[Segment], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = segment.target_text or segment.source_text
        parts.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_time(segment.start)} --> {format_srt_time(segment.end)}",
                    text.strip(),
                ]
            )
        )
    output_path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    return output_path
