from datetime import datetime
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    path: str


class ProjectOut(BaseModel):
    id: int
    name: str
    canonical_path: str
    created_at: datetime
    config: str = '{}'

    model_config = {"from_attributes": True}


class ProjectConfig(BaseModel):
    reviewer_model: str = "claude-haiku-4-5-20251001"
    qa_model: str = "claude-haiku-4-5-20251001"
    coder_model: str = "claude-haiku-4-5-20251001"
    max_fix_attempts: int = 5
    max_questions_per_attempt: int = 1
    scheduler_cadence: str = "daily_0300"
    thought_process_mode: bool = False
    use_local_llm: bool = False


class ProjectConfigPatch(BaseModel):
    reviewer_model: str | None = None
    qa_model: str | None = None
    coder_model: str | None = None
    max_fix_attempts: int | None = None
    max_questions_per_attempt: int | None = None
    scheduler_cadence: str | None = None
    thought_process_mode: bool | None = None
    use_local_llm: bool | None = None


class RunCreatedResponse(BaseModel):
    run_id: str
    status: str


class AgentRunOut(BaseModel):
    id: int
    run_id: str
    project_id: int
    status: str
    total_input_tokens: int
    total_output_tokens: int
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}
