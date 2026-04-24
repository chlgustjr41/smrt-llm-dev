import pytest
from datetime import datetime
from smrt_agent.db.models import Project
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.db.schema import init_schema


@pytest.mark.asyncio
async def test_project_persists_and_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))
    engine = get_engine(force_new=True)
    await init_schema(engine)
    Session = get_session_factory(engine)

    async with Session() as session:
        p = Project(name="todo-api", canonical_path="/tmp/todo-api")
        session.add(p)
        await session.commit()
        await session.refresh(p)
        assert p.id is not None
        assert isinstance(p.created_at, datetime)

    await engine.dispose()
