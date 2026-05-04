from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


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

    async def synthesize_batch(self, items: list[dict[str, Any]]) -> list[Path]:
        outputs: list[Path] = []
        for item in items:
            outputs.append(
                await self.synthesize(
                    text=str(item["text"]),
                    out_path=Path(item["out_path"]),
                    speaker=str(item.get("speaker") or "default"),
                    ref_audio=item.get("ref_audio"),
                    target_duration=item.get("target_duration"),
                )
            )
        return outputs
