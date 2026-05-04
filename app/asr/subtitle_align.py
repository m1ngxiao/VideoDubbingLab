from __future__ import annotations

from pathlib import Path

from app.schemas import Segment
from app.subtitle.writer import write_srt


def normalize_asr_segments(segments: list[Segment]) -> list[Segment]:
    normalized: list[Segment] = []
    for index, segment in enumerate(segments, start=1):
        start = max(0.0, segment.start)
        end = max(start, segment.end)
        normalized.append(
            segment.model_copy(
                update={
                    "id": index,
                    "start": start,
                    "end": end,
                    "duration": max(0.0, end - start),
                    "target_text": None,
                    "tts_audio_path": None,
                    "aligned_audio_path": None,
                }
            )
        )
    return normalized


def write_asr_srt(segments: list[Segment], path: str | Path) -> Path:
    return write_srt(normalize_asr_segments(segments), path)
