"""PR surface API: list pending PRs, accept or reject a fix."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project, QASession
from smrt_agent.agents.qa.tools import append_bugs_resolved
from smrt_agent.agents.reviewer.tools import write_docs_file, write_file, write_readme
from smrt_agent.fix_summary import load_fix_summary_for_ticket
from smrt_agent.knowledge import append_lesson, append_rejection, sync_wiki_log

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


def _apply_proposed_doc_updates(project_path: Path, ticket_id: str) -> dict:
    """Read the persisted Fix Summary for this ticket and apply any
    proposed_doc_updates the Reviewer queued. Returns a structured report
    of what was applied so the API response can surface counts to the user.

    Path policy mirrors the Reviewer's tool restrictions:
      - 'README.md'           → write_readme
      - 'docs/<...>.md'       → write_docs_file
      - '.smrt/Project.md'    → write_file (the only .smrt/ path we permit
                                from a doc-update proposal — others are
                                runtime artifacts the Reviewer shouldn't
                                be writing as part of an accept)

    Failures on individual files are recorded in the report but never
    raise — the user already accepted the fix; we don't want one bad
    proposal to block the whole accept flow.
    """
    report: dict = {"applied": [], "skipped": [], "errors": []}
    summary = load_fix_summary_for_ticket(project_path, ticket_id)
    if not summary:
        return report

    updates = summary.get("proposed_doc_updates") or []
    if not isinstance(updates, list):
        return report

    for u in updates:
        if not isinstance(u, dict):
            continue
        path = u.get("path")
        content = u.get("new_content")
        if not isinstance(path, str) or not isinstance(content, str):
            report["skipped"].append({"path": path, "reason": "missing path or content"})
            continue
        try:
            if path == "README.md":
                write_readme(project_path, content)
                report["applied"].append({"path": path})
            elif path.startswith("docs/") and path.endswith(".md"):
                write_docs_file(project_path, path, content)
                report["applied"].append({"path": path})
            elif path == ".smrt/Project.md":
                write_file(project_path, path, content)
                report["applied"].append({"path": path})
            else:
                report["skipped"].append({
                    "path": path,
                    "reason": "path not in allowed list (README.md / docs/*.md / .smrt/Project.md)",
                })
        except Exception as exc:
            report["errors"].append({"path": path, "error": str(exc)})
    return report


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

    # ── Git: commit fix changes and merge to base branch ───────────────────
    from smrt_agent.git import (
        commit_and_merge_fix as _git_merge,
        load_base_branch as _git_load_base,
        clear_base_branch as _git_clear_base,
    )
    try:
        base = _git_load_base(project_path, ticket_id)
        _git_merge(project_path, base, ticket_id)
        _git_clear_base(project_path, ticket_id)
    except Exception as exc:
        import logging; logging.getLogger(__name__).warning("git merge failed: %s", exc)

    append_bugs_resolved(project_path, ticket_id, "Accepted via PR surface review.")
    ticket_title = _get_ticket_title(project_path, ticket_id)
    append_lesson(project_path, ticket_id, "accepted", f"{ticket_title} — fix passed all tests.")
    sync_wiki_log(project_path, ticket_id, ticket_title, "accepted")

    # Apply any documentation updates the Reviewer queued during its final
    # summary pass. This is the "doc updates are part of the approval"
    # contract: clicking Accept implicitly approves both the source fix and
    # the doc changes the Reviewer flagged. The applier is best-effort —
    # individual proposal failures are reported but never block the accept.
    doc_report = _apply_proposed_doc_updates(project_path, ticket_id)

    return {
        "ticket_id": ticket_id,
        "status": "accepted",
        "doc_updates": doc_report,
    }


@router.post("/{project_id}/pr/{ticket_id}/reject", status_code=200)
async def reject_pr(
    project_id: int,
    ticket_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    body: RejectBody = RejectBody(),
) -> dict:
    """Reject a fix and return the ticket to pending_confirmation as a fresh ticket.

    Cleans up all status files so the ticket falls back to pending_confirmation
    in list_tickets priority logic. Archives past session JSONL logs.
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project_path = Path(project.canonical_path)

    # ── Remove from pending-prs.jsonl (if present) ─────────────────────────
    entries = _read_pending_prs(project_path)
    remaining = [e for e in entries if e.get("ticket_id") != ticket_id]
    if len(remaining) < len(entries):
        _write_pending_prs(project_path, remaining)

    # ── Remove from failed-fixes.jsonl (if present) ────────────────────────
    failed_log = project_path / ".smrt" / "failed-fixes.jsonl"
    if failed_log.exists():
        kept = []
        for line in failed_log.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                if json.loads(s).get("ticket_id") != ticket_id:
                    kept.append(s)
            except json.JSONDecodeError:
                kept.append(s)
        failed_log.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

    # ── Remove from in-progress-tickets.txt ────────────────────────────────
    in_progress_path = project_path / ".smrt" / "in-progress-tickets.txt"
    if in_progress_path.exists():
        ids = set()
        for line in in_progress_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s:
                ids.add(s)
        ids.discard(ticket_id)
        in_progress_path.write_text(
            "\n".join(sorted(ids)) + ("\n" if ids else ""),
            encoding="utf-8",
        )

    # ── Cancel any running fix task and mark active sessions as rejected ────
    from smrt_agent.api.tickets import _tasks as _fix_tasks  # avoid circular import at module level
    active_result = await db.execute(
        select(QASession)
        .where(QASession.project_id == project_id)
        .where(QASession.ticket_id == ticket_id)
        .where(QASession.completed_at.is_(None))
    )
    for active_sess in active_result.scalars().all():
        active_sess.status = "rejected"
        active_sess.completed_at = datetime.now(timezone.utc)
        task = _fix_tasks.pop(active_sess.session_id, None)
        if task and not task.done():
            task.cancel()
    await db.commit()

    # ── Archive JSONL logs for all past sessions on this ticket ────────────
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

    # ── Git: discard changes and return to base branch ─────────────────────
    from smrt_agent.git import (
        discard_fix_branch as _git_discard,
        load_base_branch as _git_load_base,
        clear_base_branch as _git_clear_base,
    )
    try:
        base = _git_load_base(project_path, ticket_id)
        _git_discard(project_path, base, ticket_id)
        _git_clear_base(project_path, ticket_id)
    except Exception as exc:
        import logging; logging.getLogger(__name__).warning("git discard failed: %s", exc)

    # ── Record rejection lesson ────────────────────────────────────────────
    ticket_title = _get_ticket_title(project_path, ticket_id)
    reason = body.reason
    append_lesson(project_path, ticket_id, "rejected", f"{ticket_title} — rejected: {reason}")
    append_rejection(project_path, ticket_id, ticket_title, reason)

    return {"ticket_id": ticket_id, "status": "rejected"}
