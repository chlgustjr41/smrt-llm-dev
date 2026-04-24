"""QA session orchestrator: coordinates QA → HITL → Coder → recheck loop."""
import asyncio
from pathlib import Path

from smrt_agent.agents.qa.loop import run_qa_agent
from smrt_agent.agents.coder.loop import run_coder_agent
from smrt_agent.agents.qa.tools import run_pytest


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
        await queue.put({"type": "session_status", "status": "qa_running", "fix_attempt": attempt})

        ticket_id = await run_qa_agent(
            project_path=project_path,
            api_key=api_key,
            model=model_qa,
            budget_usd=per_agent_budget,
            queue=queue,
            prior_fix_context=prior_fix_context,
        )

        if ticket_id is None:
            await queue.put({"type": "session_status", "status": "done", "fix_attempt": attempt})
            return "done"

        if attempt >= max_fix_attempts:
            await queue.put({
                "type": "session_status",
                "status": "error",
                "message": "Max fix attempts reached",
            })
            return "error"

        # HITL gate — pause until user approves or skips
        await queue.put({
            "type": "hitl_request",
            "session_id": session_id,
            "ticket_id": ticket_id,
            "fix_attempt": attempt,
        })
        await queue.put({"type": "session_status", "status": "hitl_waiting"})

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
            })
            return "error"

        decision = hitl_decisions.pop(session_id, "skip")
        hitl_events.pop(session_id, None)

        if decision == "skip":
            await queue.put({"type": "session_status", "status": "skipped"})
            return "skipped"

        # Approved — run Coder agent
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

        # Subprocess recheck — no AI call
        recheck_output = run_pytest(project_path)
        await queue.put({"type": "recheck_output", "output": recheck_output[:2000]})

        if "passed" in recheck_output and "failed" not in recheck_output:
            await queue.put({
                "type": "session_status",
                "status": "done",
                "fix_attempt": attempt,
            })
            return "done"

        prior_fix_context = f"Fix attempt {attempt + 1} recheck:\n{recheck_output}"

    return "error"
