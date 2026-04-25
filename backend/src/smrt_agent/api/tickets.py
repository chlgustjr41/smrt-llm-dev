"""Bug tickets API: list .smrt/tickets/ files for a project."""
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project

router = APIRouter(prefix="/projects", tags=["tickets"])


@router.get("/{project_id}/tickets")
async def list_tickets(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    tickets_dir = Path(project.canonical_path) / ".smrt" / "tickets"
    if not tickets_dir.exists():
        return []

    results = []
    for path in sorted(tickets_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = lines[0].lstrip("#").strip() if lines else path.stem
        results.append({
            "id": path.stem,
            "title": title,
            "content": content,
        })
    return results
