from app.config import load_config


def test_deepseek_v4_flash_config():
    config = load_config("configs/deepseek_v4_flash.yaml")
    assert config.llm.provider == "openai_compatible"
    assert config.llm.base_url == "https://api.deepseek.com"
    assert config.llm.model == "deepseek-v4-flash"
