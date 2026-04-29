# Agent Design

## Reviewer

The Reviewer is the root agent — the only agent that reasons over the whole codebase
AND the documentation tree. It plays two distinct roles:

1. **Init Audit** (per-run, one-shot): inspect the codebase and produce/refresh the
   knowledge artifacts.
2. **Final Summary** (per-ticket, end-of-loop): write the third-perspective Fix
   Summary AND propose any documentation updates the fix necessitates.

**Init Audit responsibilities**

- Walks `src/**`, reads relevant entry points and routers, optionally fetches
  `/openapi.json` from the running sandbox, writes the initial `.smrt/Project.md`.
- **When the user enables doc generation** (the "📝 Generate docs" toggle on the
  Init Audit button), the Reviewer also: reads any existing `README.md`, calls
  `write_readme` if missing or sparse, calls `write_docs_file` for at least
  `docs/architecture.md` plus per-module docs under `docs/modules/`. Doc tools are
  hidden from the model entirely on no-docs runs so it can't accidentally write
  docs against the user's wishes.
- Seeds Obsidian-friendly stubs under `docs/api/` and `docs/modules/` via the
  post-run `generate_docs()` pass (also gated by the same toggle).

**Final Summary responsibilities** (`_get_reviewer_final_summary` in
`agents/orchestrator.py`)

- Runs at the **terminal** of every QA-Coder loop — success, CASE A, CASE C, and
  loop_exhausted paths all flow through it.
- Reads the agent log (`_summarize_coder_evidence`) to know what the Coder
  actually did — files edited, total edit count, and the Coder's final reasoning
  text. Without this evidence the Reviewer would confabulate fixes that never
  happened (e.g. when pytest passes because the bug was already fixed).
- Pre-loads existing project docs (`_collect_existing_docs`): Project.md (full),
  README.md (head + tail capped), and an index of `docs/*.md` files (per-file
  head capped, ~12 KB total budget) so it can identify which docs the fix
  invalidates.
- Produces a markdown narrative (the Fix Summary headline) AND a structured
  `[DOC_UPDATES_JSON]` block listing proposed doc updates. The narrative streams
  via `reviewer_text_delta` events; the JSON block is parsed off the response.
- Both outputs are persisted into `.smrt/fix-summaries/<session_id>.json` so
  they survive event-log rotation. The proposed updates apply to disk when the
  user accepts the ticket from Needs Review.

**Tools** (defined in `agents/reviewer/budget.py` — `TOOL_DEFINITIONS` plus
optional `DOC_TOOL_DEFINITIONS`)

| Tool | Purpose | Path policy |
|---|---|---|
| `list_files` | Survey the project tree | respects `.gitignore` and `.agentignore` |
| `read_file` | Read source/docs | denies secrets and traversal |
| `fetch_url` | Hit `/openapi.json` from sandbox | sandbox container IPs only in practice |
| `write_file` | Write knowledge artifacts | restricted to `.smrt/` |
| `write_readme` | Create/refresh top-level README | only when doc-generation enabled |
| `write_docs_file` | Write technical docs | `docs/<...>.md` only; rejects non-`.md`; blocks traversal |

**Model**: `SMRT_MODEL_REVIEWER` (default `claude-haiku-4-5-20251001`). The
per-project Config tab can override this.

---

## QA Agent

The QA agent owns tests and enforces the blackbox boundary with the Coder. It plays
**two distinct roles** within the loop:

1. **QA Discovery agent** — runs at the start of a QA Session (Find Bugs button).
   Inspects the project, writes pytest tests under `.smrt/tests/`, runs them, files
   one bug ticket per distinct failure pattern via `write_bug_ticket`.
2. **QA Advisor** (`_get_qa_feedback` in `agents/orchestrator.py`) — runs after
   *every* failed Coder attempt. Returns one of three structured verdicts:

   | Verdict | Signal token | Loop effect |
   |---|---|---|
   | **CASE A — fix is correct** (failures unrelated to bug) | `[QA_SATISFIED]` | Loop ends as success → PR ready |
   | **CASE B — fix is wrong, bug is real** | _(no token)_ | Numbered feedback appended to ticket; next attempt fires |
   | **CASE C — generated test itself is faulty** | `[QA_TEST_FAULTY]` | Loop halts → routes to Needs Review with test-update proposal |

   The QA Advisor sees the per-attempt loop budget in its prompt (`attempt N of M`)
   so it knows when it's the last chance. CASE A and CASE C exit the loop early;
   CASE B keeps it running. The numbered feedback (`## QA feedback after attempt N
   of M`) gives the next Coder attempt a chronological log to learn from.

**Other responsibilities**

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

## Coder Agent

The Coder implements fixes without ever seeing test code.

**Responsibilities**

- Receive a bug ticket; on attempts 2+, the ticket carries appended
  `## QA feedback after attempt N of M` blocks from previous iterations.
- Receive its **loop budget** in the task message: "Fix attempt N of M — K
  attempts remain after this one." On the last attempt the prompt warns: "This is
  your LAST attempt. If it fails the ticket is escalated to human review, so
  prioritize correctness over speed."
- Read `src/**` freely; implement a fix.
- On attempts 2+: instructed to NOT repeat the approach that previously failed —
  the prior QA feedback in the ticket spells out what was wrong.
- Optionally call `ask_qa` up to `max_questions_per_attempt` times to ask QA a
  one-shot clarifying question. The counter resets each attempt and the
  remaining budget is included in each answer ("3 questions remaining").
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

Two coordination functions:

- `run_qa_session()` — QA Discovery pass that files tickets (called from
  `api/qa_sessions.py`).
- `run_ticket_fix_session()` — the per-ticket Coder→QA-Verify→Reviewer-Summary
  loop (called from `api/tickets.py` when a ticket is dragged to In Progress).

**`run_ticket_fix_session` loop sequence**

1. **Coder phase**: emit `coder_running` status, run pre-coder pytest, call
   `run_coder_agent()` with the ticket (and any accumulated QA feedback from
   prior attempts), passing `attempt_index` + `max_fix_attempts` so the Coder
   knows where it is.
2. **QA Verify phase**: emit `qa_checking`, run pytest. If green → success path
   (skip to step 5).
3. **QA Advisor phase** (`_get_qa_feedback`): emit `qa_advising`, classify the
   failure as CASE A / B / C. CASE A jumps to step 5 (success). CASE C jumps to
   step 6 (test_faulty exhaustion). CASE B appends numbered feedback to the
   ticket and loops back to step 1.
4. After `max_fix_attempts`: heuristic `_analyze_fix_failure` produces a
   `needs_more_attempts` or `possibly_not_a_bug` recommendation; jump to step 6.
5. **Success terminal** — record `pending-prs.jsonl` entry, run
   `_get_reviewer_final_summary`, emit `done`. Return "done".
6. **Failure terminal** — record `failed-fixes.jsonl` entry, run
   `_get_reviewer_final_summary`, emit `loop_exhausted`. Return "loop_exhausted".

**Reviewer Final Summary pass** (always runs at the terminal — both 5 and 6)

The Reviewer (third agent) writes the compiled Fix Summary using:
- The Coder's verified actions from the agent log (`_summarize_coder_evidence`)
- The existing project docs snapshot (`_collect_existing_docs`)
- The bug ticket and final pytest output

It outputs both a markdown narrative AND a `[DOC_UPDATES_JSON]` block listing
proposed doc updates. Both are persisted into `.smrt/fix-summaries/<sid>.json`.
Proposed updates apply to disk when the user accepts the ticket (`api/pr.py
::accept_pr → _apply_proposed_doc_updates`).

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
