from app.utils.timecode import format_srt_time, parse_srt_time


def test_parse_srt_time():
    assert parse_srt_time("00:00:01,250") == 1.25
    assert parse_srt_time("01:02:03,004") == 3723.004


def test_format_srt_time():
    assert format_srt_time(1.25) == "00:00:01,250"
    assert format_srt_time(3723.004) == "01:02:03,004"
