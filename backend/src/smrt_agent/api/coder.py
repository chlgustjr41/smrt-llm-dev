"""Coder agent status endpoint."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import QASession

router = APIRouter(prefix="/projects", tags=["coder"])


@router.get("/{project_id}/coder/status")
async def get_coder_status(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return the current Coder agent status for a project.

    Looks for any QASession that has no completed_at (still running).
    The session's ticket_id column holds the bug ticket currently being
    worked on, if the Coder is mid-fix.
    """
    result = await db.execute(
        select(QASession)
        .where(QASession.project_id == project_id)
        .where(QASession.completed_at.is_(None))
        .order_by(QASession.started_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()
    if session:
        return {
            "idle": False,
            "session_id": session.session_id,
            "status": session.status,
            "ticket_id": session.ticket_id,
        }
    return {"idle": True, "session_id": None, "status": None, "ticket_id": None}
