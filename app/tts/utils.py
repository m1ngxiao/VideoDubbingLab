from __future__ import annotations

from pathlib import Path

from app.audio.convert import convert_audio_to_wav


def ensure_wav(input_path: Path, output_path: Path, sample_rate: int) -> Path:
    if input_path.suffix.lower() == ".wav" and input_path.resolve() == output_path.resolve():
        return output_path
    return convert_audio_to_wav(input_path, output_path, sample_rate=sample_rate)
