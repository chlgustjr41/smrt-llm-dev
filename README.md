# SMRT Agent (`smrt-llm-dev`)

> A semi-autonomous multi-agent system that acts as a **QA engineer + junior developer pair** inside a Python FastAPI codebase. Discovers bugs (especially logical ones), fixes them through a blackbox QA↔Coder loop, and maintains documentation in both GitHub-native Markdown and a parallel Obsidian vault.

**Status:** Planning phase. Spec written; implementation begins after the design + plan review gates.

**Spec documents:**
- [`PRODUCTION.md`](./PRODUCTION.md) — v1 product spec (the "what" and "why")
- [`NEXT_ITERATION.md`](./NEXT_ITERATION.md) — v2 backlog
- [`docs/superpowers/specs/2026-04-23-smrt-llm-dev-design.md`](./docs/superpowers/specs/2026-04-23-smrt-llm-dev-design.md) — implementation design (the "how")

## Quick start (when implementation lands)

```bash
git clone https://github.com/chlgustjr41/smrt-llm-dev
cd smrt-llm-dev

# macOS / Linux
cp .env.example .env

# Windows
copy .env.example .env

# Edit .env and set your real ANTHROPIC_API_KEY

docker compose up
```

Open http://127.0.0.1:5173 in your browser.

## Requirements

- **Docker Desktop** (Windows / macOS) or Docker Engine (Linux)
  - On Windows, Docker Desktop must use the WSL2 backend
- **Python 3.11+**
- **Node 20+**
- **`git`** on PATH
- **Anthropic API key** — get one at https://console.anthropic.com/settings/keys

## Architecture

See `PRODUCTION.md` §2 (agent hierarchy) and `docs/superpowers/specs/2026-04-23-smrt-llm-dev-design.md` (implementation phases).

## License

[MIT](./LICENSE)
