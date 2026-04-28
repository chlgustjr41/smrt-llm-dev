import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.api.schemas import AgentRunOut, ProjectConfig, ProjectConfigPatch, ProjectCreate, ProjectOut
from smrt_agent.db.models import AgentRun, Project, QASession
from smrt_agent.platform_paths import canonicalize
from smrt_agent.settings import Settings


def _config_defaults() -> dict:
    """Return per-project config defaults sourced from the current .env settings."""
    s = Settings()
    return {
        "reviewer_model": s.model_reviewer,
        "qa_model": s.model_qa,
        "coder_model": s.model_coder,
        "max_fix_attempts": s.max_fix_attempts,
        "max_questions_per_attempt": s.max_questions_per_attempt,
        "scheduler_cadence": "daily_0300",
        "thought_process_mode": s.thought_process_mode,
        "use_local_llm": s.use_local_llm,
    }


def _smrt_config_path(project_path: str) -> Path:
    return Path(project_path) / ".smrt" / "config.json"


def _read_smrt_config(project_path: str) -> dict:
    """Read custom config from <project>/.smrt/config.json, empty dict if absent."""
    path = _smrt_config_path(project_path)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_smrt_config(project_path: str, config: dict) -> None:
    """Persist custom config to <project>/.smrt/config.json."""
    path = _smrt_config_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
async def register_project(
    body: ProjectCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Project:
    # Canonicalize the submitted path
    canonical = canonicalize(body.path)

    # Require the path to exist. /workspace paths are resolvable inside Docker;
    # Windows-style paths submitted via the file browser are already /workspace/... form.
    if not Path(body.path).exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {body.path}")

    project = Project(name=body.name, canonical_path=canonical)
    db.add(project)
    try:
        await db.commit()
        await db.refresh(project)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A project with this path is already registered")
    return project


@router.get("", response_model=list[ProjectOut])
async def list_projects(db: Annotated[AsyncSession, Depends(get_db)]) -> list[Project]:
    result = await db.execute(select(Project).order_by(Project.created_at))
    return list(result.scalars().all())


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: Annotated[AsyncSession, Depends(get_db)]) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    sessions = await db.execute(select(QASession).where(QASession.project_id == project_id))
    for session in sessions.scalars().all():
        await db.delete(session)
    runs = await db.execute(select(AgentRun).where(AgentRun.project_id == project_id))
    for run in runs.scalars().all():
        await db.delete(run)
    await db.delete(project)
    await db.commit()
    return Response(status_code=204)


@router.get("/{project_id}/runs", response_model=list[AgentRunOut])
async def list_runs(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AgentRun]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.project_id == project_id)
        .order_by(AgentRun.started_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{project_id}/config", response_model=ProjectConfig)
async def get_project_config(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectConfig:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    # .smrt/config.json is the canonical on-disk override; DB is the fallback.
    stored = _read_smrt_config(project.canonical_path)
    if not stored:
        try:
            stored = json.loads(project.config or '{}')
        except (json.JSONDecodeError, TypeError):
            stored = {}
    merged = {**_config_defaults(), **stored}
    return ProjectConfig(**merged)


@router.patch("/{project_id}/config", response_model=ProjectConfig)
async def patch_project_config(
    project_id: int,
    body: ProjectConfigPatch,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectConfig:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    # Load existing custom config from disk, fall back to DB
    stored = _read_smrt_config(project.canonical_path)
    if not stored:
        try:
            stored = json.loads(project.config or '{}')
        except (json.JSONDecodeError, TypeError):
            stored = {}
    # Merge only the provided (non-None) fields
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    stored.update(updates)
    # Write to disk (canonical) and keep DB in sync for other API consumers
    _write_smrt_config(project.canonical_path, stored)
    project.config = json.dumps(stored)
    await db.commit()
    await db.refresh(project)
    merged = {**_config_defaults(), **stored}
    return ProjectConfig(**merged)
