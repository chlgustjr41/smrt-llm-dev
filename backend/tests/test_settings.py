import pytest
from smrt_agent.settings import Settings


def test_settings_loads_from_env(monkeypatch):
    # Simulate Docker/CI: no .env file, values come from env vars only.
    monkeypatch.setattr("smrt_agent.settings._find_env_file", lambda: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("SMRT_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("SMRT_BACKEND_PORT", "8000")

    s = Settings()

    assert s.anthropic_api_key == "sk-ant-test-key"
    assert s.bind_host == "127.0.0.1"
    assert s.backend_port == 8000


def test_settings_defaults_without_overrides(monkeypatch):
    monkeypatch.setattr("smrt_agent.settings._find_env_file", lambda: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-only-required")
    monkeypatch.delenv("SMRT_BIND_HOST", raising=False)

    s = Settings()
    assert s.bind_host == "127.0.0.1"
    assert s.backend_port == 8000
    assert s.budget_per_run_usd == 1.50
    assert s.max_fix_attempts == 5


def test_settings_optional_api_key(monkeypatch):
    # ANTHROPIC_API_KEY is now optional — local LLM key may be used instead.
    monkeypatch.setattr("smrt_agent.settings._find_env_file", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings()
    assert s.anthropic_api_key == ""
    assert s.use_local_llm is False  # no local key set either


def test_settings_local_llm(monkeypatch):
    # USE_LOCAL_LLM=true is the switch; no API key required for LM Studio.
    monkeypatch.setattr("smrt_agent.settings._find_env_file", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("USE_LOCAL_LLM", "true")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "mistral-7b")

    s = Settings()
    assert s.use_local_llm is True
    assert s.local_llm_api_key == ""   # no key needed
    assert s.local_llm_base_url == "http://localhost:1234/v1"
    assert s.local_llm_model == "mistral-7b"
