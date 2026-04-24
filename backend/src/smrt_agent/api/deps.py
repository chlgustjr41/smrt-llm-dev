from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from smrt_agent.db.session import get_engine, get_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    engine = get_engine()
    Session = get_session_factory(engine)
    async with Session() as session:
        yield session
