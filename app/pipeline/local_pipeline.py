from __future__ import annotations

import shutil
from pathlib import Path

from app.config import AppConfig
from app.logging_config import setup_logging
from app.pipeline.manifest import ManifestManager
from app.pipeline.stages import align_audio_stage, mux_stage, translate_stage, tts_stage, write_subtitle_stage
from app.schemas import VideoTask
from app.subtitle.parser import parse_srt
from app.utils.files import ensure_dir, safe_filename
from app.utils.text import short_hash


async def run_local_pipeline(
    video: Path,
    subtitle: Path,
    output_dir: Path,
    config: AppConfig,
    resume: bool = True,
    force: bool = False,
):
    work_dir = ensure_dir(output_dir)
    setup_logging(work_dir, config.runtime.log_level)
    task = VideoTask(
        task_id=f"local_{short_hash(str(video.resolve()))}_{safe_filename(video.stem)}",
        title=video.stem,
        work_dir=str(work_dir),
        source_video_path=str(work_dir / "source.mp4"),
        source_subtitle_path=str(work_dir / f"source{subtitle.suffix}"),
    )
    manager = ManifestManager.load_or_create(work_dir, task, resume=resume)
    task = manager.manifest.task

    try:
        if not (resume and manager.stage_done("download")):
            shutil.copy2(video, task.source_video_path or str(work_dir / "source.mp4"))
            shutil.copy2(subtitle, task.source_subtitle_path or str(work_dir / f"source{subtitle.suffix}"))
            manager.update_task(task)
            manager.mark_done("download")

        if not (resume and manager.stage_done("parse_subtitle")):
            if not task.source_subtitle_path:
                raise FileNotFoundError("Local subtitle path is required")
            task.segments = parse_srt(task.source_subtitle_path)
            manager.update_task(task)
            manager.mark_done("parse_subtitle")

        if not (resume and manager.stage_done("translate")):
            task = await translate_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("translate")

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
        manager.fail(_current_failed_stage(manager), exc)
        raise


def _current_failed_stage(manager: ManifestManager) -> str:
    for stage in ["download", "parse_subtitle", "translate", "tts", "align_audio", "write_subtitle", "mux"]:
        if not manager.stage_done(stage):
            return stage
    return "unknown"
