import pytest
from smrt_agent.settings import Settings


def test_settings_loads_from_env(monkeypatch):
    # Simulate Docker/CI: no .env or .config file, values come from env vars only.
    monkeypatch.setattr("smrt_agent.settings._find_env_file", lambda: None)
    monkeypatch.setattr("smrt_agent.settings._find_config_file", lambda: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("SMRT_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("SMRT_BACKEND_PORT", "8000")

    s = Settings()

    assert s.anthropic_api_key == "sk-ant-test-key"
    assert s.bind_host == "127.0.0.1"
    assert s.backend_port == 8000


def test_settings_defaults_without_overrides(monkeypatch):
    monkeypatch.setattr("smrt_agent.settings._find_env_file", lambda: None)
    monkeypatch.setattr("smrt_agent.settings._find_config_file", lambda: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-only-required")
    monkeypatch.delenv("SMRT_BIND_HOST", raising=False)
    monkeypatch.delenv("SMRT_MAX_FIX_ATTEMPTS", raising=False)

    s = Settings()
    assert s.bind_host == "127.0.0.1"
    assert s.backend_port == 8000
    assert s.budget_per_run_usd == 1.50
    assert s.max_fix_attempts == 5


def test_settings_optional_api_key(monkeypatch):
    # ANTHROPIC_API_KEY is now optional — local LLM key may be used instead.
    monkeypatch.setattr("smrt_agent.settings._find_env_file", lambda: None)
    monkeypatch.setattr("smrt_agent.settings._find_config_file", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings()
    assert s.anthropic_api_key == ""
    assert s.use_local_llm is False  # no local key set either


def test_settings_local_llm(monkeypatch):
    # USE_LOCAL_LLM=true is the switch; no API key required for LM Studio.
    monkeypatch.setattr("smrt_agent.settings._find_env_file", lambda: None)
    monkeypatch.setattr("smrt_agent.settings._find_config_file", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("USE_LOCAL_LLM", "true")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "mistral-7b")

    s = Settings()
    assert s.use_local_llm is True
    assert s.local_llm_api_key == ""   # no key needed
    assert s.local_llm_base_url == "http://localhost:1234/v1"
    assert s.local_llm_model == "mistral-7b"


def test_config_file_supplies_agent_defaults(monkeypatch, tmp_path):
    """backend/.config provides values when neither env vars nor .env override."""
    config_file = tmp_path / ".config"
    config_file.write_text(
        "SMRT_MODEL_REVIEWER=claude-opus-4-7\n"
        "SMRT_MODEL_QA=claude-sonnet-4-6\n"
        "SMRT_MODEL_CODER=claude-haiku-4-5-20251001\n"
        "SMRT_MAX_FIX_ATTEMPTS=7\n"
        "SMRT_MAX_QUESTIONS_PER_ATTEMPT=4\n"
        "SMRT_THOUGHT_PROCESS_MODE=true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("smrt_agent.settings._find_env_file", lambda: None)
    monkeypatch.setattr("smrt_agent.settings._find_config_file", lambda: config_file)
    # Clear any host env that would shadow the file.
    for key in (
        "SMRT_MODEL_REVIEWER", "SMRT_MODEL_QA", "SMRT_MODEL_CODER",
        "SMRT_MAX_FIX_ATTEMPTS", "SMRT_MAX_QUESTIONS_PER_ATTEMPT",
        "SMRT_THOUGHT_PROCESS_MODE",
    ):
        monkeypatch.delenv(key, raising=False)

    s = Settings()
    assert s.model_reviewer == "claude-opus-4-7"
    assert s.model_qa == "claude-sonnet-4-6"
    assert s.model_coder == "claude-haiku-4-5-20251001"
    assert s.max_fix_attempts == 7
    assert s.max_questions_per_attempt == 4
    assert s.thought_process_mode is True


def test_env_file_overrides_config_file(monkeypatch, tmp_path):
    """Root .env takes precedence over backend/.config — local override wins."""
    config_file = tmp_path / ".config"
    config_file.write_text(
        "SMRT_MODEL_QA=claude-haiku-4-5-20251001\n"
        "SMRT_MAX_FIX_ATTEMPTS=3\n",
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SMRT_MODEL_QA=claude-opus-4-7\n",  # overrides the .config value
        encoding="utf-8",
    )
    monkeypatch.setattr("smrt_agent.settings._find_env_file", lambda: env_file)
    monkeypatch.setattr("smrt_agent.settings._find_config_file", lambda: config_file)
    for key in ("SMRT_MODEL_QA", "SMRT_MAX_FIX_ATTEMPTS"):
        monkeypatch.delenv(key, raising=False)

    s = Settings()
    assert s.model_qa == "claude-opus-4-7"          # from .env
    assert s.max_fix_attempts == 3                  # only in .config


def test_os_env_overrides_both_files(monkeypatch, tmp_path):
    """OS env (e.g. docker-compose env_file injection) wins over both files."""
    config_file = tmp_path / ".config"
    config_file.write_text("SMRT_MODEL_CODER=from-config\n", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("SMRT_MODEL_CODER=from-env\n", encoding="utf-8")
    monkeypatch.setattr("smrt_agent.settings._find_env_file", lambda: env_file)
    monkeypatch.setattr("smrt_agent.settings._find_config_file", lambda: config_file)
    monkeypatch.setenv("SMRT_MODEL_CODER", "from-os-env")

    s = Settings()
    assert s.model_coder == "from-os-env"
