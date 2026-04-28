"""Coder agent status endpoint."""
import json
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project, QASession
from smrt_agent.settings import Settings

router = APIRouter(prefix="/projects", tags=["coder"])


@router.get("/{project_id}/coder/status")
async def get_coder_status(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return the current Coder agent status for a project, including active model."""
    result = await db.execute(
        select(QASession)
        .where(QASession.project_id == project_id)
        .where(QASession.completed_at.is_(None))
        .order_by(QASession.started_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if session:
        # Read model from project config for display; falls back to global settings
        project = await db.get(Project, project_id)
        settings = Settings()
        try:
            cfg = json.loads(project.config or "{}") if project else {}
        except Exception:
            cfg = {}
        model = cfg.get("coder_model", settings.model_coder)
        return {
            "idle": False,
            "session_id": session.session_id,
            "status": session.status,
            "ticket_id": session.ticket_id,
            "model": model,
        }
    return {"idle": True, "session_id": None, "status": None, "ticket_id": None, "model": None}
