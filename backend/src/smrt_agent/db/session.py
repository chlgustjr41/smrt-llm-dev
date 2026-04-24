import os
from pathlib import Path
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None


def _resolve_db_path() -> Path:
    custom = os.getenv("SMRT_DB_PATH")
    if custom:
        p = Path(custom)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    home = Path.home() / ".smrt"
    home.mkdir(parents=True, exist_ok=True)
    return home / "state.db"


def get_engine(force_new: bool = False) -> AsyncEngine:
    global _engine
    if _engine is None or force_new:
        path = _resolve_db_path()
        _engine = create_async_engine(
            f"sqlite+aiosqlite:///{path}",
            echo=False,
            future=True,
        )
    return _engine


def get_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
