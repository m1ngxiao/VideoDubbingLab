from __future__ import annotations

from pathlib import Path

from app.config import MuxConfig
from app.utils.shell import run_command


def mux_video_audio(
    source_video: str | Path,
    zh_audio: str | Path,
    output_video: str | Path,
    config: MuxConfig,
) -> Path:
    source_video = Path(source_video)
    zh_audio = Path(zh_audio)
    output_video = Path(output_video)
    output_video.parent.mkdir(parents=True, exist_ok=True)
    video_codec = "copy" if config.keep_original_video_codec else "libx264"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_video),
        "-i",
        str(zh_audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        video_codec,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        str(output_video),
    ]
    run_command(command, timeout=None)
    return output_video
