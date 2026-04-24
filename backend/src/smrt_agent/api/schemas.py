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

    model_config = {"from_attributes": True}


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
