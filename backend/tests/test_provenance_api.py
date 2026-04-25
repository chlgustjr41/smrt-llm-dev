import json
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smrt_agent.main import app
from smrt_agent.db.schema import init_schema
from smrt_agent.db.models import Project
from smrt_agent.api.deps import get_db


@pytest.fixture
async def provenance_app(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SMRT_PROJECT_ROOT_ALLOWLIST", "")

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True
    )
    await init_schema(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as session:
        proj = Project(name="test-api", canonical_path=str(tmp_path))
        session.add(proj)
        await session.commit()
        await session.refresh(proj)
        project_id = proj.id

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app, project_id, tmp_path
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_provenance_empty(provenance_app):
    test_app, project_id, _ = provenance_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/provenance")
    assert resp.status_code == 200
    assert resp.json() == {"entries": []}


@pytest.mark.asyncio
async def test_list_provenance_with_entries(provenance_app):
    test_app, project_id, tmp_path = provenance_app
    smrt = tmp_path / ".smrt"
    smrt.mkdir(exist_ok=True)
    (smrt / "provenance.jsonl").write_text(
        json.dumps({
            "ticket": "BUG-001",
            "subagent": "coder_agent",
            "reasoning": "Fixed null pointer dereference",
            "sources_consulted": ["src/main.py"],
            "attempts": 2,
            "related_lessons_applied": ["always check for None before indexing"],
        }) + "\n",
        encoding="utf-8",
    )

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/provenance")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["ticket"] == "BUG-001"
    assert entries[0]["attempts"] == 2
    assert "src/main.py" in entries[0]["sources_consulted"]


@pytest.mark.asyncio
async def test_list_provenance_multiple_entries(provenance_app):
    test_app, project_id, tmp_path = provenance_app
    smrt = tmp_path / ".smrt"
    smrt.mkdir(exist_ok=True)
    lines = "\n".join([
        json.dumps({"ticket": "BUG-001", "subagent": "coder_agent", "reasoning": "r", "sources_consulted": [], "attempts": 1, "related_lessons_applied": []}),
        json.dumps({"ticket": "BUG-002", "subagent": "coder_agent", "reasoning": "r", "sources_consulted": [], "attempts": 3, "related_lessons_applied": []}),
    ]) + "\n"
    (smrt / "provenance.jsonl").write_text(lines, encoding="utf-8")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/provenance")
    assert len(resp.json()["entries"]) == 2


@pytest.mark.asyncio
async def test_provenance_404_for_unknown_project(provenance_app):
    test_app, _, _ = provenance_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/projects/99999/provenance")
    assert resp.status_code == 404
