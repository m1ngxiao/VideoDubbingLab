import json

from app.config import DownloadConfig
from app.downloader import youtube
from app.downloader.youtube import YouTubeDownloader
from app.schemas import VideoTask


def test_downloader_uses_single_ytdlp_download_and_keeps_streams(tmp_path, monkeypatch):
    commands = []

    def fake_run_command(command, timeout=None):
        commands.append(command)
        (tmp_path / "source.mp4").write_text("video", encoding="utf-8")
        (tmp_path / "source.en.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        (tmp_path / "source.info.json").write_text(
            json.dumps({"subtitles": {"en": [{"ext": "srt"}]}, "automatic_captions": {}}),
            encoding="utf-8",
        )

    def fake_convert(input_path, output_path, sample_rate=24000):
        output_path.write_text("wav", encoding="utf-8")
        return output_path

    monkeypatch.setattr(youtube, "run_command", fake_run_command)
    monkeypatch.setattr(youtube, "convert_audio_to_wav", fake_convert)

    downloader = YouTubeDownloader(tmp_path, DownloadConfig(), sample_rate=24000)
    task = VideoTask(task_id="demo", url="https://youtu.be/demo", work_dir=str(tmp_path))
    result = downloader.download(task, resume=False)

    ytdlp_commands = [command for command in commands if command[0] == "yt-dlp"]
    assert len(ytdlp_commands) == 1
    assert "--keep-video" in ytdlp_commands[0]
    assert "bestvideo" not in ytdlp_commands[0]
    assert "bestaudio" not in ytdlp_commands[0]
    assert result.source_subtitle_type == "manual"
