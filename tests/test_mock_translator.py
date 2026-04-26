from app.schemas import Segment


class MockTranslator:
    async def translate_segments(self, segments):
        for segment in segments:
            segment.target_text = f"中文翻译：{segment.source_text}"
        return segments


async def test_mock_translator():
    segments = [Segment(id=1, start=0, end=1, duration=1, source_text="Hello")]
    translated = await MockTranslator().translate_segments(segments)
    assert translated[0].target_text == "中文翻译：Hello"
