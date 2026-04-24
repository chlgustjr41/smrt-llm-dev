import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from smrt_agent.db.base import Base
from smrt_agent.db.models import Project, QASession
from smrt_agent.agents.orchestrator import run_qa_session
from smrt_agent.main import create_app
from smrt_agent.db.schema import init_schema
from smrt_agent.api.deps import get_db


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_qa_session_model(db):
    project = Project(name="test", canonical_path="/workspace/test")
    db.add(project)
    await db.commit()
    await db.refresh(project)

    qa = QASession(session_id="abc-123", project_id=project.id)
    db.add(qa)
    await db.commit()
    await db.refresh(qa)

    assert qa.session_id == "abc-123"
    assert qa.status == "pending"
    assert qa.fix_attempt == 0
    assert qa.ticket_id is None
    assert qa.started_at is None
    assert qa.completed_at is None


async def test_orchestrator_done_on_first_pass(tmp_path):
    """If QA agent returns no ticket, orchestrator returns 'done'."""
    queue = asyncio.Queue()
    hitl_events: dict = {}
    hitl_decisions: dict = {}

    with patch("smrt_agent.agents.orchestrator.run_qa_agent", new=AsyncMock(return_value=None)):
        status = await run_qa_session(
            session_id="sess-1",
            project_path=tmp_path,
            api_key="sk-test",
            model_qa="claude-sonnet-4-6",
            model_coder="claude-sonnet-4-6",
            budget_usd=1.0,
            max_fix_attempts=3,
            queue=queue,
            hitl_events=hitl_events,
            hitl_decisions=hitl_decisions,
        )

    assert status == "done"
    events = []
    while not queue.empty():
        events.append(await queue.get())
    assert any(e.get("status") == "done" for e in events)


async def test_orchestrator_skip_on_hitl_skip(tmp_path):
    """If HITL decision is 'skip', orchestrator returns 'skipped'."""
    queue = asyncio.Queue()
    hitl_events: dict = {}
    hitl_decisions: dict = {}
    session_id = "sess-skip"

    async def fake_qa_agent(**kwargs):
        return "2026-04-24-001"  # returns a ticket_id to trigger HITL

    async def set_skip_after_delay():
        await asyncio.sleep(0.05)
        event = hitl_events.get(session_id)
        if event:
            hitl_decisions[session_id] = "skip"
            event.set()

    with patch("smrt_agent.agents.orchestrator.run_qa_agent", new=fake_qa_agent):
        asyncio.create_task(set_skip_after_delay())
        status = await run_qa_session(
            session_id=session_id,
            project_path=tmp_path,
            api_key="sk-test",
            model_qa="claude-sonnet-4-6",
            model_coder="claude-sonnet-4-6",
            budget_usd=1.0,
            max_fix_attempts=3,
            queue=queue,
            hitl_events=hitl_events,
            hitl_decisions=hitl_decisions,
        )

    assert status == "skipped"


@pytest.fixture
async def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True)
    await init_schema(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    app = create_app()

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    await engine.dispose()


async def test_create_qa_session_404(app_client):
    resp = await app_client.post("/projects/9999/qa-sessions")
    assert resp.status_code == 404


async def test_stream_qa_session_404(app_client):
    resp = await app_client.get("/projects/1/qa-sessions/nonexistent/stream")
    assert resp.status_code == 404


async def test_approve_no_hitl_pending(app_client):
    resp = await app_client.post("/projects/1/qa-sessions/nonexistent/approve")
    assert resp.status_code == 409


async def test_skip_no_hitl_pending(app_client):
    resp = await app_client.post("/projects/1/qa-sessions/nonexistent/skip")
    assert resp.status_code == 409
