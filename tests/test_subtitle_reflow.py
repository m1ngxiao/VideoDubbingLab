from app.config import SubtitleConfig
from app.schemas import Segment
from app.subtitle.reflow import reflow_segments


def test_reflow_splits_long_subtitle_and_renumbers():
    segments = [
        Segment(
            id=7,
            start=0,
            end=8,
            duration=8,
            source_text="This is a long sentence. It should become a separate subtitle. Another sentence follows.",
        )
    ]

    result = reflow_segments(segments, SubtitleConfig(max_segment_chars=45))

    assert len(result) >= 2
    assert [segment.id for segment in result] == list(range(1, len(result) + 1))
    assert result[0].start == 0
    assert result[-1].end == 8


def test_reflow_merges_continuation_lines():
    segments = [
        Segment(id=1, start=0, end=0.4, duration=0.4, source_text="because"),
        Segment(id=2, start=0.5, end=1.5, duration=1.0, source_text="the GPU hides memory latency."),
    ]

    result = reflow_segments(segments, SubtitleConfig(min_segment_duration=0.8, max_merge_gap=0.2))

    assert len(result) == 1
    assert "GPU hides" in result[0].source_text
