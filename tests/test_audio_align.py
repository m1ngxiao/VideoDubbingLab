import soundfile as sf

from app.audio.align import align_segment_audio
from app.audio.duration import get_audio_duration
from app.audio.silence import write_silence_wav


def test_short_audio_is_padded(tmp_path):
    source = write_silence_wav(tmp_path / "short.wav", 0.5, 24000)
    output = tmp_path / "aligned.wav"
    result = align_segment_audio(source, output, 1.0, 24000, 1.25, 80)
    assert result.overflow is False
    assert abs(get_audio_duration(output) - 1.0) < 0.02


def test_slightly_long_audio_is_sped_up(tmp_path):
    source = write_silence_wav(tmp_path / "long.wav", 1.1, 24000)
    output = tmp_path / "aligned.wav"
    result = align_segment_audio(source, output, 1.0, 24000, 1.25, 80)
    assert result.overflow is False
    assert result.speed_ratio > 1
    assert abs(get_audio_duration(output) - 1.0) < 0.03


def test_severely_long_audio_warns(tmp_path):
    source = write_silence_wav(tmp_path / "too_long.wav", 2.0, 24000)
    output = tmp_path / "aligned.wav"
    result = align_segment_audio(source, output, 1.0, 24000, 1.25, 80)
    assert result.overflow is True
    assert result.warnings
    frames, sample_rate = sf.read(output)
    assert sample_rate == 24000
    assert len(frames) > 24000
