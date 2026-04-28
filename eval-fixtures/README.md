# Eval fixtures

Two ready-to-run FastAPI fixtures with planted bugs, plus a "bring your own" slot for real-world repos. Each fixture ships with a `BUGS.md` answer key gated by `.agentignore` so the agents discover bugs dynamically — not by reading the answer.

> **Don't read `BUGS.md` before evaluating.** It's the answer key. The `secret_guard_hook` already prevents the agents from reading it. If you're a human evaluator, opening `BUGS.md` first will spoil the run for you too. Run the agents, then check `BUGS.md` to score them.

---

## At a glance

| Fixture                  | LOC    | Files | Bug categories                                                            | Recommended for                                  |
|--------------------------|--------|-------|----------------------------------------------------------------------------|--------------------------------------------------|
| [`todo-api/`](#todo-api) | ~150   | 1     | silent-logical, async, auth-order, input-validation, state-mutation        | First run; verifying the loop end-to-end          |
| [`inventory-api/`](#inventory-api) | ~250 | 7  | variable-swap, unused-variable, missing-factor, off-by-one, wrong-predicate | Stress test on cross-file reasoning               |
| [`wild/`](#wild)         | —      | —     | (your choice)                                                              | Soak testing on real public FastAPI repos         |

All three live under `/workspace/eval-fixtures/<name>` from inside the backend container, since the repo root is bind-mounted to `/workspace` by `docker-compose.yml`.

---

## `todo-api/`

Single-file FastAPI app. Five planted bugs from the canonical defect taxonomy in `PRODUCTION.md` §10:

| #   | Category          | Endpoint(s)                       | Bug summary                                                            |
|-----|-------------------|-----------------------------------|------------------------------------------------------------------------|
| 1   | Silent-logical    | `POST /users`, `GET /users`       | `password_hash` leaks in response (no `response_model` filter)         |
| 2   | Async             | `POST /todos`                     | Missing `await` on `_save_todo(...)`; coroutine GC'd before write      |
| 3   | Auth-order        | `DELETE /todos/{id}`              | Ownership check runs **after** the `del` — 403 + already deleted       |
| 4   | Input validation  | `POST /todos`                     | `due_at` accepts past timestamps (no validator)                        |
| 5   | State mutation    | `PATCH /todos/{id}/complete`      | Read-yield-write race in `_completed_count` increment                  |

**Quick run:**

```bash
# 1. Boot the stack (one-time)
docker network create smrt-internal && docker compose up -d

# 2. Open http://127.0.0.1:5173, click "Register Project"
#    → use file browser to select eval-fixtures/todo-api

# 3. Click "Run Init Audit"  → Reviewer writes docs/
# 4. Click "Find Bugs"       → expect 3-5 tickets in Pending Confirmation
# 5. Drag any ticket → In Progress  → watch QA-Coder loop on AgentTimeline
# 6. Drag → Closed            → fix commit lands on a smrt-fix-* branch
```

**Expected cost:** ~$0.30 / full run on Anthropic Haiku 4.5 defaults; ~$0.05 if you only run a single ticket. Free if you set `USE_LOCAL_LLM=true`.

**Score yourself:** after the run, `cat eval-fixtures/todo-api/BUGS.md`. Each entry names the file, the failing test name, and the expected diff. The agent's commit should match.

---

## `inventory-api/`

Multi-router service: 5 routers + 1 service + a schemas module. Five planted bugs that **require cross-file reasoning** — the contract is in one file, the bug is in another.

| #   | Category           | File                              | Why it's interesting                                                                |
|-----|--------------------|-----------------------------------|-------------------------------------------------------------------------------------|
| 1   | Variable swap      | `routers/stock.py`                | Stock transfer deducts from target / adds to source; contract is in `schemas.py`    |
| 2   | Unused variable    | `services/inventory.py`           | Reads `reserved` count but never subtracts it from physical stock                   |
| 3   | Missing factor     | `routers/orders.py`               | Order total adds `unit_price` without `quantity` multiplier                         |
| 4   | Off-by-one         | `routers/reports.py`              | Low-stock alert is exclusive `<` instead of inclusive `<=` per docstring contract   |
| 5   | Wrong predicate    | `routers/products.py`             | `product.get("deleted") is not None` always true → soft-deleted items leak          |

**Why this fixture is harder than `todo-api`:**

- Bug #1 is a swap, not a missing line. The agent has to compare the docstring contract in `schemas.StockTransferRequest` against two assignments in `routers/stock.py` and reason about which is "from" and which is "to."
- Bug #5 looks correct at a glance — `is not None` reads as a sensible "field is set" check until you realize *every* product record sets the field. The agent has to trace data flow from `products` storage to the filter.
- Bugs #4 and #5 both pass the type checker and produce non-error output. There is no exception, no traceback — just wrong numbers and wrong rows.

**Quick run:**

```bash
# Same as todo-api, but pick eval-fixtures/inventory-api in the file browser.
# Allow ~10 min and ~$0.80 for the full discovery + 2-3 fixes.
```

**What to watch for:**

1. **Init Audit docs.** `docs/modules/` should list 5 routers + 1 service + 1 schema module — if it lists fewer, the Reviewer didn't recurse into subdirectories.
2. **Cross-file reads.** Toggle "Show reasoning" in AgentTimeline. The Coder should `Read schemas.py` *before* patching `routers/stock.py` for bug #1.
3. **Loop discipline.** If a ticket exhausts `MAX_FIX_ATTEMPTS`, the Needs Review dialog should show QA's failure report naming the suspected files — not the test code (blackbox contract).

---

## `wild/`

Empty placeholder for real public FastAPI repos. To use:

```bash
cd eval-fixtures/wild
git clone https://github.com/<owner>/<repo>.git
```

Then register `/workspace/eval-fixtures/wild/<repo>` in the SMRT UI.

**Recommended targets:**

- [`tiangolo/full-stack-fastapi-template`](https://github.com/tiangolo/full-stack-fastapi-template) — official Tiangolo template; point the agent at the `backend/` subdir
- [`nsidnev/fastapi-realworld-example-app`](https://github.com/nsidnev/fastapi-realworld-example-app) — popular RealWorld implementation; smaller, pure backend
- [`zhanymkanov/fastapi_best_practices`](https://github.com/zhanymkanov/fastapi_best_practices) — pedagogical reference repo

**Soak-test protocol:**

1. Clone a real repo, ensure its existing `pytest` is green on `main`.
2. Register it in SMRT and run **Init Audit**. Expect this to fail or produce a sparse `Project.md` if the repo has heavy non-FastAPI surface (DB migrations, Celery workers) — that's a known limitation tracked in `NEXT_ITERATION.md`.
3. Run **Find Bugs**. The QA agent should produce *no* tickets on a clean main branch (low false-positive rate is a hard requirement).
4. Manually break something (e.g., remove an `await` or invert an `if`), commit, then run **Find Bugs** again. The agent should now file a ticket within 1 attempt.

A one-click loader for the recommended targets is tracked in `NEXT_ITERATION.md` §5.6.

---

## How `.agentignore` works

Each fixture has an `.agentignore` file at its root listing files the agents must not read:

```text
# eval-fixtures/todo-api/.agentignore
BUGS.md
main-answer.py
```

The `secret_guard_hook` (registered as a `PreToolUse` callback on every agent) walks `.agentignore` files hierarchically — a `.agentignore` in a subdirectory inherits and extends its parent. On match, the hook returns `Access denied: <path> matches a secret-file or .agentignore pattern.` and logs the blocked call to `tool_calls.jsonl` for audit.

This is **separate from `.gitignore`**: secrets and credentials still go in `.gitignore` (and are also blocked); evaluator answer keys go in `.agentignore`. See `PRODUCTION.md` §0.7 for the rationale.
