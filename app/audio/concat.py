from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from app.schemas import Segment


def _read_mono(path: Path) -> tuple[np.ndarray, int]:
    data, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim == 2:
        data = data.mean(axis=1)
    return data.astype(np.float32, copy=False), sample_rate


def build_timeline_audio(
    segments: list[Segment],
    output_wav: Path,
    total_duration: float,
    sample_rate: int,
    prevent_overlaps: bool = True,
    min_gap_ms: int = 0,
    max_shift_ms: int = 250,
) -> Path:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    original_total_samples = max(1, int(round(total_duration * sample_rate)))
    min_gap_samples = max(0, int(round(min_gap_ms * sample_rate / 1000)))
    max_shift_samples = max(0, int(round(max_shift_ms * sample_rate / 1000)))
    cursor = 0
    placements: list[tuple[Segment, np.ndarray, int, int]] = []

    for segment in segments:
        if not segment.aligned_audio_path:
            continue
        path = Path(segment.aligned_audio_path)
        if not path.exists():
            segment.warnings.append(f"Aligned audio missing: {path}")
            continue
        data, sr = _read_mono(path)
        if sr != sample_rate and len(data) > 1:
            target_len = int(round(len(data) * sample_rate / sr))
            source_positions = np.linspace(0, len(data) - 1, num=len(data), dtype=np.float64)
            target_positions = np.linspace(0, len(data) - 1, num=target_len, dtype=np.float64)
            data = np.interp(target_positions, source_positions, data).astype(np.float32)
        if segment.original_start is None:
            segment.original_start = segment.start
        if segment.original_end is None:
            segment.original_end = segment.end
        requested_start = max(0, int(round((segment.original_start if segment.original_start is not None else segment.start) * sample_rate)))
        start = requested_start
        if prevent_overlaps:
            desired_start = max(requested_start, cursor + (min_gap_samples if placements else 0))
            shift_needed = desired_start - requested_start
            if shift_needed <= max_shift_samples:
                start = desired_start
            elif shift_needed > 0:
                start = requested_start + max_shift_samples
                segment.warnings.append(
                    f"Overlap not fully resolved within max shift {max_shift_ms}ms; dubbed audio will mix or clip"
                )
            shift_seconds = (start - requested_start) / sample_rate
            if shift_seconds > 0.01:
                segment.warnings.append(f"Shifted {shift_seconds:.2f}s later to avoid dubbed audio overlap")
        end = start + len(data)
        if end > original_total_samples:
            overflow_seconds = (end - original_total_samples) / sample_rate
            segment.warnings.append(f"Dubbed audio extends {overflow_seconds:.2f}s beyond source video duration")
        segment.placed_start = start / sample_rate
        segment.placed_end = end / sample_rate
        segment.shift_ms = (start - requested_start) * 1000 / sample_rate
        placements.append((segment, data, start, end))
        cursor = max(cursor, end)

    timeline = np.zeros(original_total_samples, dtype=np.float32)
    for segment, data, start, end in placements:
        if start >= original_total_samples:
            segment.warnings.append("Segment starts after total audio duration")
            continue
        end = min(original_total_samples, end)
        data = data[: end - start]
        if np.any(timeline[start:end] != 0):
            segment.warnings.append("Segment overlaps with existing audio; mixed")
            timeline[start:end] = np.clip(timeline[start:end] + data, -1.0, 1.0)
        else:
            timeline[start:end] = data

    sf.write(str(output_wav), timeline, sample_rate)
    return output_wav
