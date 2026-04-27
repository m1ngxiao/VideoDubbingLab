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
from app.subtitle.parser import parse_srt

logger = logging.getLogger(__name__)


async def run_youtube_pipeline(
    url: str,
    output_dir: Path,
    config: AppConfig,
    resume: bool = True,
    force: bool = False,
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

        if not (resume and manager.stage_done("tts")):
            task = await tts_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("tts")

        if not (resume and manager.stage_done("align_audio")):
            task = align_audio_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("align_audio")

        if not (resume and manager.stage_done("write_subtitle")):
            task = write_subtitle_stage(task)
            manager.update_task(task)
            manager.mark_done("write_subtitle")

        if not (resume and manager.stage_done("mux")):
            task = mux_stage(task, config, force=force)
            manager.update_task(task)
            manager.mark_done("mux")
        return manager.manifest
    except Exception as exc:
        stage = _current_failed_stage(manager)
        manager.fail(stage, exc)
        raise


def _current_failed_stage(manager: ManifestManager) -> str:
    for stage in STAGES:
        if not manager.stage_done(stage):
            return stage
    return "unknown"
