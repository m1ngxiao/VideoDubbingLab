from app.audio.concat import build_timeline_audio
from app.audio.duration import get_audio_duration
from app.audio.silence import write_silence_wav
from app.schemas import Segment


def test_timeline_shifts_later_segments_instead_of_mixing(tmp_path):
    first = write_silence_wav(tmp_path / "first.wav", 2.0, 24000)
    second = write_silence_wav(tmp_path / "second.wav", 1.0, 24000)
    segments = [
        Segment(id=1, start=0.0, end=1.0, duration=1.0, source_text="one", aligned_audio_path=str(first)),
        Segment(id=2, start=1.0, end=2.0, duration=1.0, source_text="two", aligned_audio_path=str(second)),
    ]

    output = build_timeline_audio(segments, tmp_path / "timeline.wav", 2.0, 24000, min_gap_ms=100)

    assert segments[0].start == 0.0
    assert segments[0].end > 1.9
    assert segments[1].start >= segments[0].end + 0.09
    assert any("avoid dubbed audio overlap" in warning for warning in segments[1].warnings)
    assert get_audio_duration(output) >= segments[1].end - 0.02
