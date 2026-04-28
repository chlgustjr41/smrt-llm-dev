"""Fix-summary persistence tests — verifies the materialized view of a fix
session survives re-reads and round-trips through disk."""
import json
from pathlib import Path

from smrt_agent.fix_summary import (
    build_fix_summary_from_events,
    load_events_from_jsonl,
    load_fix_summary_for_session,
    load_fix_summary_for_ticket,
    save_fix_summary,
)


def _events_for_a_simple_fix() -> list[dict]:
    return [
        {"type": "session_status", "status": "coder_running", "fix_attempt": 0, "ts": "2026-04-28T10:00:00Z"},
        {"type": "coder_text_delta", "text": "I will edit users.py to fix the validation bug. ", "agent": "coder"},
        {
            "type": "tool_use",
            "agent": "coder",
            "tool": "write_source_file",
            "input": {"path": "users.py", "content": "def create_user(): return 200"},
            "ts": "2026-04-28T10:00:05Z",
        },
        {
            "type": "tool_result",
            "agent": "coder",
            "tool": "write_source_file",
            "result": "ok",
            "ts": "2026-04-28T10:00:05Z",
        },
        {"type": "session_status", "status": "qa_checking", "fix_attempt": 0, "ts": "2026-04-28T10:00:06Z"},
        {"type": "recheck_output", "output": "1 passed in 0.5s", "ts": "2026-04-28T10:00:07Z"},
        {"type": "pr_ready", "ticket_id": "T-1", "session_id": "S-1", "ts": "2026-04-28T10:00:07Z"},
        {"type": "session_status", "status": "done"},
        {"type": "done", "status": "done"},
    ]


def test_build_fix_summary_extracts_changes_recheck_and_status():
    events = _events_for_a_simple_fix()
    summary = build_fix_summary_from_events(
        events, ticket_id="T-1", session_id="S-1", final_status="done"
    )
    assert summary["ticket_id"] == "T-1"
    assert summary["session_id"] == "S-1"
    assert summary["final_status"] == "done"
    assert summary["pr_ready"] is True
    assert summary["recheck_output"] == "1 passed in 0.5s"
    assert summary["recommendation"] is None
    assert len(summary["changes"]) == 1
    assert summary["changes"][0]["path"] == "users.py"
    assert summary["changes"][0]["kind"] == "write"
    assert "create_user" in summary["changes"][0]["content"]
    # The text delta that arrived just before the tool call becomes the
    # reasoning attached to that change.
    assert "validation bug" in summary["changes"][0]["reasoning"]


def test_build_fix_summary_captures_loop_exhausted_recommendation():
    events = [
        {"type": "session_status", "status": "coder_running", "fix_attempt": 0, "ts": "2026-04-28T10:00:00Z"},
        {"type": "recheck_output", "output": "1 failed in 0.5s"},
        {
            "type": "loop_exhausted",
            "ticket_id": "T-2",
            "session_id": "S-2",
            "attempts": 1,
            "recommendation": "test_faulty",
            "analysis": "The test asserts 201 but spec returns 200.",
        },
        {"type": "session_status", "status": "loop_exhausted"},
    ]
    summary = build_fix_summary_from_events(
        events, ticket_id="T-2", session_id="S-2", final_status="loop_exhausted"
    )
    assert summary["recommendation"] == "test_faulty"
    assert "201" in summary["analysis"]
    assert summary["recheck_output"] == "1 failed in 0.5s"
    assert summary["pr_ready"] is False


def test_save_and_load_round_trip_for_ticket(tmp_path):
    summary = build_fix_summary_from_events(
        _events_for_a_simple_fix(),
        ticket_id="T-1",
        session_id="S-1",
        final_status="done",
    )
    save_fix_summary(tmp_path, summary)

    # File written under .smrt/fix-summaries/{session_id}.json
    file_path = tmp_path / ".smrt" / "fix-summaries" / "S-1.json"
    assert file_path.exists()

    # Index updated to point at this session
    index = json.loads((tmp_path / ".smrt" / "fix-summaries" / "index.json").read_text(encoding="utf-8"))
    assert index["T-1"] == "S-1"

    # load_fix_summary_for_ticket round-trips
    loaded = load_fix_summary_for_ticket(tmp_path, "T-1")
    assert loaded is not None
    assert loaded["session_id"] == "S-1"
    assert loaded["recheck_output"] == "1 passed in 0.5s"

    # load_fix_summary_for_session also works
    by_session = load_fix_summary_for_session(tmp_path, "S-1")
    assert by_session is not None
    assert by_session["ticket_id"] == "T-1"


def test_index_points_at_latest_session_when_ticket_is_requeued(tmp_path):
    """Re-queueing a ticket runs a NEW fix session. The on-disk per-session
    files must accumulate (one per session, kept indefinitely), and the index
    must always point at the most-recent session for the ticket."""
    # First session
    s1 = build_fix_summary_from_events([], ticket_id="T-9", session_id="sess-old", final_status="loop_exhausted")
    save_fix_summary(tmp_path, s1)
    # Second session — same ticket, new session_id
    s2 = build_fix_summary_from_events([], ticket_id="T-9", session_id="sess-new", final_status="done")
    save_fix_summary(tmp_path, s2)

    # Both per-session files exist.
    base = tmp_path / ".smrt" / "fix-summaries"
    assert (base / "sess-old.json").exists()
    assert (base / "sess-new.json").exists()

    # Index points at the newer session.
    latest = load_fix_summary_for_ticket(tmp_path, "T-9")
    assert latest is not None
    assert latest["session_id"] == "sess-new"
    assert latest["final_status"] == "done"


def test_load_returns_none_when_no_summary_recorded(tmp_path):
    assert load_fix_summary_for_ticket(tmp_path, "ghost-ticket") is None
    assert load_fix_summary_for_session(tmp_path, "ghost-session") is None


def test_load_events_from_jsonl_skips_malformed_lines(tmp_path):
    log_dir = tmp_path / ".smrt" / "qa-sessions"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "S-x.jsonl"
    log_path.write_text(
        '{"type": "good", "n": 1}\n'
        'this is not json\n'
        '\n'
        '{"type": "good", "n": 2}\n',
        encoding="utf-8",
    )
    events = load_events_from_jsonl(tmp_path, "S-x")
    assert [e["n"] for e in events] == [1, 2]


def test_load_events_returns_empty_when_log_missing(tmp_path):
    assert load_events_from_jsonl(tmp_path, "nonexistent-session") == []
