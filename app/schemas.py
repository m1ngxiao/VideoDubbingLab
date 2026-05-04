from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Segment(BaseModel):
    id: int
    start: float
    end: float
    duration: float
    source_text: str
    target_text: str | None = None
    short_target_text: str | None = None
    estimated_seconds: float | None = None
    translation_notes: list[str] = Field(default_factory=list)
    speaker: str = "default"
    max_zh_chars: int | None = None
    tts_audio_path: str | None = None
    aligned_audio_path: str | None = None
    tts_cache_key: str | None = None
    tts_status: str = "pending"
    tts_error: str | None = None
    translation_cache_key: str | None = None
    original_start: float | None = None
    original_end: float | None = None
    placed_start: float | None = None
    placed_end: float | None = None
    shift_ms: float = 0.0
    speed_ratio: float = 1.0
    overflow: bool = False
    warnings: list[str] = Field(default_factory=list)


class VideoTask(BaseModel):
    task_id: str
    url: str | None = None
    title: str | None = None
    video_id: str | None = None
    work_dir: str
    source_video_path: str | None = None
    source_video_only_path: str | None = None
    source_audio_path: str | None = None
    source_wav_path: str | None = None
    source_subtitle_path: str | None = None
    source_subtitle_language: str | None = None
    source_subtitle_type: str | None = None
    zh_subtitle_path: str | None = None
    zh_audio_path: str | None = None
    output_video_path: str | None = None
    preview_video_path: str | None = None
    qc_report_path: str | None = None
    info_json_path: str | None = None
    translation_summary: str | None = None
    translation_terms: list[dict[str, str]] = Field(default_factory=list)
    status: str = "created"
    segments: list[Segment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StageRun(BaseModel):
    stage: str
    status: str
    started_at: str
    ended_at: str
    duration_seconds: float
    inputs: dict[str, str | None] = Field(default_factory=dict)
    outputs: dict[str, str | None] = Field(default_factory=dict)
    error: str | None = None


class Manifest(BaseModel):
    version: str = "0.2"
    task: VideoTask
    completed_stages: list[str] = Field(default_factory=list)
    stage_runs: list[StageRun] = Field(default_factory=list)
    segment_states: dict[str, dict[str, Any]] = Field(default_factory=dict)
    failed_stage: str | None = None
    error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    def stage_done(self, stage: str) -> bool:
        return stage in self.completed_stages

    def mark_done(self, stage: str) -> None:
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
        self.failed_stage = None
        self.error = None
        self.touch()

    def mark_failed(self, stage: str, error: str) -> None:
        self.failed_stage = stage
        self.error = error
        self.task.status = "failed"
        self.touch()

    def record_stage_run(
        self,
        stage: str,
        status: str,
        started_at: str,
        ended_at: str,
        duration_seconds: float,
        inputs: dict[str, str | None] | None = None,
        outputs: dict[str, str | None] | None = None,
        error: str | None = None,
    ) -> None:
        self.stage_runs.append(
            StageRun(
                stage=stage,
                status=status,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=duration_seconds,
                inputs=inputs or {},
                outputs=outputs or {},
                error=error,
            )
        )
        self.touch()

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
