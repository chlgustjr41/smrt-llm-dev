"""Orchestrator outcome tests — focus on the QA Advisor's three-way verdict:
CASE A (satisfied), CASE B (more attempts), CASE C (test_faulty)."""
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from smrt_agent.agents import orchestrator
from smrt_agent.agents.orchestrator import (
    _QA_SATISFIED_SIGNAL,
    _QA_TEST_FAULTY_SIGNAL,
    _faulty_test_analysis,
    run_ticket_fix_session,
)


def test_faulty_test_analysis_includes_advice_and_attempt_number():
    advice = "Replace the assertion `assert response.status_code == 201` with `== 200`."
    out = _faulty_test_analysis(advice, attempt=1)
    assert out["recommendation"] == "test_faulty"
    assert "attempt 2" in out["analysis"]
    assert advice in out["analysis"]


def test_faulty_test_analysis_handles_empty_advice():
    out = _faulty_test_analysis("", attempt=0)
    assert out["recommendation"] == "test_faulty"
    # Falls back to a default explanation rather than producing an empty body.
    assert ".smrt/tests/" in out["analysis"]


# ── Helpers ────────────────────────────────────────────────────────────────

class _StubResponse:
    """Minimal stand-in for LLMClient.stream_turn return shape."""
    def __init__(self, text: str, *, input_tokens: int = 100, output_tokens: int = 50):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.stop_reason = "end_turn"
        self.blocks = []


def _make_stub_llm_yielding(text: str):
    """Build an AsyncMock LLMClient whose stream_turn streams `text` and returns
    a response object with the same text via on_text callback."""
    async def stream_turn(*, system, tools, messages, model, on_text=None):
        if on_text is not None:
            await on_text(text)
        return _StubResponse(text)

    stub = AsyncMock()
    stub.stream_turn = stream_turn
    return stub


def _drain_queue(queue: asyncio.Queue) -> list[dict]:
    out = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


# ── CASE C: QA Advisor declares the test faulty ────────────────────────────

@pytest.mark.asyncio
async def test_qa_advisor_test_faulty_routes_to_needs_review(tmp_path):
    """When QA Advisor emits [QA_TEST_FAULTY], the loop halts on the first
    failed attempt, no retries happen, and a failed-fixes.jsonl entry is
    written with recommendation='test_faulty'."""
    # Set up project + ticket on disk
    project_path = tmp_path
    tickets_dir = project_path / ".smrt" / "tickets"
    tickets_dir.mkdir(parents=True)
    ticket_id = "2026-04-28-001"
    ticket_path = tickets_dir / f"{ticket_id}.md"
    ticket_path.write_text("# Bug Ticket\n\n**Title:** broken endpoint\n", encoding="utf-8")

    queue: asyncio.Queue = asyncio.Queue()

    # The QA Advisor responds with the test-faulty token; the body explains
    # which test file needs updating.
    qa_advice_body = (
        "The test asserts a 201 response but the spec returns 200. "
        "Update .smrt/tests/test_users.py to expect 200."
    )
    qa_text = f"{qa_advice_body}\n\n{_QA_TEST_FAULTY_SIGNAL}"
    stub_llm = _make_stub_llm_yielding(qa_text)

    coder_calls = []

    async def fake_run_coder(**kwargs):
        # Capture attempt context that's passed to the coder so we can assert
        # on the awareness-injection behavior.
        coder_calls.append({
            "attempt_index": kwargs.get("attempt_index"),
            "max_fix_attempts": kwargs.get("max_fix_attempts"),
        })

    # Pytest is "failing" — orchestrator decides to ask QA for advice.
    fake_pytest_output = "test_users.py::test_create FAILED\n1 failed in 0.5s"

    with patch("smrt_agent.agents.orchestrator.run_coder_agent", new=fake_run_coder), \
         patch("smrt_agent.agents.orchestrator.run_pytest", return_value=fake_pytest_output), \
         patch("smrt_agent.agents.orchestrator.collect_coverage", return_value=None):
        status = await run_ticket_fix_session(
            session_id="sess-1",
            ticket_id=ticket_id,
            project_path=project_path,
            llm_client=stub_llm,
            model_coder="model-c",
            budget_usd=1.0,
            max_fix_attempts=3,
            queue=queue,
            model_qa="model-q",
            max_questions_per_attempt=0,
        )

    # Loop halted on first failed attempt — no retries.
    assert status == "loop_exhausted"
    assert len(coder_calls) == 1
    assert coder_calls[0] == {"attempt_index": 0, "max_fix_attempts": 3}

    # failed-fixes.jsonl was written with recommendation='test_faulty' and
    # the QA's advice body baked into the analysis.
    failed_log = project_path / ".smrt" / "failed-fixes.jsonl"
    assert failed_log.exists()
    entries = [json.loads(l) for l in failed_log.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(entries) == 1
    assert entries[0]["ticket_id"] == ticket_id
    assert entries[0]["recommendation"] == "test_faulty"
    assert qa_advice_body in entries[0]["analysis"]

    # The session_status:loop_exhausted message names the test-faulty cause.
    events = _drain_queue(queue)
    loop_exhausted = [e for e in events if e.get("type") == "session_status" and e.get("status") == "loop_exhausted"]
    assert len(loop_exhausted) == 1
    assert "test faulty" in loop_exhausted[0]["message"].lower()


# ── CASE B: feedback gets numbered and accumulated for next attempt ──────

@pytest.mark.asyncio
async def test_case_b_feedback_is_numbered_per_attempt(tmp_path):
    """When QA gives plain CASE B feedback (no signal token), it should be
    appended to the ticket content with a numbered header so the Coder on
    the next attempt can read prior reasoning chronologically."""
    project_path = tmp_path
    tickets_dir = project_path / ".smrt" / "tickets"
    tickets_dir.mkdir(parents=True)
    ticket_id = "2026-04-28-002"
    (tickets_dir / f"{ticket_id}.md").write_text(
        "# Original ticket\n\n**Title:** broken thing\n", encoding="utf-8"
    )

    queue: asyncio.Queue = asyncio.Queue()
    feedback_body = "Try reading users.py and check the validation branch."
    stub_llm = _make_stub_llm_yielding(feedback_body)  # no signal → CASE B

    seen_ticket_contents = []

    async def fake_run_coder(**kwargs):
        seen_ticket_contents.append(kwargs["ticket_content"])

    with patch("smrt_agent.agents.orchestrator.run_coder_agent", new=fake_run_coder), \
         patch("smrt_agent.agents.orchestrator.run_pytest", return_value="1 failed"), \
         patch("smrt_agent.agents.orchestrator.collect_coverage", return_value=None):
        status = await run_ticket_fix_session(
            session_id="sess-2",
            ticket_id=ticket_id,
            project_path=project_path,
            llm_client=stub_llm,
            model_coder="model-c",
            budget_usd=1.0,
            max_fix_attempts=3,
            queue=queue,
            model_qa="model-q",
            max_questions_per_attempt=0,
        )

    assert status == "loop_exhausted"  # all 3 attempts failed without signal
    assert len(seen_ticket_contents) == 3

    # Attempt 0: original ticket only.
    assert "# Original ticket" in seen_ticket_contents[0]
    assert "QA feedback after attempt" not in seen_ticket_contents[0]

    # Attempt 1: original + numbered feedback from attempt 1.
    assert "QA feedback after attempt 1 of 3" in seen_ticket_contents[1]
    assert feedback_body in seen_ticket_contents[1]

    # Attempt 2: contains both numbered headers (1 of 3 and 2 of 3).
    assert "QA feedback after attempt 1 of 3" in seen_ticket_contents[2]
    assert "QA feedback after attempt 2 of 3" in seen_ticket_contents[2]


# ── CASE A still works (regression) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_case_a_satisfied_still_marks_pr_ready(tmp_path):
    """CASE A (QA satisfied) must continue to route to PR-ready, despite
    the new third-outcome branch."""
    project_path = tmp_path
    tickets_dir = project_path / ".smrt" / "tickets"
    tickets_dir.mkdir(parents=True)
    ticket_id = "2026-04-28-003"
    (tickets_dir / f"{ticket_id}.md").write_text("# T\n", encoding="utf-8")

    queue: asyncio.Queue = asyncio.Queue()
    qa_text = f"Looks good — failing tests are unrelated.\n\n{_QA_SATISFIED_SIGNAL}"
    stub_llm = _make_stub_llm_yielding(qa_text)

    async def fake_run_coder(**kwargs):
        return None

    with patch("smrt_agent.agents.orchestrator.run_coder_agent", new=fake_run_coder), \
         patch("smrt_agent.agents.orchestrator.run_pytest", return_value="1 failed"), \
         patch("smrt_agent.agents.orchestrator.collect_coverage", return_value=None):
        status = await run_ticket_fix_session(
            session_id="sess-3",
            ticket_id=ticket_id,
            project_path=project_path,
            llm_client=stub_llm,
            model_coder="model-c",
            budget_usd=1.0,
            max_fix_attempts=3,
            queue=queue,
            model_qa="model-q",
            max_questions_per_attempt=0,
        )
    assert status == "done"
    pending = project_path / ".smrt" / "pending-prs.jsonl"
    assert pending.exists()
    entries = [json.loads(l) for l in pending.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(e["ticket_id"] == ticket_id for e in entries)
