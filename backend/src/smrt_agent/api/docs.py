from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project

router = APIRouter(prefix="/projects", tags=["docs"])


@router.get("/{project_id}/docs")
async def list_docs(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_path = Path(project.canonical_path)
    files: list[dict] = []

    docs_dir = project_path / "docs"
    if docs_dir.exists():
        for f in sorted(docs_dir.rglob("*.md")):
            files.append(
                {
                    "backend": "obsidian",
                    "path": str(f.relative_to(project_path)).replace("\\", "/"),
                }
            )

    return {"files": files}
