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


async def test_list_tickets_includes_status_closed_for_resolved(tmp_path):
    """Tickets mentioned in bugs-resolved.md get status 'closed'."""
    smrt = tmp_path / ".smrt"
    (smrt / "tickets").mkdir(parents=True)
    (smrt / "tickets" / "2026-04-24-001.md").write_text("# Bug\nDetails.", encoding="utf-8")
    (smrt / "bugs-resolved.md").write_text("## 2026-04-24-001\n\nFixed it.", encoding="utf-8")

    async def override_db():
        from unittest.mock import AsyncMock, MagicMock
        db = AsyncMock()
        project = MagicMock(spec=Project)
        project.canonical_path = str(tmp_path)
        db.get = AsyncMock(return_value=project)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/projects/1/tickets")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["status"] == "closed"
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


async def test_approve_ticket_creates_session_and_starts_task(tmp_path):
    """approve_ticket records the ticket as in-progress and returns a session_id."""
    from unittest.mock import AsyncMock, MagicMock, patch

    smrt = tmp_path / ".smrt" / "tickets"
    smrt.mkdir(parents=True)
    (smrt / "2026-04-24-001.md").write_text("# Bug\nDetails.", encoding="utf-8")

    async def override_db():
        db = AsyncMock()
        project = MagicMock(spec=Project)
        project.canonical_path = str(tmp_path)
        project.id = 1
        db.get = AsyncMock(return_value=project)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("smrt_agent.api.tickets.asyncio.create_task") as mock_task, \
             patch("smrt_agent.api.tickets.Settings") as MockSettings:
            mock_task.return_value = None
            MockSettings.return_value.anthropic_api_key = "sk-test"
            MockSettings.return_value.model_coder = "claude-haiku-4-5-20251001"
            MockSettings.return_value.budget_per_run_usd = 1.0
            MockSettings.return_value.max_fix_attempts = 3

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/projects/1/tickets/2026-04-24-001/approve")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ticket_id"] == "2026-04-24-001"
        assert data["status"] == "in_progress"
        assert "session_id" in data and data["session_id"] is not None

        # Ticket appears in the in-progress file
        ip_path = tmp_path / ".smrt" / "in-progress-tickets.txt"
        assert ip_path.exists()
        assert "2026-04-24-001" in ip_path.read_text()

        mock_task.assert_called_once()
    finally:
        app.dependency_overrides.clear()


async def test_approve_ticket_404_for_missing_ticket(tmp_path):
    """approve_ticket returns 404 when the ticket file does not exist."""
    from unittest.mock import AsyncMock, MagicMock

    (tmp_path / ".smrt" / "tickets").mkdir(parents=True)

    async def override_db():
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
            resp = await client.post("/projects/1/tickets/nonexistent-ticket/approve")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
