from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.api.schemas import AgentRunOut, ProjectCreate, ProjectOut
from smrt_agent.db.models import AgentRun, Project
from smrt_agent.platform_paths import canonicalize
from smrt_agent.settings import Settings

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
async def register_project(
    body: ProjectCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Project:
    settings = Settings()

    # Canonicalize the submitted path
    canonical = canonicalize(body.path)

    # Reject paths outside the allowlist (when allowlist is configured).
    # Both the input and each root are canonicalized for consistent comparison.
    if settings.allowed_project_roots:
        canonical_roots: list[str] = []
        for root in settings.allowed_project_roots:
            try:
                canonical_roots.append(canonicalize(root))
            except Exception:
                canonical_roots.append(root)
        allowed = any(canonical.startswith(root) for root in canonical_roots)
        if not allowed:
            raise HTTPException(status_code=400, detail="Path is not in the project root allowlist")

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
    # Cascade deletes associated AgentRun rows via the relationship
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
