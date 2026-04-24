# PRODUCTION.md — SMRT Agent

**Project codename:** `smrt-agent`
**Target:** SMRT Systems hiring challenge — an AI-driven dev orchestrator for Python FastAPI codebases
**Spec version:** v1.0 (iteration 1)
**Companion documents:**
- `RESEARCH.md` — academic foundations (Agentless, CoverUp, RepoAgent, Ask-or-Assume, OpenHands, RepairAgent, Meta ACH)
- `NEXT_ITERATION.md` — deferred scope and the v2 roadmap

This spec is written to be consumed by Claude Code. Every section states *what* to build and *why*. Where the "why" ties to a research result, the paper is named inline so you can consult `RESEARCH.md` when implementing.

---

## 1. Product summary

SMRT Agent is a semi-autonomous multi-agent system that acts as a **QA engineer + junior developer pair** inside a Python FastAPI codebase. It proactively discovers bugs (especially logical ones), produces fixes through a blackbox QA↔Coder loop, maintains documentation in both GitHub-native Markdown and a parallel Obsidian vault, and surfaces all activity through a React web UI with a Dockerized FastAPI backend.

The agent does **not** implement new features. Its responsibilities are the three mandated by the SMRT task:

1. **Documentation** — keep code readable and self-explanatory
2. **Test generation** — cover every logic path with robust tests
3. **Bug squashing** — identify and resolve logical bugs that linters miss

Everything else — periodic repo health checks, ticket generation, branch management, PR preparation, vault maintenance — is scaffolding that serves those three outcomes.

### Human-in-the-loop contract

Two human decisions gate the loop; everything else is autonomous:

1. **Bug confirmation** — when QA generates a bug ticket, human confirms it's a real bug before fixing starts
2. **PR acceptance** — when QA certifies a fix, human reviews and accepts the PR

If the human rejects a fix at step 2, they must provide a reason (free-text). That reason becomes a signal that updates `Project.md` (see §5.1).

---

## 2. Agent hierarchy

**Three roles, not four.** The Reviewer, Orchestrator, and Documenter are a single agent. Delegation flows:

```
Reviewer/Orchestrator/Documenter  (Opus 4.7, configurable)
    │
    ├──► QA Agent  (Sonnet 4.6, configurable)
    │       │
    │       └──► (blackbox feedback loop) ──► Coder Agent  (Sonnet 4.6, configurable)
    │
    └──► (direct) Documenter outputs (owned by Reviewer role)
```

**Key rule:** only the Reviewer/Orchestrator has write access to `Project.md`. QA and Coder never write to it.

### 2.1 Reviewer / Orchestrator / Documenter

Reads the most; reasons the deepest; runs the least often. Acts as:

- **Orchestrator** of all other agents
- **Reviewer** during periodic checkups — produces the test plan
- **Documenter** — maintains `docs/`, the Obsidian `wiki/`, and `Project.md`

**Responsibilities:**

- On first connection to a new project: perform the initialization audit (§5.1)
- On periodic checkup: re-read recent commits, re-read code changes since last checkup, produce a structured test plan (§4.2), hand off to QA
- On human rejection of a PR: ask the human for the rejection reason, interpret it as a learning, update `Project.md`
- On human acceptance of a PR: update `Project.md` with the resolution pattern
- On QA↔Coder loop failure: read the QA report and Coder submission history, compose the final human-facing report
- Maintain `docs/` and `wiki/` whenever logic changes merge
- Never participate in the QA↔Coder feedback loop itself

**Model:** Opus 4.7 by default. User-configurable in the web UI per project.

**Tools allowlist:**
`Read, Glob, Grep, Write, Edit, WebFetch, WebSearch, Bash, Agent (to delegate), TodoWrite, AskUserQuestion`

Scope Bash to read-only git operations: `Bash(git log:*)`, `Bash(git diff:*)`, `Bash(git status:*)`. No `git commit`, no `git push`, no file-mutating bash.

**Permission mode:** `default` with a `can_use_tool` callback for any Edit or Write targeting `Project.md`, `docs/`, or `wiki/` (see §7.3).

### 2.2 QA Agent

The most valuable agent in the system. Does not trust the Coder. Owns tests.

**Responsibilities:**

- Receive a test plan from the Reviewer
- Convert each test plan entry into an executable pytest test
- Run tests against the target FastAPI app in the sandbox (§3)
- When a test fails, decide whether to file a bug ticket (with confidence score) or suppress (flaky / test-bug)
- During the QA↔Coder loop: re-run the relevant hidden test after each Coder submission; produce behavioral feedback (not test code)
- When the loop hits the configurable cap: produce a failure report with theories of why fixes kept failing
- Maintain `bugs-resolved.jsonl` and `test-status.yaml` (append/update on resolution)
- Never reveal test code, assertion values, or test file paths to the Coder

**Model:** Sonnet 4.6 by default.

**Tools allowlist:**
`Read, Write, Edit, Glob, Grep, Bash, TodoWrite`

`Edit` and `Write` are **restricted by permission rule** to `tests/**` and `.smrt/knowledge/{bugs-resolved.jsonl,test-status.yaml}`. Never `src/**`.

Bash is restricted to: `Bash(pytest:*)`, `Bash(curl:*)`, `Bash(docker exec smrt-sandbox-* pytest:*)`, `Bash(docker exec smrt-sandbox-* curl:*)`.

**Permission mode:** `acceptEdits` within its scoped paths.

### 2.3 Coder Agent

Writes code. Is told what's broken, not how it's being tested.

**Responsibilities:**

- Receive a bug ticket + detailed natural-language fix description from QA
- Read `src/**` and `Project.md` freely
- Implement a fix on a new branch
- Submit the fix (a git commit on its branch) back to QA
- On rejection: receive QA's behavioral feedback, optionally use its one allowed question to QA, then resubmit
- Never reads `tests/**`, never runs pytest, never sees assertion values

**Model:** Sonnet 4.6 by default.

**Tools allowlist:**
`Read, Write, Edit, Glob, Grep, Bash, TodoWrite`

`Edit` and `Write` are **restricted by permission rule** to `src/**` and `requirements.txt`/`pyproject.toml`. Never `tests/**`, never `.smrt/**`, never `docs/**`, never `wiki/**`.

Bash is restricted to `Bash(python:*)` for ad-hoc REPL-style exploration (not test execution) and `Bash(git:*)` for branch management. Explicit deny list includes `Bash(pytest:*)` and anything touching the Docker sandbox.

**Permission mode:** `acceptEdits` within its scoped paths.

**The blackbox enforcement is a hard permission rule, not a prompt-level request.** Per Anthropic's guidance ("Hooks guarantee behavior; prompts suggest it"), we enforce it in `ClaudeAgentOptions.disallowedTools` + path scoping.

---

## 3. Sandbox: Docker ephemeral-per-test-run

**Decision:** ephemeral-per-test-run containers, not semi-permanent. Justification:

| Criterion | Ephemeral | Semi-permanent |
|---|---|---|
| Security | Fresh state every run, no cross-test contamination | Accumulating state, risk of leaked secrets or persisted side-effects |
| Complexity | One entry/exit point, simple lifecycle | Needs state-reset logic, garbage collection, health checks |
| Convenience | ~5–10s startup cost per batch | Faster per-test, but startup only amortizes if test batches are huge |
| Determinism | Perfectly reproducible | Drift over time |

Ephemeral wins on three of four. The startup cost is acceptable because tests run in batches (per-ticket or per-checkup), not one at a time.

### 3.1 Container lifecycle

1. On project registration, the Reviewer agent inspects the target repo and **generates a `Dockerfile.smrt`** if none exists. Base image: `python:3.11-slim` (pin exact version per project). Install from `requirements.txt` or `pyproject.toml`. Copy source. Expose the FastAPI port.
2. `Dockerfile.smrt` is written to `.smrt/sandbox/Dockerfile` inside the target repo. Do not overwrite an existing `Dockerfile` — prefer the project's own if present and viable; fall back to `Dockerfile.smrt` otherwise.
3. On every test batch: build image if source changed (cache by source tree hash), spin up container named `smrt-sandbox-<ticket-id>-<timestamp>`, wait for `/health` (or `/` or `/docs`) to return 200, run tests, capture results + logs, tear down.
4. Container network: isolated Docker network per run. No bind mounts of the host FS beyond the target repo (read-only mount of `src/`, bind mount of `tests/` read-write for QA only).
5. **Cross-platform note:** on Windows, Docker Desktop must be configured with the WSL2 backend (Settings → General → "Use the WSL 2 based engine"). The Docker socket is auto-detected per platform via the `docker` Python SDK — no override needed. See §11 for the full cross-platform support contract.

### 3.2 HTTP testing tooling

QA uses `httpx.AsyncClient` with `ASGITransport` for in-process tests where possible (faster, shares fixtures). For integration and "does-the-whole-thing-work" tests, QA uses `httpx.AsyncClient(base_url=http://localhost:<mapped-port>)` against the Dockerized container.

**Postman / Newman note:** considered Postman collections as an alternative. Rejected for v1: Postman is a GUI workflow, Newman adds a Node runtime dependency, and the QA agent already writes pytest. Adding Postman = two sources of truth for tests. If it becomes useful for the human reviewer to manually exercise endpoints during bug confirmation, generating a Postman collection **from the OpenAPI spec** is a deferred feature (see NEXT_ITERATION.md). For v1, the UI's "reproduce this bug" button runs the QA-generated pytest inside the sandbox.

### 3.3 Sandbox safety requirements

- Container has no internet access (use `--network smrt-internal`, a Docker network with no gateway)
- Container CPU cap: 2 cores, memory cap: 2GB, process cap: 256
- QA's test execution bash calls must go through a wrapper at `bin/smrt-exec.py` that enforces these caps and rejects containers not prefixed `smrt-sandbox-`. Implemented as a Python module using the `docker` SDK so it runs unchanged on Windows/macOS/Linux (replaces the spec-original bash wrapper).
- No volume mounts to host except the read-only source mount and read-write `tests/` mount
- A 60s per-test timeout, 300s per-batch timeout

### 3.4 Secret protection (gitignore-aware deny rule)

A single `PreToolUse` hook (`secret_guard_hook`) is registered on the root agent and applied to every subagent. Its job: prevent any agent from reading or writing files the developer has marked as sensitive, even if the agent's tool scope would otherwise permit it.

**Mechanism:**

1. **On project registration**, the backend loads the target repo's `.gitignore` (hierarchical — subdirectory `.gitignore` files included) using the `pathspec` library and caches the compiled matcher in SQLite, keyed by canonical project path.
2. **On every file-touching tool call** (`Read`, `Edit`, `Write`, `Glob`, `Grep`, and `Bash` commands matching `cat|less|head|tail|nano|vim|cp|mv|rm`), the hook checks the path against:
   - The cached `.gitignore` matcher
   - A built-in **always-deny list** (independent of `.gitignore` content):
     - `.env`, `.env.*`
     - `*.key`, `*.pem`, `*.p12`, `*.pfx`
     - `id_rsa`, `id_ed25519`, `id_ecdsa`, `*.ppk`
     - `credentials.json`, `service-account*.json`, `gcloud-key*.json`
     - `secrets.yaml`, `secrets.yml`, `secret.yml`
     - `.aws/`, `.azure/`, `.gcloud/`, `.kube/config`
     - `.netrc`, `.npmrc`, `.pypirc`
     - `.git/`
3. **On denial**, the hook returns a structured error to the agent: *"Access denied: `<path>` matches a secret-file or .gitignore pattern. This file is intentionally off-limits to all agents."* The denied call is logged to `tool_calls.jsonl` with `outcome: blocked_by_secret_guard` for audit.
4. **Narrow exception:** QA's writes to `tests/generated/` are allowed even if `tests/` is gitignored (some projects do gitignore `tests/`). A registration-time warning surfaces this unusual setup to the human.
5. **Override path:** if a project gitignores something the agent legitimately needs (e.g., a generated `openapi.json`), the human can mark exceptions in the per-project Config tab (UI added in P3 only if the deny list actually trips on something useful).

This rule applies to **all three subagents** (Reviewer, QA, Coder) — not only Coder. The Reviewer walks the entire tree during the initialization audit (§5.1) and would otherwise be the most likely to ingest a `.env` or `secrets.yaml` into `Project.md` or `wiki/`, which would then poison every downstream subagent's context.

---

## 4. The full dev-cycle simulation

Two trigger paths produce tickets: periodic checkup (proactive) and human-created (reactive). Both converge to the same QA↔Coder loop.

### 4.1 Triggers (three, all converging)

1. **Periodic full checkup** (scheduler) — Reviewer runs end-to-end repo health check; produces test plan; QA executes; any failures become draft tickets. Configurable cadence per project (default: daily 03:00 local).
2. **File watcher + commit trigger** (reactive) — on new commit to the watched branch, Reviewer analyzes the diff, produces a *targeted* test plan scoped to changed code paths, QA executes only those tests.
3. **Human-created ticket** — from the web UI, a human fills a ticket form (title, description, affected endpoint if known). Skips straight to the QA agent, which reproduces and confirms.

**Scheduler:** APScheduler embedded in the FastAPI backend for time-based checks; `watchfiles` (Rust-backed, async-native) for file-change reactive triggers. Both per-project configurable.

### 4.2 Reviewer's test plan artifact

Produced on every checkup. Stored at `.smrt/test-plan.yaml` inside the target repo (committed, diffable across branches). Structure:

```yaml
version: 1
generated_at: 2026-04-23T12:00:00Z
generated_by: reviewer_agent
project_context_hash: <sha of Project.md at time of generation>
entries:
  - id: TP-0042
    endpoint: POST /users
    preconditions: "Empty database, no existing user with email 'a@b.com'"
    scenario: "Request with valid payload"
    expected: "201 with user object containing id, email; password hash not present in response"
    category: logical    # static | logical | security
    priority: high       # low | medium | high
    rationale: "User creation is a new code path per commit a1b2c3d; password leak in response is a common FastAPI mistake when response_model is omitted"
    references:
      code: ["src/routers/users.py:42-78"]
      related_tests: []
      related_bugs_resolved: []
```

The QA agent reads this file and converts entries to executable pytest tests one-to-one. The `category` field drives strategy:

- `static` → conventional assertion-style test
- `logical` → Hypothesis property test + specific corner-case assertions
- `security` → both, plus negative-auth and authz variants

### 4.3 Logical-bug detection strategy (Q1.3: option d)

All three techniques enabled, selectable per test-plan entry by the Reviewer:

**(a) Mutation-guided** (Meta ACH pattern). QA runs `mutmut` or `cosmic-ray` against source files implicated in recent commits. For each surviving mutant, QA generates a test that would kill it. New tests are added to the test plan with category `logical`.

**(b) Property-based (Hypothesis)**. For endpoints with well-typed Pydantic inputs, QA generates Hypothesis strategies from the Pydantic schema (use `hypothesis-jsonschema` from the OpenAPI spec). Runs 100 examples per property. Any failure becomes a bug ticket.

**(c) Differential vs git history**. For endpoints whose behavior changed in the last N commits, QA runs the **old** tests against the **new** code. Unexpected diffs (new 500s, changed status codes on formerly-passing paths, changed response shapes) become bug ticket candidates.

**Test-status memory** (Q1.3 memory requirement). `test-status.yaml` tracks each test's last N runs. Green tests with >10 consecutive passes are demoted to a weekly sampling; red tests are promoted to every checkup. This implements "only required tests will be tested separately until resolved."

### 4.4 QA bug ticket schema

When QA decides a failure is a real bug (confidence threshold ≥0.6, configurable), it writes a ticket to `.smrt/tickets/<id>.yaml` and emits it to the UI queue:

```yaml
id: BUG-0042
created_at: 2026-04-23T12:15:00Z
created_by: qa_agent
source: periodic_checkup   # periodic_checkup | commit_trigger | human
test_plan_entry: TP-0042
title: "POST /users leaks password hash in response"
summary: |
  Endpoint POST /users returns the full user record including the password
  hash field. The response_model is missing, so SQLAlchemy's ORM attribute
  `hashed_password` is serialized.
severity: high
category: security
observed: |
  Response body contains {"id": 1, "email": "a@b.com", "hashed_password": "$2b$12$..."}
expected: |
  Response body should omit hashed_password. A UserPublic response_model
  with only {id, email, created_at} is the typical fix.
reproducing_test: tests/generated/test_bug_0042.py::test_password_hash_not_leaked
code_pointers:
  - src/routers/users.py:42-78
  - src/models/user.py:12-25
qa_confidence: 0.92
status: awaiting_human_confirmation
```

The ticket goes to the **Pending Confirmation** queue in the UI. Human action: `Confirm & assign to Coder` / `Reject as false positive` / `Request more info`. On rejection, the human's reason is stored at `.smrt/knowledge/mistakes-pending.jsonl` and handed to the Reviewer for interpretation into `Project.md`.

### 4.5 The QA↔Coder blackbox feedback loop

On human confirmation, the Reviewer dispatches the ticket to the Coder. Coder is given:

- The bug ticket, with `reproducing_test` field **redacted** (replaced with `<redacted: QA will run the hidden test>`)
- Read access to all of `src/**`, `Project.md`, `docs/**`
- No access to `tests/**`, no access to the redacted field

Coder works on a new branch named `smrt/fix/<ticket-id>-<slug>`. When it submits a fix, the orchestrator runs QA's hidden test against the fix.

**Feedback contract (this is the entire conversation surface — no free chat):**

1. **Coder submits** → commit on its branch. A submission is a completed code change, not a draft.
2. **QA re-runs hidden test** → produces a verdict:
   - ACCEPT → loop exits, fix passes to PR preparation
   - REJECT with behavioral feedback → Coder gets feedback + one optional question

**QA feedback is strictly behavioral**, never code or assertion values. Examples of good feedback:
> "The endpoint still returns 200 with the password hash present in the JSON response when called with a valid payload. Additionally, a new failure: GET /users/{id} now returns 500 for existing users — your change may have broken serialization globally."

Example of disallowed feedback (DO NOT produce this — QA must be prompt-engineered against it):
> "Your test_users.py::test_password_hash_not_leaked expects the response to not contain 'hashed_password'."

3. **Coder's one question per rejection** (optional, configurable cap per fix attempt): natural language question to QA. QA answers descriptively, never with code. Example Q: "Should I create a new Pydantic model or modify UserResponse?" Example A: "Either is acceptable. The constraint is that the response must not include hashed_password. The implementation choice is yours."

4. **Side-effect warning**: QA runs the *full* test-status.yaml "currently-green" set after each Coder submission. If a previously-green test is now red, QA's rejection feedback must include: *"Your fix broke additional behavior: [list]."*

**Hard caps** (configurable in web UI, saved per project):
- `max_fix_attempts` (default 5)
- `max_questions_per_attempt` (default 1)
- Total conversation budget across all attempts is max_fix_attempts × max_questions_per_attempt

### 4.6 Failure report when caps are hit

If the Coder fails to produce a passing fix within `max_fix_attempts`:

1. **QA composes a failure report** containing:
   - Bug restated
   - Summary of each attempt (commit SHA, what changed, what failed)
   - Theories for why fixes kept failing (e.g., "Coder consistently missed the serialization layer — focused on the router rather than the Pydantic model")
   - Recommended approach if a human were to take over

2. **Reviewer reads the QA report + Coder's submission history** and composes a human-facing final report at `.smrt/reports/<ticket-id>.md`. This report:
   - Does NOT contain the hidden test code (preserves the blackbox for audit purposes)
   - Summarizes root cause analysis
   - Proposes next steps (escalate to human developer, split ticket, close as out-of-scope)

3. Report surfaces in the UI as a failed ticket with a "Read report" action.

### 4.7 PR preparation on acceptance

When QA accepts a fix:

1. Reviewer generates a PR summary describing what changed and why (plain English, one paragraph + a bulleted change list — no technical minutiae, since the task says "high-level description of what changed for what reason").
2. Reviewer updates `docs/**` and `wiki/**` for any affected endpoints or modules.
3. Reviewer creates a git commit bundling code changes + doc changes + test additions on the `smrt/fix/<ticket-id>-<slug>` branch.
4. The UI shows a pending PR: summary, branch name, diff view, and an Accept button.
5. Human clicks Accept (in v1: this merges locally only; does not push to GitHub — see NEXT_ITERATION.md). On accept, Reviewer updates `Project.md` with the resolution pattern and appends to `bugs-resolved.jsonl`.
6. Human can Reject with a reason; reason flows to Reviewer → `Project.md` update.

---

## 5. Memory system and project learning

### 5.1 Project.md — the living repository understanding

**Owned exclusively by the Reviewer agent.** No other agent may write to this file. It is the project's compounding knowledge base.

**When it's written:**
1. Initialization audit (first project registration)
2. After human confirms/rejects a PR — Reviewer distills the outcome into a new section or updates existing sections
3. After human rejects a bug ticket as false positive — Reviewer updates invariants/assumptions

**Never written** during the QA↔Coder loop itself — the loop is transient, the file is durable.

**Initialization audit (first registration):**

The Reviewer does a deep read of the repo. Regardless of whether docs exist, it:

1. Walks the AST of every `src/**/*.py` file, building a module-function-class graph
2. Reads every `README.md`, `docs/**/*`, and inline docstring
3. Reads `git log --oneline -n 200` and flags recurring themes, contributor patterns, and "fix" commits
4. Reads `requirements.txt` / `pyproject.toml` and infers the architectural stack
5. Spins up the FastAPI app in the sandbox and fetches `/openapi.json` to inventory every endpoint
6. If documentation is missing or thin, **generates baseline documentation into `docs/` and `wiki/` before proceeding**
7. Writes the initial `Project.md`

**Project.md structure:**

```markdown
# Project: <name>

## Purpose
<1-2 paragraphs — what this server does, who uses it>

## Architecture invariants
- <e.g., "All endpoints authenticate via Bearer JWT except /health and /docs">
- <e.g., "Passwords are hashed with bcrypt; never appear in any response">
- <e.g., "All DB writes happen in a dependency-injected session and roll back on exception">

## Domain entities
- <e.g., "User: has email, hashed_password, created_at; soft-deleted via is_active flag">

## Known sharp edges
- <things the Reviewer observed that tripped up the Coder or created bugs before>

## Security posture
- <auth model, sensitive fields, rate-limiting assumptions>

## Test coverage philosophy
- <what levels of testing this repo has and expects>

## Lessons (learned from rejected fixes and false positives)
### <Date> — <one-line summary>
<what happened, what the Reviewer learned, how future agents should behave differently>
```

### 5.2 Other memory files (not in Project.md)

Kept separate for O(1) machine access and because they have different write cadences:

**`.smrt/knowledge/bugs-resolved.jsonl`** (append-only, one JSON object per line):
```json
{"id": "BUG-0042", "title": "...", "root_cause_category": "missing_response_model", "fix_pattern": "introduce_pydantic_response_schema", "files_touched": ["src/routers/users.py", "src/schemas/user.py"], "test_added": "tests/generated/test_bug_0042.py::test_password_hash_not_leaked", "resolved_at": "2026-04-23T15:00:00Z", "attempts": 2, "final_reviewer_note": "..."}
```

Used for semantic search by future QA and Reviewer runs: "have we seen a bug like this before?"

**`.smrt/knowledge/test-status.yaml`** (last-N-runs history):
```yaml
version: 1
tests:
  tests/generated/test_bug_0042.py::test_password_hash_not_leaked:
    last_runs: [pass, pass, pass, pass, pass, pass, pass, pass, pass, pass, pass]
    status: green_stable   # green_stable | green | red | flaky
    last_run_at: 2026-04-24T03:00:00Z
    promoted_to: weekly    # per_checkup | daily | weekly
```

Drives the "only required tests until resolved" promotion/demotion logic.

### 5.3 Skill acquisition (Q7.2 option d)

The agent gets better at a specific project over time because:

1. Every resolved bug adds to `bugs-resolved.jsonl` — QA semantic-searches this before generating new tests
2. Every rejected ticket or rejected PR produces a Reviewer-curated lesson appended to `Project.md`
3. `Project.md` is injected into every subagent's context on every delegation (compressed if large)
4. The Reviewer's own system prompt includes an instruction to cite `Project.md` invariants when writing test plans

**Explicit learning signal:** when a human rejects a PR, the UI prompts for a reason. The Reviewer takes that reason and asks itself "what about the repository did I misunderstand that led to this rejection?" and writes that insight into `Project.md`'s Lessons section. The raw rejection reason goes to `.smrt/knowledge/rejections.jsonl` for auditability.

### 5.4 Explain mode (Q7.2 option b)

Every PR commit message embeds a structured JSON trailer:

```
Fix: password hash leaks in POST /users response

[smrt-provenance]
{
  "ticket": "BUG-0042",
  "subagent": "coder_agent",
  "reasoning": "Introduced UserPublic pydantic model omitting hashed_password; wired as response_model on the router decorator",
  "sources_consulted": ["Project.md#security-posture", "bugs-resolved.jsonl:BUG-0017"],
  "attempts": 2,
  "related_lessons_applied": ["L-2026-04-20: always check for ORM-to-schema leakage"]
}
[/smrt-provenance]
```

The web UI parses this trailer from any commit and displays it as an "Explain this change" panel.

---

## 6. Documentation: GitHub + parallel Obsidian vault

Both sources of truth live in the repo. Neither is transformed from the other — they are generated in parallel from the same Reviewer-agent knowledge (Q4.1 option a).

### 6.1 GitHub-native docs (`docs/`)

Standard Markdown, GitHub-renderable. No wikilinks, no callouts, no Dataview.

```
docs/
├── README.md                     # quickstart, pointers to other docs
├── architecture.md               # high-level overview
├── api/
│   ├── index.md                  # endpoint catalog
│   └── <endpoint>.md             # per-endpoint reference
├── modules/
│   └── <module>.md               # per-module technical reference
└── decisions/
    └── YYYY-MM-DD-<slug>.md      # ADRs
```

Auto-updated by Reviewer whenever a merged PR touches the corresponding code. Uses the **RepoAgent bidirectional reference graph** pattern (see RESEARCH.md §1.3) — only regenerate docs for modules whose source or whose referees changed. Full-repo regeneration requires an explicit human trigger.

### 6.2 Obsidian vault (`wiki/`)

Full Obsidian conventions. Adapted from the claude-obsidian pattern (Karpathy's LLM Wiki).

```
wiki/
├── index.md                      # master catalog, wikilinks to every note
├── hot.md                        # recent-context cache, updated on every checkup
├── log.md                        # append-only operation log
├── Wiki Map.canvas               # visual hub (Obsidian canvas JSON)
├── _moc/
│   ├── api-reference.md          # MOC of endpoints
│   ├── modules.md                # MOC of modules
│   ├── recent-changes.md         # auto-gen from git log + bugs-resolved
│   └── security.md               # MOC of security-relevant code paths
├── api/
│   └── POST_users_create.md      # one note per endpoint
├── modules/
│   └── services__auth.md         # mirroring src/ with __ replacing /
├── decisions/
│   └── 2026-04-23-chose-jwt.md
├── bugs/
│   └── BUG-0042.md               # one note per resolved bug, linked from API notes
└── meta/
    └── dashboard.base            # Obsidian Bases dashboard
```

**Every note has YAML frontmatter** with at minimum:
```yaml
---
type: endpoint | module | decision | bug | concept
tags: [api, auth, security]
related: ["[[modules/services__auth]]", "[[bugs/BUG-0042]]"]
updated: 2026-04-23
smrt_source_hash: a1b2c3d            # sha of the src file(s) this note documents
---
```

**Callouts are used where semantically useful**:
- `> [!warning]` — known sharp edges from Project.md
- `> [!info]` — non-obvious design decisions
- `> [!bug]` — historical bug locations, linked to bug notes
- `> [!tip]` — lessons learned

**Dataview support (Q4.3 yes):**

Include Dataview-queryable frontmatter. Primary dashboard uses **Obsidian Bases** (core plugin since v1.9.10, August 2025 — preferred over Dataview going forward). Legacy Dataview dashboard at `wiki/meta/dashboard.md` ships as optional fallback. Example Bases query at `wiki/meta/dashboard.base`:
- Table of all endpoints with columns: `type`, `tags`, `updated`, `related bug count`
- Filterable by tag

**Hot cache pattern:**

`wiki/hot.md` is regenerated after every checkup and every merged PR. Contains: last 5 resolved bugs, last 5 open tickets, modules touched in the last 7 days, currently-red tests. Injected into subagent prompts alongside `Project.md` (compressed).

**Parallel maintenance:**

Whenever the Reviewer updates `docs/` it also updates `wiki/`. These are separate tool calls, not a transformation. The **source of truth is the Reviewer's understanding of the codebase**; `docs/` and `wiki/` are dual projections of that understanding.

### 6.3 Beta placeholders (Q4.4 option b)

Define an abstract `DocBackend` interface in `backend/docs/backends.py`:

```python
class DocBackend(ABC):
    @abstractmethod
    async def upsert_module_doc(self, module: ModuleDoc) -> None: ...
    @abstractmethod
    async def upsert_endpoint_doc(self, endpoint: EndpointDoc) -> None: ...
    @abstractmethod
    async def upsert_decision(self, decision: DecisionDoc) -> None: ...
```

Concrete implementations:
- `GitHubBackend` — writes to `docs/`
- `ObsidianBackend` — writes to `wiki/`
- `JiraBackend` — raises `NotImplementedError("Jira backend is a v2 feature")` with a TODO
- `ConfluenceBackend` — same treatment

The web UI shows a "Documentation backends" panel with GitHub and Obsidian enabled and Jira/Confluence shown as disabled "coming soon" chips.

---

## 7. Web UI

### 7.1 Stack

- **Frontend:** React + TypeScript + Vite + Tailwind CSS + shadcn/ui (use the MCP if available to reduce boilerplate)
- **Backend:** FastAPI (separate from the target-repo FastAPI, obviously) with WebSocket for live logs
- **Storage:** SQLite for project registry, ticket history, run logs; file system for agent-managed artifacts (`.smrt/**`)
- **Real-time:** FastAPI WebSocket endpoint `/ws/projects/{id}/events` emitting JSON events (tool_call, tool_result, subagent_start, subagent_end, hitl_request)
- **Deployment:** `docker-compose up` brings up: `smrt-backend` (FastAPI + embedded scheduler), `smrt-frontend` (served via Nginx or Vite preview), and the Docker daemon socket mounted for sandbox orchestration
- **Bind address:** both backend and frontend bind `127.0.0.1` only by default. `docker-compose.yml` publishes ports as the explicit `127.0.0.1:<host-port>:<container-port>` form so nothing leaks to the LAN. Changing this requires manually editing the compose file (which carries an inline warning comment) — there is no `.env` switch to expose the UI to the network, by design. v1 has no auth; LAN exposure is only safe behind a reverse proxy you set up yourself.

### 7.2 Screens

1. **Projects dashboard** — list of registered projects, health status (green/yellow/red), last checkup time, open tickets, cost-to-date. Add Project button.
2. **Project detail** — for each project:
   - Tabs: Overview, Tickets, Tests, Runs, Docs, Config
   - **Overview**: Project.md rendered; recent activity timeline; heatmap (§7.4)
   - **Tickets**: kanban with columns Pending Confirmation / In Progress / Needs Human Review (PR ready) / Closed. Click ticket → detail view with reproducing test, code pointers, confidence, actions.
   - **Tests**: table from `test-status.yaml`; filter by status; click test → run history.
   - **Runs**: every checkup/commit-trigger/manual-run as a row; click → live or replayed log.
   - **Docs**: preview of `docs/` and `wiki/` side-by-side; "regenerate all" button (triggers HITL confirmation).
   - **Config**: model per subagent; `max_fix_attempts`; `max_questions_per_attempt`; scheduler cadence; watcher glob patterns; autonomy mode toggle (§7.5).
3. **Live agent view** — during any run, a pane showing:
   - Current active subagent with spinner
   - Streaming tool calls (Read, Write, Bash, Grep, etc.) with args and truncated results
   - Collapsible per-subagent sections
   - Cost meter (tokens and USD running total)
4. **Pending approvals panel** — always visible when approvals are pending (see §7.3 and §7.5)

### 7.3 Live observability depth (Q2.4 option d)

Four layers, all collapsible:

- **High-level status** (always visible): "Reviewer → QA → Coder (attempt 2/5)" with timings
- **Subagent summaries**: plain-English description of what each subagent did and decided
- **Tool-call log**: every Read/Grep/Write/Bash call with args and truncated results, correlated by `parent_tool_use_id` (captured via `pre_tool_use` + `post_tool_use` hooks, written to `tool_calls.jsonl` per run, streamed over WebSocket)
- **Raw reasoning stream** (off by default, toggleable): token-level streaming of the active subagent's output

The tool-call hook pattern is taken directly from Anthropic's `claude-agent-sdk-demos/research-agent/` example (see RESEARCH.md §2).

### 7.4 Dashboards & reports (Q7.1 picks)

Three visual reports, all on the Project Overview tab:

1. **Subagent token/cost breakdown per ticket** — stacked bar chart, one bar per ticket, segments colored by subagent (Reviewer/QA/Coder). Absolute cost in USD + token count. Sortable by cost.
2. **Bug-hunt heatmap of the codebase** — tree map of source files, tile area = lines of code, tile color = bugs-resolved count (heat scale). Click a tile → list of bugs that touched that file.
3. **Documentation completeness score over time** — line chart, x=date, y=score 0–100. Score = (documented endpoints / total endpoints) × 0.5 + (documented modules / total modules) × 0.5. Updated after every Reviewer doc run.

### 7.5 HITL approval surface (Q2.6 option c)

Two autonomy modes, toggleable per-project in Config:

**Default mode (strict HITL):**

Approvals required for:
- Confirming a QA-generated bug ticket
- Accepting a prepared PR
- The Reviewer regenerating the full `docs/` or `wiki/` tree

Approvals NOT required for (the loop runs autonomously):
- QA writing tests, QA running tests, QA rejecting Coder submissions
- Coder submitting fixes
- Reviewer updating Project.md

**Thought-process mode (toggle on):**

When enabled, the UI shows a live "agent thought process" pane during any run. Additional approval buttons appear inline ("Continue", "Skip this subagent's next action", "Pause") for any mutating tool call from any subagent. This is the "display AI agent's thought processes and actions in real time" requirement from Q5.2.

**Mechanism:**

Implemented via the Claude Agent SDK's `can_use_tool` callback on `ClaudeAgentOptions`. In default mode, `can_use_tool` auto-approves within the permission-rule bounds and posts to the UI event stream for display only. In thought-process mode, `can_use_tool` blocks on a WebSocket round-trip to the UI for explicit approval.

### 7.6 Project registration flow

1. User clicks "Add Project" → modal asks for a local absolute path
2. Backend validates: path exists, path is a git repo, path contains Python files (warn if no FastAPI detected by import-scan)
3. Reviewer agent runs initialization audit (§5.1) — UI shows live progress
4. On completion, project appears in the dashboard with health = pending first check

Projects are keyed by their canonical absolute path. Multiple projects supported. For the eval submission, ship 1–2 **synthetic FastAPI demo repos** in `eval-fixtures/` so reviewers can click-and-go without needing their own repo (see §10).

### 7.7 Replay and history (Q2.5)

Simplified per your answer: no side-by-side diffing across runs. Each run has a permalink showing:
- High-level description of what changed and why
- Tickets opened/closed
- Files touched
- Cost and duration

Historical runs live in SQLite, queryable from the Runs tab.

---

## 8. Triggers and scheduling

### 8.1 File watcher + commit trigger (Q3.1 (c): targeted tests)

Runs in the backend process via `watchfiles`. Watches the project root for changes in `src/**/*.py` and new commits on the current branch (polls `.git/HEAD` every 5s).

- Debounce: **500ms trailing-edge** for file saves
- Glob: `src/**/*.py`
- Ignores: `.git/`, `__pycache__/`, `.pytest_cache/`, `node_modules/`, `.venv/`, `.smrt/sandbox/`
- On trigger: Reviewer receives a diff-scoped test plan request; only entries related to changed files are generated/executed.

### 8.2 Periodic full checkup (Q3.1 (c): full audit)

APScheduler embedded in the FastAPI backend. Per-project configurable:
- Cadence: default daily 03:00 local time
- Full end-to-end Reviewer → QA run
- Any new failures become draft tickets (requires human confirmation)
- Results visible in the Runs tab

### 8.3 Budget guardrails

Each project has a configurable USD budget per run (default $1.50) and per day (default $10). When exceeded, the orchestrator halts and emits a `budget_exceeded` event. Resumable only by explicit human unblock.

---

## 9. Agentic implementation details (Claude Agent SDK)

### 9.1 Top-level orchestration

The backend has one **root agent** per concurrent project run. Defined in `backend/agents/root.py` using `ClaudeAgentOptions`:

```
from claude_agent_sdk import ClaudeAgentOptions, AgentDefinition, query, HookMatcher

options = ClaudeAgentOptions(
    system_prompt=<load backend/agents/prompts/reviewer.md>,
    model="opus-4.7",
    allowed_tools=["Agent", "Read", "Glob", "Grep", "Write", "Edit", "WebFetch", "WebSearch", "Bash", "TodoWrite", "AskUserQuestion"],
    disallowed_tools=["Bash(git commit:*)", "Bash(git push:*)", ...],
    permission_mode="default",
    can_use_tool=smrt_permission_handler,   # see §9.3
    hooks={
        "PreToolUse": [HookMatcher(matcher="Write|Edit", hooks=[write_audit_hook])],
        "PostToolUse": [HookMatcher(hooks=[log_tool_call_hook])],
        "PreCompact": [HookMatcher(hooks=[archive_transcript_hook])],
    },
    agents={
        "qa_agent": AgentDefinition(
            description="MUST BE USED to generate tests, run tests, and evaluate Coder submissions. Tests are hidden from Coder.",
            prompt=<load backend/agents/prompts/qa.md>,
            tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"],
            disallowedTools=["Bash(git push:*)", "Edit(src/**)", "Write(src/**)"],
            model="sonnet-4.6",
            permissionMode="acceptEdits",
        ),
        "coder_agent": AgentDefinition(
            description="MUST BE USED to implement bug fixes after QA has produced a behavioral description. Never sees tests.",
            prompt=<load backend/agents/prompts/coder.md>,
            tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash", "TodoWrite"],
            disallowedTools=["Read(tests/**)", "Write(tests/**)", "Edit(tests/**)", "Bash(pytest:*)", "Bash(docker:*)"],
            model="sonnet-4.6",
            permissionMode="acceptEdits",
        ),
    },
    setting_sources=["user", "project"],
    max_turns=50,
    mcp_servers={
        "smrt-sandbox": {"type": "sdk", ...},   # in-process MCP for Docker sandbox ops
        "smrt-project-registry": {"type": "sdk", ...},
    },
)
```

**Critical rule** (per Claude Agent SDK docs): subagents **cannot** spawn their own subagents. `Agent` is not in `qa_agent` or `coder_agent` tool lists. All coordination flows through the Reviewer.

### 9.2 Context isolation

Subagent context windows start fresh. The only channel from Reviewer to subagent is the Agent tool's prompt string. Pass context as explicit artifacts:

- To QA: the test plan entry JSON + `Project.md` + relevant slice of `bugs-resolved.jsonl` + `hot.md`
- To Coder: the bug ticket (with `reproducing_test` redacted) + `Project.md` + `hot.md` + source file paths it may touch

QA's return message to Reviewer is a structured JSON object (via SDK structured output):
```
{ "verdict": "accept" | "reject" | "fail_loop", "feedback": "...", "tests_broken": [...], "tests_fixed": [...] }
```

Coder's return message is a structured JSON object:
```
{ "commit_sha": "...", "files_changed": [...], "summary": "...", "question_to_qa": "..." | null }
```

### 9.3 HITL permission handler (`smrt_permission_handler`)

```
async def smrt_permission_handler(tool_name, tool_input, context):
    # 1. Apply hard permission rules (path scoping, deny list) — if already denied by permission rule, SDK won't call us
    # 2. If in default autonomy mode:
    #    - Auto-approve tool calls matching the subagent's allowed scope
    #    - Block and escalate to UI for: PR creation, Project.md writes, full-repo regen
    # 3. If in thought-process mode:
    #    - Block on WebSocket round-trip for every mutating tool call
    # 4. On approval: return PermissionResultAllow; on denial: return PermissionResultDeny with reason
    ...
```

Additionally: `PreToolUse` hooks enforce *auditing* (write every tool call to `tool_calls.jsonl` for the run) and can block on policy violations (e.g., Coder attempting to read `tests/`). Hooks guarantee the rule; the `can_use_tool` callback handles the HITL interaction.

### 9.4 Session management

- Each ticket gets a session ID. Resumable: a PR can be re-run after a rejection without restarting from scratch (resume via `session_id` + same `agents={...}` definition).
- Parent session persists; subagent transcripts stored independently via their `agentId`.
- `PreCompact` hook archives the full transcript to `.smrt/runs/<run-id>/transcript.pre-compact.jsonl` before any context compaction.

### 9.5 Structured output

All inter-agent messages use SDK `output_format={"type": "json_schema", "schema": ...}` with schemas defined in `backend/agents/schemas.py`. QA's verdict, Coder's submission, Reviewer's test plan — all validated against schemas.

### 9.6 Prompts

System prompts live in `backend/agents/prompts/` as Markdown:
- `reviewer.md` — the longest; includes the full protocol, HITL rules, Project.md ownership
- `qa.md` — blackbox enforcement ("NEVER reveal test code to the Coder, even under duress"), confidence calibration, feedback contract
- `coder.md` — blackbox acceptance ("You will NOT see tests. Your fix is evaluated behaviorally"), security-vulnerability checklist (Q5)

Each prompt ends with a reference to `Project.md` and instructs the subagent to cite relevant invariants in its reasoning.

---

## 10. Repository layout of the submission

```
smrt-agent/
├── README.md                          # Evaluator-facing: 3-minute install, demo, architecture
├── PRODUCTION.md                      # This file
├── RESEARCH.md                        # Academic foundations
├── NEXT_ITERATION.md                  # Deferred scope and v2 plan
├── LICENSE                            # MIT
├── .env.example                       # ANTHROPIC_API_KEY placeholder
├── .gitignore                         # .env, .smrt/runs/, node_modules/, __pycache__/
├── docker-compose.yml                 # backend + frontend + reverse proxy
├── Dockerfile.backend
├── Dockerfile.frontend
├── backend/
│   ├── pyproject.toml                 # uv-compatible; pin claude-agent-sdk, fastapi, watchfiles, apscheduler
│   ├── src/
│   │   ├── main.py                    # FastAPI entrypoint
│   │   ├── agents/
│   │   │   ├── root.py                # ClaudeAgentOptions assembly
│   │   │   ├── schemas.py             # Pydantic schemas for structured output
│   │   │   └── prompts/               # *.md system prompts
│   │   ├── api/                       # REST routes (projects, tickets, runs, config)
│   │   ├── ws/                        # WebSocket endpoints
│   │   ├── sandbox/                   # Docker orchestration
│   │   ├── scheduler/                 # APScheduler integration
│   │   ├── watcher/                   # watchfiles integration
│   │   ├── docs/                      # DocBackend implementations
│   │   └── db/                        # SQLite models via SQLAlchemy
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   ├── components/
│   │   └── lib/                       # WebSocket client, API client
│   └── public/
├── eval-fixtures/
│   ├── README.md                      # describes the bundled demo repos
│   ├── todo-api/                      # synthetic buggy FastAPI app #1 (~5 intentional bugs) — ONLY fixture in v1
│   └── wild/                          # empty in v1; users clone real-world FastAPI repos here for soak testing
│       └── README.md                  # links to recommended public FastAPI repos
├── docs/
│   ├── architecture.md                # high-level diagram + prose
│   ├── agent-design.md                # detailed look at each subagent
│   ├── hitl-contract.md               # exactly what approvals exist and why
│   └── evaluation-rubric-mapping.md   # explicitly maps features to the SMRT rubric
└── bin/
    ├── smrt-exec.py                   # cross-platform hardened Docker exec wrapper (§3.3) — replaces .sh from earlier draft
    └── setup-vault.py                 # Obsidian vault initializer (cross-platform port of the claude-obsidian script)
```

**`eval-fixtures/`** ships two deliberately-buggy FastAPI apps so evaluators can run `smrt-agent` end-to-end without pointing it at their private repo first. Include at minimum:
- One silent-logical bug (response_model missing → sensitive-field leak)
- One async-pattern bug (forgot `await` on a coroutine)
- One auth-logic bug (authorization check in wrong order)
- One input-validation bug (Pydantic field with insufficient constraint)
- One state-mutation bug (race in a counter-increment endpoint)

This lets us demonstrate the "especially logical bugs that a standard linter might miss" differentiator without depending on the evaluator's setup.

---

## 11. Secrets, privacy, and responsible deployment

- All secrets read from environment or `.env` (gitignored). Supply `.env.example`.
- The only required secret is `ANTHROPIC_API_KEY`.
- **Cross-platform support is a v1 requirement.** Windows 10+, macOS 12+, and Linux are all supported. Windows requires Docker Desktop with the WSL2 backend. The previous draft's bash `bin/smrt-exec.sh` is replaced by a cross-platform Python wrapper at `bin/smrt-exec.py` (uses the `docker` Python SDK; no shell dependency). Path normalization happens at the project-registration boundary so all internal logic uses `pathlib.PurePosixPath` regardless of host OS.
- No telemetry leaves the user's machine. All run data lives in local SQLite + file system.
- Docker sandbox containers have no internet access (§3.3). This prevents the target repo's code from exfiltrating anything even if it tries.
- The agent is explicitly prompt-engineered to refuse any tool call that reads or writes outside the registered project path + `.smrt/**`.
- `tool_calls.jsonl` may contain code snippets; gitignored by default but surfaced in the UI.
- On project deregistration, optionally run `smrt-agent scrub --project-id <id>` to delete all SQLite rows and `.smrt/runs/` data for that project.

---

## 12. Evaluation rubric mapping

The SMRT task rubric has four judgments. This section is mirrored in `docs/evaluation-rubric-mapping.md` for the evaluators.

1. **AI Orchestration** — multi-agent hierarchy with strict blackbox between QA and Coder; context isolation via SDK subagents; structured JSON handoffs; budget guardrails. Grounded in Agentless (phased pipeline), OpenHands (`AgentDelegateAction` isolation), and Anthropic's own multi-agent research post.
2. **Attention to Detail (logical bugs)** — three-strategy logical-bug engine (mutation, property-based, differential-vs-history) driven by test-status memory. Grounded in Meta ACH (mutation-guided) and CoverUp (coverage-directed iteration).
3. **Communication & Critical Thinking (when to ask)** — explicit HITL surface with two fixed human decisions (ticket confirm, PR accept) plus thought-process mode. Grounded in Ask-or-Assume's uncertainty-gated scaffold.
4. **Bonus (visual reports, performance)** — three dashboards (§7.4), Obsidian vault with Bases/Dataview dashboards, Explain mode (Q7.2b), skill acquisition via Project.md (Q7.2d).

---

## 13. Implementation milestones

Build in this order. Each milestone should produce a runnable artifact before moving on.

**M1 — Sandbox + Basic Orchestration** (foundation)
- Docker sandbox lifecycle working end-to-end with a demo FastAPI app
- Claude Agent SDK plumbing: Reviewer + QA + Coder skeletons with structured handoffs
- Run a hand-crafted test plan entry through QA against the sandbox and get a verdict
- Minimum-viable web UI shows a registered project and runs a hand-crafted test plan via a button. **No CLI surface in v1** — the web UI is the sole entry point from day one.

**M2 — Full QA↔Coder Loop** (core functionality)
- End-to-end: human ticket → Coder fix → QA feedback → Coder resubmit → accept
- Blackbox enforced by permission rules (verify with deliberate escape attempts)
- Failure report on cap hit
- UI ticket-creation form and live verdict log added in this milestone

**M3 — Reviewer/Orchestrator + Project.md** (intelligence)
- Initialization audit builds Project.md for a fresh repo
- Periodic checkup produces test plan from first principles
- Commit-triggered targeted checks
- Project.md updates on rejection/acceptance

**M4 — Full Web UI + HITL** (observability)
- Builds out the minimum-viable UI from M1 into the full screens specified in §7.2
- React app with Projects / Project Detail / Live Agent View / Pending Approvals
- WebSocket streaming of tool calls correlated by `parent_tool_use_id`
- HITL approvals route through `can_use_tool` (default mode + thought-process mode toggle)

**M5 — Documentation System** (polish)
- DocBackend with GitHub and Obsidian implementations
- Auto-regeneration on code change
- Bases/Dataview dashboards scaffolded

**M6 — Over-Deliverers** (differentiation)
- Three dashboards (cost, heatmap, doc-completeness)
- Explain mode with provenance trailers
- Thought-process mode
- Skill acquisition validation: run the loop 5x on the same demo repo and show `Project.md` growing

**M7 — Submission Polish**
- Two eval-fixture FastAPI apps committed
- Evaluator README with 3-minute demo path
- Rubric mapping doc
- Final pass on .env.example, secrets, `docker-compose up` smoke test

---

## 14. Known open questions and caveats

Flagged honestly for the evaluator:

1. **No peer-reviewed pipeline specifically for FastAPI LLM test generation** — the design composes CoverUp (Python/pytest), Meta Assured-LLM (filter chain), and OpenAPI-derived inputs. This composition is a design decision, not a citation.
2. **Multi-agent cost** — ~4× single-agent tokens per Anthropic's own multi-agent post. Mitigated by budget guardrails + Haiku fallback consideration in v2.
3. **Uncertainty calibration for HITL** — Ask-or-Assume (March 2026) is a pre-print. The mechanism (can_use_tool + AskUserQuestion) is sound; the calibration is future work.
4. **v1 does not push to GitHub** — PR acceptance merges locally only. GitHub API push is in NEXT_ITERATION.md.
5. **v1 does not support remote repos** — project path must be local. Remote clone support in v2.
6. **Sonnet 4.6 for Coder may underperform on dense bugs** — escalation pattern to Opus 4.7 after 3 failed attempts is a v2 feature.
7. **Bases plugin requires Obsidian ≥ v1.9.10** — legacy Dataview dashboard provided as fallback.
8. **v1 ships one synthetic eval fixture (`todo-api`); the second (`bookstore-api`) is deferred to v2.** Single fixture is sufficient for known-answer benchmarking during development. Users who want soak-test material can clone real-world public FastAPI repos into `eval-fixtures/wild/` (see `eval-fixtures/wild/README.md` for recommendations); a one-click fixture loader is tracked in `NEXT_ITERATION.md` §5.6.

---

## 15. Definition of done

This iteration is shippable when:

- [ ] `docker-compose up` brings up backend + frontend without manual config beyond `.env`
- [ ] The two eval fixtures can be registered via the UI
- [ ] Periodic checkup produces a test plan and at least one valid bug ticket on a fixture
- [ ] Human confirms a ticket, Coder fixes it, QA accepts, PR is surfaced in the UI, human accepts, Project.md updates
- [ ] Tool calls stream live in the UI for the full run
- [ ] `docs/` and `wiki/` are both generated and kept in sync on PR acceptance
- [ ] Blackbox invariant is automatically verified by a self-test: Coder attempts to read `tests/`, permission denies, attempt is logged
- [ ] `max_fix_attempts` and `max_questions_per_attempt` are user-configurable in the UI and take effect immediately
- [ ] Three dashboards render with real data from a completed run
- [ ] Rejection reason on a PR produces a visible update to Project.md's Lessons section
- [ ] `README.md` contains a ≤3-minute demo path an evaluator can follow
