import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from smrt_agent.db.base import Base
from smrt_agent.db.models import Project, QASession


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
