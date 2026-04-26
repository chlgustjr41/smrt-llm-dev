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


def _analyze_fix_failure(recheck_outputs: list[str]) -> dict[str, str]:
    """Heuristic: guess if ticket needs more attempts or isn't a real bug."""
    import re

    def count_failures(output: str) -> int:
        m = re.search(r"(\d+) failed", output)
        return int(m.group(1)) if m else 0

    if not recheck_outputs:
        return {
            "recommendation": "needs_more_attempts",
            "analysis": (
                "No recheck data was collected. The coder may not have produced any changes. "
                "Consider reviewing the ticket description or increasing the budget."
            ),
        }

    first_failures = count_failures(recheck_outputs[0])
    last_failures = count_failures(recheck_outputs[-1])
    all_same = all(count_failures(o) == first_failures for o in recheck_outputs)

    if all_same and first_failures == 0:
        return {
            "recommendation": "possibly_not_a_bug",
            "analysis": (
                f"All {len(recheck_outputs)} fix attempts completed with 0 test failures throughout. "
                "The existing test suite may not cover this issue, or the ticket may be a "
                "documentation gap, enhancement request, or false positive rather than an actual bug. "
                "Consider closing this ticket or adding a targeted test before re-queueing."
            ),
        }
    if all_same:
        return {
            "recommendation": "possibly_not_a_bug",
            "analysis": (
                f"All {len(recheck_outputs)} attempts produced the same failure count "
                f"({first_failures} failures) — the coder made no measurable progress. "
                "This often means: (1) the bug is in a location the coder cannot pinpoint from the "
                "ticket description alone, (2) the ticket description is ambiguous or incorrect, or "
                "(3) the fix requires architectural changes beyond what a single-pass coder can safely make."
            ),
        }
    if last_failures < first_failures:
        return {
            "recommendation": "needs_more_attempts",
            "analysis": (
                f"Failures decreased from {first_failures} → {last_failures} over "
                f"{len(recheck_outputs)} attempts — the coder is making progress. "
                "Increasing max_fix_attempts in Config or triggering a new fix session "
                "from the current state is likely to succeed."
            ),
        }
    return {
        "recommendation": "needs_more_attempts",
        "analysis": (
            f"After {len(recheck_outputs)} attempts tests still show {last_failures} failures. "
            "The coder's approach may need revision. Try reviewing the coder's changes manually, "
            "refining the ticket description, or increasing max_fix_attempts."
        ),
    }


def _record_failed_fix(
    project_path: Path, ticket_id: str, session_id: str, analysis: dict[str, str]
) -> None:
    """Append a loop-exhausted entry to .smrt/failed-fixes.jsonl."""
    log_path = project_path / ".smrt" / "failed-fixes.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ticket_id": ticket_id,
            "session_id": session_id,
            "recommendation": analysis["recommendation"],
            "analysis": analysis["analysis"],
            "ts": _ts(),
        }) + "\n")


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

    recheck_outputs: list[str] = []

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
        recheck_outputs.append(recheck_output)
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

    # All attempts exhausted — generate failure analysis and route to Needs Review
    analysis = _analyze_fix_failure(recheck_outputs)
    await asyncio.to_thread(_record_failed_fix, project_path, ticket_id, session_id, analysis)
    await queue.put({
        "type": "loop_exhausted",
        "ticket_id": ticket_id,
        "session_id": session_id,
        "attempts": max_fix_attempts,
        "recommendation": analysis["recommendation"],
        "analysis": analysis["analysis"],
        "ts": _ts(),
    })
    await queue.put({
        "type": "session_status",
        "status": "loop_exhausted",
        "message": f"Max fix attempts ({max_fix_attempts}) reached — routed to Needs Review",
        "ts": _ts(),
    })
    return "loop_exhausted"
