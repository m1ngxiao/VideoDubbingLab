from app.config import MuxConfig
from app.mux import ffmpeg_muxer


def test_mux_burns_chinese_subtitles_and_reencodes_video(tmp_path, monkeypatch):
    source_video = tmp_path / "source.mp4"
    zh_audio = tmp_path / "zh.wav"
    zh_subtitle = tmp_path / "zh.srt"
    output = tmp_path / "final.mp4"
    for path in [source_video, zh_audio, zh_subtitle]:
        path.write_text("placeholder", encoding="utf-8")
    commands = []

    def fake_run_command(command, timeout=None):
        commands.append(command)

    monkeypatch.setattr(ffmpeg_muxer, "run_command", fake_run_command)

    ffmpeg_muxer.mux_video_audio(
        source_video,
        zh_audio,
        output,
        MuxConfig(burn_subtitle=True, keep_original_video_codec=True),
        zh_subtitle,
    )

    command = commands[0]
    assert "-vf" in command
    assert "subtitles=" in command[command.index("-vf") + 1]
    assert "-filter_complex" in command
    assert "amix=inputs=2" in command[command.index("-filter_complex") + 1]
    assert command[command.index("-c:v") + 1] == "libx264"
