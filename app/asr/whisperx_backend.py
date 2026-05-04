from __future__ import annotations

import asyncio
from pathlib import Path

from app.asr.base import ASRBackend
from app.schemas import Segment
from app.subtitle.normalize import normalize_subtitle_text


class WhisperXBackend(ASRBackend):
    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "auto",
        word_timestamps: bool = False,
    ):
        self.model_size = model_size
        self.device = "cuda" if device == "auto" else device
        self.compute_type = "float16" if compute_type == "auto" else compute_type
        self.word_timestamps = word_timestamps
        self._model = None

    async def transcribe(self, audio_path: str | Path, language: str = "en") -> list[Segment]:
        return await asyncio.to_thread(self._transcribe_sync, Path(audio_path), language)

    def _load_model(self):
        if self._model is None:
            try:
                import whisperx  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "ASR backend 'whisperx' requires optional package whisperx. "
                    "Install it on the GPU/ASR worker or disable asr.enabled."
                ) from exc
            self._model = whisperx.load_model(self.model_size, self.device, compute_type=self.compute_type)
        return self._model

    def _transcribe_sync(self, audio_path: Path, language: str) -> list[Segment]:
        try:
            import whisperx  # type: ignore
        except ImportError as exc:
            raise RuntimeError("whisperx is not installed") from exc
        model = self._load_model()
        audio = whisperx.load_audio(str(audio_path))
        result = model.transcribe(audio, language=language)
        raw_segments = result.get("segments", [])
        segments: list[Segment] = []
        for index, item in enumerate(raw_segments, start=1):
            text = normalize_subtitle_text(str(item.get("text") or ""))
            if not text:
                continue
            start = float(item.get("start") or 0.0)
            end = float(item.get("end") or start)
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
