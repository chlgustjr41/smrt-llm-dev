# SMRT Agent v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship SMRT Agent v1 — a multi-agent QA-engineer + junior-developer system for Python FastAPI codebases — in five phases, each producing a runnable artifact.

**Architecture:** Python 3.11 FastAPI backend orchestrates Claude Agent SDK subagents (Reviewer/QA/Coder), runs target apps in ephemeral Docker sandboxes, and exposes a React+Vite frontend on `127.0.0.1`. Per-project state lives in `<target>/.smrt/`; cross-project state in `~/.smrt/state.db`.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy 2.x async · aiosqlite · pydantic-settings · pytest + httpx · `claude-agent-sdk` · `docker` Python SDK · `pathspec` · `watchfiles` · APScheduler · React 18 · TypeScript · Vite · Tailwind CSS · Radix UI primitives.

---

## Plan organization

This is a **multi-phase project**. Per the writing-plans skill's scope rule, the project is decomposed into five phase-level plans, each producing working/testable software on its own. This document is the **master plan**:

- §A — Phase coverage matrix (which spec sections land in which phase)
- §B — **P1 detailed bite-sized tasks** (the only phase with full TDD step-level detail today)
- §C — P2–P5 phase summaries (detailed bite-sized plans written when each phase begins)
- §D — Self-review checklist

When P1 ships and merges to `main`, the next session re-invokes the writing-plans skill to produce `docs/superpowers/plans/<date>-smrt-llm-dev-p2-plan.md` with full bite-sized detail. Speculative bite-sized steps for P3–P5 today would violate the no-placeholders rule because we'd be guessing at types and signatures hours before designing them.

**One issue per task.** Each numbered Task in §B becomes one GitHub issue, labeled `phase:1` plus a category label (`backend`, `frontend`, `sandbox`, `fixture`, `infra`). Issues are created **after** you approve this plan, **before** P1 implementation starts.

---

## §A. Phase coverage matrix

| Spec section (PRODUCTION.md) | P1 | P2 | P3 | P4 | P5 |
|---|:-:|:-:|:-:|:-:|:-:|
| §1 Product summary (read-only) | — | — | — | — | — |
| §2.1 Reviewer agent | — | ✅ | — | — | — |
| §2.2 QA agent | — | — | ✅ | — | — |
| §2.3 Coder agent | — | — | ✅ | — | — |
| §3 Sandbox (ephemeral, lifecycle, safety, secret guard) | ✅ | — | — | — | — |
| §3.4 Secret protection (gitignore-aware) | ✅ | — | — | — | — |
| §4.1 Triggers (scheduler + watcher + manual) | — | — | ✅ | — | — |
| §4.2 Reviewer test plan artifact | — | ✅ | — | — | — |
| §4.3 Logical-bug detection (mutation/hypothesis/diff) | — | — | ✅ | — | — |
| §4.4 QA bug ticket schema | — | — | ✅ | — | — |
| §4.5 QA↔Coder blackbox feedback loop | — | — | ✅ | — | — |
| §4.6 Failure report on cap hit | — | — | ✅ | — | — |
| §4.7 PR preparation on acceptance | — | — | ✅ | — | — |
| §5.1 Project.md initialization audit | — | ✅ | — | — | — |
| §5.2 Memory files (bugs-resolved, test-status) | — | — | ✅ | — | — |
| §5.3–5.4 Skill acquisition + Explain mode | — | — | — | — | ✅ |
| §6.1 GitHub-native docs backend | — | — | — | ✅ | — |
| §6.2 Obsidian vault backend | — | — | — | ✅ | — |
| §6.3 Beta backends (Jira/Confluence stubs) | — | — | — | ✅ | — |
| §7.1 Stack + bind-address security | ✅ | — | — | — | — |
| §7.2 Screens (Projects/Detail/Live/Approvals) | ✅ (Projects only) | ✅ (Detail+Live) | ✅ (Tickets+Approvals) | ✅ (Docs tab) | ✅ (Overview dashboards) |
| §7.3 Live observability (4-layer) | — | ✅ | ✅ | — | — |
| §7.4 Three Overview-tab dashboards | — | — | — | — | ✅ |
| §7.5 HITL approval surface + thought-process mode | — | — | ✅ | — | ✅ (toggle) |
| §7.6 Project registration flow | ✅ | — | — | — | — |
| §7.7 Replay + history | — | — | — | — | ✅ |
| §8.1 File watcher + commit trigger | — | — | ✅ | — | — |
| §8.2 Periodic full checkup (APScheduler) | — | ✅ | — | — | — |
| §8.3 Budget guardrails | — | ✅ | — | — | ✅ (UI display) |
| §9.1 SDK orchestration (root agent) | — | ✅ | ✅ | — | — |
| §9.2 Context isolation | — | ✅ | ✅ | — | — |
| §9.3 HITL permission handler | — | — | ✅ | — | ✅ (thought-process mode) |
| §9.4 Session management + PreCompact archive | — | ✅ | — | — | — |
| §9.5 Structured output (JSON schemas) | — | ✅ | ✅ | — | — |
| §9.6 Prompts (reviewer.md, qa.md, coder.md) | — | ✅ | ✅ | — | — |
| §10 Repository layout | ✅ (skeleton) | ✅ (backend/agents/) | ✅ (db expansion) | ✅ (docs/ backends) | ✅ (eval-fixtures finalization) |
| §11 Secrets, privacy, cross-platform | ✅ | — | — | — | — |
| §12 Evaluation rubric mapping | — | — | — | — | ✅ |
| §15 Definition of done checklist | — | — | — | — | ✅ |

---

## §B. Phase 1 (P1) — Foundation: detailed plan

**Goal at end of P1:** `docker compose up` boots backend (FastAPI on `127.0.0.1:8000`) + frontend (Vite on `127.0.0.1:5173`). UI lists registered projects and lets you register the local `eval-fixtures/todo-api/` path. A "Build sandbox" button triggers the cross-platform Docker wrapper to build + start an isolated container running the todo-api fixture, then health-checks it. No agents yet — just the rails everything else runs on.

**Branch:** `phase/1-foundation`. Open PR into `main` when all P1 tasks pass.

### Task 1: Create the P1 feature branch

**Files:** none yet

- [ ] **Step 1: Create and switch to the phase branch**

```bash
cd D:/web-project/smrt-llm-dev
git checkout -b phase/1-foundation
```

Expected: `Switched to a new branch 'phase/1-foundation'`

---

### Task 2: Initialize the backend Python project

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.python-version`
- Create: `backend/src/__init__.py`
- Create: `backend/src/smrt_agent/__init__.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create `backend/.python-version` pinning Python 3.11**

```
3.11
```

- [ ] **Step 2: Create `backend/pyproject.toml`**

```toml
[project]
name = "smrt-agent-backend"
version = "0.1.0"
description = "SMRT Agent backend — FastAPI orchestration for Claude Agent SDK subagents"
requires-python = ">=3.11,<3.12"
dependencies = [
    "fastapi>=0.110,<0.120",
    "uvicorn[standard]>=0.29,<0.40",
    "pydantic>=2.6,<3",
    "pydantic-settings>=2.2,<3",
    "sqlalchemy[asyncio]>=2.0,<3",
    "aiosqlite>=0.19,<0.21",
    "alembic>=1.13,<2",
    "httpx>=0.27,<0.30",
    "docker>=7.0,<8",
    "pathspec>=0.12,<0.13",
    "watchfiles>=0.21,<1",
    "apscheduler>=3.10,<4",
    "claude-agent-sdk>=0.0.10",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8,<9",
    "pytest-asyncio>=0.23,<1",
    "pytest-cov>=4,<6",
    "ruff>=0.4,<1",
    "mypy>=1.10,<2",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/smrt_agent"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "B", "UP", "ASYNC"]
ignore = ["E501"]
```

- [ ] **Step 3: Create empty package init files**

```bash
touch backend/src/__init__.py backend/src/smrt_agent/__init__.py backend/tests/__init__.py
```

- [ ] **Step 4: Create `backend/tests/conftest.py` with the asyncio loop fixture**

```python
import asyncio
import pytest


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

- [ ] **Step 5: Verify install works**

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest --collect-only
```

Expected: `collected 0 items` (no tests yet, but pytest discovery succeeds)

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat(backend): initialize Python 3.11 project with pyproject.toml"
```

---

### Task 3: Backend Settings module (TDD)

**Files:**
- Create: `backend/src/smrt_agent/settings.py`
- Create: `backend/tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_settings.py
import os
from smrt_agent.settings import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("SMRT_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("SMRT_BACKEND_PORT", "8000")

    s = Settings()

    assert s.anthropic_api_key == "sk-ant-test-key"
    assert s.bind_host == "127.0.0.1"
    assert s.backend_port == 8000


def test_settings_defaults_without_overrides(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-only-required")
    monkeypatch.delenv("SMRT_BIND_HOST", raising=False)

    s = Settings()
    assert s.bind_host == "127.0.0.1"
    assert s.backend_port == 8000
    assert s.budget_per_run_usd == 1.50
    assert s.max_fix_attempts == 5


def test_settings_rejects_missing_api_key(monkeypatch):
    import pytest
    from pydantic import ValidationError
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings()
```

- [ ] **Step 2: Run the test — expect failure**

```bash
cd backend
pytest tests/test_settings.py -v
```

Expected: `ImportError: cannot import name 'Settings' from 'smrt_agent.settings'`

- [ ] **Step 3: Implement `backend/src/smrt_agent/settings.py`**

```python
"""Application settings loaded from environment / .env file."""
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Required ───────────────────────────────────────────
    anthropic_api_key: str = Field(..., description="Anthropic API key")

    # ─── Bind address ───────────────────────────────────────
    bind_host: str = Field(default="127.0.0.1", alias="smrt_bind_host")
    backend_port: int = Field(default=8000, alias="smrt_backend_port")
    frontend_port: int = Field(default=5173, alias="smrt_frontend_port")

    # ─── Budget guardrails ─────────────────────────────────
    budget_per_run_usd: float = Field(default=1.50, alias="smrt_budget_per_run_usd")
    budget_per_day_usd: float = Field(default=10.00, alias="smrt_budget_per_day_usd")

    # ─── Models ────────────────────────────────────────────
    model_reviewer: str = Field(default="claude-opus-4-7", alias="smrt_model_reviewer")
    model_qa: str = Field(default="claude-sonnet-4-6", alias="smrt_model_qa")
    model_coder: str = Field(default="claude-sonnet-4-6", alias="smrt_model_coder")

    # ─── Loop caps ─────────────────────────────────────────
    max_fix_attempts: int = Field(default=5, alias="smrt_max_fix_attempts")
    max_questions_per_attempt: int = Field(default=1, alias="smrt_max_questions_per_attempt")

    # ─── Path allowlist ────────────────────────────────────
    project_root_allowlist: str = Field(default="", alias="smrt_project_root_allowlist")

    # ─── Observability ─────────────────────────────────────
    log_level: str = Field(default="INFO", alias="smrt_log_level")

    @property
    def allowed_project_roots(self) -> list[str]:
        return [p.strip() for p in self.project_root_allowlist.split(",") if p.strip()]
```

- [ ] **Step 4: Run the test — expect pass**

```bash
pytest tests/test_settings.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/settings.py backend/tests/test_settings.py
git commit -m "feat(backend): Settings module with .env loading and defaults"
```

---

### Task 4: FastAPI app skeleton with health endpoint (TDD)

**Files:**
- Create: `backend/src/smrt_agent/main.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from smrt_agent.main import app


@pytest.mark.asyncio
async def test_health_returns_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_health.py -v
```

Expected: ImportError

- [ ] **Step 3: Implement `backend/src/smrt_agent/main.py`**

```python
"""FastAPI application entrypoint."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from smrt_agent.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Future: scheduler start, DB engine init
    yield
    # Future: graceful shutdown


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(
        title="SMRT Agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS for the local frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://{settings.bind_host}:{settings.frontend_port}"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": app.version}

    return app


app = create_app()
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_health.py -v
```

Expected: 1 passed

- [ ] **Step 5: Smoke-test live server**

```bash
uvicorn smrt_agent.main:app --host 127.0.0.1 --port 8000
# In another terminal:
curl http://127.0.0.1:8000/health
```

Expected: `{"status":"ok","version":"0.1.0"}`

- [ ] **Step 6: Commit**

```bash
git add backend/src/smrt_agent/main.py backend/tests/test_health.py
git commit -m "feat(backend): FastAPI app with /health endpoint"
```

---

### Task 5: SQLite/SQLAlchemy async setup

**Files:**
- Create: `backend/src/smrt_agent/db/__init__.py`
- Create: `backend/src/smrt_agent/db/base.py`
- Create: `backend/src/smrt_agent/db/session.py`
- Create: `backend/tests/test_db_session.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_db_session.py
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
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement `backend/src/smrt_agent/db/base.py`**

```python
"""SQLAlchemy declarative base."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 4: Implement `backend/src/smrt_agent/db/session.py`**

```python
"""Async SQLite engine + session factory."""
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
        return Path(custom)
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
```

- [ ] **Step 5: Implement `backend/src/smrt_agent/db/__init__.py`**

```python
from smrt_agent.db.base import Base
from smrt_agent.db.session import get_engine, get_session_factory

__all__ = ["Base", "get_engine", "get_session_factory"]
```

- [ ] **Step 6: Run — expect pass**

- [ ] **Step 7: Commit**

```bash
git add backend/src/smrt_agent/db/ backend/tests/test_db_session.py
git commit -m "feat(backend): async SQLite engine and session factory"
```

---

### Task 6: Project model and DB schema creation

**Files:**
- Create: `backend/src/smrt_agent/db/models.py`
- Create: `backend/src/smrt_agent/db/schema.py`
- Create: `backend/tests/test_project_model.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_project_model.py
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
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement `backend/src/smrt_agent/db/models.py`**

```python
"""SQLAlchemy models for cross-project state."""
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from smrt_agent.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 4: Implement `backend/src/smrt_agent/db/schema.py`**

```python
"""Schema initialization (lightweight; Alembic added in P3 if needed)."""
from sqlalchemy.ext.asyncio import AsyncEngine

from smrt_agent.db.base import Base
# Import models so they register on Base.metadata
from smrt_agent.db import models  # noqa: F401


async def init_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 5: Run — expect pass**

- [ ] **Step 6: Commit**

```bash
git add backend/src/smrt_agent/db/models.py backend/src/smrt_agent/db/schema.py backend/tests/test_project_model.py
git commit -m "feat(backend): Project model and schema initialization"
```

---

### Task 7: Path normalization helper (cross-platform)

**Files:**
- Create: `backend/src/smrt_agent/platform_paths.py`
- Create: `backend/tests/test_platform_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_platform_paths.py
import sys
import pytest
from pathlib import PurePosixPath, PureWindowsPath

from smrt_agent.platform_paths import canonicalize, to_docker_mount


def test_canonicalize_returns_posix_string():
    if sys.platform == "win32":
        assert canonicalize("D:\\web-project\\foo") == "/d/web-project/foo"
    else:
        assert canonicalize("/Users/jdoe/foo") == "/Users/jdoe/foo"


def test_canonicalize_rejects_dotdot():
    with pytest.raises(ValueError, match="parent traversal"):
        canonicalize("/foo/../bar")


def test_to_docker_mount_windows_form(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    assert to_docker_mount("D:\\web-project\\foo") == "//d/web-project/foo"


def test_to_docker_mount_posix_passthrough(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    assert to_docker_mount("/Users/jdoe/foo") == "/Users/jdoe/foo"
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement `backend/src/smrt_agent/platform_paths.py`**

```python
"""Cross-platform path normalization at the registration boundary.

All internal logic uses POSIX-style strings regardless of host OS. Windows
drive letters are rewritten as /d/, /c/, etc.
"""
import re
import sys
from pathlib import Path, PurePosixPath


_WIN_DRIVE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def canonicalize(host_path: str) -> str:
    """Convert a host-OS path to a canonical POSIX-style string.

    - Resolves the path to an absolute form (without requiring it to exist)
    - Rejects any input containing parent-traversal segments (`..`)
    - Translates Windows drive letters to /<letter>/
    """
    if ".." in Path(host_path).parts:
        raise ValueError(f"parent traversal not allowed: {host_path!r}")

    if sys.platform == "win32":
        m = _WIN_DRIVE.match(host_path)
        if m:
            drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
            return str(PurePosixPath(f"/{drive}/{rest}"))
    return str(PurePosixPath(Path(host_path).as_posix()))


def to_docker_mount(host_path: str) -> str:
    """Translate a host path into a string usable in a Docker bind-mount.

    Windows uses //d/foo form; POSIX uses the path as-is.
    """
    if sys.platform == "win32":
        m = _WIN_DRIVE.match(host_path)
        if m:
            drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
            return f"//{drive}/{rest}"
    return host_path
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/platform_paths.py backend/tests/test_platform_paths.py
git commit -m "feat(backend): cross-platform path normalization helper"
```

---

### Task 8: Project registry API — POST and GET endpoints (TDD)

**Files:**
- Create: `backend/src/smrt_agent/api/__init__.py`
- Create: `backend/src/smrt_agent/api/projects.py`
- Modify: `backend/src/smrt_agent/main.py` — wire the router
- Create: `backend/tests/test_projects_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_projects_api.py
import pytest
from httpx import AsyncClient, ASGITransport

from smrt_agent.main import create_app
from smrt_agent.db.session import get_engine
from smrt_agent.db.schema import init_schema


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    engine = get_engine(force_new=True)
    await init_schema(engine)

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_and_list_project(client, tmp_path):
    target = tmp_path / "todo-api"
    target.mkdir()

    resp = await client.post("/api/projects", json={"path": str(target)})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "todo-api"
    assert body["id"] > 0

    list_resp = await client.get("/api/projects")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_register_rejects_dotdot(client):
    resp = await client.post("/api/projects", json={"path": "/foo/../bar"})
    assert resp.status_code == 400
    assert "parent traversal" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_rejects_nonexistent_path(client, tmp_path):
    resp = await client.post("/api/projects", json={"path": str(tmp_path / "ghost")})
    assert resp.status_code == 404
    assert "does not exist" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_refuses_self_registration(client, monkeypatch):
    # smrt-llm-dev itself must not be registerable as a target
    monkeypatch.setenv("SMRT_SELF_PATH", "/web/smrt-llm-dev")
    resp = await client.post("/api/projects", json={"path": "/web/smrt-llm-dev"})
    assert resp.status_code == 400
    assert "self-registration" in resp.json()["detail"]
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement `backend/src/smrt_agent/api/projects.py`**

```python
"""Project registration and listing endpoints."""
import os
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from smrt_agent.db.models import Project
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.platform_paths import canonicalize


router = APIRouter(prefix="/api/projects", tags=["projects"])


class RegisterRequest(BaseModel):
    path: str


class ProjectOut(BaseModel):
    id: int
    name: str
    canonical_path: str
    created_at: datetime


def _validate_path(host_path: str) -> str:
    """Canonicalize and apply registration-time guards. Returns canonical path."""
    try:
        canonical = canonicalize(host_path)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))

    self_path = os.getenv("SMRT_SELF_PATH")
    if self_path and canonicalize(self_path) == canonical:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="self-registration of smrt-llm-dev is not allowed",
        )

    if not Path(host_path).exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"path does not exist: {host_path}",
        )

    return canonical


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProjectOut)
async def register_project(req: RegisterRequest) -> ProjectOut:
    canonical = _validate_path(req.path)
    name = Path(req.path).name

    Session = get_session_factory(get_engine())
    async with Session() as session:
        project = Project(name=name, canonical_path=canonical)
        session.add(project)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"project already registered: {canonical}",
            )
        await session.refresh(project)
        return ProjectOut.model_validate(project, from_attributes=True)


@router.get("", response_model=list[ProjectOut])
async def list_projects() -> list[ProjectOut]:
    Session = get_session_factory(get_engine())
    async with Session() as session:
        result = await session.execute(select(Project).order_by(Project.created_at.desc()))
        return [ProjectOut.model_validate(p, from_attributes=True) for p in result.scalars()]
```

- [ ] **Step 4: Wire the router into the app — modify `main.py`**

Modify `backend/src/smrt_agent/main.py` `create_app` function: after `add_middleware(...)` call, before the inline `/health` endpoint, add:

```python
    from smrt_agent.api.projects import router as projects_router
    app.include_router(projects_router)
```

Also, in `lifespan`, add schema init:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from smrt_agent.db.session import get_engine
    from smrt_agent.db.schema import init_schema
    engine = get_engine()
    await init_schema(engine)
    yield
    await engine.dispose()
```

- [ ] **Step 5: Create `backend/src/smrt_agent/api/__init__.py`**

```python
# Empty package marker
```

- [ ] **Step 6: Run — expect 4 tests passing**

```bash
pytest tests/test_projects_api.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/src/smrt_agent/api/ backend/src/smrt_agent/main.py backend/tests/test_projects_api.py
git commit -m "feat(backend): project registration and listing API with path guards"
```

---

### Task 9: Frontend bootstrap — Vite + React + TypeScript

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/.eslintrc.cjs`

- [ ] **Step 1: Initialize Vite project structure manually (we want full control)**

Create `frontend/package.json`:

```json
{
  "name": "smrt-agent-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite --host 127.0.0.1 --port 5173",
    "build": "tsc -b && vite build",
    "preview": "vite preview --host 127.0.0.1 --port 5173",
    "lint": "eslint src --ext ts,tsx --max-warnings 0",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.20",
    "eslint": "^9.0.0",
    "@typescript-eslint/eslint-plugin": "^7.0.0",
    "@typescript-eslint/parser": "^7.0.0",
    "postcss": "^8.4.41",
    "tailwindcss": "^3.4.10",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "vitest": "^2.0.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.5.0",
    "jsdom": "^25.0.0"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.ts`**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
});
```

- [ ] **Step 3: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "allowImportingTsExtensions": false,
    "noEmit": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"],
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 4: Create `frontend/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "skipLibCheck": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 5: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SMRT Agent</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/index.css`**

```tsx
// frontend/src/main.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

```tsx
// frontend/src/App.tsx
export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b bg-white px-6 py-4">
        <h1 className="text-xl font-semibold">SMRT Agent</h1>
      </header>
      <main className="px-6 py-6">
        <p className="text-slate-600">Frontend bootstrapped.</p>
      </main>
    </div>
  );
}
```

```css
/* frontend/src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 7: Install + smoke**

```bash
cd frontend
npm install
npm run dev
```

Then open http://127.0.0.1:5173 in a browser. Expected: "SMRT Agent" header + "Frontend bootstrapped."

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): Vite + React + TypeScript bootstrap on 127.0.0.1"
```

---

### Task 10: Tailwind CSS configuration

**Files:**
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`

- [ ] **Step 1: Create `frontend/tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Cascadia Code', 'monospace'],
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 2: Create `frontend/postcss.config.js`**

```javascript
export default {
  plugins: { tailwindcss: {}, autoprefixer: {} },
};
```

- [ ] **Step 3: Verify Tailwind classes render**

Restart `npm run dev`, refresh browser. Expected: header has white background and bottom border (Tailwind classes applied).

- [ ] **Step 4: Commit**

```bash
git add frontend/tailwind.config.js frontend/postcss.config.js
git commit -m "feat(frontend): Tailwind CSS configuration"
```

---

### Task 11: Frontend API client + ProjectsPage (TDD with vitest)

**Files:**
- Create: `frontend/src/test-setup.ts`
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/pages/ProjectsPage.tsx`
- Modify: `frontend/src/App.tsx` — render ProjectsPage
- Create: `frontend/src/lib/api.test.ts`
- Create: `frontend/src/pages/ProjectsPage.test.tsx`

- [ ] **Step 1: Create `frontend/src/test-setup.ts`**

```typescript
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 2: Write `frontend/src/lib/api.test.ts`**

```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { listProjects, registerProject } from './api';

describe('api client', () => {
  beforeEach(() => {
    global.fetch = vi.fn();
  });

  it('listProjects calls GET /api/projects', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [{ id: 1, name: 'todo-api', canonical_path: '/d/todo-api', created_at: '2026-04-23T00:00:00Z' }],
    });
    const projects = await listProjects();
    expect(fetch).toHaveBeenCalledWith('/api/projects');
    expect(projects).toHaveLength(1);
    expect(projects[0].name).toBe('todo-api');
  });

  it('registerProject POSTs the path and returns the new project', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: true,
      status: 201,
      json: async () => ({ id: 2, name: 'todo-api', canonical_path: '/d/todo-api', created_at: '2026-04-23T00:00:00Z' }),
    });
    const p = await registerProject('/d/todo-api');
    expect(fetch).toHaveBeenCalledWith('/api/projects', expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: '/d/todo-api' }),
    }));
    expect(p.id).toBe(2);
  });

  it('registerProject throws on non-2xx with detail', async () => {
    (fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'parent traversal not allowed' }),
    });
    await expect(registerProject('/foo/../bar')).rejects.toThrow('parent traversal not allowed');
  });
});
```

- [ ] **Step 3: Run — expect failure**

```bash
cd frontend
npm test -- api.test
```

- [ ] **Step 4: Implement `frontend/src/lib/api.ts`**

```typescript
export interface Project {
  id: number;
  name: string;
  canonical_path: string;
  created_at: string;
}

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(body.detail ?? `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function listProjects(): Promise<Project[]> {
  const resp = await fetch('/api/projects');
  return handle<Project[]>(resp);
}

export async function registerProject(path: string): Promise<Project> {
  const resp = await fetch('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  return handle<Project>(resp);
}
```

- [ ] **Step 5: Run — expect pass**

- [ ] **Step 6: Write `frontend/src/pages/ProjectsPage.test.tsx`**

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ProjectsPage } from './ProjectsPage';
import * as api from '../lib/api';

vi.mock('../lib/api');

describe('ProjectsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders the empty state when no projects exist', async () => {
    vi.mocked(api.listProjects).mockResolvedValue([]);
    render(<ProjectsPage />);
    await waitFor(() => expect(screen.getByText(/no projects registered/i)).toBeInTheDocument());
  });

  it('renders the list when projects exist', async () => {
    vi.mocked(api.listProjects).mockResolvedValue([
      { id: 1, name: 'todo-api', canonical_path: '/d/todo-api', created_at: '2026-04-23T00:00:00Z' },
    ]);
    render(<ProjectsPage />);
    await waitFor(() => expect(screen.getByText('todo-api')).toBeInTheDocument());
  });
});
```

- [ ] **Step 7: Implement `frontend/src/pages/ProjectsPage.tsx`**

```tsx
import { useEffect, useState, FormEvent } from 'react';
import { listProjects, registerProject, type Project } from '../lib/api';

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [path, setPath] = useState('');
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setProjects(await listProjects());
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await registerProject(path);
      setPath('');
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="space-y-6">
      <form onSubmit={onSubmit} className="flex gap-2">
        <input
          aria-label="Project path"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder="Absolute path to a Python FastAPI project"
          className="flex-1 rounded border border-slate-300 px-3 py-2"
        />
        <button
          type="submit"
          className="rounded bg-slate-900 px-4 py-2 text-white hover:bg-slate-700"
          disabled={!path.trim()}
        >
          Register
        </button>
      </form>

      {error && <p className="rounded border border-red-300 bg-red-50 p-3 text-red-800">{error}</p>}

      {projects === null ? (
        <p className="text-slate-500">Loading…</p>
      ) : projects.length === 0 ? (
        <p className="text-slate-500">No projects registered yet.</p>
      ) : (
        <ul className="divide-y rounded border bg-white">
          {projects.map((p) => (
            <li key={p.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <div className="font-medium">{p.name}</div>
                <div className="font-mono text-xs text-slate-500">{p.canonical_path}</div>
              </div>
              <span className="text-xs text-slate-400">
                {new Date(p.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

- [ ] **Step 8: Update `frontend/src/App.tsx`**

```tsx
import { ProjectsPage } from './pages/ProjectsPage';

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b bg-white px-6 py-4">
        <h1 className="text-xl font-semibold">SMRT Agent</h1>
      </header>
      <main className="px-6 py-6">
        <ProjectsPage />
      </main>
    </div>
  );
}
```

- [ ] **Step 9: Run all frontend tests — expect pass**

```bash
npm test
```

- [ ] **Step 10: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): API client and ProjectsPage with form + list"
```

---

### Task 12: Docker Compose dev environment

**Files:**
- Create: `Dockerfile.backend.dev`
- Create: `Dockerfile.frontend.dev`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `Dockerfile.backend.dev`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml ./pyproject.toml
RUN pip install --no-cache-dir -e ".[dev]" || true

COPY backend/ ./

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
EXPOSE 8000
CMD ["uvicorn", "smrt_agent.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

- [ ] **Step 2: Create `Dockerfile.frontend.dev`**

```dockerfile
FROM node:20-bookworm-slim

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
# Localhost-only by design. Do NOT change `127.0.0.1:` to `0.0.0.0:` without
# putting an authenticated reverse proxy in front. v1 has no built-in auth.
services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend.dev
    container_name: smrt-backend
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - ./backend:/app
      - smrt_state:/root/.smrt
      # Mount Docker socket so backend can orchestrate target sandboxes.
      # Linux: /var/run/docker.sock; on Windows/macOS Docker Desktop bridges.
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - SMRT_DB_PATH=/root/.smrt/state.db
      - SMRT_BIND_HOST=0.0.0.0  # inside container; published only to 127.0.0.1 above
      - SMRT_BACKEND_PORT=8000
    env_file:
      - .env

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend.dev
    container_name: smrt-frontend
    ports:
      - "127.0.0.1:5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    depends_on:
      - backend

volumes:
  smrt_state:
```

- [ ] **Step 4: Smoke-test the full stack**

```bash
docker compose up --build
# Open http://127.0.0.1:5173 in browser
# In a separate terminal: curl http://127.0.0.1:8000/health
```

Expected: browser shows "No projects registered yet." curl returns `{"status":"ok",...}`.

- [ ] **Step 5: Tear down**

```bash
docker compose down
```

- [ ] **Step 6: Commit**

```bash
git add Dockerfile.backend.dev Dockerfile.frontend.dev docker-compose.yml
git commit -m "feat(infra): docker-compose dev environment with 127.0.0.1 binds"
```

---

### Task 13: bin/smrt-exec.py — cross-platform Docker wrapper

**Files:**
- Create: `bin/smrt-exec.py`
- Create: `bin/__init__.py`
- Create: `backend/tests/test_smrt_exec.py` — symlink or copy via path

(For testability, the wrapper's logic lives in `backend/src/smrt_agent/sandbox/exec.py` and `bin/smrt-exec.py` is a thin CLI shim importing from there. This keeps it unit-testable without involving subprocess.)

**Real files:**
- Create: `backend/src/smrt_agent/sandbox/__init__.py`
- Create: `backend/src/smrt_agent/sandbox/exec.py`
- Create: `bin/smrt-exec.py`
- Create: `backend/tests/test_sandbox_exec.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sandbox_exec.py
import pytest
from unittest.mock import MagicMock, patch

from smrt_agent.sandbox.exec import (
    SmrtExecConfig,
    SmrtExecError,
    enforce_container_name,
    run_with_caps,
)


def test_enforce_container_name_accepts_smrt_prefix():
    enforce_container_name("smrt-sandbox-todo-api-1714")  # no exception


def test_enforce_container_name_rejects_others():
    with pytest.raises(SmrtExecError, match="must be prefixed"):
        enforce_container_name("nginx")


def test_run_with_caps_invokes_docker_with_resource_limits():
    fake_client = MagicMock()
    fake_client.containers.run.return_value = MagicMock(id="abc123", logs=lambda **_: b"")
    cfg = SmrtExecConfig(image="python:3.11-slim", name="smrt-sandbox-test-1", network="smrt-internal")

    with patch("smrt_agent.sandbox.exec.docker.from_env", return_value=fake_client):
        run_with_caps(cfg, command=["python", "--version"])

    call = fake_client.containers.run.call_args
    assert call.kwargs["name"] == "smrt-sandbox-test-1"
    assert call.kwargs["network"] == "smrt-internal"
    assert call.kwargs["mem_limit"] == "2g"
    assert call.kwargs["nano_cpus"] == 2 * 10**9
    assert call.kwargs["pids_limit"] == 256
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement `backend/src/smrt_agent/sandbox/exec.py`**

```python
"""Hardened cross-platform Docker exec wrapper.

Replaces the spec-original bash script. Enforces:
- Container name prefix `smrt-sandbox-` (rejects others)
- Internal-only network (no internet)
- 2 CPU / 2 GB / 256 PID caps
- 60s per-command / 300s per-batch timeouts (caller responsibility)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import docker
from docker.errors import APIError, ImageNotFound


class SmrtExecError(RuntimeError):
    pass


@dataclass(frozen=True)
class SmrtExecConfig:
    image: str
    name: str
    network: str = "smrt-internal"
    mem_limit: str = "2g"
    nano_cpus: int = 2 * 10**9  # 2 CPUs
    pids_limit: int = 256
    binds: dict[str, dict] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)


def enforce_container_name(name: str) -> None:
    if not name.startswith("smrt-sandbox-"):
        raise SmrtExecError(
            f"refusing to operate on container {name!r}: must be prefixed `smrt-sandbox-`"
        )


def ensure_internal_network(client: docker.DockerClient, name: str = "smrt-internal") -> None:
    """Create the no-gateway internal network if it doesn't exist."""
    try:
        client.networks.get(name)
    except docker.errors.NotFound:
        client.networks.create(name, driver="bridge", internal=True)


def run_with_caps(cfg: SmrtExecConfig, command: list[str]) -> str:
    """Run a one-shot command in a hardened container; return logs."""
    enforce_container_name(cfg.name)
    client = docker.from_env()
    ensure_internal_network(client, cfg.network)

    try:
        container = client.containers.run(
            image=cfg.image,
            name=cfg.name,
            command=command,
            network=cfg.network,
            mem_limit=cfg.mem_limit,
            nano_cpus=cfg.nano_cpus,
            pids_limit=cfg.pids_limit,
            volumes=cfg.binds,
            environment=cfg.env,
            detach=True,
            remove=False,
        )
    except (APIError, ImageNotFound) as e:
        raise SmrtExecError(f"docker run failed: {e}") from e

    try:
        result = container.wait(timeout=60)
        logs = container.logs().decode("utf-8", errors="replace")
        if result.get("StatusCode", 1) != 0:
            raise SmrtExecError(f"command failed (exit {result['StatusCode']}):\n{logs}")
        return logs
    finally:
        try:
            container.remove(force=True)
        except APIError:
            pass
```

- [ ] **Step 4: Implement `backend/src/smrt_agent/sandbox/__init__.py`**

```python
from smrt_agent.sandbox.exec import (
    SmrtExecConfig,
    SmrtExecError,
    enforce_container_name,
    ensure_internal_network,
    run_with_caps,
)

__all__ = [
    "SmrtExecConfig",
    "SmrtExecError",
    "enforce_container_name",
    "ensure_internal_network",
    "run_with_caps",
]
```

- [ ] **Step 5: Implement `bin/smrt-exec.py` as a thin CLI shim**

```python
#!/usr/bin/env python
"""CLI wrapper around smrt_agent.sandbox.exec.run_with_caps.

Usage:
  python bin/smrt-exec.py --name smrt-sandbox-foo --image python:3.11-slim -- python --version
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend" / "src"))

from smrt_agent.sandbox import SmrtExecConfig, SmrtExecError, run_with_caps  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Run a one-shot command in a hardened SMRT sandbox.")
    p.add_argument("--name", required=True, help="container name (must start with smrt-sandbox-)")
    p.add_argument("--image", required=True)
    p.add_argument("--network", default="smrt-internal")
    p.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args()

    cfg = SmrtExecConfig(image=args.image, name=args.name, network=args.network)
    try:
        out = run_with_caps(cfg, command=args.command or [])
        sys.stdout.write(out)
        return 0
    except SmrtExecError as e:
        sys.stderr.write(f"[smrt-exec] {e}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run unit tests — expect pass**

```bash
cd backend
pytest tests/test_sandbox_exec.py -v
```

- [ ] **Step 7: Smoke-test the CLI against a real container**

```bash
python bin/smrt-exec.py --name smrt-sandbox-cli-smoke --image python:3.11-slim -- python --version
```

Expected: prints `Python 3.11.x` and exits 0.

- [ ] **Step 8: Commit**

```bash
git add backend/src/smrt_agent/sandbox/ bin/smrt-exec.py backend/tests/test_sandbox_exec.py
git commit -m "feat(sandbox): cross-platform Docker exec wrapper with caps and naming"
```

---

### Task 14: Sandbox lifecycle — Dockerfile generation + build/start/health-check

**Files:**
- Create: `backend/src/smrt_agent/sandbox/dockerfile.py`
- Create: `backend/src/smrt_agent/sandbox/lifecycle.py`
- Create: `backend/tests/test_dockerfile_generation.py`
- Create: `backend/tests/test_sandbox_lifecycle.py`

- [ ] **Step 1: Write `test_dockerfile_generation.py`**

```python
from pathlib import Path
import pytest
from smrt_agent.sandbox.dockerfile import generate_dockerfile


def test_generates_with_requirements_txt(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi==0.110.0\nuvicorn==0.29.0\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")

    out = generate_dockerfile(tmp_path, app_module="src.main:app")
    assert "FROM python:3.11-slim" in out
    assert "COPY requirements.txt" in out
    assert "pip install" in out
    assert "uvicorn" in out
    assert "EXPOSE" in out


def test_generates_with_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion="0.1"\ndependencies=["fastapi"]\n')
    out = generate_dockerfile(tmp_path, app_module="x.main:app")
    assert "pip install ." in out


def test_raises_when_no_dependency_manifest(tmp_path):
    with pytest.raises(ValueError, match="no requirements.txt or pyproject.toml"):
        generate_dockerfile(tmp_path, app_module="x:app")
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement `backend/src/smrt_agent/sandbox/dockerfile.py`**

```python
"""Generate a Dockerfile.smrt for a registered target project."""
from pathlib import Path


def generate_dockerfile(project_root: Path, app_module: str, port: int = 8000) -> str:
    """Build a Dockerfile string for a target FastAPI project.

    Args:
        project_root: absolute path to the registered target
        app_module: ASGI app reference, e.g. "src.main:app"
        port: port the app binds to inside the container
    """
    has_req = (project_root / "requirements.txt").exists()
    has_pyproject = (project_root / "pyproject.toml").exists()

    if not (has_req or has_pyproject):
        raise ValueError(
            f"no requirements.txt or pyproject.toml found in {project_root}"
        )

    lines = [
        "# Generated by smrt-agent — do not edit",
        "FROM python:3.11-slim",
        "WORKDIR /app",
        "RUN apt-get update && apt-get install -y --no-install-recommends "
        "curl ca-certificates && rm -rf /var/lib/apt/lists/*",
    ]

    if has_req:
        lines += [
            "COPY requirements.txt ./requirements.txt",
            "RUN pip install --no-cache-dir -r requirements.txt",
            "COPY . .",
        ]
    else:
        lines += ["COPY . .", "RUN pip install --no-cache-dir ."]

    lines += [
        f"EXPOSE {port}",
        f'CMD ["uvicorn", "{app_module}", "--host", "0.0.0.0", "--port", "{port}"]',
        "",
    ]
    return "\n".join(lines)


def write_dockerfile(project_root: Path, app_module: str, port: int = 8000) -> Path:
    """Write the generated Dockerfile to <project>/.smrt/sandbox/Dockerfile."""
    target = project_root / ".smrt" / "sandbox" / "Dockerfile"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(generate_dockerfile(project_root, app_module, port))
    return target
```

- [ ] **Step 4: Run — expect pass**

- [ ] **Step 5: Write `backend/tests/test_sandbox_lifecycle.py` with mocked docker**

```python
from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest

from smrt_agent.sandbox.lifecycle import build_sandbox_image, start_sandbox_container


def test_build_sandbox_image_calls_docker_build(tmp_path):
    (tmp_path / ".smrt" / "sandbox").mkdir(parents=True)
    (tmp_path / ".smrt" / "sandbox" / "Dockerfile").write_text("FROM python:3.11-slim\n")

    fake_client = MagicMock()
    fake_image = MagicMock(id="sha256:abc", tags=["smrt-sandbox-todo-api:latest"])
    fake_client.images.build.return_value = (fake_image, iter([{"stream": "Step 1/2"}]))

    with patch("smrt_agent.sandbox.lifecycle.docker.from_env", return_value=fake_client):
        image_id = build_sandbox_image(tmp_path, "todo-api")

    assert image_id == "sha256:abc"
    fake_client.images.build.assert_called_once()


def test_start_sandbox_container_uses_caps_and_network():
    fake_client = MagicMock()
    fake_container = MagicMock(id="cid")
    fake_client.containers.run.return_value = fake_container

    with patch("smrt_agent.sandbox.lifecycle.docker.from_env", return_value=fake_client), \
         patch("smrt_agent.sandbox.lifecycle.ensure_internal_network"):
        cid = start_sandbox_container("smrt-sandbox-todo-api-001", "image-id", host_port=18080)

    assert cid == "cid"
    kwargs = fake_client.containers.run.call_args.kwargs
    assert kwargs["mem_limit"] == "2g"
    assert kwargs["nano_cpus"] == 2 * 10**9
    assert kwargs["network"] == "smrt-internal"
    assert kwargs["ports"] == {"8000/tcp": ("127.0.0.1", 18080)}
```

- [ ] **Step 6: Implement `backend/src/smrt_agent/sandbox/lifecycle.py`**

```python
"""Build and run lifecycle for a target project's sandbox container."""
from __future__ import annotations

import time
from pathlib import Path

import docker
import httpx

from smrt_agent.sandbox.exec import enforce_container_name, ensure_internal_network


def build_sandbox_image(project_root: Path, project_slug: str) -> str:
    """Build the sandbox image for a registered target. Returns image ID.

    Reads <project>/.smrt/sandbox/Dockerfile.
    """
    dockerfile_dir = project_root / ".smrt" / "sandbox"
    if not (dockerfile_dir / "Dockerfile").exists():
        raise FileNotFoundError(f"no sandbox Dockerfile at {dockerfile_dir}")

    client = docker.from_env()
    tag = f"smrt-sandbox-{project_slug}:latest"
    image, _logs = client.images.build(
        path=str(project_root),
        dockerfile=str(dockerfile_dir / "Dockerfile"),
        tag=tag,
        rm=True,
        forcerm=True,
    )
    return image.id


def start_sandbox_container(
    container_name: str,
    image_id: str,
    host_port: int,
    container_port: int = 8000,
    network: str = "smrt-internal",
) -> str:
    """Start a hardened sandbox container; return container ID."""
    enforce_container_name(container_name)
    client = docker.from_env()
    ensure_internal_network(client, network)

    container = client.containers.run(
        image=image_id,
        name=container_name,
        detach=True,
        network=network,
        mem_limit="2g",
        nano_cpus=2 * 10**9,
        pids_limit=256,
        ports={f"{container_port}/tcp": ("127.0.0.1", host_port)},
    )
    return container.id


def wait_for_health(host_port: int, path: str = "/health", timeout: float = 30.0) -> bool:
    """Poll the sandbox's health endpoint until it returns 2xx or timeout."""
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{host_port}{path}", timeout=2.0)
            if r.status_code < 300:
                return True
        except Exception as e:
            last_error = e
        time.sleep(0.5)
    if last_error:
        raise TimeoutError(f"sandbox health check timed out: {last_error}")
    return False


def stop_and_remove_container(container_name: str) -> None:
    enforce_container_name(container_name)
    client = docker.from_env()
    try:
        c = client.containers.get(container_name)
        c.stop(timeout=5)
        c.remove(force=True)
    except docker.errors.NotFound:
        pass
```

- [ ] **Step 7: Run all sandbox tests — expect pass**

- [ ] **Step 8: Commit**

```bash
git add backend/src/smrt_agent/sandbox/ backend/tests/test_dockerfile_generation.py backend/tests/test_sandbox_lifecycle.py
git commit -m "feat(sandbox): Dockerfile generation and container lifecycle (build/start/health)"
```

---

### Task 15: API endpoint to build + start sandbox for a project

**Files:**
- Create: `backend/src/smrt_agent/api/sandbox.py`
- Modify: `backend/src/smrt_agent/main.py` — register the router
- Create: `backend/tests/test_sandbox_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sandbox_api.py
import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport

from smrt_agent.main import create_app
from smrt_agent.db.session import get_engine
from smrt_agent.db.schema import init_schema


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    engine = get_engine(force_new=True)
    await init_schema(engine)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await engine.dispose()


@pytest.mark.asyncio
async def test_build_sandbox_endpoint(client, tmp_path):
    target = tmp_path / "todo-api"
    target.mkdir()
    (target / "requirements.txt").write_text("fastapi\n")
    (target / "src").mkdir()
    (target / "src" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")

    reg = await client.post("/api/projects", json={"path": str(target)})
    pid = reg.json()["id"]

    with patch("smrt_agent.api.sandbox.build_sandbox_image", return_value="sha256:fake"):
        resp = await client.post(f"/api/projects/{pid}/sandbox/build", json={"app_module": "src.main:app"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["image_id"] == "sha256:fake"
    assert body["dockerfile_written_to"].endswith(".smrt/sandbox/Dockerfile")
```

- [ ] **Step 2: Run — expect failure**

- [ ] **Step 3: Implement `backend/src/smrt_agent/api/sandbox.py`**

```python
"""Sandbox lifecycle API."""
from pathlib import Path
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from smrt_agent.db.models import Project
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.sandbox.dockerfile import write_dockerfile
from smrt_agent.sandbox.lifecycle import (
    build_sandbox_image,
    start_sandbox_container,
    wait_for_health,
)


router = APIRouter(prefix="/api/projects", tags=["sandbox"])


class BuildSandboxRequest(BaseModel):
    app_module: str  # e.g. "src.main:app"


class BuildSandboxResponse(BaseModel):
    image_id: str
    dockerfile_written_to: str


class StartSandboxRequest(BaseModel):
    image_id: str
    host_port: int = 18080


class StartSandboxResponse(BaseModel):
    container_id: str
    healthy: bool


async def _project_or_404(project_id: int) -> Project:
    Session = get_session_factory(get_engine())
    async with Session() as session:
        result = await session.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"project {project_id} not found")
    return project


@router.post("/{project_id}/sandbox/build", response_model=BuildSandboxResponse)
async def build_sandbox(project_id: int, req: BuildSandboxRequest) -> BuildSandboxResponse:
    project = await _project_or_404(project_id)
    project_root = Path(project.canonical_path)

    dockerfile_path = write_dockerfile(project_root, app_module=req.app_module)
    image_id = build_sandbox_image(project_root, project_slug=project.name)

    return BuildSandboxResponse(
        image_id=image_id,
        dockerfile_written_to=str(dockerfile_path),
    )


@router.post("/{project_id}/sandbox/start", response_model=StartSandboxResponse)
async def start_sandbox(project_id: int, req: StartSandboxRequest) -> StartSandboxResponse:
    project = await _project_or_404(project_id)
    container_name = f"smrt-sandbox-{project.name}-{project_id:04d}"
    cid = start_sandbox_container(container_name, req.image_id, req.host_port)
    healthy = False
    try:
        healthy = wait_for_health(req.host_port, timeout=30)
    except TimeoutError:
        healthy = False
    return StartSandboxResponse(container_id=cid, healthy=healthy)
```

- [ ] **Step 4: Wire the router — modify `backend/src/smrt_agent/main.py`** add after the projects router include:

```python
    from smrt_agent.api.sandbox import router as sandbox_router
    app.include_router(sandbox_router)
```

- [ ] **Step 5: Run — expect pass**

- [ ] **Step 6: Commit**

```bash
git add backend/src/smrt_agent/api/sandbox.py backend/src/smrt_agent/main.py backend/tests/test_sandbox_api.py
git commit -m "feat(api): build and start sandbox endpoints for registered projects"
```

---

### Task 16: todo-api fixture — base FastAPI app (no bugs yet)

**Files:**
- Create: `eval-fixtures/todo-api/requirements.txt`
- Create: `eval-fixtures/todo-api/src/__init__.py`
- Create: `eval-fixtures/todo-api/src/main.py`
- Create: `eval-fixtures/todo-api/src/models.py`
- Create: `eval-fixtures/todo-api/src/db.py`
- Create: `eval-fixtures/todo-api/.gitignore`

- [ ] **Step 1: Create `eval-fixtures/todo-api/requirements.txt`**

```
fastapi==0.110.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
aiosqlite==0.20.0
pydantic==2.6.4
bcrypt==4.1.3
```

- [ ] **Step 2: Create `eval-fixtures/todo-api/.gitignore`**

```
# This is the TARGET project's gitignore. The smrt agent's secret_guard_hook
# reads this file to determine what's off-limits. BUGS.md is the answer key
# for evaluators — it MUST be hidden from the agent so it has to find the bugs.
BUGS.md

__pycache__/
*.py[cod]
.venv/
.smrt/
*.db
.env
```

- [ ] **Step 3: Create `eval-fixtures/todo-api/src/db.py`**

```python
"""Tiny in-memory SQLite for the fixture (zero external deps)."""
from sqlalchemy import Column, DateTime, Integer, String, Boolean, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Todo(Base):
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True)
    owner_id = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True)
    completed = Column(Boolean, default=False, nullable=False)


class Counter(Base):
    __tablename__ = "counters"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    value = Column(Integer, default=0, nullable=False)


engine = create_async_engine("sqlite+aiosqlite:///./todo.db", future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 4: Create `eval-fixtures/todo-api/src/models.py` (Pydantic schemas)**

```python
"""Pydantic schemas for request/response. Several intentional gaps planted later."""
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    id: int
    email: EmailStr
    is_admin: bool
    created_at: datetime


class TodoCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    due_at: datetime | None = None  # NOTE: planted bug — no past-date validation


class TodoOut(BaseModel):
    id: int
    title: str
    due_at: datetime | None
    completed: bool
```

- [ ] **Step 5: Create `eval-fixtures/todo-api/src/__init__.py`** (empty)

- [ ] **Step 6: Create `eval-fixtures/todo-api/src/main.py` (skeleton, no bugs yet)**

```python
"""TODO API — fixture for SMRT Agent eval. Bugs planted in subsequent tasks."""
from contextlib import asynccontextmanager
import bcrypt
from fastapi import FastAPI, HTTPException, Header, status
from sqlalchemy import select

from src.db import SessionLocal, User, Todo, Counter, init_db
from src.models import UserCreate, UserOut, TodoCreate, TodoOut


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title="todo-api fixture", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _check_admin(authorization: str | None) -> int:
    """Return user_id when token is valid admin, else raise 401/403.

    Toy auth: header is `Bearer user-<id>`; admin bit looked up from DB.
    """
    if not authorization or not authorization.startswith("Bearer user-"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing/invalid bearer")
    try:
        return int(authorization.removeprefix("Bearer user-"))
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="malformed bearer")
```

- [ ] **Step 7: Verify it imports**

```bash
cd eval-fixtures/todo-api
python -m venv .venv
# activate
pip install -r requirements.txt
python -c "from src.main import app; print('ok')"
```

- [ ] **Step 8: Commit**

```bash
git add eval-fixtures/todo-api/
git commit -m "feat(fixture): todo-api skeleton (FastAPI + SQLAlchemy, no bugs yet)"
```

---

### Task 17: todo-api — plant Bug #1 (silent-logical: password hash leak)

**Files:** Modify `eval-fixtures/todo-api/src/main.py`

- [ ] **Step 1: Add the buggy POST /users endpoint to `src/main.py`**

```python
# BUG #1 (silent-logical): missing response_model causes hashed_password leak
@app.post("/users", status_code=201)
async def create_user(req: UserCreate):
    async with SessionLocal() as s:
        existing = await s.execute(select(User).where(User.email == req.email))
        if existing.scalar_one_or_none():
            raise HTTPException(409, detail="email exists")
        user = User(email=req.email, hashed_password=_hash_password(req.password))
        s.add(user)
        await s.commit()
        await s.refresh(user)
        # The bug: returning the ORM object directly serializes ALL columns,
        # including hashed_password. Correct fix is response_model=UserOut.
        return user
```

- [ ] **Step 2: Manual smoke (optional)** — start app, POST a user, observe `hashed_password` in response.

- [ ] **Step 3: Commit**

```bash
git add eval-fixtures/todo-api/src/main.py
git commit -m "fixture(todo-api): plant bug #1 (password hash leaks in POST /users)"
```

---

### Task 18: todo-api — plant Bug #2 (async: missing `await`)

**Files:** Modify `eval-fixtures/todo-api/src/main.py`

- [ ] **Step 1: Add a buggy background-task endpoint**

```python
import asyncio


async def notify_admin(message: str) -> None:
    """Pretend to send an admin notification."""
    await asyncio.sleep(0.1)
    print(f"[admin-notification] {message}")


@app.post("/users/{user_id}/promote", status_code=200)
async def promote_user(user_id: int, authorization: str | None = Header(None)):
    caller = _check_admin(authorization)
    async with SessionLocal() as s:
        user = await s.get(User, user_id)
        if not user:
            raise HTTPException(404, detail="user not found")
        user.is_admin = True
        await s.commit()
        # BUG #2 (async): notify_admin is a coroutine but we forgot `await`,
        # so it never actually runs. Linters won't catch this — RuntimeWarning
        # is emitted to stderr but tests don't fail.
        notify_admin(f"user {caller} promoted user {user_id}")
        return {"id": user_id, "is_admin": True}
```

- [ ] **Step 2: Commit**

```bash
git add eval-fixtures/todo-api/src/main.py
git commit -m "fixture(todo-api): plant bug #2 (missing await on notify_admin)"
```

---

### Task 19: todo-api — plant Bug #3 (auth-order: check after DB write)

**Files:** Modify `eval-fixtures/todo-api/src/main.py`

- [ ] **Step 1: Add the buggy DELETE endpoint**

```python
@app.delete("/todos/{todo_id}", status_code=204)
async def delete_todo(todo_id: int, authorization: str | None = Header(None)):
    async with SessionLocal() as s:
        todo = await s.get(Todo, todo_id)
        if not todo:
            raise HTTPException(404, detail="todo not found")
        # BUG #3 (auth-order): we delete first, then check ownership. A user
        # can delete anyone else's todo and still get the correct 403, but
        # the row is gone. Correct fix: check ownership BEFORE deletion.
        await s.delete(todo)
        await s.commit()
        caller = _check_admin(authorization) if authorization else 0
        if todo.owner_id != caller:
            raise HTTPException(403, detail="not your todo")
        return None
```

- [ ] **Step 2: Commit**

```bash
git add eval-fixtures/todo-api/src/main.py
git commit -m "fixture(todo-api): plant bug #3 (auth check after delete in DELETE /todos)"
```

---

### Task 20: todo-api — plant Bug #4 (input-validation: insufficient constraint)

**Files:** `eval-fixtures/todo-api/src/main.py` already has the issue from Task 16's `TodoCreate.due_at: datetime | None = None`. The bug is that no validator rejects past-dated `due_at`.

- [ ] **Step 1: Add the POST /todos endpoint that exposes the bug**

```python
@app.post("/todos", status_code=201, response_model=TodoOut)
async def create_todo(req: TodoCreate, authorization: str | None = Header(None)):
    caller = _check_admin(authorization)
    async with SessionLocal() as s:
        # BUG #4 (input-validation): TodoCreate accepts due_at in the past
        # without rejecting it. Pydantic field has no @field_validator for it.
        # Allows nonsense like due_at = "1970-01-01T00:00:00Z".
        todo = Todo(owner_id=caller, title=req.title, due_at=req.due_at)
        s.add(todo)
        await s.commit()
        await s.refresh(todo)
        return TodoOut(id=todo.id, title=todo.title, due_at=todo.due_at, completed=todo.completed)
```

- [ ] **Step 2: Commit**

```bash
git add eval-fixtures/todo-api/src/main.py
git commit -m "fixture(todo-api): plant bug #4 (POST /todos accepts past due_at)"
```

---

### Task 21: todo-api — plant Bug #5 (state-mutation: race in counter increment)

**Files:** Modify `eval-fixtures/todo-api/src/main.py`

- [ ] **Step 1: Add the buggy counter endpoint**

```python
@app.post("/counters/{name}/increment")
async def increment_counter(name: str):
    async with SessionLocal() as s:
        counter = (await s.execute(select(Counter).where(Counter.name == name))).scalar_one_or_none()
        if not counter:
            counter = Counter(name=name, value=0)
            s.add(counter)
            await s.commit()
            await s.refresh(counter)
        # BUG #5 (state-mutation): read-modify-write without row-level lock.
        # Under concurrent requests, two callers can read the same value,
        # both write value+1, and one increment is lost. Fix: use SELECT
        # FOR UPDATE or an atomic UPDATE counters SET value = value + 1.
        new_value = counter.value + 1
        counter.value = new_value
        await s.commit()
        return {"name": name, "value": new_value}
```

- [ ] **Step 2: Commit**

```bash
git add eval-fixtures/todo-api/src/main.py
git commit -m "fixture(todo-api): plant bug #5 (race in counter increment)"
```

---

### Task 22: todo-api — answer key BUGS.md

**Files:** Create `eval-fixtures/todo-api/BUGS.md`

(This file is committed to the meta repo — visible to evaluators — but listed in `eval-fixtures/todo-api/.gitignore` so the agent's secret_guard_hook hides it during runs.)

- [ ] **Step 1: Create `eval-fixtures/todo-api/BUGS.md`**

```markdown
# todo-api — planted bug answer key

These five bugs are intentionally seeded for evaluating the SMRT Agent's logical-bug detection. The agent never sees this file (listed in `.gitignore`; secret_guard_hook respects that).

## Bug 1 — Silent-logical: password hash leak in POST /users
**Location:** `src/main.py` — `create_user`
**Symptom:** Response body includes `hashed_password`.
**Correct fix:** Add `response_model=UserOut` to the route decorator (UserOut omits `hashed_password`).

## Bug 2 — Async: missing `await` on coroutine
**Location:** `src/main.py` — `promote_user`
**Symptom:** `notify_admin(...)` produces a RuntimeWarning ("coroutine was never awaited") and never actually runs.
**Correct fix:** `await notify_admin(...)`.

## Bug 3 — Auth-order: ownership check after deletion
**Location:** `src/main.py` — `delete_todo`
**Symptom:** Any authenticated user can delete any other user's todo. The row is gone before the 403 fires.
**Correct fix:** Check `todo.owner_id != caller` before `s.delete(todo)`.

## Bug 4 — Input-validation: past `due_at` accepted
**Location:** `src/models.py` — `TodoCreate.due_at`
**Symptom:** `POST /todos {"title":"x","due_at":"1970-01-01T00:00:00Z"}` returns 201.
**Correct fix:** Add `@field_validator("due_at")` rejecting past datetimes.

## Bug 5 — State-mutation: race in counter increment
**Location:** `src/main.py` — `increment_counter`
**Symptom:** Concurrent POSTs lose increments (read-modify-write without lock).
**Correct fix:** Use atomic SQL `UPDATE counters SET value = value + 1 WHERE name = :n` and return via `RETURNING`, or wrap in row-level lock.
```

- [ ] **Step 2: Verify gitignore precedence (BUGS.md committed to meta repo, hidden from agent)**

```bash
# At meta repo root:
git add eval-fixtures/todo-api/BUGS.md
git status
# Expected: BUGS.md staged for commit (NOT ignored by meta .gitignore)

# Inside the fixture directory, verify the target's .gitignore lists it:
grep -q "^BUGS.md$" eval-fixtures/todo-api/.gitignore && echo "Hidden from agent: OK"
```

Expected output: `Hidden from agent: OK`

- [ ] **Step 3: Commit**

```bash
git add eval-fixtures/todo-api/BUGS.md
git commit -m "fixture(todo-api): commit BUGS.md answer key (hidden from agent via target .gitignore)"
```

---

### Task 23: End-to-end smoke — register todo-api, build sandbox, hit /health

**Files:** none (manual smoke test)

- [ ] **Step 1: Start the stack**

```bash
docker compose up --build
```

- [ ] **Step 2: Open http://127.0.0.1:5173 in browser**

- [ ] **Step 3: Register the todo-api fixture path**

In the form, paste the absolute path:

- Windows: `D:\web-project\smrt-llm-dev\eval-fixtures\todo-api`
- macOS/Linux: `/path/to/smrt-llm-dev/eval-fixtures/todo-api`

Click Register. Expected: `todo-api` appears in the list.

- [ ] **Step 4: Trigger sandbox build via curl** (UI button comes in P3; for P1 we trigger by API)

```bash
# Get project ID from the list endpoint:
curl -s http://127.0.0.1:8000/api/projects | python -c "import json,sys; print(json.load(sys.stdin)[0]['id'])"
# e.g., 1

# Build the sandbox:
curl -X POST http://127.0.0.1:8000/api/projects/1/sandbox/build \
  -H "Content-Type: application/json" \
  -d '{"app_module": "src.main:app"}'
```

Expected: `{"image_id":"sha256:...","dockerfile_written_to":"...todo-api/.smrt/sandbox/Dockerfile"}`

- [ ] **Step 5: Start the sandbox**

```bash
curl -X POST http://127.0.0.1:8000/api/projects/1/sandbox/start \
  -H "Content-Type: application/json" \
  -d '{"image_id":"sha256:...","host_port":18080}'
```

Expected: `{"container_id":"...","healthy":true}`

- [ ] **Step 6: Verify the fixture is running**

```bash
curl http://127.0.0.1:18080/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 7: Tear down**

```bash
docker stop smrt-sandbox-todo-api-0001
docker rm smrt-sandbox-todo-api-0001
docker compose down
```

- [ ] **Step 8: Mark P1 done — open the PR**

```bash
git push -u origin phase/1-foundation
gh pr create --title "Phase 1 — Foundation" --body "Implements P1 of the impl plan: backend + frontend skeleton, project registry, sandbox lifecycle wrapper, and the todo-api synthetic fixture with five planted bugs.

Closes the P1-labeled issues."
```

---

## §C. Phase 2–5 — summaries (detailed plans deferred)

Each phase below has a one-line goal + the spec sections it covers. **Detailed bite-sized plans for these phases are written when each phase begins** (re-invoke the writing-plans skill at the start of each phase). Writing speculative bite-sized steps now would force placeholders for types and signatures we haven't designed.

### P2 — Reviewer + Project.md
**Goal:** Reviewer agent runs initialization audit on a registered project, walks the source tree, fetches `/openapi.json` from the running sandbox, and writes a populated `<project>/.smrt/Project.md`. Live tool-call streaming visible in a new "Live Agent View" tab in the UI.

**Spec coverage:** §2.1 Reviewer agent · §4.2 Reviewer test plan artifact · §5.1 Project.md initialization audit · §7.2 Project Detail tab + Live Agent View · §7.3 Live observability layers 1–3 · §8.2 APScheduler periodic checkup · §8.3 Budget guardrails · §9.1 SDK orchestration (root only) · §9.2 Context isolation · §9.4 Session management · §9.5 Structured output · §9.6 Reviewer prompt.

### P3 — QA + Coder + blackbox loop
**Goal:** Human creates a bug ticket via UI form. Reviewer dispatches to QA which generates a hidden test. On human confirmation, Coder gets the redacted ticket and produces a fix on a `smrt/fix/<ticket-id>-<slug>` branch. QA verdict loop with caps. PR-equivalent surfaces in UI for human accept/reject.

**Spec coverage:** §2.2 QA agent · §2.3 Coder agent · §3.4 Secret protection (gitignore-aware deny rule, applied to all subagents) · §4.1 Triggers (file watcher only; manual UI ticket flow) · §4.3 Logical-bug detection strategies · §4.4 Bug ticket schema · §4.5 Blackbox feedback loop · §4.6 Failure report · §4.7 PR preparation · §5.2 Memory files · §7.2 Tickets tab + Pending Approvals · §7.5 HITL approval surface · §9.3 HITL permission handler · §9.6 QA + Coder prompts.

### P4 — Documentation backends
**Goal:** On PR accept, Reviewer regenerates `docs/` (GitHub MD) + `wiki/` (Obsidian vault) for the target project. DocBackend abstraction with two real implementations + Jira/Confluence stubs visible as "coming soon" in the UI.

**Spec coverage:** §6.1 GitHub-native docs · §6.2 Obsidian vault · §6.3 Beta backends (stubs) · §7.2 Docs tab.

### P5 — Polish: dashboards + Explain mode + submission readiness
**Goal:** Three Overview-tab dashboards (cost breakdown, bug-hunt heatmap, doc completeness over time). Explain mode with provenance trailers in commit messages. Thought-process mode toggle. README finalization, evaluation rubric mapping doc, scrub for any submission-blocking gaps.

**Spec coverage:** §5.3 Skill acquisition · §5.4 Explain mode · §7.4 Three dashboards · §7.5 Thought-process mode toggle · §7.7 Replay + history · §12 Evaluation rubric mapping · §15 Definition of done.

---

## §D. Self-review checklist (run by author before opening to user)

Performed by Claude immediately after writing this plan:

**1. Spec coverage** — every section of `PRODUCTION.md` mapped to a phase in §A matrix? **Yes** — verified by table walkthrough.

**2. Placeholder scan** — any "TBD" / "TODO" / "implement later" / "add error handling" inside P1 step bodies? **No** — checked. P2–P5 summaries explicitly defer detail; that's structural, not a placeholder.

**3. Type consistency in P1** — does `Project` model match what the API and tests use? **Yes** — `id`, `name`, `canonical_path`, `created_at`. `SmrtExecConfig` shape consistent across `exec.py`, the CLI shim, and tests. Frontend `Project` interface matches the backend `ProjectOut` shape.

**4. Path consistency** — Linux paths in tests, Windows-aware paths in `platform_paths.py` tests, both supported in registration tests via `tmp_path`. Cross-platform handling explicit.

**5. Test-first discipline** — every behavior task has Step 1 = write failing test, Step 2 = run-fail, Step 3 = implement, Step 4 = run-pass, then commit. Setup-only tasks (Dockerfiles, configs) skip TDD because there's no behavior to test.

**6. Frequent commits** — every task ends with a commit step. P1 produces ~22 commits.

If anything in §B reads as fuzzy when you (the user) review it, flag it and I'll rewrite that task.
