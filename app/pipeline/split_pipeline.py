from __future__ import annotations

import logging
from pathlib import Path

from app.config import AppConfig
from app.downloader.youtube import YouTubeDownloader
from app.logging_config import setup_logging
from app.pipeline.manifest import ManifestManager
from app.pipeline.stage_control import should_run_stage, stage_in_range
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
from app.subtitle.writer import write_srt

logger = logging.getLogger(__name__)


async def run_youtube_translation_pipeline(
    url: str,
    output_dir: Path,
    config: AppConfig,
    resume: bool = True,
    from_stage: str | None = None,
    to_stage: str | None = None,
):
    downloader = YouTubeDownloader(output_dir=output_dir, config=config.download, sample_rate=config.audio_align.sample_rate)
    task = downloader.build_task(url)
    setup_logging(Path(task.work_dir), config.runtime.log_level)
    manager = ManifestManager.load_or_create(Path(task.work_dir), task, resume=resume)
    task = manager.manifest.task

    try:
        if should_run_stage("download", manager, resume, from_stage, to_stage):
            outputs: dict[str, str | None] = {}
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
            with manager.stage_run("translate", outputs={"segments": "manifest.task.segments"}):
                task = await translate_stage(task, manager, config)
            manager.update_task(task)
            manager.mark_done("translate")

        if should_run_stage("plan_dubbing", manager, resume, from_stage, to_stage):
            with manager.stage_run("plan_dubbing", outputs={"segments": "manifest.task.segments"}):
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
    from_stage: str | None = None,
    to_stage: str | None = None,
):
    work_dir = work_dir.resolve()
    manager = ManifestManager.load_existing(work_dir)
    setup_logging(work_dir, config.runtime.log_level)
    task = _rebase_task_paths(manager.manifest.task, work_dir)
    manager.update_task(task)

    try:
        if not manager.stage_done("translate"):
            raise RuntimeError("Work dir is not translated yet. Run translate-youtube first.")

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

        # Always regenerate subtitles after alignment because timing may move to avoid overlap.
        if stage_in_range("write_subtitle", from_stage, to_stage) and manager.stage_done("write_subtitle"):
            manager.manifest.completed_stages.remove("write_subtitle")
            manager.save()
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
