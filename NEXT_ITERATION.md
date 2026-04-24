# NEXT_ITERATION.md — SMRT Agent v2 Backlog

**Purpose.** This document tracks every feature, capability, or hardening item that was *explicitly deferred* from v1 (see `PRODUCTION.md`) and should be revisited in the next iteration. Each entry includes rationale for deferral, an acceptance sketch for v2, and any blocking dependencies.

When starting the v2 planning conversation, this file should be consumed in full and each item either (a) promoted into `PRODUCTION.md`, (b) re-deferred with updated rationale, or (c) closed as won't-fix.

**Structure of each entry:**
- **Area** — which part of the system it affects
- **What** — one sentence describing the feature
- **Why v1 deferred** — the honest reason
- **v2 acceptance sketch** — what "done" looks like
- **Dependencies** — what must exist before this can be built
- **Priority** — HIGH (ship early in v2) / MEDIUM (ship within v2) / LOW (v2+)

---

## Tier 1: Features promised as "next iteration" during v1 planning

### 1.1 Real GitHub integration for PR push
- **Area:** git / version control
- **What:** The "Accept PR" button in the UI should actually push the agent's branch to GitHub and open a real PR via the GitHub REST API, not just merge locally.
- **Why v1 deferred:** Adds OAuth/PAT management, GitHub App setup, and webhook handling — all surface that distracts from the core orchestration story in the hiring eval. Local-merge-only is sufficient to demonstrate the loop.
- **v2 acceptance sketch:**
  - Per-project config field for GitHub repo URL + PAT (encrypted at rest via OS keyring or libsodium-sealed secret)
  - On PR accept, push the `smrt/fix/<ticket-id>-<slug>` branch and POST to `/repos/{owner}/{repo}/pulls`
  - UI shows the real PR URL once created
  - Support GitHub App installation as an alternative to PATs (better for team use)
- **Dependencies:** secrets handling layer; retry + rate-limit logic for the GitHub API.
- **Priority:** HIGH

### 1.2 Past-ticket similarity linking during ticket creation
- **Area:** memory / QA
- **What:** When QA generates a new bug ticket, automatically search `bugs-resolved.jsonl` for semantically similar past tickets and link them in the new ticket's "related" field.
- **Why v1 deferred:** Nice-to-have; the raw JSONL memory is already searchable ad-hoc and the first iteration of the eval repo won't have much resolved history to draw on.
- **v2 acceptance sketch:**
  - Embedding-based similarity over the title + summary of each bug (use a local model or Anthropic embeddings)
  - Top-3 similar past bugs shown inline in the ticket detail UI
  - "This looks like BUG-0017, which was fixed by X" surfaced to the human during confirmation
  - Also surface to the Coder in its prompt — "this may be the same root cause as BUG-0017"
- **Dependencies:** embeddings pipeline; a lightweight vector store (in-memory FAISS or sqlite-vss is enough).
- **Priority:** MEDIUM

### 1.3 Jira backend (real implementation)
- **Area:** documentation backends
- **What:** Replace the `JiraBackend.upsert_*` `NotImplementedError` stubs with a real Jira Cloud REST API implementation that creates Jira pages from agent-generated docs.
- **Why v1 deferred:** Credentials management for Jira, tenant-specific quirks, and the primary eval doesn't require it.
- **v2 acceptance sketch:**
  - Per-project Jira config (host, project key, API token)
  - Endpoint docs map to Jira pages under a configurable parent page
  - Decisions (ADRs) map to Confluence blog posts or standalone pages
  - One-way sync (agent → Jira); Jira → agent is out of scope
- **Dependencies:** 1.1 (shared secrets-handling layer).
- **Priority:** LOW

### 1.4 Confluence backend (real implementation)
- **Area:** documentation backends
- **What:** Same as Jira but for Confluence.
- **Why v1 deferred:** Same as Jira.
- **v2 acceptance sketch:** Parallel to Jira; may share auth config since both are Atlassian.
- **Dependencies:** 1.1.
- **Priority:** LOW

### 1.6 Second eval fixture (`bookstore-api`)
- **Area:** evaluation fixtures
- **What:** Ship the second deliberately-buggy FastAPI app referenced in `PRODUCTION.md` §10. Same five-bug taxonomy as `todo-api` but a different domain (bookstore catalog + checkout) so evaluators see the agent generalizing across schemas.
- **Why v1 deferred:** A single fixture is enough for known-answer benchmarking during development; building two takes ~2× the time without proving anything new at v1.
- **v2 acceptance sketch:**
  - `eval-fixtures/bookstore-api/` with ~150–200 LOC
  - Five planted bugs spanning the same categories (silent-logical, async, auth-order, input-validation, state-mutation)
  - `BUGS.md` documenting them, gitignored from agent reach
  - Both fixtures registerable side-by-side; cost dashboards compare them
- **Dependencies:** none.
- **Priority:** HIGH

### 1.5 Feature-implementation ticket type
- **Area:** ticket taxonomy
- **What:** Allow tickets of type `feature` (not just `bug`), where the human describes a small feature and the Coder implements it while QA writes tests for the new behavior.
- **Why v1 deferred:** The SMRT task explicitly scopes the agent to docs/tests/bugs. Expanding to features balloons scope and invites the evaluator to judge on feature-implementation quality, which isn't the core value proposition.
- **v2 acceptance sketch:**
  - New ticket category `feature` with fields for user-facing description and acceptance criteria
  - QA writes "specification tests" up front (test-driven), hands to Coder
  - Same blackbox loop, same caps
  - PR acceptance path identical to bug tickets
- **Dependencies:** robust QA test-writing (v1 is good enough).
- **Priority:** MEDIUM

---

## Tier 2: Hardening and evaluation-quality improvements

### 2.1 Opus escalation for stuck Coder
- **Area:** model routing
- **What:** After 2 failed Coder attempts, escalate the Coder model from Sonnet 4.6 to Opus 4.7 for the remaining attempts.
- **Why v1 deferred:** Adds complexity and cost unpredictability; keeping a single model per subagent is simpler to reason about.
- **v2 acceptance sketch:**
  - Config flag `coder_escalation_attempt` (default 3, disable with `null`)
  - UI shows which model produced each attempt
  - Cost breakdown distinguishes escalated vs non-escalated attempts
- **Dependencies:** none.
- **Priority:** MEDIUM

### 2.2 Pytest plugin for streaming QA observability
- **Area:** observability
- **What:** A pytest plugin that streams per-test progress and per-assertion outcomes to the backend WebSocket so the UI can show test-execution progress in real time.
- **Why v1 deferred:** Parsing pytest's stdout or JUnit XML is sufficient for v1; a native plugin is cleaner but not critical.
- **v2 acceptance sketch:**
  - `pytest-smrt` plugin installed in the sandbox container
  - Streams events over a WebSocket channel to the backend
  - UI shows a live "28 / 42 tests passed, currently running test_users.py::test_leak" progress bar
- **Dependencies:** none.
- **Priority:** LOW

### 2.3 Session-wide rate-limit backoff with cost-aware queueing
- **Area:** SDK integration
- **What:** When Anthropic rate-limits return 429, the orchestrator should suspend in-flight tickets to a queue, honor `retry-after`, and resume — currently v1 just halts.
- **Why v1 deferred:** Rate limits are unlikely during a single-user eval demo; queueing infra is heavy.
- **v2 acceptance sketch:**
  - Per-tier queue with priority by ticket age + severity
  - Transparent retry for ITPM/OTPM hits; hard stop only on persistent failures
  - Cost-aware: if a ticket's budget would be exceeded by a retry, escalate to human
- **Dependencies:** persistent task queue (Celery, Dramatiq, or APScheduler job-store).
- **Priority:** LOW

### 2.4 Multi-user auth and RBAC
- **Area:** deployment
- **What:** Login, team workspaces, role-based approvals (e.g., only a "lead" role can accept PRs).
- **Why v1 deferred:** Single-user local tool is sufficient for the eval.
- **v2 acceptance sketch:**
  - Email/password or OAuth (GitHub) login
  - Per-workspace project registry
  - RBAC: viewer, developer, lead
- **Dependencies:** HTTP session layer, persistent users table, secrets for OAuth.
- **Priority:** LOW

### 2.5 Remote repo support
- **Area:** project registration
- **What:** Register a project by GitHub URL instead of local path; the backend clones and keeps in sync.
- **Why v1 deferred:** Local-path-only keeps the mental model simple and dodges auth concerns.
- **v2 acceptance sketch:**
  - Register by URL
  - Background job keeps the local clone fresh (pulls on schedule)
  - Write-backs push to a dedicated fork or branch
- **Dependencies:** 1.1 (GitHub integration).
- **Priority:** MEDIUM

### 2.6 Postman collection generation from OpenAPI
- **Area:** QA / manual reproduction
- **What:** Auto-generate a Postman collection from the target app's `/openapi.json` so humans can manually exercise endpoints during bug confirmation.
- **Why v1 deferred:** The UI's "run the reproducing pytest" button is sufficient for v1; Postman adds a second surface.
- **v2 acceptance sketch:**
  - "Export Postman collection" button on the Project Detail → Tests tab
  - Pre-populated with sample payloads from test-plan entries
  - Optionally generates a Newman CLI invocation for CI
- **Dependencies:** none.
- **Priority:** LOW

---

## Tier 3: Learning system improvements

### 3.1 Cross-project learning (agent model distillation)
- **Area:** memory / skill acquisition
- **What:** Allow the agent to transfer patterns learned on one FastAPI project to another (shared bug-pattern library across projects, not just per-project Project.md).
- **Why v1 deferred:** Per-project learning is sufficient to demonstrate the skill-acquisition narrative; cross-project learning risks leaking project A's patterns into project B.
- **v2 acceptance sketch:**
  - Opt-in cross-project pattern library at `~/.smrt/global-patterns/`
  - Only abstract patterns (e.g., "missing_response_model → password leak") stored, never project-specific code
  - Reviewer consults global patterns during initialization audit
- **Dependencies:** a notion of "abstract bug pattern" distinct from a specific instance.
- **Priority:** MEDIUM

### 3.2 Agent self-evaluation report
- **Area:** learning
- **What:** Weekly self-eval where the Reviewer analyzes its own performance (accept rate, false-positive rate, average attempts per fix) and proposes prompt/config changes.
- **Why v1 deferred:** Sophisticated; better after v1's data accumulates.
- **v2 acceptance sketch:**
  - Weekly background job produces `.smrt/self-eval/<week>.md`
  - Surfaces in UI as a "How is the agent doing?" card
  - Proposes tuning suggestions (e.g., "QA's confidence threshold is too low — 40% of tickets rejected as false positive")
- **Dependencies:** enough accumulated runs per project (a few weeks minimum).
- **Priority:** MEDIUM

### 3.3 Mistake taxonomy with structured root causes
- **Area:** memory
- **What:** Move from free-text lessons in `Project.md` to a typed taxonomy of root causes (e.g., `SerializationLeak`, `AuthOrderError`, `AsyncMissing`) that can be queried and measured.
- **Why v1 deferred:** Premature taxonomy-building without enough data.
- **v2 acceptance sketch:**
  - Reviewer picks a root-cause tag from a curated list when updating Project.md
  - Dashboard shows most-common root causes per project and globally
  - QA uses the taxonomy to guide its test-strategy selection
- **Dependencies:** 3.1 (cross-project pattern concept).
- **Priority:** LOW

---

## Tier 4: Safety and robustness

### 4.1 Sandbox container escape hardening
- **Area:** security
- **What:** Beyond v1's network isolation + CPU/mem caps: run the sandbox under gVisor or Kata Containers for kernel-level isolation.
- **Why v1 deferred:** Docker isolation + no-network is adequate for the eval repo threat model; gVisor adds install complexity.
- **v2 acceptance sketch:**
  - Config flag `sandbox_runtime: docker | gvisor | kata`
  - Default stays Docker; opt-in for hardened modes
  - Document threat models for each
- **Dependencies:** none.
- **Priority:** MEDIUM

### 4.2 Prompt-injection defense in target repo content
- **Area:** security
- **What:** The target repo's code and comments are treated as untrusted data; explicit prompt-injection detection on any content the agents consume.
- **Why v1 deferred:** The Claude Agent SDK's existing hooks + the system-level rules in this runtime already provide baseline defense.
- **v2 acceptance sketch:**
  - PreToolUse hook scans Read results for injection patterns (e.g., "ignore previous instructions")
  - Flags are surfaced to the UI as warnings
  - Agent continues but annotates its output with a "potentially compromised source" marker
- **Dependencies:** classifier or heuristic pack.
- **Priority:** MEDIUM

### 4.3 Full audit log with tamper-evidence
- **Area:** auditability
- **What:** Every agent action, every human decision, every Project.md write is appended to a hash-chained audit log for post-hoc review.
- **Why v1 deferred:** SQLite + JSONL is good enough for v1.
- **v2 acceptance sketch:**
  - Append-only SQLite table with previous-row hash chain
  - Export to signed JSON bundle
  - UI shows the current head hash
- **Dependencies:** none.
- **Priority:** LOW

---

## Tier 5: UX and developer experience

### 5.1 Inline PR comments and iterative human feedback
- **Area:** UX / PR review
- **What:** Instead of binary accept/reject on a prepared PR, let humans leave inline comments on specific lines of the diff. Coder resumes with that feedback.
- **Why v1 deferred:** Significantly more complex than binary accept/reject; takes the PR out of blackbox territory (Coder sees human hints about the test).
- **v2 acceptance sketch:**
  - GitHub-style inline commenting on the PR diff view
  - Comments flow to a new QA↔Coder sub-loop
  - Careful: if the human's comment reveals test intent, the blackbox is compromised; rule options tbd
- **Dependencies:** thoughtful design for blackbox preservation.
- **Priority:** MEDIUM

### 5.2 Replay mode (time-travel debugger)
- **Area:** observability
- **What:** Scrub through any past agent run step-by-step, see state at each tool call, branch off a replay to try a different path.
- **Why v1 deferred:** High complexity; static run logs are sufficient for v1's "high-level description" requirement.
- **v2 acceptance sketch:**
  - Every tool call recorded with sufficient context to re-run
  - UI timeline slider
  - "Fork from here" button that creates a new session resumed at that tool call with different options
- **Dependencies:** full transcript preservation (v1 already does this via PreCompact hook).
- **Priority:** LOW

### 5.3 Counterfactual mode
- **Area:** observability
- **What:** "Show me what would happen if the agent ran with just the QA, not the Reviewer's test plan" — runs an alternate path in a shadow session and diffs outcomes.
- **Why v1 deferred:** Academically interesting, practically niche.
- **v2 acceptance sketch:**
  - UI "what if" panel on any run
  - Runs a shadow session with chosen config changes
  - Side-by-side outcome comparison
- **Dependencies:** 5.2 (replay infra).
- **Priority:** LOW

### 5.4 Slack / Discord notifications
- **Area:** notifications
- **What:** Push events (new ticket, PR ready, failure report) to Slack or Discord.
- **Why v1 deferred:** Local UI is sufficient; notification integrations are v2 polish.
- **v2 acceptance sketch:**
  - Webhook config per project
  - Event taxonomy with per-event opt-in
- **Dependencies:** none.
- **Priority:** LOW

### 5.6 Real-world fixture loader
- **Area:** UX / evaluation
- **What:** UI helper to clone recommended public FastAPI repos into `eval-fixtures/wild/` with one click (e.g., `tiangolo/full-stack-fastapi-template`, `nsidnev/fastapi-realworld-example-app`).
- **Why v1 deferred:** Users can `git clone` themselves into the placeholder directory; a UI helper is convenience polish.
- **v2 acceptance sketch:**
  - "Clone wild fixture" button on the Projects dashboard
  - Curated list of recommended FastAPI repos with size/complexity hints
  - Sandbox auto-detects the target's `requirements.txt` or `pyproject.toml` and builds the per-fixture Dockerfile
  - One-click "register this clone" once the clone completes
- **Dependencies:** none.
- **Priority:** LOW

### 5.5 Mobile-responsive UI
- **Area:** UX
- **What:** Make the UI usable on mobile for approval actions (confirm ticket, accept PR).
- **Why v1 deferred:** Desktop-first is fine for the eval.
- **v2 acceptance sketch:**
  - Responsive layout for screens ≥ 360px
  - Mobile push notification for pending approvals
- **Dependencies:** 5.4 (notifications).
- **Priority:** LOW

---

## Tier 6: Observability for the agent itself

### 6.1 Run cost forecasting
- **Area:** cost observability
- **What:** Before a checkup runs, predict its cost based on repo size and historical data; let human pre-approve the budget.
- **Why v1 deferred:** v1 has hard budget caps that halt runs; forecasting is optimization.
- **v2 acceptance sketch:**
  - Predicted cost shown on the Config → Scheduler tab
  - Prediction model: simple linear regression on (LOC, endpoints, historical cost)
  - Hard-stop if actual cost exceeds forecast by >50%
- **Dependencies:** accumulated run history.
- **Priority:** LOW

### 6.2 Trace export to OpenTelemetry
- **Area:** observability
- **What:** Emit OTel spans for agent runs so users can plug in their own observability stack.
- **Why v1 deferred:** WebSocket event stream is sufficient for the built-in UI.
- **v2 acceptance sketch:**
  - OTLP exporter configurable
  - Spans for: agent turn, tool call, subagent delegation, HITL wait
- **Dependencies:** none.
- **Priority:** LOW

---

## Tier 7: Research-backed improvements

### 7.1 Ask-or-Assume uncertainty calibration
- **Area:** HITL / agent behavior
- **What:** Formalize the orchestrator's "when to ask" decision using the UA-Multi pattern from Ask-or-Assume (arXiv 2603.26233). v1 uses hardcoded HITL gates; v2 uses prompt-elicited uncertainty.
- **Why v1 deferred:** Paper is pre-print (March 2026), uncertainty calibration is immature, and the hardcoded gates meet the task requirements.
- **v2 acceptance sketch:**
  - Reviewer includes a dedicated "Intent Agent" subagent that evaluates underspec in incoming tickets
  - Router transitions QA→Coder conditional on uncertainty signal
  - Compare against v1's hardcoded gates on eval fixtures; keep v1 behavior as fallback
- **Dependencies:** reproducible uncertainty elicitation prompts (see RESEARCH.md §1.4).
- **Priority:** MEDIUM

### 7.2 Full Meta ACH mutation-guided testing
- **Area:** QA logical-bug detection
- **What:** Implement the complete Assured LLM-based Coverage+Hunting pipeline from Meta's FSE Companion 2025 paper — concern-specific mutation, LLM-as-judge equivalence detection, kill-the-surviving-mutant test synthesis.
- **Why v1 deferred:** v1 implements the mutation strategy via off-the-shelf `mutmut`/`cosmic-ray`; the full ACH pipeline adds LLM-judge equivalence which is complex and its precision is limited (0.79 in the paper).
- **v2 acceptance sketch:**
  - Concern-specific mutation operators (e.g., "auth bypass" mutations, "validation skip" mutations)
  - LLM-judge equivalence detection for mutation filtering
  - Kill-the-mutant test-generation goal explicit in QA's prompt
  - Compare acceptance rate and logical-bug-found rate against v1
- **Dependencies:** mutation-operator catalog.
- **Priority:** MEDIUM

### 7.3 Live-SWE-agent self-evolving scaffold
- **Area:** research
- **What:** Explore whether a simpler bash-only self-evolving scaffold (per Live-SWE-agent arXiv 2511.13646, 79.2% SWE-Bench Verified with Opus 4.5) outperforms the current structured multi-agent approach.
- **Why v1 deferred:** Structured multi-agent is better for *demonstration* and observability; Live-SWE is better for raw performance but worse for human legibility.
- **v2 acceptance sketch:**
  - A/B comparison on eval fixtures: v1 multi-agent vs Live-SWE-style single bash loop
  - If Live-SWE wins materially, consider hybrid: Live-SWE for bug-hunting, structured multi-agent for HITL surfaces
- **Dependencies:** benchmarking infrastructure.
- **Priority:** LOW (exploratory)

---

## Tier 8: Known issues / technical debt from v1

### 8.1 `Project.md` unbounded growth
- **What:** Over time, Project.md grows unboundedly as lessons accumulate. No summarization strategy in v1.
- **Mitigation in v2:** Reviewer does periodic Project.md compaction (monthly), folding repetitive lessons into higher-level invariants.
- **Priority:** MEDIUM

### 8.2 SQLite single-writer bottleneck under concurrent project runs
- **What:** SQLite handles one writer at a time; if two projects schedule checkups at the same minute, one waits.
- **Mitigation in v2:** WAL mode (partial, sometimes enabled in v1) or migration to Postgres as optional backend.
- **Priority:** LOW

### 8.3 No retry on transient Docker failures
- **What:** If `docker build` fails transiently (network, disk), the whole run fails.
- **Mitigation in v2:** 3-retry exponential backoff on Docker operations.
- **Priority:** MEDIUM

### 8.4 No Windows support — `[resolved in v1]`
- **What:** v1 targets Linux/macOS. Docker Desktop on Windows has enough idiosyncrasies that certifying v1 on Windows was out of scope.
- **Resolution:** Promoted into v1 scope during the 2026-04-23 brainstorming round (see `docs/superpowers/specs/2026-04-23-smrt-llm-dev-design.md` §5). Windows 10+ with Docker Desktop in WSL2 mode is now a v1 supported target. The bash-only `bin/smrt-exec.sh` was replaced by a cross-platform Python wrapper (`bin/smrt-exec.py`) using the `docker` Python SDK.
- **Priority:** ~~LOW~~ — done

### 8.5 No internationalization
- **What:** All UI strings hardcoded in English.
- **Mitigation in v2:** i18n framework (react-i18next) with English as the only shipped locale; Korean support likely useful given Jacob's background.
- **Priority:** LOW

---

## Consumption protocol for the next planning round

1. Open this file alongside the latest `PRODUCTION.md`.
2. For each Tier 1 item, evaluate whether it should be promoted into v2's scope or re-deferred.
3. For Tiers 2–7, pick 3–5 items to include in v2 based on (a) evaluator feedback from v1, (b) real-world usage patterns observed, (c) strategic positioning.
4. Move promoted items into `PRODUCTION.md` under §13 (milestones) or as new sections.
5. Mark completed items in this file as `[done v2]` rather than deleting — preserves history.
6. Append any newly discovered deferrals from v1 implementation to this file.

## Cross-reference

- For research foundations that may unlock items above, see `RESEARCH.md`.
- For v1 scope as shipped, see `PRODUCTION.md` §15 (Definition of done).
