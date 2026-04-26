"""Analytics stats API: cost breakdown, heatmap, doc-completeness history."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import yaml

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import AgentRun, Project

router = APIRouter(prefix="/projects", tags=["stats"])

# Cost per million tokens (input, output) by model substring match
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (0.80, 4.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-7": (15.00, 75.00),
}
_DEFAULT_PRICING = (3.00, 15.00)  # sonnet fallback


def _model_cost_per_mtok(model: str) -> tuple[float, float]:
    for key, pricing in _MODEL_PRICING.items():
        if key in model:
            return pricing
    return _DEFAULT_PRICING

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

    config_raw = project.config or "{}"
    try:
        config_data = json.loads(config_raw)
    except json.JSONDecodeError:
        config_data = {}
    reviewer_model = config_data.get("reviewer_model", "claude-sonnet-4-6")
    cost_in, cost_out = _model_cost_per_mtok(reviewer_model)

    data = []
    for run in runs:
        reviewer_cost = (
            (run.total_input_tokens / 1_000_000) * cost_in
            + (run.total_output_tokens / 1_000_000) * cost_out
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


@router.get("/{project_id}/tests")
async def get_test_status(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_path = Path(project.canonical_path)

    # Prefer structured YAML if it exists (future-proof path)
    yaml_path = project_path / ".smrt" / "knowledge" / "test-status.yaml"
    if yaml_path.exists():
        try:
            raw = yaml_path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            version = data.get("version", 1)
            raw_tests: dict = data.get("tests") or {}
            tests = []
            for name, info in raw_tests.items():
                if not isinstance(info, dict):
                    continue
                last_run_at = info.get("last_run_at")
                tests.append({
                    "name": name,
                    "status": info.get("status", "green"),
                    "last_run_at": last_run_at.isoformat() if hasattr(last_run_at, "isoformat") else (str(last_run_at) if last_run_at is not None else None),
                    "promoted_to": info.get("promoted_to", None),
                    "last_runs": info.get("last_runs") or [],
                })
            return {"version": version, "tests": tests}
        except Exception:
            pass

    # Fall back: discover test files the QA agent actually wrote to .smrt/tests/
    tests_dir = project_path / ".smrt" / "tests"
    if not tests_dir.exists():
        return {"tests": [], "version": 1}

    tests = []
    for test_file in sorted(tests_dir.glob("test_*.py")):  # noqa: ASYNC240
        try:
            stat = test_file.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            mtime_str = mtime.isoformat()
        except OSError:
            mtime_str = None
        tests.append({
            "name": test_file.name,
            "status": "green",
            "last_run_at": mtime_str,
            "promoted_to": None,
            "last_runs": [],
        })

    return {"version": 1, "tests": tests}


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
