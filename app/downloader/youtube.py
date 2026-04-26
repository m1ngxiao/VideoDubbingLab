from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.audio.convert import convert_audio_to_wav
from app.config import DownloadConfig
from app.downloader.utils import subtitle_candidates
from app.schemas import VideoTask
from app.utils.files import ensure_dir, find_first_existing, safe_filename
from app.utils.shell import run_command
from app.utils.text import short_hash

logger = logging.getLogger(__name__)


class YouTubeDownloader:
    def __init__(self, output_dir: Path, config: DownloadConfig, sample_rate: int = 24000):
        self.output_dir = ensure_dir(output_dir)
        self.config = config
        self.sample_rate = sample_rate

    def probe(self, url: str) -> dict[str, Any]:
        result = run_command(["yt-dlp", "--dump-single-json", "--skip-download", url], timeout=120)
        return json.loads(result.stdout)

    def build_task(self, url: str) -> VideoTask:
        try:
            info = self.probe(url)
        except Exception as exc:
            logger.warning("yt-dlp metadata probe failed, using URL hash as task id: %s", exc)
            info = {"id": short_hash(url), "title": "youtube_video"}
        video_id = str(info.get("id") or short_hash(url))
        title = str(info.get("title") or "youtube_video")
        task_id = f"{video_id}_{safe_filename(title)}"
        work_dir = ensure_dir(self.output_dir / task_id)
        info_path = work_dir / "source.info.json"
        if not info_path.exists():
            info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        return VideoTask(
            task_id=task_id,
            url=url,
            title=title,
            video_id=video_id,
            work_dir=str(work_dir),
            info_json_path=str(info_path),
        )

    def download(self, task: VideoTask, resume: bool = True) -> VideoTask:
        work_dir = ensure_dir(Path(task.work_dir))
        logger.info("[download] start: %s", task.url)

        source_mp4 = work_dir / "source.mp4"
        if not (resume and source_mp4.exists()):
            command = [
                "yt-dlp",
                "-f",
                self.config.format,
                "--merge-output-format",
                self.config.merge_output_format,
            ]
            if self.config.write_subs:
                command.append("--write-subs")
            if self.config.write_auto_subs:
                command.append("--write-auto-subs")
            if self.config.subtitle_languages:
                command.extend(["--sub-langs", ",".join(self.config.subtitle_languages)])
            if self.config.convert_subs_to:
                command.extend(["--convert-subs", self.config.convert_subs_to])
            if self.config.write_info_json:
                command.append("--write-info-json")
            if self.config.write_thumbnail:
                command.append("--write-thumbnail")
            command.extend(["-o", str(work_dir / "source.%(ext)s"), str(task.url)])
            run_command(command, timeout=None)

        task.source_video_path = str(source_mp4 if source_mp4.exists() else self._find_source_video(work_dir))
        task.info_json_path = str(work_dir / "source.info.json") if (work_dir / "source.info.json").exists() else task.info_json_path

        if self.config.keep_video_stream:
            task.source_video_only_path = self._download_stream(
                task.url or "",
                work_dir,
                stream_format="bestvideo",
                template="source.video.%(ext)s",
                resume=resume,
            )

        if self.config.keep_audio_stream:
            task.source_audio_path = self._download_stream(
                task.url or "",
                work_dir,
                stream_format="bestaudio",
                template="source.audio.%(ext)s",
                resume=resume,
            )

        if task.source_audio_path:
            source_wav = work_dir / "source.audio.wav"
            if not (resume and source_wav.exists()):
                convert_audio_to_wav(task.source_audio_path, source_wav, sample_rate=self.sample_rate)
            task.source_wav_path = str(source_wav)

        subtitle = self.select_subtitle(work_dir)
        if subtitle is None:
            raise FileNotFoundError("No subtitle found. Please provide subtitle file or enable ASR in future version.")
        task.source_subtitle_path = str(subtitle)

        download_manifest = {
            "source_video_path": task.source_video_path,
            "source_video_only_path": task.source_video_only_path,
            "source_audio_path": task.source_audio_path,
            "source_wav_path": task.source_wav_path,
            "source_subtitle_path": task.source_subtitle_path,
            "info_json_path": task.info_json_path,
        }
        (work_dir / "download_manifest.json").write_text(
            json.dumps(download_manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        task.status = "downloaded"
        logger.info("[download] done: %s", work_dir)
        return task

    def select_subtitle(self, work_dir: Path) -> Path | None:
        return find_first_existing(subtitle_candidates(work_dir))

    def _download_stream(self, url: str, work_dir: Path, stream_format: str, template: str, resume: bool) -> str | None:
        existing = sorted(work_dir.glob(template.replace("%(ext)s", "*")))
        if resume and existing:
            return str(existing[0])
        run_command(["yt-dlp", "-f", stream_format, "-o", str(work_dir / template), url], timeout=None)
        downloaded = sorted(work_dir.glob(template.replace("%(ext)s", "*")))
        return str(downloaded[0]) if downloaded else None

    def _find_source_video(self, work_dir: Path) -> Path:
        for candidate in [work_dir / "source.mp4", work_dir / "source.mkv", work_dir / "source.webm"]:
            if candidate.exists():
                return candidate
        matches = sorted(work_dir.glob("source.*"))
        for match in matches:
            if match.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}:
                return match
        raise FileNotFoundError(f"Downloaded source video not found in {work_dir}")
