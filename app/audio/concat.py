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
) -> Path:
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    total_samples = max(1, int(round(total_duration * sample_rate)))
    timeline = np.zeros(total_samples, dtype=np.float32)

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
        start = max(0, int(round(segment.start * sample_rate)))
        end = min(total_samples, start + len(data))
        if start >= total_samples:
            segment.warnings.append("Segment starts after total audio duration")
            continue
        data = data[: end - start]
        if np.any(timeline[start:end] != 0):
            segment.warnings.append("Segment overlaps with existing audio; mixed in v0.1")
        timeline[start:end] = np.clip(timeline[start:end] + data, -1.0, 1.0)

    sf.write(str(output_wav), timeline, sample_rate)
    return output_wav
