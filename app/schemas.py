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
    speaker: str = "default"
    tts_audio_path: str | None = None
    aligned_audio_path: str | None = None
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
    zh_subtitle_path: str | None = None
    zh_audio_path: str | None = None
    output_video_path: str | None = None
    info_json_path: str | None = None
    status: str = "created"
    segments: list[Segment] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    version: str = "0.1"
    task: VideoTask
    completed_stages: list[str] = Field(default_factory=list)
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

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
