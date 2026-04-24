import pytest
from sqlalchemy import text
from smrt_agent.db.session import get_engine, get_session_factory


@pytest.mark.asyncio
async def test_engine_can_execute_select_one(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("SMRT_DB_PATH", str(db_path))

    engine = get_engine(force_new=True)
    Session = get_session_factory(engine)
    async with Session() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
    await engine.dispose()
