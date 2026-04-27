from __future__ import annotations

import logging
from pathlib import Path

from app.config import AppConfig
from app.downloader.youtube import YouTubeDownloader
from app.logging_config import setup_logging
from app.pipeline.manifest import ManifestManager
from app.pipeline.stages import (
    STAGES,
    align_audio_stage,
    mux_stage,
    plan_dubbing_stage,
    reflow_subtitle_stage,
    translate_stage,
    tts_stage,
    write_subtitle_stage,
)
from app.schemas import VideoTask
from app.subtitle.parser import parse_srt
from app.subtitle.writer import write_srt

logger = logging.getLogger(__name__)


async def run_youtube_translation_pipeline(
    url: str,
    output_dir: Path,
    config: AppConfig,
    resume: bool = True,
):
    downloader = YouTubeDownloader(output_dir=output_dir, config=config.download, sample_rate=config.audio_align.sample_rate)
    task = downloader.build_task(url)
    setup_logging(Path(task.work_dir), config.runtime.log_level)
    manager = ManifestManager.load_or_create(Path(task.work_dir), task, resume=resume)
    task = manager.manifest.task

    try:
        if not (resume and manager.stage_done("download")):
            task = downloader.download(task, resume=resume)
            manager.update_task(task)
            manager.mark_done("download")

        if not (resume and manager.stage_done("parse_subtitle")):
            logger.info("[parse_subtitle] start")
            if not task.source_subtitle_path:
                raise FileNotFoundError("No subtitle found. Please provide subtitle file or enable ASR in future version.")
            task.segments = parse_srt(task.source_subtitle_path)
            manager.update_task(task)
            manager.mark_done("parse_subtitle")
            logger.info("[parse_subtitle] done: %s segments", len(task.segments))

        if not (resume and manager.stage_done("reflow_subtitle")):
            task = reflow_subtitle_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("reflow_subtitle")

        if not (resume and manager.stage_done("translate")):
            task = await translate_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("translate")

        if not (resume and manager.stage_done("plan_dubbing")):
            task = plan_dubbing_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("plan_dubbing")

        preview_path = Path(task.work_dir) / "zh_preview.srt"
        write_srt(task.segments, preview_path)
        task.zh_subtitle_path = str(preview_path)
        task.status = "translated"
        manager.update_task(task)
        return manager.manifest
    except Exception as exc:
        manager.fail(_current_failed_stage(manager), exc)
        raise


async def run_dubbing_from_workdir(
    work_dir: Path,
    config: AppConfig,
    resume: bool = True,
    force: bool = False,
):
    work_dir = work_dir.resolve()
    manager = ManifestManager.load_existing(work_dir)
    setup_logging(work_dir, config.runtime.log_level)
    task = _rebase_task_paths(manager.manifest.task, work_dir)
    manager.update_task(task)

    try:
        if not manager.stage_done("translate"):
            raise RuntimeError("Work dir is not translated yet. Run translate-youtube first.")

        if not (resume and manager.stage_done("plan_dubbing")):
            task = plan_dubbing_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("plan_dubbing")

        if not (resume and manager.stage_done("tts")):
            task = await tts_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("tts")

        if not (resume and manager.stage_done("align_audio")):
            task = align_audio_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("align_audio")

        # Always regenerate subtitles after alignment because timing may move to avoid overlap.
        if manager.stage_done("write_subtitle"):
            manager.manifest.completed_stages.remove("write_subtitle")
            manager.save()
        task = write_subtitle_stage(task)
        manager.update_task(task)
        manager.mark_done("write_subtitle")

        if not (resume and manager.stage_done("mux")):
            task = mux_stage(task, config, force=force)
            manager.update_task(task)
            manager.mark_done("mux")
        return manager.manifest
    except Exception as exc:
        manager.fail(_current_failed_stage(manager), exc)
        raise


def _rebase_task_paths(task: VideoTask, work_dir: Path) -> VideoTask:
    task.work_dir = str(work_dir)
    task.source_video_path = _rebase_path(task.source_video_path, work_dir, ["source.mp4", "source.mkv", "source.webm"])
    task.source_video_only_path = _rebase_path(task.source_video_only_path, work_dir, ["source.video.*"])
    task.source_audio_path = _rebase_path(task.source_audio_path, work_dir, ["source.audio.*"])
    task.source_wav_path = _rebase_path(task.source_wav_path, work_dir, ["source.audio.wav"])
    task.source_subtitle_path = _rebase_path(task.source_subtitle_path, work_dir, ["source.en.srt", "source.*.srt"])
    task.info_json_path = _rebase_path(task.info_json_path, work_dir, ["source.info.json"])
    task.zh_subtitle_path = _rebase_path(task.zh_subtitle_path, work_dir, ["zh_preview.srt", "zh.srt"])
    task.zh_audio_path = _rebase_path(task.zh_audio_path, work_dir, ["zh_audio_aligned.wav"])
    task.output_video_path = _rebase_path(task.output_video_path, work_dir, ["final_zh_dubbed.*"])
    for segment in task.segments:
        segment.tts_audio_path = _rebase_path(segment.tts_audio_path, work_dir / "zh_tts_segments", [f"{segment.id:06d}.wav"])
        segment.aligned_audio_path = _rebase_path(
            segment.aligned_audio_path,
            work_dir / "zh_tts_segments" / "aligned",
            [f"{segment.id:06d}.wav"],
        )
    return task


def _rebase_path(value: str | None, base_dir: Path, patterns: list[str]) -> str | None:
    if not value:
        return None
    path = Path(value)
    if path.exists():
        return str(path)
    candidate = base_dir / path.name
    if candidate.exists():
        return str(candidate)
    for pattern in patterns:
        matches = sorted(base_dir.glob(pattern))
        if matches:
            return str(matches[0])
    return str(candidate)


def _current_failed_stage(manager: ManifestManager) -> str:
    for stage in STAGES:
        if not manager.stage_done(stage):
            return stage
    return "unknown"
