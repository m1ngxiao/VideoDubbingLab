from app.tts.cache import tts_cache_key


def test_tts_cache_key_changes_with_voice_and_prompt():
    base = tts_cache_key("你好", "voice-a", "speaker", "ref", "model", "prompt")
    same = tts_cache_key("你好", "voice-a", "speaker", "ref", "model", "prompt")
    different_voice = tts_cache_key("你好", "voice-b", "speaker", "ref", "model", "prompt")
    different_prompt = tts_cache_key("你好", "voice-a", "speaker", "ref", "model", "other")

    assert base == same
    assert base != different_voice
    assert base != different_prompt
