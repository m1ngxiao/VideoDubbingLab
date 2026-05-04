from __future__ import annotations

import logging
from pathlib import Path

from app.config import AppConfig
from app.downloader.youtube import YouTubeDownloader
from app.logging_config import setup_logging
from app.pipeline.manifest import ManifestManager
from app.pipeline.stage_control import should_run_stage, stage_limiter
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

logger = logging.getLogger(__name__)


async def run_youtube_pipeline(
    url: str,
    output_dir: Path,
    config: AppConfig,
    resume: bool = True,
    force: bool = False,
    from_stage: str | None = None,
    to_stage: str | None = None,
    stage_locks: dict[str, object] | None = None,
):
    downloader = YouTubeDownloader(output_dir=output_dir, config=config.download, sample_rate=config.audio_align.sample_rate)
    task = downloader.build_task(url)
    setup_logging(Path(task.work_dir), config.runtime.log_level)
    manager = ManifestManager.load_or_create(Path(task.work_dir), task, resume=resume)
    task = manager.manifest.task

    try:
        if should_run_stage("download", manager, resume, from_stage, to_stage):
            outputs: dict[str, str | None] = {}
            async with stage_limiter("download", stage_locks):
                with manager.stage_run("download", inputs={"url": task.url}, outputs=outputs):
                    task = downloader.download(task, resume=resume)
                    outputs.update(
                        {
                            "source_video_path": task.source_video_path,
                            "source_audio_path": task.source_audio_path,
                            "source_wav_path": task.source_wav_path,
                            "source_subtitle_path": task.source_subtitle_path,
                            "info_json_path": task.info_json_path,
                        }
                    )
            manager.update_task(task)
            manager.mark_done("download")

        if should_run_stage("parse_subtitle", manager, resume, from_stage, to_stage):
            with manager.stage_run(
                "parse_subtitle",
                inputs={"source_subtitle_path": task.source_subtitle_path},
                outputs={"segments": "manifest.task.segments"},
            ):
                task = await parse_subtitle_stage(task, config)
            manager.update_task(task)
            manager.mark_done("parse_subtitle")
            logger.info("[parse_subtitle] done: %s segments", len(task.segments))

        if should_run_stage("reflow_subtitle", manager, resume, from_stage, to_stage):
            with manager.stage_run("reflow_subtitle", outputs={"segments": "manifest.task.segments"}):
                task = reflow_subtitle_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("reflow_subtitle")

        if should_run_stage("translate", manager, resume, from_stage, to_stage):
            async with stage_limiter("translate", stage_locks):
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
            async with stage_limiter("tts", stage_locks):
                with manager.stage_run("tts", outputs={"tts_dir": str(Path(task.work_dir) / "zh_tts_segments")}):
                    task = await tts_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("tts")

        if should_run_stage("align_audio", manager, resume, from_stage, to_stage):
            outputs = {"zh_audio_path": str(Path(task.work_dir) / "zh_audio_aligned.wav")}
            with manager.stage_run("align_audio", outputs=outputs):
                task = align_audio_stage(task, manager, config)
                outputs["zh_audio_path"] = task.zh_audio_path
            manager.update_task(task)
            manager.mark_done("align_audio")

        if should_run_stage("write_subtitle", manager, resume, from_stage, to_stage):
            outputs = {"zh_subtitle_path": str(Path(task.work_dir) / "zh.srt")}
            with manager.stage_run("write_subtitle", outputs=outputs):
                task = write_subtitle_stage(task)
                outputs["zh_subtitle_path"] = task.zh_subtitle_path
            manager.update_task(task)
            manager.mark_done("write_subtitle")

        if should_run_stage("mux", manager, resume, from_stage, to_stage):
            outputs = {"output_video_path": str(Path(task.work_dir) / f"final_zh_dubbed.{config.mux.output_container}")}
            async with stage_limiter("mux", stage_locks):
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
            outputs = {"qc_report_path": str(Path(task.work_dir) / "qc_report.json")}
            with manager.stage_run("qc_report", outputs=outputs):
                task = qc_report_stage(task, config)
                outputs["qc_report_path"] = task.qc_report_path
            manager.update_task(task)
            manager.mark_done("qc_report")
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
