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
    _summarize_coder_evidence,
    run_ticket_fix_session,
)
from smrt_agent.event_log import EventLogger


def _make_logged_queue(tmp_path: Path, session_id: str) -> EventLogger:
    """Wrap a plain Queue with EventLogger so events tee to the same JSONL
    location production uses. _summarize_coder_evidence reads from this
    file, so without the wrapper it sees an empty log."""
    log_path = tmp_path / ".smrt" / "qa-sessions" / f"{session_id}.jsonl"
    return EventLogger(asyncio.Queue(), log_path)


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


# ── Coder-evidence helper: ground for the QA Final Summary ─────────────────

def _write_session_jsonl(tmp_path: Path, session_id: str, events: list[dict]) -> None:
    log_path = tmp_path / ".smrt" / "qa-sessions" / f"{session_id}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )


def test_summarize_coder_evidence_counts_edits_across_attempts(tmp_path):
    """Files written by the Coder across multiple attempts must all show up
    in files_edited, deduplicated by path."""
    _write_session_jsonl(tmp_path, "sess-edits", [
        {"type": "session_status", "status": "coder_running", "fix_attempt": 0},
        {"type": "tool_use", "agent": "coder", "tool": "write_source_file",
         "input": {"path": "users.py", "content": "def x(): pass"}},
        {"type": "tool_use", "agent": "coder", "tool": "write_source_file",
         "input": {"path": "auth.py", "content": "def y(): pass"}},
        {"type": "session_status", "status": "qa_checking", "fix_attempt": 0},
        {"type": "session_status", "status": "coder_running", "fix_attempt": 1},
        # Re-edit users.py on attempt 2 — should NOT double-count in files_edited
        {"type": "tool_use", "agent": "coder", "tool": "write_source_file",
         "input": {"path": "users.py", "content": "def x(): return 1"}},
        {"type": "session_status", "status": "qa_checking", "fix_attempt": 1},
    ])
    ev = _summarize_coder_evidence(tmp_path, "sess-edits")
    assert ev["total_edits"] == 3              # three write calls total
    assert ev["files_edited"] == ["users.py", "auth.py"]  # unique, in order


def test_summarize_coder_evidence_zero_edits_returns_empty(tmp_path):
    """When the Coder makes no file-write calls (the no-op case the user
    reported), total_edits MUST be 0 and files_edited MUST be empty so the
    QA prompt's no-op clause fires."""
    _write_session_jsonl(tmp_path, "sess-noop", [
        {"type": "session_status", "status": "coder_running", "fix_attempt": 0},
        {"type": "coder_text_delta", "agent": "coder",
         "text": "I examined the source. The bug appears to already be fixed; "
                 "the predicate now correctly excludes deleted items. "
                 "No changes needed."},
        {"type": "session_status", "status": "qa_checking", "fix_attempt": 0},
    ])
    ev = _summarize_coder_evidence(tmp_path, "sess-noop")
    assert ev["total_edits"] == 0
    assert ev["files_edited"] == []
    # The Coder's verdict is captured for the QA prompt to cite verbatim.
    assert "already be fixed" in ev["coder_final_reasoning"]
    assert "No changes needed" in ev["coder_final_reasoning"]


def test_summarize_coder_evidence_keeps_only_last_attempt_reasoning(tmp_path):
    """coder_final_reasoning must reflect the MOST RECENT attempt's verdict —
    earlier-attempt narration is stale and could mislead the QA."""
    _write_session_jsonl(tmp_path, "sess-multi", [
        {"type": "session_status", "status": "coder_running", "fix_attempt": 0},
        {"type": "coder_text_delta", "agent": "coder",
         "text": "First attempt: editing the wrong file."},
        {"type": "session_status", "status": "qa_checking", "fix_attempt": 0},
        {"type": "session_status", "status": "coder_running", "fix_attempt": 1},
        {"type": "coder_text_delta", "agent": "coder",
         "text": "Second attempt: this is the right place."},
        {"type": "session_status", "status": "qa_checking", "fix_attempt": 1},
    ])
    ev = _summarize_coder_evidence(tmp_path, "sess-multi")
    assert "Second attempt" in ev["coder_final_reasoning"]
    assert "First attempt" not in ev["coder_final_reasoning"]


def test_summarize_coder_evidence_handles_missing_log(tmp_path):
    """No JSONL file → returns the safe empty record so the QA Final Summary
    pass still runs (best-effort)."""
    ev = _summarize_coder_evidence(tmp_path, "sess-missing")
    assert ev == {"files_edited": [], "total_edits": 0, "coder_final_reasoning": ""}


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
async def test_qa_final_summary_prompt_includes_no_op_clause_when_coder_made_no_edits(tmp_path):
    """The user-reported bug: when the Coder makes no edits and tests pass
    (because the bug was already fixed), the QA Final Summary previously
    confabulated changes. The fix is to inject the verified evidence into
    the prompt and require the QA to cite zero edits.

    This test stubs the LLM and inspects the system prompt the QA receives
    to verify it carries the no-op signal — the model's actual behavior is
    a downstream concern, but we can guarantee the *information* gets to it."""
    project_path = tmp_path
    tickets_dir = project_path / ".smrt" / "tickets"
    tickets_dir.mkdir(parents=True)
    ticket_id = "2026-04-28-NO-OP"
    (tickets_dir / f"{ticket_id}.md").write_text(
        "# T\n\n**Title:** apparently fixed\n", encoding="utf-8"
    )

    # EventLogger wraps the queue so all session_status / coder_text_delta
    # events tee to .smrt/qa-sessions/<id>.jsonl. Without this, the
    # JSONL stays empty and _summarize_coder_evidence has nothing to read.
    queue = _make_logged_queue(tmp_path, "sess-noop-e2e")

    captured_systems: list[str] = []

    class _CapturingStub:
        async def stream_turn(self, *, system, tools, messages, model, on_text=None):
            # Capture every system prompt the LLM is asked to render under;
            # we'll inspect the QA Final Summary one for the no-op clause.
            captured_systems.append(system)
            text = "## What changed\nNo source files were modified during this fix loop."
            if on_text is not None:
                await on_text(text)
            return _StubResponse(text)

    stub_llm = _CapturingStub()

    async def fake_run_coder(**kwargs):
        # Simulate the bug-not-broken case: the Coder writes a clear verdict
        # but does NOT call any file-write tool. These events MUST end up in
        # the JSONL so _summarize_coder_evidence can read them.
        q = kwargs["queue"]
        await q.put({
            "type": "coder_text_delta",
            "agent": "coder",
            "text": "Looking at routers/products.py, the predicate already "
                    "correctly excludes deleted items. The bug appears to be "
                    "already fixed — no source change is needed.",
        })

    with patch("smrt_agent.agents.orchestrator.run_coder_agent", new=fake_run_coder), \
         patch("smrt_agent.agents.orchestrator.run_pytest", return_value="1 passed in 0.5s"), \
         patch("smrt_agent.agents.orchestrator.collect_coverage", return_value=None):
        status = await run_ticket_fix_session(
            session_id="sess-noop-e2e",
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
    assert len(captured_systems) >= 1, "QA Final Summary should have run"
    # The LAST system prompt is the QA Final Summary one.
    final_prompt = captured_systems[-1]

    # Verified evidence must be in the prompt.
    assert "VERIFIED EVIDENCE FROM AGENT LOG" in final_prompt
    assert "Total file edits the Coder made: 0" in final_prompt
    assert "Files edited (unique): (none)" in final_prompt
    # Coder's verdict surfaces verbatim so the QA can cite it.
    assert "already fixed" in final_prompt
    assert "no source change is needed" in final_prompt

    # The no-op clause must be present and emphatic — this is what stops
    # the model from confabulating fixes.
    assert "NO SOURCE FILES WERE MODIFIED" in final_prompt
    assert "DO NOT invent" in final_prompt
    assert "No source files were modified during this fix loop" in final_prompt


@pytest.mark.asyncio
async def test_qa_final_summary_prompt_omits_no_op_clause_when_coder_did_edit(tmp_path):
    """The mirror case: when the Coder DID edit files, the no-op clause
    must NOT appear (otherwise the QA would refuse to describe real
    changes)."""
    project_path = tmp_path
    tickets_dir = project_path / ".smrt" / "tickets"
    tickets_dir.mkdir(parents=True)
    ticket_id = "2026-04-28-EDITED"
    (tickets_dir / f"{ticket_id}.md").write_text("# T\n", encoding="utf-8")

    queue = _make_logged_queue(tmp_path, "sess-edited")
    captured_systems: list[str] = []

    class _CapturingStub:
        async def stream_turn(self, *, system, tools, messages, model, on_text=None):
            captured_systems.append(system)
            text = "## What changed\n- Edited routers/products.py"
            if on_text is not None:
                await on_text(text)
            return _StubResponse(text)

    async def fake_run_coder(**kwargs):
        q = kwargs["queue"]
        await q.put({
            "type": "tool_use", "agent": "coder", "tool": "write_source_file",
            "input": {"path": "routers/products.py", "content": "def fixed(): pass"},
        })

    with patch("smrt_agent.agents.orchestrator.run_coder_agent", new=fake_run_coder), \
         patch("smrt_agent.agents.orchestrator.run_pytest", return_value="1 passed in 0.5s"), \
         patch("smrt_agent.agents.orchestrator.collect_coverage", return_value=None):
        await run_ticket_fix_session(
            session_id="sess-edited",
            ticket_id=ticket_id,
            project_path=project_path,
            llm_client=_CapturingStub(),
            model_coder="model-c",
            budget_usd=1.0,
            max_fix_attempts=3,
            queue=queue,
            model_qa="model-q",
            max_questions_per_attempt=0,
        )

    final_prompt = captured_systems[-1]
    assert "Total file edits the Coder made: 1" in final_prompt
    assert "routers/products.py" in final_prompt
    # No-op clause MUST be absent when there were real edits.
    assert "NO SOURCE FILES WERE MODIFIED" not in final_prompt


@pytest.mark.asyncio
async def test_first_pass_success_emits_qa_final_summary_phase(tmp_path):
    """When tests pass on the first attempt the loop must STILL run the QA
    Final Summary pass — every successful ticket should have a qa_summarizing
    phase visible in the timeline AFTER Coder/QA Verify, plus a
    qa_final_summary event captured for the persisted Fix Summary."""
    project_path = tmp_path
    tickets_dir = project_path / ".smrt" / "tickets"
    tickets_dir.mkdir(parents=True)
    ticket_id = "2026-04-28-S1"
    (tickets_dir / f"{ticket_id}.md").write_text("# T\n\n**Title:** broken\n", encoding="utf-8")

    queue: asyncio.Queue = asyncio.Queue()
    # The QA model is invoked exactly once on the success path — for the
    # final summary. Stub it to return a markdown narrative.
    summary_text = (
        "## What the bug was\nThe predicate was inverted.\n\n"
        "## What changed\n- Flipped the condition in routers/products.py.\n\n"
        "## Why this works\nThe filter now correctly excludes deleted items.\n\n"
        "## Final test status\n1 passed in 0.5s"
    )
    stub_llm = _make_stub_llm_yielding(summary_text)

    coder_calls = []
    async def fake_run_coder(**kwargs):
        coder_calls.append(kwargs.get("attempt_index"))

    # Pytest passes on first attempt → success path is taken.
    with patch("smrt_agent.agents.orchestrator.run_coder_agent", new=fake_run_coder), \
         patch("smrt_agent.agents.orchestrator.run_pytest", return_value="1 passed in 0.5s"), \
         patch("smrt_agent.agents.orchestrator.collect_coverage", return_value=None):
        status = await run_ticket_fix_session(
            session_id="sess-success",
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
    assert coder_calls == [0]  # only one attempt was needed

    events = _drain_queue(queue)
    # Sequence requirement from the user: QA Final Summary phase appears
    # AFTER the Coder and QA Verify phases.
    statuses = [
        e["status"] for e in events
        if e.get("type") == "session_status"
    ]
    assert "coder_running" in statuses
    assert "qa_checking" in statuses
    assert "qa_summarizing" in statuses
    assert "done" in statuses
    # Order check: qa_summarizing must come after the LAST qa_checking and
    # before the terminal `done`.
    last_qa_check_idx = max(i for i, s in enumerate(statuses) if s == "qa_checking")
    summarizing_idx = statuses.index("qa_summarizing")
    done_idx = statuses.index("done")
    assert last_qa_check_idx < summarizing_idx < done_idx

    # The qa_final_summary event must carry the narrative we returned from
    # the stubbed LLM — this is what the persisted Fix Summary captures.
    final_summary_events = [e for e in events if e.get("type") == "qa_final_summary"]
    assert len(final_summary_events) == 1
    assert "## What the bug was" in final_summary_events[0]["summary"]
    assert "predicate was inverted" in final_summary_events[0]["summary"]


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
