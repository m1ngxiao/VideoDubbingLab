from app.audio.concat import build_timeline_audio
from app.audio.duration import get_audio_duration
from app.audio.silence import write_silence_wav
from app.schemas import Segment


def test_timeline_uses_bounded_shift_instead_of_unbounded_drift(tmp_path):
    first = write_silence_wav(tmp_path / "first.wav", 2.0, 24000)
    second = write_silence_wav(tmp_path / "second.wav", 1.0, 24000)
    segments = [
        Segment(id=1, start=0.0, end=1.0, duration=1.0, source_text="one", aligned_audio_path=str(first)),
        Segment(id=2, start=1.0, end=2.0, duration=1.0, source_text="two", aligned_audio_path=str(second)),
    ]

    output = build_timeline_audio(
        segments,
        tmp_path / "timeline.wav",
        2.0,
        24000,
        min_gap_ms=100,
        max_shift_ms=250,
    )

    assert segments[0].start == 0.0
    assert segments[0].placed_start == 0.0
    assert segments[0].placed_end == 2.0
    assert segments[1].start == 1.0
    assert segments[1].shift_ms <= 250
    assert segments[1].placed_start == 1.25
    assert any("Overlap not fully resolved" in warning for warning in segments[1].warnings)
    assert abs(get_audio_duration(output) - 2.0) < 0.02
