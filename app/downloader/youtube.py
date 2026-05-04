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
            command = self.build_download_command(work_dir, str(task.url))
            run_command(command, timeout=None)

        task.source_video_path = str(source_mp4 if source_mp4.exists() else self._find_source_video(work_dir))
        task.info_json_path = str(work_dir / "source.info.json") if (work_dir / "source.info.json").exists() else task.info_json_path

        task.source_video_only_path = self._find_video_stream(work_dir) if self.config.keep_video_stream else None
        task.source_audio_path = self._find_audio_stream(work_dir) if self.config.keep_audio_stream else task.source_video_path
        if not task.source_audio_path:
            task.source_audio_path = task.source_video_path

        if task.source_audio_path:
            source_wav = work_dir / "source.audio.wav"
            if not (resume and source_wav.exists()):
                convert_audio_to_wav(task.source_audio_path, source_wav, sample_rate=self.sample_rate)
            task.source_wav_path = str(source_wav)

        subtitle = self.select_subtitle(work_dir, task.info_json_path)
        if subtitle is None:
            task.warnings.append("No YouTube subtitle found; ASR fallback may run if enabled.")
        else:
            task.source_subtitle_path = str(subtitle["path"])
            task.source_subtitle_language = subtitle["language"]
            task.source_subtitle_type = subtitle["type"]

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

    def build_download_command(self, work_dir: Path, url: str) -> list[str]:
        command = [
            "yt-dlp",
            "-f",
            self.config.format,
            "--merge-output-format",
            self.config.merge_output_format,
        ]
        if self.config.avoid_duplicate_stream_downloads and (self.config.keep_video_stream or self.config.keep_audio_stream):
            command.append("--keep-video")
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
        command.extend(["-o", str(work_dir / "source.%(ext)s"), url])
        return command

    def select_subtitle(self, work_dir: Path, info_json_path: str | None = None) -> dict[str, str | Path] | None:
        info = self._load_info(info_json_path)
        languages = self.config.subtitle_languages or ["en"]
        if self.config.write_subs:
            subtitle = self._select_subtitle_by_info(work_dir, info.get("subtitles", {}), languages, "manual")
            if subtitle:
                return subtitle
        if self.config.write_auto_subs:
            subtitle = self._select_subtitle_by_info(
                work_dir,
                info.get("automatic_captions", {}),
                languages,
                "auto",
            )
            if subtitle:
                return subtitle
        fallback = find_first_existing(subtitle_candidates(work_dir))
        if fallback:
            return {"path": fallback, "language": _language_from_subtitle_name(fallback), "type": "unknown"}
        return None

    def _find_source_video(self, work_dir: Path) -> Path:
        for candidate in [work_dir / "source.mp4", work_dir / "source.mkv", work_dir / "source.webm"]:
            if candidate.exists():
                return candidate
        matches = sorted(work_dir.glob("source.*"))
        for match in matches:
            if match.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}:
                return match
        raise FileNotFoundError(f"Downloaded source video not found in {work_dir}")

    def _load_info(self, info_json_path: str | None) -> dict[str, Any]:
        if not info_json_path:
            return {}
        path = Path(info_json_path)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - subtitle selection can fall back to file patterns
            logger.warning("Could not read info json for subtitle selection: %s", exc)
            return {}

    def _select_subtitle_by_info(
        self,
        work_dir: Path,
        subtitles: dict[str, Any],
        languages: list[str],
        subtitle_type: str,
    ) -> dict[str, str | Path] | None:
        for requested in languages:
            matching_languages = _matching_subtitle_languages(subtitles, requested)
            for language in matching_languages:
                path = _find_subtitle_file(work_dir, language)
                if path:
                    return {"path": path, "language": language, "type": subtitle_type}
        return None

    def _find_video_stream(self, work_dir: Path) -> str | None:
        explicit = sorted(work_dir.glob("source.video.*"))
        if explicit:
            return str(explicit[0])
        for match in sorted(work_dir.glob("source.f*.*")):
            if match.suffix.lower() in {".mp4", ".mkv", ".webm"}:
                return str(match)
        return None

    def _find_audio_stream(self, work_dir: Path) -> str | None:
        explicit = sorted(work_dir.glob("source.audio.*"))
        if explicit:
            return str(explicit[0])
        for match in sorted(work_dir.glob("source.f*.*")):
            if match.suffix.lower() in {".m4a", ".mp3", ".opus", ".ogg", ".wav"}:
                return str(match)
        return None


def _matching_subtitle_languages(subtitles: dict[str, Any], requested: str) -> list[str]:
    if not isinstance(subtitles, dict):
        return []
    exact = [language for language in subtitles if language == requested]
    prefixed = [language for language in subtitles if language.startswith(f"{requested}-")]
    dotted = [language for language in subtitles if language.startswith(f"{requested}.")]
    return exact + sorted(prefixed) + sorted(dotted)


def _find_subtitle_file(work_dir: Path, language: str) -> Path | None:
    for suffix in ("srt", "vtt"):
        direct = work_dir / f"source.{language}.{suffix}"
        if direct.exists():
            return direct
    escaped = language.replace("-", "*")
    matches = sorted(work_dir.glob(f"source.{escaped}*.srt")) + sorted(work_dir.glob(f"source.{escaped}*.vtt"))
    return matches[0] if matches else None


def _language_from_subtitle_name(path: Path) -> str:
    parts = path.name.split(".")
    if len(parts) >= 3:
        return parts[1]
    return "unknown"
