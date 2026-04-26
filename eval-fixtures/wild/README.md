# Wild Fixtures: Real-World FastAPI Soak Testing

This directory is a placeholder for cloning real-world public FastAPI repositories to test SMRT Agent against unfamiliar, production-grade codebases. By soak-testing against diverse projects, we discover edge cases, patterns the agent misses, and opportunities to improve reasoning.

**Everything in this directory except this `README.md` is gitignored** — your clones never commit back to smrt-llm-dev.

## Recommended Repositories

### 1. **tiangolo/full-stack-fastapi-template**
- **GitHub**: https://github.com/tiangolo/full-stack-fastapi-template
- **Description**: Production-ready FastAPI + React + PostgreSQL starter. Includes authentication, permission scopes, async sqlalchemy, background tasks, email templates.
- **SMRT finds**: Auth/permission logic flaws, async context bugs, SQL injection risks in query construction, missing validation on request body constraints.

### 2. **nsidnev/fastapi-realworld-example-app**
- **GitHub**: https://github.com/nsidnev/fastapi-realworld-example-app
- **Description**: Medium.com-like API with articles, comments, tags, followers. Real data relationships and ORM usage.
- **SMRT finds**: N+1 query problems, race conditions in create-and-reference patterns, missing pagination limits, inconsistent error codes.

### 3. **zhanymkanov/fastapi-best-practices**
- **GitHub**: https://github.com/zhanymkanov/fastapi-best-practices
- **Description**: Best practices repo with multiple patterns: dependency injection, middleware, async generators, proper error handling. Compact, high-signal examples.
- **SMRT finds**: Subtle dependency lifecycle issues, exception handler shadowing, incorrect async context manager usage.

### 4. **jod35/Blog-API-with-FastAPI**
- **GitHub**: https://github.com/jod35/Blog-API-with-FastAPI
- **Description**: Comprehensive blog API with JWT auth, comments, roles, pagination, filtering. Single compact repo.
- **SMRT finds**: Token expiration edge cases, comment permission leaks, inefficient filter/sort chains on large datasets.

### 5. **litestar-org/litestar** (reference ASGI patterns)
- **GitHub**: https://github.com/litestar-org/litestar
- **Description**: Modern ASGI framework (formerly Starlite). Extensive middleware, validation, OpenAPI integration. Use `/examples/` for real patterns.
- **SMRT finds**: Middleware ordering issues, validation schema conflicts, ORM integration mismatch, subtle async state corruption.

### 6. **fastapi/fastapi** (framework tests and examples)
- **GitHub**: https://github.com/fastapi/fastapi
- **Description**: FastAPI framework itself. Explore `/docs/` examples and `/tests/` for edge cases and integration patterns.
- **SMRT finds**: Undocumented feature interactions, OpenAPI spec generation bugs, Pydantic v2 migration pitfalls.

## How to Use

1. Clone a repo into this directory:
   ```bash
   git clone https://github.com/tiangolo/full-stack-fastapi-template eval-fixtures/wild/full-stack-fastapi-template
   ```

2. Register the workspace in the SMRT Agent UI:
   - Navigate to your agent's workspace manager
   - Add `/workspace/eval-fixtures/wild/full-stack-fastapi-template`

3. Run analysis:
   - The agent will now discover and reason about the cloned codebase
   - Check agent logs for what issues it flags

## Tips

- **Smaller is better for iteration**: Start with repos under 2000 lines of code (like fastapi-best-practices) to see faster feedback.
- **Mix patterns**: Clone both monolithic (full-stack) and modular (realworld) repos for variety.
- **Update periodically**: `cd eval-fixtures/wild/<repo> && git pull` to test against latest changes.
- **Check local issues first**: Before soak-testing, run the repo's own tests (`pytest`, `docker-compose up`) to ensure it's healthy.
