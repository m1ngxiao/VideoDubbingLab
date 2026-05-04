from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.schemas import Segment


class ASRBackend(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str | Path, language: str = "en") -> list[Segment]:
        raise NotImplementedError
