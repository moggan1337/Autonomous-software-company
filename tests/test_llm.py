"""The LLM layer must degrade cleanly to simulation without a key."""
from company.config import Settings
from company.llm import LLMClient


def _sim_settings() -> Settings:
    return Settings(
        api_key=None,
        model="claude-opus-4-8",
        effort="high",
        db_path=":memory:",
        force_simulate=True,
    )


def test_no_key_is_unavailable():
    llm = LLMClient(_sim_settings())
    assert llm.available is False


def test_generate_returns_none_without_client():
    llm = LLMClient(_sim_settings())
    assert llm.generate("system", "user") is None
    assert llm.generate_json("system", "user", {"type": "object"}) is None


def test_forced_simulate_even_with_key():
    settings = Settings(
        api_key="sk-not-real",
        model="claude-opus-4-8",
        effort="high",
        db_path=":memory:",
        force_simulate=True,
    )
    assert settings.simulate is True
    assert LLMClient(settings).available is False
