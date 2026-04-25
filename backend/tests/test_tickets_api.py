"""Tests for the bug tickets API."""
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from smrt_agent.main import app
from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project


@pytest.fixture
def tickets_dir(tmp_path):
    """Creates a temp project directory with two ticket files."""
    smrt = tmp_path / ".smrt" / "tickets"
    smrt.mkdir(parents=True)
    (smrt / "2026-04-24-001.md").write_text(
        "# GET /items returns 404\nDescription: endpoint missing.", encoding="utf-8"
    )
    (smrt / "2026-04-24-002.md").write_text(
        "# POST /items ignores body\nDescription: input not saved.", encoding="utf-8"
    )
    return tmp_path


async def test_list_tickets_returns_empty_when_no_smrt_dir(tmp_path):
    async def override_db():
        from unittest.mock import AsyncMock, MagicMock
        db = AsyncMock()
        project = MagicMock(spec=Project)
        project.canonical_path = str(tmp_path)
        db.get = AsyncMock(return_value=project)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/projects/1/tickets")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()


async def test_list_tickets_returns_files(tickets_dir):
    async def override_db():
        from unittest.mock import AsyncMock, MagicMock
        db = AsyncMock()
        project = MagicMock(spec=Project)
        project.canonical_path = str(tickets_dir)
        db.get = AsyncMock(return_value=project)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/projects/1/tickets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        ids = [t["id"] for t in data]
        assert "2026-04-24-001" in ids
        assert "2026-04-24-002" in ids
        ticket = next(t for t in data if t["id"] == "2026-04-24-001")
        assert ticket["title"] == "GET /items returns 404"
        assert "Description" in ticket["content"]
    finally:
        app.dependency_overrides.clear()


async def test_list_tickets_404_for_unknown_project():
    async def override_db():
        from unittest.mock import AsyncMock
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/projects/999/tickets")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
