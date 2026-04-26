from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSBackend(ABC):
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        out_path: Path,
        speaker: str = "default",
        ref_audio: str | None = None,
        target_duration: float | None = None,
    ) -> Path:
        raise NotImplementedError
