from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.api.schemas import ProjectCreate, ProjectOut
from smrt_agent.db.models import Project
from smrt_agent.platform_paths import canonicalize
from smrt_agent.settings import Settings

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, status_code=201)
async def register_project(
    body: ProjectCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Project:
    settings = Settings()

    # Reject paths outside the allowlist (when allowlist is configured)
    canonical = canonicalize(body.path)
    if settings.allowed_project_roots:
        allowed = any(canonical.startswith(root) for root in settings.allowed_project_roots)
        if not allowed:
            raise HTTPException(status_code=400, detail="Path is not in the project root allowlist")

    # Require the path to exist on disk
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
