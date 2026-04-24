import pytest
from datetime import datetime, timezone
from smrt_agent.db.models import AgentRun, Project
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.db.schema import init_schema


@pytest.mark.asyncio
async def test_agent_run_round_trips(tmp_path, monkeypatch):
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))
    engine = get_engine(force_new=True)
    await init_schema(engine)
    Session = get_session_factory(engine)

    async with Session() as session:
        proj = Project(name="todo-api", canonical_path="/tmp/todo-api")
        session.add(proj)
        await session.flush()

        run = AgentRun(project_id=proj.id)
        session.add(run)
        await session.commit()
        await session.refresh(run)

        assert run.id is not None
        assert len(run.run_id) == 36  # UUID
        assert run.status == "pending"
        assert run.total_input_tokens == 0
        assert run.total_output_tokens == 0
        assert run.started_at is None
        assert run.completed_at is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_agent_run_status_update(tmp_path, monkeypatch):
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test2.db"))
    engine = get_engine(force_new=True)
    await init_schema(engine)
    Session = get_session_factory(engine)

    async with Session() as session:
        proj = Project(name="todo-api", canonical_path="/tmp/todo-api2")
        session.add(proj)
        await session.flush()

        run = AgentRun(project_id=proj.id)
        session.add(run)
        await session.commit()
        await session.refresh(run)

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        run.total_input_tokens = 500
        run.total_output_tokens = 200
        await session.commit()
        await session.refresh(run)

        assert run.status == "running"
        assert run.total_input_tokens == 500

    await engine.dispose()
