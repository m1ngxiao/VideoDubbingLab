from __future__ import annotations

import asyncio
from pathlib import Path

from app.asr.base import ASRBackend
from app.schemas import Segment
from app.subtitle.normalize import normalize_subtitle_text


class FasterWhisperBackend(ASRBackend):
    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "auto",
        word_timestamps: bool = False,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.word_timestamps = word_timestamps
        self._model = None

    async def transcribe(self, audio_path: str | Path, language: str = "en") -> list[Segment]:
        return await asyncio.to_thread(self._transcribe_sync, Path(audio_path), language)

    def _load_model(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "ASR backend 'faster_whisper' requires optional package faster-whisper. "
                    "Install it on the GPU/ASR worker or disable asr.enabled."
                ) from exc
            kwargs = {}
            if self.compute_type != "auto":
                kwargs["compute_type"] = self.compute_type
            self._model = WhisperModel(self.model_size, device=self.device, **kwargs)
        return self._model

    def _transcribe_sync(self, audio_path: Path, language: str) -> list[Segment]:
        model = self._load_model()
        segments_iter, _info = model.transcribe(
            str(audio_path),
            language=language,
            word_timestamps=self.word_timestamps,
            vad_filter=True,
        )
        segments: list[Segment] = []
        for index, item in enumerate(segments_iter, start=1):
            text = normalize_subtitle_text(str(item.text))
            if not text:
                continue
            start = float(item.start)
            end = float(item.end)
            segments.append(
                Segment(
                    id=index,
                    start=start,
                    end=end,
                    duration=max(0.0, end - start),
                    source_text=text,
                )
            )
        return segments
