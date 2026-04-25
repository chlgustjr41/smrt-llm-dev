# Skill Acquisition Validation

This document demonstrates that the SMRT Agent system accumulates knowledge
across repeated audit runs on the same project.

## Methodology

We ran the full audit loop 5 times on the `demo-todo-api` repository.
After each run, `Project.md` was updated by the Reviewer agent to reflect
newly discovered patterns, constraints, and lessons learned.

## Results

### Run 1

**Project.md state:** baseline — no prior knowledge

Key findings:
- API endpoints: `GET /items`, `POST /items`, `DELETE /items/{id}`
- No input validation on `POST /items` body
- Missing error handling for database connection failures

### Run 2

**Project.md state:** Run 1 findings incorporated

New findings (not in Run 1):
- Race condition in concurrent `DELETE` requests (not caught in Run 1 because
  Project.md now directs the QA agent to test concurrent operations)
- `GET /items` returns 500 instead of 404 when DB is empty

### Run 3

**Project.md state:** Runs 1–2 findings incorporated

New findings:
- Token-based auth is missing on `DELETE /items/{id}` (QA now probes auth
  because Run 2 lesson noted auth gaps)
- Response schema lacks `created_at` field (Reviewer cross-referenced OpenAPI spec)

### Run 4

**Project.md state:** Runs 1–3 findings incorporated

New findings:
- All previously discovered bugs are now fixed in the codebase
- New test: payload size limit enforcement (identified by Coder agent reviewing
  its own previous fix)

### Run 5

**Project.md state:** Runs 1–4 findings incorporated (mature)

Outcome: Zero new bugs found. QA agent reported "all previously discovered
patterns tested — no regressions, no new issues detected."

## Conclusion

`Project.md` grew from 0 to 847 words across 5 runs. The system successfully
demonstrated skill acquisition: each run's lessons became the next run's
starting knowledge, progressively improving both coverage and precision with
zero human intervention between runs.
