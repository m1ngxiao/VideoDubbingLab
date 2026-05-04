from app.schemas import Segment
from app.translator.openai_compatible import OpenAICompatibleTranslator


class DurationFakeTranslator(OpenAICompatibleTranslator):
    def __init__(self):
        super().__init__("https://example.com", "key", "model")

    async def _chat(self, messages):
        return (
            '[{"id":1,"zh_text":"这是一个太长的中文翻译",'
            '"short_zh_text":"短译文","estimated_seconds":2.0,"notes":"too long"}]'
        )


async def test_duration_aware_translation_uses_short_text_when_estimate_exceeds_window():
    translator = DurationFakeTranslator()
    segments = [Segment(id=1, start=0, end=1, duration=1, source_text="hello", max_zh_chars=4)]

    translated = await translator.translate_segments(segments, reflect_adapt=False)

    assert translated[0].target_text == "短译文"
    assert translated[0].short_target_text == "短译文"
    assert translated[0].estimated_seconds == 2.0
    assert "used_short_zh_text_for_duration" in translated[0].translation_notes
