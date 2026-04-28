"""Budget pause gateway: bridges agent budget exhaustion with frontend decisions.

When an agent exceeds its budget ceiling, instead of hard-stopping it calls
handle_budget_pause(), which emits a budget_pause SSE event and waits up to
120 s for a human decision. The decision endpoint calls resolve() to unblock it.

Decision values: "continue" | "terminate"
On "continue": the agent gets a 20% grace extension and keeps running.
On "terminate" or timeout: budget_exceeded is emitted and the loop exits.
"""
import asyncio
from collections.abc import Callable

_pending: dict[str, "asyncio.Future[str]"] = {}

_PAUSE_TIMEOUT_S = 120.0
_GRACE_FACTOR = 0.20  # 20% of current ceiling added as grace


def resolve(job_id: str, decision: str) -> bool:
    """Resolve a pending budget pause. Returns True if there was one waiting."""
    fut = _pending.pop(job_id, None)
    if fut is None or fut.done():
        return False
    fut.set_result(decision)
    return True


async def handle_budget_pause(
    *,
    job_id: str | None,
    cost: float,
    budget_usd: float,
    queue: asyncio.Queue,
    total_input: int,
    total_output: int,
    ts_fn: Callable[[], str],
) -> tuple[bool, float]:
    """Handle a budget-exceeded condition.

    Returns (should_continue, new_budget_usd).

    If job_id is None: hard-stop (backward-compatible, no blocking).
    If job_id is set: emit budget_pause, await decision (120 s timeout),
    then either continue with a 20% grace extension or terminate.
    """
    if job_id is None:
        await queue.put({
            "type": "budget_exceeded",
            "cost_usd": round(cost, 4),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "ts": ts_fn(),
        })
        return False, budget_usd

    await queue.put({
        "type": "budget_pause",
        "cost_usd": round(cost, 4),
        "budget_usd": round(budget_usd, 4),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "ts": ts_fn(),
    })

    loop = asyncio.get_running_loop()
    fut: asyncio.Future[str] = loop.create_future()
    _pending[job_id] = fut

    try:
        decision = await asyncio.wait_for(asyncio.shield(fut), timeout=_PAUSE_TIMEOUT_S)
    except asyncio.TimeoutError:
        _pending.pop(job_id, None)
        decision = "terminate"
    except asyncio.CancelledError:
        _pending.pop(job_id, None)
        decision = "terminate"

    if decision == "continue":
        grace = budget_usd * _GRACE_FACTOR
        new_budget = cost + grace
        await queue.put({
            "type": "budget_continue",
            "grace_usd": round(grace, 4),
            "new_budget_usd": round(new_budget, 4),
            "ts": ts_fn(),
        })
        return True, new_budget

    await queue.put({
        "type": "budget_exceeded",
        "cost_usd": round(cost, 4),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "ts": ts_fn(),
    })
    return False, budget_usd
