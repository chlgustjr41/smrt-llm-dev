import json
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smrt_agent.main import app
from smrt_agent.db.schema import init_schema
from smrt_agent.db.models import Project, AgentRun
from smrt_agent.api.deps import get_db


@pytest.fixture
async def stats_app(tmp_path, monkeypatch):
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

        run = AgentRun(
            run_id="run-test-001",
            project_id=project_id,
            status="done",
            total_input_tokens=1_000_000,
            total_output_tokens=500_000,
        )
        session.add(run)
        await session.commit()

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app, project_id, tmp_path
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_cost_returns_runs(stats_app):
    test_app, project_id, _ = stats_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/cost")
    assert resp.status_code == 200
    data = resp.json()
    assert "runs" in data
    assert len(data["runs"]) == 1
    run = data["runs"][0]
    assert run["run_id"] == "run-test-001"
    # 1M input @ $15/MTok = $15; 0.5M output @ $75/MTok = $37.5; total = $52.5
    assert abs(run["reviewer_cost_usd"] - 52.5) < 0.001
    assert run["qa_cost_usd"] == 0.0
    assert run["coder_cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_cost_404_for_unknown_project(stats_app):
    test_app, _, _ = stats_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/projects/99999/stats/cost")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_heatmap_returns_source_files(stats_app):
    test_app, project_id, tmp_path = stats_app
    (tmp_path / "main.py").write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Docs", encoding="utf-8")  # md excluded

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/heatmap")
    assert resp.status_code == 200
    files = {f["file"]: f for f in resp.json()["files"]}
    assert "main.py" in files
    assert files["main.py"]["loc"] >= 3
    assert "README.md" not in files


@pytest.mark.asyncio
async def test_heatmap_bugs_from_provenance(stats_app):
    test_app, project_id, tmp_path = stats_app
    (tmp_path / "handler.py").write_text("pass\n", encoding="utf-8")
    smrt = tmp_path / ".smrt"
    smrt.mkdir(exist_ok=True)
    (smrt / "provenance.jsonl").write_text(
        json.dumps({
            "ticket": "BUG-001",
            "subagent": "coder_agent",
            "reasoning": "r",
            "sources_consulted": ["handler.py"],
            "attempts": 1,
            "related_lessons_applied": [],
        }) + "\n",
        encoding="utf-8",
    )

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/heatmap")
    files = {f["file"]: f for f in resp.json()["files"]}
    assert files["handler.py"]["bugs_resolved"] == 1


@pytest.mark.asyncio
async def test_heatmap_excludes_ignored_dirs(stats_app):
    test_app, project_id, tmp_path = stats_app
    (tmp_path / "node_modules").mkdir(exist_ok=True)
    (tmp_path / "node_modules" / "dep.js").write_text("module.exports={}", encoding="utf-8")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/heatmap")
    files = {f["file"]: f for f in resp.json()["files"]}
    assert not any("node_modules" in k for k in files)


@pytest.mark.asyncio
async def test_doc_completeness_empty(stats_app):
    test_app, project_id, _ = stats_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/doc-completeness")
    assert resp.status_code == 200
    assert resp.json() == {"history": []}


@pytest.mark.asyncio
async def test_doc_completeness_with_history(stats_app):
    test_app, project_id, tmp_path = stats_app
    smrt = tmp_path / ".smrt"
    smrt.mkdir(exist_ok=True)
    (smrt / "doc_scores.jsonl").write_text(
        '{"ts": "2026-04-25T00:00:00Z", "score": 75.0, "ep_documented": 3, "ep_total": 4, "mod_documented": 1, "mod_total": 1}\n',
        encoding="utf-8",
    )

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/doc-completeness")
    history = resp.json()["history"]
    assert len(history) == 1
    assert history[0]["score"] == 75.0


@pytest.mark.asyncio
async def test_stats_404_for_unknown_project(stats_app):
    test_app, _, _ = stats_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        for path in [
            "/api/projects/99999/stats/heatmap",
            "/api/projects/99999/stats/doc-completeness",
        ]:
            resp = await client.get(path)
            assert resp.status_code == 404, path
