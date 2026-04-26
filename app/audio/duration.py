from __future__ import annotations

from pathlib import Path

import soundfile as sf

from app.utils.shell import run_command


def get_audio_duration(path: str | Path) -> float:
    audio_path = Path(path)
    try:
        return float(sf.info(str(audio_path)).duration)
    except RuntimeError:
        return get_media_duration(audio_path)


def get_media_duration(path: str | Path) -> float:
    media_path = Path(path)
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ]
    )
    return float(result.stdout.strip())
