# Architecture

SMRT Agent is a Dockerized multi-agent system that connects to a local Python FastAPI
codebase, runs autonomous quality checks (documentation, test generation, bug squashing),
and surfaces all activity in a React web UI. The backend embeds three Anthropic-powered
agents, a scheduler, and a file watcher; the frontend consumes a streaming FastAPI API
and renders live agent activity, bug tickets, and three analytics dashboards.

## System Diagram

```
Browser
  │
  └─► Vite / React 18 (127.0.0.1:5173)   frontend/src/
        │  SSE streams + REST calls
        ▼
      FastAPI backend (127.0.0.1:8000)    backend/src/smrt_agent/
        │
        ├─► Reviewer agent (claude-opus-4-7)
        │     tools: list_files, read_file, fetch_url, write_file
        │     writes: .smrt/Project.md, docs/, wiki/
        │
        ├─► QA agent (claude-sonnet-4-6)
        │     tools: list_files, read_file, write_test_file, run_pytest,
        │            write_bug_ticket, write_test_status, append_bugs_resolved
        │     writes: .smrt/tests/, .smrt/tickets/, .smrt/test-status.md
        │
        ├─► Coder agent (claude-sonnet-4-6)
        │     tools: list_files, read_source_file, write_source_file
        │     writes: src/** only
        │
        ├─► APScheduler  (scheduler.py)  — nightly 03:00 QA runs
        ├─► File watcher (watchers.py)   — watchfiles, src/**/*.py
        ├─► SQLite       (state.db)      — projects, runs, qa_sessions
        └─► DocBackend   (docs/)         — GitHub + Obsidian writers

        target repo mounted at /workspace (read-write)
        Docker socket mounted for ephemeral sandbox containers
```

## Component Breakdown

### Backend — `backend/src/smrt_agent/`

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI app factory; registers all routers |
| `api/projects.py` | Project CRUD, registration, path validation |
| `api/runs.py` | Reviewer runs — POST to start, SSE stream, event log |
| `api/qa_sessions.py` | QA/Coder sessions — HITL approve/skip endpoints |
| `api/tickets.py` | Bug ticket listing per project |
| `api/stats.py` | `/stats/cost`, `/stats/heatmap`, `/stats/doc-completeness` |
| `api/provenance.py` | `[smrt-provenance]` entry listing |
| `api/docs.py` | Documentation preview endpoint |
| `agents/reviewer/` | Anthropic SDK loop, tools, budget for Reviewer |
| `agents/qa/` | Anthropic SDK loop, tools, budget for QA |
| `agents/coder/` | Anthropic SDK loop, tools, budget for Coder |
| `agents/orchestrator.py` | QA↔Coder coordination loop with HITL gate |
| `docs/backends.py` | `DocBackend` ABC; `GitHubBackend`, `ObsidianBackend` |
| `scheduler.py` | APScheduler — `CronTrigger(hour=3)` per project |
| `watchers.py` | watchfiles integration for commit/file-change triggers |
| `sandbox/` | Docker ephemeral-container lifecycle |
| `db/` | SQLAlchemy async models: `Project`, `AgentRun`, `QASession` |
| `settings.py` | Pydantic `Settings` — models, budgets, ports via env vars |
| `event_log.py` | `EventLogger` — wraps queue, writes `.smrt/runs/*.jsonl` |
| `knowledge.py` | `compute_doc_score`, `record_doc_score` helpers |

### Frontend — `frontend/src/`

| Component / Page | Responsibility |
|---|---|
| `pages/ProjectsPage.tsx` | Project list, Add Project form |
| `pages/ProjectDetailPage.tsx` | Tabbed detail: audit, QA session, tickets, dashboards, docs |
| `components/LiveAgentView.tsx` | SSE-driven live tool-call stream for Reviewer runs |
| `components/QASessionView.tsx` | SSE-driven view for QA↔Coder sessions; approve/skip buttons |
| `components/AgentTimeline.tsx` | Ordered event log for past runs |
| `components/TicketsPanel.tsx` | Bug ticket list from `.smrt/tickets/` |
| `components/CostChart.tsx` | Stacked bar chart — token cost per run by subagent |
| `components/HeatmapChart.tsx` | Treemap — file LOC vs bugs-resolved count |
| `components/DocScoreChart.tsx` | Line chart — documentation completeness over time |
| `components/ProvenancePanel.tsx` | `[smrt-provenance]` JSON trailer viewer |
| `components/DocPanel.tsx` | Preview of generated `docs/` and `wiki/` content |

## Data Flow

1. **Project registration** — user POSTs a local path; backend validates it is a git repo with Python files; project row written to SQLite.
2. **Init audit** — `POST /projects/{id}/runs` starts a Reviewer agent task; agent calls `list_files`, `read_file`, `fetch_url` (OpenAPI), then `write_file` to produce `.smrt/Project.md` and seeds `docs/` + `wiki/` via `DocBackend`.
3. **Periodic checkup** — APScheduler fires `POST /projects/{id}/qa-sessions` at 03:00 daily; same path as a manual QA session trigger.
4. **QA↔Coder loop** — `orchestrator.py` drives: QA runs pytest, writes ticket if confidence ≥ 0.6, emits `hitl_request` event; frontend shows Approve/Skip; on approve, Coder receives ticket (test path redacted) and edits `src/**`; orchestrator re-runs pytest; repeats up to `max_fix_attempts`.
5. **PR surface** — on QA acceptance, Reviewer bundles a PR summary; the pending PR appears in the Tickets panel for human acceptance.
6. **Doc generation** — after every successful run, `docs/service.py` calls `GitHubBackend` and `ObsidianBackend` to upsert endpoint and module docs; `compute_doc_score` appends to `.smrt/doc_scores.jsonl`.

## Storage Layout

```
SQLite (SMRT_DB_PATH / state.db)
  tables: projects, agent_runs, qa_sessions

Target repo at /workspace (or local path)
  .smrt/
    Project.md          # Reviewer's living knowledge base
    tickets/            # YYYY-MM-DD-NNN.md per bug
    tests/              # QA-generated pytest files
    runs/               # <run-id>.jsonl event logs
    qa-sessions/        # <session-id>.jsonl event logs
    test-status.md      # test promotion/demotion state
    bugs-resolved.md    # append-only resolution log
    provenance.jsonl    # [smrt-provenance] entries
    doc_scores.jsonl    # doc completeness history
  docs/                 # GitHub-native Markdown (GitHubBackend)
    api/                # per-endpoint .md files + index.md
    modules/            # per-module .md files
    decisions/          # ADR files
  wiki/                 # Obsidian vault (ObsidianBackend)
    api/, modules/, decisions/  # mirroring docs/ with YAML frontmatter
```

## Docker Topology

```
docker-compose.yml
  smrt-backend   (uvicorn, port 8000, network: default + smrt-internal)
    volumes:
      ./backend/src → /app/src
      /var/run/docker.sock → sandbox orchestration
      . → /workspace  (target repo mount)
      smrt-db volume → /app/.smrt

  smrt-frontend  (vite dev, port 5173)
    volumes: ./frontend/src → /app/src

  smrt-internal network (no gateway — sandbox containers are isolated here)

Ephemeral sandbox containers  smrt-sandbox-<ticket-id>-<timestamp>
  built from Dockerfile.smrt in target repo
  CPU: 2 cores, memory: 2 GB, no internet access
  mounts: src/ (read-only), .smrt/tests/ (read-write for QA)
```
