# Evaluation Rubric Mapping

This document maps each SMRT rubric criterion to its concrete implementation.

---

## 1. AI Orchestration

**Spec requirement**: multi-agent hierarchy, context isolation, structured handoffs, budget guardrails.

**Implementation**

| Aspect | Where |
|---|---|
| Three-agent hierarchy (Reviewer → QA → Coder) | `agents/orchestrator.py` `run_qa_session()` |
| Blackbox between QA and Coder enforced at tool level | Coder tools (`agents/coder/budget.py`) omit any path to `.smrt/tests/`; `read_source_file` rejects paths outside `src/` |
| Context isolation — subagents start fresh; only explicit artifacts passed | `orchestrator.py` lines 40–47 (QA), 121–128 (Coder): only `Project.md` content + ticket/pytest output injected |
| Structured JSON handoffs | QA returns `ticket_id` (string); Coder result is inferred by re-running pytest; session-status events carry `{"type": "session_status", "status": "..."}` |
| Budget guardrails — $1.50/run default, $10/day default | `settings.py` `budget_per_run_usd`, `budget_per_day_usd`; per-agent share enforced in each `loop.py`; `budget_exceeded` event halts and surfaces in `LiveAgentView` / `QASessionView` |
| Subagents cannot spawn subagents | `Agent` tool absent from QA and Coder tool definitions |

**Where to see it in the UI**: the Live Agent View (`components/LiveAgentView.tsx`) and QA Session View (`components/QASessionView.tsx`) show agent transitions in real time. Budget events appear as error-state status badges.

---

## 2. Attention to Detail (Logical Bugs)

**Spec requirement**: find especially logical bugs that a standard linter would miss; test-status memory.

**Implementation**

| Aspect | Where |
|---|---|
| Three-strategy logical-bug engine | QA prompt (`prompts/qa.md`); strategy selected by test-plan `category` field |
| Strategy A — mutation-guided | QA uses mutmut/cosmic-ray on changed source files; surviving mutants become new test-plan entries with `category: logical` |
| Strategy B — property-based (Hypothesis) | QA generates Hypothesis strategies from Pydantic schemas via OpenAPI spec; 100 examples per property |
| Strategy C — differential vs git history | QA runs old green tests against new code; unexpected 500s or status-code changes become ticket candidates |
| Confidence threshold 0.6 before filing a ticket | `agents/qa/tools.py` `write_bug_ticket`; QA prompt instructs confidence gate |
| Test-status promotion/demotion memory | `agents/qa/tools.py` `write_test_status`; `.smrt/test-status.md`; green-stable tests promoted to weekly, red tests to every checkup |
| Eval fixtures with intentional logical bugs | `eval-fixtures/todo-api/` — 5 deliberate bugs including missing `response_model`, forgotten `await`, wrong auth order |

**Where to see it in the UI**: the Tickets panel (`components/TicketsPanel.tsx`) lists filed tickets with severity and confidence score. The Heatmap chart (`components/HeatmapChart.tsx`) shows which source files have the most resolved bugs — a direct output of the logical-bug engine. Data sourced from `GET /projects/{id}/stats/heatmap` (`api/stats.py`).

---

## 3. Communication and Critical Thinking (When to Ask)

**Spec requirement**: explicit HITL surface; uncertainty-gated scaffold; display agent thought process.

**Implementation**

| Aspect | Where |
|---|---|
| Two mandatory human decisions (ticket confirm, PR accept) | `orchestrator.py` HITL gate; `api/qa_sessions.py` `/approve` and `/skip` endpoints |
| HITL blocks on `asyncio.Event` with 1-hour timeout | `orchestrator.py` lines 79–95 |
| Approve/Skip buttons rendered when `status === "hitl_waiting"` | `components/QASessionView.tsx` |
| Thought-process mode — live agent text stream + inline mutating-tool gates | SSE events `text_delta`, `qa_text_delta`, `coder_text_delta` emitted by every agent loop; `can_use_tool` callback blocks in thought-process mode |
| Coder's one question per rejection — uncertainty-gated | `settings.py` `max_questions_per_attempt` (default 1); QA answers descriptively |
| Rejection reason flows to `Project.md` Lessons section | `orchestrator.py` post-rejection path; Reviewer writes updated `.smrt/Project.md` |
| Live tool-call observability (four collapsible layers) | `components/LiveAgentView.tsx` renders `tool_use` + `tool_result` events; `components/AgentTimeline.tsx` for past runs |

**Where to see it in the UI**: the QA Session View shows the HITL waiting state with Approve/Skip and the real-time agent text stream. The Config section of Project Detail has the autonomy mode toggle that activates thought-process mode.

---

## 4. Bonus (Visual Reports, Performance, Extra Features)

**Spec requirement**: visual dashboards, Obsidian vault, Explain mode, skill acquisition.

**Implementation**

| Aspect | Where |
|---|---|
| Dashboard 1 — audit cost breakdown per run | `components/CostChart.tsx`; data from `GET /projects/{id}/stats/cost` (`api/stats.py`) |
| Dashboard 2 — bug-hunt heatmap | `components/HeatmapChart.tsx`; data from `GET /projects/{id}/stats/heatmap`; tile area = LOC, color = bugs resolved count |
| Dashboard 3 — documentation completeness over time | `components/DocScoreChart.tsx`; data from `GET /projects/{id}/stats/doc-completeness`; score = (documented endpoints / total) × 0.5 + (documented modules / total) × 0.5 |
| Obsidian vault (`wiki/`) with YAML frontmatter | `docs/backends.py` `ObsidianBackend.upsert_*`; writes `type`, `tags`, `updated` frontmatter; parallel to `GitHubBackend` |
| `DocBackend` abstract interface — GitHub + Obsidian live, Jira/Confluence stub | `docs/backends.py`; `JiraBackend` and `ConfluenceBackend` raise `NotImplementedError` with v2 note |
| Explain mode / change provenance | `[smrt-provenance]` JSON trailer in commit messages; parsed by `api/provenance.py`; displayed in `components/ProvenancePanel.tsx` |
| Skill acquisition — Project.md grows from every outcome | `agents/reviewer/` writes `.smrt/Project.md`; injected into every QA and Coder context; Lessons section updated on each rejection |
| `bugs-resolved.md` for semantic search by future agents | `agents/qa/tools.py` `append_bugs_resolved`; QA reads this before generating new tests to avoid re-filing known patterns |
| Doc completeness tracked and auto-updated after every run | `knowledge.py` `compute_doc_score` + `record_doc_score`; called in `api/runs.py` `_run_task` after `generate_docs` |
