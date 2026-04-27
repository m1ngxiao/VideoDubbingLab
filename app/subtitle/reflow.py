from __future__ import annotations

import re

from app.config import SubtitleConfig
from app.schemas import Segment
from app.subtitle.normalize import normalize_subtitle_text

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;:])\s+")
_SOFT_SPLIT_RE = re.compile(r"(?<=,)\s+|\s+(?=(?:and|but|because|which|that|when|while|so)\b)", re.IGNORECASE)


def reflow_segments(segments: list[Segment], config: SubtitleConfig) -> list[Segment]:
    if not config.enable_reflow or not segments:
        return segments
    pieces = _split_segments(segments, config.max_segment_chars)
    merged = _merge_pieces(pieces, config)
    return _renumber(merged)


def _split_segments(segments: list[Segment], max_chars: int) -> list[Segment]:
    pieces: list[Segment] = []
    for segment in segments:
        text = normalize_subtitle_text(segment.source_text)
        split_texts = _split_text(text, max_chars)
        if len(split_texts) <= 1:
            pieces.append(segment.model_copy(update={"source_text": text, "target_text": None}))
            continue
        total_weight = sum(max(1, len(item)) for item in split_texts)
        cursor = segment.start
        for index, item in enumerate(split_texts):
            weight = max(1, len(item)) / total_weight
            duration = segment.duration * weight
            end = segment.end if index == len(split_texts) - 1 else cursor + duration
            pieces.append(
                Segment(
                    id=segment.id,
                    start=cursor,
                    end=end,
                    duration=max(0.0, end - cursor),
                    source_text=item,
                    speaker=segment.speaker,
                )
            )
            cursor = end
    return pieces


def _split_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = _split_by_regex(text, _SENTENCE_SPLIT_RE, max_chars)
    if any(len(item) > max_chars for item in chunks):
        chunks = [piece for chunk in chunks for piece in _split_by_regex(chunk, _SOFT_SPLIT_RE, max_chars)]
    if any(len(item) > max_chars for item in chunks):
        chunks = [piece for chunk in chunks for piece in _split_by_length(chunk, max_chars)]
    return [item for item in chunks if item]


def _split_by_regex(text: str, regex: re.Pattern[str], max_chars: int) -> list[str]:
    raw_parts = [part.strip() for part in regex.split(text) if part.strip()]
    parts: list[str] = []
    current = ""
    for part in raw_parts:
        candidate = f"{current} {part}".strip() if current else part
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = part
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts or [text]


def _split_by_length(text: str, max_chars: int) -> list[str]:
    words = text.split()
    parts: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = word
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts or [text]


def _merge_pieces(pieces: list[Segment], config: SubtitleConfig) -> list[Segment]:
    merged: list[Segment] = []
    current: Segment | None = None
    for piece in pieces:
        if current is None:
            current = piece.model_copy()
            continue
        gap = max(0.0, piece.start - current.end)
        candidate_text = f"{current.source_text} {piece.source_text}".strip()
        candidate_duration = piece.end - current.start
        should_merge = (
            gap <= config.max_merge_gap
            and len(candidate_text) <= config.max_segment_chars
            and candidate_duration <= config.max_segment_duration
            and (
                current.duration < config.min_segment_duration
                or not _ends_sentence(current.source_text)
                or _starts_continuation(piece.source_text)
            )
        )
        if should_merge:
            current.source_text = normalize_subtitle_text(candidate_text)
            current.end = piece.end
            current.duration = max(0.0, current.end - current.start)
        else:
            merged.append(current)
            current = piece.model_copy()
    if current is not None:
        merged.append(current)
    return merged


def _ends_sentence(text: str) -> bool:
    return text.rstrip().endswith((".", "!", "?"))


def _starts_continuation(text: str) -> bool:
    stripped = text.lstrip()
    return bool(stripped) and (stripped[0].islower() or stripped.lower().startswith(("and ", "but ", "so ")))


def _renumber(segments: list[Segment]) -> list[Segment]:
    for index, segment in enumerate(segments, start=1):
        segment.id = index
        segment.target_text = None
        segment.tts_audio_path = None
        segment.aligned_audio_path = None
    return segments
