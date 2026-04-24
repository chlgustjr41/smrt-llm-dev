# Eval fixtures

## `todo-api/` — synthetic fixture (built in P1)

A small FastAPI app (~150 LOC) with five planted bugs spanning the categories from `PRODUCTION.md` §10:

1. Silent-logical (missing `response_model` causes `hashed_password` leak)
2. Async (missing `await` on a coroutine)
3. Auth-order (authorization check after database write)
4. Input-validation (Pydantic field with insufficient constraint)
5. State-mutation (race condition under concurrent requests)

The answer key lives in `todo-api/BUGS.md` for evaluators to verify the agent's findings. The same file is added to `todo-api/.gitignore` so the agent itself can't read it.

## `wild/` — real-world fixtures (you bring them)

Empty in v1. Recommended public FastAPI repos for soak testing:

- `github.com/tiangolo/full-stack-fastapi-template` — official Tiangolo template (point the agent at the `backend/` subdir)
- `github.com/nsidnev/fastapi-realworld-example-app` — popular RealWorld implementation; smaller, pure backend
- `github.com/zhanymkanov/fastapi_best_practices` — pedagogical reference repo

To use any of these:

```bash
cd eval-fixtures/wild
git clone https://github.com/<owner>/<repo>.git
```

Then register the local path in the SMRT Agent UI.

A one-click loader for these is tracked in `NEXT_ITERATION.md` §5.6.
