from __future__ import annotations

import shutil
from pathlib import Path

from app.config import AppConfig
from app.logging_config import setup_logging
from app.pipeline.manifest import ManifestManager
from app.pipeline.stage_control import should_run_stage
from app.pipeline.stages import (
    STAGES,
    align_audio_stage,
    mux_stage,
    parse_subtitle_stage,
    plan_dubbing_stage,
    qc_report_stage,
    reflow_subtitle_stage,
    translate_stage,
    tts_stage,
    write_subtitle_stage,
)
from app.schemas import VideoTask
from app.utils.files import ensure_dir, safe_filename
from app.utils.text import short_hash


async def run_local_pipeline(
    video: Path,
    subtitle: Path,
    output_dir: Path,
    config: AppConfig,
    resume: bool = True,
    force: bool = False,
    from_stage: str | None = None,
    to_stage: str | None = None,
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
        if should_run_stage("download", manager, resume, from_stage, to_stage):
            with manager.stage_run(
                "download",
                inputs={"video": str(video), "subtitle": str(subtitle)},
                outputs={"source_video_path": task.source_video_path, "source_subtitle_path": task.source_subtitle_path},
            ):
                shutil.copy2(video, task.source_video_path or str(work_dir / "source.mp4"))
                shutil.copy2(subtitle, task.source_subtitle_path or str(work_dir / f"source{subtitle.suffix}"))
            manager.update_task(task)
            manager.mark_done("download")

        if should_run_stage("parse_subtitle", manager, resume, from_stage, to_stage):
            with manager.stage_run(
                "parse_subtitle",
                inputs={"source_subtitle_path": task.source_subtitle_path},
                outputs={"segments": "manifest.task.segments"},
            ):
                if not task.source_subtitle_path:
                    raise FileNotFoundError("Local subtitle path is required")
                task = await parse_subtitle_stage(task, config)
            manager.update_task(task)
            manager.mark_done("parse_subtitle")

        if should_run_stage("reflow_subtitle", manager, resume, from_stage, to_stage):
            with manager.stage_run("reflow_subtitle", outputs={"segments": "manifest.task.segments"}):
                task = reflow_subtitle_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("reflow_subtitle")

        if should_run_stage("translate", manager, resume, from_stage, to_stage):
            with manager.stage_run("translate", outputs={"segments": "manifest.task.segments"}):
                task = await translate_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("translate")

        if should_run_stage("plan_dubbing", manager, resume, from_stage, to_stage):
            with manager.stage_run("plan_dubbing", outputs={"segments": "manifest.task.segments"}):
                task = plan_dubbing_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("plan_dubbing")

        if should_run_stage("tts", manager, resume, from_stage, to_stage):
            with manager.stage_run("tts", outputs={"tts_dir": str(work_dir / "zh_tts_segments")}):
                task = await tts_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("tts")

        if should_run_stage("align_audio", manager, resume, from_stage, to_stage):
            outputs = {"zh_audio_path": str(work_dir / "zh_audio_aligned.wav")}
            with manager.stage_run("align_audio", outputs=outputs):
                task = align_audio_stage(task, manager, config)
                outputs["zh_audio_path"] = task.zh_audio_path
            manager.update_task(task)
            manager.mark_done("align_audio")

        if should_run_stage("write_subtitle", manager, resume, from_stage, to_stage):
            outputs = {"zh_subtitle_path": str(work_dir / "zh.srt")}
            with manager.stage_run("write_subtitle", outputs=outputs):
                task = write_subtitle_stage(task)
                outputs["zh_subtitle_path"] = task.zh_subtitle_path
            manager.update_task(task)
            manager.mark_done("write_subtitle")

        if should_run_stage("mux", manager, resume, from_stage, to_stage):
            outputs = {"output_video_path": str(work_dir / f"final_zh_dubbed.{config.mux.output_container}")}
            with manager.stage_run(
                "mux",
                inputs={"source_video_path": task.source_video_path, "zh_audio_path": task.zh_audio_path},
                outputs=outputs,
            ):
                task = mux_stage(task, config, force=force)
                outputs["output_video_path"] = task.output_video_path
            manager.update_task(task)
            manager.mark_done("mux")

        if should_run_stage("qc_report", manager, resume, from_stage, to_stage):
            outputs = {"qc_report_path": str(work_dir / "qc_report.json")}
            with manager.stage_run("qc_report", outputs=outputs):
                task = qc_report_stage(task, config)
                outputs["qc_report_path"] = task.qc_report_path
            manager.update_task(task)
            manager.mark_done("qc_report")
        return manager.manifest
    except Exception as exc:
        manager.fail(_current_failed_stage(manager), exc)
        raise


def _current_failed_stage(manager: ManifestManager) -> str:
    for stage in STAGES:
        if not manager.stage_done(stage):
            return stage
    return "unknown"
