# SMRT Agent P5 — Documentation System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the DocBackend system that reads `.smrt/Project.md` (produced by the Reviewer audit) and generates `docs/` (GitHub-flavoured Markdown) and `wiki/` (Obsidian-compatible notes with YAML frontmatter) for each project, then surfaces the generated files in a new DocPanel on the Project Detail page.

**Architecture:** `DocBackend` is an abstract class called by backend service code (not the agent itself) after each Reviewer audit. A `ProjectMdParser` reads `.smrt/Project.md` and extracts structured `EndpointDoc`/`ModuleDoc` objects from the Markdown tables. `GitHubBackend` writes GitHub-renderable Markdown to `docs/`; `ObsidianBackend` writes notes with YAML frontmatter to `wiki/`. `JiraBackend` and `ConfluenceBackend` are stubs raising `NotImplementedError`. After `run_reviewer()` completes in `_run_task`, `generate_docs()` is called; the result is saved to the JSONL event log. A `GET /projects/{id}/docs` endpoint lists generated .md files. A `DocPanel` React component fetches that list and shows a chip row (GitHub ✓, Obsidian ✓, Jira coming-soon, Confluence coming-soon) plus the file list.

**Tech Stack:** Python 3.11 · FastAPI · SQLAlchemy async · pytest · React 18 · TypeScript · Vite · Tailwind CSS · Vitest · MSW · @testing-library/react

---

## File Structure

**New backend files:**
- `backend/src/smrt_agent/docs/__init__.py` — empty package marker
- `backend/src/smrt_agent/docs/backends.py` — dataclasses (`EndpointDoc`, `ModuleDoc`, `DecisionDoc`), abstract `DocBackend`, `GitHubBackend`, `ObsidianBackend`, `JiraBackend`, `ConfluenceBackend`
- `backend/src/smrt_agent/docs/parser.py` — `parse_endpoints()`, `parse_module_doc()`, `load_and_parse()`
- `backend/src/smrt_agent/docs/service.py` — `generate_docs(project_path)` calling GitHubBackend + ObsidianBackend
- `backend/src/smrt_agent/api/docs.py` — `GET /projects/{id}/docs` listing docs/ and wiki/ .md files

**New backend tests:**
- `backend/tests/test_doc_backends.py` — unit tests for all DocBackend classes
- `backend/tests/test_doc_parser.py` — unit tests for parser functions
- `backend/tests/test_doc_service.py` — unit test for `generate_docs()` integration
- `backend/tests/test_docs_api.py` — integration tests for the docs API endpoint

**Modified backend files:**
- `backend/src/smrt_agent/api/runs.py` — add `generate_docs()` call after `run_reviewer()` succeeds; put `docs_written` event in queue
- `backend/src/smrt_agent/main.py` — wire docs router

**New frontend files:**
- `frontend/src/api/docs.ts` — `listDocs(projectId)` fetch helper, `DocFile` type
- `frontend/src/components/DocPanel.tsx` — backend chip row + doc file list
- `frontend/src/test/DocPanel.test.tsx` — DocPanel tests via MSW

**Modified frontend files:**
- `frontend/src/pages/ProjectDetailPage.tsx` — add Documentation section with DocPanel

---

### Task 1: Create phase/5-docs branch

**Files:** none

- [ ] **Step 1: Create and switch to the phase branch**

```bash
cd D:/web-project/smrt-llm-dev
git checkout main && git pull origin main
git checkout -b phase/5-docs
```

Expected: `Switched to a new branch 'phase/5-docs'`

- [ ] **Step 2: Commit an empty marker**

```bash
git commit --allow-empty -m "chore: start phase/5-docs branch"
```

---

### Task 2: DocBackend abstract interface + data types

**Files:**
- Create: `backend/src/smrt_agent/docs/__init__.py`
- Create: `backend/src/smrt_agent/docs/backends.py`
- Create: `backend/tests/test_doc_backends.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_doc_backends.py`:

```python
import pytest
import asyncio
from smrt_agent.docs.backends import DocBackend, EndpointDoc, ModuleDoc, DecisionDoc


def test_endpoint_doc_fields():
    ep = EndpointDoc(method="GET", path="/items", auth_required=False, purpose="List items")
    assert ep.method == "GET"
    assert ep.path == "/items"
    assert ep.auth_required is False
    assert ep.purpose == "List items"
    assert ep.tags == []


def test_module_doc_fields():
    mod = ModuleDoc(name="services.auth", description="Handles authentication", file_path="src/auth.py")
    assert mod.name == "services.auth"
    assert mod.tags == []


def test_decision_doc_fields():
    dec = DecisionDoc(
        slug="2026-04-24-chose-jwt",
        title="Use JWT",
        context="Need stateless auth",
        decision="Use JWT tokens",
        consequences="Tokens cannot be revoked without blocklist",
    )
    assert dec.slug == "2026-04-24-chose-jwt"
    assert dec.tags == []


def test_doc_backend_is_abstract():
    import inspect
    assert inspect.isabstract(DocBackend)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_backends.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'smrt_agent.docs'`

- [ ] **Step 3: Create the package and abstract interface**

Create `backend/src/smrt_agent/docs/__init__.py` — leave empty.

Create `backend/src/smrt_agent/docs/backends.py`:

```python
"""DocBackend abstract interface and concrete implementations."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EndpointDoc:
    method: str
    path: str
    auth_required: bool
    purpose: str
    tags: list[str] = field(default_factory=list)


@dataclass
class ModuleDoc:
    name: str
    description: str
    file_path: str
    tags: list[str] = field(default_factory=list)


@dataclass
class DecisionDoc:
    slug: str
    title: str
    context: str
    decision: str
    consequences: str
    tags: list[str] = field(default_factory=list)


class DocBackend(ABC):
    @abstractmethod
    async def upsert_module_doc(self, module: ModuleDoc) -> None: ...

    @abstractmethod
    async def upsert_endpoint_doc(self, endpoint: EndpointDoc) -> None: ...

    @abstractmethod
    async def upsert_decision(self, decision: DecisionDoc) -> None: ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_backends.py -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/docs/ backend/tests/test_doc_backends.py
git commit -m "feat: add DocBackend abstract interface and dataclasses"
```

---

### Task 3: GitHubBackend

**Files:**
- Modify: `backend/src/smrt_agent/docs/backends.py`
- Modify: `backend/tests/test_doc_backends.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_doc_backends.py`:

```python
def test_github_backend_writes_module_doc(tmp_path):
    from smrt_agent.docs.backends import GitHubBackend
    backend = GitHubBackend(tmp_path)
    mod = ModuleDoc(name="services.auth", description="Auth service", file_path="src/auth.py", tags=["auth"])
    asyncio.run(backend.upsert_module_doc(mod))
    out = (tmp_path / "docs" / "modules" / "services.auth.md").read_text()
    assert "# services.auth" in out
    assert "Auth service" in out
    assert "src/auth.py" in out


def test_github_backend_writes_endpoint_doc(tmp_path):
    from smrt_agent.docs.backends import GitHubBackend
    backend = GitHubBackend(tmp_path)
    ep = EndpointDoc(method="GET", path="/items", auth_required=False, purpose="List items")
    asyncio.run(backend.upsert_endpoint_doc(ep))
    out = (tmp_path / "docs" / "api" / "GET_items.md").read_text()
    assert "# GET /items" in out
    assert "List items" in out
    assert "None" in out  # auth = None (not required)


def test_github_backend_api_index_lists_all_endpoints(tmp_path):
    from smrt_agent.docs.backends import GitHubBackend
    backend = GitHubBackend(tmp_path)
    asyncio.run(backend.upsert_endpoint_doc(EndpointDoc(method="POST", path="/items", auth_required=True, purpose="Create")))
    asyncio.run(backend.upsert_endpoint_doc(EndpointDoc(method="GET", path="/items", auth_required=False, purpose="List")))
    index = (tmp_path / "docs" / "api" / "index.md").read_text()
    assert "GET_items.md" in index
    assert "POST_items.md" in index


def test_github_backend_writes_decision_doc(tmp_path):
    from smrt_agent.docs.backends import GitHubBackend
    backend = GitHubBackend(tmp_path)
    dec = DecisionDoc(
        slug="2026-04-24-chose-jwt",
        title="Use JWT",
        context="Need stateless auth",
        decision="JWT tokens",
        consequences="Tokens persist until expiry",
    )
    asyncio.run(backend.upsert_decision(dec))
    out = (tmp_path / "docs" / "decisions" / "2026-04-24-chose-jwt.md").read_text()
    assert "# Use JWT" in out
    assert "JWT tokens" in out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_backends.py::test_github_backend_writes_module_doc -v
```

Expected: FAIL with `cannot import name 'GitHubBackend'`

- [ ] **Step 3: Implement GitHubBackend**

Append to `backend/src/smrt_agent/docs/backends.py`:

```python
class GitHubBackend(DocBackend):
    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    async def upsert_module_doc(self, module: ModuleDoc) -> None:
        path = self.project_path / "docs" / "modules" / f"{module.name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        tags_line = f"\n\n**Tags:** {', '.join(module.tags)}" if module.tags else ""
        path.write_text(
            f"# {module.name}\n\n{module.description}\n\n**File:** `{module.file_path}`{tags_line}\n",
            encoding="utf-8",
        )

    async def upsert_endpoint_doc(self, endpoint: EndpointDoc) -> None:
        slug = endpoint.path.strip("/").replace("/", "_") or "root"
        filename = f"{endpoint.method}_{slug}.md"
        path = self.project_path / "docs" / "api" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        auth = "Required" if endpoint.auth_required else "None"
        path.write_text(
            f"# {endpoint.method} {endpoint.path}\n\n"
            f"**Authentication:** {auth}\n\n"
            f"**Purpose:** {endpoint.purpose}\n",
            encoding="utf-8",
        )
        await self._update_api_index()

    async def _update_api_index(self) -> None:
        api_dir = self.project_path / "docs" / "api"
        if not api_dir.exists():
            return
        entries = sorted(f.name for f in api_dir.glob("*.md") if f.name != "index.md")
        lines = ["# API Reference\n"] + [f"- [{e}]({e})" for e in entries]
        (api_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    async def upsert_decision(self, decision: DecisionDoc) -> None:
        path = self.project_path / "docs" / "decisions" / f"{decision.slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# {decision.title}\n\n"
            f"## Context\n{decision.context}\n\n"
            f"## Decision\n{decision.decision}\n\n"
            f"## Consequences\n{decision.consequences}\n",
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_backends.py -v
```

Expected: 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/docs/backends.py backend/tests/test_doc_backends.py
git commit -m "feat: implement GitHubBackend writing docs/ markdown files"
```

---

### Task 4: ObsidianBackend

**Files:**
- Modify: `backend/src/smrt_agent/docs/backends.py`
- Modify: `backend/tests/test_doc_backends.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_doc_backends.py`:

```python
def test_obsidian_backend_writes_module_doc(tmp_path):
    from smrt_agent.docs.backends import ObsidianBackend
    backend = ObsidianBackend(tmp_path)
    mod = ModuleDoc(name="services.auth", description="Auth service", file_path="src/auth.py", tags=["auth"])
    asyncio.run(backend.upsert_module_doc(mod))
    # dots in name become __ in slug
    out = (tmp_path / "wiki" / "modules" / "services__auth.md").read_text()
    assert "type: module" in out
    assert "# services.auth" in out
    assert "Auth service" in out


def test_obsidian_backend_writes_endpoint_doc(tmp_path):
    from smrt_agent.docs.backends import ObsidianBackend
    backend = ObsidianBackend(tmp_path)
    ep = EndpointDoc(method="GET", path="/items", auth_required=True, purpose="List items")
    asyncio.run(backend.upsert_endpoint_doc(ep))
    out = (tmp_path / "wiki" / "api" / "GET_items.md").read_text()
    assert "type: endpoint" in out
    assert "# GET /items" in out
    assert "Required" in out


def test_obsidian_backend_frontmatter_has_updated_field(tmp_path):
    from smrt_agent.docs.backends import ObsidianBackend
    import re
    backend = ObsidianBackend(tmp_path)
    asyncio.run(backend.upsert_module_doc(ModuleDoc(name="m", description="d", file_path="f")))
    out = (tmp_path / "wiki" / "modules" / "m.md").read_text()
    assert re.search(r"updated: \d{4}-\d{2}-\d{2}", out)


def test_obsidian_backend_writes_decision_doc(tmp_path):
    from smrt_agent.docs.backends import ObsidianBackend
    backend = ObsidianBackend(tmp_path)
    dec = DecisionDoc(
        slug="2026-04-24-chose-jwt",
        title="Use JWT",
        context="Need stateless auth",
        decision="JWT tokens",
        consequences="Tokens persist until expiry",
    )
    asyncio.run(backend.upsert_decision(dec))
    out = (tmp_path / "wiki" / "decisions" / "2026-04-24-chose-jwt.md").read_text()
    assert "type: decision" in out
    assert "# Use JWT" in out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_backends.py::test_obsidian_backend_writes_module_doc -v
```

Expected: FAIL with `cannot import name 'ObsidianBackend'`

- [ ] **Step 3: Implement ObsidianBackend**

Append to `backend/src/smrt_agent/docs/backends.py`:

```python
class ObsidianBackend(DocBackend):
    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path

    def _frontmatter(self, type_: str, tags: list[str]) -> str:
        from datetime import date
        tag_str = "[" + ", ".join(tags) + "]" if tags else "[]"
        return (
            "---\n"
            f"type: {type_}\n"
            f"tags: {tag_str}\n"
            f"updated: {date.today().isoformat()}\n"
            "---\n\n"
        )

    async def upsert_module_doc(self, module: ModuleDoc) -> None:
        slug = module.name.replace(".", "__").replace("/", "__")
        path = self.project_path / "wiki" / "modules" / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self._frontmatter("module", module.tags)
            + f"# {module.name}\n\n{module.description}\n\n**File:** `{module.file_path}`\n",
            encoding="utf-8",
        )

    async def upsert_endpoint_doc(self, endpoint: EndpointDoc) -> None:
        slug = endpoint.path.strip("/").replace("/", "_") or "root"
        filename = f"{endpoint.method}_{slug}.md"
        path = self.project_path / "wiki" / "api" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        auth = "Required" if endpoint.auth_required else "None"
        path.write_text(
            self._frontmatter("endpoint", endpoint.tags)
            + f"# {endpoint.method} {endpoint.path}\n\n"
            f"**Authentication:** {auth}\n\n"
            f"**Purpose:** {endpoint.purpose}\n",
            encoding="utf-8",
        )

    async def upsert_decision(self, decision: DecisionDoc) -> None:
        path = self.project_path / "wiki" / "decisions" / f"{decision.slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self._frontmatter("decision", decision.tags)
            + f"# {decision.title}\n\n"
            f"## Context\n{decision.context}\n\n"
            f"## Decision\n{decision.decision}\n\n"
            f"## Consequences\n{decision.consequences}\n",
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_backends.py -v
```

Expected: 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/docs/backends.py backend/tests/test_doc_backends.py
git commit -m "feat: implement ObsidianBackend writing wiki/ notes with YAML frontmatter"
```

---

### Task 5: JiraBackend and ConfluenceBackend stubs

**Files:**
- Modify: `backend/src/smrt_agent/docs/backends.py`
- Modify: `backend/tests/test_doc_backends.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_doc_backends.py`:

```python
def test_jira_backend_raises_not_implemented():
    from smrt_agent.docs.backends import JiraBackend
    backend = JiraBackend()
    with pytest.raises(NotImplementedError, match="v2"):
        asyncio.run(backend.upsert_module_doc(ModuleDoc(name="x", description="x", file_path="x")))


def test_confluence_backend_raises_not_implemented():
    from smrt_agent.docs.backends import ConfluenceBackend
    backend = ConfluenceBackend()
    with pytest.raises(NotImplementedError, match="v2"):
        asyncio.run(backend.upsert_endpoint_doc(EndpointDoc(method="GET", path="/", auth_required=False, purpose="x")))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_backends.py::test_jira_backend_raises_not_implemented -v
```

Expected: FAIL with `cannot import name 'JiraBackend'`

- [ ] **Step 3: Implement the stubs**

Append to `backend/src/smrt_agent/docs/backends.py`:

```python
class JiraBackend(DocBackend):
    async def upsert_module_doc(self, module: ModuleDoc) -> None:
        raise NotImplementedError("Jira backend is a v2 feature")

    async def upsert_endpoint_doc(self, endpoint: EndpointDoc) -> None:
        raise NotImplementedError("Jira backend is a v2 feature")

    async def upsert_decision(self, decision: DecisionDoc) -> None:
        raise NotImplementedError("Jira backend is a v2 feature")


class ConfluenceBackend(DocBackend):
    async def upsert_module_doc(self, module: ModuleDoc) -> None:
        raise NotImplementedError("Confluence backend is a v2 feature")

    async def upsert_endpoint_doc(self, endpoint: EndpointDoc) -> None:
        raise NotImplementedError("Confluence backend is a v2 feature")

    async def upsert_decision(self, decision: DecisionDoc) -> None:
        raise NotImplementedError("Confluence backend is a v2 feature")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_backends.py -v
```

Expected: 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/docs/backends.py backend/tests/test_doc_backends.py
git commit -m "feat: add JiraBackend and ConfluenceBackend stubs"
```

---

### Task 6: Project.md parser

**Files:**
- Create: `backend/src/smrt_agent/docs/parser.py`
- Create: `backend/tests/test_doc_parser.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_doc_parser.py`:

```python
from pathlib import Path
from smrt_agent.docs.parser import parse_endpoints, parse_module_doc, load_and_parse

SAMPLE_MD = """\
# Project: todo-api

## Purpose
A simple todo list API for managing tasks.

## Endpoints
| Method | Path | Auth required | Purpose |
|--------|------|---------------|---------|
| GET | /items | No | List all items |
| POST | /items | Yes | Create a new item |
| DELETE | /items/{id} | Yes | Delete an item |

## Lessons
<!-- empty -->
"""


def test_parse_endpoints_count():
    eps = parse_endpoints(SAMPLE_MD)
    assert len(eps) == 3


def test_parse_endpoints_methods():
    eps = parse_endpoints(SAMPLE_MD)
    methods = {e.method for e in eps}
    assert methods == {"GET", "POST", "DELETE"}


def test_parse_endpoints_auth_required():
    eps = parse_endpoints(SAMPLE_MD)
    get_ep = next(e for e in eps if e.method == "GET")
    post_ep = next(e for e in eps if e.method == "POST")
    assert get_ep.auth_required is False
    assert post_ep.auth_required is True


def test_parse_endpoints_purpose():
    eps = parse_endpoints(SAMPLE_MD)
    get_ep = next(e for e in eps if e.method == "GET")
    assert get_ep.purpose == "List all items"


def test_parse_endpoints_skips_header_row():
    eps = parse_endpoints(SAMPLE_MD)
    assert all(e.method != "Method" for e in eps)


def test_parse_module_doc_name_and_description():
    mod = parse_module_doc(SAMPLE_MD, "todo-api")
    assert mod.name == "todo-api"
    assert "todo list" in mod.description.lower()


def test_load_and_parse_reads_file(tmp_path):
    smrt_dir = tmp_path / ".smrt"
    smrt_dir.mkdir()
    (smrt_dir / "Project.md").write_text(SAMPLE_MD, encoding="utf-8")
    module, endpoints = load_and_parse(tmp_path)
    assert module.name == "todo-api"
    assert len(endpoints) == 3


def test_load_and_parse_missing_returns_empty(tmp_path):
    module, endpoints = load_and_parse(tmp_path)
    assert endpoints == []
    assert module.name == tmp_path.name
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_parser.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'smrt_agent.docs.parser'`

- [ ] **Step 3: Implement the parser**

Create `backend/src/smrt_agent/docs/parser.py`:

```python
"""Parse .smrt/Project.md into structured doc objects."""
import re
from pathlib import Path

from smrt_agent.docs.backends import EndpointDoc, ModuleDoc

# Matches endpoint rows in the Markdown table — e.g.  | GET | /items | Yes | List items |
_ENDPOINT_ROW_RE = re.compile(
    r"^\|\s*([A-Z]+)\s*\|\s*(/[^|]*?)\s*\|\s*(Yes|No)\s*\|\s*([^|]+?)\s*\|",
    re.IGNORECASE | re.MULTILINE,
)


def parse_endpoints(project_md: str) -> list[EndpointDoc]:
    """Return EndpointDoc list from the Endpoints table in Project.md."""
    endpoints: list[EndpointDoc] = []
    for m in _ENDPOINT_ROW_RE.finditer(project_md):
        method, path, auth_str, purpose = m.groups()
        if method.strip().upper() in {"METHOD", "---"}:
            continue
        endpoints.append(
            EndpointDoc(
                method=method.strip().upper(),
                path=path.strip(),
                auth_required=auth_str.strip().lower() == "yes",
                purpose=purpose.strip(),
            )
        )
    return endpoints


def parse_module_doc(project_md: str, project_name: str) -> ModuleDoc:
    """Return a ModuleDoc from the Purpose section of Project.md."""
    purpose_m = re.search(r"## Purpose\s+(.+?)(?=\n##|\Z)", project_md, re.DOTALL)
    description = purpose_m.group(1).strip() if purpose_m else ""
    return ModuleDoc(name=project_name, description=description, file_path=".smrt/Project.md")


def load_and_parse(project_path: Path) -> tuple[ModuleDoc, list[EndpointDoc]]:
    """Read .smrt/Project.md and return (ModuleDoc, list[EndpointDoc])."""
    project_md_path = project_path / ".smrt" / "Project.md"
    if not project_md_path.exists():
        return ModuleDoc(name=project_path.name, description="", file_path=".smrt/Project.md"), []
    text = project_md_path.read_text(encoding="utf-8")
    name_m = re.search(r"^# Project:\s*(.+)$", text, re.MULTILINE)
    project_name = name_m.group(1).strip() if name_m else project_path.name
    return parse_module_doc(text, project_name), parse_endpoints(text)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_parser.py -v
```

Expected: 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/docs/parser.py backend/tests/test_doc_parser.py
git commit -m "feat: add Project.md parser extracting EndpointDoc and ModuleDoc"
```

---

### Task 7: DocService

**Files:**
- Create: `backend/src/smrt_agent/docs/service.py`
- Create: `backend/tests/test_doc_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_doc_service.py`:

```python
import asyncio
import pytest
from pathlib import Path
from smrt_agent.docs.service import generate_docs

SAMPLE_MD = """\
# Project: todo-api

## Purpose
A simple todo API.

## Endpoints
| Method | Path | Auth required | Purpose |
|--------|------|---------------|---------|
| GET | /items | No | List items |
| POST | /items | Yes | Create item |
"""


def test_generate_docs_creates_github_files(tmp_path):
    smrt_dir = tmp_path / ".smrt"
    smrt_dir.mkdir()
    (smrt_dir / "Project.md").write_text(SAMPLE_MD, encoding="utf-8")
    result = asyncio.run(generate_docs(tmp_path))
    assert result["backends"] == 2
    assert result["endpoints"] == 2
    assert (tmp_path / "docs" / "modules" / "todo-api.md").exists()
    assert (tmp_path / "docs" / "api" / "GET_items.md").exists()
    assert (tmp_path / "docs" / "api" / "POST_items.md").exists()


def test_generate_docs_creates_obsidian_files(tmp_path):
    smrt_dir = tmp_path / ".smrt"
    smrt_dir.mkdir()
    (smrt_dir / "Project.md").write_text(SAMPLE_MD, encoding="utf-8")
    asyncio.run(generate_docs(tmp_path))
    assert (tmp_path / "wiki" / "modules" / "todo-api.md").exists()
    assert (tmp_path / "wiki" / "api" / "GET_items.md").exists()


def test_generate_docs_no_project_md_returns_zero_endpoints(tmp_path):
    result = asyncio.run(generate_docs(tmp_path))
    assert result["backends"] == 2
    assert result["endpoints"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_service.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'smrt_agent.docs.service'`

- [ ] **Step 3: Implement DocService**

Create `backend/src/smrt_agent/docs/service.py`:

```python
"""DocService: parse Project.md and write docs via all enabled backends."""
from pathlib import Path

from smrt_agent.docs.backends import GitHubBackend, ObsidianBackend
from smrt_agent.docs.parser import load_and_parse


async def generate_docs(project_path: Path) -> dict[str, int]:
    """Parse .smrt/Project.md and write to GitHub + Obsidian backends.

    Returns {"backends": int, "endpoints": int}.
    """
    module, endpoints = load_and_parse(project_path)
    backends = [GitHubBackend(project_path), ObsidianBackend(project_path)]
    for backend in backends:
        await backend.upsert_module_doc(module)
        for endpoint in endpoints:
            await backend.upsert_endpoint_doc(endpoint)
    return {"backends": len(backends), "endpoints": len(endpoints)}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_doc_service.py -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/docs/service.py backend/tests/test_doc_service.py
git commit -m "feat: add DocService calling GitHubBackend and ObsidianBackend"
```

---

### Task 8: Wire DocService into runs.py

**Files:**
- Modify: `backend/src/smrt_agent/api/runs.py`

The `_run_task` function currently calls `run_reviewer()` and then updates the DB status. We add `generate_docs()` between them. The `run_reviewer()` function puts the `done` event in the queue itself; `docs_written` is put afterwards and captured in the JSONL event log (via `EventLogger`) even though the SSE stream has already closed.

- [ ] **Step 1: Add the import**

At the top of `backend/src/smrt_agent/api/runs.py`, after the existing imports, add:

```python
from smrt_agent.docs.service import generate_docs
```

- [ ] **Step 2: Add generate_docs call in _run_task**

In `_run_task`, the current structure is:

```python
    try:
        # ... DB status update to running ...
        await run_reviewer(
            project_path=Path(canonical_path),
            api_key=api_key,
            model=model,
            budget_usd=budget_usd,
            queue=queue,
        )
        final_status = "done"
    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})
        final_status = "error"
    finally:
        # ... DB status update ...
```

Change it to:

```python
    try:
        # ... DB status update to running (unchanged) ...
        await run_reviewer(
            project_path=Path(canonical_path),
            api_key=api_key,
            model=model,
            budget_usd=budget_usd,
            queue=queue,
        )
        final_status = "done"
        # Generate docs after audit completes — saved to JSONL log via EventLogger
        try:
            doc_counts = await generate_docs(Path(canonical_path))
            await queue.put({
                "type": "docs_written",
                "backends": doc_counts["backends"],
                "endpoints": doc_counts["endpoints"],
                "ts": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as doc_exc:
            await queue.put({
                "type": "docs_error",
                "error": str(doc_exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})
        final_status = "error"
    finally:
        # ... DB status update (unchanged) ...
```

- [ ] **Step 3: Run existing tests to verify nothing broke**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_runs_api.py -v
```

Expected: 3 tests PASS (no regressions)

- [ ] **Step 4: Commit**

```bash
git add backend/src/smrt_agent/api/runs.py
git commit -m "feat: call generate_docs after Reviewer audit, emit docs_written to event log"
```

---

### Task 9: Backend docs API endpoint

**Files:**
- Create: `backend/src/smrt_agent/api/docs.py`
- Modify: `backend/src/smrt_agent/main.py`
- Create: `backend/tests/test_docs_api.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_docs_api.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from smrt_agent.main import app
from smrt_agent.db.schema import init_schema
from smrt_agent.db.models import Project
from smrt_agent.api.deps import get_db


@pytest.fixture
async def test_app_with_docs(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("SMRT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("SMRT_PROJECT_ROOT_ALLOWLIST", "")

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True)
    await init_schema(engine)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with Session() as session:
        proj = Project(name="todo-api", canonical_path=str(tmp_path))
        session.add(proj)
        await session.commit()
        await session.refresh(proj)
        project_id = proj.id

    # Create some doc files in the project path
    docs_api = tmp_path / "docs" / "api"
    docs_api.mkdir(parents=True)
    (docs_api / "GET_items.md").write_text("# GET /items", encoding="utf-8")
    (docs_api / "index.md").write_text("# API Reference", encoding="utf-8")

    wiki_api = tmp_path / "wiki" / "api"
    wiki_api.mkdir(parents=True)
    (wiki_api / "GET_items.md").write_text("---\ntype: endpoint\n---\n# GET /items", encoding="utf-8")

    async def override_get_db():
        async with Session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app, project_id, tmp_path
    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_docs_returns_files(test_app_with_docs):
    test_app, project_id, _ = test_app_with_docs
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/projects/{project_id}/docs")
    assert resp.status_code == 200
    data = resp.json()
    assert "files" in data
    paths = [f["path"] for f in data["files"]]
    assert any("docs/api/GET_items.md" in p for p in paths)
    assert any("wiki/api/GET_items.md" in p for p in paths)


@pytest.mark.asyncio
async def test_list_docs_backend_field(test_app_with_docs):
    test_app, project_id, _ = test_app_with_docs
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/projects/{project_id}/docs")
    files = resp.json()["files"]
    backends = {f["backend"] for f in files}
    assert "github" in backends
    assert "obsidian" in backends


@pytest.mark.asyncio
async def test_list_docs_404_for_unknown_project(test_app_with_docs):
    test_app, _, _ = test_app_with_docs
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/projects/99999/docs")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_docs_empty_when_no_dirs(test_app_with_docs):
    test_app, _, tmp_path = test_app_with_docs
    # Create a second project with no doc dirs
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}", future=True)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    empty_path = tmp_path / "empty"
    empty_path.mkdir()
    async with Session() as session:
        proj2 = Project(name="empty-project", canonical_path=str(empty_path))
        session.add(proj2)
        await session.commit()
        await session.refresh(proj2)
        proj2_id = proj2.id
    await engine.dispose()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/projects/{proj2_id}/docs")
    assert resp.status_code == 200
    assert resp.json()["files"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_docs_api.py -v
```

Expected: FAIL with `404` (route not registered yet)

- [ ] **Step 3: Create the docs API**

Create `backend/src/smrt_agent/api/docs.py`:

```python
"""Docs API: list generated documentation files for a project."""
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project

router = APIRouter(prefix="/projects", tags=["docs"])


@router.get("/{project_id}/docs")
async def list_docs(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_path = Path(project.canonical_path)
    files: list[dict] = []

    for directory, label in [
        (project_path / "docs", "github"),
        (project_path / "wiki", "obsidian"),
    ]:
        if directory.exists():
            for f in sorted(directory.rglob("*.md")):
                files.append(
                    {
                        "backend": label,
                        "path": str(f.relative_to(project_path)).replace("\\", "/"),
                    }
                )

    return {"files": files}
```

- [ ] **Step 4: Wire the router into main.py**

Open `backend/src/smrt_agent/main.py`. It already imports and includes routers for projects, runs, qa_sessions, sandbox, and tickets. Add docs:

```python
from smrt_agent.api.docs import router as docs_router
# ...
app.include_router(docs_router, prefix="/api")
```

Exact location: add alongside the other `include_router` calls.

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest backend/tests/test_docs_api.py -v
```

Expected: 4 tests PASS

- [ ] **Step 6: Run full backend suite to verify no regressions**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest -v
```

Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/src/smrt_agent/api/docs.py backend/src/smrt_agent/main.py backend/tests/test_docs_api.py
git commit -m "feat: add GET /projects/{id}/docs endpoint listing generated doc files"
```

---

### Task 10: Frontend DocPanel component

**Files:**
- Create: `frontend/src/api/docs.ts`
- Create: `frontend/src/components/DocPanel.tsx`
- Create: `frontend/src/test/DocPanel.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/test/DocPanel.test.tsx`:

```tsx
import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { DocPanel } from '../components/DocPanel'

const mockFiles = [
  { backend: 'github', path: 'docs/api/GET_items.md' },
  { backend: 'github', path: 'docs/modules/todo-api.md' },
  { backend: 'obsidian', path: 'wiki/api/GET_items.md' },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/docs', () =>
    HttpResponse.json({ files: mockFiles }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('DocPanel', () => {
  it('shows GitHub and Obsidian as enabled chips', async () => {
    render(<DocPanel projectId={1} />)
    await waitFor(() => expect(screen.getByText(/✓ GitHub/i)).toBeInTheDocument())
    expect(screen.getByText(/✓ Obsidian/i)).toBeInTheDocument()
  })

  it('shows Jira and Confluence as coming soon', async () => {
    render(<DocPanel projectId={1} />)
    await waitFor(() => screen.getByText(/✓ GitHub/i))
    expect(screen.getByText(/Jira.*coming soon/i)).toBeInTheDocument()
    expect(screen.getByText(/Confluence.*coming soon/i)).toBeInTheDocument()
  })

  it('lists generated doc files', async () => {
    render(<DocPanel projectId={1} />)
    await waitFor(() => expect(screen.getByText('docs/api/GET_items.md')).toBeInTheDocument())
    expect(screen.getByText('docs/modules/todo-api.md')).toBeInTheDocument()
    expect(screen.getByText('wiki/api/GET_items.md')).toBeInTheDocument()
  })

  it('shows no-docs message when list is empty', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/docs', () =>
        HttpResponse.json({ files: [] }),
      ),
    )
    render(<DocPanel projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no documentation generated/i)).toBeInTheDocument(),
    )
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /d/web-project/smrt-llm-dev/frontend && npm test -- --run 2>&1 | tail -20
```

Expected: FAIL (DocPanel not found)

- [ ] **Step 3: Create the API client**

Create `frontend/src/api/docs.ts`:

```typescript
import { apiFetch } from './client'

export interface DocFile {
  backend: 'github' | 'obsidian'
  path: string
}

export async function listDocs(projectId: number, signal?: AbortSignal): Promise<DocFile[]> {
  const data = await apiFetch<{ files: DocFile[] }>(`/projects/${projectId}/docs`, { signal })
  return data.files
}
```

- [ ] **Step 4: Create the DocPanel component**

Create `frontend/src/components/DocPanel.tsx`:

```tsx
import { useState, useEffect } from 'react'
import { listDocs, type DocFile } from '../api/docs'

const BACKENDS = [
  { id: 'github', label: 'GitHub', enabled: true },
  { id: 'obsidian', label: 'Obsidian', enabled: true },
  { id: 'jira', label: 'Jira', enabled: false },
  { id: 'confluence', label: 'Confluence', enabled: false },
] as const

export function DocPanel({ projectId }: { projectId: number }) {
  const [files, setFiles] = useState<DocFile[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    listDocs(projectId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setFiles(data) })
      .catch(() => { if (!controller.signal.aborted) setFiles([]) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [projectId])

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {BACKENDS.map((b) => (
          <span
            key={b.id}
            className={`px-2 py-1 rounded text-xs font-medium ${
              b.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-400'
            }`}
          >
            {b.enabled ? `✓ ${b.label}` : `${b.label} (coming soon)`}
          </span>
        ))}
      </div>
      {loading ? (
        <p className="text-xs text-gray-400">Loading docs…</p>
      ) : files.length === 0 ? (
        <p className="text-xs text-gray-400 italic">
          No documentation generated yet. Run Init Audit to generate.
        </p>
      ) : (
        <ul className="text-xs space-y-1 font-mono">
          {files.map((f) => (
            <li key={f.path} className="text-gray-600">
              {f.path}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /d/web-project/smrt-llm-dev/frontend && npm test -- --run 2>&1 | tail -20
```

Expected: all tests PASS (previously passing + 4 new DocPanel tests)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/docs.ts frontend/src/components/DocPanel.tsx frontend/src/test/DocPanel.test.tsx
git commit -m "feat: add DocPanel component with backend chips and doc file list"
```

---

### Task 11: Wire DocPanel into ProjectDetailPage

**Files:**
- Modify: `frontend/src/pages/ProjectDetailPage.tsx`
- Modify: `frontend/src/test/ProjectDetailPage.test.tsx`

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/test/ProjectDetailPage.test.tsx`:

At the top of the file, add a mock for DocPanel alongside the existing mocks:

```tsx
vi.mock('../components/DocPanel', () => ({
  DocPanel: ({ projectId }: { projectId: number }) => (
    <div data-testid="doc-panel">DocPanel:{projectId}</div>
  ),
}))
```

Add a new test case at the bottom of the `describe` block:

```tsx
it('renders the DocPanel section', async () => {
  renderPage()
  await waitFor(() => expect(screen.getByTestId('doc-panel')).toBeInTheDocument())
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /d/web-project/smrt-llm-dev/frontend && npm test -- --run 2>&1 | tail -20
```

Expected: FAIL (`doc-panel` testid not found)

- [ ] **Step 3: Add the Documentation section to ProjectDetailPage**

In `frontend/src/pages/ProjectDetailPage.tsx`:

Add import at the top (alongside existing component imports):
```tsx
import { DocPanel } from '../components/DocPanel'
```

Add a new section at the bottom of the returned JSX, after the Bug Tickets section:

```tsx
      {/* ── Documentation ── */}
      <div className="mt-8 border-t pt-6">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Documentation
        </h2>
        <DocPanel projectId={projectId} />
      </div>
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /d/web-project/smrt-llm-dev/frontend && npm test -- --run 2>&1 | tail -20
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ProjectDetailPage.tsx frontend/src/test/ProjectDetailPage.test.tsx
git commit -m "feat: add Documentation section to ProjectDetailPage with DocPanel"
```

---

### Task 12: Full suite green + PR

**Files:** none (verification only)

- [ ] **Step 1: Run full backend test suite**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest -v 2>&1 | tail -20
```

Expected: all tests PASS (95 existing + new doc tests)

- [ ] **Step 2: Run full frontend test suite**

```bash
cd /d/web-project/smrt-llm-dev/frontend && npm test -- --run 2>&1 | tail -20
```

Expected: all tests PASS

- [ ] **Step 3: TypeScript check**

```bash
cd /d/web-project/smrt-llm-dev/frontend && npx tsc --noEmit
```

Expected: no output (zero errors)

- [ ] **Step 4: Push branch and open PR**

```bash
git push -u origin phase/5-docs
gh pr create \
  --title "P5: Documentation System — DocBackend, GitHubBackend, ObsidianBackend, DocPanel" \
  --body "Implements M5 documentation system from PRODUCTION.md §6.3"
```
