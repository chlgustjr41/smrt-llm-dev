"""Bug tickets API: list tickets and approve them to start a Coder fix session."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project, QASession
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.event_log import EventLogger
from smrt_agent.settings import Settings
from smrt_agent.agents.orchestrator import run_ticket_fix_session

router = APIRouter(prefix="/projects", tags=["tickets"])

# In-memory queues keyed by session_id (available for future SSE endpoints)
_queues: dict[str, asyncio.Queue] = {}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_in_progress_ids(project_path: Path) -> set[str]:
    p = project_path / ".smrt" / "in-progress-tickets.txt"
    if not p.exists():
        return set()
    return {line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}


async def _update_session_status(session_id: str, status: str) -> None:
    """Persist mid-session status change to DB (coder_running ↔ qa_checking)."""
    try:
        engine = get_engine(force_new=False)
        Session = get_session_factory(engine)
        async with Session() as db:
            result = await db.execute(
                select(QASession).where(QASession.session_id == session_id)
            )
            sess = result.scalar_one_or_none()
            if sess:
                sess.status = status
                await db.commit()
    except Exception:
        pass


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

    # Closed tickets (bugs-resolved.md)
    resolved_ids: set[str] = set()
    resolved_path = Path(project.canonical_path) / ".smrt" / "bugs-resolved.md"
    if resolved_path.exists():
        for line in resolved_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                resolved_ids.add(line[3:].strip())

    # Needs-review tickets (pending-prs.jsonl written after QA verify passes)
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

    # Active fix sessions — derive in_progress vs qa_review from QASession.status
    active_result = await db.execute(
        select(QASession.ticket_id, QASession.session_id, QASession.status)
        .where(QASession.project_id == project_id)
        .where(QASession.completed_at.is_(None))
        .where(QASession.ticket_id.is_not(None))
    )
    ticket_to_active: dict[str, dict] = {}
    coder_running_ids: set[str] = set()
    qa_checking_ids: set[str] = set()
    for tid, sid, sstatus in active_result.all():
        ticket_to_active[tid] = {"session_id": sid, "status": sstatus}
        if sstatus == "qa_checking":
            qa_checking_ids.add(tid)
        else:
            coder_running_ids.add(tid)

    # Most recent completed session per ticket — so users can view logs after the run
    done_result = await db.execute(
        select(QASession.ticket_id, QASession.session_id)
        .where(QASession.project_id == project_id)
        .where(QASession.completed_at.is_not(None))
        .where(QASession.status == "done")
        .where(QASession.ticket_id.is_not(None))
        .order_by(QASession.completed_at.desc())
    )
    completed_session: dict[str, str] = {}
    for tid, sid in done_result.all():
        completed_session.setdefault(tid, sid)

    # File-based fallback for tickets approved before per-ticket sessions existed
    in_progress_ids = _read_in_progress_ids(Path(project.canonical_path))

    results = []
    for path in sorted(tickets_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = lines[0].lstrip("#").strip() if lines else path.stem
        ticket_id = path.stem

        # Priority: closed > needs_review > qa_review > in_progress > pending_confirmation
        if ticket_id in resolved_ids:
            status = "closed"
        elif ticket_id in pending_review_ids:
            status = "needs_review"
        elif ticket_id in qa_checking_ids:
            status = "qa_review"
        elif ticket_id in coder_running_ids or ticket_id in in_progress_ids:
            status = "in_progress"
        else:
            status = "pending_confirmation"

        active_info = ticket_to_active.get(ticket_id, {})
        session_id = active_info.get("session_id") or completed_session.get(ticket_id)

        results.append({
            "id": ticket_id,
            "title": title,
            "content": content,
            "status": status,
            "session_id": session_id,
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

    # Mark ticket as in-progress in the approval file (durable record)
    in_progress_path = Path(project.canonical_path) / ".smrt" / "in-progress-tickets.txt"
    in_progress_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_in_progress_ids(Path(project.canonical_path))
    existing.add(ticket_id)
    in_progress_path.write_text("\n".join(sorted(existing)) + "\n", encoding="utf-8")

    # Create a QASession row for this ticket's Coder fix loop
    session_id = str(uuid.uuid4())
    qa_session = QASession(
        session_id=session_id,
        project_id=project_id,
        status="coder_running",
        ticket_id=ticket_id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(qa_session)
    await db.commit()

    # Wire queue → JSONL event log
    queue: asyncio.Queue = asyncio.Queue()
    _queues[session_id] = queue
    log_path = (
        Path(project.canonical_path) / ".smrt" / "qa-sessions" / f"{session_id}.jsonl"
    )
    logged_queue = EventLogger(queue, log_path)

    settings = Settings()
    asyncio.create_task(_ticket_fix_task(
        project_id=project_id,
        session_id=session_id,
        ticket_id=ticket_id,
        canonical_path=project.canonical_path,
        queue=logged_queue,
        api_key=settings.anthropic_api_key,
        model_coder=settings.model_coder,
        budget_usd=settings.budget_per_run_usd,
        max_fix_attempts=settings.max_fix_attempts,
    ))

    return {"ticket_id": ticket_id, "session_id": session_id, "status": "in_progress"}


async def _ticket_fix_task(
    *,
    project_id: int,
    session_id: str,
    ticket_id: str,
    canonical_path: str,
    queue: "EventLogger",
    api_key: str,
    model_coder: str,
    budget_usd: float,
    max_fix_attempts: int,
) -> None:
    """Background coroutine: runs Coder → QA-verify loop for one approved ticket."""
    async def on_status_change(status: str) -> None:
        await _update_session_status(session_id, status)

    final_status = "error"
    try:
        final_status = await run_ticket_fix_session(
            session_id=session_id,
            ticket_id=ticket_id,
            project_path=Path(canonical_path),
            api_key=api_key,
            model_coder=model_coder,
            budget_usd=budget_usd,
            max_fix_attempts=max_fix_attempts,
            queue=queue,
            on_status_change=on_status_change,
        )
    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc), "ts": _ts()})
        final_status = "error"
    finally:
        try:
            engine = get_engine(force_new=False)
            Session = get_session_factory(engine)
            async with Session() as db:
                result = await db.execute(
                    select(QASession).where(QASession.session_id == session_id)
                )
                sess = result.scalar_one_or_none()
                if sess:
                    sess.status = final_status
                    sess.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass
        await queue.put({"type": "done", "status": final_status})
        _queues.pop(session_id, None)
