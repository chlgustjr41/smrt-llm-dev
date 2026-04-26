"""Bug tickets API: list .smrt/tickets/ files for a project."""
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project

router = APIRouter(prefix="/projects", tags=["tickets"])


def _read_in_progress_ids(project_path: Path) -> set[str]:
    p = project_path / ".smrt" / "in-progress-tickets.txt"
    if not p.exists():
        return set()
    return {line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}


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

    # Read bugs-resolved.md to determine which tickets are closed
    resolved_ids: set[str] = set()
    resolved_path = Path(project.canonical_path) / ".smrt" / "bugs-resolved.md"
    if resolved_path.exists():
        resolved_text = resolved_path.read_text(encoding="utf-8")
        for line in resolved_text.splitlines():
            if line.startswith("## "):
                resolved_ids.add(line[3:].strip())

    # Read pending-prs.jsonl for needs_review tickets
    pending_review_ids: set[str] = set()
    pr_log = Path(project.canonical_path) / ".smrt" / "pending-prs.jsonl"
    if pr_log.exists():
        for line in pr_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    pending_review_ids.add(entry.get("ticket_id", ""))
                except json.JSONDecodeError:
                    pass

    in_progress_ids = _read_in_progress_ids(Path(project.canonical_path))

    results = []
    for path in sorted(tickets_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = lines[0].lstrip("#").strip() if lines else path.stem
        ticket_id = path.stem
        # Priority: terminal states override earlier ones
        if ticket_id in resolved_ids:
            status = "closed"
        elif ticket_id in pending_review_ids:
            status = "needs_review"
        elif ticket_id in in_progress_ids:
            status = "in_progress"
        else:
            status = "pending_confirmation"
        results.append({
            "id": ticket_id,
            "title": title,
            "content": content,
            "status": status,
        })
    return results


@router.post("/{project_id}/tickets/{ticket_id}/approve")
async def approve_ticket(
    project_id: int,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    ticket_path = Path(project.canonical_path) / ".smrt" / "tickets" / f"{ticket_id}.md"
    if not ticket_path.exists():
        raise HTTPException(status_code=404, detail="Ticket not found")

    in_progress_path = Path(project.canonical_path) / ".smrt" / "in-progress-tickets.txt"
    in_progress_path.parent.mkdir(parents=True, exist_ok=True)

    existing = _read_in_progress_ids(Path(project.canonical_path))
    existing.add(ticket_id)
    in_progress_path.write_text("\n".join(sorted(existing)) + "\n", encoding="utf-8")

    return {"ticket_id": ticket_id, "status": "in_progress"}
