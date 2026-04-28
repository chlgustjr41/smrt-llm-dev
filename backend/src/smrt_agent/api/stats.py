"""Analytics stats API: cost breakdown and doc-completeness history."""
import ast
import asyncio
import fnmatch
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


def _parse_reviewer_run_cost(runs_dir: Path, run_id: str) -> dict:
    """Return cost_usd, model, and token counts from the 'done' event in a reviewer JSONL."""
    log_path = runs_dir / f"{run_id}.jsonl"
    out = {"cost": 0.0, "model": None, "input_tokens": 0, "output_tokens": 0}
    if not log_path.exists():
        return out
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                if event.get("type") == "done":
                    out["cost"] = float(event.get("cost_usd") or 0)
                    out["model"] = event.get("model")
                    out["input_tokens"] = int(event.get("total_input_tokens") or 0)
                    out["output_tokens"] = int(event.get("total_output_tokens") or 0)
                    break
            except (json.JSONDecodeError, ValueError):
                pass
    except Exception:
        pass
    return out


def _parse_session_costs(sessions_dir: Path, session_id: str) -> dict:
    """Read JSONL events and accumulate QA + Coder costs, tokens, and model names.

    Multiple coder_done events per session are summed (one per fix attempt).
    The last model seen wins for model_qa / model_coder.
    """
    log_path = sessions_dir / f"{session_id}.jsonl"
    out = {
        "qa_cost": 0.0, "coder_cost": 0.0,
        "model_qa": None, "model_coder": None,
        "qa_input_tokens": 0, "qa_output_tokens": 0,
        "coder_input_tokens": 0, "coder_output_tokens": 0,
    }
    if not log_path.exists():
        return out
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                etype = event.get("type", "")
                if etype in ("qa_done", "qa_feedback_done"):
                    out["qa_cost"] += float(event.get("cost_usd") or 0)
                    out["qa_input_tokens"] += int(event.get("total_input_tokens") or 0)
                    out["qa_output_tokens"] += int(event.get("total_output_tokens") or 0)
                    if event.get("model"):
                        out["model_qa"] = event["model"]
                elif etype == "coder_done":
                    out["coder_cost"] += float(event.get("cost_usd") or 0)
                    out["coder_input_tokens"] += int(event.get("total_input_tokens") or 0)
                    out["coder_output_tokens"] += int(event.get("total_output_tokens") or 0)
                    if event.get("model"):
                        out["model_coder"] = event["model"]
            except (json.JSONDecodeError, ValueError):
                pass
    except Exception:
        pass
    return out


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
        rev = await asyncio.to_thread(_parse_reviewer_run_cost, runs_dir, run.run_id)
        data.append({
            "run_id": run.run_id,
            "type": "reviewer_run",
            "ticket_id": None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "reviewer_cost_usd": round(rev["cost"], 6),
            "qa_cost_usd": 0.0,
            "coder_cost_usd": 0.0,
            "reviewer_model": rev["model"] or run.model,
            "qa_model": None,
            "coder_model": None,
            "reviewer_input_tokens": rev["input_tokens"] or (run.total_input_tokens or 0),
            "reviewer_output_tokens": rev["output_tokens"] or (run.total_output_tokens or 0),
            "qa_input_tokens": 0,
            "qa_output_tokens": 0,
            "coder_input_tokens": 0,
            "coder_output_tokens": 0,
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
        s = await asyncio.to_thread(_parse_session_costs, sessions_dir, session.session_id)
        if s["qa_cost"] == 0.0 and s["coder_cost"] == 0.0:
            continue
        data.append({
            "run_id": session.session_id,
            "type": "qa_session",
            "ticket_id": session.ticket_id,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "reviewer_cost_usd": 0.0,
            "qa_cost_usd": round(s["qa_cost"], 6),
            "coder_cost_usd": round(s["coder_cost"], 6),
            "reviewer_model": None,
            "qa_model": s["model_qa"],
            "coder_model": s["model_coder"],
            "reviewer_input_tokens": 0,
            "reviewer_output_tokens": 0,
            "qa_input_tokens": s["qa_input_tokens"],
            "qa_output_tokens": s["qa_output_tokens"],
            "coder_input_tokens": s["coder_input_tokens"],
            "coder_output_tokens": s["coder_output_tokens"],
        })

    data.sort(key=lambda x: x["started_at"] or "")
    return {"runs": data}


# ── Test AST helpers ──────────────────────────────────────────────────────


def _parse_test_functions(test_path: Path) -> list[dict]:
    """Extract test functions and docstrings from a .py test file via AST."""
    try:
        tree = ast.parse(test_path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return []
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            raw = node.name.removeprefix("test_").replace("_", " ")
            docstring = ast.get_docstring(node) or ""
            functions.append({"fn": node.name, "description": raw, "docstring": docstring})
    return functions


def _load_coverage(project_path: Path) -> dict:
    """Load stored coverage.json written by collect_coverage(). Returns {} on miss."""
    cov_path = project_path / ".smrt" / "knowledge" / "coverage.json"
    if not cov_path.exists():
        return {}
    try:
        return json.loads(cov_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_ignore_patterns(project_path: Path) -> list[str]:
    """Return non-comment lines from .gitignore and .agentignore."""
    patterns: list[str] = []
    for name in ('.gitignore', '.agentignore'):
        ignore_file = project_path / name
        if not ignore_file.exists():
            continue
        try:
            for line in ignore_file.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    patterns.append(line)
        except Exception:
            pass
    return patterns


def _is_ignored_path(fpath: str, patterns: list[str]) -> bool:
    """Return True if fpath (relative or absolute, posix-style) matches any pattern."""
    norm = fpath.replace('\\', '/')
    basename = Path(fpath).name
    for pat in patterns:
        pat_norm = pat.replace('\\', '/').rstrip('/')
        if fnmatch.fnmatch(basename, pat_norm):
            return True
        if fnmatch.fnmatch(norm, pat_norm):
            return True
        # Handle plain directory names without wildcards (e.g. "node_modules", "build")
        if '/' not in pat_norm and '*' not in pat_norm:
            parts = norm.split('/')
            if pat_norm in parts:
                return True
    return False


def _load_coverage_context(project_path: Path) -> dict[str, list[str]]:
    """Load coverage_context.json: source basename → [test_node_ids]. Returns {} on miss."""
    ctx_path = project_path / ".smrt" / "knowledge" / "coverage_context.json"
    if not ctx_path.exists():
        return {}
    try:
        data = json.loads(ctx_path.read_text(encoding="utf-8"))
        return data.get("file_tests", {})
    except Exception:
        return {}


@router.get("/{project_id}/tests")
async def get_test_status(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_path = Path(project.canonical_path)
    cov_data = await asyncio.to_thread(_load_coverage, project_path)
    cov_totals: dict = cov_data.get("totals", {})
    cov_files: dict = cov_data.get("files", {})
    overall_coverage: float | None = cov_totals.get("percent_covered")
    file_tests: dict[str, list[str]] = await asyncio.to_thread(_load_coverage_context, project_path)

    ignore_patterns = await asyncio.to_thread(_load_ignore_patterns, project_path)

    # Per-source-file coverage — exclude test files, agent artifacts, and gitignored paths
    file_pct: dict[str, float] = {}
    for fpath, finfo in cov_files.items():
        pct = (finfo.get("summary") or {}).get("percent_covered")
        if pct is None:
            continue
        norm = fpath.replace('\\', '/')
        # Skip anything inside .smrt/ (test files, generated knowledge, etc.)
        if '/.smrt/' in norm or norm.startswith('.smrt/'):
            continue
        # Skip files matching .gitignore / .agentignore patterns
        if _is_ignored_path(norm, ignore_patterns):
            continue
        file_pct[Path(fpath).name] = pct

    # ── Prefer structured YAML ───────────────────────────────────────────────
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
                # Try to find coverage for the associated .py file
                test_path = project_path / ".smrt" / "tests" / name
                functions = await asyncio.to_thread(_parse_test_functions, test_path)
                tests.append({
                    "name": name,
                    "status": info.get("status", "green"),
                    "last_run_at": last_run_at.isoformat() if hasattr(last_run_at, "isoformat") else (str(last_run_at) if last_run_at is not None else None),
                    "promoted_to": info.get("promoted_to", None),
                    "last_runs": info.get("last_runs") or [],
                    "functions": functions,
                    "coverage_pct": None,  # per-test file coverage not easily isolated
                })
            return {"version": version, "tests": tests, "overall_coverage": overall_coverage, "file_coverage": file_pct, "file_tests": file_tests}
        except Exception:
            pass

    # ── Fall back: discover .py files + parse AST ───────────────────────────
    tests_dir = project_path / ".smrt" / "tests"
    if not tests_dir.exists():
        return {"tests": [], "version": 1, "overall_coverage": overall_coverage, "file_coverage": file_pct, "file_tests": file_tests}

    tests = []
    for test_file in sorted(tests_dir.glob("test_*.py")):
        try:
            stat = test_file.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            mtime = None
        functions = await asyncio.to_thread(_parse_test_functions, test_file)
        tests.append({
            "name": test_file.name,
            "status": "green",
            "last_run_at": mtime,
            "promoted_to": None,
            "last_runs": [],
            "functions": functions,
            "coverage_pct": None,
        })

    return {"version": 1, "tests": tests, "overall_coverage": overall_coverage, "file_coverage": file_pct, "file_tests": file_tests}


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
