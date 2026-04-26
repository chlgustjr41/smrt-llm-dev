"""Tests for the PR surface API."""
import json
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from smrt_agent.main import app
from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project


def _make_override(path: Path):
    async def override_db():
        from unittest.mock import AsyncMock, MagicMock
        db = AsyncMock()
        project = MagicMock(spec=Project)
        project.canonical_path = str(path)
        db.get = AsyncMock(return_value=project)
        yield db
    return override_db


async def test_list_pending_prs_empty(tmp_path):
    app.dependency_overrides[get_db] = _make_override(tmp_path)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/projects/1/pr/pending")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()


async def test_list_pending_prs_returns_entries(tmp_path):
    smrt = tmp_path / ".smrt"
    smrt.mkdir()
    pr_log = smrt / "pending-prs.jsonl"
    pr_log.write_text(
        json.dumps({"ticket_id": "2026-04-24-001", "session_id": "sess-1", "recheck_output": "1 passed", "fixed_at": "2026-04-24T10:00:00Z"}) + "\n",
        encoding="utf-8"
    )
    app.dependency_overrides[get_db] = _make_override(tmp_path)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/projects/1/pr/pending")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["ticket_id"] == "2026-04-24-001"
    finally:
        app.dependency_overrides.clear()


async def test_accept_pr_appends_bugs_resolved(tmp_path):
    smrt = tmp_path / ".smrt"
    smrt.mkdir()
    pr_log = smrt / "pending-prs.jsonl"
    pr_log.write_text(
        json.dumps({"ticket_id": "2026-04-24-001", "session_id": "sess-1", "recheck_output": "1 passed", "fixed_at": "2026-04-24T10:00:00Z"}) + "\n",
        encoding="utf-8"
    )
    app.dependency_overrides[get_db] = _make_override(tmp_path)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/projects/1/pr/2026-04-24-001/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        # PR entry removed
        remaining = [l for l in pr_log.read_text().splitlines() if l.strip()]
        assert remaining == []
        # bugs-resolved.md updated
        resolved = (smrt / "bugs-resolved.md").read_text(encoding="utf-8")
        assert "2026-04-24-001" in resolved
    finally:
        app.dependency_overrides.clear()


async def test_reject_pr_removes_entry(tmp_path):
    smrt = tmp_path / ".smrt"
    smrt.mkdir()
    pr_log = smrt / "pending-prs.jsonl"
    pr_log.write_text(
        json.dumps({"ticket_id": "2026-04-24-001", "session_id": "sess-1", "recheck_output": "1 passed", "fixed_at": "2026-04-24T10:00:00Z"}) + "\n",
        encoding="utf-8"
    )
    app.dependency_overrides[get_db] = _make_override(tmp_path)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/projects/1/pr/2026-04-24-001/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
        # PR entry removed, bugs-resolved NOT updated
        remaining = [l for l in pr_log.read_text().splitlines() if l.strip()]
        assert remaining == []
        assert not (smrt / "bugs-resolved.md").exists()
    finally:
        app.dependency_overrides.clear()


async def test_accept_pr_404_for_unknown_ticket(tmp_path):
    app.dependency_overrides[get_db] = _make_override(tmp_path)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/projects/1/pr/nonexistent/accept")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
