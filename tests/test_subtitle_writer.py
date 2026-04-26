from app.schemas import Segment
from app.subtitle.writer import write_srt


def test_write_srt_prefers_target_text(tmp_path):
    path = tmp_path / "zh.srt"
    write_srt(
        [
            Segment(id=1, start=1.0, end=3.5, duration=2.5, source_text="Hello", target_text="你好"),
            Segment(id=2, start=4.0, end=5.0, duration=1.0, source_text="Fallback"),
        ],
        path,
    )
    text = path.read_text(encoding="utf-8")
    assert "00:00:01,000 --> 00:00:03,500" in text
    assert "你好" in text
    assert "Fallback" in text
