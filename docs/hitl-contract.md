# HITL Contract

SMRT Agent requires exactly two human decisions per bug fix. Everything else runs
autonomously. This document states precisely when approvals fire, what happens on each
path, and how thought-process mode changes the surface.

---

## Two Mandatory Approvals

### 1. Bug Confirmation

**When**: after QA generates a bug ticket (confidence ≥ 0.6) and before the Coder starts
work.

**Mechanism**: the orchestrator (`agents/orchestrator.py`) emits a `hitl_request` SSE
event containing the `session_id` and `ticket_id`, then awaits an `asyncio.Event` with a
1-hour timeout. The frontend (`components/QASessionView.tsx`) renders Approve and Skip
buttons while `status === "hitl_waiting"`.

**Endpoints**:
- `POST /projects/{id}/qa-sessions/{session_id}/approve` — sets decision to `"approve"`, unblocks the loop
- `POST /projects/{id}/qa-sessions/{session_id}/skip` — sets decision to `"skip"`, terminates session

**What the human sees**: the ticket file contents (title, description, observed vs expected
behavior, code pointers, QA confidence score). The reproducing test path is listed but the
test code is not shown.

### 2. PR Acceptance

**When**: after QA certifies a fix (pytest passes after a Coder submission).

**Mechanism**: the orchestrator returns `"done"` status; the Reviewer composes a PR
summary and commits the fix on `smrt/fix/<ticket-id>-<slug>`. The UI shows the pending PR
in the Tickets panel with an Accept button.

**What the human sees**: plain-English PR summary, branch name, files changed, and the
diff. No test code is included in the PR view (blackbox preserved for audit).

---

## What Runs Autonomously

No human approval is needed for:

- QA writing pytest files to `.smrt/tests/`
- QA running pytest inside the sandbox
- QA rejecting a Coder submission and sending behavioral feedback
- Coder reading `src/**` and editing source files
- Coder asking its one optional question per fix attempt
- Reviewer updating `.smrt/Project.md` after acceptance or rejection
- Reviewer regenerating `docs/` and `wiki/` after a merged change
- The nightly APScheduler trigger starting a new QA session

---

## Thought-Process Mode

**What changes**: when enabled, the frontend receives live streaming of each agent's text
output (the `text_delta` / `qa_text_delta` / `coder_text_delta` SSE events that are
already emitted). Additionally, every mutating tool call (`write_file`, `write_test_file`,
`write_source_file`) triggers an inline approval gate rather than auto-proceeding.

**How to enable**: toggle "Thought-process mode" in the Config section of the Project
Detail page (stored per project in the backend settings).

**Inline buttons during thought-process mode**:
- **Continue** — allow the pending mutating tool call to proceed
- **Skip** — deny the specific tool call; agent receives a denial result and continues
- **Pause** — suspend the entire session; human can resume later via the Run History panel

**Implementation**: the `can_use_tool` permission callback in the orchestrator checks the
current autonomy mode. In default mode it auto-approves within permission-rule bounds. In
thought-process mode it blocks on a WebSocket round-trip to the UI before returning
`PermissionResultAllow` or `PermissionResultDeny`.

---

## Rejection Flows

### Human rejects a PR (fix acceptance)

1. Human clicks Reject and provides a free-text reason in the UI.
2. The reason is stored to `.smrt/knowledge/rejections.jsonl` for audit.
3. The Reviewer agent receives the reason and asks itself what about the repository it
   misunderstood that led to the rejection.
4. The Reviewer appends a new entry to the `## Lessons` section of `.smrt/Project.md`
   (date-stamped, one-line summary + interpretation).
5. The ticket status returns to "In Progress"; the next QA session will use the updated
   `Project.md` context.

### Human rejects a bug ticket (false positive)

1. Human clicks "Reject as false positive" on a pending ticket with an optional reason.
2. The reason is stored to `.smrt/knowledge/mistakes-pending.jsonl`.
3. The Reviewer interprets the rejection as an invariant update (e.g., _"this field is
   intentionally present in the response for internal clients"_) and updates
   `Project.md`'s `## Architecture invariants` or `## Known sharp edges` section.
4. The ticket is closed; `test-status.md` marks the associated test as suppressed so it
   is not promoted to future checkups.

---

## Max Fix Attempts Exceeded

**Default cap**: `max_fix_attempts = 5` (env `SMRT_MAX_FIX_ATTEMPTS`, configurable in UI).

When the Coder fails to produce a passing fix within the cap:

1. **QA composes a failure report** containing: bug restated, per-attempt summary (what
   changed, what still failed), and theories about why the fix kept missing the mark.
2. **Reviewer reads the QA report** and the Coder's edit history, then writes a
   human-facing final report to `.smrt/reports/<ticket-id>.md`. The hidden test code is
   not included in this report.
3. The ticket status is set to "Failed" in the UI with a "Read report" action.
4. The human can: escalate to a developer, split the ticket, or close it as out-of-scope.
5. If the human chooses to escalate, the reason and report path are appended to
   `Project.md`'s `## Known sharp edges` so future agents do not attempt the same fix
   strategy.
