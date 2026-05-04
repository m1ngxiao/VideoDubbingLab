from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.schemas import Manifest, VideoTask
from app.schemas import utc_now_iso


class ManifestManager:
    def __init__(self, path: Path, manifest: Manifest):
        self.path = path
        self.manifest = manifest

    @classmethod
    def load_or_create(cls, work_dir: Path, task: VideoTask, resume: bool = True) -> "ManifestManager":
        path = work_dir / "manifest.json"
        if resume and path.exists():
            manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
            return cls(path, manifest)
        manifest = Manifest(task=task)
        manager = cls(path, manifest)
        manager.save()
        return manager

    @classmethod
    def load_existing(cls, work_dir: Path) -> "ManifestManager":
        path = work_dir / "manifest.json"
        if not path.exists():
            raise FileNotFoundError(f"Manifest not found: {path}")
        manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
        return cls(path, manifest)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.manifest.to_json_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def stage_done(self, stage: str) -> bool:
        return self.manifest.stage_done(stage)

    def mark_done(self, stage: str) -> None:
        self.manifest.mark_done(stage)
        self.save()

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
        self.manifest.record_stage_run(
            stage=stage,
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            inputs=inputs,
            outputs=outputs,
            error=error,
        )
        self.save()

    @contextmanager
    def stage_run(
        self,
        stage: str,
        inputs: dict[str, str | None] | None = None,
        outputs: dict[str, str | None] | None = None,
    ) -> Iterator[None]:
        started_at = utc_now_iso()
        start = time.perf_counter()
        try:
            yield
        except Exception as exc:
            ended_at = utc_now_iso()
            self.record_stage_run(
                stage=stage,
                status="failed",
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=time.perf_counter() - start,
                inputs=inputs,
                outputs=outputs,
                error=str(exc),
            )
            raise
        ended_at = utc_now_iso()
        self.record_stage_run(
            stage=stage,
            status="completed",
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=time.perf_counter() - start,
            inputs=inputs,
            outputs=outputs,
        )

    def update_segment_state(self, segment_id: int, state: dict) -> None:
        self.manifest.segment_states[str(segment_id)] = state
        self.manifest.touch()
        self.save()

    def fail(self, stage: str, error: Exception | str) -> None:
        self.manifest.mark_failed(stage, str(error))
        self.save()

    def update_task(self, task: VideoTask) -> None:
        self.manifest.task = task
        self.manifest.touch()
        self.save()
