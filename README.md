# SMRT Agent

A semi-autonomous multi-agent system that **discovers logical bugs in Python FastAPI codebases**, **fixes them through a blackbox QA↔Coder loop**, and **maintains Obsidian-friendly documentation** — all behind a React kanban UI with two human-in-the-loop gates.

> **Status:** v1 — local-only, single-user, two bundled eval fixtures. See `PRODUCTION.md` for the build spec and `NEXT_ITERATION.md` for the v2 roadmap.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Quickstart — under 3 minutes](#quickstart--under-3-minutes)
3. [Architecture](#architecture)
4. [Eval fixtures](#eval-fixtures)
5. [Testing scenarios](#testing-scenarios)
6. [Configuration](#configuration)
7. [Local LLM (LM Studio)](#local-llm-lm-studio)
8. [Project layout](#project-layout)
9. [Troubleshooting](#troubleshooting)
10. [License](#license)

---

## What it does

Three agents, each on a scoped tool allowlist, collaborate on a bounded set of repository-maintenance tasks:

| Agent          | Default model           | Role                                                                                              |
|----------------|-------------------------|---------------------------------------------------------------------------------------------------|
| **Reviewer**   | `claude-haiku-4-5`      | Reads source, writes `.smrt/Project.md`, optionally generates `README.md` + Obsidian-flavored docs in `docs/`. Also writes the **third-perspective Fix Summary** at the end of every QA-Coder loop and proposes documentation updates. |
| **QA**         | `claude-haiku-4-5`      | Writes pytest tests, runs them in a sandboxed Docker container, opens bug tickets with confidence. Also acts as a **per-attempt QA Advisor** that returns one of three verdicts: *satisfied*, *needs more attempts*, or *test_faulty*. |
| **Coder**      | `claude-sonnet-4-6`     | Implements fixes proposed by QA — never sees the tests (blackbox loop). Aware of attempt count and prior-attempt feedback so it doesn't repeat failed approaches. |

The **QA↔Coder loop** repeats up to `SMRT_MAX_FIX_ATTEMPTS` times (default `3`). On each failed attempt, the QA Advisor weighs in with one of three structured verdicts:

- **CASE A — fix is correct** (failing tests are unrelated): mark the ticket ready for review.
- **CASE B — fix is wrong**: actionable feedback that the Coder uses on the next attempt.
- **CASE C — the *test* is faulty**: halt the loop and route the ticket to **Needs Review** with a test-update proposal.

If neither A nor C fires within `SMRT_MAX_FIX_ATTEMPTS`, the ticket is escalated to **Needs Review** with a heuristic failure report (`needs_more_attempts` / `possibly_not_a_bug`).

After the loop, the **Reviewer agent** writes the **compiled Fix Summary** (a third perspective beyond Coder and QA), reads the existing project docs, and queues any documentation updates the fix necessitates. These are stored in `.smrt/fix-summaries/<session-id>.json` and survive across sessions.

**Two human gates** anchor the loop:

1. **Bug confirmation** — drag a ticket from *Pending Confirmation* → *In Progress* to launch the Coder.
2. **PR acceptance** — when QA certifies a fix, drag the ticket from *Needs Review* → *Closed* to merge. **Accepting also applies the Reviewer's queued documentation updates.** Drag back to *In Progress* to retry.

A third gate fires **interactively** when an agent hits its budget ceiling: a *budget_pause* SSE event surfaces a "Continue (+20% grace) / Terminate" dialog in the UI. Default timeout: 120 s → terminate.

---

## Quickstart — under 3 minutes

> Uses the bundled `eval-fixtures/todo-api` (5 intentional bugs). No external repo needed.

### 1. Clone and configure

```bash
git clone https://github.com/chlgustjr41/smrt-llm-dev
cd smrt-llm-dev

# macOS / Linux
cp .env.example .env

# Windows (PowerShell or cmd)
copy .env.example .env
```

Open `.env` and replace `sk-ant-api03-REPLACE_ME` with your real Anthropic API key.
*(Or set `USE_LOCAL_LLM=true` and run LM Studio — see [Local LLM](#local-llm-lm-studio).)*

### 2. Start the stack

```bash
docker network create smrt-internal       # one-time, isolated sandbox network
docker compose up
```

Wait for both services to report ready (~20–30 s on first run).

### 3. Register the demo project

Open **http://127.0.0.1:5173** in your browser.

- Click **Register Project**
- Use the **file browser** to pick `eval-fixtures/todo-api` (the backend already has `/workspace` mounted, so the canonical path becomes `/workspace/eval-fixtures/todo-api`)
- Give it any name (e.g. `todo-api`) and click **Save**

### 4. Run the agents

| UI action                                           | What happens                                                                                              |
|-----------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| **Run Init Audit** (Overview tab) — with **📝 Generate docs** checked | Reviewer reads the codebase, writes `.smrt/Project.md`, **also writes `README.md` (when missing/sparse) and `docs/architecture.md` + `docs/modules/*.md`** if the toggle is on. Uncheck the toggle for an inspection-only audit that touches only `.smrt/`. |
| **Find Bugs** (Overview tab)                        | QA writes pytests, runs them in the Docker sandbox, files tickets in **Pending Confirmation**             |
| **Drag ticket → In Progress**                       | Spawns a per-ticket QA↔Coder session. AgentTimeline streams thoughts via SSE. After the loop ends, the **Reviewer Final Summary** phase writes the compiled Fix Summary and proposes any doc updates. |
| **Drag ticket → Needs Review** *(automatic on fix)* | QA has accepted the patch; the diff is now ready for human review. The Reviewer's compiled Fix Summary appears as the headline of the **Fix Summary** tab; any proposed doc updates are listed below. |
| **Drag ticket → Closed**                            | PR is accepted: the agent commits the fix, emits a `[smrt-provenance]` JSON trailer, **and applies any proposed documentation updates** (README.md / docs/*.md / .smrt/Project.md) the Reviewer queued. |
| **Drag ticket back → In Progress**                  | PR rejected; loop restarts (within `SMRT_MAX_FIX_ATTEMPTS`)                                               |

Toggle **Show reasoning** in the AgentTimeline to expose each agent's intermediate thoughts. Use **Collapse all / Expand all** at the top of any timeline to manage long agent logs. The Fix Summary tab updates live — leave it open through the loop and it'll refresh as soon as the Reviewer's narrative is ready.

### 5. Inspect results

- **Cost dashboard** (Overview) — token and USD breakdown per agent, per run, per ticket
- **Doc completeness** (Docs tab) — per-module coverage score
- **Tests tab** — pytest history, per-file code coverage, hover any source file to see which test files cover it
- **Tickets tab** — kanban with full per-ticket history; click any card to open the dialog with **History / Events / Diff** tabs
- Each merged commit carries a `[smrt-provenance]` JSON trailer so you can audit *why* the patch was applied

Expected findings in `todo-api`: password hash leaked in API response, missing `await` on async DB call, authorization checked after deletion, `due_at` accepted in the past, and a race condition in the completion toggle. (Full answer key: `eval-fixtures/todo-api/BUGS.md` — protected from agents by `.agentignore`.)

---

## Architecture

```
                    Browser (React + Vite :5173)
                              │  REST + Server-Sent Events
                              ▼
                    Backend (FastAPI :8000)
                              │
   ┌──────────────────────────┼──────────────────────────────────┐
   │                          │                                  │
   ▼                          ▼                                  ▼
Reviewer agent          QA agent (per-ticket)              Coder agent
reads /workspace        ↑   ↓ blackbox loop                  patches src/**
writes Project.md       ↑   ↓ feedback                       opens PR branch
writes docs/            ↑   ↓ (≤ MAX_FIX_ATTEMPTS)           commit on accept
                        │
                        ▼
              Docker sandbox network (smrt-internal)
              ephemeral container per test batch
              CPU 2c, RAM 2 GB, no internet
```

### Request lifecycle (per ticket)

```
human drag → POST /tickets/{id}/approve
                ↓
backend launches asyncio task
                ↓
budget_gateway.handle_budget_pause() arms ──► budget_pause SSE event
                ↓                              ↑
QA loop: write test → run in sandbox          │ POST /tickets/{id}/budget-decision
                ↓                              │   "continue" → +20% grace
QA result: accept | reject + feedback         │   "terminate" → end loop
                ↓                              │
Coder loop: read src/** + ticket → patch ─────┘
                ↓
QA re-runs hidden test on Coder's branch
                ↓ (loop until accept or cap)
emit ticket_complete | failure_report SSE
```

All agents call the configured LLM provider (Anthropic by default; OpenAI-compatible endpoint when `USE_LOCAL_LLM=true`). Budget guardrails (`SMRT_BUDGET_PER_RUN_USD`, `SMRT_BUDGET_PER_TICKET_USD`, `SMRT_BUDGET_PER_DAY_USD`) hard-halt any run that exceeds its limit unless a human grants a 20% grace extension.

---

## Eval fixtures

Two ready-to-run FastAPI fixtures live under `eval-fixtures/`. Each ships with planted bugs and a `BUGS.md` answer key gated by `.agentignore`.

### `eval-fixtures/todo-api/` — single-file FastAPI (~150 LOC)

Five planted bugs spanning the canonical defect taxonomy:

| #   | Category          | Endpoint(s)                       | Bug summary                                                            |
|-----|-------------------|-----------------------------------|------------------------------------------------------------------------|
| 1   | Silent-logical    | `POST /users`, `GET /users`       | `password_hash` leaks in response (no `response_model` filter)         |
| 2   | Async             | `POST /todos`                     | Missing `await` on `_save_todo(...)`; coroutine GC'd before write      |
| 3   | Auth-order        | `DELETE /todos/{id}`              | Ownership check runs **after** the `del` — 403 + already deleted       |
| 4   | Input validation  | `POST /todos`                     | `due_at` accepts past timestamps (no validator)                        |
| 5   | State mutation    | `PATCH /todos/{id}/complete`      | Read-yield-write race in `_completed_count` increment                  |

**Why this fixture is good for a first run:** every bug is local to a single function, so the agents converge fast and you get a clean end-to-end demo on a tight budget.

### `eval-fixtures/inventory-api/` — multi-router service (~250 LOC)

Five planted bugs that require **cross-file reasoning** (router → service → docstring contract). Recommended for the second run once you've seen the loop work.

| #   | Category           | File                              | Bug summary                                                            |
|-----|--------------------|-----------------------------------|------------------------------------------------------------------------|
| 1   | Variable swap      | `routers/stock.py`                | Stock transfer deducts from target and adds to source (swapped IDs)    |
| 2   | Unused variable    | `services/inventory.py`           | `available_stock` returns `physical` instead of `physical - reserved`  |
| 3   | Missing factor     | `routers/orders.py`               | Order total adds `unit_price` without multiplying by `quantity`        |
| 4   | Off-by-one         | `routers/reports.py`              | Low-stock alert uses strict `<` instead of inclusive `<=`              |
| 5   | Wrong predicate    | `routers/products.py`             | Soft-delete filter is `is not None` (always true) — deleted items leak |

The agent must read **two routers + a service module + a schema docstring** to spot bug #1 (the contract is in `schemas.py`; the swap is in `routers/stock.py`).

### `eval-fixtures/wild/` — bring your own

Empty in v1. Drop any FastAPI repo here, then register `/workspace/eval-fixtures/wild/<your-repo>` in the UI. Suggested public targets:

- [`tiangolo/full-stack-fastapi-template`](https://github.com/tiangolo/full-stack-fastapi-template) — point at the `backend/` subdir
- [`nsidnev/fastapi-realworld-example-app`](https://github.com/nsidnev/fastapi-realworld-example-app) — small, pure backend
- [`zhanymkanov/fastapi_best_practices`](https://github.com/zhanymkanov/fastapi_best_practices) — pedagogical repo

---

## Testing scenarios

Three end-to-end scenarios you can run after [§Quickstart step 2](#2-start-the-stack). Each one fits inside the default `$2/run` Anthropic budget when models are left at the haiku-default.

### Scenario A — "Cold start to first PR" *(todo-api, ~5 min, ~$0.30)*

**Goal:** see the full loop produce a merged commit on a freshly cloned repo.

```text
1. Register   /workspace/eval-fixtures/todo-api  (any name)
2. Click      Run Init Audit                      → Reviewer writes docs/
3. Click      Find Bugs                           → QA opens 3-5 tickets
4. Drag the "password_hash leaked" ticket → In Progress
5. Watch     AgentTimeline (Overview tab)         → Coder patches main.py
6. When      ticket lands in Needs Review         → click card → Diff tab
7. Drag      → Closed                             → commit lands on new branch
8. Run       cd eval-fixtures/todo-api && git log → see [smrt-provenance] trailer
```

**Expected outcomes:**
- `docs/modules/todo-api.md` and `docs/api/*.md` populated by Reviewer
- 3–5 tickets created (QA may merge bugs #4 and #5 into a single ticket)
- Coder produces a fix that adds a `UserOut` Pydantic model with only `id` and `email`
- Commit on a `smrt-fix-<id>` branch, NOT on `main`

### Scenario B — "Budget brake" *(todo-api, ~3 min, ~$0.05)*

**Goal:** verify the interactive budget-pause gate.

```text
1. Open    Config tab on a registered project
2. Set     Budget per ticket = 0.02   (intentionally too small)
3. Drag    any pending ticket → In Progress
4. Wait    ~10 s for the budget_pause SSE event
5. Dialog  "Budget exceeded — Continue with 20% grace, or Terminate?"
6. Click   Continue                                → loop runs ~20% longer
7. Click   Terminate (on the next pause)           → ticket → Needs Review with budget_exceeded
```

**What this exercises:** `agents/budget_gateway.py` — the asyncio future bridge between agent loop and frontend decision.

### Scenario C — "Cross-file reasoning" *(inventory-api, ~10 min, ~$0.80)*

**Goal:** stress-test the agents on a multi-router codebase.

```text
1. Register  /workspace/eval-fixtures/inventory-api
2. Run       Init Audit                            → docs/ should list 5 routers + 1 service
3. Run       Find Bugs                             → expect 4-5 tickets
4. Drag      "stock transfer swap" ticket → In Progress
5. Observe   Coder reads routers/stock.py, schemas.py, services/inventory.py
             before patching (visible in AgentTimeline → Show reasoning)
6. Drag      "soft-delete predicate" ticket → In Progress in parallel
             (the orchestrator queues it after the first ticket)
7. Verify    git log --oneline shows two distinct fix commits with provenance trailers
```

**What to look for:** the QA agent's failure-report dialog if either ticket exhausts attempts. The report should name the file paths it suspects, not the test code (blackbox contract preserved).

> **Tip — programmatic verification.** After Scenario A or C, `cd eval-fixtures/<fixture> && git diff main..smrt-fix-* -- main.py` and compare against the matching entry in `BUGS.md`. The patch should fix exactly the bug and nothing else.

---

## Configuration

Configuration lives in two layered files plus the per-project UI **Config** tab:

1. **`.env`** (repo root, gitignored) — secrets and runtime/server settings: `ANTHROPIC_API_KEY`, `USE_LOCAL_LLM`, ports, budgets, log level. Copy `.env.example` to start.
2. **`backend/.config`** (gitignored) — agent defaults the team commits as `backend/.config.example`: model choices, loop caps, UI toggles. These are the *initial* values for any newly-registered project.
3. **`<project>/.smrt/config.json`** — per-project overrides set via the UI's Config tab. Created on first save.

**Loading order** (later wins): `backend/.config` → `.env` → process environment → per-project `config.json`. So per-project tweaks always take precedence; `.env` is the per-developer override layer; `backend/.config` is the team baseline.

### Required

| Variable             | Description                                         |
|----------------------|-----------------------------------------------------|
| `ANTHROPIC_API_KEY`  | Required when `USE_LOCAL_LLM=false`                 |

### Budget guardrails

| Variable                   | Default | Description                                    |
|----------------------------|---------|------------------------------------------------|
| `SMRT_BUDGET_PER_RUN_USD`  | `2.00`  | Hard cap per Init Audit or QA discovery run    |
| `SMRT_BUDGET_PER_TICKET_USD` | `2.00` | Hard cap per QA-Coder ticket fix loop          |
| `SMRT_BUDGET_PER_DAY_USD`  | `40.00` | Hard daily total per project                   |

### Models (overridable per-project)

| Variable                | Default                  |
|-------------------------|--------------------------|
| `SMRT_MODEL_REVIEWER`   | `claude-haiku-4-5-20251001` |
| `SMRT_MODEL_QA`         | `claude-haiku-4-5-20251001` |
| `SMRT_MODEL_CODER`      | `claude-sonnet-4-6`         |

### Loop caps

| Variable                            | Default | Description                                       |
|-------------------------------------|---------|---------------------------------------------------|
| `SMRT_MAX_FIX_ATTEMPTS`             | `3`     | QA↔Coder loop attempts before escalation          |
| `SMRT_MAX_QUESTIONS_PER_ATTEMPT`    | `1`     | Coder's allowed clarifying questions to QA per attempt |

### UI defaults

| Variable                       | Default | Description                                       |
|--------------------------------|---------|---------------------------------------------------|
| `SMRT_THOUGHT_PROCESS_MODE`    | `false` | Show agent reasoning stream by default            |

### Bind / network

| Variable             | Default       | Description                                     |
|----------------------|---------------|-------------------------------------------------|
| `SMRT_BIND_HOST`     | `127.0.0.1`   | Localhost-only by default (no auth in v1)       |
| `SMRT_BACKEND_PORT`  | `8000`        |                                                 |
| `SMRT_FRONTEND_PORT` | `5173`        |                                                 |

### Per-project config persistence

Per-project overrides are written to `<project-path>/.smrt/config.json` *and* mirrored into the SQLite state DB. The filesystem version takes precedence on read, so the config travels with the repo.

---

## Local LLM (LM Studio)

To run fully offline against an OpenAI-compatible local server:

```bash
# 1. Install LM Studio, download a model (e.g. Qwen2.5-Coder-32B-Instruct GGUF)
# 2. Start the LM Studio "Local Server" → http://localhost:1234

# 3. In .env:
USE_LOCAL_LLM=true
LOCAL_LLM_BASE_URL=http://host.docker.internal:1234/v1   # for Docker Desktop
LOCAL_LLM_MODEL=local-model                              # whatever LM Studio reports
```

`host.docker.internal` is required so the backend container can reach LM Studio on your host. On Linux Docker, replace with the gateway IP (`docker network inspect bridge | grep Gateway`) or run with `--network=host`.

The Reviewer/QA/Coder model overrides are ignored when `USE_LOCAL_LLM=true` — every agent uses `LOCAL_LLM_MODEL`.

---

## Project layout

```
smrt-llm-dev/
├── README.md                  # this file
├── PRODUCTION.md              # the v1 build spec (source of truth for behavior)
├── NEXT_ITERATION.md          # deferred scope and v2 roadmap
├── docker-compose.yml         # backend + frontend services
├── .env.example               # copy → .env, edit, never commit secrets
│
├── backend/                   # FastAPI service
│   ├── Dockerfile.dev
│   ├── pyproject.toml
│   ├── .config.example        # team-shared agent defaults (copy to .config)
│   └── src/smrt_agent/
│       ├── main.py            # app factory, router registration
│       ├── settings.py        # pydantic-settings; .env + backend/.config discovery
│       ├── llm.py             # provider routing (Anthropic | local OpenAI-compatible)
│       ├── agents/            # orchestrator, budget_gateway, coder/, qa/, reviewer/
│       │   └── orchestrator.py # QA↔Coder loop + Reviewer Final Summary pass
│       ├── api/               # REST + SSE routers (one file per resource)
│       ├── docs/              # backends.py (Obsidian writer), parser.py, service.py
│       ├── fix_summary.py     # persistent Fix Summary builder + index
│       ├── sandbox/           # docker SDK wrapper, smrt-exec.py CPU/RAM caps
│       ├── db/                # SQLAlchemy async, schema migrations
│       ├── hooks/             # secret_guard_hook, .agentignore enforcement
│       ├── prompts/           # per-agent system prompts
│       ├── event_log.py       # JSONL append + SSE replay
│       └── scheduler.py       # periodic checkup APScheduler job
│
├── frontend/                  # React 19 + Vite + Tailwind
│   ├── Dockerfile.dev
│   └── src/
│       ├── pages/             # ProjectsPage, ProjectDetailPage (tabs)
│       ├── components/        # TicketsPanel (kanban), AgentTimeline (SSE),
│       │                      # DocPanel, FileBrowser, LiveAgentView,
│       │                      # QASessionView, CostChart, GfmMarkdown
│       └── api/               # typed fetch wrappers per backend resource
│
├── eval-fixtures/             # ⬅ sample test projects (see §Eval fixtures)
│   ├── README.md
│   ├── todo-api/              # single-file fixture, 5 bugs
│   ├── inventory-api/         # multi-router fixture, 5 bugs
│   └── wild/                  # bring-your-own real-world repos
│
├── docs/                      # docs about the meta-repo itself (CHANGELOG, etc.)
├── bin/                       # smrt-exec.py (sandbox runner)
└── .smrt/                     # auto-generated per project (gitignored)
    ├── Project.md             # Reviewer-maintained living spec
    ├── config.json            # per-project UI overrides
    ├── qa-sessions/           # JSONL event logs per session
    ├── tickets/               # bug ticket markdown files
    ├── pending-prs.jsonl      # tickets that passed QA, awaiting Accept
    ├── failed-fixes.jsonl     # loop-exhausted tickets in Needs Review
    ├── fix-summaries/         # Reviewer-written Fix Summaries — durable
    │   ├── index.json         #   ticket_id → latest_session_id
    │   └── <session_id>.json  #   one per session, with proposed_doc_updates
    └── knowledge/             # bugs-resolved.jsonl, test-status.yaml
```

---

## Troubleshooting

**`docker compose up` exits with port conflict**
Another process is using `:8000` or `:5173`. Change `SMRT_BACKEND_PORT` and `SMRT_FRONTEND_PORT` in `.env`, then re-run.

**`network smrt-internal not found`**
Run `docker network create smrt-internal` once. The sandbox containers attach to this isolated, gateway-less network.

**Init Audit finishes but no docs appear**
The project path must resolve **inside the backend container**. The repo is mounted at `/workspace`, so the canonical path for `eval-fixtures/todo-api` is `/workspace/eval-fixtures/todo-api`. Use the file browser (it does this for you) instead of typing host paths.

**`Anthropic API error 401`**
`ANTHROPIC_API_KEY` is missing or still set to the placeholder. Replace it with a real key and `docker compose restart backend`.

**Agent reads `BUGS.md` even though it's "the answer"**
Confirm `eval-fixtures/<fixture>/.agentignore` exists and contains `BUGS.md`. The `secret_guard_hook` walks `.agentignore` files and refuses Read/Glob/Grep on listed paths.

**LM Studio replies but agent loops error out**
Some local models reject Anthropic-flavored tool-use schemas. Try a model with strong tool-use support (Qwen2.5-Coder-Instruct, DeepSeek-Coder-V2, Llama-3.3-70B-Instruct) and check LM Studio's "Tool use" toggle.

**Pre-existing tests already failed before the agent ran**
QA tracks baseline pytest results; only *new* regressions become tickets. If your real repo's `pytest` is red on `main`, fix that first or run `Find Bugs` on a clean branch.

---

## License

[MIT](./LICENSE)
