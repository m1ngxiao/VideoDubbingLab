from app.config import load_config
from app.pipeline.stages import build_tts_backend
from app.tts.cosyvoice_backend import CosyVoiceHTTPBackend


def test_cosyvoice3_rl_config_builds_http_backend():
    config = load_config("configs/cosyvoice3_rl.yaml")
    assert config.llm.base_url == "https://api.deepseek.com"
    assert config.llm.model == "deepseek-v4-flash"
    backend = build_tts_backend(config)
    assert isinstance(backend, CosyVoiceHTTPBackend)
    assert backend.endpoint == "http://127.0.0.1:9880/tts"
    assert backend.prompt_text
