"""Tests for EventLogger and events replay endpoints."""
import asyncio
import json
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

from smrt_agent.event_log import EventLogger
from smrt_agent.main import app
from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project


# ── EventLogger unit tests ──────────────────────────────────────────────────

async def test_event_logger_puts_to_inner_queue(tmp_path):
    inner: asyncio.Queue = asyncio.Queue()
    logger = EventLogger(inner, tmp_path / "events.jsonl")
    await logger.put({"type": "text_delta", "text": "hello"})
    assert not inner.empty()
    event = inner.get_nowait()
    assert event == {"type": "text_delta", "text": "hello"}


async def test_event_logger_writes_jsonl_file(tmp_path):
    inner: asyncio.Queue = asyncio.Queue()
    log_path = tmp_path / "events.jsonl"
    logger = EventLogger(inner, log_path)
    await logger.put({"type": "tool_use", "tool": "list_files"})
    await logger.put({"type": "done", "cost_usd": 0.001})
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"type": "tool_use", "tool": "list_files"}
    assert json.loads(lines[1]) == {"type": "done", "cost_usd": 0.001}


async def test_event_logger_creates_parent_dirs(tmp_path):
    inner: asyncio.Queue = asyncio.Queue()
    deep_path = tmp_path / "a" / "b" / "c" / "events.jsonl"
    logger = EventLogger(inner, deep_path)
    await logger.put({"type": "done"})
    assert deep_path.exists()


# ── Replay API tests ─────────────────────────────────────────────────────────

async def test_get_run_events_returns_stored_events(tmp_path):
    """GET /projects/1/runs/run-abc/events reads the JSONL log."""
    log_dir = tmp_path / ".smrt" / "runs"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "run-abc.jsonl"
    log_file.write_text(
        json.dumps({"type": "text_delta", "text": "hi"}) + "\n" +
        json.dumps({"type": "done"}) + "\n",
        encoding="utf-8",
    )

    async def override_db():
        db = AsyncMock()
        project = MagicMock(spec=Project)
        project.canonical_path = str(tmp_path)
        db.get = AsyncMock(return_value=project)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/projects/1/runs/run-abc/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"][0] == {"type": "text_delta", "text": "hi"}
        assert data["events"][1] == {"type": "done"}
    finally:
        app.dependency_overrides.clear()


async def test_get_run_events_returns_empty_when_no_log(tmp_path):
    async def override_db():
        db = AsyncMock()
        project = MagicMock(spec=Project)
        project.canonical_path = str(tmp_path)
        db.get = AsyncMock(return_value=project)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/projects/1/runs/nonexistent-run/events")
        assert resp.status_code == 200
        assert resp.json() == {"events": []}
    finally:
        app.dependency_overrides.clear()


async def test_get_run_events_404_for_unknown_project():
    async def override_db():
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/projects/999/runs/run-abc/events")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def test_get_qa_session_events_returns_stored_events(tmp_path):
    """GET /projects/1/qa-sessions/sess-abc/events reads the JSONL log."""
    log_dir = tmp_path / ".smrt" / "qa-sessions"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "sess-abc.jsonl"
    log_file.write_text(
        json.dumps({"type": "session_status", "status": "qa_running"}) + "\n",
        encoding="utf-8",
    )

    async def override_db():
        db = AsyncMock()
        project = MagicMock(spec=Project)
        project.canonical_path = str(tmp_path)
        db.get = AsyncMock(return_value=project)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/projects/1/qa-sessions/sess-abc/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"][0]["type"] == "session_status"
    finally:
        app.dependency_overrides.clear()
