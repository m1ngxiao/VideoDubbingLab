from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from app.utils.shell import run_command


@dataclass
class LoudnessStats:
    integrated_lufs: float | None
    true_peak_db: float


def trim_silence(input_wav: str | Path, output_wav: str | Path | None = None, threshold_db: float = -45.0) -> Path:
    input_path = Path(input_wav)
    output_path = Path(output_wav) if output_wav else input_path
    data, sample_rate = sf.read(str(input_path), dtype="float32", always_2d=False)
    mono = data.mean(axis=1) if data.ndim == 2 else data
    threshold = 10 ** (threshold_db / 20.0)
    active = np.flatnonzero(np.abs(mono) > threshold)
    if active.size:
        start = max(0, int(active[0]))
        end = min(len(mono), int(active[-1]) + 1)
        data = data[start:end]
    sf.write(str(output_path), data, sample_rate)
    return output_path


def apply_fade(input_wav: str | Path, output_wav: str | Path | None = None, fade_in_ms: int = 10, fade_out_ms: int = 10) -> Path:
    input_path = Path(input_wav)
    output_path = Path(output_wav) if output_wav else input_path
    data, sample_rate = sf.read(str(input_path), dtype="float32", always_2d=False)
    if len(data) == 0:
        sf.write(str(output_path), data, sample_rate)
        return output_path
    fade_in_samples = min(len(data), int(sample_rate * max(0, fade_in_ms) / 1000))
    fade_out_samples = min(len(data), int(sample_rate * max(0, fade_out_ms) / 1000))
    if fade_in_samples:
        shape = (fade_in_samples, 1) if data.ndim == 2 else (fade_in_samples,)
        data[:fade_in_samples] *= np.linspace(0.0, 1.0, fade_in_samples, dtype=np.float32).reshape(shape)
    if fade_out_samples:
        shape = (fade_out_samples, 1) if data.ndim == 2 else (fade_out_samples,)
        data[-fade_out_samples:] *= np.linspace(1.0, 0.0, fade_out_samples, dtype=np.float32).reshape(shape)
    sf.write(str(output_path), data, sample_rate)
    return output_path


def normalize_loudness(
    input_wav: str | Path,
    output_wav: str | Path | None = None,
    target_lufs: float = -16.0,
    true_peak_db: float = -1.0,
) -> Path:
    input_path = Path(input_wav)
    output_path = Path(output_wav) if output_wav else input_path
    data, sample_rate = sf.read(str(input_path), dtype="float32", always_2d=False)
    if len(data) == 0:
        sf.write(str(output_path), data, sample_rate)
        return output_path
    mono = data.mean(axis=1) if data.ndim == 2 else data
    rms = float(np.sqrt(np.mean(np.square(mono)))) if np.any(mono) else 0.0
    current_lufs = 20 * math.log10(max(rms, 1e-9))
    gain = 10 ** ((target_lufs - current_lufs) / 20.0)
    peak_limit = 10 ** (true_peak_db / 20.0)
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak * gain > peak_limit:
        gain = peak_limit / max(peak, 1e-9)
    data = np.clip(data * gain, -1.0, 1.0)
    sf.write(str(output_path), data, sample_rate)
    return output_path


def time_stretch(input_wav: str | Path, output_wav: str | Path, speed_ratio: float) -> Path:
    input_path = Path(input_wav)
    output_path = Path(output_wav)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if speed_ratio <= 0:
        raise ValueError("speed_ratio must be positive")
    if shutil.which("ffmpeg"):
        run_command(["ffmpeg", "-y", "-i", str(input_path), "-filter:a", f"atempo={speed_ratio:.6f}", str(output_path)])
        return output_path
    data, sample_rate = sf.read(str(input_path), dtype="float32", always_2d=False)
    target_samples = max(1, int(round(len(data) / speed_ratio)))
    source_positions = np.linspace(0, len(data) - 1, num=len(data), dtype=np.float64)
    target_positions = np.linspace(0, len(data) - 1, num=target_samples, dtype=np.float64)
    if data.ndim == 2:
        stretched = np.vstack(
            [np.interp(target_positions, source_positions, data[:, channel]) for channel in range(data.shape[1])]
        ).T
    else:
        stretched = np.interp(target_positions, source_positions, data)
    sf.write(str(output_path), stretched.astype(np.float32), sample_rate)
    return output_path


def measure_lufs(input_wav: str | Path) -> LoudnessStats:
    input_path = Path(input_wav)
    if shutil.which("ffmpeg"):
        completed = run_command(
            [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-i",
                str(input_path),
                "-af",
                "loudnorm=I=-16:TP=-1:LRA=11:print_format=json",
                "-f",
                "null",
                "-",
            ],
            check=False,
        )
        payload = _extract_json_object(completed.stderr)
        if payload:
            return LoudnessStats(
                integrated_lufs=_optional_float(payload.get("input_i")),
                true_peak_db=_optional_float(payload.get("input_tp")) or _measure_true_peak_db(input_path),
            )
    return LoudnessStats(integrated_lufs=None, true_peak_db=_measure_true_peak_db(input_path))


def postprocess_tts_file(
    wav_path: str | Path,
    trim: bool = True,
    normalize: bool = True,
    target_lufs: float = -16.0,
    true_peak_db: float = -1.0,
    fade_in_ms: int = 10,
    fade_out_ms: int = 10,
) -> Path:
    path = Path(wav_path)
    if trim:
        trim_silence(path)
    apply_fade(path, fade_in_ms=fade_in_ms, fade_out_ms=fade_out_ms)
    if normalize:
        normalize_loudness(path, target_lufs=target_lufs, true_peak_db=true_peak_db)
    return path


def _measure_true_peak_db(path: Path) -> float:
    data, _sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    return 20 * math.log10(max(peak, 1e-9))


def _extract_json_object(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _optional_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
