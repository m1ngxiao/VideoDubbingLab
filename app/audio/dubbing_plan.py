from __future__ import annotations

import re

from app.config import AudioAlignConfig
from app.schemas import Segment
from app.subtitle.normalize import normalize_subtitle_text

_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def estimate_speech_duration(text: str, chars_per_second: float) -> float:
    text = normalize_subtitle_text(text)
    cjk_count = len(_CJK_RE.findall(text))
    ascii_words = len(re.findall(r"[A-Za-z0-9]+", text))
    punctuation = len(re.findall(r"[，。！？；：,.!?;:]", text))
    weighted_chars = cjk_count + ascii_words * 1.7 + punctuation * 0.4
    return max(0.3, weighted_chars / max(chars_per_second, 0.1))


def plan_dubbing_segments(segments: list[Segment], config: AudioAlignConfig) -> list[Segment]:
    if not config.enable_dubbing_plan or len(segments) <= 1:
        return segments
    planned: list[Segment] = []
    index = 0
    while index < len(segments):
        group = [segments[index].model_copy()]
        while _should_merge_group(group, segments, index, config):
            group.append(segments[index + len(group)].model_copy())
        planned.append(_merge_group(group, config))
        index += len(group)
    return _renumber(planned)


def _should_merge_group(group: list[Segment], segments: list[Segment], index: int, config: AudioAlignConfig) -> bool:
    next_index = index + len(group)
    if next_index >= len(segments) or len(group) >= config.max_merge_segments:
        return False
    current = _merge_group(group, config, renumber=False)
    next_segment = segments[next_index]
    gap = max(0.0, next_segment.start - current.end)
    if gap > config.planning_tolerance:
        return False
    available = max(0.1, current.duration + min(gap, config.planning_tolerance))
    estimated = estimate_speech_duration(current.target_text or current.source_text, config.speech_chars_per_second)
    too_fast = estimated / max(config.max_speedup, 0.1) > available
    too_short = current.duration < 1.0
    return too_fast or too_short


def _merge_group(group: list[Segment], config: AudioAlignConfig, renumber: bool = True) -> Segment:
    first = group[0]
    last = group[-1]
    target_text = normalize_subtitle_text(" ".join(item.target_text or item.source_text for item in group))
    source_text = normalize_subtitle_text(" ".join(item.source_text for item in group))
    merged = Segment(
        id=first.id,
        start=first.start,
        end=last.end,
        duration=max(0.0, last.end - first.start),
        source_text=source_text,
        target_text=target_text,
        speaker=first.speaker,
    )
    estimated = estimate_speech_duration(target_text, config.speech_chars_per_second)
    available = max(0.1, merged.duration)
    if estimated / max(config.max_speedup, 0.1) > available:
        merged.warnings.append(
            f"Estimated dubbing duration {estimated:.2f}s may exceed planned window {available:.2f}s"
        )
    if renumber and len(group) > 1:
        merged.warnings.append(f"Merged {len(group)} subtitle segments for dubbing timing")
    return merged


def _renumber(segments: list[Segment]) -> list[Segment]:
    for index, segment in enumerate(segments, start=1):
        segment.id = index
        segment.tts_audio_path = None
        segment.aligned_audio_path = None
    return segments
