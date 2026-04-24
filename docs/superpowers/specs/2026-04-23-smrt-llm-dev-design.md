# Design: smrt-llm-dev — implementation plan and v1 amendments

**Date:** 2026-04-23
**Author:** Brainstorming session (Claude Opus 4.7)
**Status:** Draft, awaiting review
**Related docs:**
- `PRODUCTION.md` — v1 spec (amended in same commit; see §8 below)
- `NEXT_ITERATION.md` — v2 backlog (amended in same commit; see §8 below)

---

## 1. Purpose

This design captures the implementation plan for SMRT Agent v1 as it will actually be built — i.e., after the four scope decisions made during this brainstorming round. The original `PRODUCTION.md` remains the source of truth for product requirements; this doc records the deltas and the operational plan (phases, repo topology, security baseline, configuration) that turn the spec into a buildable thing.

Read this doc to know **how** we're building. Read `PRODUCTION.md` (with the amendments listed in §8) to know **what** we're building.

---

## 2. Decisions made in this session

| # | Decision | Override of original spec? | Rationale |
|---|---|---|---|
| 1 | Cross-platform support (Windows 10+, macOS 12+, Linux) | Yes — spec was Linux/macOS only; `NEXT_ITERATION.md` §8.4 is now resolved | Developer machine is Windows 11; eval should also work on macOS/Linux without code changes |
| 2 | Ephemeral-per-test-run sandbox (kept) | No — matches original spec §3 | Initially considered persistent sandbox; reverted because state-reset bugs would corrupt the QA blackbox verdict signal |
| 3 | Web UI from day one; no CLI surface | Yes — spec's M1/M2 milestones were CLI-only | User experience requirement; minimum-viable UI added to P1 instead of deferred to M4 |
| 4 | Single synthetic eval fixture (`todo-api`) in v1 | Yes — spec §10 lists two | Sufficient for known-answer benchmarking; second fixture deferred to `NEXT_ITERATION.md` item 1.6 |

All other decisions in `PRODUCTION.md` stand as written.

---

## 3. Phase decomposition

v1 ships in five phases. Each phase ends on a runnable artifact, so if session budget runs out the project is shippable at any phase boundary.

| Phase | Spec milestones | Runnable artifact at end |
|---|---|---|
| **P1 — Foundation** | M1 partial | `docker compose up` boots backend + frontend on `127.0.0.1`; minimal UI lists registered projects; sandbox container builds + health-checks against the `todo-api` fixture |
| **P2 — Reviewer + Project.md** | M1 finish + M3 | Register `todo-api`, click "Run Init Audit", watch Reviewer write `Project.md` live in the UI tool-call stream |
| **P3 — QA↔Coder blackbox loop** | M2 + M4 (HITL pieces) | Human creates a ticket in UI → Coder fixes → QA verdict loop with caps → PR-equivalent surfaces in UI for human accept/reject |
| **P4 — Doc backends** | M5 | On PR accept, Reviewer regenerates `docs/` (GitHub MD) + `wiki/` (Obsidian) for the target project; Jira/Confluence stubs visible in UI as "coming soon" |
| **P5 — Polish** | M6 + M7 | Three Overview-tab dashboards; Explain mode with provenance trailers; thought-process mode toggle; final README + rubric-mapping doc |

**Sub-items dropped from the spec** (not part of v1):
- M6 "skill acquisition validation: run the loop 5x and show Project.md grow" — natural artifact of usage, not production code
- Second eval fixture (`bookstore-api`) — deferred to `NEXT_ITERATION.md` item 1.6

---

## 4. Repo topology

Initial commit lands docs + empty scaffolding (option (b) from brainstorming). Subsequent phases flesh out each subtree.

```
github.com/chlgustjr41/smrt-llm-dev
└── (clone at D:\web-project\smrt-llm-dev\)
    ├── README.md                 # 3-min evaluator demo path (skeletal in P1, finalized in P5)
    ├── PRODUCTION.md             # v1 spec (amended in this commit)
    ├── NEXT_ITERATION.md         # v2 backlog (amended in this commit)
    ├── LICENSE                   # MIT
    ├── .gitignore                # .env, .smrt/runs/, node_modules/, __pycache__/, .venv/, dist/
    ├── .env.example              # public template (see §7)
    ├── docs/
    │   └── superpowers/specs/
    │       └── 2026-04-23-smrt-llm-dev-design.md   # this file
    ├── docker-compose.yml        # added in P1
    ├── Dockerfile.backend        # added in P1
    ├── Dockerfile.frontend       # added in P1
    ├── backend/                  # .gitkeep at first commit; structure per PRODUCTION.md §10
    │   └── .gitkeep
    ├── frontend/                 # .gitkeep at first commit; structure per PRODUCTION.md §10
    │   └── .gitkeep
    ├── eval-fixtures/
    │   ├── README.md             # explains what's here and how to add wild fixtures
    │   ├── todo-api/             # synthetic fixture, built in P1 (see §4.1)
    │   │   └── .gitkeep
    │   └── wild/                 # empty in v1; users clone real-world FastAPI repos here
    │       └── README.md         # links to recommended public FastAPI repos for soak testing
    └── bin/
        └── smrt-exec.py          # cross-platform Docker exec wrapper (replaces .sh from spec)
```

### 4.1 The `todo-api` synthetic fixture

A ~150-LOC FastAPI app with five planted bugs spanning the categories in `PRODUCTION.md` §10:

1. **Silent-logical:** missing `response_model` on `POST /users` causes `hashed_password` to leak in the response
2. **Async:** missing `await` on a coroutine in the `notify_admin` background task
3. **Auth-order:** authorization check happens after the database write in `DELETE /todos/{id}`
4. **Input-validation:** Pydantic field for `due_date` accepts negative timestamps
5. **State-mutation:** counter-increment endpoint has a race condition under concurrent requests

Built during P1. Each bug is documented in `eval-fixtures/todo-api/BUGS.md` (kept out of the agent's reach via `.gitignore` so the agent has to find them itself).

### 4.2 Branch model

Default branch: `main`. The **initial commit** (this design doc + amended specs + scaffolding) lands directly on `main` — it's the seed of the repo, no PR target exists yet. After that, **all feature work happens on `phase/<n>-<slug>` branches with PRs into `main`** (one PR per phase). This is the standard public-repo convention: bootstrap commit on `main`, every later change goes through review.

---

## 5. Cross-platform handling

Three concrete changes from a Linux-only build:

**5.1 Python exec wrapper.** `bin/smrt-exec.sh` (bash) is replaced by `bin/smrt-exec.py` using the `docker` Python SDK. Identical responsibilities: enforce CPU/memory caps, reject containers not prefixed `smrt-sandbox-`, normalize bind-mount paths per platform.

**5.2 Path normalization at the registration boundary.** The web UI accepts a local path. Backend canonicalizes it once into a `pathlib.PurePosixPath` for use as the project key everywhere downstream. Docker bind-mount strings are translated per-platform via `platform_paths.to_docker_mount(host_path)`:
- Linux: `/foo/bar` → `/foo/bar`
- macOS: `/Users/foo/bar` → `/Users/foo/bar`
- Windows: `D:\foo\bar` → `//d/foo/bar`

**5.3 Docker socket auto-detection.** The `docker` Python SDK auto-detects:
- Linux: `/var/run/docker.sock`
- Windows: `//./pipe/docker_engine` (Docker Desktop with WSL2 backend)
- macOS: `~/.docker/run/docker.sock`

We don't override; we just document in the README that Docker Desktop on Windows must be in WSL2 mode.

**Sharp edge documented in README:** Docker Desktop on Windows (WSL2 backend) has noticeably slower bind-mount I/O than native Linux (~3–5× for many small files). Affects per-test-batch container startup, not the agent itself.

---

## 6. Security baseline

Seven defenses, all implemented by P3 latest (most by P1). Cross-references to `PRODUCTION.md` sections in parens.

1. **Secrets only in `.env`** (gitignored; `pydantic-settings` reads them; never logged; `pre-commit` + gitleaks blocks accidental commits). Refines spec §11.
2. **Web UI binds `127.0.0.1` only.** Compose uses explicit `127.0.0.1:<port>:<port>` form. New §7.1 amendment.
3. **Sandbox network isolation.** Internal-only Docker network, no internet, CPU/mem/PID caps. Spec §3.3 unchanged.
4. **Tool scoping enforced by SDK permissions, not just prompts.** `disallowedTools` + path scoping; `PreToolUse` hook writes every call to `tool_calls.jsonl`. Spec §2.x and §9.3 unchanged.
5. **Path traversal hardening on registration.** Refuses paths with `..`; refuses self-registration of the smrt-llm-dev repo; optional `SMRT_PROJECT_ROOT_ALLOWLIST` env var.
6. **Don't auto-trust target-repo content as instructions.** Reviewer prompt has explicit "code is data" clause; all target content wrapped in `<target_file path="...">` tags before subagent injection.
7. **gitignore-aware secret guard** (new in this design; see §6.1 below). New `PRODUCTION.md` §3.4.

### 6.1 gitignore-aware secret guard

A single `PreToolUse` hook (`secret_guard_hook`) registered on the root agent, applied to every subagent.

**Mechanism:**
- On project registration, load the target repo's `.gitignore` (hierarchical — subdirectory `.gitignore` files included) using the `pathspec` library. Cache the compiled matcher in SQLite.
- On every file-touching tool call (`Read`, `Edit`, `Write`, `Glob`, `Grep`, and `Bash` commands matching `cat|less|head|tail|nano|vim|cp|mv|rm`), check the path against:
  - The cached `.gitignore` matcher
  - A built-in **always-deny list** that doesn't depend on `.gitignore` content:
    - `.env`, `.env.*`
    - `*.key`, `*.pem`, `*.p12`, `*.pfx`
    - `id_rsa`, `id_ed25519`, `id_ecdsa`, `*.ppk`
    - `credentials.json`, `service-account*.json`, `gcloud-key*.json`
    - `secrets.yaml`, `secrets.yml`, `secret.yml`
    - `.aws/`, `.azure/`, `.gcloud/`, `.kube/config`
    - `.netrc`, `.npmrc`, `.pypirc`
    - `.git/`
- If denied: structured error returned to the agent (`"Access denied: <path> matches a secret-file or .gitignore pattern."`), call logged to `tool_calls.jsonl` with `outcome: blocked_by_secret_guard`.
- **Narrow exception:** QA writes to `tests/generated/` are allowed even if `tests/` is gitignored. Surfaced as a registration-time warning when this unusual setup is detected.
- **Override path:** if a project gitignores something the agent legitimately needs (e.g., generated `openapi.json`), the human can mark exceptions in the per-project Config tab. Not built in P1; added in P3 only if the deny list actually trips on something useful.

### 6.2 Explicitly out of scope for v1

- Login / RBAC — single-user localhost tool (consistent with `NEXT_ITERATION.md` §2.4)
- gVisor / Kata sandbox runtime — Docker isolation + caps adequate (`NEXT_ITERATION.md` §4.1)
- Tamper-evident audit log — JSONL is good enough (`NEXT_ITERATION.md` §4.3)
- Encrypted secrets at rest beyond `.env` file perms — only one shared secret (`ANTHROPIC_API_KEY`)

---

## 7. Configuration: `.env` + per-project

### 7.1 `.env.example` (committed, public)

```bash
# ─── REQUIRED ───────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-REPLACE_ME

# ─── BUDGET GUARDRAILS ──────────────────────────────────────
SMRT_BUDGET_PER_RUN_USD=1.50
SMRT_BUDGET_PER_DAY_USD=10.00

# ─── BIND ADDRESS ──────────────────────────────────────────
# Localhost-only by default. Setting to 0.0.0.0 exposes the
# UI to your local network — use a reverse proxy with auth if
# you need that.
SMRT_BIND_HOST=127.0.0.1
SMRT_BACKEND_PORT=8000
SMRT_FRONTEND_PORT=5173

# ─── MODEL OVERRIDES (UI overrides per-project) ────────────
SMRT_MODEL_REVIEWER=claude-opus-4-7
SMRT_MODEL_QA=claude-sonnet-4-6
SMRT_MODEL_CODER=claude-sonnet-4-6

# ─── LOOP CAPS (UI overrides per-project) ──────────────────
SMRT_MAX_FIX_ATTEMPTS=5
SMRT_MAX_QUESTIONS_PER_ATTEMPT=1

# ─── PATH ALLOWLIST (optional, off by default) ─────────────
# Comma-separated absolute paths. If set, registration refuses
# paths outside these roots.
SMRT_PROJECT_ROOT_ALLOWLIST=

# ─── OBSERVABILITY ─────────────────────────────────────────
SMRT_LOG_LEVEL=INFO
```

### 7.2 `.env` (gitignored, local)

User runs `cp .env.example .env` after first checkout, fills in their real `ANTHROPIC_API_KEY`. Windows users use `copy` instead; README documents both.

### 7.3 Per-project config (SQLite)

Per `PRODUCTION.md` §7.2 Config tab. Stores model per subagent, scheduler cadence, watcher globs, `max_fix_attempts`, autonomy mode. Defaults inherit from `.env`; UI overrides take precedence.

### 7.4 State location

| What | Where | Notes |
|---|---|---|
| Cross-project registry, run history | `~/.smrt/state.db` (SQLite) | Backend's home; per-OS user dir |
| Per-project agent state (tickets, knowledge, runs) | `<target-repo>/.smrt/` | Owned by the agent inside each registered repo; `.smrt/runs/` gitignored |
| Backend run artifacts (transcripts, logs) | `<smrt-llm-dev>/.smrt/runs/` | Gitignored |

---

## 8. Spec amendments summary

The following surgical edits are made to existing files in the same commit as this design doc.

### 8.1 `PRODUCTION.md` edits

| Edit | Section | Change |
|---|---|---|
| 1 | §3.1 (Container lifecycle) | Add bullet: WSL2 requirement on Windows; Docker socket auto-detected per platform |
| 2 | §3.3 (Sandbox safety) | Replace `bin/smrt-exec.sh` references with `bin/smrt-exec.py`; note cross-platform Python implementation |
| 3 | New §3.4 (Secret protection) | Full new subsection covering the gitignore-aware secret guard from this design's §6.1 |
| 4 | §7.1 (Stack) | Append: bind defaults to `127.0.0.1`; Compose uses explicit `127.0.0.1:<port>:<port>` form |
| 5 | §10 (Repository layout) | Replace `bin/smrt-exec.sh` with `bin/smrt-exec.py`; note `eval-fixtures/` ships only `todo-api/` in v1; add `eval-fixtures/wild/` placeholder |
| 6 | §11 (Secrets, privacy) | Add bullet: cross-platform support (Windows/macOS/Linux) is a v1 requirement; WSL2 backend required on Windows |
| 7 | §13 (Implementation milestones) | M1: remove "No UI yet — driven from a CLI"; M2: remove "CLI still sufficient"; M4: rename to "Full Web UI + HITL" |
| 8 | §14 (Known open questions) | Add: v1 ships one synthetic fixture; second deferred to v2 |

### 8.2 `NEXT_ITERATION.md` edits

| Edit | Section | Change |
|---|---|---|
| A | §8.4 (No Windows support) | Mark `[resolved in v1]` rather than deleting |
| B | New §1.6 | Second eval fixture (`bookstore-api`) — HIGH priority for v2 |
| C | New §5.6 | Real-world fixture loader UI — LOW priority for v2 |

---

## 9. Open questions deferred to implementation

These are intentional "decide when we get there" items. Each will be resolved during the named phase, not now:

| Question | Phase | Default if no other input |
|---|---|---|
| `pathspec` vs `igittigitt` for gitignore parsing | P1 | `pathspec` (more mature, used by `pre-commit`) |
| `shadcn/ui` MCP availability and use | P1 | Plain Tailwind + Radix primitives if MCP not available |
| SQLAlchemy 2.x async vs sync session | P1 | Async (matches FastAPI's async story) |
| Pytest output capture: stdout/JSON parser vs custom plugin | P3 | stdout + JUnit XML parser (custom plugin deferred to `NEXT_ITERATION.md` §2.2) |
| Obsidian Bases plugin: required or fallback to Dataview | P4 | Bases primary, Dataview fallback (per spec §6.2) |
| Cost-meter accuracy: token counts from SDK responses vs. tiktoken | P5 | SDK responses (authoritative) |

---

## 10. Workflow from here

1. **Now:** this design doc + amended `PRODUCTION.md` + amended `NEXT_ITERATION.md` + LICENSE + .gitignore + .gitattributes + .env.example + README + scaffolding stubs are staged for an initial commit directly on `main` (bootstrap commit; no PR target exists yet)
2. **Spec self-review** (inline; no separate doc)
3. **User reviews written spec** — gate
4. **Create public GitHub repo** `chlgustjr41/smrt-llm-dev`, push the initial `main` commit
5. **Invoke writing-plans skill** → produces `docs/superpowers/plans/2026-04-23-smrt-llm-dev-impl-plan.md`
6. **User reviews implementation plan** — gate
7. **Create GitHub issues from impl plan** — one issue per major step, labeled by phase (`phase:1`, `phase:2`, …)
8. **Notify user to switch model to Sonnet** — explicit message
9. **Begin P1 implementation**, closing issues as features land
10. **Repeat for P2–P5**

---

## 11. Definition of done for this brainstorming round

- [x] Four scope decisions recorded (§2)
- [x] Phase decomposition agreed (§3)
- [x] Repo topology agreed (§4)
- [x] Cross-platform plan agreed (§5)
- [x] Security baseline including secret guard agreed (§6)
- [x] `.env` template and config layout agreed (§7)
- [x] Spec amendments enumerated (§8)
- [ ] Spec doc + `PRODUCTION.md` + `NEXT_ITERATION.md` written and committed locally
- [ ] User reviews this spec and approves before writing-plans skill is invoked
