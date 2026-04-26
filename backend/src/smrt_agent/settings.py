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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # env_file is intentionally not set here; it is resolved dynamically in
        # settings_customise_sources so that tests can monkeypatch _find_env_file.
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Required
    anthropic_api_key: str = Field(..., description="Anthropic API key")

    # Bind address
    bind_host: str = Field(default="127.0.0.1", alias="smrt_bind_host")
    backend_port: int = Field(default=8000, alias="smrt_backend_port")
    frontend_port: int = Field(default=5173, alias="smrt_frontend_port")

    # Budget guardrails
    budget_per_run_usd: float = Field(default=1.50, alias="smrt_budget_per_run_usd")
    budget_per_day_usd: float = Field(default=10.00, alias="smrt_budget_per_day_usd")

    # Models (env overrides these; haiku is the dev default)
    model_reviewer: str = Field(default="claude-haiku-4-5-20251001", alias="smrt_model_reviewer")
    model_qa: str = Field(default="claude-haiku-4-5-20251001", alias="smrt_model_qa")
    model_coder: str = Field(default="claude-haiku-4-5-20251001", alias="smrt_model_coder")

    # Loop caps
    max_fix_attempts: int = Field(default=5, alias="smrt_max_fix_attempts")
    max_questions_per_attempt: int = Field(default=1, alias="smrt_max_questions_per_attempt")

    # Path allowlist (comma-separated)
    project_root_allowlist: str = Field(default="", alias="smrt_project_root_allowlist")

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
        # Resolve the .env file dynamically so tests can monkeypatch _find_env_file.
        # Dotenv beats OS env vars: ANTHROPIC_API_KEY in the project's .env is always
        # used, even if the host shell has a different key exported (e.g. another project).
        # In Docker _find_env_file() returns None → dotenv source contributes nothing →
        # Docker's env_file: injection (regular OS env vars in the container) applies.
        env_file = _find_env_file()
        if env_file:
            fresh_dotenv = DotEnvSettingsSource(
                settings_cls,
                env_file=str(env_file),
                env_file_encoding="utf-8",
                case_sensitive=False,
            )
            return (init_settings, fresh_dotenv, env_settings, file_secret_settings)
        return (init_settings, env_settings, file_secret_settings)

    @property
    def allowed_project_roots(self) -> list[str]:
        return [p.strip() for p in self.project_root_allowlist.split(",") if p.strip()]
