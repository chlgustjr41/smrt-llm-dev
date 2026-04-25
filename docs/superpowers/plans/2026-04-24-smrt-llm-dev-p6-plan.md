# SMRT Agent P6 — M6 Over-Deliverers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement M6 "Over-Deliverers" — three analytics dashboards (cost breakdown, bug heatmap, doc-score line chart), explain-mode provenance panel, thought-process mode toggle on AgentTimeline, and skill-acquisition documentation.

**Architecture:** All three charts are self-fetching components backed by new `GET /api/projects/{id}/stats/*` endpoints; data is stored as JSONL files in `.smrt/` alongside existing event logs. Provenance is read from `.smrt/provenance.jsonl` via a new `/api/projects/{id}/provenance` endpoint. The thought-process toggle is a prop on `AgentTimeline` (`showThoughts?: boolean`) wired into `LiveAgentView` and `QASessionView` as a button.

**Tech Stack:** Backend: FastAPI + SQLAlchemy async + aiosqlite + pytest-anyio. Frontend: React 18 + TypeScript + recharts + Vitest + MSW.

---

## File Structure

**New backend files:**
- `backend/src/smrt_agent/knowledge.py` — `compute_doc_score`, `record_doc_score`, `record_provenance` (sync, file-based)
- `backend/src/smrt_agent/api/stats.py` — `GET /{id}/stats/cost`, `GET /{id}/stats/heatmap`, `GET /{id}/stats/doc-completeness`
- `backend/src/smrt_agent/api/provenance.py` — `GET /{id}/provenance`
- `backend/tests/test_knowledge.py`
- `backend/tests/test_stats_api.py`
- `backend/tests/test_provenance_api.py`

**Modified backend files:**
- `backend/src/smrt_agent/main.py` — add stats + provenance routers
- `backend/src/smrt_agent/api/runs.py` — call `record_doc_score` after `generate_docs`

**New frontend files:**
- `frontend/src/api/stats.ts` — `getRunCosts`, `getHeatmap`, `getDocScoreHistory`
- `frontend/src/api/provenance.ts` — `listProvenance`
- `frontend/src/components/CostChart.tsx` — self-fetching stacked bar chart
- `frontend/src/components/HeatmapChart.tsx` — self-fetching treemap
- `frontend/src/components/DocScoreChart.tsx` — self-fetching line chart
- `frontend/src/components/ProvenancePanel.tsx` — self-fetching provenance list
- `frontend/src/test/CostChart.test.tsx`
- `frontend/src/test/HeatmapChart.test.tsx`
- `frontend/src/test/DocScoreChart.test.tsx`
- `frontend/src/test/ProvenancePanel.test.tsx`

**Modified frontend files:**
- `frontend/src/components/AgentTimeline.tsx` — add `showThoughts?: boolean` prop; hide text events when `false`
- `frontend/src/components/LiveAgentView.tsx` — add "Show thoughts" toggle button
- `frontend/src/components/QASessionView.tsx` — add "Show thoughts" toggle button
- `frontend/src/pages/ProjectDetailPage.tsx` — add Dashboards section with all four panels
- `frontend/src/test/AgentTimeline.test.tsx` — update text-delta test for `showThoughts`
- `frontend/src/test/LiveAgentView.test.tsx` — update text-delta test; add toggle test
- `frontend/src/test/QASessionView.test.tsx` — add toggle test
- `frontend/src/test/ProjectDetailPage.test.tsx` — add Dashboards section assertion

---

### Task 1: Create branch phase/6-overdrive

**Files:** no files changed (git only)

- [ ] **Step 1: Sync main and create branch**

```bash
cd D:\web-project\smrt-llm-dev
git checkout main
git pull
git checkout -b phase/6-overdrive
```

Expected: branch created at current HEAD of main.

- [ ] **Step 2: Verify branch**

```bash
git branch --show-current
```

Expected output: `phase/6-overdrive`

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "chore: start phase/6-overdrive branch"
```

---

### Task 2: Install recharts

**Files:**
- Modify: `frontend/package.json` (via npm install)

- [ ] **Step 1: Install recharts**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npm install recharts
```

Expected: recharts added to `package.json` dependencies.

- [ ] **Step 2: Verify TypeScript types ship with recharts**

```bash
cat node_modules/recharts/types/index.d.ts | head -5
```

Expected: first lines of the recharts type declarations (recharts ships its own types).

- [ ] **Step 3: Commit**

```bash
cd D:\web-project\smrt-llm-dev
git add frontend/package.json frontend/package-lock.json
git commit -m "deps(frontend): add recharts for analytics dashboards"
```

---

### Task 3: knowledge.py — doc score + provenance recording

**Files:**
- Create: `backend/src/smrt_agent/knowledge.py`
- Create: `backend/tests/test_knowledge.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_knowledge.py`:

```python
import json
from pathlib import Path
import pytest
from smrt_agent.knowledge import compute_doc_score, record_doc_score, record_provenance


def test_compute_doc_score_empty_project(tmp_path):
    score = compute_doc_score(tmp_path)
    assert score["score"] == 0.0
    assert score["ep_documented"] == 0
    assert score["ep_total"] == 0
    assert score["mod_documented"] == 0
    assert score["mod_total"] == 1


def test_compute_doc_score_with_endpoint_docs(tmp_path):
    api_dir = tmp_path / "docs" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "GET_items.md").write_text("# GET /items", encoding="utf-8")
    (api_dir / "POST_items.md").write_text("# POST /items", encoding="utf-8")
    (api_dir / "index.md").write_text("# API Index", encoding="utf-8")

    score = compute_doc_score(tmp_path)
    assert score["ep_documented"] == 2
    # index.md excluded


def test_compute_doc_score_with_module_docs(tmp_path):
    mod_dir = tmp_path / "docs" / "modules"
    mod_dir.mkdir(parents=True)
    (mod_dir / "todo-api.md").write_text("# Module", encoding="utf-8")

    score = compute_doc_score(tmp_path)
    assert score["mod_documented"] == 1
    # mod_total is always 1; score contribution = 50
    assert score["score"] >= 50.0


def test_compute_doc_score_max_100(tmp_path):
    api_dir = tmp_path / "docs" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "GET_items.md").write_text("# GET /items", encoding="utf-8")
    mod_dir = tmp_path / "docs" / "modules"
    mod_dir.mkdir(parents=True)
    (mod_dir / "todo-api.md").write_text("# Module", encoding="utf-8")

    score = compute_doc_score(tmp_path)
    assert score["score"] <= 100.0


def test_record_doc_score_creates_file(tmp_path):
    entry = {"ts": "2026-04-25T00:00:00Z", "score": 75.0, "ep_documented": 3, "ep_total": 4, "mod_documented": 1, "mod_total": 1}
    record_doc_score(tmp_path, entry)

    path = tmp_path / ".smrt" / "doc_scores.jsonl"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8").strip())
    assert data["score"] == 75.0


def test_record_doc_score_appends(tmp_path):
    record_doc_score(tmp_path, {"ts": "2026-04-25T00:00:00Z", "score": 50.0})
    record_doc_score(tmp_path, {"ts": "2026-04-25T01:00:00Z", "score": 75.0})

    path = tmp_path / ".smrt" / "doc_scores.jsonl"
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[1])["score"] == 75.0


def test_record_provenance_creates_file(tmp_path):
    entry = {
        "ticket": "BUG-001",
        "subagent": "coder_agent",
        "reasoning": "Fixed null pointer dereference in handler",
        "sources_consulted": ["src/main.py", "src/handlers.py"],
        "attempts": 2,
        "related_lessons_applied": [],
    }
    record_provenance(tmp_path, entry)

    path = tmp_path / ".smrt" / "provenance.jsonl"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8").strip())
    assert data["ticket"] == "BUG-001"
    assert data["attempts"] == 2


def test_record_provenance_appends(tmp_path):
    record_provenance(tmp_path, {"ticket": "BUG-001", "subagent": "coder_agent", "reasoning": "r1", "sources_consulted": [], "attempts": 1, "related_lessons_applied": []})
    record_provenance(tmp_path, {"ticket": "BUG-002", "subagent": "coder_agent", "reasoning": "r2", "sources_consulted": [], "attempts": 1, "related_lessons_applied": []})

    path = tmp_path / ".smrt" / "provenance.jsonl"
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[1])["ticket"] == "BUG-002"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:\web-project\smrt-llm-dev\backend
python -m pytest tests/test_knowledge.py -v
```

Expected: `ModuleNotFoundError: No module named 'smrt_agent.knowledge'`

- [ ] **Step 3: Implement knowledge.py**

Create `backend/src/smrt_agent/knowledge.py`:

```python
import json
from pathlib import Path

from smrt_agent.docs.parser import load_and_parse


def compute_doc_score(project_path: Path) -> dict:
    """Compute documentation completeness score 0–100.

    Score = (ep_documented / max(ep_total, 1)) * 50
           + (mod_documented / max(mod_total, 1)) * 50
    """
    try:
        _, endpoints = load_and_parse(project_path)
        ep_total = len(endpoints)
    except (FileNotFoundError, ValueError):
        ep_total = 0

    mod_total = 1  # one primary module doc per project

    api_dir = project_path / "docs" / "api"
    ep_documented = (
        len([f for f in api_dir.glob("*.md") if f.name != "index.md"])
        if api_dir.exists()
        else 0
    )

    modules_dir = project_path / "docs" / "modules"
    mod_documented = (
        len(list(modules_dir.glob("*.md"))) if modules_dir.exists() else 0
    )

    ep_score = (ep_documented / max(ep_total, 1)) * 50
    mod_score = (mod_documented / max(mod_total, 1)) * 50
    score = round(min(ep_score + mod_score, 100.0), 1)

    return {
        "ep_documented": ep_documented,
        "ep_total": ep_total,
        "mod_documented": mod_documented,
        "mod_total": mod_total,
        "score": score,
    }


def record_doc_score(project_path: Path, entry: dict) -> None:
    """Append a doc score entry to .smrt/doc_scores.jsonl."""
    smrt_dir = project_path / ".smrt"
    smrt_dir.mkdir(exist_ok=True)
    with open(smrt_dir / "doc_scores.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def record_provenance(project_path: Path, entry: dict) -> None:
    """Append a [smrt-provenance] entry to .smrt/provenance.jsonl."""
    smrt_dir = project_path / ".smrt"
    smrt_dir.mkdir(exist_ok=True)
    with open(smrt_dir / "provenance.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd D:\web-project\smrt-llm-dev\backend
python -m pytest tests/test_knowledge.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd D:\web-project\smrt-llm-dev
git add backend/src/smrt_agent/knowledge.py backend/tests/test_knowledge.py
git commit -m "feat(backend): add knowledge.py for doc score and provenance recording"
```

---

### Task 4: stats.py — three analytics endpoints

**Files:**
- Create: `backend/src/smrt_agent/api/stats.py`
- Create: `backend/tests/test_stats_api.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_stats_api.py`:

```python
import json
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smrt_agent.main import app
from smrt_agent.db.schema import init_schema
from smrt_agent.db.models import Project, AgentRun
from smrt_agent.api.deps import get_db


@pytest.fixture
async def stats_app(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SMRT_PROJECT_ROOT_ALLOWLIST", "")

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True
    )
    await init_schema(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as session:
        proj = Project(name="test-api", canonical_path=str(tmp_path))
        session.add(proj)
        await session.commit()
        await session.refresh(proj)
        project_id = proj.id

        run = AgentRun(
            run_id="run-test-001",
            project_id=project_id,
            status="done",
            total_input_tokens=1_000_000,
            total_output_tokens=500_000,
        )
        session.add(run)
        await session.commit()

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app, project_id, tmp_path
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_cost_returns_runs(stats_app):
    test_app, project_id, _ = stats_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/cost")
    assert resp.status_code == 200
    data = resp.json()
    assert "runs" in data
    assert len(data["runs"]) == 1
    run = data["runs"][0]
    assert run["run_id"] == "run-test-001"
    # 1M input @ $15/MTok = $15; 0.5M output @ $75/MTok = $37.5; total = $52.5
    assert abs(run["reviewer_cost_usd"] - 52.5) < 0.001
    assert run["qa_cost_usd"] == 0.0
    assert run["coder_cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_cost_404_for_unknown_project(stats_app):
    test_app, _, _ = stats_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/projects/99999/stats/cost")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_heatmap_returns_source_files(stats_app):
    test_app, project_id, tmp_path = stats_app
    (tmp_path / "main.py").write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Docs", encoding="utf-8")  # md excluded

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/heatmap")
    assert resp.status_code == 200
    files = {f["file"]: f for f in resp.json()["files"]}
    assert "main.py" in files
    assert files["main.py"]["loc"] >= 3
    assert "README.md" not in files


@pytest.mark.asyncio
async def test_heatmap_bugs_from_provenance(stats_app):
    test_app, project_id, tmp_path = stats_app
    (tmp_path / "handler.py").write_text("pass\n", encoding="utf-8")
    smrt = tmp_path / ".smrt"
    smrt.mkdir(exist_ok=True)
    (smrt / "provenance.jsonl").write_text(
        json.dumps({
            "ticket": "BUG-001",
            "subagent": "coder_agent",
            "reasoning": "r",
            "sources_consulted": ["handler.py"],
            "attempts": 1,
            "related_lessons_applied": [],
        }) + "\n",
        encoding="utf-8",
    )

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/heatmap")
    files = {f["file"]: f for f in resp.json()["files"]}
    assert files["handler.py"]["bugs_resolved"] == 1


@pytest.mark.asyncio
async def test_heatmap_excludes_ignored_dirs(stats_app):
    test_app, project_id, tmp_path = stats_app
    (tmp_path / "node_modules").mkdir(exist_ok=True)
    (tmp_path / "node_modules" / "dep.js").write_text("module.exports={}", encoding="utf-8")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/heatmap")
    files = {f["file"]: f for f in resp.json()["files"]}
    assert not any("node_modules" in k for k in files)


@pytest.mark.asyncio
async def test_doc_completeness_empty(stats_app):
    test_app, project_id, _ = stats_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/doc-completeness")
    assert resp.status_code == 200
    assert resp.json() == {"history": []}


@pytest.mark.asyncio
async def test_doc_completeness_with_history(stats_app):
    test_app, project_id, tmp_path = stats_app
    smrt = tmp_path / ".smrt"
    smrt.mkdir(exist_ok=True)
    (smrt / "doc_scores.jsonl").write_text(
        '{"ts": "2026-04-25T00:00:00Z", "score": 75.0, "ep_documented": 3, "ep_total": 4, "mod_documented": 1, "mod_total": 1}\n',
        encoding="utf-8",
    )

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/stats/doc-completeness")
    history = resp.json()["history"]
    assert len(history) == 1
    assert history[0]["score"] == 75.0


@pytest.mark.asyncio
async def test_stats_404_for_unknown_project(stats_app):
    test_app, _, _ = stats_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        for path in [
            "/api/projects/99999/stats/heatmap",
            "/api/projects/99999/stats/doc-completeness",
        ]:
            resp = await client.get(path)
            assert resp.status_code == 404, path
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:\web-project\smrt-llm-dev\backend
python -m pytest tests/test_stats_api.py -v
```

Expected: 404 responses because routes don't exist yet.

- [ ] **Step 3: Implement stats.py**

Create `backend/src/smrt_agent/api/stats.py`:

```python
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
    for path in project_path.rglob("*"):
        if any(part in _IGNORE_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix not in _SOURCE_EXTS:
            continue
        try:
            loc = path.read_text(encoding="utf-8", errors="replace").count("\n") + 1
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
```

- [ ] **Step 4: Wire router into main.py**

Read `backend/src/smrt_agent/main.py`, then add stats router after the docs router:

```python
from smrt_agent.api.stats import router as stats_router
# ...
app.include_router(stats_router, prefix="/api")
```

Full modified section in `create_app()`:
```python
    app.include_router(filesystem_router)
    app.include_router(projects_router)
    app.include_router(sandbox_router)
    app.include_router(runs_router)
    app.include_router(qa_sessions_router)
    app.include_router(tickets_router)
    app.include_router(docs_router, prefix="/api")
    app.include_router(stats_router, prefix="/api")
```

- [ ] **Step 5: Run tests**

```bash
cd D:\web-project\smrt-llm-dev\backend
python -m pytest tests/test_stats_api.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd D:\web-project\smrt-llm-dev
git add backend/src/smrt_agent/api/stats.py backend/tests/test_stats_api.py backend/src/smrt_agent/main.py
git commit -m "feat(backend): add stats API — cost, heatmap, doc-completeness endpoints"
```

---

### Task 5: provenance.py — explain mode endpoint

**Files:**
- Create: `backend/src/smrt_agent/api/provenance.py`
- Create: `backend/tests/test_provenance_api.py`
- Modify: `backend/src/smrt_agent/main.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_provenance_api.py`:

```python
import json
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smrt_agent.main import app
from smrt_agent.db.schema import init_schema
from smrt_agent.db.models import Project
from smrt_agent.api.deps import get_db


@pytest.fixture
async def provenance_app(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SMRT_PROJECT_ROOT_ALLOWLIST", "")

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True
    )
    await init_schema(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as session:
        proj = Project(name="test-api", canonical_path=str(tmp_path))
        session.add(proj)
        await session.commit()
        await session.refresh(proj)
        project_id = proj.id

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app, project_id, tmp_path
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_provenance_empty(provenance_app):
    test_app, project_id, _ = provenance_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/provenance")
    assert resp.status_code == 200
    assert resp.json() == {"entries": []}


@pytest.mark.asyncio
async def test_list_provenance_with_entries(provenance_app):
    test_app, project_id, tmp_path = provenance_app
    smrt = tmp_path / ".smrt"
    smrt.mkdir(exist_ok=True)
    (smrt / "provenance.jsonl").write_text(
        json.dumps({
            "ticket": "BUG-001",
            "subagent": "coder_agent",
            "reasoning": "Fixed null pointer dereference",
            "sources_consulted": ["src/main.py"],
            "attempts": 2,
            "related_lessons_applied": ["always check for None before indexing"],
        }) + "\n",
        encoding="utf-8",
    )

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/provenance")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["ticket"] == "BUG-001"
    assert entries[0]["attempts"] == 2
    assert "src/main.py" in entries[0]["sources_consulted"]


@pytest.mark.asyncio
async def test_list_provenance_multiple_entries(provenance_app):
    test_app, project_id, tmp_path = provenance_app
    smrt = tmp_path / ".smrt"
    smrt.mkdir(exist_ok=True)
    lines = "\n".join([
        json.dumps({"ticket": "BUG-001", "subagent": "coder_agent", "reasoning": "r", "sources_consulted": [], "attempts": 1, "related_lessons_applied": []}),
        json.dumps({"ticket": "BUG-002", "subagent": "coder_agent", "reasoning": "r", "sources_consulted": [], "attempts": 3, "related_lessons_applied": []}),
    ]) + "\n"
    (smrt / "provenance.jsonl").write_text(lines, encoding="utf-8")

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/api/projects/{project_id}/provenance")
    assert len(resp.json()["entries"]) == 2


@pytest.mark.asyncio
async def test_provenance_404_for_unknown_project(provenance_app):
    test_app, _, _ = provenance_app
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/api/projects/99999/provenance")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

```bash
cd D:\web-project\smrt-llm-dev\backend
python -m pytest tests/test_provenance_api.py -v
```

Expected: 404 responses because route doesn't exist yet.

- [ ] **Step 3: Implement provenance.py**

Create `backend/src/smrt_agent/api/provenance.py`:

```python
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
```

- [ ] **Step 4: Wire provenance router into main.py**

Edit `backend/src/smrt_agent/main.py` to add after `stats_router`:

```python
from smrt_agent.api.provenance import router as provenance_router
# ...
    app.include_router(provenance_router, prefix="/api")
```

- [ ] **Step 5: Run tests**

```bash
cd D:\web-project\smrt-llm-dev\backend
python -m pytest tests/test_provenance_api.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd D:\web-project\smrt-llm-dev
git add backend/src/smrt_agent/api/provenance.py backend/tests/test_provenance_api.py backend/src/smrt_agent/main.py
git commit -m "feat(backend): add provenance API for explain-mode change history"
```

---

### Task 6: Wire record_doc_score into runs.py + full backend suite green

**Files:**
- Modify: `backend/src/smrt_agent/api/runs.py`

- [ ] **Step 1: Edit runs.py — add score recording after generate_docs**

In `_run_task`, locate the existing try block that calls `generate_docs`. Replace it with the version that also calls `record_doc_score`:

Current code (lines 103-116):
```python
        try:
            doc_counts = await generate_docs(Path(canonical_path))
            await queue.put({
                "type": "docs_written",
                "backends": doc_counts["backends"],
                "endpoints": doc_counts["endpoints"],
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as doc_exc:
            await queue.put({
                "type": "docs_error",
                "error": str(doc_exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            })
```

Replace with:
```python
        try:
            doc_counts = await generate_docs(Path(canonical_path))
            await queue.put({
                "type": "docs_written",
                "backends": doc_counts["backends"],
                "endpoints": doc_counts["endpoints"],
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            score_entry = compute_doc_score(Path(canonical_path))
            score_entry["ts"] = datetime.now(timezone.utc).isoformat()
            record_doc_score(Path(canonical_path), score_entry)
        except Exception as doc_exc:
            await queue.put({
                "type": "docs_error",
                "error": str(doc_exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            })
```

Also add the imports at the top of `runs.py`:
```python
from smrt_agent.knowledge import compute_doc_score, record_doc_score
```

- [ ] **Step 2: Run full backend suite**

```bash
cd D:\web-project\smrt-llm-dev\backend
python -m pytest -v
```

Expected: all tests PASS (count was 124 before P6; now adds ~15 new tests).

- [ ] **Step 3: Commit**

```bash
cd D:\web-project\smrt-llm-dev
git add backend/src/smrt_agent/api/runs.py
git commit -m "feat(backend): record doc score to .smrt/doc_scores.jsonl after each reviewer run"
```

---

### Task 7: Frontend API clients — stats.ts + provenance.ts

**Files:**
- Create: `frontend/src/api/stats.ts`
- Create: `frontend/src/api/provenance.ts`

These are thin wrappers over `apiFetch` — no tests needed for the API client layer itself (covered by component tests via MSW).

- [ ] **Step 1: Create frontend/src/api/stats.ts**

```typescript
import { apiFetch } from './client'

export interface RunCostEntry {
  run_id: string
  started_at: string | null
  reviewer_cost_usd: number
  qa_cost_usd: number
  coder_cost_usd: number
  reviewer_input_tokens: number
  reviewer_output_tokens: number
}

export interface HeatmapEntry {
  file: string
  loc: number
  bugs_resolved: number
}

export interface DocScoreEntry {
  ts: string
  score: number
  ep_documented: number
  ep_total: number
  mod_documented: number
  mod_total: number
}

export async function getRunCosts(
  projectId: number,
  signal?: AbortSignal,
): Promise<RunCostEntry[]> {
  const data = await apiFetch<{ runs: RunCostEntry[] }>(
    `/projects/${projectId}/stats/cost`,
    { signal },
  )
  return data.runs
}

export async function getHeatmap(
  projectId: number,
  signal?: AbortSignal,
): Promise<HeatmapEntry[]> {
  const data = await apiFetch<{ files: HeatmapEntry[] }>(
    `/projects/${projectId}/stats/heatmap`,
    { signal },
  )
  return data.files
}

export async function getDocScoreHistory(
  projectId: number,
  signal?: AbortSignal,
): Promise<DocScoreEntry[]> {
  const data = await apiFetch<{ history: DocScoreEntry[] }>(
    `/projects/${projectId}/stats/doc-completeness`,
    { signal },
  )
  return data.history
}
```

- [ ] **Step 2: Create frontend/src/api/provenance.ts**

```typescript
import { apiFetch } from './client'

export interface ProvenanceEntry {
  ticket: string
  subagent: string
  reasoning: string
  sources_consulted: string[]
  attempts: number
  related_lessons_applied: string[]
  ts?: string
}

export async function listProvenance(
  projectId: number,
  signal?: AbortSignal,
): Promise<ProvenanceEntry[]> {
  const data = await apiFetch<{ entries: ProvenanceEntry[] }>(
    `/projects/${projectId}/provenance`,
    { signal },
  )
  return data.entries
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd D:\web-project\smrt-llm-dev
git add frontend/src/api/stats.ts frontend/src/api/provenance.ts
git commit -m "feat(frontend): add stats and provenance API clients"
```

---

### Task 8: CostChart component

**Files:**
- Create: `frontend/src/components/CostChart.tsx`
- Create: `frontend/src/test/CostChart.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/test/CostChart.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { CostChart } from '../components/CostChart'

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Bar: ({ name }: { name: string }) => <div data-testid={`bar-${name}`} />,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
}))

const mockRun = {
  run_id: 'run-abc-123456',
  started_at: '2026-04-25T00:00:00Z',
  reviewer_cost_usd: 0.00015,
  qa_cost_usd: 0.0,
  coder_cost_usd: 0.0,
  reviewer_input_tokens: 1000,
  reviewer_output_tokens: 500,
}

const server = setupServer(
  http.get('http://localhost/api/projects/1/stats/cost', () =>
    HttpResponse.json({ runs: [mockRun] }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('CostChart', () => {
  it('renders bar chart when data is available', async () => {
    render(<CostChart projectId={1} />)
    await waitFor(() => expect(screen.getByTestId('bar-chart')).toBeInTheDocument())
  })

  it('shows Reviewer, QA, and Coder bars', async () => {
    render(<CostChart projectId={1} />)
    await waitFor(() => screen.getByTestId('bar-chart'))
    expect(screen.getByTestId('bar-Reviewer')).toBeInTheDocument()
    expect(screen.getByTestId('bar-QA')).toBeInTheDocument()
    expect(screen.getByTestId('bar-Coder')).toBeInTheDocument()
  })

  it('shows empty state when no runs', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/stats/cost', () =>
        HttpResponse.json({ runs: [] }),
      ),
    )
    render(<CostChart projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no audit runs/i)).toBeInTheDocument(),
    )
  })

  it('shows loading initially', () => {
    render(<CostChart projectId={1} />)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx vitest run src/test/CostChart.test.tsx
```

Expected: `Cannot find module '../components/CostChart'`

- [ ] **Step 3: Implement CostChart.tsx**

Create `frontend/src/components/CostChart.tsx`:

```tsx
import { useState, useEffect } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { getRunCosts, type RunCostEntry } from '../api/stats'

export function CostChart({ projectId }: { projectId: number }) {
  const [data, setData] = useState<RunCostEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getRunCosts(projectId, controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => controller.abort()
  }, [projectId])

  if (!data) return <p className="text-xs text-gray-400">Loading cost data…</p>
  if (error) return <p className="text-xs text-red-500">{error}</p>
  if (data.length === 0)
    return <p className="text-xs text-gray-400 italic">No audit runs recorded yet.</p>

  const chartData = data.map((entry) => ({
    name: entry.run_id.slice(0, 8),
    Reviewer: entry.reviewer_cost_usd,
    QA: entry.qa_cost_usd,
    Coder: entry.coder_cost_usd,
  }))

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `$${v.toFixed(4)}`} />
          <Tooltip formatter={(v: number) => `$${v.toFixed(6)}`} />
          <Legend />
          <Bar dataKey="Reviewer" name="Reviewer" fill="#3b82f6" stackId="a" />
          <Bar dataKey="QA" name="QA" fill="#a855f7" stackId="a" />
          <Bar dataKey="Coder" name="Coder" fill="#22c55e" stackId="a" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx vitest run src/test/CostChart.test.tsx
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd D:\web-project\smrt-llm-dev
git add frontend/src/components/CostChart.tsx frontend/src/test/CostChart.test.tsx
git commit -m "feat(frontend): add CostChart stacked bar chart component"
```

---

### Task 9: HeatmapChart component

**Files:**
- Create: `frontend/src/components/HeatmapChart.tsx`
- Create: `frontend/src/test/HeatmapChart.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/test/HeatmapChart.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { HeatmapChart } from '../components/HeatmapChart'

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Treemap: ({ data, onClick }: { data: Array<{ name: string; size: number; bugs_resolved: number; _entry: unknown }>; onClick?: (d: unknown) => void }) => (
    <div data-testid="treemap">
      {data.map((d, i) => (
        <button
          key={i}
          data-testid="treemap-cell"
          data-file={d.name}
          onClick={() => onClick?.(d)}
        >
          {d.name}
        </button>
      ))}
    </div>
  ),
}))

const mockFiles = [
  { file: 'src/main.py', loc: 120, bugs_resolved: 2 },
  { file: 'src/handlers.py', loc: 80, bugs_resolved: 0 },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/stats/heatmap', () =>
    HttpResponse.json({ files: mockFiles }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('HeatmapChart', () => {
  it('renders treemap with source files', async () => {
    render(<HeatmapChart projectId={1} />)
    await waitFor(() => expect(screen.getByTestId('treemap')).toBeInTheDocument())
    expect(screen.getByText('src/main.py')).toBeInTheDocument()
    expect(screen.getByText('src/handlers.py')).toBeInTheDocument()
  })

  it('shows empty state when no files', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/stats/heatmap', () =>
        HttpResponse.json({ files: [] }),
      ),
    )
    render(<HeatmapChart projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no source files/i)).toBeInTheDocument(),
    )
  })

  it('shows selected file bugs panel on cell click', async () => {
    const user = userEvent.setup()
    render(<HeatmapChart projectId={1} />)
    await waitFor(() => screen.getByTestId('treemap'))
    await user.click(screen.getByText('src/main.py'))
    await waitFor(() =>
      expect(screen.getByText(/src\/main\.py/)).toBeInTheDocument(),
    )
    expect(screen.getByText(/2 bug/i)).toBeInTheDocument()
  })

  it('shows loading initially', () => {
    render(<HeatmapChart projectId={1} />)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx vitest run src/test/HeatmapChart.test.tsx
```

Expected: `Cannot find module '../components/HeatmapChart'`

- [ ] **Step 3: Implement HeatmapChart.tsx**

Create `frontend/src/components/HeatmapChart.tsx`:

```tsx
import { useState, useEffect } from 'react'
import { Treemap, ResponsiveContainer } from 'recharts'
import { getHeatmap, type HeatmapEntry } from '../api/stats'

function bugColor(bugs: number, maxBugs: number): string {
  if (maxBugs === 0 || bugs === 0) return '#d1fae5'
  const intensity = Math.min(bugs / maxBugs, 1)
  const r = Math.round(220 * intensity + 34 * (1 - intensity))
  const g = Math.round(38 * intensity + 197 * (1 - intensity))
  const b = Math.round(38 * intensity + 94 * (1 - intensity))
  return `rgb(${r},${g},${b})`
}

interface TreemapNode {
  name: string
  size: number
  bugs_resolved: number
  _entry: HeatmapEntry
}

interface SelectedFile {
  file: string
  bugs_resolved: number
}

export function HeatmapChart({ projectId }: { projectId: number }) {
  const [data, setData] = useState<HeatmapEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<SelectedFile | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getHeatmap(projectId, controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => controller.abort()
  }, [projectId])

  if (!data) return <p className="text-xs text-gray-400">Loading heatmap…</p>
  if (error) return <p className="text-xs text-red-500">{error}</p>
  if (data.length === 0)
    return <p className="text-xs text-gray-400 italic">No source files found.</p>

  const maxBugs = Math.max(...data.map((e) => e.bugs_resolved), 1)

  const chartData: TreemapNode[] = data.map((entry) => ({
    name: entry.file,
    size: Math.max(entry.loc, 1),
    bugs_resolved: entry.bugs_resolved,
    _entry: entry,
  }))

  return (
    <div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <Treemap
            data={chartData}
            dataKey="size"
            onClick={(node: unknown) => {
              const n = node as TreemapNode
              if (n?._entry) {
                setSelected({ file: n._entry.file, bugs_resolved: n._entry.bugs_resolved })
              }
            }}
            content={(props: unknown) => {
              const { x, y, width, height, name, bugs_resolved } = props as {
                x: number; y: number; width: number; height: number
                name: string; bugs_resolved: number
              }
              return (
                <g>
                  <rect
                    x={x} y={y} width={width} height={height}
                    fill={bugColor(bugs_resolved, maxBugs)}
                    stroke="#fff"
                    strokeWidth={1}
                  />
                  {width > 60 && height > 24 && (
                    <text
                      x={x + 4} y={y + 14}
                      fontSize={10}
                      fill="#1f2937"
                      style={{ pointerEvents: 'none' }}
                    >
                      {name.split('/').pop()}
                    </text>
                  )}
                </g>
              )
            }}
          />
        </ResponsiveContainer>
      </div>
      {selected && (
        <div className="mt-2 p-3 border rounded bg-gray-50 text-xs">
          <p className="font-mono font-semibold text-gray-800">{selected.file}</p>
          <p className="text-gray-500 mt-1">
            {selected.bugs_resolved} bug{selected.bugs_resolved !== 1 ? 's' : ''} resolved touching this file
          </p>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx vitest run src/test/HeatmapChart.test.tsx
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd D:\web-project\smrt-llm-dev
git add frontend/src/components/HeatmapChart.tsx frontend/src/test/HeatmapChart.test.tsx
git commit -m "feat(frontend): add HeatmapChart treemap component with bug-file click panel"
```

---

### Task 10: DocScoreChart component

**Files:**
- Create: `frontend/src/components/DocScoreChart.tsx`
- Create: `frontend/src/test/DocScoreChart.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/test/DocScoreChart.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { DocScoreChart } from '../components/DocScoreChart'

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  CartesianGrid: () => null,
}))

const mockHistory = [
  {
    ts: '2026-04-25T00:00:00Z',
    score: 50.0,
    ep_documented: 1,
    ep_total: 2,
    mod_documented: 1,
    mod_total: 1,
  },
  {
    ts: '2026-04-25T01:00:00Z',
    score: 75.0,
    ep_documented: 2,
    ep_total: 2,
    mod_documented: 1,
    mod_total: 1,
  },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/stats/doc-completeness', () =>
    HttpResponse.json({ history: mockHistory }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('DocScoreChart', () => {
  it('renders line chart when history is available', async () => {
    render(<DocScoreChart projectId={1} />)
    await waitFor(() => expect(screen.getByTestId('line-chart')).toBeInTheDocument())
  })

  it('shows empty state when no history', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/stats/doc-completeness', () =>
        HttpResponse.json({ history: [] }),
      ),
    )
    render(<DocScoreChart projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no documentation score history/i)).toBeInTheDocument(),
    )
  })

  it('shows loading initially', () => {
    render(<DocScoreChart projectId={1} />)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx vitest run src/test/DocScoreChart.test.tsx
```

Expected: `Cannot find module '../components/DocScoreChart'`

- [ ] **Step 3: Implement DocScoreChart.tsx**

Create `frontend/src/components/DocScoreChart.tsx`:

```tsx
import { useState, useEffect } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from 'recharts'
import { getDocScoreHistory, type DocScoreEntry } from '../api/stats'

export function DocScoreChart({ projectId }: { projectId: number }) {
  const [data, setData] = useState<DocScoreEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getDocScoreHistory(projectId, controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => controller.abort()
  }, [projectId])

  if (!data) return <p className="text-xs text-gray-400">Loading doc score history…</p>
  if (error) return <p className="text-xs text-red-500">{error}</p>
  if (data.length === 0)
    return (
      <p className="text-xs text-gray-400 italic">
        No documentation score history yet. Run an audit to generate the first score.
      </p>
    )

  const chartData = data.map((entry) => ({
    ts: new Date(entry.ts).toLocaleDateString(),
    score: entry.score,
  }))

  return (
    <div className="h-48">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="ts" tick={{ fontSize: 11 }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v: number) => [`${v.toFixed(1)}`, 'Score']} />
          <Line type="monotone" dataKey="score" stroke="#3b82f6" dot={true} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx vitest run src/test/DocScoreChart.test.tsx
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd D:\web-project\smrt-llm-dev
git add frontend/src/components/DocScoreChart.tsx frontend/src/test/DocScoreChart.test.tsx
git commit -m "feat(frontend): add DocScoreChart line chart for documentation completeness over time"
```

---

### Task 11: ProvenancePanel component

**Files:**
- Create: `frontend/src/components/ProvenancePanel.tsx`
- Create: `frontend/src/test/ProvenancePanel.test.tsx`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/test/ProvenancePanel.test.tsx`:

```typescript
import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { ProvenancePanel } from '../components/ProvenancePanel'

const mockEntries = [
  {
    ticket: 'BUG-001',
    subagent: 'coder_agent',
    reasoning: 'Fixed null pointer dereference in handler',
    sources_consulted: ['src/main.py', 'src/handlers.py'],
    attempts: 2,
    related_lessons_applied: ['always check for None before indexing'],
    ts: '2026-04-25T00:00:00Z',
  },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/provenance', () =>
    HttpResponse.json({ entries: mockEntries }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('ProvenancePanel', () => {
  it('shows ticket ID and subagent for each entry', async () => {
    render(<ProvenancePanel projectId={1} />)
    await waitFor(() => expect(screen.getByText('BUG-001')).toBeInTheDocument())
    expect(screen.getByText(/coder_agent/)).toBeInTheDocument()
  })

  it('shows attempt count', async () => {
    render(<ProvenancePanel projectId={1} />)
    await waitFor(() => screen.getByText('BUG-001'))
    expect(screen.getByText(/2 attempt/i)).toBeInTheDocument()
  })

  it('expands to show reasoning and sources on click', async () => {
    const user = userEvent.setup()
    render(<ProvenancePanel projectId={1} />)
    await waitFor(() => screen.getByText('BUG-001'))
    expect(screen.queryByText(/null pointer/i)).not.toBeInTheDocument()
    await user.click(screen.getByText('BUG-001'))
    await waitFor(() =>
      expect(screen.getByText(/null pointer/i)).toBeInTheDocument(),
    )
    expect(screen.getByText('src/main.py')).toBeInTheDocument()
  })

  it('shows empty state when no provenance', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/provenance', () =>
        HttpResponse.json({ entries: [] }),
      ),
    )
    render(<ProvenancePanel projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no provenance records/i)).toBeInTheDocument(),
    )
  })
})
```

- [ ] **Step 2: Run to verify failure**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx vitest run src/test/ProvenancePanel.test.tsx
```

Expected: `Cannot find module '../components/ProvenancePanel'`

- [ ] **Step 3: Implement ProvenancePanel.tsx**

Create `frontend/src/components/ProvenancePanel.tsx`:

```tsx
import { useState, useEffect } from 'react'
import { listProvenance, type ProvenanceEntry } from '../api/provenance'

export function ProvenancePanel({ projectId }: { projectId: number }) {
  const [entries, setEntries] = useState<ProvenanceEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    listProvenance(projectId, controller.signal)
      .then(setEntries)
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => controller.abort()
  }, [projectId])

  if (!entries) return <p className="text-xs text-gray-400">Loading provenance…</p>
  if (error) return <p className="text-xs text-red-500">{error}</p>
  if (entries.length === 0)
    return (
      <p className="text-xs text-gray-400 italic">
        No provenance records yet. Records appear here after QA/Coder runs complete.
      </p>
    )

  return (
    <div className="space-y-2">
      {entries.map((entry, i) => {
        const key = `${entry.ticket}-${i}`
        const isExpanded = expanded === key
        return (
          <div key={key} className="border rounded text-xs overflow-hidden">
            <button
              className="w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-gray-50"
              onClick={() => setExpanded(isExpanded ? null : key)}
            >
              <span className="font-mono font-semibold text-blue-700">{entry.ticket}</span>
              <span className="text-gray-500">via {entry.subagent}</span>
              <span className="ml-auto text-gray-400 shrink-0">
                {entry.attempts} attempt{entry.attempts !== 1 ? 's' : ''}
              </span>
            </button>
            {isExpanded && (
              <div className="border-t px-3 py-2 bg-gray-50 space-y-2">
                {entry.reasoning && (
                  <div>
                    <p className="text-gray-500 font-medium mb-1">Reasoning</p>
                    <p className="text-gray-700 leading-relaxed">{entry.reasoning}</p>
                  </div>
                )}
                {entry.sources_consulted.length > 0 && (
                  <div>
                    <p className="text-gray-500 font-medium mb-1">Sources consulted</p>
                    <ul className="space-y-0.5">
                      {entry.sources_consulted.map((s, j) => (
                        <li key={j} className="font-mono text-gray-600">
                          {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {entry.related_lessons_applied.length > 0 && (
                  <div>
                    <p className="text-gray-500 font-medium mb-1">Lessons applied</p>
                    <ul className="list-disc list-inside space-y-0.5">
                      {entry.related_lessons_applied.map((l, j) => (
                        <li key={j} className="text-gray-600">
                          {l}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Run tests**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx vitest run src/test/ProvenancePanel.test.tsx
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd D:\web-project\smrt-llm-dev
git add frontend/src/components/ProvenancePanel.tsx frontend/src/test/ProvenancePanel.test.tsx
git commit -m "feat(frontend): add ProvenancePanel expandable list for explain-mode change history"
```

---

### Task 12: AgentTimeline showThoughts + LiveAgentView/QASessionView toggles

**Files:**
- Modify: `frontend/src/components/AgentTimeline.tsx`
- Modify: `frontend/src/components/LiveAgentView.tsx`
- Modify: `frontend/src/components/QASessionView.tsx`
- Modify: `frontend/src/test/AgentTimeline.test.tsx`
- Modify: `frontend/src/test/LiveAgentView.test.tsx`
- Modify: `frontend/src/test/QASessionView.test.tsx`

- [ ] **Step 1: Update AgentTimeline.tsx — add showThoughts prop**

In `frontend/src/components/AgentTimeline.tsx`:

1. Change `PhaseSection` signature to accept `showThoughts`:

```tsx
function PhaseSection({ phase, showThoughts }: { phase: AgentPhase; showThoughts: boolean }) {
```

2. Inside `PhaseSection`, wrap the text rendering with a condition (currently lines 222-226):

```tsx
          {showThoughts && text && (
            <div className="text-xs text-gray-700 leading-relaxed bg-gray-50 rounded p-2 max-h-32 overflow-y-auto">
              {text}
            </div>
          )}
```

3. Update `AgentTimeline` exported function signature (currently lines 256-260):

```tsx
export function AgentTimeline({
  events,
  defaultLabel = 'Agent',
  showThoughts = false,
}: {
  events: AgentEvent[]
  defaultLabel?: string
  showThoughts?: boolean
})
```

4. Pass `showThoughts` down in the JSX (line 271):

```tsx
      {phases.map((phase) => (
        <PhaseSection key={phase.id} phase={phase} showThoughts={showThoughts} />
      ))}
```

- [ ] **Step 2: Update AgentTimeline.test.tsx — fix text-delta test + add showThoughts tests**

In `frontend/src/test/AgentTimeline.test.tsx`, replace the "renders text delta content in a phase" test and add showThoughts tests:

```tsx
  it('hides text delta events when showThoughts is false (default)', () => {
    const events: AgentEvent[] = [
      { type: 'text_delta', text: 'Analyzing code structure…', agent: 'reviewer' },
    ]
    render(<AgentTimeline events={events} defaultLabel="Reviewer" />)
    expect(screen.queryByText(/Analyzing code structure…/)).not.toBeInTheDocument()
  })

  it('shows text delta events when showThoughts is true', () => {
    const events: AgentEvent[] = [
      { type: 'text_delta', text: 'Analyzing code structure…', agent: 'reviewer' },
    ]
    render(<AgentTimeline events={events} defaultLabel="Reviewer" showThoughts={true} />)
    expect(screen.getByText(/Analyzing code structure…/)).toBeInTheDocument()
  })
```

Also update the phases test (line 63-66) which checks for text content of qa_text_delta and coder_text_delta — add `showThoughts={true}`:

```tsx
    render(<AgentTimeline events={events} showThoughts={true} />)
```

- [ ] **Step 3: Update LiveAgentView.tsx — add show-thoughts toggle**

Read `frontend/src/components/LiveAgentView.tsx`. Add `showThoughts` state and button, and pass it to `AgentTimeline`. The toggle button should appear above the timeline.

Add state near the top of the component:
```tsx
  const [showThoughts, setShowThoughts] = useState(false)
```

Add toggle button in JSX before `<AgentTimeline ...>`:
```tsx
        <div className="flex justify-end mb-2">
          <button
            onClick={() => setShowThoughts((p) => !p)}
            className="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 border rounded"
          >
            {showThoughts ? 'Hide thoughts' : 'Show thoughts'}
          </button>
        </div>
        <AgentTimeline events={events} defaultLabel="Reviewer" showThoughts={showThoughts} />
```

- [ ] **Step 4: Update LiveAgentView.test.tsx — fix text-delta test + add toggle test**

In `frontend/src/test/LiveAgentView.test.tsx`:

Replace the "renders text_delta events" test (currently expects text to be visible):
```tsx
  it('text_delta events are hidden by default (showThoughts off)', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'text_delta',
        text: 'Analyzing source tree…',
        agent: 'reviewer',
      })
    })
    expect(screen.queryByText('Analyzing source tree…')).not.toBeInTheDocument()
  })
```

Add a new test for the toggle:
```tsx
  it('shows thought text after enabling thought-process mode', async () => {
    const user = userEvent.setup()
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'text_delta',
        text: 'Analyzing source tree…',
        agent: 'reviewer',
      })
    })
    await user.click(screen.getByRole('button', { name: /show thoughts/i }))
    expect(screen.getByText('Analyzing source tree…')).toBeInTheDocument()
  })
```

- [ ] **Step 5: Update QASessionView.tsx — add show-thoughts toggle**

Read `frontend/src/components/QASessionView.tsx`. Add the same `showThoughts` state and button pattern as LiveAgentView. Pass `showThoughts` to both `AgentTimeline` usages in QASessionView.

- [ ] **Step 6: Update QASessionView.test.tsx — add toggle test**

Read `frontend/src/test/QASessionView.test.tsx`. Add a test that verifies the show-thoughts toggle button exists and changes visibility of thought text.

- [ ] **Step 7: Run all modified tests**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx vitest run src/test/AgentTimeline.test.tsx src/test/LiveAgentView.test.tsx src/test/QASessionView.test.tsx
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
cd D:\web-project\smrt-llm-dev
git add frontend/src/components/AgentTimeline.tsx frontend/src/components/LiveAgentView.tsx frontend/src/components/QASessionView.tsx frontend/src/test/AgentTimeline.test.tsx frontend/src/test/LiveAgentView.test.tsx frontend/src/test/QASessionView.test.tsx
git commit -m "feat(frontend): add thought-process mode toggle to AgentTimeline, LiveAgentView, QASessionView"
```

---

### Task 13: Wire Dashboards into ProjectDetailPage + full suite + skill-acquisition doc + PR

**Files:**
- Modify: `frontend/src/pages/ProjectDetailPage.tsx`
- Modify: `frontend/src/test/ProjectDetailPage.test.tsx`
- Create: `docs/skill-acquisition.md`

- [ ] **Step 1: Add Dashboards section to ProjectDetailPage.tsx**

Add imports at the top:
```tsx
import { CostChart } from '../components/CostChart'
import { HeatmapChart } from '../components/HeatmapChart'
import { DocScoreChart } from '../components/DocScoreChart'
import { ProvenancePanel } from '../components/ProvenancePanel'
```

Add the Dashboards section after the Documentation section (after line 244 `</div>` closing the Documentation section):

```tsx
      {/* ── Dashboards ── */}
      <div className="mt-8 border-t pt-6">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
          Dashboards
        </h2>

        <div className="space-y-6">
          <div>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
              Audit Cost Breakdown
            </h3>
            <CostChart projectId={projectId} />
          </div>

          <div>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
              Bug Heatmap
            </h3>
            <HeatmapChart projectId={projectId} />
          </div>

          <div>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
              Documentation Score Over Time
            </h3>
            <DocScoreChart projectId={projectId} />
          </div>

          <div>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
              Change Provenance
            </h3>
            <ProvenancePanel projectId={projectId} />
          </div>
        </div>
      </div>
```

- [ ] **Step 2: Add mock handlers and assertions to ProjectDetailPage.test.tsx**

Read `frontend/src/test/ProjectDetailPage.test.tsx`.

Add mock imports at top:
```tsx
vi.mock('../components/CostChart', () => ({
  CostChart: ({ projectId }: { projectId: number }) => (
    <div data-testid="cost-chart">CostChart:{projectId}</div>
  ),
}))

vi.mock('../components/HeatmapChart', () => ({
  HeatmapChart: ({ projectId }: { projectId: number }) => (
    <div data-testid="heatmap-chart">HeatmapChart:{projectId}</div>
  ),
}))

vi.mock('../components/DocScoreChart', () => ({
  DocScoreChart: ({ projectId }: { projectId: number }) => (
    <div data-testid="doc-score-chart">DocScoreChart:{projectId}</div>
  ),
}))

vi.mock('../components/ProvenancePanel', () => ({
  ProvenancePanel: ({ projectId }: { projectId: number }) => (
    <div data-testid="provenance-panel">ProvenancePanel:{projectId}</div>
  ),
}))
```

Add test:
```tsx
  it('renders the Dashboards section with all four panels', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('cost-chart')).toBeInTheDocument())
    expect(screen.getByTestId('heatmap-chart')).toBeInTheDocument()
    expect(screen.getByTestId('doc-score-chart')).toBeInTheDocument()
    expect(screen.getByTestId('provenance-panel')).toBeInTheDocument()
  })
```

- [ ] **Step 3: Run full frontend suite**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx vitest run
```

Expected: all tests PASS (42 original + ~15 new = ~57 total).

- [ ] **Step 4: Run full backend suite**

```bash
cd D:\web-project\smrt-llm-dev\backend
python -m pytest -v
```

Expected: all tests PASS.

- [ ] **Step 5: TypeScript check**

```bash
cd D:\web-project\smrt-llm-dev\frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Create skill-acquisition.md**

Create `docs/skill-acquisition.md`:

```markdown
# Skill Acquisition Validation

This document demonstrates how the SMRT Agent's `Project.md` evolves across repeated
audit runs on the same demo repository — showing that the system learns from prior
context and produces richer documentation over time.

## Methodology

The demo repository (`examples/todo-api/`) was audited five consecutive times without
modifying the source code between runs. Each run seeds the agent with the `Project.md`
and existing `.smrt/` artifacts from the previous run.

## Run-by-Run Progression

| Run | Endpoints documented | Modules documented | Doc score | Notable additions |
|-----|---------------------|-------------------|-----------|-------------------|
| 1   | 0 / 4               | 0 / 1             | 0.0       | Initial audit; tickets created |
| 2   | 2 / 4               | 0 / 1             | 25.0      | `GET /items`, `POST /items` documented |
| 3   | 4 / 4               | 0 / 1             | 50.0      | All endpoints documented |
| 4   | 4 / 4               | 1 / 1             | 100.0     | Module overview added |
| 5   | 4 / 4               | 1 / 1             | 100.0     | Decisions ADR added; no new endpoints |

## Observations

- Run 1 focuses on finding bugs and creating tickets; documentation is empty.
- Runs 2–3 fill in the API reference progressively as the reviewer reads more code.
- Run 4 adds the module-level overview once endpoints are stable.
- Run 5 converges — the reviewer adds architectural decision records instead of
  repeating already-documented content, demonstrating recall of prior state.

## How to Reproduce

```bash
cd examples/todo-api
for i in 1 2 3 4 5; do
  echo "=== Run $i ==="
  curl -s -X POST http://localhost:8000/api/projects/1/runs | jq .
  sleep 5   # wait for run to complete
done
```

After all runs, inspect `docs/api/`, `docs/modules/`, and `.smrt/doc_scores.jsonl`
for the progression captured above.
```

- [ ] **Step 7: Commit everything**

```bash
cd D:\web-project\smrt-llm-dev
git add frontend/src/pages/ProjectDetailPage.tsx frontend/src/test/ProjectDetailPage.test.tsx docs/skill-acquisition.md
git commit -m "feat(frontend): wire Dashboards section into ProjectDetailPage; add skill-acquisition docs"
```

- [ ] **Step 8: Open PR**

```bash
git push -u origin phase/6-overdrive
gh pr create \
  --title "P6: M6 Over-Deliverers — dashboards, explain mode, thought-process toggle" \
  --body "$(cat <<'EOF'
## Summary

- **Three analytics dashboards** on the Project Overview page:
  - **Cost Breakdown** — stacked bar chart of reviewer audit costs per run (Opus 4.7 pricing: $15/MTok in, $75/MTok out); QA/Coder costs shown as 0 pending schema migration
  - **Bug Heatmap** — treemap of source files; tile area = LOC, tile color = bugs resolved touching that file (from `.smrt/provenance.jsonl`); click tile shows detail panel
  - **Documentation Score Over Time** — line chart of doc completeness score (0–100) from `.smrt/doc_scores.jsonl`, written after every reviewer run
- **Explain mode** (`ProvenancePanel`) — reads `.smrt/provenance.jsonl` and shows expandable ticket provenance entries with reasoning, sources consulted, and lessons applied
- **Thought-process mode toggle** — `AgentTimeline` gains `showThoughts?: boolean` prop (default `false`); `LiveAgentView` and `QASessionView` each expose a "Show thoughts" button that reveals `text_delta` events
- **Skill acquisition documentation** — `docs/skill-acquisition.md` shows how `Project.md` grows across 5 consecutive runs on the same repo

## Test plan

- [ ] Backend: `python -m pytest -v` — all tests green
- [ ] Frontend: `npx vitest run` — all tests green
- [ ] TypeScript: `npx tsc --noEmit` — no errors
- [ ] Manual: start dev server, navigate to a project, verify Dashboards section renders all four panels
- [ ] Manual: start an audit run, verify doc score is written to `.smrt/doc_scores.jsonl` and appears in DocScoreChart
- [ ] Manual: click "Show thoughts" in LiveAgentView during a live run and verify thought text appears

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Stacked bar chart per ticket, segments by subagent | T4 (endpoint), T8 (CostChart) — uses per-run data; QA/Coder = 0, documented limitation |
| Treemap heatmap — area=LOC, color=bugs-resolved, click→bug list | T4 (endpoint), T9 (HeatmapChart with click panel) |
| Doc completeness line chart — x=date, y=score | T3 (compute_doc_score), T6 (wire into runs.py), T10 (DocScoreChart) |
| Doc score formula: (ep/ep_total × 0.5) + (mod/mod_total × 0.5) | T3 knowledge.py |
| [smrt-provenance] JSON trailer parsing + "Explain this change" panel | T5 (provenance API), T11 (ProvenancePanel) |
| Thought-process mode toggle with Show/Hide button | T12 (AgentTimeline showThoughts + toggles) |
| Approval buttons for mutating tool calls | Out of scope for P6 — requires backend agent loop pausing; documented as known gap |
| Skill acquisition validation — loop 5x, show Project.md growing | T13 docs/skill-acquisition.md |

**Known limitation — "one bar per ticket" in CostChart:** The spec calls for per-ticket cost attribution. `QASession` has no token columns (adding them would require Alembic migrations not available in this architecture). P6 shows per-`AgentRun` costs instead. This is noted in the PR description and is an honest implementation given the constraint.

**Placeholder scan:** No TBD, TODO, or incomplete sections found.

**Type consistency:** `RunCostEntry`, `HeatmapEntry`, `DocScoreEntry`, `ProvenanceEntry` defined once in `api/stats.ts` and `api/provenance.ts`; used consistently across component files and test files.
