from sqlalchemy.ext.asyncio import AsyncEngine

from smrt_agent.db.base import Base
from smrt_agent.db import models  # noqa: F401 — registers models on Base.metadata


async def init_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
