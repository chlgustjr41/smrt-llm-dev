# Agent Design

## Reviewer (claude-opus-4-7)

The Reviewer is the root agent and the only agent that reasons over the whole codebase.
It also acts as Orchestrator and Documenter — these are roles, not separate processes.

**Responsibilities**

- **Init audit**: walks `src/**` AST, reads `README.md` and existing docs, fetches
  `/openapi.json` from the running sandbox, writes the initial `.smrt/Project.md`, and
  seeds `docs/` and `wiki/` via `DocBackend`.
- **Periodic checkup** (scheduler or commit trigger): re-reads recent commits and changed
  files, produces a structured test plan (`.smrt/test-plan.yaml`), delegates to QA.
- **Doc maintenance**: after every accepted PR, calls `GitHubBackend` and
  `ObsidianBackend` to upsert affected endpoint and module docs.
- **Project.md ownership**: the only agent permitted to write `.smrt/Project.md`. Updates
  it after human PR acceptance, PR rejection (lessons), or false-positive ticket rejection.

**Tools** (defined in `agents/reviewer/budget.py`)

`list_files`, `read_file`, `fetch_url`, `write_file` — `write_file` is restricted to
paths starting with `.smrt/`.

**Model**: `claude-opus-4-7` (env `SMRT_MODEL_REVIEWER`). Configurable per project.

**Permission mode**: default. The `can_use_tool` callback in `orchestrator.py` gates writes
to `Project.md`, `docs/`, and `wiki/` in thought-process mode.

---

## QA Agent (claude-sonnet-4-6)

The QA agent owns tests and enforces the blackbox boundary with the Coder.

**Responsibilities**

- Convert test-plan entries into executable pytest tests written to `.smrt/tests/`.
- Run pytest inside the Docker sandbox; evaluate results.
- When a test fails and confidence ≥ 0.6 (configurable), call `write_bug_ticket` to
  produce a `.smrt/tickets/YYYY-MM-DD-NNN.md` file and emit a `hitl_request` event.
- During the QA↔Coder loop: re-run the hidden test after each Coder submission; return a
  structured verdict (`done` / `error`) — behavioral description only, never test code.
- Append resolved bugs to `.smrt/bugs-resolved.md` via `append_bugs_resolved`.
- Update `.smrt/test-status.md` to record run history and promotion state.

**Three test strategies** (driven by test-plan `category` field)

| Category | Strategy |
|---|---|
| `static` | Conventional assertion-style pytest |
| `logical` | Hypothesis property tests + specific corner-case assertions; mutation-guided (mutmut/cosmic-ray surviving mutants become new tests) |
| `security` | Both above + negative-auth and authz variants |

**Test-status promotion logic** — tests with > 10 consecutive passes are promoted to weekly
sampling; any red test is promoted to every checkup. Tracked in `.smrt/test-status.md`.

**Blackbox enforcement** — QA never exposes test file paths, assertion values, or test code
to the Coder. This is enforced at the tool level: `write_test_file` writes only to
`.smrt/tests/`; the Coder's tool list has no `read_source_file` for that directory.
Behavioral feedback examples:

- Allowed: _"The endpoint still returns 200 with the password hash present in the response."_
- Blocked: _"Your test expects the response to not contain 'hashed_password'."_

**Tools** (defined in `agents/qa/budget.py`)

`list_files`, `read_file`, `write_test_file`, `run_pytest`, `write_bug_ticket`,
`write_test_status`, `append_bugs_resolved`.

**Model**: `claude-sonnet-4-6` (env `SMRT_MODEL_QA`).

---

## Coder Agent (claude-sonnet-4-6)

The Coder implements fixes without ever seeing test code.

**Responsibilities**

- Receive a bug ticket with the `reproducing_test` field replaced with
  `<redacted: QA will run the hidden test>`.
- Read `src/**` freely; implement a fix.
- Submit the fix (source edits) back to the orchestrator.
- On rejection: receive QA's behavioral feedback; optionally use one allowed question
  per attempt (QA answers descriptively, never with code).
- Never reads `.smrt/tests/`, never runs pytest directly.

**Branch naming**: `smrt/fix/<ticket-id>-<slug>` (managed via `Bash(git:*)` on the target
repo).

**Tools** (defined in `agents/coder/budget.py`)

`list_files`, `read_source_file`, `write_source_file`. Explicit deny: anything touching
`tests/**`, `.smrt/**`, `docs/**`, `wiki/**`.

**Model**: `claude-sonnet-4-6` (env `SMRT_MODEL_CODER`).

**Hard cap**: `max_fix_attempts` (default 5, `SMRT_MAX_FIX_ATTEMPTS`). When exceeded,
QA composes a failure report; Reviewer converts it to a human-facing report at
`.smrt/reports/<ticket-id>.md`. The UI surfaces it as a failed ticket with "Read report".

---

## Orchestrator (`agents/orchestrator.py`)

`run_qa_session()` is the coordination function called by `api/qa_sessions.py`.

**Loop sequence**

1. Call `run_qa_agent()` — QA inspects the project and either returns `None` (all passing)
   or a `ticket_id`.
2. Emit `hitl_request` event → put session into `hitl_waiting` state.
3. Await `asyncio.Event` (1-hour timeout) for human approve/skip decision.
4. On **approve**: read ticket file, run current pytest baseline, call `run_coder_agent()`
   with redacted ticket content.
5. Re-run pytest; if passing → `done`. If still failing and attempts remain → repeat from
   step 1 with prior-fix context injected into QA prompt.
6. On cap hit → return `"error"`.

**Context isolation** — each subagent runs a fresh `anthropic.Anthropic` streaming loop.
The only context passed between agents is explicit:

- To QA: `.smrt/Project.md` content + prior fix output.
- To Coder: ticket markdown (redacted) + current pytest output.

**Structured JSON handoffs** — QA verdict arrives as the `ticket_id` return value plus
session-status events (`done`/`error`). Coder submission is implicit: the orchestrator
re-runs pytest to verify, rather than trusting a Coder-reported result.

**Budget guardrails** — each agent loop tracks cumulative `(input_tokens, output_tokens)`,
calls `compute_cost_usd()`, and emits `budget_exceeded` if the per-agent share is hit.
The per-agent share is `budget_per_run_usd / (max_fix_attempts * 2 + 1)`. Default:
$1.50/run, $10/day (env `SMRT_BUDGET_PER_RUN_USD`, `SMRT_BUDGET_PER_DAY_USD`). On
`budget_exceeded`, the orchestrator halts and the UI surfaces the event.
