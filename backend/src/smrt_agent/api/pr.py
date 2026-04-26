"""PR surface API: list pending PRs, accept or reject a fix."""
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project
from smrt_agent.agents.qa.tools import append_bugs_resolved
from smrt_agent.knowledge import append_lesson, append_rejection

router = APIRouter(prefix="/projects", tags=["pr"])


class RejectBody(BaseModel):
    reason: str = "No reason given"


def _get_ticket_title(project_path: Path, ticket_id: str) -> str:
    ticket_path = project_path / ".smrt" / "tickets" / f"{ticket_id}.md"
    if ticket_path.exists():
        lines = ticket_path.read_text(encoding="utf-8").splitlines()
        return lines[0].lstrip("#").strip() if lines else ticket_id
    return ticket_id


def _read_pending_prs(project_path: Path) -> list[dict]:
    pr_log = project_path / ".smrt" / "pending-prs.jsonl"
    if not pr_log.exists():
        return []
    entries = []
    for line in pr_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def _write_pending_prs(project_path: Path, entries: list[dict]) -> None:
    pr_log = project_path / ".smrt" / "pending-prs.jsonl"
    pr_log.parent.mkdir(parents=True, exist_ok=True)
    with pr_log.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


@router.get("/{project_id}/pr/pending")
async def list_pending_prs(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _read_pending_prs(Path(project.canonical_path))


@router.post("/{project_id}/pr/{ticket_id}/accept", status_code=200)
async def accept_pr(
    project_id: int,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project_path = Path(project.canonical_path)

    entries = _read_pending_prs(project_path)
    remaining = [e for e in entries if e.get("ticket_id") != ticket_id]
    if len(remaining) == len(entries):
        raise HTTPException(status_code=404, detail="No pending PR for this ticket")
    _write_pending_prs(project_path, remaining)

    append_bugs_resolved(project_path, ticket_id, "Accepted via PR surface review.")
    ticket_title = _get_ticket_title(project_path, ticket_id)
    append_lesson(project_path, ticket_id, "accepted", f"{ticket_title} — fix passed all tests.")
    return {"ticket_id": ticket_id, "status": "accepted"}


@router.post("/{project_id}/pr/{ticket_id}/reject", status_code=200)
async def reject_pr(
    project_id: int,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    body: RejectBody = RejectBody(),
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project_path = Path(project.canonical_path)

    entries = _read_pending_prs(project_path)
    remaining = [e for e in entries if e.get("ticket_id") != ticket_id]
    if len(remaining) == len(entries):
        raise HTTPException(status_code=404, detail="No pending PR for this ticket")
    _write_pending_prs(project_path, remaining)
    ticket_title = _get_ticket_title(project_path, ticket_id)
    reason = body.reason
    append_lesson(project_path, ticket_id, "rejected", f"{ticket_title} — rejected: {reason}")
    append_rejection(project_path, ticket_id, ticket_title, reason)
    return {"ticket_id": ticket_id, "status": "rejected"}
