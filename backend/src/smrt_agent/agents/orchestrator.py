"""QA session orchestrator: coordinates QA → HITL → Coder → recheck loop."""
import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

from smrt_agent.agents.qa.loop import run_qa_agent
from smrt_agent.agents.coder.loop import run_coder_agent
from smrt_agent.agents.qa.tools import run_pytest, collect_coverage
from smrt_agent.agents.qa.budget import compute_cost_usd as _qa_cost
from smrt_agent.llm import LLMClient, NormalizedTextBlock


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


def _faulty_test_analysis(qa_advice: str, attempt: int) -> dict[str, str]:
    """Build the failure-report payload when QA Advisor declares the test itself
    is buggy. The QA's own analysis (qa_advice) is the substantive payload —
    typically a description of which test file is wrong and how to update it."""
    body = qa_advice.strip() or (
        "QA Advisor flagged the generated test file as faulty but did not "
        "provide a specific update. Manually review .smrt/tests/ for the "
        "test exercising this ticket."
    )
    return {
        "recommendation": "test_faulty",
        "analysis": (
            f"After attempt {attempt + 1}, the QA Advisor concluded that the "
            f"generated test itself is buggy — not the source code under test. "
            f"The fix loop was halted to avoid wasting attempts on a test that "
            f"would never pass.\n\n"
            f"QA Advisor explanation and proposed test-file update:\n\n{body}"
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


_QA_SATISFIED_SIGNAL = "[QA_SATISFIED]"
_QA_TEST_FAULTY_SIGNAL = "[QA_TEST_FAULTY]"


async def _get_qa_feedback(
    *,
    ticket_content: str,
    recheck_output: str,
    attempt: int,
    max_fix_attempts: int,
    llm_client: LLMClient,
    model: str,
    queue: asyncio.Queue,
    ticket_id: str = "",
    session_id: str = "",
) -> tuple[str, bool, bool]:
    """Ask QA agent to analyze a failed fix and produce guidance for the next attempt.

    Returns (feedback_text, satisfied, test_faulty):
      - satisfied=True  → CASE A: QA declared the fix complete despite failing
                         tests (unrelated failures). Loop ends as success (PR ready).
      - test_faulty=True → CASE C: QA declared the generated test itself buggy.
                         Loop ends as failure routed to Needs Review with a
                         test-update request.
      - both False      → CASE B: actionable feedback for the next attempt.

    Emits session_status "qa_advising", streams qa_text_delta events, and
    emits qa_feedback_done.
    """
    await queue.put({
        "type": "session_status",
        "status": "qa_advising",
        "fix_attempt": attempt,
        "ts": _ts(),
    })

    attempts_left = max(0, max_fix_attempts - attempt - 1)
    is_last = attempts_left == 0
    budget_note = (
        f"Loop budget: this was attempt {attempt + 1} of {max_fix_attempts}"
        f" — {attempts_left} attempt(s) remain. "
        + (
            "After this verdict the loop ENDS (no more retries), so be decisive."
            if is_last
            else "Your CASE B feedback should be precise enough that the next "
            "attempt does not repeat the same approach."
        )
    )

    system = (
        "You are the senior QA engineer who wrote the bug ticket below. "
        "The coder has made a fix attempt. Analyze the pytest output carefully.\n\n"
        f"{budget_note}\n\n"
        "CASE A — the fix IS correct: all failures are unrelated to the bug (e.g. pre-existing "
        "flaky tests, environmental issues, or tests for other features). "
        "In that case, explain why the fix is correct and end your response with the exact token: "
        f"{_QA_SATISFIED_SIGNAL}\n\n"
        "CASE B — the fix is NOT correct AND the bug is real: provide specific, actionable "
        "guidance for the next attempt (3-5 sentences). Identify exactly what was wrong with the "
        "previous approach so the next attempt does not repeat it. Focus on the root cause and "
        "what to try differently. Do NOT include either signal token.\n\n"
        "CASE C — the GENERATED TEST itself is buggy (not the source code): the test has wrong "
        "assertions, the wrong endpoint URL, the wrong fixture setup, an incorrect status code "
        "expectation, or otherwise asserts behavior the spec does not require. In that case the "
        "coder will never make this test pass even with a perfect fix. Explain which test file "
        "needs updating and exactly what the corrected test should look like (1-3 paragraphs, "
        "with a code-block snippet of the corrected test if helpful), then end your response "
        "with the exact token: "
        f"{_QA_TEST_FAULTY_SIGNAL}\n\n"
        "Choose CASE C only when you are confident the test is the problem, not the source — "
        "this halts the loop and routes the ticket to human review."
    )
    user_msg = (
        f"Original bug ticket:\n{ticket_content}\n\n"
        f"Fix attempt {attempt + 1} pytest output:\n```\n{recheck_output}\n```\n\n"
        "Is the fix correct (CASE A), is the source still wrong (CASE B), "
        "or is the generated test itself faulty (CASE C)? Respond accordingly."
    )
    messages: list[dict] = [{"role": "user", "content": user_msg}]
    collected: list[str] = []

    async def on_text(text: str) -> None:
        collected.append(text)
        await queue.put({"type": "qa_text_delta", "text": text, "agent": "qa", "ts": _ts()})

    response = await llm_client.stream_turn(
        system=system,
        tools=[],
        messages=messages,
        model=model,
        on_text=on_text,
    )

    raw = "".join(collected).strip()
    # CASE C wins over CASE A if (somehow) both tokens were emitted — declaring
    # the test faulty is the more conservative outcome (routes to human review
    # instead of marking ready-to-merge).
    test_faulty = _QA_TEST_FAULTY_SIGNAL in raw
    satisfied = (not test_faulty) and (_QA_SATISFIED_SIGNAL in raw)
    feedback = raw.replace(_QA_SATISFIED_SIGNAL, "").replace(_QA_TEST_FAULTY_SIGNAL, "").strip()

    feedback_cost = _qa_cost(response.input_tokens, response.output_tokens, model)
    await queue.put({
        "type": "qa_feedback_done",
        "model": model,
        "total_input_tokens": response.input_tokens,
        "total_output_tokens": response.output_tokens,
        "cost_usd": round(feedback_cost, 6),
        "ts": _ts(),
    })

    if satisfied:
        await queue.put({
            "type": "qa_early_exit",
            "ticket_id": ticket_id,
            "session_id": session_id,
            "reasoning": feedback,
            "ts": _ts(),
        })

    return feedback, satisfied, test_faulty


async def run_qa_session(
    *,
    session_id: str,
    project_path: Path,
    llm_client: LLMClient,
    model_qa: str,
    model_coder: str,
    budget_usd: float,
    max_fix_attempts: int = 0,
    max_questions_per_attempt: int = 0,
    queue: asyncio.Queue,
    job_id: str | None = None,
) -> str:
    """Run one QA discovery pass. Files tickets into pending_confirmation; coder loop is
    triggered separately when the user approves a ticket via the kanban board."""
    await queue.put({
        "type": "session_status",
        "status": "qa_running",
        "fix_attempt": 0,
        "ts": _ts(),
    })

    ticket_id = await run_qa_agent(
        project_path=project_path,
        llm_client=llm_client,
        model=model_qa,
        budget_usd=budget_usd,
        queue=queue,
        job_id=job_id,
    )

    if ticket_id is None:
        await queue.put({
            "type": "session_status",
            "status": "done",
            "fix_attempt": 0,
            "ts": _ts(),
        })
        return "done"

    # Ticket filed — emit hitl_request so the frontend can count tickets filed,
    # then immediately end the session. The ticket stays in pending_confirmation
    # until the user approves it via the kanban board.
    await queue.put({
        "type": "hitl_request",
        "session_id": session_id,
        "ticket_id": ticket_id,
        "fix_attempt": 0,
        "ts": _ts(),
    })
    await queue.put({
        "type": "session_status",
        "status": "done",
        "fix_attempt": 0,
        "ts": _ts(),
    })
    return "done"


async def run_ticket_fix_session(
    *,
    session_id: str,
    ticket_id: str,
    project_path: Path,
    llm_client: LLMClient,
    model_coder: str,
    budget_usd: float,
    max_fix_attempts: int,
    queue: asyncio.Queue,
    on_status_change: Callable[[str], Awaitable[None]] | None = None,
    model_qa: str | None = None,
    max_questions_per_attempt: int = 0,
    job_id: str | None = None,
) -> str:
    """Run Coder → pytest-verify loop for a specific approved ticket.

    Status transitions emitted to queue and via on_status_change callback:
      coder_running  → Coder agent is editing source files
      qa_checking    → Pytest recheck is running (QA verify)
      done           → Tests green; PR entry recorded in pending-prs.jsonl
      error          → Max attempts exhausted
    """
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
            llm_client=llm_client,
            model=model_coder,
            budget_usd=budget_usd,
            queue=queue,
            ticket_content=ticket_content,
            pytest_output=pytest_output,
            llm_client_qa=llm_client if model_qa else None,
            model_qa=model_qa,
            max_questions=max_questions_per_attempt,
            job_id=job_id,
            attempt_index=attempt,
            max_fix_attempts=max_fix_attempts,
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
            await asyncio.to_thread(collect_coverage, project_path)
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

        # Run the QA Advisor on every failed attempt — including the last one.
        # On the last attempt it can still declare CASE C (test_faulty), which
        # routes the ticket to a more useful Needs Review state than the
        # generic loop-exhausted heuristic would produce.
        if model_qa:
            qa_advice, qa_satisfied, qa_test_faulty = await _get_qa_feedback(
                ticket_content=ticket_content,
                recheck_output=recheck_output,
                attempt=attempt,
                max_fix_attempts=max_fix_attempts,
                llm_client=llm_client,
                model=model_qa,
                queue=queue,
                ticket_id=ticket_id,
                session_id=session_id,
            )
            if qa_satisfied:
                # CASE A: QA advisor declared the fix complete despite failing tests
                _record_pending_pr(project_path, ticket_id, session_id, recheck_output)
                await asyncio.to_thread(collect_coverage, project_path)
                await queue.put({"type": "pr_ready", "ticket_id": ticket_id, "session_id": session_id, "ts": _ts()})
                await queue.put({"type": "session_status", "status": "done", "fix_attempt": attempt, "ts": _ts()})
                return "done"
            if qa_test_faulty:
                # CASE C: the generated test itself is buggy. Halt the loop and
                # route to Needs Review with a test-update recommendation —
                # further attempts would be wasted on an unwinnable test.
                analysis = _faulty_test_analysis(qa_advice, attempt)
                await asyncio.to_thread(_record_failed_fix, project_path, ticket_id, session_id, analysis)
                await queue.put({
                    "type": "loop_exhausted",
                    "ticket_id": ticket_id,
                    "session_id": session_id,
                    "attempts": attempt + 1,
                    "recommendation": analysis["recommendation"],
                    "analysis": analysis["analysis"],
                    "ts": _ts(),
                })
                await queue.put({
                    "type": "session_status",
                    "status": "loop_exhausted",
                    "message": (
                        "QA Advisor declared the generated test faulty — "
                        "routed to Needs Review with test-update request"
                    ),
                    "ts": _ts(),
                })
                return "loop_exhausted"
            # CASE B: append numbered feedback so the next Coder attempt can
            # learn from the previous failure and avoid repeating the approach.
            if attempt < max_fix_attempts - 1:
                ticket_content = (
                    ticket_content
                    + f"\n\n---\n## QA feedback after attempt {attempt + 1} of {max_fix_attempts}\n\n"
                    + qa_advice
                )

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
