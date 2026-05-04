from app.schemas import Segment
from app.translator.openai_compatible import OpenAICompatibleTranslator


class FakeTranslator(OpenAICompatibleTranslator):
    def __init__(self):
        super().__init__("https://example.com", "key", "model")
        self.calls = 0

    async def _chat(self, messages):
        self.calls += 1
        prompt = messages[-1]["content"]
        if "生成全片翻译上下文" in prompt:
            return '{"summary":"GPU 教程","terms":[{"source":"GPU","target":"GPU"}]}'
        if "原文和初稿" in prompt:
            return '[{"id":1,"zh_text":"最终中文","short_zh_text":"最终中文","estimated_seconds":0.8,"notes":""}]'
        return '[{"id":1,"zh_text":"初稿中文","short_zh_text":"短中文","estimated_seconds":1.4,"notes":"long"}]'


async def test_translator_generates_context_and_reflects():
    translator = FakeTranslator()
    segments = [Segment(id=1, start=0, end=1, duration=1, source_text="GPU tutorial", max_zh_chars=6)]

    summary, terms = await translator.prepare_context(segments, ["CUDA"])
    translated = await translator.translate_segments(segments, summary=summary, terms=terms, reflect_adapt=True)

    assert summary == "GPU 教程"
    assert {"source": "GPU", "target": "GPU"} in terms
    assert translated[0].target_text == "最终中文"
    assert translated[0].short_target_text == "最终中文"
    assert translated[0].estimated_seconds == 0.8
    assert translator.calls == 3
