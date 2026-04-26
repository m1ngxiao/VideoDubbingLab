from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from app.audio.duration import get_audio_duration
from app.utils.shell import run_command

logger = logging.getLogger(__name__)


@dataclass
class AudioAlignResult:
    input_path: Path
    output_path: Path
    input_duration: float
    target_duration: float
    output_duration: float
    speed_ratio: float = 1.0
    overflow: bool = False
    warnings: list[str] = field(default_factory=list)


def _mono_float32(data: np.ndarray) -> np.ndarray:
    if data.ndim == 2:
        data = data.mean(axis=1)
    return data.astype(np.float32, copy=False)


def _fit_to_duration(data: np.ndarray, sample_rate: int, target_duration: float) -> np.ndarray:
    target_samples = max(1, int(round(target_duration * sample_rate)))
    if len(data) == target_samples:
        return data
    if len(data) > target_samples:
        return data[:target_samples]
    padding = np.zeros(target_samples - len(data), dtype=np.float32)
    return np.concatenate([data, padding])


def _resample_to_duration(data: np.ndarray, sample_rate: int, target_duration: float) -> np.ndarray:
    target_samples = max(1, int(round(target_duration * sample_rate)))
    if len(data) <= 1 or len(data) == target_samples:
        return _fit_to_duration(data, sample_rate, target_duration)
    source_positions = np.linspace(0, len(data) - 1, num=len(data), dtype=np.float64)
    target_positions = np.linspace(0, len(data) - 1, num=target_samples, dtype=np.float64)
    return np.interp(target_positions, source_positions, data).astype(np.float32)


def _resample_sample_rate(data: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate or len(data) <= 1:
        return data
    target_samples = max(1, int(round(len(data) * target_rate / source_rate)))
    source_positions = np.linspace(0, len(data) - 1, num=len(data), dtype=np.float64)
    target_positions = np.linspace(0, len(data) - 1, num=target_samples, dtype=np.float64)
    return np.interp(target_positions, source_positions, data).astype(np.float32)


def _try_ffmpeg_atempo(input_wav: Path, output_wav: Path, ratio: float) -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    try:
        run_command(["ffmpeg", "-y", "-i", str(input_wav), "-filter:a", f"atempo={ratio:.6f}", str(output_wav)])
        return True
    except Exception as exc:  # noqa: BLE001 - fallback to numpy stretch
        logger.warning("ffmpeg atempo failed, falling back to numpy resample: %s", exc)
        return False


def align_segment_audio(
    input_wav: Path,
    output_wav: Path,
    target_duration: float,
    sample_rate: int,
    max_speedup: float,
    silence_padding_ms: int,
) -> AudioAlignResult:
    del silence_padding_ms
    input_wav = Path(input_wav)
    output_wav = Path(output_wav)
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    input_duration = get_audio_duration(input_wav)
    if target_duration <= 0:
        shutil.copy2(input_wav, output_wav)
        output_duration = get_audio_duration(output_wav)
        return AudioAlignResult(input_wav, output_wav, input_duration, target_duration, output_duration)

    ratio = input_duration / target_duration if target_duration else 1.0
    warnings: list[str] = []

    data, sr = sf.read(str(input_wav), dtype="float32", always_2d=False)
    data = _mono_float32(data)
    if sr != sample_rate:
        data = _resample_sample_rate(data, sr, sample_rate)
        sr = sample_rate

    if input_duration <= target_duration:
        aligned = _fit_to_duration(data, sr, target_duration)
        sf.write(str(output_wav), aligned, sr)
        output_duration = get_audio_duration(output_wav)
        return AudioAlignResult(input_wav, output_wav, input_duration, target_duration, output_duration)

    if ratio <= max_speedup:
        if not _try_ffmpeg_atempo(input_wav, output_wav, ratio):
            aligned = _resample_to_duration(data, sr, target_duration)
            sf.write(str(output_wav), aligned, sr)
        else:
            aligned_data, aligned_sr = sf.read(str(output_wav), dtype="float32", always_2d=False)
            aligned_data = _fit_to_duration(_mono_float32(aligned_data), aligned_sr, target_duration)
            sf.write(str(output_wav), aligned_data, aligned_sr)
        output_duration = get_audio_duration(output_wav)
        return AudioAlignResult(
            input_wav,
            output_wav,
            input_duration,
            target_duration,
            output_duration,
            speed_ratio=ratio,
        )

    warning = (
        f"TTS duration {input_duration:.2f}s exceeds target {target_duration:.2f}s "
        f"by ratio {ratio:.2f}."
    )
    warnings.append(warning)
    shutil.copy2(input_wav, output_wav)
    output_duration = get_audio_duration(output_wav)
    return AudioAlignResult(
        input_wav,
        output_wav,
        input_duration,
        target_duration,
        output_duration,
        speed_ratio=1.0,
        overflow=True,
        warnings=warnings,
    )
