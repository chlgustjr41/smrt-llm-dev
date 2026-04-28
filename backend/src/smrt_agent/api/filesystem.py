from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/filesystem", tags=["filesystem"])


class FsEntry(BaseModel):
    name: str
    path: str
    is_dir: bool


@router.get("", response_model=list[FsEntry])
async def list_directory(path: str = Query(default="/workspace")) -> list[FsEntry]:
    target = Path(path).resolve()

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    entries: list[FsEntry] = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.name.startswith("."):
            continue
        entries.append(FsEntry(name=child.name, path=str(child), is_dir=child.is_dir()))

    return entries
