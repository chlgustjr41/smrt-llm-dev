# SMRT Agent

A semi-autonomous multi-agent system that discovers logical bugs in Python FastAPI codebases, fixes them through a blackbox QA↔Coder loop, and maintains documentation in GitHub Markdown and Obsidian vault format.

---

## Demo — under 3 minutes

> Uses the bundled `eval-fixtures/todo-api` (5 intentional bugs). No external repo needed.

### 1. Clone and configure

```bash
git clone https://github.com/chlgustjr41/smrt-llm-dev
cd smrt-llm-dev

# macOS / Linux
cp .env.example .env

# Windows
copy .env.example .env
```

Open `.env` and replace `sk-ant-api03-REPLACE_ME` with your real Anthropic API key.

### 2. Start the stack

```bash
docker compose up
```

Wait for both services to report ready (roughly 20–30 seconds on first run).

### 3. Register the demo project

Open **http://127.0.0.1:5173** in your browser.

- Click **Register Project**
- Set the project path to `/workspace/eval-fixtures/todo-api`
- Give it any name (e.g. `todo-api`) and click **Save**

> The backend container mounts the repo root at `/workspace`, so this path resolves to `eval-fixtures/todo-api` inside the repo.

### 4. Run the agents

- Click **Init Audit** — the Reviewer agent reads the codebase, writes `Project.md`, and generates `docs/` and `wiki/` documentation
- Click **Find Bugs** — the QA agent writes pytest tests, runs them in an isolated Docker sandbox, and creates bug tickets
- **Confirm** the tickets that appear in the UI (human-in-the-loop gate)
- Watch the **Coder** agent fix each bug; approve the resulting PRs one at a time

The **AgentTimeline** panel streams live thoughts for each agent. Toggle **Show reasoning** to see intermediate steps.

### 5. Inspect results

- **Cost dashboard** — token and USD breakdown per agent and per run
- **Bug heatmap** — files ranked by defect density
- **Doc completeness** — coverage score across the generated docs
- Each PR commit carries a `[smrt-provenance]` JSON trailer explaining why the fix was applied

Expected findings in `todo-api`: password hash returned in API response, missing `await` on async DB call, authorization checked after the resource is deleted, `due_at` accepted as a past timestamp, and a race condition in the completion toggle.

---

## What it does

| Agent | Role |
|-------|------|
| **Reviewer** | Reads source, writes `Project.md`, generates API docs and Obsidian wiki |
| **QA** | Writes and runs pytest tests in a sandboxed container; opens bug tickets |
| **Coder** | Implements fixes proposed by QA; never sees the tests (blackbox loop) |

The QA↔Coder loop repeats up to `SMRT_MAX_FIX_ATTEMPTS` times (default 5). If QA still rejects after the cap, the ticket is escalated for human review.

Human gates exist at two points: confirming bug tickets before fixes begin, and approving each PR before it is merged.

---

## Architecture

```
Browser (React/Vite :5173)
        │  REST + SSE
        ▼
Backend (FastAPI :8000)
        │
        ├── Reviewer agent ──► reads /workspace/<project>
        │                       writes docs/ and wiki/
        │
        ├── QA agent ────────► generates pytest suite
        │        ▲              runs in Docker sandbox
        │        │ accept/reject
        └── Coder agent ─────► patches source files
                                opens PR (branch + diff)
```

All agents call the Anthropic Claude API. Budget guardrails (`SMRT_BUDGET_PER_RUN_USD`, `SMRT_BUDGET_PER_DAY_USD`) hard-halt any run that exceeds the configured limits.

---

## Requirements

- **Docker Desktop** with the WSL2 backend enabled (Windows) or Docker Engine (Linux/macOS)
- **Anthropic API key** — get one at https://console.anthropic.com/settings/keys
- 4 GB RAM available to Docker (the sandbox container needs headroom)

Python, Node, and all other dependencies are installed inside the containers. Nothing needs to be installed on the host beyond Docker.

---

## Configuration

Copy `.env.example` to `.env`. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Claude API key |
| `SMRT_BUDGET_PER_RUN_USD` | `1.50` | Hard spend cap per agent run |
| `SMRT_BUDGET_PER_DAY_USD` | `10.00` | Hard daily spend cap per project |
| `SMRT_MODEL_REVIEWER` | `claude-opus-4-7` | Model used by the Reviewer |
| `SMRT_MODEL_QA` | `claude-sonnet-4-6` | Model used by QA |
| `SMRT_MODEL_CODER` | `claude-sonnet-4-6` | Model used by Coder |
| `SMRT_MAX_FIX_ATTEMPTS` | `5` | QA↔Coder loop cap before escalation |
| `SMRT_BIND_HOST` | `127.0.0.1` | Bind address (localhost only by default) |

All model and loop settings can also be overridden per-project in the UI.

---

## Troubleshooting

**`docker compose up` exits immediately with a port conflict**
Another process is using port 8000 or 5173. Change `SMRT_BACKEND_PORT` and `SMRT_FRONTEND_PORT` in `.env`, then re-run.

**Init Audit finishes but no docs appear**
The project path must be an absolute path as seen by the backend container. For the bundled demo the correct path is `/workspace/eval-fixtures/todo-api`. For your own repo, mount it and use the corresponding `/workspace/...` path.

**"Anthropic API error 401"**
The `ANTHROPIC_API_KEY` in `.env` is missing or still set to the placeholder. Replace it with a real key and restart with `docker compose restart backend`.

---

## License

[MIT](./LICENSE)
