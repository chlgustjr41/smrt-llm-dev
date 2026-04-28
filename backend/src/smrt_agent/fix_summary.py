"""Persistent fix-summary storage.

A "fix summary" is the durable, human-readable record of what happened during
a single QA→Coder fix session: which files were changed, what the agent's
reasoning was, what the final pytest output looked like, and (when applicable)
what the QA Advisor concluded.

Why persist this separately from the JSONL event log?
- Event logs are streaming-oriented and may be rotated/cleaned eventually.
- Reconstructing the summary by re-walking events on every UI dialog open is
  slow and tightly couples the UI to the event-format internals.
- Persisting a small JSON snapshot once-per-session decouples viewers from
  event retention and makes "remember the fix across sessions" trivial: just
  read the file. New sessions get new summary files; the index points at the
  latest one for each ticket.

Layout:
  .smrt/fix-summaries/
    index.json                    # { ticket_id → latest_session_id }
    {session_id}.json             # one file per session, kept indefinitely
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Tools we recognize as "the coder modified a source file." Mirrors the same
# allow-list the frontend uses in TicketsPanel.tsx::FILE_WRITE_TOOLS so the
# server-built summary matches the previously client-reconstructed one.
FILE_WRITE_TOOLS: set[str] = {
    "write_file",
    "write_source_file",
    "str_replace",
    "patch_file",
    "edit_file",
    "apply_patch",
    "create_file",
    "append_file",
    "patch_source_file",
}

_TEXT_DELTA_TYPES = {"text_delta", "qa_text_delta", "coder_text_delta"}


def _extract_file_path(input_obj: Any) -> str | None:
    if not isinstance(input_obj, dict):
        return None
    p = input_obj.get("path") or input_obj.get("file_path") or input_obj.get("filename")
    return p if isinstance(p, str) else None


def _extract_change(tool: str, input_obj: Any) -> tuple[str, str]:
    """Return (kind, content_preview) for a file-write tool call.

    Mirrors `extractChangeContent` in TicketsPanel.tsx — same truncation
    limits, same kind labels, so the UI doesn't need to special-case
    server-built summaries vs client-reconstructed ones.
    """
    if not isinstance(input_obj, dict):
        return ("unknown", "")
    if tool in ("str_replace", "patch_source_file"):
        old = str(input_obj.get("old_str", "") or "")
        new = str(input_obj.get("new_str", "") or "")
        return ("edit", f"− {old[:300]}\n+ {new[:300]}")
    if tool in ("patch_file", "apply_patch"):
        patch = str(input_obj.get("patch", "") or "")
        return ("patch", patch[:600])
    content = str(input_obj.get("content", "") or "")
    return ("write", content[:600])


def build_fix_summary_from_events(
    events: list[dict],
    *,
    ticket_id: str,
    session_id: str,
    final_status: str,
) -> dict:
    """Walk a session's event stream and produce a self-contained summary dict.

    The walker mirrors the frontend's `groupFileChanges` so a server-persisted
    summary and a client-reconstructed one render identically. Pending text
    accumulates between tool calls and is captured as the "reasoning" for the
    next file-write tool — exactly the same heuristic used in the UI today.
    """
    changes: list[dict] = []
    pending_text = ""
    qa_early_exit: str | None = None
    qa_final_summary: str | None = None
    recheck_output: str | None = None
    recommendation: str | None = None
    analysis: str | None = None
    pr_ready = False

    for ev in events:
        t = ev.get("type")
        if t in _TEXT_DELTA_TYPES:
            pending_text += ev.get("text", "") or ""
        elif t == "tool_use" and ev.get("tool") in FILE_WRITE_TOOLS:
            path = _extract_file_path(ev.get("input"))
            if path:
                kind, content = _extract_change(ev["tool"], ev.get("input"))
                changes.append({
                    "path": path,
                    "tool": ev["tool"],
                    "reasoning": pending_text[-400:].strip(),
                    "kind": kind,
                    "content": content,
                    "ts": ev.get("ts"),
                })
            pending_text = ""
        elif t in ("tool_use", "tool_result", "session_status"):
            pending_text = ""
        elif t == "qa_early_exit":
            qa_early_exit = ev.get("reasoning")
        elif t == "qa_final_summary":
            # The QA's compiled narrative — the headline of the persisted
            # Fix Summary. Always take the LAST one if multiple exist (the
            # final terminal pass wins over any earlier ones).
            summary_text = ev.get("summary")
            if isinstance(summary_text, str) and summary_text.strip():
                qa_final_summary = summary_text
        elif t == "recheck_output":
            # Take the LAST recheck — that's what the loop ended on.
            recheck_output = ev.get("output")
        elif t == "loop_exhausted":
            recommendation = ev.get("recommendation")
            analysis = ev.get("analysis")
        elif t == "pr_ready":
            pr_ready = True

    return {
        "ticket_id": ticket_id,
        "session_id": session_id,
        "final_status": final_status,
        "pr_ready": pr_ready,
        "recommendation": recommendation,
        "analysis": analysis,
        "qa_early_exit": qa_early_exit,
        "qa_final_summary": qa_final_summary,
        "recheck_output": recheck_output,
        "changes": changes,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def _summaries_dir(project_path: Path) -> Path:
    return project_path / ".smrt" / "fix-summaries"


def _index_path(project_path: Path) -> Path:
    return _summaries_dir(project_path) / "index.json"


def save_fix_summary(project_path: Path, summary: dict) -> None:
    """Persist a single session's summary to disk and update the ticket index.

    Idempotent: re-saving the same session_id overwrites the file, and the
    index always points at the most-recently-saved session for the ticket.
    Per-session files are kept indefinitely so the user can scroll back to
    earlier fix attempts even after a re-queue.
    """
    base = _summaries_dir(project_path)
    base.mkdir(parents=True, exist_ok=True)

    session_id = summary.get("session_id")
    ticket_id = summary.get("ticket_id")
    if not session_id or not ticket_id:
        return

    file_path = base / f"{session_id}.json"
    file_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    index_path = _index_path(project_path)
    index: dict = {}
    if index_path.exists():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                index = loaded
        except (json.JSONDecodeError, OSError):
            index = {}
    index[ticket_id] = session_id
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def load_fix_summary_for_ticket(project_path: Path, ticket_id: str) -> dict | None:
    """Return the most recently saved summary for a ticket, or None."""
    index_path = _index_path(project_path)
    if not index_path.exists():
        return None
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    sid = index.get(ticket_id) if isinstance(index, dict) else None
    if not sid:
        return None
    return _load_summary_file(project_path, sid)


def load_fix_summary_for_session(project_path: Path, session_id: str) -> dict | None:
    """Return the summary for a specific session, or None."""
    return _load_summary_file(project_path, session_id)


def _load_summary_file(project_path: Path, session_id: str) -> dict | None:
    file_path = _summaries_dir(project_path) / f"{session_id}.json"
    if not file_path.exists():
        return None
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_events_from_jsonl(project_path: Path, session_id: str) -> list[dict]:
    """Slurp the persisted SSE event log for a session into a list of dicts."""
    log_path = project_path / ".smrt" / "qa-sessions" / f"{session_id}.jsonl"
    if not log_path.exists():
        return []
    events: list[dict] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            events.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return events
