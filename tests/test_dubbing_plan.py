from app.audio.dubbing_plan import estimate_speech_duration, plan_dubbing_segments
from app.config import AudioAlignConfig
from app.schemas import Segment


def test_estimate_speech_duration_counts_chinese_text():
    assert estimate_speech_duration("这是一个中文配音测试。", 4.0) > 1.0


def test_dubbing_plan_merges_fast_segments():
    segments = [
        Segment(id=1, start=0, end=1, duration=1, source_text="a", target_text="这是一个非常长的中文配音句子"),
        Segment(id=2, start=1.2, end=2.2, duration=1, source_text="b", target_text="需要和下一句合并"),
    ]

    result = plan_dubbing_segments(
        segments,
        AudioAlignConfig(speech_chars_per_second=3.0, planning_tolerance=1.5, max_merge_segments=3),
    )

    assert len(result) == 1
    assert result[0].id == 1
    assert "合并" in result[0].target_text
