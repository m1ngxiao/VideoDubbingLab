from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    name: str = "VideoDubbingLab"


class PathsConfig(BaseModel):
    cache_dir: str = "./data/cache"
    output_dir: str = "./data/output"


class DownloadConfig(BaseModel):
    format: str = "bv*+ba/b"
    merge_output_format: str = "mp4"
    write_subs: bool = True
    write_auto_subs: bool = True
    subtitle_languages: list[str] = Field(default_factory=lambda: ["en"])
    convert_subs_to: str = "srt"
    write_info_json: bool = True
    write_thumbnail: bool = True
    keep_video_stream: bool = True
    keep_audio_stream: bool = True
    avoid_duplicate_stream_downloads: bool = True


class SubtitleConfig(BaseModel):
    source_language: str = "en"
    target_language: str = "zh"
    prefer_manual_subtitle: bool = True
    enable_reflow: bool = True
    max_segment_chars: int = 180
    max_segment_duration: float = 10.0
    max_merge_gap: float = 1.0
    min_segment_duration: float = 0.3
    max_zh_chars_per_second: float = 4.2
    min_zh_chars: int = 4


class LLMConfig(BaseModel):
    provider: str = "openai_compatible"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key_env: str = "LLM_API_KEY"
    model: str = "qwen-plus"
    temperature: float = 0.2
    timeout_seconds: int = 120
    max_retries: int = 3
    batch_size: int = 20


class TranslationConfig(BaseModel):
    mode: str = "technical_oral_zh"
    preserve_terms: list[str] = Field(default_factory=list)
    enable_summary: bool = True
    enable_terms: bool = True
    enable_reflect_adapt: bool = True
    summary_max_chars: int = 8000
    cache_enabled: bool = True
    prompt_version: str = "duration-aware-v1"
    over_duration_ratio: float = 1.10


class ASRConfig(BaseModel):
    enabled: bool = False
    backend: str = "faster_whisper"
    model_size: str = "small"
    device: str = "auto"
    compute_type: str = "auto"
    language: str = "en"
    word_timestamps: bool = False
    output_srt: bool = True


class TTSConfig(BaseModel):
    backend: str = "edge"
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"
    sample_rate: int = 24000
    speaker: str = "default"
    ref_audio: str | None = None
    endpoint: str | None = None
    prompt_text: str | None = None
    prompt_lang: str = "zh"
    text_lang: str = "zh"
    timeout_seconds: int = 120
    model_version: str | None = None


class TTSBatchConfig(BaseModel):
    enabled: bool = True
    endpoint: str | None = None
    max_batch_size: int = 8
    concurrency: int = 1
    cache_enabled: bool = True


class AudioAlignConfig(BaseModel):
    sample_rate: int = 24000
    max_speedup: float = 1.4
    min_speed: float = 0.85
    silence_padding_ms: int = 80
    allow_overflow: bool = True
    overflow_warning_ratio: float = 1.35
    enable_dubbing_plan: bool = True
    speech_chars_per_second: float = 4.2
    planning_tolerance: float = 1.5
    max_merge_segments: int = 3
    max_shift_ms: int = 250


class AudioPostprocessConfig(BaseModel):
    trim_silence: bool = True
    normalize_loudness: bool = True
    target_lufs: float = -16.0
    true_peak_db: float = -1.0
    fade_in_ms: int = 10
    fade_out_ms: int = 10
    max_time_stretch_ratio: float = 1.12


class AudioSeparationConfig(BaseModel):
    enabled: bool = False
    backend: str = "demucs"
    two_stems: str = "vocals"
    vocals_volume: float = 0.0
    background_volume: float = 1.0


class MuxConfig(BaseModel):
    output_container: str = "mp4"
    replace_audio: bool = True
    keep_original_video_codec: bool = True
    burn_subtitle: bool = True
    attach_subtitle: bool = False
    keep_original_audio: bool = False
    mix_original_audio: bool = True
    original_audio_volume: float = 0.18
    dubbed_audio_volume: float = 1.0
    duck_original_audio: bool = True
    duck_volume: float = 0.12
    duck_fade_ms: int = 80
    create_preview: bool = False
    preview_seconds: int = 60


class QCConfig(BaseModel):
    max_shift_seconds: float = 0.25
    max_duration_diff_seconds: float = 1.0
    max_overflow_ratio: float = 0.05
    target_lufs: float = -16.0
    true_peak_db: float = -1.0


class BatchConfig(BaseModel):
    jobs: int = 1
    download_concurrency: int = 2
    translate_concurrency: int = 2
    tts_concurrency: int = 1
    mux_concurrency: int = 1


class RuntimeConfig(BaseModel):
    resume: bool = True
    verbose: bool = True
    log_level: str = "INFO"


class AppConfig(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    download: DownloadConfig = Field(default_factory=DownloadConfig)
    subtitle: SubtitleConfig = Field(default_factory=SubtitleConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    asr: ASRConfig = Field(default_factory=ASRConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    tts_batch: TTSBatchConfig = Field(default_factory=TTSBatchConfig)
    audio_align: AudioAlignConfig = Field(default_factory=AudioAlignConfig)
    audio_postprocess: AudioPostprocessConfig = Field(default_factory=AudioPostprocessConfig)
    audio_separation: AudioSeparationConfig = Field(default_factory=AudioSeparationConfig)
    mux: MuxConfig = Field(default_factory=MuxConfig)
    qc: QCConfig = Field(default_factory=QCConfig)
    batch: BatchConfig = Field(default_factory=BatchConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {config_path}")
    return AppConfig.model_validate(data)


def dump_config(config: AppConfig) -> dict[str, Any]:
    return config.model_dump(mode="json")
