"""Tests for Project.md lessons update on PR accept/reject."""
import json
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from smrt_agent.main import app
from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project
from smrt_agent.knowledge import append_lesson


def _make_override(path: Path):
    async def override_db():
        from unittest.mock import AsyncMock, MagicMock
        db = AsyncMock()
        project = MagicMock(spec=Project)
        project.canonical_path = str(path)
        db.get = AsyncMock(return_value=project)
        yield db
    return override_db


def _make_pending_pr(path: Path, ticket_id: str = "2026-04-24-001") -> None:
    smrt = path / ".smrt"
    smrt.mkdir(exist_ok=True)
    pr_log = smrt / "pending-prs.jsonl"
    with pr_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ticket_id": ticket_id,
            "session_id": "sess-1",
            "recheck_output": "1 passed",
            "fixed_at": "2026-04-24T10:00:00Z",
        }) + "\n")


def test_append_lesson_creates_lessons_section_in_existing_file(tmp_path):
    smrt = tmp_path / ".smrt"
    smrt.mkdir()
    project_md = smrt / "Project.md"
    project_md.write_text("# Project: test\n\n## Purpose\nA test project.\n", encoding="utf-8")
    append_lesson(tmp_path, "2026-04-24-001", "accepted", "Fixed null pointer.")
    text = project_md.read_text(encoding="utf-8")
    assert "## Lessons" in text
    assert "2026-04-24-001 (accepted)" in text
    assert "Fixed null pointer." in text


def test_append_lesson_appends_to_existing_lessons_section(tmp_path):
    smrt = tmp_path / ".smrt"
    smrt.mkdir()
    project_md = smrt / "Project.md"
    project_md.write_text(
        "# Project: test\n\n## Lessons\n\n- **OLD-001 (accepted)**: Prior fix.\n",
        encoding="utf-8"
    )
    append_lesson(tmp_path, "2026-04-24-002", "rejected", "Bad fix.")
    text = project_md.read_text(encoding="utf-8")
    assert "OLD-001" in text
    assert "2026-04-24-002 (rejected)" in text
    assert "Bad fix." in text


def test_append_lesson_creates_file_and_section_when_neither_exist(tmp_path):
    smrt = tmp_path / ".smrt"
    smrt.mkdir()
    # No Project.md exists yet
    append_lesson(tmp_path, "2026-04-24-001", "accepted", "First fix ever.")
    project_md = smrt / "Project.md"
    assert project_md.exists()
    text = project_md.read_text(encoding="utf-8")
    assert "## Lessons" in text
    assert "2026-04-24-001 (accepted)" in text


def test_append_lesson_inserts_before_next_section(tmp_path):
    smrt = tmp_path / ".smrt"
    smrt.mkdir()
    project_md = smrt / "Project.md"
    project_md.write_text(
        "# Project: test\n\n## Lessons\n\n## Next Section\nContent.\n",
        encoding="utf-8"
    )
    append_lesson(tmp_path, "2026-04-24-001", "accepted", "Inserted fix.")
    text = project_md.read_text(encoding="utf-8")
    lesson_pos = text.index("2026-04-24-001")
    next_section_pos = text.index("## Next Section")
    assert lesson_pos < next_section_pos


async def test_accept_pr_updates_project_md(tmp_path):
    smrt = tmp_path / ".smrt"
    smrt.mkdir()
    (smrt / "tickets").mkdir()
    (smrt / "tickets" / "2026-04-24-001.md").write_text(
        "# Fixed null pointer\n\nDetails here.", encoding="utf-8"
    )
    _make_pending_pr(tmp_path)
    app.dependency_overrides[get_db] = _make_override(tmp_path)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/projects/1/pr/2026-04-24-001/accept")
        assert resp.status_code == 200
        project_md = (smrt / "Project.md").read_text(encoding="utf-8")
        assert "## Lessons" in project_md
        assert "2026-04-24-001 (accepted)" in project_md
    finally:
        app.dependency_overrides.clear()


async def test_reject_pr_updates_project_md_and_rejections_log(tmp_path):
    smrt = tmp_path / ".smrt"
    smrt.mkdir()
    (smrt / "tickets").mkdir()
    (smrt / "tickets" / "2026-04-24-001.md").write_text(
        "# Missing input validation\n\nDetails here.", encoding="utf-8"
    )
    _make_pending_pr(tmp_path)
    app.dependency_overrides[get_db] = _make_override(tmp_path)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/projects/1/pr/2026-04-24-001/reject",
                json={"reason": "Regression introduced in auth module"},
            )
        assert resp.status_code == 200
        project_md = (smrt / "Project.md").read_text(encoding="utf-8")
        assert "## Lessons" in project_md
        assert "2026-04-24-001 (rejected)" in project_md
        # Check rejections.jsonl
        rejections = json.loads((smrt / "rejections.jsonl").read_text(encoding="utf-8").strip())
        assert rejections["ticket_id"] == "2026-04-24-001"
        assert "Regression introduced" in rejections["reason"]
    finally:
        app.dependency_overrides.clear()


async def test_reject_pr_uses_default_reason_when_no_body(tmp_path):
    smrt = tmp_path / ".smrt"
    smrt.mkdir()
    _make_pending_pr(tmp_path)
    app.dependency_overrides[get_db] = _make_override(tmp_path)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/projects/1/pr/2026-04-24-001/reject")
        assert resp.status_code == 200
        rejections = json.loads((smrt / "rejections.jsonl").read_text(encoding="utf-8").strip())
        assert rejections["reason"] == "No reason given"
    finally:
        app.dependency_overrides.clear()
