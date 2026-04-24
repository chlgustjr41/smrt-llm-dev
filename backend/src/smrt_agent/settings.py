from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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

    # Models
    model_reviewer: str = Field(default="claude-opus-4-7", alias="smrt_model_reviewer")
    model_qa: str = Field(default="claude-sonnet-4-6", alias="smrt_model_qa")
    model_coder: str = Field(default="claude-sonnet-4-6", alias="smrt_model_coder")

    # Loop caps
    max_fix_attempts: int = Field(default=5, alias="smrt_max_fix_attempts")
    max_questions_per_attempt: int = Field(default=1, alias="smrt_max_questions_per_attempt")

    # Path allowlist (comma-separated)
    project_root_allowlist: str = Field(default="", alias="smrt_project_root_allowlist")

    # Observability
    log_level: str = Field(default="INFO", alias="smrt_log_level")

    @property
    def allowed_project_roots(self) -> list[str]:
        return [p.strip() for p in self.project_root_allowlist.split(",") if p.strip()]
