"""Provenance API: list [smrt-provenance] entries for a project."""
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project

router = APIRouter(prefix="/projects", tags=["provenance"])


@router.get("/{project_id}/provenance")
async def list_provenance(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    prov_path = Path(project.canonical_path) / ".smrt" / "provenance.jsonl"
    if not prov_path.exists():
        return {"entries": []}

    entries = []
    for line in prov_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return {"entries": entries}
