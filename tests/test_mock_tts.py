from pathlib import Path

from app.audio.duration import get_audio_duration
from app.audio.silence import write_silence_wav
from app.tts.base import TTSBackend


class MockTTS(TTSBackend):
    async def synthesize(
        self,
        text: str,
        out_path: Path,
        speaker: str = "default",
        ref_audio: str | None = None,
        target_duration: float | None = None,
    ) -> Path:
        del text, speaker, ref_audio
        return write_silence_wav(out_path, target_duration or 0.5, 24000)


async def test_mock_tts(tmp_path):
    out_path = await MockTTS().synthesize("你好", tmp_path / "tts.wav", target_duration=0.75)
    assert out_path.exists()
    assert abs(get_audio_duration(out_path) - 0.75) < 0.02
