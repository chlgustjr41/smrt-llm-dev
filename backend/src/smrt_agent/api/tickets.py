"""Bug tickets API: list tickets and approve them to start a Coder fix session."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, case, select
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.api.session_registry import session_queues
from smrt_agent.agents import budget_gateway
from smrt_agent.db.models import Project, QASession
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.event_log import EventLogger
from smrt_agent.llm import LLMClient
from smrt_agent.settings import Settings
from smrt_agent.agents.orchestrator import run_ticket_fix_session
import smrt_agent.git as _git

router = APIRouter(prefix="/projects", tags=["tickets"])

_tasks: dict[str, "asyncio.Task[None]"] = {}  # session_id → running fix task


def _project_config(project_config_json: str | None, settings: Settings) -> dict:
    """Parse per-project config, falling back to global Settings for missing fields."""
    try:
        stored = json.loads(project_config_json or '{}')
    except Exception:
        stored = {}
    return {
        "model_coder": stored.get("coder_model", settings.model_coder),
        "model_qa": stored.get("qa_model", settings.model_qa),
        "max_fix_attempts": stored.get("max_fix_attempts", settings.max_fix_attempts),
        "max_questions_per_attempt": stored.get("max_questions_per_attempt", 0),
    }


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_in_progress_ids(project_path: Path) -> set[str]:
    p = project_path / ".smrt" / "in-progress-tickets.txt"
    if not p.exists():
        return set()
    return {line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}


def _read_resolved_ids(project_path: Path) -> set[str]:
    p = project_path / ".smrt" / "bugs-resolved.md"
    if not p.exists():
        return set()
    return {line[3:].strip() for line in p.read_text(encoding="utf-8").splitlines() if line.startswith("## ")}


def _read_needs_review_ids(project_path: Path) -> set[str]:
    """IDs that have completed their fix loop (pending-prs.jsonl or failed-fixes.jsonl)."""
    ids: set[str] = set()
    for filename in ("pending-prs.jsonl", "failed-fixes.jsonl"):
        p = project_path / ".smrt" / filename
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                tid = json.loads(line).get("ticket_id", "")
                if tid:
                    ids.add(tid)
            except json.JSONDecodeError:
                pass
    return ids


async def _launch_ticket_fix(
    *,
    project_id: int,
    project_path: Path,
    project_config_json: str | None,
    ticket_id: str,
    settings: Settings,
) -> str:
    """Create a QASession, wire the event queue, and fire asyncio.create_task for one ticket.

    Returns the new session_id immediately. Git setup and the agent loop run in the
    background task so the HTTP response stays under ~50ms — the user sees the
    Coder agent appear in the LoopStatusBanner the instant the drag completes.
    """
    # Mark ticket as in-progress immediately so listTickets shows it correctly
    in_progress_path = project_path / ".smrt" / "in-progress-tickets.txt"
    in_progress_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_in_progress_ids(project_path)
    existing.add(ticket_id)
    in_progress_path.write_text("\n".join(sorted(existing)) + "\n", encoding="utf-8")

    # Create a QASession row for this ticket's Coder fix loop
    session_id = str(uuid.uuid4())
    engine = get_engine(force_new=False)
    DbSession = get_session_factory(engine)
    async with DbSession() as db:
        qa_session = QASession(
            session_id=session_id,
            project_id=project_id,
            status="coder_running",
            ticket_id=ticket_id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(qa_session)
        await db.commit()

    # Wire queue → JSONL event log BEFORE returning so the SSE stream endpoint
    # can find the queue immediately if the user opens the dialog quickly
    queue: asyncio.Queue = asyncio.Queue()
    session_queues[session_id] = queue
    log_path = project_path / ".smrt" / "qa-sessions" / f"{session_id}.jsonl"
    logged_queue = EventLogger(queue, log_path)

    # Emit an initial "session_status" event so the dialog shows activity immediately,
    # even before the agent has produced any tokens
    await logged_queue.put({
        "type": "session_status",
        "status": "coder_running",
        "ticket_id": ticket_id,
        "fix_attempt": 0,
        "ts": _ts(),
    })

    cfg = _project_config(project_config_json, settings)
    task = asyncio.create_task(_ticket_fix_task(
        project_id=project_id,
        session_id=session_id,
        ticket_id=ticket_id,
        canonical_path=str(project_path),
        project_config_json=project_config_json,
        queue=logged_queue,
        llm_client=LLMClient.from_project(project_config_json, settings),
        model_coder=cfg["model_coder"],
        model_qa=cfg["model_qa"],
        budget_usd=settings.budget_per_ticket_usd,
        max_fix_attempts=cfg["max_fix_attempts"],
        max_questions_per_attempt=cfg["max_questions_per_attempt"],
        job_id=session_id,
    ))
    _tasks[session_id] = task
    task.add_done_callback(lambda _: _tasks.pop(session_id, None))
    return session_id




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

    # Loop-exhausted tickets (failed-fixes.jsonl) — also shown in Needs Review
    failed_fix_reports: dict[str, dict] = {}
    failed_log = Path(project.canonical_path) / ".smrt" / "failed-fixes.jsonl"
    if failed_log.exists():
        for line in failed_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    tid = entry.get("ticket_id", "")
                    if tid:
                        failed_fix_reports[tid] = {
                            "recommendation": entry.get("recommendation"),
                            "analysis": entry.get("analysis"),
                        }
                        pending_review_ids.add(tid)
                except json.JSONDecodeError:
                    pass

    # Attempt and failure counts per ticket
    counts_result = await db.execute(
        select(
            QASession.ticket_id,
            func.count().label("attempt_count"),
            func.sum(
                case((QASession.status.in_(["error", "loop_exhausted"]), 1), else_=0)
            ).label("failure_count"),
        )
        .where(QASession.project_id == project_id)
        .where(QASession.ticket_id.is_not(None))
        .group_by(QASession.ticket_id)
    )
    ticket_counts: dict[str, dict] = {
        row.ticket_id: {
            "attempt_count": row.attempt_count,
            "failure_count": int(row.failure_count or 0),
        }
        for row in counts_result.all()
    }

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

        # Priority: closed > active DB session > file-based needs_review > legacy in-progress > pending
        # pending_review_ids must beat in_progress_ids: the approval file is written once and
        # never cleaned up, so a ticket that completed its fix (→ pending-prs.jsonl) would
        # otherwise stay stuck in in_progress forever.
        if ticket_id in resolved_ids:
            status = "closed"
        elif ticket_id in qa_checking_ids:
            status = "qa_review"
        elif ticket_id in coder_running_ids:
            status = "in_progress"
        elif ticket_id in pending_review_ids:
            status = "needs_review"
        elif ticket_id in in_progress_ids:
            # Legacy fallback: approved before per-ticket DB sessions existed
            status = "in_progress"
        else:
            status = "pending_confirmation"

        active_info = ticket_to_active.get(ticket_id, {})
        session_id = active_info.get("session_id") or completed_session.get(ticket_id)
        counts = ticket_counts.get(ticket_id, {"attempt_count": 0, "failure_count": 0})

        results.append({
            "id": ticket_id,
            "title": title,
            "content": content,
            "status": status,
            "session_id": session_id,
            "failure_report": failed_fix_reports.get(ticket_id) if status == "needs_review" else None,
            "attempt_count": counts["attempt_count"],
            "failure_count": counts["failure_count"],
        })
    return results


@router.get("/{project_id}/tickets/{ticket_id}/sessions")
async def list_ticket_sessions(
    project_id: int,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    """Return all QA sessions that worked on a specific ticket, newest first.

    Used by the Tickets tab to show per-ticket history: each session is an
    expandable accordion entry that loads its events from the JSONL log.
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(QASession)
        .where(QASession.project_id == project_id)
        .where(QASession.ticket_id == ticket_id)
        .order_by(QASession.started_at.desc())
    )
    sessions = result.scalars().all()
    return [
        {
            "session_id": s.session_id,
            "status": s.status,
            "fix_attempt": s.fix_attempt,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        }
        for s in sessions
    ]


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

    session_id = await _launch_ticket_fix(
        project_id=project_id,
        project_path=Path(project.canonical_path),
        project_config_json=project.config,
        ticket_id=ticket_id,
        settings=Settings(),
    )
    return {"ticket_id": ticket_id, "session_id": session_id, "status": "in_progress"}


async def _ticket_fix_task(
    *,
    project_id: int,
    session_id: str,
    ticket_id: str,
    canonical_path: str,
    project_config_json: str | None = None,
    queue: "EventLogger",
    llm_client: "LLMClient",
    model_coder: str,
    model_qa: str | None = None,
    budget_usd: float,
    max_fix_attempts: int,
    max_questions_per_attempt: int = 0,
    job_id: str | None = None,
) -> None:
    """Background coroutine: runs Coder → QA-verify loop for one approved ticket.

    On completion (any final status), auto-drains the next pending_confirmation
    ticket so the pipeline empties without user intervention.
    """
    async def on_status_change(status: str) -> None:
        await _update_session_status(session_id, status)

    project_path = Path(canonical_path)

    # Git setup runs in the background (was previously blocking the HTTP response).
    # If git ops fail we still attempt the fix on the current branch — the agent
    # may produce a usable diff that the user can review manually.
    try:
        await asyncio.to_thread(_git.ensure_git_repo, project_path)
        base = await asyncio.to_thread(_git.current_branch, project_path)
        await asyncio.to_thread(_git.save_base_branch, project_path, ticket_id, base)
        await asyncio.to_thread(_git.create_fix_branch, project_path, ticket_id)
    except Exception as exc:
        import logging; logging.getLogger(__name__).warning("git setup failed: %s", exc)
        await queue.put({
            "type": "session_status",
            "status": "git_setup_warning",
            "message": f"Git setup failed (will fix on current branch): {exc}",
            "ts": _ts(),
        })

    final_status = "error"
    try:
        final_status = await run_ticket_fix_session(
            session_id=session_id,
            ticket_id=ticket_id,
            project_path=project_path,
            llm_client=llm_client,
            model_coder=model_coder,
            model_qa=model_qa,
            budget_usd=budget_usd,
            max_fix_attempts=max_fix_attempts,
            max_questions_per_attempt=max_questions_per_attempt,
            queue=queue,
            on_status_change=on_status_change,
            job_id=job_id,
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
                # Guard: cancel_ticket/reject_pr may have already set completed_at
                if sess and sess.completed_at is None:
                    sess.status = final_status
                    sess.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass
        try:
            await queue.put({"type": "done", "status": final_status})
        except Exception:
            pass
        session_queues.pop(session_id, None)


@router.post("/{project_id}/tickets/{ticket_id}/cancel", status_code=200)
async def cancel_ticket(
    project_id: int,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Cancel an active fix session and move the ticket to needs_review.

    Idempotent: succeeds even if the session already completed (e.g., errored
    before the user clicked Cancel). Always ensures the ticket ends up in
    needs_review by writing to failed-fixes.jsonl.
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_path = Path(project.canonical_path)

    # Find the active session (if any) — don't 409 if none exists
    result = await db.execute(
        select(QASession)
        .where(QASession.project_id == project_id)
        .where(QASession.ticket_id == ticket_id)
        .where(QASession.completed_at.is_(None))
    )
    session = result.scalar_one_or_none()
    session_id: str | None = None

    if session is not None:
        session_id = session.session_id
        session.status = "cancelled"
        session.completed_at = datetime.now(timezone.utc)
        await db.commit()

        task = _tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    # Ensure ticket shows as needs_review: write to failed-fixes.jsonl if not already there
    failed_log = project_path / ".smrt" / "failed-fixes.jsonl"
    failed_log.parent.mkdir(parents=True, exist_ok=True)

    already_logged = False
    if failed_log.exists():
        for line in failed_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                if json.loads(line).get("ticket_id") == ticket_id:
                    already_logged = True
                    break
            except json.JSONDecodeError:
                pass

    if not already_logged:
        with failed_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ticket_id": ticket_id,
                "session_id": session_id or "unknown",
                "recommendation": "needs_more_attempts",
                "analysis": "Fix session was cancelled by user. The ticket is back in the queue.",
                "ts": _ts(),
            }) + "\n")

    # ── Git: discard changes and return to base branch ──────────────────────
    try:
        base = await asyncio.to_thread(_git.load_base_branch, project_path, ticket_id)
        await asyncio.to_thread(_git.discard_fix_branch, project_path, base, ticket_id)
        await asyncio.to_thread(_git.clear_base_branch, project_path, ticket_id)
    except Exception as exc:
        import logging; logging.getLogger(__name__).warning("git discard failed: %s", exc)

    return {"ticket_id": ticket_id, "session_id": session_id, "status": "cancelled"}


@router.post("/{project_id}/tickets/{ticket_id}/budget-decision", status_code=200)
async def ticket_budget_decision(
    project_id: int,
    ticket_id: str,
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Resolve a budget pause for the active fix session on this ticket."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(QASession)
        .where(QASession.project_id == project_id)
        .where(QASession.ticket_id == ticket_id)
        .where(QASession.completed_at.is_(None))
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="No active session for this ticket")

    decision = body.get("decision", "terminate")
    found = budget_gateway.resolve(session.session_id, decision)
    if not found:
        raise HTTPException(status_code=409, detail="No budget pause pending for this session")
    return {"ticket_id": ticket_id, "session_id": session.session_id, "decision": decision}


@router.post("/{project_id}/tickets/{ticket_id}/close", status_code=200)
async def close_ticket(
    project_id: int,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Manually close a ticket (skip fixing). Appends to bugs-resolved.md."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    ticket_path = Path(project.canonical_path) / ".smrt" / "tickets" / f"{ticket_id}.md"
    if not ticket_path.exists():
        raise HTTPException(status_code=404, detail="Ticket not found")

    resolved_path = Path(project.canonical_path) / ".smrt" / "bugs-resolved.md"
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ticket_id}\nManually closed at {_ts()}.\n")

    return {"ticket_id": ticket_id, "status": "closed"}


@router.post("/{project_id}/tickets/{ticket_id}/requeue", status_code=202)
async def requeue_ticket(
    project_id: int,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Restart a fix session for a needs_review ticket (drag to In Progress)."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    ticket_path = Path(project.canonical_path) / ".smrt" / "tickets" / f"{ticket_id}.md"
    if not ticket_path.exists():
        raise HTTPException(status_code=404, detail="Ticket not found")

    session_id = await _launch_ticket_fix(
        project_id=project_id,
        project_path=Path(project.canonical_path),
        project_config_json=project.config,
        ticket_id=ticket_id,
        settings=Settings(),
    )
    return {"ticket_id": ticket_id, "session_id": session_id, "status": "in_progress"}


@router.post("/{project_id}/tickets/{ticket_id}/reset", status_code=200)
async def reset_ticket(
    project_id: int,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Hard reset: discard all git changes, clear all status data, return to pending_confirmation."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_path = Path(project.canonical_path)

    # Cancel any running session
    active_result = await db.execute(
        select(QASession)
        .where(QASession.project_id == project_id)
        .where(QASession.ticket_id == ticket_id)
        .where(QASession.completed_at.is_(None))
    )
    for active_sess in active_result.scalars().all():
        active_sess.status = "reset"
        active_sess.completed_at = datetime.now(timezone.utc)
        task = _tasks.pop(active_sess.session_id, None)
        if task and not task.done():
            task.cancel()
    await db.commit()

    # Remove from all status files
    for log_file in ("pending-prs.jsonl", "failed-fixes.jsonl"):
        p = project_path / ".smrt" / log_file
        if p.exists():
            kept = []
            for line in p.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if not s:
                    continue
                try:
                    if json.loads(s).get("ticket_id") != ticket_id:
                        kept.append(s)
                except json.JSONDecodeError:
                    kept.append(s)
            p.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    in_progress_path = project_path / ".smrt" / "in-progress-tickets.txt"
    if in_progress_path.exists():
        ids = set()
        for line in in_progress_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s:
                ids.add(s)
        ids.discard(ticket_id)
        in_progress_path.write_text("\n".join(sorted(ids)) + ("\n" if ids else ""), encoding="utf-8")

    # Archive JSONL session logs
    sessions_dir = project_path / ".smrt" / "qa-sessions"
    if sessions_dir.exists():
        archived_dir = sessions_dir / "archived"
        archived_dir.mkdir(parents=True, exist_ok=True)
        all_sessions = await db.execute(
            select(QASession.session_id)
            .where(QASession.project_id == project_id)
            .where(QASession.ticket_id == ticket_id)
        )
        for (sid,) in all_sessions.all():
            src = sessions_dir / f"{sid}.jsonl"
            if src.exists():
                src.rename(archived_dir / f"{sid}.jsonl")

    # Git: discard changes and return to base branch
    try:
        base = await asyncio.to_thread(_git.load_base_branch, project_path, ticket_id)
        await asyncio.to_thread(_git.discard_fix_branch, project_path, base, ticket_id)
        await asyncio.to_thread(_git.clear_base_branch, project_path, ticket_id)
    except Exception as exc:
        import logging; logging.getLogger(__name__).warning("git reset failed: %s", exc)

    return {"ticket_id": ticket_id, "status": "reset"}
