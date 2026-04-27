from __future__ import annotations

import platform
from pathlib import Path

from app.config import MuxConfig
from app.utils.shell import run_command


def _subtitle_filter_path(path: Path) -> str:
    value = path.resolve().as_posix().replace("'", r"\'")
    return value.replace(":", r"\:")


def _subtitle_style() -> str:
    font_name = "Arial"
    if platform.system() == "Linux":
        font_name = "NotoSansCJK-Regular"
    elif platform.system() == "Darwin":
        font_name = "Arial Unicode MS"
    return (
        f"FontName={font_name},FontSize=17,PrimaryColour=&H00FFFF,"
        "OutlineColour=&H000000,OutlineWidth=1,BackColour=&H33000000,"
        "Alignment=2,MarginV=27,BorderStyle=4"
    )


def mux_video_audio(
    source_video: str | Path,
    zh_audio: str | Path,
    output_video: str | Path,
    config: MuxConfig,
    zh_subtitle: str | Path | None = None,
) -> Path:
    source_video = Path(source_video)
    zh_audio = Path(zh_audio)
    output_video = Path(output_video)
    subtitle_path = Path(zh_subtitle) if zh_subtitle else None
    output_video.parent.mkdir(parents=True, exist_ok=True)

    if (config.burn_subtitle or config.attach_subtitle) and (subtitle_path is None or not subtitle_path.exists()):
        raise FileNotFoundError("Chinese subtitle file is required when burn_subtitle or attach_subtitle is enabled")

    burn_subtitle = config.burn_subtitle and subtitle_path is not None
    attach_subtitle = config.attach_subtitle and subtitle_path is not None
    video_codec = "copy" if config.keep_original_video_codec and not burn_subtitle else "libx264"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_video),
        "-i",
        str(zh_audio),
    ]
    subtitle_input_index = 2
    if attach_subtitle:
        command.extend(["-i", str(subtitle_path)])

    if burn_subtitle and subtitle_path is not None:
        command.extend(
            [
                "-vf",
                f"subtitles='{_subtitle_filter_path(subtitle_path)}':force_style='{_subtitle_style()}'",
            ]
        )

    if config.mix_original_audio:
        command.extend(
            [
                "-filter_complex",
                (
                    f"[0:a:0]volume={config.original_audio_volume:.3f}[orig];"
                    f"[1:a:0]volume={config.dubbed_audio_volume:.3f}[dub];"
                    "[orig][dub]amix=inputs=2:duration=longest:dropout_transition=0[a]"
                ),
            ]
        )

    command.extend(
        [
            "-map",
            "0:v:0",
            "-map",
        ]
    )
    if config.mix_original_audio:
        command.append("[a]")
    else:
        command.append("1:a:0")
    if config.keep_original_audio and not config.mix_original_audio:
        command.extend(["-map", "0:a:0?"])
    if attach_subtitle:
        command.extend(["-map", f"{subtitle_input_index}:0"])

    command.extend(
        [
            "-c:v",
            video_codec,
        ]
    )
    if video_codec != "copy":
        command.extend(["-preset", "veryfast", "-crf", "18"])
    command.extend(
        [
            "-c:a",
            "aac",
            "-b:a",
            "192k",
        ]
    )
    if attach_subtitle:
        subtitle_codec = "mov_text" if output_video.suffix.lower() == ".mp4" else "srt"
        command.extend(["-c:s", subtitle_codec])
    command.extend(
        [
            "-shortest",
            str(output_video),
        ]
    )
    run_command(command, timeout=None)
    return output_video
