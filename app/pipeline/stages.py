from __future__ import annotations

import logging
import os
from pathlib import Path

from app.audio.align import align_segment_audio
from app.audio.concat import build_timeline_audio
from app.audio.duration import get_media_duration
from app.audio.silence import write_silence_wav
from app.config import AppConfig
from app.mux.ffmpeg_muxer import mux_video_audio
from app.pipeline.manifest import ManifestManager
from app.schemas import Segment, VideoTask
from app.subtitle.writer import write_srt
from app.translator.openai_compatible import OpenAICompatibleTranslator
from app.tts.base import TTSBackend
from app.tts.cosyvoice_backend import CosyVoiceHTTPBackend
from app.tts.edge_tts_backend import EdgeTTSBackend
from app.tts.gpt_sovits_backend import GPTSoVITSHTTPBackend

logger = logging.getLogger(__name__)

STAGES = ["download", "extract_audio", "parse_subtitle", "translate", "tts", "align_audio", "write_subtitle", "mux"]


def build_translator(config: AppConfig) -> OpenAICompatibleTranslator:
    if config.llm.provider != "openai_compatible":
        raise ValueError(f"Unsupported llm.provider: {config.llm.provider}")
    api_key = os.getenv(config.llm.api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing API key environment variable: {config.llm.api_key_env}")
    return OpenAICompatibleTranslator(
        base_url=config.llm.base_url,
        api_key=api_key,
        model=config.llm.model,
        temperature=config.llm.temperature,
        timeout_seconds=config.llm.timeout_seconds,
        batch_size=config.llm.batch_size,
        max_retries=config.llm.max_retries,
    )


def build_tts_backend(config: AppConfig) -> TTSBackend:
    backend = config.tts.backend.lower()
    if backend == "edge":
        return EdgeTTSBackend(
            voice=config.tts.voice,
            rate=config.tts.rate,
            volume=config.tts.volume,
            pitch=config.tts.pitch,
            sample_rate=config.tts.sample_rate,
        )
    if backend == "cosyvoice_http":
        if not config.tts.endpoint:
            raise ValueError("tts.endpoint is required for cosyvoice_http")
        return CosyVoiceHTTPBackend(config.tts.endpoint, sample_rate=config.tts.sample_rate)
    if backend == "gpt_sovits_http":
        if not config.tts.endpoint:
            raise ValueError("tts.endpoint is required for gpt_sovits_http")
        return GPTSoVITSHTTPBackend(
            config.tts.endpoint,
            sample_rate=config.tts.sample_rate,
            prompt_text=config.tts.prompt_text,
            prompt_lang=config.tts.prompt_lang,
            text_lang=config.tts.text_lang,
        )
    raise ValueError(f"Unsupported tts.backend: {config.tts.backend}")


async def translate_stage(task: VideoTask, manager: ManifestManager, config: AppConfig) -> VideoTask:
    logger.info("[translate] start")
    translator = build_translator(config)
    untranslated = [segment for segment in task.segments if not segment.target_text]
    if untranslated:
        translated = await translator.translate_segments(untranslated)
        by_id = {segment.id: segment for segment in translated}
        for index, segment in enumerate(task.segments):
            if segment.id in by_id:
                task.segments[index] = by_id[segment.id]
        manager.update_task(task)
    logger.info("[translate] done")
    return task


async def tts_stage(task: VideoTask, manager: ManifestManager, config: AppConfig) -> VideoTask:
    logger.info("[tts] start")
    backend = build_tts_backend(config)
    tts_dir = Path(task.work_dir) / "zh_tts_segments"
    tts_dir.mkdir(parents=True, exist_ok=True)
    for index, segment in enumerate(task.segments, start=1):
        out_path = tts_dir / f"{segment.id:06d}.wav"
        if segment.tts_audio_path and Path(segment.tts_audio_path).exists():
            continue
        logger.info("[tts] segment %s/%s", index, len(task.segments))
        try:
            await backend.synthesize(
                segment.target_text or segment.source_text,
                out_path,
                speaker=segment.speaker or config.tts.speaker,
                ref_audio=config.tts.ref_audio,
                target_duration=segment.duration,
            )
        except Exception as exc:  # noqa: BLE001 - continue with silence placeholder
            warning = f"TTS failed for segment {segment.id}: {exc}"
            segment.warnings.append(warning)
            task.warnings.append(warning)
            write_silence_wav(out_path, min(max(segment.duration, 0.1), 1.0), config.tts.sample_rate)
        segment.tts_audio_path = str(out_path)
        manager.update_task(task)
    logger.info("[tts] done")
    return task


def align_audio_stage(task: VideoTask, manager: ManifestManager, config: AppConfig) -> VideoTask:
    logger.info("[align_audio] start")
    aligned_dir = Path(task.work_dir) / "zh_tts_segments" / "aligned"
    aligned_dir.mkdir(parents=True, exist_ok=True)
    warning_count = 0
    for segment in task.segments:
        if not segment.tts_audio_path:
            continue
        output_path = aligned_dir / f"{segment.id:06d}.wav"
        result = align_segment_audio(
            Path(segment.tts_audio_path),
            output_path,
            target_duration=segment.duration,
            sample_rate=config.audio_align.sample_rate,
            max_speedup=config.audio_align.max_speedup,
            silence_padding_ms=config.audio_align.silence_padding_ms,
        )
        segment.aligned_audio_path = str(result.output_path)
        if result.warnings:
            for warning in result.warnings:
                full_warning = f"Segment {segment.id} {warning}"
                segment.warnings.append(full_warning)
                task.warnings.append(full_warning)
            warning_count += len(result.warnings)
        manager.update_task(task)

    total_duration = _get_total_duration(task)
    zh_audio_path = Path(task.work_dir) / "zh_audio_aligned.wav"
    build_timeline_audio(task.segments, zh_audio_path, total_duration, config.audio_align.sample_rate)
    task.zh_audio_path = str(zh_audio_path)
    logger.info("[align_audio] warnings: %s", warning_count)
    return task


def write_subtitle_stage(task: VideoTask) -> VideoTask:
    logger.info("[write_subtitle] start")
    zh_srt = Path(task.work_dir) / "zh.srt"
    write_srt(task.segments, zh_srt)
    task.zh_subtitle_path = str(zh_srt)
    logger.info("[write_subtitle] done: %s", zh_srt)
    return task


def mux_stage(task: VideoTask, config: AppConfig, force: bool = False) -> VideoTask:
    logger.info("[mux] start")
    if not task.source_video_path:
        raise ValueError("source_video_path is required for mux")
    if not task.zh_audio_path:
        raise ValueError("zh_audio_path is required for mux")
    output_path = Path(task.work_dir) / f"final_zh_dubbed.{config.mux.output_container}"
    if output_path.exists() and not force:
        logger.info("[mux] existing output kept: %s", output_path)
    else:
        mux_video_audio(task.source_video_path, task.zh_audio_path, output_path, config.mux)
    task.output_video_path = str(output_path)
    task.status = "completed"
    logger.info("[mux] done: %s", output_path)
    return task


def _get_total_duration(task: VideoTask) -> float:
    if task.source_video_path and Path(task.source_video_path).exists():
        try:
            return get_media_duration(task.source_video_path)
        except Exception as exc:  # noqa: BLE001 - fallback to subtitle timeline
            task.warnings.append(f"Could not probe video duration, using subtitle end time: {exc}")
    return max((segment.end for segment in task.segments), default=0.1)
