from __future__ import annotations

from pathlib import Path

import edge_tts

from app.audio.convert import convert_audio_to_wav
from app.tts.base import TTSBackend


class EdgeTTSBackend(TTSBackend):
    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        sample_rate: int = 24000,
    ):
        self.voice = voice
        self.rate = rate
        self.volume = volume
        self.pitch = pitch
        self.sample_rate = sample_rate

    async def synthesize(
        self,
        text: str,
        out_path: Path,
        speaker: str = "default",
        ref_audio: str | None = None,
        target_duration: float | None = None,
    ) -> Path:
        del speaker, ref_audio, target_duration
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_mp3 = out_path.with_suffix(".mp3")
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            volume=self.volume,
            pitch=self.pitch,
        )
        await communicate.save(str(tmp_mp3))
        convert_audio_to_wav(tmp_mp3, out_path, sample_rate=self.sample_rate)
        tmp_mp3.unlink(missing_ok=True)
        return out_path
