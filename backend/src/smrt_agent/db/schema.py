from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from smrt_agent.db.base import Base
from smrt_agent.db import models  # noqa: F401 — registers models on Base.metadata


async def init_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migration: add config column to projects if it doesn't exist yet
        try:
            await conn.execute(
                text("ALTER TABLE projects ADD COLUMN config VARCHAR(4096) NOT NULL DEFAULT '{}'")
            )
        except Exception:
            # Column already exists — safe to ignore
            pass
