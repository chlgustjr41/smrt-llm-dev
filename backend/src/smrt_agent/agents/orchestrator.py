"""QA session orchestrator: coordinates QA → HITL → Coder → recheck loop."""
import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

from smrt_agent.agents.qa.loop import run_qa_agent
from smrt_agent.agents.coder.loop import run_coder_agent
from smrt_agent.agents.qa.tools import run_pytest


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_pending_pr(project_path: Path, ticket_id: str, session_id: str, recheck_output: str) -> None:
    """Append a pending PR entry to .smrt/pending-prs.jsonl."""
    pr_log = project_path / ".smrt" / "pending-prs.jsonl"
    pr_log.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ticket_id": ticket_id,
        "session_id": session_id,
        "recheck_output": recheck_output[:500],
        "fixed_at": _ts(),
    }
    with pr_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


async def run_qa_session(
    *,
    session_id: str,
    project_path: Path,
    api_key: str,
    model_qa: str,
    model_coder: str,
    budget_usd: float,
    max_fix_attempts: int,
    queue: asyncio.Queue,
    hitl_events: dict[str, asyncio.Event],
    hitl_decisions: dict[str, str],
) -> str:
    """Coordinate the QA/Coder fix loop. Returns final status string."""
    per_agent_budget = budget_usd / max(max_fix_attempts * 2 + 1, 1)
    prior_fix_context: str | None = None

    for attempt in range(max_fix_attempts + 1):
        await queue.put({
            "type": "session_status",
            "status": "qa_running",
            "fix_attempt": attempt,
            "ts": _ts(),
        })

        ticket_id = await run_qa_agent(
            project_path=project_path,
            api_key=api_key,
            model=model_qa,
            budget_usd=per_agent_budget,
            queue=queue,
            prior_fix_context=prior_fix_context,
        )

        if ticket_id is None:
            await queue.put({
                "type": "session_status",
                "status": "done",
                "fix_attempt": attempt,
                "ts": _ts(),
            })
            return "done"

        if attempt >= max_fix_attempts:
            await queue.put({
                "type": "session_status",
                "status": "error",
                "message": "Max fix attempts reached",
                "ts": _ts(),
            })
            return "error"

        await queue.put({
            "type": "hitl_request",
            "session_id": session_id,
            "ticket_id": ticket_id,
            "fix_attempt": attempt,
            "ts": _ts(),
        })
        await queue.put({
            "type": "session_status",
            "status": "hitl_waiting",
            "ts": _ts(),
        })

        event = asyncio.Event()
        hitl_events[session_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=3600.0)
        except asyncio.TimeoutError:
            hitl_events.pop(session_id, None)
            hitl_decisions.pop(session_id, None)
            await queue.put({
                "type": "session_status",
                "status": "error",
                "message": "HITL approval timed out",
                "ts": _ts(),
            })
            return "error"

        decision = hitl_decisions.pop(session_id, "skip")
        hitl_events.pop(session_id, None)

        if decision == "skip":
            await queue.put({
                "type": "session_status",
                "status": "skipped",
                "ts": _ts(),
            })
            return "skipped"

        ticket_path = project_path / ".smrt" / "tickets" / f"{ticket_id}.md"
        ticket_content = (
            ticket_path.read_text(encoding="utf-8")
            if ticket_path.exists()
            else f"Ticket {ticket_id}"
        )
        pytest_output = run_pytest(project_path)

        await queue.put({
            "type": "session_status",
            "status": "coder_running",
            "fix_attempt": attempt,
            "ts": _ts(),
        })
        await run_coder_agent(
            project_path=project_path,
            api_key=api_key,
            model=model_coder,
            budget_usd=per_agent_budget,
            queue=queue,
            ticket_content=ticket_content,
            pytest_output=pytest_output,
        )

        recheck_output = run_pytest(project_path)
        await queue.put({
            "type": "recheck_output",
            "output": recheck_output[:2000],
            "ts": _ts(),
        })

        if "passed" in recheck_output and "failed" not in recheck_output:
            _record_pending_pr(project_path, ticket_id, session_id, recheck_output)
            await queue.put({"type": "pr_ready", "ticket_id": ticket_id, "session_id": session_id, "ts": _ts()})
            await queue.put({
                "type": "session_status",
                "status": "done",
                "fix_attempt": attempt,
                "ts": _ts(),
            })
            return "done"

        prior_fix_context = f"Fix attempt {attempt + 1} recheck:\n{recheck_output}"

    return "error"


async def run_ticket_fix_session(
    *,
    session_id: str,
    ticket_id: str,
    project_path: Path,
    api_key: str,
    model_coder: str,
    budget_usd: float,
    max_fix_attempts: int,
    queue: asyncio.Queue,
    on_status_change: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    """Run Coder → pytest-verify loop for a specific approved ticket.

    Status transitions emitted to queue and via on_status_change callback:
      coder_running  → Coder agent is editing source files
      qa_checking    → Pytest recheck is running (QA verify)
      done           → Tests green; PR entry recorded in pending-prs.jsonl
      error          → Max attempts exhausted
    """
    per_agent_budget = budget_usd / max(max_fix_attempts * 2, 1)

    ticket_path = project_path / ".smrt" / "tickets" / f"{ticket_id}.md"
    ticket_content = (
        ticket_path.read_text(encoding="utf-8")
        if ticket_path.exists()
        else f"Ticket {ticket_id}: content not found"
    )

    for attempt in range(max_fix_attempts):
        # ── Coder phase ──────────────────────────────────────────────────────
        if on_status_change:
            await on_status_change("coder_running")
        await queue.put({
            "type": "session_status",
            "status": "coder_running",
            "ticket_id": ticket_id,
            "fix_attempt": attempt,
            "ts": _ts(),
        })

        pytest_output = run_pytest(project_path)
        await run_coder_agent(
            project_path=project_path,
            api_key=api_key,
            model=model_coder,
            budget_usd=per_agent_budget,
            queue=queue,
            ticket_content=ticket_content,
            pytest_output=pytest_output,
        )

        # ── QA verification phase ─────────────────────────────────────────
        if on_status_change:
            await on_status_change("qa_checking")
        await queue.put({
            "type": "session_status",
            "status": "qa_checking",
            "ticket_id": ticket_id,
            "fix_attempt": attempt,
            "ts": _ts(),
        })

        recheck_output = run_pytest(project_path)
        await queue.put({
            "type": "recheck_output",
            "output": recheck_output[:2000],
            "ts": _ts(),
        })

        if "passed" in recheck_output and "failed" not in recheck_output:
            _record_pending_pr(project_path, ticket_id, session_id, recheck_output)
            await queue.put({
                "type": "pr_ready",
                "ticket_id": ticket_id,
                "session_id": session_id,
                "ts": _ts(),
            })
            await queue.put({
                "type": "session_status",
                "status": "done",
                "fix_attempt": attempt,
                "ts": _ts(),
            })
            return "done"

        await queue.put({
            "type": "fix_attempt_failed",
            "attempt": attempt + 1,
            "max_attempts": max_fix_attempts,
            "recheck": recheck_output[:500],
            "ts": _ts(),
        })

    await queue.put({
        "type": "session_status",
        "status": "error",
        "message": f"Max fix attempts ({max_fix_attempts}) reached without green tests",
        "ts": _ts(),
    })
    return "error"
