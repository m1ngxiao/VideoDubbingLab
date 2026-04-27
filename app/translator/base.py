from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import Segment


class Translator(ABC):
    @abstractmethod
    async def translate_segments(
        self,
        segments: list[Segment],
        summary: str = "",
        terms: list[dict[str, str]] | None = None,
        reflect_adapt: bool = True,
    ) -> list[Segment]:
        raise NotImplementedError
