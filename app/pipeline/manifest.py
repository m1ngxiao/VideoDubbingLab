from __future__ import annotations

import json
from pathlib import Path

from app.schemas import Manifest, VideoTask


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

    def fail(self, stage: str, error: Exception | str) -> None:
        self.manifest.mark_failed(stage, str(error))
        self.save()

    def update_task(self, task: VideoTask) -> None:
        self.manifest.task = task
        self.manifest.touch()
        self.save()
