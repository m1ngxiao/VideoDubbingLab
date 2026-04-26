from app.subtitle.parser import parse_srt


def test_parse_srt(tmp_path):
    path = tmp_path / "demo.srt"
    path.write_text(
        """1
00:00:01,000 --> 00:00:03,500
<i>Hello</i>
everyone.

2
00:00:04,000 --> 00:00:05,000
CUDA  warp
""",
        encoding="utf-8",
    )
    segments = parse_srt(path)
    assert len(segments) == 2
    assert segments[0].id == 1
    assert segments[0].start == 1.0
    assert segments[0].duration == 2.5
    assert segments[0].source_text == "Hello everyone."
    assert segments[1].source_text == "CUDA warp"
