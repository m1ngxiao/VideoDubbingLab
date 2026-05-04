from app.subtitle.parser import parse_srt, parse_subtitle


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


def test_parse_vtt_and_clean_autocaption_artifacts(tmp_path):
    path = tmp_path / "demo.vtt"
    path.write_text(
        """WEBVTT

00:00:01.000 --> 00:00:02.000 align:start
<v Speaker>  >> Hello   CUDA </v>

00:00:02.000 --> 00:00:03.000
[Music]
""",
        encoding="utf-8",
    )

    segments = parse_subtitle(path)

    assert len(segments) == 1
    assert segments[0].source_text == "Hello CUDA"
