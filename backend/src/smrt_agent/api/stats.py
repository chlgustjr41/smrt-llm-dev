"""Analytics stats API: cost breakdown, heatmap, doc-completeness history."""
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import AgentRun, Project

router = APIRouter(prefix="/projects", tags=["stats"])

_COST_PER_MTOK_IN = 15.0   # Opus 4.7 input cost per million tokens
_COST_PER_MTOK_OUT = 75.0  # Opus 4.7 output cost per million tokens

_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".smrt", "dist", "build", ".pytest_cache", ".mypy_cache",
}
_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rs", ".rb", ".c", ".cpp", ".h"}


@router.get("/{project_id}/stats/cost")
async def get_cost_stats(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.project_id == project_id)
        .order_by(AgentRun.started_at)
    )
    runs = result.scalars().all()

    data = []
    for run in runs:
        reviewer_cost = (
            (run.total_input_tokens / 1_000_000) * _COST_PER_MTOK_IN
            + (run.total_output_tokens / 1_000_000) * _COST_PER_MTOK_OUT
        )
        data.append({
            "run_id": run.run_id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "reviewer_cost_usd": round(reviewer_cost, 6),
            "qa_cost_usd": 0.0,
            "coder_cost_usd": 0.0,
            "reviewer_input_tokens": run.total_input_tokens,
            "reviewer_output_tokens": run.total_output_tokens,
        })
    return {"runs": data}


@router.get("/{project_id}/stats/heatmap")
async def get_heatmap(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_path = Path(project.canonical_path)

    # Read provenance.jsonl for file → bug count mapping
    file_bug_counts: dict[str, int] = {}
    prov_path = project_path / ".smrt" / "provenance.jsonl"
    if prov_path.exists():
        for line in prov_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                for f in entry.get("sources_consulted", []):
                    file_bug_counts[f] = file_bug_counts.get(f, 0) + 1
            except json.JSONDecodeError:
                pass

    # Scan source files for LOC
    files = []
    for path in project_path.rglob("*"):  # noqa: ASYNC240
        if any(part in _IGNORE_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix not in _SOURCE_EXTS:
            continue
        try:
            loc = max(len(path.read_text(encoding="utf-8", errors="replace").splitlines()), 1)
        except Exception:
            continue
        rel = str(path.relative_to(project_path)).replace("\\", "/")
        files.append({
            "file": rel,
            "loc": loc,
            "bugs_resolved": file_bug_counts.get(rel, 0),
        })

    files.sort(key=lambda x: x["loc"], reverse=True)
    return {"files": files[:50]}


@router.get("/{project_id}/stats/doc-completeness")
async def get_doc_completeness(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    scores_path = Path(project.canonical_path) / ".smrt" / "doc_scores.jsonl"
    if not scores_path.exists():
        return {"history": []}

    history = []
    for line in scores_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            history.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return {"history": history}
