from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

from app.asr.subtitle_align import write_asr_srt
from app.audio.align import align_segment_audio
from app.audio.concat import build_timeline_audio
from app.audio.dubbing_plan import plan_dubbing_segments
from app.audio.duration import get_media_duration
from app.audio.duration import get_audio_duration
from app.audio.postprocess import postprocess_tts_file, time_stretch
from app.audio.silence import write_silence_wav
from app.config import AppConfig
from app.mux.ffmpeg_muxer import mux_video_audio
from app.pipeline.manifest import ManifestManager
from app.qc.report import write_qc_report
from app.schemas import Segment, VideoTask
from app.subtitle.parser import parse_subtitle
from app.subtitle.reflow import reflow_segments
from app.subtitle.writer import write_srt
from app.translator.openai_compatible import OpenAICompatibleTranslator
from app.translator.utils import chunked
from app.tts.base import TTSBackend
from app.tts.cache import ref_audio_hash, tts_cache_key
from app.tts.cosyvoice_backend import CosyVoiceHTTPBackend
from app.tts.edge_tts_backend import EdgeTTSBackend
from app.tts.gpt_sovits_backend import GPTSoVITSHTTPBackend
from app.utils.shell import run_command

logger = logging.getLogger(__name__)

STAGES = [
    "download",
    "parse_subtitle",
    "reflow_subtitle",
    "translate",
    "plan_dubbing",
    "tts",
    "align_audio",
    "write_subtitle",
    "mux",
    "qc_report",
]


def build_translator(config: AppConfig) -> OpenAICompatibleTranslator:
    if config.llm.provider != "openai_compatible":
        raise ValueError(f"Unsupported llm.provider: {config.llm.provider}")
    api_key = get_llm_api_key(config)
    if not api_key:
        raise RuntimeError(
            f"Missing API key environment variable: {config.llm.api_key_env}. "
            "For DeepSeek configs, DEEPSEEK_API_KEY is preferred and LLM_API_KEY is accepted as a fallback."
        )
    return OpenAICompatibleTranslator(
        base_url=config.llm.base_url,
        api_key=api_key,
        model=config.llm.model,
        temperature=config.llm.temperature,
        timeout_seconds=config.llm.timeout_seconds,
        batch_size=config.llm.batch_size,
        max_retries=config.llm.max_retries,
        cache_dir=str(Path(config.paths.cache_dir) / "translation"),
        cache_enabled=config.translation.cache_enabled,
        prompt_version=config.translation.prompt_version,
        over_duration_ratio=config.translation.over_duration_ratio,
    )


def get_llm_api_key(config: AppConfig) -> str | None:
    api_key = os.getenv(config.llm.api_key_env)
    if api_key:
        return api_key
    if "deepseek" in config.llm.base_url.lower() or "deepseek" in config.llm.model.lower():
        return os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
    return None


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
        return CosyVoiceHTTPBackend(
            config.tts.endpoint,
            sample_rate=config.tts.sample_rate,
            prompt_text=config.tts.prompt_text,
            timeout_seconds=config.tts.timeout_seconds,
            batch_endpoint=config.tts_batch.endpoint if config.tts_batch.enabled else None,
        )
    if backend == "gpt_sovits_http":
        if not config.tts.endpoint:
            raise ValueError("tts.endpoint is required for gpt_sovits_http")
        return GPTSoVITSHTTPBackend(
            config.tts.endpoint,
            sample_rate=config.tts.sample_rate,
            prompt_text=config.tts.prompt_text,
            prompt_lang=config.tts.prompt_lang,
            text_lang=config.tts.text_lang,
            timeout_seconds=config.tts.timeout_seconds,
        )
    raise ValueError(f"Unsupported tts.backend: {config.tts.backend}")


def build_asr_backend(config: AppConfig):
    backend = config.asr.backend.lower()
    if backend == "faster_whisper":
        from app.asr.faster_whisper_backend import FasterWhisperBackend

        return FasterWhisperBackend(
            model_size=config.asr.model_size,
            device=config.asr.device,
            compute_type=config.asr.compute_type,
            word_timestamps=config.asr.word_timestamps,
        )
    if backend == "whisperx":
        from app.asr.whisperx_backend import WhisperXBackend

        return WhisperXBackend(
            model_size=config.asr.model_size,
            device=config.asr.device,
            compute_type=config.asr.compute_type,
            word_timestamps=config.asr.word_timestamps,
        )
    raise ValueError(f"Unsupported asr.backend: {config.asr.backend}")


async def parse_subtitle_stage(task: VideoTask, config: AppConfig) -> VideoTask:
    logger.info("[parse_subtitle] start")
    if task.source_subtitle_path:
        task.segments = parse_subtitle(task.source_subtitle_path)
        logger.info(
            "[parse_subtitle] parsed %s subtitle segments from %s",
            len(task.segments),
            task.source_subtitle_path,
        )
        return task

    if not config.asr.enabled:
        raise FileNotFoundError("No subtitle found. Enable asr.enabled to use ASR fallback.")
    audio_path = task.source_wav_path or task.source_audio_path or task.source_video_path
    if not audio_path:
        raise FileNotFoundError("No subtitle found and no source audio/video path is available for ASR fallback.")

    logger.info("[parse_subtitle] no subtitle found; running ASR fallback with %s", config.asr.backend)
    backend = build_asr_backend(config)
    task.segments = await backend.transcribe(audio_path, language=config.asr.language)
    task.source_subtitle_type = "asr"
    if config.asr.output_srt:
        asr_srt = Path(task.work_dir) / f"source.{config.asr.language}.asr.srt"
        write_asr_srt(task.segments, asr_srt)
        task.source_subtitle_path = str(asr_srt)
    logger.info("[parse_subtitle] ASR produced %s segments", len(task.segments))
    return task


async def translate_stage(task: VideoTask, manager: ManifestManager, config: AppConfig) -> VideoTask:
    logger.info("[translate] start")
    translator = build_translator(config)
    untranslated = [segment for segment in task.segments if not segment.target_text]
    if untranslated and (not task.translation_summary and not task.translation_terms):
        summary, terms = await translator.prepare_context(
            task.segments,
            preserve_terms=config.translation.preserve_terms,
            max_chars=config.translation.summary_max_chars,
            enable_summary=config.translation.enable_summary,
            enable_terms=config.translation.enable_terms,
        )
        task.translation_summary = summary
        task.translation_terms = terms
        manager.update_task(task)
    if untranslated:
        translated = await translator.translate_segments(
            untranslated,
            summary=task.translation_summary or "",
            terms=task.translation_terms,
            reflect_adapt=config.translation.enable_reflect_adapt,
        )
        by_id = {segment.id: segment for segment in translated}
        for index, segment in enumerate(task.segments):
            if segment.id in by_id:
                task.segments[index] = by_id[segment.id]
        manager.update_task(task)
    logger.info("[translate] done")
    return task


def reflow_subtitle_stage(task: VideoTask, manager: ManifestManager, config: AppConfig) -> VideoTask:
    logger.info("[reflow_subtitle] start")
    if any(segment.target_text for segment in task.segments):
        task.warnings.append("Subtitle reflow skipped because translated segments already exist")
        _populate_dubbing_unit_fields(task.segments, config)
        return task
    before = len(task.segments)
    task.segments = reflow_segments(task.segments, config.subtitle)
    _populate_dubbing_unit_fields(task.segments, config)
    after = len(task.segments)
    manager.update_task(task)
    logger.info("[reflow_subtitle] done: %s -> %s segments", before, after)
    return task


def _populate_dubbing_unit_fields(segments: list[Segment], config: AppConfig) -> None:
    for segment in segments:
        segment.original_start = segment.original_start if segment.original_start is not None else segment.start
        segment.original_end = segment.original_end if segment.original_end is not None else segment.end
        segment.max_zh_chars = max(
            config.subtitle.min_zh_chars,
            int(round(segment.duration * config.subtitle.max_zh_chars_per_second)),
        )


def plan_dubbing_stage(task: VideoTask, manager: ManifestManager, config: AppConfig) -> VideoTask:
    logger.info("[plan_dubbing] start")
    if any(segment.tts_audio_path for segment in task.segments):
        task.warnings.append("Dubbing plan skipped because TTS audio already exists")
        return task
    before = len(task.segments)
    task.segments = plan_dubbing_segments(task.segments, config.audio_align)
    _populate_dubbing_unit_fields(task.segments, config)
    for segment in task.segments:
        for warning in segment.warnings:
            task.warnings.append(f"Segment {segment.id} {warning}")
    manager.update_task(task)
    logger.info("[plan_dubbing] done: %s -> %s segments", before, len(task.segments))
    return task


async def tts_stage(task: VideoTask, manager: ManifestManager, config: AppConfig) -> VideoTask:
    logger.info("[tts] start")
    backend = build_tts_backend(config)
    tts_dir = Path(task.work_dir) / "zh_tts_segments"
    tts_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(config.paths.cache_dir) / "tts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ref_digest = ref_audio_hash(config.tts.ref_audio)
    jobs: list[dict] = []
    for index, segment in enumerate(task.segments, start=1):
        out_path = tts_dir / f"{segment.id:06d}.wav"
        if segment.tts_audio_path and Path(segment.tts_audio_path).exists():
            segment.tts_status = "done"
            continue
        text = segment.target_text or segment.source_text
        cache_key = tts_cache_key(
            text=text,
            voice=config.tts.voice,
            speaker=segment.speaker or config.tts.speaker,
            ref_audio_digest=ref_digest,
            model_version=config.tts.model_version or config.tts.voice or config.tts.backend,
            prompt_text=config.tts.prompt_text,
        )
        segment.tts_cache_key = cache_key
        cache_path = cache_dir / f"{cache_key}.wav"
        if config.tts_batch.cache_enabled and cache_path.exists():
            shutil.copy2(cache_path, out_path)
            segment.tts_audio_path = str(out_path)
            segment.tts_status = "done"
            manager.update_segment_state(segment.id, _segment_tts_state(segment))
            continue
        jobs.append(
            {
                "id": segment.id,
                "index": index,
                "segment": segment,
                "text": text,
                "out_path": out_path,
                "cache_path": cache_path,
                "cache_dir": cache_dir,
                "voice": config.tts.voice,
                "model_version": config.tts.model_version or config.tts.voice or config.tts.backend,
                "prompt_text": config.tts.prompt_text,
                "ref_digest": ref_digest,
                "speaker": segment.speaker or config.tts.speaker,
                "ref_audio": config.tts.ref_audio,
                "target_duration": segment.duration,
            }
        )

    batch_size = max(1, config.tts_batch.max_batch_size if config.tts_batch.enabled else 1)
    concurrency = max(1, config.tts_batch.concurrency)
    semaphore = asyncio.Semaphore(concurrency)

    async def run_batch(batch: list[dict]) -> None:
        async with semaphore:
            await _run_tts_batch(batch, backend, config, manager, task)

    await asyncio.gather(*(run_batch(batch) for batch in chunked(jobs, batch_size)))
    if hasattr(backend, "aclose"):
        await backend.aclose()  # type: ignore[attr-defined]
    manager.update_task(task)
    logger.info("[tts] done")
    return task


async def _run_tts_batch(
    batch: list[dict],
    backend: TTSBackend,
    config: AppConfig,
    manager: ManifestManager,
    task: VideoTask,
) -> None:
    if not batch:
        return
    try:
        logger.info("[tts] batch ids=%s", ",".join(str(item["id"]) for item in batch))
        await backend.synthesize_batch(batch)
        for item in batch:
            await _finalize_tts_item(item, backend, config, manager, task)
    except Exception as exc:  # noqa: BLE001 - isolate failures to segments
        if len(batch) > 1:
            logger.warning("[tts] batch failed, retrying individually: %s", exc)
            for item in batch:
                await _run_tts_batch([item], backend, config, manager, task)
            return
        item = batch[0]
        segment: Segment = item["segment"]
        warning = f"TTS failed for segment {segment.id}: {exc}"
        segment.tts_status = "failed"
        segment.tts_error = str(exc)
        segment.warnings.append(warning)
        task.warnings.append(warning)
        manager.update_segment_state(segment.id, _segment_tts_state(segment))


async def _finalize_tts_item(
    item: dict,
    backend: TTSBackend,
    config: AppConfig,
    manager: ManifestManager,
    task: VideoTask,
) -> None:
    segment: Segment = item["segment"]
    out_path = Path(item["out_path"])
    postprocess_tts_file(
        out_path,
        trim=config.audio_postprocess.trim_silence,
        normalize=config.audio_postprocess.normalize_loudness,
        target_lufs=config.audio_postprocess.target_lufs,
        true_peak_db=config.audio_postprocess.true_peak_db,
        fade_in_ms=config.audio_postprocess.fade_in_ms,
        fade_out_ms=config.audio_postprocess.fade_out_ms,
    )
    duration = get_audio_duration(out_path)
    if segment.duration > 0 and duration > segment.duration * config.audio_align.overflow_warning_ratio:
        if segment.short_target_text and segment.short_target_text != item["text"]:
            logger.info("[tts] segment %s too long; retrying with short_zh_text", segment.id)
            item["text"] = segment.short_target_text
            short_key = tts_cache_key(
                text=item["text"],
                voice=item["voice"],
                speaker=item["speaker"],
                ref_audio_digest=item["ref_digest"],
                model_version=item["model_version"],
                prompt_text=item["prompt_text"],
            )
            segment.tts_cache_key = short_key
            item["cache_path"] = Path(item["cache_dir"]) / f"{short_key}.wav"
            await backend.synthesize(
                text=segment.short_target_text,
                out_path=out_path,
                speaker=item["speaker"],
                ref_audio=item["ref_audio"],
                target_duration=segment.duration,
            )
            postprocess_tts_file(
                out_path,
                trim=config.audio_postprocess.trim_silence,
                normalize=config.audio_postprocess.normalize_loudness,
                target_lufs=config.audio_postprocess.target_lufs,
                true_peak_db=config.audio_postprocess.true_peak_db,
                fade_in_ms=config.audio_postprocess.fade_in_ms,
                fade_out_ms=config.audio_postprocess.fade_out_ms,
            )
            duration = get_audio_duration(out_path)
            segment.translation_notes.append("tts_retried_with_short_zh_text")
        if duration > segment.duration * config.audio_align.overflow_warning_ratio and get_llm_api_key(config):
            try:
                logger.info("[tts] segment %s still too long; asking LLM to compress translation", segment.id)
                translator = build_translator(config)
                await translator.compress_segment(segment)
                if segment.target_text and segment.target_text != item["text"]:
                    item["text"] = segment.target_text
                    compressed_key = tts_cache_key(
                        text=item["text"],
                        voice=item["voice"],
                        speaker=item["speaker"],
                        ref_audio_digest=item["ref_digest"],
                        model_version=item["model_version"],
                        prompt_text=item["prompt_text"],
                    )
                    segment.tts_cache_key = compressed_key
                    item["cache_path"] = Path(item["cache_dir"]) / f"{compressed_key}.wav"
                    await backend.synthesize(
                        text=item["text"],
                        out_path=out_path,
                        speaker=item["speaker"],
                        ref_audio=item["ref_audio"],
                        target_duration=segment.duration,
                    )
                    postprocess_tts_file(
                        out_path,
                        trim=config.audio_postprocess.trim_silence,
                        normalize=config.audio_postprocess.normalize_loudness,
                        target_lufs=config.audio_postprocess.target_lufs,
                        true_peak_db=config.audio_postprocess.true_peak_db,
                        fade_in_ms=config.audio_postprocess.fade_in_ms,
                        fade_out_ms=config.audio_postprocess.fade_out_ms,
                    )
                    duration = get_audio_duration(out_path)
            except Exception as exc:  # noqa: BLE001 - compression improves fit but should not hide TTS output
                warning = f"LLM compression retry failed for segment {segment.id}: {exc}"
                segment.warnings.append(warning)
                task.warnings.append(warning)
        if duration > segment.duration * config.audio_align.overflow_warning_ratio:
            ratio = duration / max(segment.duration, 0.1)
            if ratio <= config.audio_postprocess.max_time_stretch_ratio:
                stretched = out_path.with_suffix(".stretch.wav")
                time_stretch(out_path, stretched, ratio)
                shutil.move(str(stretched), out_path)
                duration = get_audio_duration(out_path)
                segment.translation_notes.append("tts_time_stretched")
            else:
                warning = f"TTS audio duration {duration:.2f}s exceeds target {segment.duration:.2f}s"
                segment.warnings.append(warning)
                task.warnings.append(f"Segment {segment.id} {warning}")
    cache_path = Path(item["cache_path"])
    if config.tts_batch.cache_enabled:
        shutil.copy2(out_path, cache_path)
    segment.tts_audio_path = str(out_path)
    segment.tts_status = "done"
    segment.tts_error = None
    manager.update_segment_state(segment.id, _segment_tts_state(segment))


def _segment_tts_state(segment: Segment) -> dict:
    return {
        "tts_status": segment.tts_status,
        "tts_audio_path": segment.tts_audio_path,
        "tts_cache_key": segment.tts_cache_key,
        "tts_error": segment.tts_error,
    }


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
        segment.speed_ratio = result.speed_ratio
        segment.overflow = result.overflow
        if result.warnings:
            for warning in result.warnings:
                full_warning = f"Segment {segment.id} {warning}"
                segment.warnings.append(full_warning)
                task.warnings.append(full_warning)
            warning_count += len(result.warnings)
        manager.update_task(task)

    total_duration = _get_total_duration(task)
    zh_audio_path = Path(task.work_dir) / "zh_audio_aligned.wav"
    warning_offsets = {segment.id: len(segment.warnings) for segment in task.segments}
    build_timeline_audio(
        task.segments,
        zh_audio_path,
        total_duration,
        config.audio_align.sample_rate,
        prevent_overlaps=True,
        min_gap_ms=config.audio_align.silence_padding_ms,
        max_shift_ms=config.audio_align.max_shift_ms,
    )
    for segment in task.segments:
        for warning in segment.warnings[warning_offsets.get(segment.id, 0) :]:
            task.warnings.append(f"Segment {segment.id} {warning}")
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
        mux_video_audio(task.source_video_path, task.zh_audio_path, output_path, config.mux, task.zh_subtitle_path)
    task.output_video_path = str(output_path)
    if config.mux.create_preview:
        task.preview_video_path = str(_create_preview(output_path, config.mux.preview_seconds))
    task.status = "completed"
    logger.info("[mux] done: %s", output_path)
    return task


def qc_report_stage(task: VideoTask, config: AppConfig) -> VideoTask:
    logger.info("[qc_report] start")
    report_path = Path(task.work_dir) / "qc_report.json"
    write_qc_report(task, config, report_path)
    task.qc_report_path = str(report_path)
    logger.info("[qc_report] done: %s", report_path)
    return task


def _create_preview(output_path: Path, seconds: int) -> Path:
    preview_path = output_path.with_name("preview_60s.mp4")
    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(output_path),
            "-t",
            str(max(1, seconds)),
            "-c",
            "copy",
            str(preview_path),
        ],
        timeout=None,
    )
    return preview_path


def _get_total_duration(task: VideoTask) -> float:
    if task.source_video_path and Path(task.source_video_path).exists():
        try:
            return get_media_duration(task.source_video_path)
        except Exception as exc:  # noqa: BLE001 - fallback to subtitle timeline
            task.warnings.append(f"Could not probe video duration, using subtitle end time: {exc}")
    return max((segment.end for segment in task.segments), default=0.1)
