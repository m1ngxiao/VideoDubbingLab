from __future__ import annotations

from pathlib import Path

from app.utils.shell import run_command


def convert_audio_to_wav(input_path: str | Path, output_path: str | Path, sample_rate: int = 24000) -> Path:
    input_file = Path(input_path)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_file),
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            str(output_file),
        ]
    )
    return output_file


def extract_wav_from_video(video_path: str | Path, output_path: str | Path, sample_rate: int = 24000) -> Path:
    return convert_audio_to_wav(video_path, output_path, sample_rate=sample_rate)
