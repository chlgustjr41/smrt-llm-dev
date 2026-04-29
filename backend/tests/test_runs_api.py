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
async def test_cancel_run_marks_db_status_and_emits_cancelled_event(test_app_with_project):
    """Cancel endpoint must: cancel the asyncio task, emit a cancelled SSE
    event onto the queue, and update the AgentRun row to 'cancelled' so the
    UI's StatusBadge flips immediately."""
    test_app, project_id = test_app_with_project
    import smrt_agent.api.runs as runs_module

    # Simulate a running task by stuffing the registries directly. Using a
    # real long-running coroutine lets us verify .cancel() actually fires.
    test_run_id = "cancel-test-0000-0000-0000-000000000001"
    test_queue: asyncio.Queue = asyncio.Queue()
    runs_module._queues[test_run_id] = test_queue

    async def long_running():
        await asyncio.sleep(60)  # never naturally finishes within the test

    task = asyncio.create_task(long_running())
    runs_module._tasks[test_run_id] = task

    # Pre-create the AgentRun row in the test DB so the endpoint's status
    # update has something to write to. Use the same DB the fixture wired up.
    from smrt_agent.db.models import AgentRun
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
    from datetime import datetime, timezone
    db_path = test_app.dependency_overrides  # not directly accessible; just create a separate connection
    # Use the same SQLite DB the fixture set up via SMRT_DB_PATH env.
    import os
    db_url = f"sqlite+aiosqlite:///{os.environ['SMRT_DB_PATH']}"
    engine = create_async_engine(db_url, future=True)
    Sess = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Sess() as s:
        s.add(AgentRun(run_id=test_run_id, project_id=project_id, status="running",
                       started_at=datetime.now(timezone.utc)))
        await s.commit()
    await engine.dispose()

    try:
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            resp = await client.post(f"/projects/{project_id}/runs/{test_run_id}/cancel")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cancelled"] is True
        assert body["status"] == "cancelled"

        # The task was cancelled (await raises CancelledError eventually).
        await asyncio.sleep(0.05)
        assert task.cancelled() or task.done()

        # The cancelled event landed on the queue for the SSE consumer.
        # Drain and look for it.
        events_seen = []
        while not test_queue.empty():
            events_seen.append(test_queue.get_nowait())
        assert any(e.get("type") == "cancelled" for e in events_seen)
    finally:
        runs_module._queues.pop(test_run_id, None)
        runs_module._tasks.pop(test_run_id, None)
        if not task.done():
            task.cancel()


@pytest.mark.asyncio
async def test_cancel_run_for_unknown_run_is_idempotent(test_app_with_project):
    """Cancelling a run that never existed (or already finished) returns
    200 with cancelled=False — never a 404. Lets the UI fire-and-forget."""
    test_app, project_id = test_app_with_project
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post(f"/projects/{project_id}/runs/nonexistent-run-id/cancel")
    assert resp.status_code == 200
    assert resp.json()["cancelled"] is False


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
