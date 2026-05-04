from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.audio.duration import get_media_duration
from app.audio.postprocess import measure_lufs
from app.config import AppConfig
from app.schemas import VideoTask


def build_qc_report(task: VideoTask, config: AppConfig) -> dict[str, Any]:
    total_segments = len(task.segments)
    missing_tts = [segment.id for segment in task.segments if not segment.tts_audio_path]
    failed_tts = [segment.id for segment in task.segments if segment.tts_status == "failed"]
    overflow = [segment.id for segment in task.segments if segment.overflow]
    shifts = [abs(segment.shift_ms) / 1000 for segment in task.segments]
    max_shift = max(shifts, default=0.0)
    avg_shift = sum(shifts) / len(shifts) if shifts else 0.0
    total_duration_source = _duration_or_zero(task.source_video_path)
    total_duration_output = _duration_or_zero(task.output_video_path) or _duration_or_zero(task.zh_audio_path)
    duration_diff = abs(total_duration_output - total_duration_source) if total_duration_source and total_duration_output else 0.0
    loudness_lufs = None
    true_peak_db = -999.0
    if task.zh_audio_path and Path(task.zh_audio_path).exists():
        stats = measure_lufs(task.zh_audio_path)
        loudness_lufs = stats.integrated_lufs
        true_peak_db = stats.true_peak_db

    warnings = list(task.warnings)
    for segment in task.segments:
        for warning in segment.warnings:
            warnings.append(f"Segment {segment.id}: {warning}")

    publish_blockers: list[str] = []
    if missing_tts:
        publish_blockers.append("missing_tts_segments")
    if failed_tts:
        publish_blockers.append("failed_tts_segments")
    if max_shift > config.qc.max_shift_seconds:
        publish_blockers.append("max_shift_seconds")
    if duration_diff > config.qc.max_duration_diff_seconds:
        publish_blockers.append("duration_diff_seconds")
    if true_peak_db > config.qc.true_peak_db:
        publish_blockers.append("true_peak_db")
    overflow_ratio = len(overflow) / total_segments if total_segments else 0.0
    if overflow_ratio > config.qc.max_overflow_ratio:
        publish_blockers.append("overflow_ratio")

    return {
        "total_segments": total_segments,
        "missing_tts_segments": missing_tts,
        "failed_tts_segments": failed_tts,
        "overflow_segments": overflow,
        "max_shift_seconds": max_shift,
        "avg_shift_seconds": avg_shift,
        "total_duration_source": total_duration_source,
        "total_duration_output": total_duration_output,
        "duration_diff_seconds": duration_diff,
        "loudness_lufs": loudness_lufs,
        "true_peak_db": true_peak_db,
        "warnings": warnings,
        "publishable": not publish_blockers,
        "publish_blockers": publish_blockers,
    }


def write_qc_report(task: VideoTask, config: AppConfig, path: str | Path) -> Path:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = build_qc_report(task, config)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def _duration_or_zero(path: str | None) -> float:
    if not path:
        return 0.0
    media_path = Path(path)
    if not media_path.exists():
        return 0.0
    try:
        return get_media_duration(media_path)
    except Exception:
        return 0.0
