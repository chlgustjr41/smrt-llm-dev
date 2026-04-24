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
