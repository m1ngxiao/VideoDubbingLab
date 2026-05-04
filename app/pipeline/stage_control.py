from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.pipeline.manifest import ManifestManager
from app.pipeline.stages import STAGES


STAGE_RESOURCE = {
    "download": "download",
    "translate": "translate",
    "tts": "tts",
    "align_audio": "mux",
    "write_subtitle": "mux",
    "mux": "mux",
    "qc_report": "mux",
}


def should_run_stage(
    stage: str,
    manager: ManifestManager,
    resume: bool,
    from_stage: str | None = None,
    to_stage: str | None = None,
) -> bool:
    if not stage_in_range(stage, from_stage, to_stage):
        return False
    return not (resume and manager.stage_done(stage))


def stage_in_range(stage: str, from_stage: str | None = None, to_stage: str | None = None) -> bool:
    if stage not in STAGES:
        raise ValueError(f"Unknown stage: {stage}")
    start = STAGES.index(from_stage) if from_stage else 0
    end = STAGES.index(to_stage) if to_stage else len(STAGES) - 1
    if start > end:
        raise ValueError(f"from-stage must be before to-stage: {from_stage} > {to_stage}")
    index = STAGES.index(stage)
    return start <= index <= end


@asynccontextmanager
async def stage_limiter(stage: str, locks: dict[str, object] | None = None) -> AsyncIterator[None]:
    if not locks:
        yield
        return
    resource = STAGE_RESOURCE.get(stage)
    semaphore = locks.get(resource) if resource else None
    if semaphore is None:
        yield
        return
    async with semaphore:  # type: ignore[attr-defined]
        yield
