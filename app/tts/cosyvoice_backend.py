from __future__ import annotations

from pathlib import Path

import httpx

from app.audio.convert import convert_audio_to_wav
from app.tts.base import TTSBackend


class CosyVoiceHTTPBackend(TTSBackend):
    def __init__(self, endpoint: str, sample_rate: int = 24000, timeout_seconds: int = 120):
        self.endpoint = endpoint
        self.sample_rate = sample_rate
        self.timeout_seconds = timeout_seconds

    async def synthesize(
        self,
        text: str,
        out_path: Path,
        speaker: str = "default",
        ref_audio: str | None = None,
        target_duration: float | None = None,
    ) -> Path:
        del target_duration
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "text": text,
            "speaker": speaker,
            "ref_audio": ref_audio,
            "sample_rate": self.sample_rate,
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.endpoint, json=payload)
            response.raise_for_status()
        tmp_wav = out_path.with_suffix(".raw.wav")
        tmp_wav.write_bytes(response.content)
        convert_audio_to_wav(tmp_wav, out_path, sample_rate=self.sample_rate)
        tmp_wav.unlink(missing_ok=True)
        return out_path
