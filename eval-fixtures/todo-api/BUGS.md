# todo-api — Planted Bugs Answer Key

> **EVALUATOR ONLY.** This file is committed to the meta-repo so evaluators can see it,
> but it is listed in `eval-fixtures/todo-api/.agentignore` so all SMRT agents
> (Reviewer, QA, Coder) are denied read access during evaluation. The bugs must
> be discovered by the agent through dynamic testing, not by reading this file.

---

## Bug #1 — Silent Logical: password_hash exposed in API response

**Affected endpoints:** `POST /users`, `GET /users`

**Expected behavior:** The `password_hash` field must never appear in any API response.
User objects returned to callers should contain only `id` and `email`.

**Actual behavior (with bug):** Both `POST /users` and `GET /users` return the raw dict
including `password_hash`. A caller receives `{"id":1,"email":"...","password_hash":"hashed:secret"}`.

**Location in code:** `main.py` lines for `create_user` and `list_users` — both return
`user` or `_users.values()` directly without stripping the `password_hash` field.

**Fix:** Introduce a response schema that excludes `password_hash`, e.g. a Pydantic
`UserOut` model with only `id` and `email`, and use it as the `response_model`.

**Hint for evaluators:** The agent should discover this by POSTing a user and inspecting
the response body for the presence of `password_hash`.

---

## Bug #2 — Async: missing `await` on async DB write

**Affected endpoint:** `POST /todos`

**Expected behavior:** A todo created via `POST /todos` is immediately visible in
`GET /todos`.

**Actual behavior (with bug):** `_save_todo(todo)` is called without `await`. The coroutine
is created but never awaited, so it is garbage-collected without executing. The todo dict
is returned in the 201 response but never written to `_todos`. A subsequent `GET /todos`
returns an empty list (or a list without the newly created todo).

**Location in code:** `main.py`, `create_todo` — `_save_todo(todo)` should be
`await _save_todo(todo)`.

**Fix:** Add `await` before `_save_todo(todo)`.

**Hint for evaluators:** POST a todo, then GET /todos. The list will be empty.

---

## Bug #3 — Auth order: ownership check after DB write (delete)

**Affected endpoint:** `DELETE /todos/{todo_id}`

**Expected behavior:** Ownership is checked before any mutation. If `caller_id` does not
match `todo["owner_id"]`, return 403 with no side-effects — the todo must still exist.

**Actual behavior (with bug):** The todo is deleted from `_todos` first, then the
ownership check runs. An unauthorized caller receives 403, but the todo is already gone.
Subsequent `GET /todos` will not return the deleted item.

**Location in code:** `main.py`, `delete_todo` — `del _todos[todo_id]` happens before
the `if todo["owner_id"] != caller_id` check.

**Fix:** Move the ownership check before the `del` statement.

**Hint for evaluators:** Delete a todo with a mismatched caller_id; verify with GET /todos
that the todo is gone despite the 403.

---

## Bug #4 — Input validation: due_at accepted in the past

**Affected endpoint:** `POST /todos`

**Expected behavior:** `due_at`, when provided, must be a future datetime (strictly after
`datetime.utcnow()`). Requests with a past `due_at` should return 422 Unprocessable Entity.

**Actual behavior (with bug):** Any datetime is accepted, including values in the past.
Todos can be created that are already overdue at the moment of creation.

**Location in code:** `main.py`, `create_todo` — no validation is performed on `body.due_at`.

**Fix:** After parsing, check `if body.due_at and body.due_at < datetime.utcnow(): raise HTTPException(422, ...)`.

**Hint for evaluators:** POST a todo with `due_at` set to yesterday; expect 422 but get 201.

---

## Bug #5 — State mutation: race condition in completed_count increment

**Affected endpoint:** `PATCH /todos/{todo_id}/complete`

**Expected behavior:** Each call atomically increments `_completed_count` by 1.
N concurrent calls → final count == N.

**Actual behavior (with bug):** The handler reads `current = _completed_count`, yields
to the event loop (`await asyncio.sleep(0)`), then writes `_completed_count = current + 1`.
If two concurrent requests both read the same `current` value before either writes,
the final count is N-1 instead of N (lost update).

**Location in code:** `main.py`, `complete_todo` — the read-yield-write pattern:
```python
current = _completed_count
await asyncio.sleep(0)
_completed_count = current + 1
```

**Fix:** Remove the yield between read and write, or use an atomic increment:
`_completed_count += 1` (no intermediate yield).

**Hint for evaluators:** Fire 10 concurrent requests to `/todos/{id}/complete`; expect
`completed_count == 10` but get a lower value.
