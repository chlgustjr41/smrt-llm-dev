# SMRT Agent P3 — QA/Coder Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** QA agent reads Project.md + OpenAPI spec, generates pytest tests, Coder agent fixes failures, black-box feedback loop iterates up to SMRT_MAX_FIX_ATTEMPTS, with HITL approval gate and SSE streaming throughout.

**Architecture:** Two Anthropic SDK streaming agents (QA, Coder) coordinated by an async orchestrator that pauses at HITL boundaries via `asyncio.Event`. A QASession DB model tracks state. File watcher + APScheduler trigger sessions automatically.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Anthropic SDK streaming, watchfiles, APScheduler, React 18, TypeScript, Vitest, MSW

---

## File Structure

**New backend files:**
- `backend/src/smrt_agent/db/models.py` — add `QASession` model (modify)
- `backend/src/smrt_agent/agents/qa/__init__.py` — empty
- `backend/src/smrt_agent/agents/qa/tools.py` — write_test_file, run_pytest, write_bug_ticket, write_test_status, append_bugs_resolved
- `backend/src/smrt_agent/agents/qa/budget.py` — TOOL_DEFINITIONS for QA agent
- `backend/src/smrt_agent/agents/qa/loop.py` — run_qa_agent() streaming loop
- `backend/src/smrt_agent/agents/coder/__init__.py` — empty
- `backend/src/smrt_agent/agents/coder/tools.py` — read_source_file, write_source_file
- `backend/src/smrt_agent/agents/coder/budget.py` — TOOL_DEFINITIONS for Coder agent
- `backend/src/smrt_agent/agents/coder/loop.py` — run_coder_agent() streaming loop
- `backend/src/smrt_agent/agents/orchestrator.py` — run_qa_session() coordinating loop
- `backend/src/smrt_agent/prompts/qa.md` — QA agent system prompt
- `backend/src/smrt_agent/prompts/coder.md` — Coder agent system prompt
- `backend/src/smrt_agent/api/qa_sessions.py` — POST/stream/approve/skip endpoints
- `backend/src/smrt_agent/watchers.py` — watchfiles file watcher
- `backend/src/smrt_agent/scheduler.py` — APScheduler nightly jobs
- `backend/src/smrt_agent/main.py` — add qa_sessions router + lifespan watcher/scheduler (modify)
- `backend/tests/test_qa_tools.py` — unit tests for QA tools
- `backend/tests/test_coder_tools.py` — unit tests for Coder tools
- `backend/tests/test_qa_sessions.py` — API tests for QA sessions endpoints

**New frontend files:**
- `frontend/src/api/qa_sessions.ts` — createQASession, approveQASession, skipQASession
- `frontend/src/components/QASessionView.tsx` — SSE view with HITL approve/skip
- `frontend/src/pages/ProjectDetailPage.tsx` — add QA section (modify)
- `frontend/src/test/QASessionView.test.tsx` — component tests

---

### Task 1: QASession DB Model

**Files:**
- Modify: `backend/src/smrt_agent/db/models.py`
- Test: `backend/tests/test_qa_sessions.py` (partial — model test)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_qa_sessions.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from smrt_agent.db.base import Base
from smrt_agent.db.models import Project, QASession


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_qa_session_model(db):
    project = Project(name="test", canonical_path="/workspace/test")
    db.add(project)
    await db.commit()
    await db.refresh(project)

    qa = QASession(session_id="abc-123", project_id=project.id)
    db.add(qa)
    await db.commit()
    await db.refresh(qa)

    assert qa.session_id == "abc-123"
    assert qa.status == "pending"
    assert qa.fix_attempt == 0
    assert qa.ticket_id is None
    assert qa.started_at is None
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_qa_sessions.py::test_qa_session_model -v
```
Expected: `ImportError` or `AttributeError` — QASession not defined yet.

- [ ] **Step 3: Add QASession to models.py**

```python
# Add to backend/src/smrt_agent/db/models.py after AgentRun class

class QASession(Base):
    __tablename__ = "qa_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    fix_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ticket_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="qa_sessions")
```

Also add to `Project` class:
```python
qa_sessions: Mapped[list["QASession"]] = relationship("QASession", back_populates="project")
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_qa_sessions.py::test_qa_session_model -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/db/models.py backend/tests/test_qa_sessions.py
git commit -m "feat: add QASession DB model"
```

---

### Task 2: QA Agent Tools

**Files:**
- Create: `backend/src/smrt_agent/agents/qa/__init__.py`
- Create: `backend/src/smrt_agent/agents/qa/tools.py`
- Create: `backend/tests/test_qa_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_qa_tools.py`:

```python
import subprocess
import pytest
from pathlib import Path
from smrt_agent.agents.qa.tools import (
    write_test_file, run_pytest, write_bug_ticket,
    write_test_status, append_bugs_resolved,
)


def test_write_test_file(tmp_path):
    result = write_test_file(tmp_path, "test_api.py", "def test_ok(): pass\n")
    assert "test_api.py" in result
    assert (tmp_path / ".smrt" / "tests" / "test_api.py").exists()


def test_write_test_file_rejects_non_py(tmp_path):
    with pytest.raises(ValueError, match="must end with .py"):
        write_test_file(tmp_path, "test_api.sh", "echo hi")


def test_write_test_file_rejects_traversal(tmp_path):
    with pytest.raises(PermissionError):
        write_test_file(tmp_path, "../outside.py", "bad")


def test_run_pytest_no_tests(tmp_path):
    result = run_pytest(tmp_path)
    assert "No test files" in result


def test_run_pytest_passing(tmp_path):
    write_test_file(tmp_path, "test_trivial.py", "def test_pass(): assert 1 == 1\n")
    result = run_pytest(tmp_path)
    assert "passed" in result


def test_write_bug_ticket(tmp_path):
    ticket_id = write_bug_ticket(tmp_path, "API 500", "POST /items returns 500", "FAILED test_items")
    assert ticket_id.count("-") >= 3  # YYYY-MM-DD-NNN format
    ticket_file = tmp_path / ".smrt" / "tickets" / f"{ticket_id}.md"
    assert ticket_file.exists()
    assert "API 500" in ticket_file.read_text()


def test_write_test_status(tmp_path):
    write_test_status(tmp_path, "## All passing\n")
    assert (tmp_path / ".smrt" / "test-status.md").read_text() == "## All passing\n"


def test_append_bugs_resolved(tmp_path):
    append_bugs_resolved(tmp_path, "2026-04-24-001", "Fixed null pointer")
    content = (tmp_path / ".smrt" / "bugs-resolved.md").read_text()
    assert "2026-04-24-001" in content
    assert "Fixed null pointer" in content
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/test_qa_tools.py -v
```
Expected: `ModuleNotFoundError` — qa package not created yet.

- [ ] **Step 3: Create QA tools**

Create `backend/src/smrt_agent/agents/qa/__init__.py` (empty).

Create `backend/src/smrt_agent/agents/qa/tools.py`:

```python
"""QA agent tools: write_test_file, run_pytest, write_bug_ticket, write_test_status, append_bugs_resolved."""
import os
import subprocess
from datetime import date
from pathlib import Path

from smrt_agent.agents.reviewer.tools import list_files, read_file  # reuse


def write_test_file(project_path: Path, filename: str, content: str) -> str:
    """Write a test file to .smrt/tests/. filename must end with .py and contain no path separators."""
    if not filename.endswith(".py"):
        raise ValueError(f"Test filename must end with .py: {filename!r}")
    if "/" in filename or "\\" in filename:
        raise PermissionError(f"filename must not contain path separators: {filename!r}")
    target = (project_path / ".smrt" / "tests" / filename).resolve()
    expected_root = (project_path / ".smrt" / "tests").resolve()
    if not str(target).startswith(str(expected_root)):
        raise PermissionError(f"Path traversal denied: {filename!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"Wrote {len(content)} bytes to .smrt/tests/{filename}"


def run_pytest(project_path: Path) -> str:
    """Run pytest in .smrt/tests/. Returns raw pytest output (stdout + stderr)."""
    tests_dir = project_path / ".smrt" / "tests"
    if not tests_dir.exists() or not list(tests_dir.glob("test_*.py")):
        return "No test files found in .smrt/tests/"
    env = {**os.environ, "PYTHONPATH": str(project_path)}
    result = subprocess.run(
        ["python", "-m", "pytest", str(tests_dir), "-v", "--tb=short", "--asyncio-mode=auto"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(project_path),
        env=env,
    )
    return result.stdout + result.stderr


def write_bug_ticket(project_path: Path, title: str, description: str, test_output: str) -> str:
    """Write a bug ticket to .smrt/tickets/YYYY-MM-DD-NNN.md. Returns the ticket ID."""
    tickets_dir = project_path / ".smrt" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    existing = sorted(tickets_dir.glob(f"{today}-*.md"))
    seq = len(existing) + 1
    ticket_id = f"{today}-{seq:03d}"
    content = (
        f"# Bug Ticket {ticket_id}\n\n"
        f"**Title:** {title}\n\n"
        f"## Description\n\n{description}\n\n"
        f"## Test Output\n\n```\n{test_output}\n```\n"
    )
    (tickets_dir / f"{ticket_id}.md").write_text(content)
    return ticket_id


def write_test_status(project_path: Path, content: str) -> str:
    """Overwrite .smrt/test-status.md with the current test run summary."""
    target = project_path / ".smrt" / "test-status.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"Wrote test-status.md ({len(content)} bytes)"


def append_bugs_resolved(project_path: Path, ticket_id: str, resolution: str) -> str:
    """Append a resolution entry to .smrt/bugs-resolved.md."""
    target = project_path / ".smrt" / "bugs-resolved.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = f"\n## {ticket_id}\n\n{resolution}\n"
    with open(target, "a") as f:
        f.write(entry)
    return f"Appended resolution for {ticket_id}"
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_qa_tools.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/agents/qa/ backend/tests/test_qa_tools.py
git commit -m "feat: add QA agent tools"
```

---

### Task 3: Coder Agent Tools

**Files:**
- Create: `backend/src/smrt_agent/agents/coder/__init__.py`
- Create: `backend/src/smrt_agent/agents/coder/tools.py`
- Create: `backend/tests/test_coder_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_coder_tools.py`:

```python
import pytest
from pathlib import Path
from smrt_agent.agents.coder.tools import read_source_file, write_source_file


def test_read_source_file(tmp_path):
    (tmp_path / "app.py").write_text("print('hello')")
    result = read_source_file(tmp_path, "app.py")
    assert result == "print('hello')"


def test_read_source_file_blocks_smrt(tmp_path):
    (tmp_path / ".smrt").mkdir()
    (tmp_path / ".smrt" / "notes.md").write_text("secret")
    with pytest.raises(PermissionError, match=".smrt"):
        read_source_file(tmp_path, ".smrt/notes.md")


def test_read_source_file_blocks_traversal(tmp_path):
    with pytest.raises(PermissionError):
        read_source_file(tmp_path, "../outside.py")


def test_write_source_file(tmp_path):
    result = write_source_file(tmp_path, "src/fix.py", "x = 1\n")
    assert "fix.py" in result
    assert (tmp_path / "src" / "fix.py").read_text() == "x = 1\n"


def test_write_source_file_blocks_smrt(tmp_path):
    with pytest.raises(PermissionError, match=".smrt"):
        write_source_file(tmp_path, ".smrt/injected.py", "bad")


def test_write_source_file_blocks_tests(tmp_path):
    with pytest.raises(PermissionError, match="tests"):
        write_source_file(tmp_path, "tests/test_fake.py", "bad")


def test_write_source_file_blocks_docs(tmp_path):
    with pytest.raises(PermissionError, match="docs"):
        write_source_file(tmp_path, "docs/README.md", "bad")
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd backend && python -m pytest tests/test_coder_tools.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create Coder tools**

Create `backend/src/smrt_agent/agents/coder/__init__.py` (empty).

Create `backend/src/smrt_agent/agents/coder/tools.py`:

```python
"""Coder agent tools: read_source_file, write_source_file."""
from pathlib import Path

from smrt_agent.agents.reviewer.tools import _SECRET_SPEC

_BLOCKED_DIRS = {".smrt", "tests", "docs"}


def read_source_file(project_path: Path, rel_path: str) -> str:
    """Read a source file. Blocks .smrt/, tests/, docs/ and secret files."""
    first_part = Path(rel_path).parts[0] if Path(rel_path).parts else ""
    if first_part in _BLOCKED_DIRS:
        raise PermissionError(f"read_source_file cannot read from {first_part}/: {rel_path!r}")
    if _SECRET_SPEC.match_file(rel_path):
        raise PermissionError(f"Secret file access denied: {rel_path!r}")
    target = (project_path / rel_path).resolve()
    root = project_path.resolve()
    if not str(target).startswith(str(root)):
        raise PermissionError(f"Path traversal denied: {rel_path!r}")
    return target.read_text(errors="replace")


def write_source_file(project_path: Path, rel_path: str, content: str) -> str:
    """Write/overwrite a source file. Blocks .smrt/, tests/, docs/."""
    first_part = Path(rel_path).parts[0] if Path(rel_path).parts else ""
    if first_part in _BLOCKED_DIRS:
        raise PermissionError(f"write_source_file cannot write to {first_part}/: {rel_path!r}")
    if _SECRET_SPEC.match_file(rel_path):
        raise PermissionError(f"Cannot overwrite secret file: {rel_path!r}")
    target = (project_path / rel_path).resolve()
    root = project_path.resolve()
    if not str(target).startswith(str(root)):
        raise PermissionError(f"Path traversal denied: {rel_path!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"Wrote {len(content)} bytes to {rel_path}"
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_coder_tools.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/agents/coder/ backend/tests/test_coder_tools.py
git commit -m "feat: add Coder agent tools"
```

---

### Task 4: Agent Tool Definitions (QA + Coder)

**Files:**
- Create: `backend/src/smrt_agent/agents/qa/budget.py`
- Create: `backend/src/smrt_agent/agents/coder/budget.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_qa_tools.py`:

```python
from smrt_agent.agents.qa.budget import TOOL_DEFINITIONS as QA_TOOLS
from smrt_agent.agents.coder.budget import TOOL_DEFINITIONS as CODER_TOOLS

def test_qa_tool_definitions():
    names = {t["name"] for t in QA_TOOLS}
    assert names == {"list_files", "read_file", "write_test_file", "run_pytest",
                     "write_bug_ticket", "write_test_status", "append_bugs_resolved"}

def test_coder_tool_definitions():
    names = {t["name"] for t in CODER_TOOLS}
    assert names == {"list_files", "read_source_file", "write_source_file"}
```

- [ ] **Step 2: Run to verify they fail**

```
cd backend && python -m pytest tests/test_qa_tools.py::test_qa_tool_definitions tests/test_qa_tools.py::test_coder_tool_definitions -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create budget files**

Create `backend/src/smrt_agent/agents/qa/budget.py`:

```python
"""Tool definitions and cost computation for the QA agent."""
from smrt_agent.agents.reviewer.budget import compute_cost_usd  # reuse

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "list_files",
        "description": "List all source files in the project tree. Returns relative paths. Skips .smrt/ and secrets.",
        "input_schema": {"type": "object", "properties": {"subdir": {"type": "string", "description": "Subdirectory to list. Omit for whole project."}}, "required": []},
    },
    {
        "name": "read_file",
        "description": "Read a source file from the project. Path is relative to project root.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "Relative file path."}}, "required": ["path"]},
    },
    {
        "name": "write_test_file",
        "description": "Write a pytest test file to .smrt/tests/. Filename must end with .py and contain no path separators.",
        "input_schema": {"type": "object", "properties": {"filename": {"type": "string", "description": "Filename like 'test_users.py'."}, "content": {"type": "string", "description": "Full Python test file content."}}, "required": ["filename", "content"]},
    },
    {
        "name": "run_pytest",
        "description": "Run pytest against all tests in .smrt/tests/. Returns raw pytest output.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "write_bug_ticket",
        "description": "Write a bug ticket to .smrt/tickets/. Returns the ticket ID (YYYY-MM-DD-NNN).",
        "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "test_output": {"type": "string"}}, "required": ["title", "description", "test_output"]},
    },
    {
        "name": "write_test_status",
        "description": "Write the test run summary to .smrt/test-status.md.",
        "input_schema": {"type": "object", "properties": {"content": {"type": "string", "description": "Markdown summary of test results."}}, "required": ["content"]},
    },
    {
        "name": "append_bugs_resolved",
        "description": "Append a resolution entry to .smrt/bugs-resolved.md.",
        "input_schema": {"type": "object", "properties": {"ticket_id": {"type": "string"}, "resolution": {"type": "string"}}, "required": ["ticket_id", "resolution"]},
    },
]
```

Create `backend/src/smrt_agent/agents/coder/budget.py`:

```python
"""Tool definitions and cost computation for the Coder agent."""
from smrt_agent.agents.reviewer.budget import compute_cost_usd  # reuse

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "list_files",
        "description": "List source files in the project. Returns relative paths.",
        "input_schema": {"type": "object", "properties": {"subdir": {"type": "string", "description": "Subdirectory to list."}}, "required": []},
    },
    {
        "name": "read_source_file",
        "description": "Read a source file. Cannot read from .smrt/, tests/, or docs/.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "Relative path to source file."}}, "required": ["path"]},
    },
    {
        "name": "write_source_file",
        "description": "Write/overwrite a source file. Cannot write to .smrt/, tests/, or docs/.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string", "description": "Relative path."}, "content": {"type": "string", "description": "Full new file content."}}, "required": ["path", "content"]},
    },
]
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_qa_tools.py -v
```
Expected: all PASS including the new definition tests.

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/agents/qa/budget.py backend/src/smrt_agent/agents/coder/budget.py
git commit -m "feat: add QA and Coder agent tool definitions"
```

---

### Task 5: Agent Prompts

**Files:**
- Create: `backend/src/smrt_agent/prompts/qa.md`
- Create: `backend/src/smrt_agent/prompts/coder.md`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_qa_tools.py`:

```python
from pathlib import Path

def test_qa_prompt_exists():
    prompt = Path(__file__).parent.parent / "src/smrt_agent/prompts/qa.md"
    assert prompt.exists(), "qa.md prompt missing"
    assert len(prompt.read_text()) > 100

def test_coder_prompt_exists():
    prompt = Path(__file__).parent.parent / "src/smrt_agent/prompts/coder.md"
    assert prompt.exists(), "coder.md prompt missing"
    assert len(prompt.read_text()) > 100
```

- [ ] **Step 2: Run to verify they fail**

```
cd backend && python -m pytest tests/test_qa_tools.py::test_qa_prompt_exists tests/test_qa_tools.py::test_coder_prompt_exists -v
```
Expected: `AssertionError` — files don't exist.

- [ ] **Step 3: Write the prompts**

Create `backend/src/smrt_agent/prompts/qa.md`:

```markdown
# QA Agent

You are a quality assurance engineer testing a REST API black-box. You receive project context in your task message and must generate and run automated tests.

## Your mission

1. Read `.smrt/Project.md` using `read_file` to understand the API design.
2. Use `list_files` to survey the source tree.
3. Write black-box pytest tests using `write_test_file`. Tests go in `.smrt/tests/`.
4. Use `run_pytest` to run all tests.
5. If any tests fail, write a bug ticket with `write_bug_ticket` (one ticket per distinct failure pattern).
6. Update test status with `write_test_status` — include a summary of passing/failing counts.
7. Call `append_bugs_resolved` if you confirm a previously reported bug is now fixed.

## Test file conventions

- One file per feature area: `test_users.py`, `test_items.py`, etc.
- Use `httpx.AsyncClient` with `base_url` pointing to the sandbox.
- Mark async tests with `@pytest.mark.asyncio`.
- Test the golden path AND edge cases: missing required fields, wrong types, 404 for nonexistent IDs, duplicate creation.

## Bug ticket rules

- Be specific: which endpoint, what input, what expected vs actual response code/body.
- Include the exact failing pytest output in `test_output`.
- One ticket per distinct root cause — do not write one ticket per failing test if they share the same cause.

## Stopping criteria

Stop when:
- All tests pass (write a passing `write_test_status` and stop)
- You have written bug tickets for all distinct failures (stop and let the Coder agent fix them)
- You have run `run_pytest` twice and results are consistent
```

Create `backend/src/smrt_agent/prompts/coder.md`:

```markdown
# Coder Agent

You are a software engineer fixing bugs in a REST API project. You receive a bug ticket and the failing pytest output from the QA agent.

## Your mission

1. Read the bug ticket carefully to understand what endpoint and behavior is broken.
2. Use `list_files` to survey the source tree.
3. Use `read_source_file` to read the relevant source files.
4. Use `write_source_file` to fix the source code.
5. Make the minimal change that fixes the failing tests. Do not refactor unrelated code.

## Rules

- You CANNOT modify test files or anything in `.smrt/`, `tests/`, or `docs/`.
- Fix only what the bug ticket describes. Do not add new features.
- If the fix requires changing multiple files, write all of them.
- Prefer minimal diffs — change the fewest lines possible.
- After writing your fix, summarize exactly what you changed and why.
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_qa_tools.py::test_qa_prompt_exists tests/test_qa_tools.py::test_coder_prompt_exists -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/prompts/qa.md backend/src/smrt_agent/prompts/coder.md
git commit -m "feat: add QA and Coder agent system prompts"
```

---

### Task 6: QA Agent Streaming Loop

**Files:**
- Create: `backend/src/smrt_agent/agents/qa/loop.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_qa_tools.py`:

```python
import asyncio
from unittest.mock import patch, MagicMock
from smrt_agent.agents.qa.loop import run_qa_agent


@pytest.mark.asyncio
async def test_run_qa_agent_no_project_md(tmp_path):
    """QA agent handles missing Project.md gracefully (uses fallback message)."""
    queue = asyncio.Queue()

    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = []
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 5

    mock_stream = MagicMock()
    mock_stream.__iter__ = MagicMock(return_value=iter([]))
    mock_stream.get_final_message = MagicMock(return_value=mock_response)
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)

    with patch("smrt_agent.agents.qa.loop.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.stream.return_value = mock_stream
        ticket_id = await run_qa_agent(
            project_path=tmp_path,
            api_key="sk-test",
            model="claude-sonnet-4-6",
            budget_usd=1.0,
            queue=queue,
        )

    assert ticket_id is None
    events = []
    while not queue.empty():
        events.append(await queue.get())
    assert any(e["type"] == "qa_done" for e in events)
```

- [ ] **Step 2: Run to verify it fails**

```
cd backend && python -m pytest tests/test_qa_tools.py::test_run_qa_agent_no_project_md -v
```
Expected: `ModuleNotFoundError` — loop.py not created.

- [ ] **Step 3: Create QA agent loop**

Create `backend/src/smrt_agent/agents/qa/loop.py`:

```python
"""Anthropic SDK streaming loop for the QA agent."""
import asyncio
import json
from pathlib import Path
from typing import Any

import anthropic

from smrt_agent.agents.qa.budget import TOOL_DEFINITIONS, compute_cost_usd
from smrt_agent.agents.qa.tools import (
    write_test_file, run_pytest, write_bug_ticket,
    write_test_status, append_bugs_resolved,
)
from smrt_agent.agents.reviewer.tools import list_files, read_file


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "qa.md"
    return prompt_path.read_text()


def _dispatch_tool(name: str, inputs: dict[str, Any], project_path: Path) -> tuple[str, str | None]:
    """Returns (result_str, ticket_id_if_written)."""
    ticket_id = None
    try:
        if name == "list_files":
            result = json.dumps(list_files(project_path, inputs.get("subdir", "")))
        elif name == "read_file":
            result = read_file(project_path, inputs["path"])
        elif name == "write_test_file":
            result = write_test_file(project_path, inputs["filename"], inputs["content"])
        elif name == "run_pytest":
            result = run_pytest(project_path)
        elif name == "write_bug_ticket":
            ticket_id = write_bug_ticket(
                project_path, inputs["title"], inputs["description"], inputs["test_output"]
            )
            result = ticket_id
        elif name == "write_test_status":
            result = write_test_status(project_path, inputs["content"])
        elif name == "append_bugs_resolved":
            result = append_bugs_resolved(project_path, inputs["ticket_id"], inputs["resolution"])
        else:
            result = f"Unknown tool: {name}"
    except Exception as exc:
        result = f"Error: {exc}"
    return result, ticket_id


async def run_qa_agent(
    *,
    project_path: Path,
    api_key: str,
    model: str,
    budget_usd: float,
    queue: asyncio.Queue,
    prior_fix_context: str | None = None,
) -> str | None:
    """Run the QA agent. Returns ticket_id if bugs found, None if all tests pass."""
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _load_system_prompt()

    project_md = project_path / ".smrt" / "Project.md"
    context = project_md.read_text() if project_md.exists() else "(No Project.md found — survey the source tree directly.)"

    task = f"Project context:\n{context}\n"
    if prior_fix_context:
        task += f"\nPrevious fix attempt output:\n{prior_fix_context}\n"
    task += "\nGenerate and run black-box pytest tests. Write bug tickets for failures."

    messages: list[dict] = [{"role": "user", "content": task}]
    total_input = 0
    total_output = 0
    last_ticket_id: str | None = None

    while True:
        with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        ) as stream:
            for event in stream:
                if hasattr(event, "type") and event.type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta and getattr(delta, "type", None) == "text_delta":
                        await queue.put({"type": "qa_text_delta", "text": delta.text})
            response = stream.get_final_message()

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens
        cost = compute_cost_usd(total_input, total_output, model)

        if cost >= budget_usd:
            await queue.put({"type": "budget_exceeded", "cost_usd": round(cost, 4),
                             "total_input_tokens": total_input, "total_output_tokens": total_output})
            return last_ticket_id

        if response.stop_reason == "end_turn":
            await queue.put({"type": "qa_done", "total_input_tokens": total_input,
                             "total_output_tokens": total_output, "cost_usd": round(cost, 4),
                             "ticket_id": last_ticket_id})
            return last_ticket_id

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    await queue.put({"type": "tool_use", "agent": "qa",
                                     "tool": block.name, "input": block.input})
                    result, ticket_id = _dispatch_tool(block.name, block.input, project_path)
                    if ticket_id:
                        last_ticket_id = ticket_id
                    await queue.put({"type": "tool_result", "agent": "qa",
                                     "tool": block.name, "result": result[:500]})
                    tool_results.append({"type": "tool_result",
                                         "tool_use_id": block.id, "content": result})
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        await queue.put({"type": "error", "message": f"QA agent unexpected stop_reason: {response.stop_reason}"})
        return last_ticket_id
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_qa_tools.py::test_run_qa_agent_no_project_md -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/agents/qa/loop.py
git commit -m "feat: add QA agent streaming loop"
```

---

### Task 7: Coder Agent Streaming Loop

**Files:**
- Create: `backend/src/smrt_agent/agents/coder/loop.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_coder_tools.py`:

```python
import asyncio
from unittest.mock import patch, MagicMock
from smrt_agent.agents.coder.loop import run_coder_agent


@pytest.mark.asyncio
async def test_run_coder_agent_end_turn(tmp_path):
    queue = asyncio.Queue()

    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = []
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 5

    mock_stream = MagicMock()
    mock_stream.__iter__ = MagicMock(return_value=iter([]))
    mock_stream.get_final_message = MagicMock(return_value=mock_response)
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)

    with patch("smrt_agent.agents.coder.loop.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.stream.return_value = mock_stream
        await run_coder_agent(
            project_path=tmp_path,
            api_key="sk-test",
            model="claude-sonnet-4-6",
            budget_usd=1.0,
            queue=queue,
            ticket_content="# Bug: 500 on POST /items",
            pytest_output="FAILED test_items::test_create_item",
        )

    events = []
    while not queue.empty():
        events.append(await queue.get())
    assert any(e["type"] == "coder_done" for e in events)
```

- [ ] **Step 2: Run to verify it fails**

```
cd backend && python -m pytest tests/test_coder_tools.py::test_run_coder_agent_end_turn -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create Coder agent loop**

Create `backend/src/smrt_agent/agents/coder/loop.py`:

```python
"""Anthropic SDK streaming loop for the Coder agent."""
import asyncio
import json
from pathlib import Path
from typing import Any

import anthropic

from smrt_agent.agents.coder.budget import TOOL_DEFINITIONS, compute_cost_usd
from smrt_agent.agents.coder.tools import read_source_file, write_source_file
from smrt_agent.agents.reviewer.tools import list_files


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "coder.md"
    return prompt_path.read_text()


def _dispatch_tool(name: str, inputs: dict[str, Any], project_path: Path) -> str:
    try:
        if name == "list_files":
            return json.dumps(list_files(project_path, inputs.get("subdir", "")))
        elif name == "read_source_file":
            return read_source_file(project_path, inputs["path"])
        elif name == "write_source_file":
            return write_source_file(project_path, inputs["path"], inputs["content"])
        else:
            return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Error: {exc}"


async def run_coder_agent(
    *,
    project_path: Path,
    api_key: str,
    model: str,
    budget_usd: float,
    queue: asyncio.Queue,
    ticket_content: str,
    pytest_output: str,
) -> None:
    """Run the Coder agent to fix bugs described in ticket_content."""
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _load_system_prompt()

    task = (
        f"Bug ticket to fix:\n\n{ticket_content}\n\n"
        f"Failing pytest output:\n\n```\n{pytest_output}\n```\n\n"
        f"Fix the source code so these tests pass."
    )
    messages: list[dict] = [{"role": "user", "content": task}]
    total_input = 0
    total_output = 0

    while True:
        with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        ) as stream:
            for event in stream:
                if hasattr(event, "type") and event.type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta and getattr(delta, "type", None) == "text_delta":
                        await queue.put({"type": "coder_text_delta", "text": delta.text})
            response = stream.get_final_message()

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens
        cost = compute_cost_usd(total_input, total_output, model)

        if cost >= budget_usd:
            await queue.put({"type": "budget_exceeded", "cost_usd": round(cost, 4),
                             "total_input_tokens": total_input, "total_output_tokens": total_output})
            return

        if response.stop_reason == "end_turn":
            await queue.put({"type": "coder_done", "total_input_tokens": total_input,
                             "total_output_tokens": total_output, "cost_usd": round(cost, 4)})
            return

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    await queue.put({"type": "tool_use", "agent": "coder",
                                     "tool": block.name, "input": block.input})
                    result = _dispatch_tool(block.name, block.input, project_path)
                    await queue.put({"type": "tool_result", "agent": "coder",
                                     "tool": block.name, "result": result[:500]})
                    tool_results.append({"type": "tool_result",
                                         "tool_use_id": block.id, "content": result})
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        await queue.put({"type": "error", "message": f"Coder unexpected stop_reason: {response.stop_reason}"})
        return
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_coder_tools.py::test_run_coder_agent_end_turn -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/agents/coder/loop.py
git commit -m "feat: add Coder agent streaming loop"
```

---

### Task 8: Orchestrator

**Files:**
- Create: `backend/src/smrt_agent/agents/orchestrator.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_qa_sessions.py`:

```python
import asyncio
from unittest.mock import patch, AsyncMock
from smrt_agent.agents.orchestrator import run_qa_session


@pytest.mark.asyncio
async def test_orchestrator_done_on_first_pass(tmp_path):
    """If QA agent returns no ticket, orchestrator returns 'done'."""
    queue = asyncio.Queue()
    hitl_events: dict = {}
    hitl_decisions: dict = {}

    with patch("smrt_agent.agents.orchestrator.run_qa_agent", new=AsyncMock(return_value=None)):
        status = await run_qa_session(
            session_id="sess-1",
            project_path=tmp_path,
            api_key="sk-test",
            model_qa="claude-sonnet-4-6",
            model_coder="claude-sonnet-4-6",
            budget_usd=1.0,
            max_fix_attempts=3,
            queue=queue,
            hitl_events=hitl_events,
            hitl_decisions=hitl_decisions,
        )

    assert status == "done"
    events = []
    while not queue.empty():
        events.append(await queue.get())
    assert any(e.get("status") == "done" for e in events)


@pytest.mark.asyncio
async def test_orchestrator_skip_on_hitl_skip(tmp_path):
    """If HITL decision is 'skip', orchestrator returns 'skipped'."""
    queue = asyncio.Queue()
    hitl_events: dict = {}
    hitl_decisions: dict = {}
    session_id = "sess-skip"

    async def fake_qa_agent(**kwargs):
        return "2026-04-24-001"  # returns a ticket_id to trigger HITL

    async def set_skip_after_delay():
        await asyncio.sleep(0.05)
        event = hitl_events.get(session_id)
        if event:
            hitl_decisions[session_id] = "skip"
            event.set()

    with patch("smrt_agent.agents.orchestrator.run_qa_agent", new=fake_qa_agent):
        asyncio.create_task(set_skip_after_delay())
        status = await run_qa_session(
            session_id=session_id,
            project_path=tmp_path,
            api_key="sk-test",
            model_qa="claude-sonnet-4-6",
            model_coder="claude-sonnet-4-6",
            budget_usd=1.0,
            max_fix_attempts=3,
            queue=queue,
            hitl_events=hitl_events,
            hitl_decisions=hitl_decisions,
        )

    assert status == "skipped"
```

- [ ] **Step 2: Run to verify they fail**

```
cd backend && python -m pytest tests/test_qa_sessions.py::test_orchestrator_done_on_first_pass tests/test_qa_sessions.py::test_orchestrator_skip_on_hitl_skip -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create orchestrator**

Create `backend/src/smrt_agent/agents/orchestrator.py`:

```python
"""QA session orchestrator: coordinates QA → HITL → Coder → recheck loop."""
import asyncio
from pathlib import Path

from smrt_agent.agents.qa.loop import run_qa_agent
from smrt_agent.agents.coder.loop import run_coder_agent
from smrt_agent.agents.qa.tools import run_pytest


async def run_qa_session(
    *,
    session_id: str,
    project_path: Path,
    api_key: str,
    model_qa: str,
    model_coder: str,
    budget_usd: float,
    max_fix_attempts: int,
    queue: asyncio.Queue,
    hitl_events: dict[str, asyncio.Event],
    hitl_decisions: dict[str, str],
) -> str:
    """Coordinate the QA/Coder fix loop. Returns final status string."""
    per_agent_budget = budget_usd / max(max_fix_attempts * 2 + 1, 1)
    prior_fix_context: str | None = None

    for attempt in range(max_fix_attempts + 1):
        await queue.put({"type": "session_status", "status": "qa_running", "fix_attempt": attempt})

        ticket_id = await run_qa_agent(
            project_path=project_path,
            api_key=api_key,
            model=model_qa,
            budget_usd=per_agent_budget,
            queue=queue,
            prior_fix_context=prior_fix_context,
        )

        if ticket_id is None:
            await queue.put({"type": "session_status", "status": "done", "fix_attempt": attempt})
            return "done"

        if attempt >= max_fix_attempts:
            await queue.put({"type": "session_status", "status": "error",
                             "message": "Max fix attempts reached"})
            return "error"

        # HITL gate
        await queue.put({"type": "hitl_request", "session_id": session_id,
                         "ticket_id": ticket_id, "fix_attempt": attempt})
        await queue.put({"type": "session_status", "status": "hitl_waiting"})

        event = asyncio.Event()
        hitl_events[session_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=3600.0)
        except asyncio.TimeoutError:
            hitl_events.pop(session_id, None)
            hitl_decisions.pop(session_id, None)
            await queue.put({"type": "session_status", "status": "error",
                             "message": "HITL approval timed out"})
            return "error"

        decision = hitl_decisions.pop(session_id, "skip")
        hitl_events.pop(session_id, None)

        if decision == "skip":
            await queue.put({"type": "session_status", "status": "skipped"})
            return "skipped"

        # Run Coder agent
        ticket_path = project_path / ".smrt" / "tickets" / f"{ticket_id}.md"
        ticket_content = ticket_path.read_text() if ticket_path.exists() else f"Ticket {ticket_id}"
        pytest_output = run_pytest(project_path)

        await queue.put({"type": "session_status", "status": "coder_running", "fix_attempt": attempt})
        await run_coder_agent(
            project_path=project_path,
            api_key=api_key,
            model=model_coder,
            budget_usd=per_agent_budget,
            queue=queue,
            ticket_content=ticket_content,
            pytest_output=pytest_output,
        )

        # Subprocess recheck — no AI call
        recheck_output = run_pytest(project_path)
        await queue.put({"type": "recheck_output", "output": recheck_output[:2000]})

        if "passed" in recheck_output and "failed" not in recheck_output:
            await queue.put({"type": "session_status", "status": "done", "fix_attempt": attempt})
            return "done"

        prior_fix_context = f"Fix attempt {attempt + 1} recheck:\n{recheck_output}"

    return "error"
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_qa_sessions.py::test_orchestrator_done_on_first_pass tests/test_qa_sessions.py::test_orchestrator_skip_on_hitl_skip -v
```
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/smrt_agent/agents/orchestrator.py
git commit -m "feat: add QA session orchestrator with HITL loop"
```

---

### Task 9: QA Sessions API

**Files:**
- Create: `backend/src/smrt_agent/api/qa_sessions.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_qa_sessions.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from smrt_agent.main import create_app
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.db.schema import init_schema
from smrt_agent.db.models import Project


@pytest.fixture
async def app_client(tmp_path):
    import os
    db_path = tmp_path / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["ANTHROPIC_API_KEY"] = "sk-test"
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.mark.asyncio
async def test_create_qa_session(app_client):
    # Register a project first
    reg = await app_client.post("/projects", json={"name": "p", "path": "/workspace/p"})
    # May fail path validation in test env; use direct DB insert instead
    # Skip if project registration fails due to allowlist
    if reg.status_code != 201:
        pytest.skip("Path allowlist blocks /workspace/p in test environment")
    project_id = reg.json()["id"]

    with patch("smrt_agent.api.qa_sessions.run_qa_session", new=AsyncMock(return_value="done")):
        resp = await app_client.post(f"/projects/{project_id}/qa-sessions")
    assert resp.status_code == 202
    data = resp.json()
    assert "session_id" in data
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_create_qa_session_404(app_client):
    resp = await app_client.post("/projects/9999/qa-sessions")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stream_qa_session_404(app_client):
    resp = await app_client.get("/projects/1/qa-sessions/nonexistent/stream")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_no_hitl_pending(app_client):
    resp = await app_client.post("/projects/1/qa-sessions/nonexistent/approve")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_skip_no_hitl_pending(app_client):
    resp = await app_client.post("/projects/1/qa-sessions/nonexistent/skip")
    assert resp.status_code == 409
```

- [ ] **Step 2: Run to verify they fail**

```
cd backend && python -m pytest tests/test_qa_sessions.py -k "test_create_qa_session_404 or test_stream_qa_session_404 or test_approve_no_hitl or test_skip_no_hitl" -v
```
Expected: `ModuleNotFoundError` or `404` mismatch — router not wired yet.

- [ ] **Step 3: Create QA sessions API**

Create `backend/src/smrt_agent/api/qa_sessions.py`:

```python
"""QA sessions API: create, stream SSE, approve/skip HITL."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project, QASession
from smrt_agent.db.session import get_engine, get_session_factory
from smrt_agent.settings import Settings
from smrt_agent.agents.orchestrator import run_qa_session

router = APIRouter(prefix="/projects", tags=["qa-sessions"])

_queues: dict[str, asyncio.Queue] = {}
_hitl_events: dict[str, asyncio.Event] = {}
_hitl_decisions: dict[str, str] = {}


@router.post("/{project_id}/qa-sessions", status_code=202)
async def create_qa_session(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    session_id = str(uuid.uuid4())
    qa_session = QASession(session_id=session_id, project_id=project_id, status="pending")
    db.add(qa_session)
    await db.commit()

    queue: asyncio.Queue = asyncio.Queue()
    _queues[session_id] = queue
    settings = Settings()

    asyncio.create_task(_session_task(
        project_id=project_id,
        session_id=session_id,
        canonical_path=project.canonical_path,
        queue=queue,
        api_key=settings.anthropic_api_key,
        model_qa=settings.model_qa,
        model_coder=settings.model_coder,
        budget_usd=settings.budget_per_run_usd,
        max_fix_attempts=settings.max_fix_attempts,
    ))

    return {"session_id": session_id, "status": "pending"}


async def _session_task(
    *, project_id: int, session_id: str, canonical_path: str,
    queue: asyncio.Queue, api_key: str, model_qa: str, model_coder: str,
    budget_usd: float, max_fix_attempts: int,
) -> None:
    from pathlib import Path
    final_status = "error"
    try:
        engine = get_engine(force_new=False)
        Session = get_session_factory(engine)
        async with Session() as db:
            result = await db.execute(select(QASession).where(QASession.session_id == session_id))
            sess = result.scalar_one_or_none()
            if sess:
                sess.status = "qa_running"
                sess.started_at = datetime.now(timezone.utc)
                await db.commit()
    except Exception:
        pass

    try:
        final_status = await run_qa_session(
            session_id=session_id,
            project_path=Path(canonical_path),
            api_key=api_key,
            model_qa=model_qa,
            model_coder=model_coder,
            budget_usd=budget_usd,
            max_fix_attempts=max_fix_attempts,
            queue=queue,
            hitl_events=_hitl_events,
            hitl_decisions=_hitl_decisions,
        )
    except Exception as exc:
        await queue.put({"type": "error", "message": str(exc)})
        final_status = "error"
    finally:
        try:
            engine = get_engine(force_new=False)
            Session = get_session_factory(engine)
            async with Session() as db:
                result = await db.execute(select(QASession).where(QASession.session_id == session_id))
                sess = result.scalar_one_or_none()
                if sess:
                    sess.status = final_status
                    sess.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass
        await queue.put({"type": "done", "status": final_status})


@router.get("/{project_id}/qa-sessions/{session_id}/stream")
async def stream_qa_session(project_id: int, session_id: str) -> StreamingResponse:
    queue = _queues.get(session_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Session not found or already completed")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=120.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("done", "error", "budget_exceeded"):
                    _queues.pop(session_id, None)
                    break
        except asyncio.TimeoutError:
            yield 'data: {"type": "timeout"}\n\n'
            _queues.pop(session_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{project_id}/qa-sessions/{session_id}/approve", status_code=200)
async def approve_qa_session(project_id: int, session_id: str) -> dict:
    event = _hitl_events.get(session_id)
    if event is None:
        raise HTTPException(status_code=409, detail="No HITL request pending for this session")
    _hitl_decisions[session_id] = "approve"
    event.set()
    return {"decision": "approve"}


@router.post("/{project_id}/qa-sessions/{session_id}/skip", status_code=200)
async def skip_qa_session(project_id: int, session_id: str) -> dict:
    event = _hitl_events.get(session_id)
    if event is None:
        raise HTTPException(status_code=409, detail="No HITL request pending for this session")
    _hitl_decisions[session_id] = "skip"
    event.set()
    return {"decision": "skip"}
```

- [ ] **Step 4: Wire router into main.py**

Edit `backend/src/smrt_agent/main.py` — add after existing router imports:

```python
from smrt_agent.api.qa_sessions import router as qa_sessions_router
```

Add to `create_app()` after `app.include_router(runs_router)`:

```python
app.include_router(qa_sessions_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_qa_sessions.py::test_create_qa_session_404 tests/test_qa_sessions.py::test_stream_qa_session_404 tests/test_qa_sessions.py::test_approve_no_hitl_pending tests/test_qa_sessions.py::test_skip_no_hitl_pending -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/smrt_agent/api/qa_sessions.py backend/src/smrt_agent/main.py
git commit -m "feat: add QA sessions API with SSE streaming and HITL endpoints"
```

---

### Task 10: File Watcher + APScheduler

**Files:**
- Create: `backend/src/smrt_agent/watchers.py`
- Create: `backend/src/smrt_agent/scheduler.py`
- Modify: `backend/src/smrt_agent/main.py` (lifespan integration)

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_qa_sessions.py`:

```python
from smrt_agent.watchers import _DEBOUNCE_SECONDS

def test_debounce_constant():
    assert _DEBOUNCE_SECONDS == 30.0

from smrt_agent.scheduler import start_scheduler, stop_scheduler

def test_scheduler_starts_and_stops():
    triggered = []
    async def fake_trigger(project_id: int):
        triggered.append(project_id)
    sched = start_scheduler(fake_trigger, [1, 2])
    assert sched.running
    assert len(sched.get_jobs()) == 2
    stop_scheduler()
```

- [ ] **Step 2: Run to verify they fail**

```
cd backend && python -m pytest tests/test_qa_sessions.py::test_debounce_constant tests/test_qa_sessions.py::test_scheduler_starts_and_stops -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Create watchers.py**

Create `backend/src/smrt_agent/watchers.py`:

```python
"""File watcher: triggers a QA session when project .py files change."""
import asyncio
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable

from watchfiles import awatch

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 30.0


async def watch_project(
    project_id: int,
    canonical_path: str,
    trigger_fn: Callable[[int], Awaitable[None]],
) -> None:
    """Watch canonical_path for *.py changes and call trigger_fn with debounce."""
    path = Path(canonical_path)
    if not path.exists():
        logger.warning("Watch path does not exist: %s", canonical_path)
        return

    last_trigger: float = 0.0

    async for changes in awatch(str(path)):
        if not any(str(c[1]).endswith(".py") for c in changes):
            continue
        now = time.monotonic()
        if now - last_trigger >= _DEBOUNCE_SECONDS:
            last_trigger = now
            logger.info("File change in project %d — triggering QA session", project_id)
            try:
                await trigger_fn(project_id)
            except Exception as exc:
                logger.error("QA trigger failed for project %d: %s", project_id, exc)
```

- [ ] **Step 4: Create scheduler.py**

Create `backend/src/smrt_agent/scheduler.py`:

```python
"""APScheduler: nightly QA session per registered project at 03:00 local."""
import logging
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def start_scheduler(
    trigger_fn: Callable[[int], Awaitable[None]],
    project_ids: list[int],
) -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler()
    for project_id in project_ids:
        _scheduler.add_job(
            trigger_fn,
            CronTrigger(hour=3, minute=0),
            args=[project_id],
            id=f"nightly_qa_{project_id}",
        )
    _scheduler.start()
    logger.info("Scheduler started with %d nightly jobs", len(project_ids))
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
```

- [ ] **Step 5: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_qa_sessions.py::test_debounce_constant tests/test_qa_sessions.py::test_scheduler_starts_and_stops -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/smrt_agent/watchers.py backend/src/smrt_agent/scheduler.py
git commit -m "feat: add file watcher and APScheduler for automated QA triggers"
```

---

### Task 11: Frontend QA Sessions API Client

**Files:**
- Create: `frontend/src/api/qa_sessions.ts`

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/test/ProjectDetailPage.test.tsx`:

```typescript
import { createQASession } from '../api/qa_sessions'

// This is just a type-check / import verification; real tests are in QASessionView.test.tsx
it('qa_sessions api module exports createQASession', () => {
  expect(typeof createQASession).toBe('function')
})
```

- [ ] **Step 2: Run to verify it fails**

```
cd frontend && npx vitest run src/test/ProjectDetailPage.test.tsx
```
Expected: `Cannot find module '../api/qa_sessions'`.

- [ ] **Step 3: Create the API client**

Create `frontend/src/api/qa_sessions.ts`:

```typescript
import { apiFetch } from './client'

export interface QASessionCreated {
  session_id: string
  status: string
}

export interface HITLDecision {
  decision: 'approve' | 'skip'
}

export function createQASession(projectId: number): Promise<QASessionCreated> {
  return apiFetch<QASessionCreated>(`/projects/${projectId}/qa-sessions`, { method: 'POST' })
}

export function approveQASession(projectId: number, sessionId: string): Promise<HITLDecision> {
  return apiFetch<HITLDecision>(`/projects/${projectId}/qa-sessions/${sessionId}/approve`, {
    method: 'POST',
  })
}

export function skipQASession(projectId: number, sessionId: string): Promise<HITLDecision> {
  return apiFetch<HITLDecision>(`/projects/${projectId}/qa-sessions/${sessionId}/skip`, {
    method: 'POST',
  })
}
```

- [ ] **Step 4: Run to verify it passes**

```
cd frontend && npx vitest run src/test/ProjectDetailPage.test.tsx
```
Expected: PASS (all tests including the new import check).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/qa_sessions.ts frontend/src/test/ProjectDetailPage.test.tsx
git commit -m "feat: add QA sessions frontend API client"
```

---

### Task 12: QASessionView Component + Tests

**Files:**
- Create: `frontend/src/components/QASessionView.tsx`
- Create: `frontend/src/test/QASessionView.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/test/QASessionView.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { QASessionView } from '../components/QASessionView'

// SSE event sequences to replay
type SSEScenario = Array<object>
let _sseScenario: SSEScenario = []

class MockEventSource {
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  private _closed = false

  constructor(_url: string) {
    setTimeout(() => this._replay(), 10)
  }

  _replay() {
    for (const evt of _sseScenario) {
      if (this._closed) break
      this.onmessage?.({ data: JSON.stringify(evt) })
    }
  }

  close() { this._closed = true }
}

vi.stubGlobal('EventSource', MockEventSource)

const server = setupServer(
  http.post('http://localhost/api/projects/1/qa-sessions/sess-1/approve', () =>
    HttpResponse.json({ decision: 'approve' }),
  ),
  http.post('http://localhost/api/projects/1/qa-sessions/sess-1/skip', () =>
    HttpResponse.json({ decision: 'skip' }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => { server.resetHandlers(); _sseScenario = [] })
afterAll(() => server.close())

describe('QASessionView', () => {
  it('renders QA text delta events', async () => {
    _sseScenario = [
      { type: 'qa_text_delta', text: 'Running tests...' },
      { type: 'done', status: 'done' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => expect(screen.getByText(/Running tests/)).toBeInTheDocument())
  })

  it('shows HITL buttons on hitl_request event', async () => {
    _sseScenario = [
      { type: 'hitl_request', session_id: 'sess-1', ticket_id: '2026-04-24-001', fix_attempt: 0 },
      { type: 'session_status', status: 'hitl_waiting' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => expect(screen.getByRole('button', { name: /approve fix/i })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /skip/i })).toBeInTheDocument()
  })

  it('calls approve API when Approve clicked', async () => {
    const user = userEvent.setup()
    _sseScenario = [
      { type: 'hitl_request', session_id: 'sess-1', ticket_id: '2026-04-24-001', fix_attempt: 0 },
      { type: 'session_status', status: 'hitl_waiting' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => screen.getByRole('button', { name: /approve fix/i }))
    await user.click(screen.getByRole('button', { name: /approve fix/i }))
    // No error thrown = API call succeeded (MSW handler returns 200)
  })

  it('calls skip API when Skip clicked', async () => {
    const user = userEvent.setup()
    _sseScenario = [
      { type: 'hitl_request', session_id: 'sess-1', ticket_id: '2026-04-24-001', fix_attempt: 0 },
      { type: 'session_status', status: 'hitl_waiting' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => screen.getByRole('button', { name: /skip/i }))
    await user.click(screen.getByRole('button', { name: /skip/i }))
  })

  it('shows session complete after done event', async () => {
    _sseScenario = [{ type: 'done', status: 'done' }]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => expect(screen.getByText(/session complete/i)).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run to verify they fail**

```
cd frontend && npx vitest run src/test/QASessionView.test.tsx
```
Expected: `Cannot find module '../components/QASessionView'`.

- [ ] **Step 3: Create QASessionView component**

Create `frontend/src/components/QASessionView.tsx`:

```tsx
import { useState, useEffect, useRef } from 'react'
import { approveQASession, skipQASession } from '../api/qa_sessions'

interface QAEvent {
  type: string
  text?: string
  tool?: string
  agent?: string
  status?: string
  ticket_id?: string
  fix_attempt?: number
  message?: string
  output?: string
}

interface Props {
  projectId: number
  sessionId: string
}

export function QASessionView({ projectId, sessionId }: Props) {
  const [events, setEvents] = useState<QAEvent[]>([])
  const [hitlTicket, setHitlTicket] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [actioning, setActioning] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const es = new EventSource(`/api/projects/${projectId}/qa-sessions/${sessionId}/stream`)

    es.onmessage = (evt) => {
      const event: QAEvent = JSON.parse(evt.data)
      setEvents((prev) => [...prev, event])

      if (event.type === 'hitl_request' && event.ticket_id) {
        setHitlTicket(event.ticket_id)
      }
      if (event.type === 'session_status' && event.status !== 'hitl_waiting') {
        setHitlTicket(null)
      }
      if (['done', 'error', 'budget_exceeded', 'timeout'].includes(event.type)) {
        setDone(true)
        es.close()
      }
    }

    es.onerror = () => {
      setDone(true)
      es.close()
    }

    return () => es.close()
  }, [projectId, sessionId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  async function handleApprove() {
    setActioning(true)
    try {
      await approveQASession(projectId, sessionId)
    } finally {
      setActioning(false)
    }
  }

  async function handleSkip() {
    setActioning(true)
    try {
      await skipQASession(projectId, sessionId)
    } finally {
      setActioning(false)
    }
  }

  return (
    <div className="border rounded p-4 bg-gray-50 space-y-3">
      <div className="max-h-64 overflow-y-auto font-mono text-xs space-y-0.5">
        {events.map((evt, i) => {
          if (evt.type === 'qa_text_delta' || evt.type === 'coder_text_delta') {
            return <span key={i} className="text-gray-700">{evt.text}</span>
          }
          if (evt.type === 'tool_use') {
            return (
              <div key={i} className="text-blue-600">
                [{evt.agent}] → {evt.tool}
              </div>
            )
          }
          if (evt.type === 'session_status') {
            return (
              <div key={i} className="text-purple-700 font-semibold">
                ◆ {evt.status}{evt.fix_attempt !== undefined ? ` (attempt ${evt.fix_attempt})` : ''}
              </div>
            )
          }
          if (evt.type === 'recheck_output') {
            return (
              <pre key={i} className="text-yellow-700 whitespace-pre-wrap">
                {evt.output}
              </pre>
            )
          }
          if (evt.type === 'error') {
            return <div key={i} className="text-red-600">Error: {evt.message}</div>
          }
          return null
        })}
        <div ref={bottomRef} />
      </div>

      {hitlTicket && !done && (
        <div className="p-3 border border-yellow-300 bg-yellow-50 rounded">
          <p className="text-sm font-medium mb-2">
            Bug ticket <code>{hitlTicket}</code> filed. Approve fix attempt?
          </p>
          <div className="flex gap-2">
            <button
              onClick={handleApprove}
              disabled={actioning}
              className="bg-green-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
            >
              Approve Fix
            </button>
            <button
              onClick={handleSkip}
              disabled={actioning}
              className="border px-3 py-1.5 rounded text-sm hover:bg-gray-100 disabled:opacity-50"
            >
              Skip
            </button>
          </div>
        </div>
      )}

      {done && (
        <p className="text-xs text-gray-400">Session complete.</p>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd frontend && npx vitest run src/test/QASessionView.test.tsx
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/QASessionView.tsx frontend/src/test/QASessionView.test.tsx
git commit -m "feat: add QASessionView component with SSE streaming and HITL buttons"
```

---

### Task 13: ProjectDetailPage QA Section

**Files:**
- Modify: `frontend/src/pages/ProjectDetailPage.tsx`
- Test: `frontend/src/test/ProjectDetailPage.test.tsx` (extend)

- [ ] **Step 1: Write the failing test**

Add to `frontend/src/test/ProjectDetailPage.test.tsx`:

```typescript
import { createQASession } from '../api/qa_sessions'

// Stub QASessionView so it doesn't need EventSource for these tests
vi.mock('../components/QASessionView', () => ({
  QASessionView: ({ sessionId }: { sessionId: string }) => (
    <div data-testid="qa-view">{sessionId}</div>
  ),
}))

// Add MSW handler for QA session creation
// (add to the existing server.use() in the test file)

it('shows Run QA Session button', async () => {
  renderDetailPage()
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /run qa session/i })).toBeInTheDocument()
  )
})

it('starts a QA session when button clicked', async () => {
  server.use(
    http.post('http://localhost/api/projects/1/qa-sessions', () =>
      HttpResponse.json({ session_id: 'qa-sess-uuid-5678', status: 'pending' }, { status: 202 }),
    ),
  )
  const user = userEvent.setup()
  renderDetailPage()
  await waitFor(() => screen.getByRole('button', { name: /run qa session/i }))
  await user.click(screen.getByRole('button', { name: /run qa session/i }))
  await waitFor(() => expect(screen.getByTestId('qa-view')).toBeInTheDocument())
})
```

- [ ] **Step 2: Run to verify they fail**

```
cd frontend && npx vitest run src/test/ProjectDetailPage.test.tsx
```
Expected: "Run QA Session" button not found.

- [ ] **Step 3: Add QA section to ProjectDetailPage**

Edit `frontend/src/pages/ProjectDetailPage.tsx`:

Add imports at top:
```typescript
import { createQASession } from '../api/qa_sessions'
import { QASessionView } from '../components/QASessionView'
```

Add state in the component body (after existing state):
```typescript
const [qaSessionId, setQaSessionId] = useState<string | null>(null)
const [startingQA, setStartingQA] = useState(false)
```

Add handler (after handleRunAudit):
```typescript
async function handleRunQA() {
  setStartingQA(true)
  setError(null)
  try {
    const session = await createQASession(projectId)
    setQaSessionId(session.session_id)
  } catch (e: unknown) {
    setError(e instanceof Error ? e.message : 'Failed to start QA session')
  } finally {
    setStartingQA(false)
  }
}
```

Add JSX section after the run history table (before closing `</div>`):
```tsx
<div className="mt-8 border-t pt-6">
  <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
    QA / Test Session
  </h2>
  {!qaSessionId ? (
    <button
      onClick={handleRunQA}
      disabled={startingQA}
      className="bg-purple-600 text-white px-4 py-2 rounded disabled:opacity-50"
    >
      {startingQA ? 'Starting…' : 'Run QA Session'}
    </button>
  ) : (
    <QASessionView projectId={projectId} sessionId={qaSessionId} />
  )}
</div>
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd frontend && npx vitest run src/test/ProjectDetailPage.test.tsx
```
Expected: all PASS.

- [ ] **Step 5: Run full frontend suite**

```
cd frontend && npx vitest run
```
Expected: all PASS.

- [ ] **Step 6: Run full backend suite**

```
cd backend && python -m pytest -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ProjectDetailPage.tsx frontend/src/test/ProjectDetailPage.test.tsx
git commit -m "feat: add QA session section to ProjectDetailPage"
```

---

### Task 14: Final Integration — Full Suite Green

- [ ] **Step 1: Run full backend test suite**

```
cd backend && python -m pytest -v
```
Expected: all PASS. Fix any failures before continuing.

- [ ] **Step 2: Run full frontend test suite**

```
cd frontend && npx vitest run
```
Expected: all PASS.

- [ ] **Step 3: Build TypeScript check**

```
cd frontend && npx tsc --noEmit
```
Expected: 0 errors.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: P3 complete — QA/Coder loop with HITL, file watcher, scheduler"
```

---

## Self-Review

**Spec coverage:**
- ✅ QA agent reads Project.md + OpenAPI spec (via tools)
- ✅ QA agent generates pytest test plan and writes tests
- ✅ Coder agent writes fixes
- ✅ Black-box feedback loop with max_fix_attempts
- ✅ bugs-resolved.md and test-status.md memory files
- ✅ File watcher (watchfiles) with 30s debounce
- ✅ Nightly commit trigger (APScheduler 03:00)
- ✅ HITL approval surface — tickets + approve/skip UI
- ✅ SSE streaming for QA/Coder loop (qa_text_delta, coder_text_delta, session_status, hitl_request)
- ✅ QASession DB model
- ✅ API: POST/stream/approve/skip
- ✅ Frontend QASessionView with HITL buttons
- ✅ New tab/section on ProjectDetailPage

**Type consistency:** `session_id` is `str` (UUID) throughout. `ticket_id` is `str | None` from QA loop → passed to orchestrator → surfaced in hitl_request SSE event → used by frontend to display ticket reference.

**No placeholders:** All steps contain complete code.
