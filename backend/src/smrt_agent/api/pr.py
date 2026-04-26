"""PR surface API: list pending PRs, accept or reject a fix."""
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project
from smrt_agent.agents.qa.tools import append_bugs_resolved

router = APIRouter(prefix="/projects", tags=["pr"])


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
    return {"ticket_id": ticket_id, "status": "accepted"}


@router.post("/{project_id}/pr/{ticket_id}/reject", status_code=200)
async def reject_pr(
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
    return {"ticket_id": ticket_id, "status": "rejected"}
