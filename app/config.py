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
    subtitle_languages: list[str] = Field(default_factory=lambda: ["en", "zh-Hans", "zh-Hant"])
    convert_subs_to: str = "srt"
    write_info_json: bool = True
    write_thumbnail: bool = True
    keep_video_stream: bool = True
    keep_audio_stream: bool = True


class SubtitleConfig(BaseModel):
    source_language: str = "en"
    target_language: str = "zh"
    prefer_manual_subtitle: bool = True
    max_segment_chars: int = 300
    min_segment_duration: float = 0.3


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


class AudioAlignConfig(BaseModel):
    sample_rate: int = 24000
    max_speedup: float = 1.25
    min_speed: float = 0.85
    silence_padding_ms: int = 80
    allow_overflow: bool = True
    overflow_warning_ratio: float = 1.35


class MuxConfig(BaseModel):
    output_container: str = "mp4"
    replace_audio: bool = True
    keep_original_video_codec: bool = True
    burn_subtitle: bool = False
    attach_subtitle: bool = False
    keep_original_audio: bool = False


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
    tts: TTSConfig = Field(default_factory=TTSConfig)
    audio_align: AudioAlignConfig = Field(default_factory=AudioAlignConfig)
    mux: MuxConfig = Field(default_factory=MuxConfig)
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
