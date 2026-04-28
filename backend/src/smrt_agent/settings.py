from pathlib import Path

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


def _find_env_file() -> Path | None:
    """Walk up from this file's location to find the nearest .env file.

    When running locally the source tree sits inside the repo root which has .env.
    When running inside Docker the source is at /app/src/... with no .env nearby,
    so this returns None and dotenv_settings contributes nothing — Docker's env_file:
    injection (which lands as ordinary OS env vars) takes over instead.
    """
    for parent in Path(__file__).resolve().parents:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return None


def _find_config_file() -> Path | None:
    """Locate the backend-level `.config` file holding agent defaults.

    Layout is fixed: settings.py lives at backend/src/smrt_agent/settings.py,
    so backend/.config is parents[2]/.config. We resolve it explicitly rather
    than walking up so we never accidentally pick up an unrelated `.config`
    file in some other parent directory.

    Returns None inside Docker (the file isn't part of the image), in which
    case the values come from env vars injected via docker-compose's env_file:.
    """
    parents = Path(__file__).resolve().parents
    if len(parents) < 3:
        return None
    candidate = parents[2] / ".config"
    return candidate if candidate.exists() else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # env_file is intentionally not set here; it is resolved dynamically in
        # settings_customise_sources so that tests can monkeypatch _find_env_file.
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required when not using local LLM
    anthropic_api_key: str = Field(default="", description="Anthropic API key")

    # Local LLM (LM Studio or any OpenAI-compatible server)
    # Set USE_LOCAL_LLM=true to prefer local over Anthropic regardless of whether
    # a key is present (most local servers don't require auth).
    use_local_llm: bool = Field(default=False, alias="use_local_llm")
    local_llm_api_key: str = Field(default="", alias="local_llm_api_key")
    local_llm_base_url: str = Field(default="http://localhost:1234/v1", alias="local_llm_base_url")
    local_llm_model: str = Field(default="local-model", alias="local_llm_model")

    # Bind address
    bind_host: str = Field(default="127.0.0.1", alias="smrt_bind_host")
    backend_port: int = Field(default=8000, alias="smrt_backend_port")
    frontend_port: int = Field(default=5173, alias="smrt_frontend_port")

    # Budget guardrails
    budget_per_run_usd: float = Field(default=1.50, alias="smrt_budget_per_run_usd")
    budget_per_ticket_usd: float = Field(default=0.50, alias="smrt_budget_per_ticket_usd")
    budget_per_day_usd: float = Field(default=10.00, alias="smrt_budget_per_day_usd")

    # Models — sourced from backend/.config; root .env or OS env can override.
    model_reviewer: str = Field(default="claude-haiku-4-5-20251001", alias="smrt_model_reviewer")
    model_qa: str = Field(default="claude-haiku-4-5-20251001", alias="smrt_model_qa")
    model_coder: str = Field(default="claude-haiku-4-5-20251001", alias="smrt_model_coder")

    # Loop caps — sourced from backend/.config; root .env or OS env can override.
    max_fix_attempts: int = Field(default=5, alias="smrt_max_fix_attempts")
    max_questions_per_attempt: int = Field(default=1, alias="smrt_max_questions_per_attempt")

    # Path allowlist (comma-separated)
    project_root_allowlist: str = Field(default="", alias="smrt_project_root_allowlist")

    # UI defaults for new projects — sourced from backend/.config; .env / OS env can override.
    thought_process_mode: bool = Field(default=False, alias="smrt_thought_process_mode")

    # Observability
    log_level: str = Field(default="INFO", alias="smrt_log_level")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Layered config (highest priority first in the returned tuple):
        #   init kwargs > OS env > root .env > backend/.config > file_secret
        #
        # Why this order:
        #   - backend/.config holds the agent defaults the team commits via
        #     .config.example. It's the floor.
        #   - root .env can override per-developer (e.g. a contributor temporarily
        #     pointing SMRT_MODEL_QA at a different model).
        #   - OS env wins last so docker-compose env_file: and explicit exports
        #     always take precedence (Docker doesn't ship .env / .config in the
        #     image; env vars are how values arrive there).
        #
        # Both file paths are resolved dynamically so tests can monkeypatch them.
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings]

        env_file = _find_env_file()
        if env_file:
            sources.append(
                DotEnvSettingsSource(
                    settings_cls,
                    env_file=str(env_file),
                    env_file_encoding="utf-8",
                    case_sensitive=False,
                )
            )

        config_file = _find_config_file()
        if config_file:
            sources.append(
                DotEnvSettingsSource(
                    settings_cls,
                    env_file=str(config_file),
                    env_file_encoding="utf-8",
                    case_sensitive=False,
                )
            )

        sources.append(file_secret_settings)
        return tuple(sources)

    @property
    def allowed_project_roots(self) -> list[str]:
        return [p.strip() for p in self.project_root_allowlist.split(",") if p.strip()]
