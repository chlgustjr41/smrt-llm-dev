import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from smrt_agent.db.base import Base
from smrt_agent.db.models import Project, QASession
from smrt_agent.agents.orchestrator import run_qa_session


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
