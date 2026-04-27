"""Analytics stats API: cost breakdown and doc-completeness history."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import yaml

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import AgentRun, Project, QASession

router = APIRouter(prefix="/projects", tags=["stats"])


def _parse_reviewer_run_cost(runs_dir: Path, run_id: str) -> float:
    """Read cost_usd from the 'done' event in a reviewer run JSONL log."""
    log_path = runs_dir / f"{run_id}.jsonl"
    if not log_path.exists():
        return 0.0
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if event.get("type") == "done":
                    return float(event.get("cost_usd") or 0)
            except (json.JSONDecodeError, ValueError):
                pass
    except Exception:
        pass
    return 0.0


def _parse_session_costs(sessions_dir: Path, session_id: str) -> tuple[float, float]:
    """Read JSONL events for a session and sum QA + Coder costs.

    Returns (qa_cost_usd, coder_cost_usd).  Each agent loop emits a *_done
    event with cost_usd already computed; we just accumulate them.
    """
    log_path = sessions_dir / f"{session_id}.jsonl"
    if not log_path.exists():
        return 0.0, 0.0
    qa_cost = 0.0
    coder_cost = 0.0
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                etype = event.get("type", "")
                if etype == "qa_done":
                    qa_cost += float(event.get("cost_usd") or 0)
                elif etype == "coder_done":
                    coder_cost += float(event.get("cost_usd") or 0)
            except (json.JSONDecodeError, ValueError):
                pass
    except Exception:
        pass
    return qa_cost, coder_cost


@router.get("/{project_id}/stats/cost")
async def get_cost_stats(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # ── Reviewer runs ────────────────────────────────────────────────────────
    run_result = await db.execute(
        select(AgentRun)
        .where(AgentRun.project_id == project_id)
        .order_by(AgentRun.started_at)
    )
    runs = run_result.scalars().all()

    runs_dir = Path(project.canonical_path) / ".smrt" / "runs"

    data = []
    for run in runs:
        reviewer_cost = await asyncio.to_thread(
            _parse_reviewer_run_cost, runs_dir, run.run_id
        )
        data.append({
            "run_id": run.run_id,
            "type": "reviewer_run",
            "ticket_id": None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "reviewer_cost_usd": round(reviewer_cost, 6),
            "qa_cost_usd": 0.0,
            "coder_cost_usd": 0.0,
            "reviewer_input_tokens": run.total_input_tokens,
            "reviewer_output_tokens": run.total_output_tokens,
        })

    # ── QA sessions (full + per-ticket) ─────────────────────────────────────
    qa_result = await db.execute(
        select(QASession)
        .where(QASession.project_id == project_id)
        .where(QASession.completed_at.is_not(None))
        .order_by(QASession.started_at)
    )
    qa_sessions = qa_result.scalars().all()

    sessions_dir = Path(project.canonical_path) / ".smrt" / "qa-sessions"

    for session in qa_sessions:
        qa_cost, coder_cost = await asyncio.to_thread(
            _parse_session_costs, sessions_dir, session.session_id
        )
        if qa_cost == 0.0 and coder_cost == 0.0:
            continue  # no billable work logged yet — skip empty entries
        data.append({
            "run_id": session.session_id,
            "type": "qa_session",
            "ticket_id": session.ticket_id,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "reviewer_cost_usd": 0.0,
            "qa_cost_usd": round(qa_cost, 6),
            "coder_cost_usd": round(coder_cost, 6),
            "reviewer_input_tokens": 0,
            "reviewer_output_tokens": 0,
        })

    # Sort chronologically so chart bars are left→right in time order
    data.sort(key=lambda x: x["started_at"] or "")
    return {"runs": data}


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
    for test_file in sorted(tests_dir.glob("test_*.py")):
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
