import asyncio
import json
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
from smrt_agent.main import app
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.db.schema import init_schema
from smrt_agent.db.models import Project
from smrt_agent.api.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
async def test_app_with_project(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SMRT_PROJECT_ROOT_ALLOWLIST", "")

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True)
    await init_schema(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as session:
        proj = Project(name="todo-api", canonical_path=str(tmp_path))
        session.add(proj)
        await session.commit()
        await session.refresh(proj)
        project_id = proj.id

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app, project_id
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_run_returns_202(test_app_with_project):
    test_app, project_id = test_app_with_project

    async def fake_run_reviewer(**_kwargs):
        pass

    with patch("smrt_agent.api.runs.run_reviewer", side_effect=fake_run_reviewer):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post(f"/projects/{project_id}/runs")

    assert resp.status_code == 202
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "pending"
    assert len(data["run_id"]) == 36


@pytest.mark.asyncio
async def test_create_run_propagates_generate_docs_flag(test_app_with_project):
    """The generate_docs flag in the POST body must reach the background
    _run_task intact. Default-true behavior is verified separately; this
    test pins down the false path so a future refactor can't silently
    always-on it.

    We patch _run_task itself (not run_reviewer) — that way the captured
    fake completes immediately and doesn't leave behind DB writes that
    would race with subsequent tests' fixture teardown.
    """
    test_app, project_id = test_app_with_project
    captured: dict = {}
    called = asyncio.Event()

    async def fake_run_task(**kwargs):
        captured["generate_docs"] = kwargs.get("generate_docs")
        called.set()

    with patch("smrt_agent.api.runs._run_task", side_effect=fake_run_task):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post(
                f"/projects/{project_id}/runs",
                json={"generate_docs": False},
            )
            assert resp.status_code == 202
            await asyncio.wait_for(called.wait(), timeout=2.0)

    assert captured.get("generate_docs") is False


@pytest.mark.asyncio
async def test_create_run_defaults_generate_docs_to_true_when_body_omitted(test_app_with_project):
    """Backward-compat: callers that POST with no body should still see
    documentation generated, matching pre-flag behavior."""
    test_app, project_id = test_app_with_project
    captured: dict = {}
    called = asyncio.Event()

    async def fake_run_task(**kwargs):
        captured["generate_docs"] = kwargs.get("generate_docs")
        called.set()

    with patch("smrt_agent.api.runs._run_task", side_effect=fake_run_task):
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post(f"/projects/{project_id}/runs")
            assert resp.status_code == 202
            await asyncio.wait_for(called.wait(), timeout=2.0)

    assert captured.get("generate_docs") is True


@pytest.mark.asyncio
async def test_create_run_for_unknown_project_returns_404(test_app_with_project):
    test_app, _ = test_app_with_project

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post("/projects/99999/runs")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stream_run_yields_sse_events(test_app_with_project):
    """Test SSE streaming by seeding the queue directly — avoids background-task timing."""
    test_app, project_id = test_app_with_project
    import smrt_agent.api.runs as runs_module

    # Use a deterministic run_id and seed the queue before the SSE client connects
    test_run_id = "feed0000-0000-0000-0000-000000000001"
    test_queue: asyncio.Queue = asyncio.Queue()
    await test_queue.put({"type": "text_delta", "text": "hello"})
    await test_queue.put({
        "type": "done",
        "total_input_tokens": 10,
        "total_output_tokens": 5,
        "cost_usd": 0.0,
    })
    runs_module._queues[test_run_id] = test_queue

    try:
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            stream_resp = await client.get(
                f"/projects/{project_id}/runs/{test_run_id}/stream",
                headers={"Accept": "text/event-stream"},
            )
    finally:
        runs_module._queues.pop(test_run_id, None)

    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers["content-type"]
    body = stream_resp.text
    events = [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:")]
    types = [e["type"] for e in events]
    assert "text_delta" in types
    assert "done" in types
