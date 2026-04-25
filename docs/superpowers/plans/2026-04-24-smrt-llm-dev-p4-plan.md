# SMRT Agent P4 — Live Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the raw SSE log dump with a structured, phase-grouped `AgentTimeline` component that shows expandable tool calls (input + result), timestamped phase headers per agent, and a Bug Tickets panel listing filed `.smrt/tickets/*.md` files.

**Architecture:** Three backend changes (add `ts`/`agent` fields to all SSE events, increase result window 500→2000 chars, add `GET /projects/{id}/tickets` endpoint) paired with three frontend changes (new pure `AgentTimeline` display component, new `TicketsPanel` component, refactored `LiveAgentView` and `QASessionView` that delegate rendering to `AgentTimeline`). All SSE connection and HITL state stays in the parent views; `AgentTimeline` is stateless display only.

**Tech Stack:** FastAPI · Python 3.11 · React 18 · TypeScript · Vite · Tailwind CSS · Vitest · MSW · @testing-library/react · userEvent

---

## File Structure

**New files:**
- `backend/src/smrt_agent/api/tickets.py` — `GET /projects/{id}/tickets` listing `.smrt/tickets/*.md`
- `backend/tests/test_tickets_api.py` — API tests for the tickets endpoint
- `frontend/src/components/AgentTimeline.tsx` — pure display component: phases → collapsible tool calls
- `frontend/src/test/AgentTimeline.test.tsx` — component tests
- `frontend/src/api/tickets.ts` — `listTickets(projectId)` fetch helper
- `frontend/src/components/TicketsPanel.tsx` — fetches and displays bug tickets
- `frontend/src/test/TicketsPanel.test.tsx` — component tests

**Modified files:**
- `backend/src/smrt_agent/agents/reviewer/loop.py` — add `ts`, `agent: "reviewer"` to all events; result `[:500]` → `[:2000]`
- `backend/src/smrt_agent/agents/qa/loop.py` — add `ts` to all events; result `[:500]` → `[:2000]`
- `backend/src/smrt_agent/agents/coder/loop.py` — add `ts` to all events; result `[:500]` → `[:2000]`
- `backend/src/smrt_agent/agents/orchestrator.py` — add `ts` to session_status, hitl_request, recheck_output events
- `backend/src/smrt_agent/main.py` — wire tickets router
- `backend/tests/test_reviewer_loop.py` — add assertions for `ts` and `agent` fields
- `frontend/src/components/LiveAgentView.tsx` — use `AgentTimeline`; delete local event grouping
- `frontend/src/test/LiveAgentView.test.tsx` — update tool_result test to use expand interaction
- `frontend/src/components/QASessionView.tsx` — use `AgentTimeline`; delete raw log rendering
- `frontend/src/test/QASessionView.test.tsx` — no behavior changes needed (HITL panel tests unchanged)
- `frontend/src/pages/ProjectDetailPage.tsx` — add `TicketsPanel` section + refresh after QA completes
- `frontend/src/test/ProjectDetailPage.test.tsx` — add test for tickets section

---

### Task 1: Create phase/4-observability branch

**Files:** none (already done if you are reading this on the branch)

- [ ] **Step 1: Create and switch to the phase branch**

```bash
git checkout main && git pull origin main
git checkout -b phase/4-observability
```

Expected: `Switched to a new branch 'phase/4-observability'`

---

### Task 2: Backend — enrich SSE events (timestamps, agent labels, larger result window)

**Files:**
- Modify: `backend/src/smrt_agent/agents/reviewer/loop.py`
- Modify: `backend/src/smrt_agent/agents/qa/loop.py`
- Modify: `backend/src/smrt_agent/agents/coder/loop.py`
- Modify: `backend/src/smrt_agent/agents/orchestrator.py`
- Modify: `backend/tests/test_reviewer_loop.py`

- [ ] **Step 1: Write a failing test that asserts `ts` and `agent` fields exist on tool events**

Add this test to the end of `backend/tests/test_reviewer_loop.py`:

```python
async def test_run_reviewer_tool_events_have_ts_and_agent(project_path):
    queue: asyncio.Queue = asyncio.Queue()

    tool_use_response = _make_tool_use_response("list_files", {"subdir": ""})
    end_turn_response = _make_end_turn_response()

    call_count = 0

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)

    def stream_side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        s = MagicMock()
        s.__enter__ = MagicMock(return_value=s)
        s.__exit__ = MagicMock(return_value=False)
        s.__iter__ = MagicMock(return_value=iter([]))
        if call_count == 1:
            s.get_final_message = MagicMock(return_value=tool_use_response)
        else:
            s.get_final_message = MagicMock(return_value=end_turn_response)
        return s

    mock_client = MagicMock()
    mock_client.messages.stream = MagicMock(side_effect=stream_side_effect)

    with patch("smrt_agent.agents.reviewer.loop.anthropic.Anthropic", return_value=mock_client):
        await run_reviewer(
            project_path=project_path,
            api_key="test-key",
            model="claude-sonnet-4-6",
            budget_usd=1.50,
            queue=queue,
        )

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    tool_events = [e for e in events if e["type"] in ("tool_use", "tool_result")]
    assert len(tool_events) >= 2, "Expected at least one tool_use + tool_result pair"

    for evt in tool_events:
        assert "ts" in evt, f"Event {evt['type']} missing 'ts' field"
        assert "agent" in evt, f"Event {evt['type']} missing 'agent' field"
        assert evt["agent"] == "reviewer"
```

- [ ] **Step 2: Verify the test fails**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest tests/test_reviewer_loop.py::test_run_reviewer_tool_events_have_ts_and_agent -v
```

Expected: FAIL with `AssertionError: Event tool_use missing 'ts' field`

- [ ] **Step 3: Rewrite `backend/src/smrt_agent/agents/reviewer/loop.py` with enriched events**

Replace the entire file:

```python
"""Anthropic SDK streaming loop for the Reviewer agent."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

from smrt_agent.agents.reviewer.budget import TOOL_DEFINITIONS, compute_cost_usd
from smrt_agent.agents.reviewer.tools import fetch_url, list_files, read_file, write_file


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "reviewer.md"
    return prompt_path.read_text(encoding="utf-8")


def _dispatch_tool(name: str, inputs: dict[str, Any], project_path: Path) -> str:
    try:
        if name == "list_files":
            files = list_files(project_path, inputs.get("subdir", ""))
            return json.dumps(files)
        elif name == "read_file":
            return read_file(project_path, inputs["path"])
        elif name == "fetch_url":
            return fetch_url(inputs["url"])
        elif name == "write_file":
            return write_file(project_path, inputs["path"], inputs["content"])
        else:
            return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Error: {exc}"


async def run_reviewer(
    *,
    project_path: Path,
    api_key: str,
    model: str,
    budget_usd: float,
    queue: asyncio.Queue,
    container_ip: str | None = None,
) -> None:
    """Run the Reviewer agent loop. Puts SSE event dicts into `queue`."""
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = _load_system_prompt()

    task_description = f"Perform initialization audit for the project at {project_path}."
    if container_ip:
        task_description += f" The sandbox is running at container IP {container_ip}:8080."

    messages: list[dict] = [{"role": "user", "content": task_description}]
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
                        await queue.put({
                            "type": "text_delta",
                            "text": delta.text,
                            "agent": "reviewer",
                            "ts": _ts(),
                        })

            response = stream.get_final_message()

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens

        cost = compute_cost_usd(total_input, total_output, model)
        if cost >= budget_usd:
            await queue.put({
                "type": "budget_exceeded",
                "cost_usd": round(cost, 4),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "ts": _ts(),
            })
            return

        if response.stop_reason == "end_turn":
            await queue.put({
                "type": "done",
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cost_usd": round(cost, 4),
                "ts": _ts(),
            })
            return

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    await queue.put({
                        "type": "tool_use",
                        "agent": "reviewer",
                        "tool": block.name,
                        "input": block.input,
                        "ts": _ts(),
                    })
                    result = _dispatch_tool(block.name, block.input, project_path)
                    await queue.put({
                        "type": "tool_result",
                        "agent": "reviewer",
                        "tool": block.name,
                        "result": result[:2000],
                        "ts": _ts(),
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        await queue.put({
            "type": "error",
            "message": f"Unexpected stop_reason: {response.stop_reason}",
            "ts": _ts(),
        })
        return
```

- [ ] **Step 4: Rewrite `backend/src/smrt_agent/agents/qa/loop.py` with enriched events**

Replace the entire file:

```python
"""Anthropic SDK streaming loop for the QA agent."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

from smrt_agent.agents.qa.budget import TOOL_DEFINITIONS, compute_cost_usd
from smrt_agent.agents.qa.tools import (
    write_test_file, run_pytest, write_bug_ticket,
    write_test_status, append_bugs_resolved,
)
from smrt_agent.agents.reviewer.tools import list_files, read_file


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "qa.md"
    return prompt_path.read_text(encoding="utf-8")


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
    context = (
        project_md.read_text(encoding="utf-8")
        if project_md.exists()
        else "(No Project.md found — survey the source tree directly.)"
    )

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
                        await queue.put({
                            "type": "qa_text_delta",
                            "text": delta.text,
                            "agent": "qa",
                            "ts": _ts(),
                        })
            response = stream.get_final_message()

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens
        cost = compute_cost_usd(total_input, total_output, model)

        if cost >= budget_usd:
            await queue.put({
                "type": "budget_exceeded",
                "cost_usd": round(cost, 4),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "ts": _ts(),
            })
            return last_ticket_id

        if response.stop_reason == "end_turn":
            await queue.put({
                "type": "qa_done",
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cost_usd": round(cost, 4),
                "ticket_id": last_ticket_id,
                "ts": _ts(),
            })
            return last_ticket_id

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    await queue.put({
                        "type": "tool_use",
                        "agent": "qa",
                        "tool": block.name,
                        "input": block.input,
                        "ts": _ts(),
                    })
                    result, ticket_id = _dispatch_tool(block.name, block.input, project_path)
                    if ticket_id:
                        last_ticket_id = ticket_id
                    await queue.put({
                        "type": "tool_result",
                        "agent": "qa",
                        "tool": block.name,
                        "result": result[:2000],
                        "ts": _ts(),
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        await queue.put({
            "type": "error",
            "message": f"QA agent unexpected stop_reason: {response.stop_reason}",
            "ts": _ts(),
        })
        return last_ticket_id
```

- [ ] **Step 5: Rewrite `backend/src/smrt_agent/agents/coder/loop.py` with enriched events**

Replace the entire file:

```python
"""Anthropic SDK streaming loop for the Coder agent."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

from smrt_agent.agents.coder.budget import TOOL_DEFINITIONS, compute_cost_usd
from smrt_agent.agents.coder.tools import read_source_file, write_source_file
from smrt_agent.agents.reviewer.tools import list_files


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_system_prompt() -> str:
    prompt_path = Path(__file__).parent.parent.parent / "prompts" / "coder.md"
    return prompt_path.read_text(encoding="utf-8")


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
                        await queue.put({
                            "type": "coder_text_delta",
                            "text": delta.text,
                            "agent": "coder",
                            "ts": _ts(),
                        })
            response = stream.get_final_message()

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens
        cost = compute_cost_usd(total_input, total_output, model)

        if cost >= budget_usd:
            await queue.put({
                "type": "budget_exceeded",
                "cost_usd": round(cost, 4),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "ts": _ts(),
            })
            return

        if response.stop_reason == "end_turn":
            await queue.put({
                "type": "coder_done",
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cost_usd": round(cost, 4),
                "ts": _ts(),
            })
            return

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    await queue.put({
                        "type": "tool_use",
                        "agent": "coder",
                        "tool": block.name,
                        "input": block.input,
                        "ts": _ts(),
                    })
                    result = _dispatch_tool(block.name, block.input, project_path)
                    await queue.put({
                        "type": "tool_result",
                        "agent": "coder",
                        "tool": block.name,
                        "result": result[:2000],
                        "ts": _ts(),
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        await queue.put({
            "type": "error",
            "message": f"Coder unexpected stop_reason: {response.stop_reason}",
            "ts": _ts(),
        })
        return
```

- [ ] **Step 6: Rewrite `backend/src/smrt_agent/agents/orchestrator.py` with `ts` on all events**

Replace the entire file:

```python
"""QA session orchestrator: coordinates QA → HITL → Coder → recheck loop."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from smrt_agent.agents.qa.loop import run_qa_agent
from smrt_agent.agents.coder.loop import run_coder_agent
from smrt_agent.agents.qa.tools import run_pytest


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        await queue.put({
            "type": "session_status",
            "status": "qa_running",
            "fix_attempt": attempt,
            "ts": _ts(),
        })

        ticket_id = await run_qa_agent(
            project_path=project_path,
            api_key=api_key,
            model=model_qa,
            budget_usd=per_agent_budget,
            queue=queue,
            prior_fix_context=prior_fix_context,
        )

        if ticket_id is None:
            await queue.put({
                "type": "session_status",
                "status": "done",
                "fix_attempt": attempt,
                "ts": _ts(),
            })
            return "done"

        if attempt >= max_fix_attempts:
            await queue.put({
                "type": "session_status",
                "status": "error",
                "message": "Max fix attempts reached",
                "ts": _ts(),
            })
            return "error"

        # HITL gate — pause until user approves or skips
        await queue.put({
            "type": "hitl_request",
            "session_id": session_id,
            "ticket_id": ticket_id,
            "fix_attempt": attempt,
            "ts": _ts(),
        })
        await queue.put({
            "type": "session_status",
            "status": "hitl_waiting",
            "ts": _ts(),
        })

        event = asyncio.Event()
        hitl_events[session_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=3600.0)
        except asyncio.TimeoutError:
            hitl_events.pop(session_id, None)
            hitl_decisions.pop(session_id, None)
            await queue.put({
                "type": "session_status",
                "status": "error",
                "message": "HITL approval timed out",
                "ts": _ts(),
            })
            return "error"

        decision = hitl_decisions.pop(session_id, "skip")
        hitl_events.pop(session_id, None)

        if decision == "skip":
            await queue.put({
                "type": "session_status",
                "status": "skipped",
                "ts": _ts(),
            })
            return "skipped"

        # Approved — run Coder agent
        ticket_path = project_path / ".smrt" / "tickets" / f"{ticket_id}.md"
        ticket_content = (
            ticket_path.read_text(encoding="utf-8")
            if ticket_path.exists()
            else f"Ticket {ticket_id}"
        )
        pytest_output = run_pytest(project_path)

        await queue.put({
            "type": "session_status",
            "status": "coder_running",
            "fix_attempt": attempt,
            "ts": _ts(),
        })
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
        await queue.put({
            "type": "recheck_output",
            "output": recheck_output[:2000],
            "ts": _ts(),
        })

        if "passed" in recheck_output and "failed" not in recheck_output:
            await queue.put({
                "type": "session_status",
                "status": "done",
                "fix_attempt": attempt,
                "ts": _ts(),
            })
            return "done"

        prior_fix_context = f"Fix attempt {attempt + 1} recheck:\n{recheck_output}"

    return "error"
```

- [ ] **Step 7: Run the new test to verify it passes**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest tests/test_reviewer_loop.py -v
```

Expected: all tests PASS including the new `test_run_reviewer_tool_events_have_ts_and_agent`

- [ ] **Step 8: Run the full backend suite to confirm no regressions**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest -v
```

Expected: all tests PASS

- [ ] **Step 9: Commit**

```bash
git add backend/src/smrt_agent/agents/
git add backend/tests/test_reviewer_loop.py
git commit -m "feat: enrich SSE events with timestamps, agent labels, and 2000-char result window"
```

---

### Task 3: Backend — Bug Tickets API

**Files:**
- Create: `backend/src/smrt_agent/api/tickets.py`
- Create: `backend/tests/test_tickets_api.py`
- Modify: `backend/src/smrt_agent/main.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_tickets_api.py`:

```python
"""Tests for the bug tickets API."""
import pytest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from smrt_agent.main import app
from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project


@pytest.fixture
def tickets_dir(tmp_path):
    """Creates a temp project directory with two ticket files."""
    smrt = tmp_path / ".smrt" / "tickets"
    smrt.mkdir(parents=True)
    (smrt / "2026-04-24-001.md").write_text(
        "# GET /items returns 404\nDescription: endpoint missing.", encoding="utf-8"
    )
    (smrt / "2026-04-24-002.md").write_text(
        "# POST /items ignores body\nDescription: input not saved.", encoding="utf-8"
    )
    return tmp_path


async def test_list_tickets_returns_empty_when_no_smrt_dir(tmp_path, monkeypatch):
    async def override_db():
        from unittest.mock import AsyncMock, MagicMock
        db = AsyncMock()
        project = MagicMock(spec=Project)
        project.canonical_path = str(tmp_path)
        db.get = AsyncMock(return_value=project)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/projects/1/tickets")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        app.dependency_overrides.clear()


async def test_list_tickets_returns_files(tickets_dir, monkeypatch):
    async def override_db():
        from unittest.mock import AsyncMock, MagicMock
        db = AsyncMock()
        project = MagicMock(spec=Project)
        project.canonical_path = str(tickets_dir)
        db.get = AsyncMock(return_value=project)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/projects/1/tickets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        ids = [t["id"] for t in data]
        assert "2026-04-24-001" in ids
        assert "2026-04-24-002" in ids
        ticket = next(t for t in data if t["id"] == "2026-04-24-001")
        assert ticket["title"] == "GET /items returns 404"
        assert "Description" in ticket["content"]
    finally:
        app.dependency_overrides.clear()


async def test_list_tickets_404_for_unknown_project():
    async def override_db():
        from unittest.mock import AsyncMock
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/projects/999/tickets")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Verify the test fails**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest tests/test_tickets_api.py -v
```

Expected: FAIL with `404` (no route registered) or import error

- [ ] **Step 3: Create `backend/src/smrt_agent/api/tickets.py`**

```python
"""Bug tickets API: list .smrt/tickets/ files for a project."""
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from smrt_agent.api.deps import get_db
from smrt_agent.db.models import Project

router = APIRouter(prefix="/projects", tags=["tickets"])


@router.get("/{project_id}/tickets")
async def list_tickets(
    project_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    tickets_dir = Path(project.canonical_path) / ".smrt" / "tickets"
    if not tickets_dir.exists():
        return []

    results = []
    for path in sorted(tickets_dir.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = lines[0].lstrip("#").strip() if lines else path.stem
        results.append({
            "id": path.stem,
            "title": title,
            "content": content,
        })
    return results
```

- [ ] **Step 4: Wire the tickets router into `backend/src/smrt_agent/main.py`**

Add the import and `include_router` call. The final file:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from smrt_agent.settings import Settings
from smrt_agent.db.session import get_engine
from smrt_agent.db.schema import init_schema
from smrt_agent.api.projects import router as projects_router
from smrt_agent.api.sandbox import router as sandbox_router
from smrt_agent.api.runs import router as runs_router
from smrt_agent.api.filesystem import router as filesystem_router
from smrt_agent.api.qa_sessions import router as qa_sessions_router
from smrt_agent.api.tickets import router as tickets_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    await init_schema(engine)
    yield


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(
        title="SMRT Agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[f"http://{settings.bind_host}:{settings.frontend_port}"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "version": app.version}

    app.include_router(projects_router)
    app.include_router(sandbox_router)
    app.include_router(runs_router)
    app.include_router(filesystem_router)
    app.include_router(qa_sessions_router)
    app.include_router(tickets_router)

    return app


app = create_app()
```

- [ ] **Step 5: Verify the test passes**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest tests/test_tickets_api.py -v
```

Expected: all 3 tests PASS

- [ ] **Step 6: Run full backend suite**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest -v
```

Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/src/smrt_agent/api/tickets.py backend/src/smrt_agent/main.py backend/tests/test_tickets_api.py
git commit -m "feat: add GET /projects/{id}/tickets endpoint for bug tickets"
```

---

### Task 4: Frontend — AgentTimeline component

**Files:**
- Create: `frontend/src/components/AgentTimeline.tsx`
- Create: `frontend/src/test/AgentTimeline.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/AgentTimeline.test.tsx`:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AgentTimeline, type AgentEvent } from '../components/AgentTimeline'

describe('AgentTimeline', () => {
  it('shows waiting message with empty event array', () => {
    render(<AgentTimeline events={[]} />)
    expect(screen.getByText(/waiting for events/i)).toBeInTheDocument()
  })

  it('renders text delta content in a phase', () => {
    const events: AgentEvent[] = [
      { type: 'text_delta', text: 'Analyzing code structure…', agent: 'reviewer' },
    ]
    render(<AgentTimeline events={events} defaultLabel="Reviewer" />)
    expect(screen.getByText(/Analyzing code structure…/)).toBeInTheDocument()
  })

  it('shows tool name in collapsed tool call row', () => {
    const events: AgentEvent[] = [
      { type: 'tool_use', tool: 'list_files', input: { subdir: '' }, agent: 'reviewer' },
      { type: 'tool_result', tool: 'list_files', result: '["main.py"]', agent: 'reviewer' },
    ]
    render(<AgentTimeline events={events} defaultLabel="Reviewer" />)
    expect(screen.getByText(/list_files/)).toBeInTheDocument()
  })

  it('expands a tool call to show input and result', async () => {
    const user = userEvent.setup()
    const events: AgentEvent[] = [
      {
        type: 'tool_use',
        tool: 'read_file',
        input: { path: 'src/main.py' },
        agent: 'reviewer',
        ts: '2026-04-24T12:00:00.000Z',
      },
      {
        type: 'tool_result',
        tool: 'read_file',
        result: 'from fastapi import FastAPI',
        agent: 'reviewer',
        ts: '2026-04-24T12:00:01.000Z',
      },
    ]
    render(<AgentTimeline events={events} defaultLabel="Reviewer" />)
    await user.click(screen.getByText(/read_file/))
    expect(screen.getByText(/src\/main\.py/)).toBeInTheDocument()
    expect(screen.getByText(/from fastapi import FastAPI/)).toBeInTheDocument()
  })

  it('renders separate phases for qa_running and coder_running session_status events', () => {
    const ts = new Date().toISOString()
    const events: AgentEvent[] = [
      { type: 'session_status', status: 'qa_running', fix_attempt: 0, ts },
      { type: 'qa_text_delta', text: 'Running QA tests…', agent: 'qa' },
      { type: 'session_status', status: 'coder_running', fix_attempt: 0, ts },
      { type: 'coder_text_delta', text: 'Fixing the bug…', agent: 'coder' },
    ]
    render(<AgentTimeline events={events} />)
    expect(screen.getByText(/QA Agent/)).toBeInTheDocument()
    expect(screen.getByText(/Coder Agent/)).toBeInTheDocument()
    expect(screen.getByText(/Running QA tests…/)).toBeInTheDocument()
    expect(screen.getByText(/Fixing the bug…/)).toBeInTheDocument()
  })

  it('renders recheck_output in a code block with green styling when tests pass', () => {
    const ts = new Date().toISOString()
    const events: AgentEvent[] = [
      { type: 'session_status', status: 'coder_running', fix_attempt: 0, ts },
      { type: 'recheck_output', output: '2 passed in 0.5s', ts },
    ]
    render(<AgentTimeline events={events} />)
    expect(screen.getByText(/2 passed in 0\.5s/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Verify the test fails**

```bash
cd frontend && npm test -- --run src/test/AgentTimeline.test.tsx
```

Expected: FAIL with `Cannot find module '../components/AgentTimeline'`

- [ ] **Step 3: Create `frontend/src/components/AgentTimeline.tsx`**

```typescript
import { useState, useMemo } from 'react'

export interface AgentEvent {
  type: string
  text?: string
  tool?: string
  agent?: string
  input?: unknown
  result?: string
  message?: string
  status?: string
  fix_attempt?: number
  output?: string
  ts?: string
  ticket_id?: string
  total_input_tokens?: number
  total_output_tokens?: number
  cost_usd?: number
}

interface ToolCallPair {
  use: AgentEvent
  result: AgentEvent | null
}

interface AgentPhase {
  id: string
  label: string
  agentType: string
  startTs?: string
  textEvents: AgentEvent[]
  toolPairs: ToolCallPair[]
  recheckEvent: AgentEvent | null
  errorEvent: AgentEvent | null
}

function makePhaseLabel(status: string, fixAttempt?: number): string {
  const attempt = fixAttempt !== undefined ? ` — Attempt ${fixAttempt}` : ''
  switch (status) {
    case 'qa_running':
      return `QA Agent${attempt}`
    case 'coder_running':
      return `Coder Agent${attempt}`
    case 'hitl_waiting':
      return 'Awaiting Approval'
    case 'done':
      return 'Complete'
    case 'error':
      return 'Error'
    case 'skipped':
      return 'Skipped'
    default:
      return status
  }
}

function agentFromStatus(status: string): string {
  if (status.startsWith('coder')) return 'coder'
  if (status.startsWith('qa')) return 'qa'
  return 'system'
}

function groupIntoPhases(events: AgentEvent[], defaultLabel: string): AgentPhase[] {
  const phases: AgentPhase[] = []
  let toolUseQueue: AgentEvent[] = []
  let current: AgentPhase = {
    id: 'default',
    label: defaultLabel,
    agentType: defaultLabel.toLowerCase().includes('reviewer') ? 'reviewer' : 'qa',
    textEvents: [],
    toolPairs: [],
    recheckEvent: null,
    errorEvent: null,
  }

  for (const event of events) {
    if (event.type === 'session_status' && event.status) {
      toolUseQueue.forEach((use) => current.toolPairs.push({ use, result: null }))
      toolUseQueue = []
      if (
        current.textEvents.length > 0 ||
        current.toolPairs.length > 0 ||
        current.recheckEvent ||
        current.errorEvent
      ) {
        phases.push(current)
      }
      current = {
        id: `${event.status}-${event.fix_attempt ?? 0}-${phases.length}`,
        label: makePhaseLabel(event.status, event.fix_attempt),
        agentType: agentFromStatus(event.status),
        startTs: event.ts,
        textEvents: [],
        toolPairs: [],
        recheckEvent: null,
        errorEvent: null,
      }
    } else if (['text_delta', 'qa_text_delta', 'coder_text_delta'].includes(event.type)) {
      current.textEvents.push(event)
    } else if (event.type === 'tool_use') {
      toolUseQueue.push(event)
    } else if (event.type === 'tool_result') {
      const use = toolUseQueue.shift()
      if (use) {
        current.toolPairs.push({ use, result: event })
      }
    } else if (event.type === 'recheck_output') {
      current.recheckEvent = event
    } else if (event.type === 'error') {
      current.errorEvent = event
    }
  }

  toolUseQueue.forEach((use) => current.toolPairs.push({ use, result: null }))
  if (
    current.textEvents.length > 0 ||
    current.toolPairs.length > 0 ||
    current.recheckEvent ||
    current.errorEvent
  ) {
    phases.push(current)
  }

  return phases
}

const AGENT_STYLES = {
  reviewer: {
    header: 'bg-blue-50 border-blue-200',
    text: 'text-blue-800',
    border: 'border-blue-200',
    tool: 'text-blue-700',
  },
  qa: {
    header: 'bg-purple-50 border-purple-200',
    text: 'text-purple-800',
    border: 'border-purple-200',
    tool: 'text-purple-700',
  },
  coder: {
    header: 'bg-orange-50 border-orange-200',
    text: 'text-orange-800',
    border: 'border-orange-200',
    tool: 'text-orange-700',
  },
  system: {
    header: 'bg-gray-50 border-gray-200',
    text: 'text-gray-700',
    border: 'border-gray-200',
    tool: 'text-gray-600',
  },
}

function ToolCallRow({ pair }: { pair: ToolCallPair }) {
  const [expanded, setExpanded] = useState(false)
  const style =
    AGENT_STYLES[pair.use.agent as keyof typeof AGENT_STYLES] ?? AGENT_STYLES.system

  return (
    <div className={`border rounded text-xs font-mono ${style.border}`}>
      <button
        className="w-full text-left px-3 py-1.5 flex items-center gap-2 hover:bg-gray-50"
        onClick={() => setExpanded((p) => !p)}
      >
        <span className="text-gray-400 w-3 shrink-0">{expanded ? '▼' : '▶'}</span>
        <span className={`font-semibold ${style.tool}`}>{pair.use.tool}</span>
        {!expanded && (
          <span className="text-gray-400 truncate">
            {JSON.stringify(pair.use.input).slice(0, 80)}
          </span>
        )}
        {pair.use.ts && (
          <span className="ml-auto text-gray-400 shrink-0">
            {new Date(pair.use.ts).toLocaleTimeString()}
          </span>
        )}
      </button>
      {expanded && (
        <div className="border-t px-3 py-2 space-y-2 bg-gray-50">
          <div>
            <p className="text-gray-400 text-xs mb-1">Input</p>
            <pre className="whitespace-pre-wrap text-gray-700 text-xs">
              {JSON.stringify(pair.use.input, null, 2)}
            </pre>
          </div>
          {pair.result && (
            <div>
              <p className="text-gray-400 text-xs mb-1">Result</p>
              <pre className="whitespace-pre-wrap text-gray-600 text-xs max-h-48 overflow-y-auto">
                {pair.result.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function PhaseSection({ phase, defaultOpen }: { phase: AgentPhase; defaultOpen: boolean }) {
  const [collapsed, setCollapsed] = useState(!defaultOpen)
  const style =
    AGENT_STYLES[phase.agentType as keyof typeof AGENT_STYLES] ?? AGENT_STYLES.system
  const text = phase.textEvents.map((e) => e.text ?? '').join('')

  return (
    <div className={`border rounded overflow-hidden ${style.border}`}>
      <button
        className={`w-full text-left px-3 py-2 flex items-center gap-2 border-b ${style.header}`}
        onClick={() => setCollapsed((p) => !p)}
      >
        <span className="text-gray-400 w-3 shrink-0">{collapsed ? '▶' : '▼'}</span>
        <span className={`font-semibold text-sm ${style.text}`}>{phase.label}</span>
        {phase.startTs && (
          <span className="ml-auto text-xs text-gray-400">
            {new Date(phase.startTs).toLocaleTimeString()}
          </span>
        )}
      </button>
      {!collapsed && (
        <div className="p-3 space-y-2 bg-white">
          {text && (
            <div className="text-xs text-gray-700 leading-relaxed bg-gray-50 rounded p-2 max-h-32 overflow-y-auto">
              {text}
            </div>
          )}
          {phase.toolPairs.map((pair, i) => (
            <ToolCallRow key={i} pair={pair} />
          ))}
          {phase.recheckEvent && (
            <div>
              <p className="text-xs text-gray-500 mb-1 font-medium">Pytest recheck</p>
              <pre
                className={`text-xs p-2 rounded border whitespace-pre-wrap max-h-48 overflow-y-auto ${
                  phase.recheckEvent.output?.includes('passed') &&
                  !phase.recheckEvent.output?.includes('failed')
                    ? 'bg-green-50 border-green-200 text-green-800'
                    : 'bg-red-50 border-red-200 text-red-800'
                }`}
              >
                {phase.recheckEvent.output}
              </pre>
            </div>
          )}
          {phase.errorEvent && (
            <div className="bg-red-50 border border-red-200 rounded p-2 text-xs text-red-700">
              Error: {phase.errorEvent.message}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function AgentTimeline({
  events,
  defaultLabel = 'Agent',
}: {
  events: AgentEvent[]
  defaultLabel?: string
}) {
  const phases = useMemo(() => groupIntoPhases(events, defaultLabel), [events, defaultLabel])

  if (phases.length === 0) {
    return <p className="text-xs text-gray-400 italic">Waiting for events…</p>
  }

  return (
    <div className="space-y-2">
      {phases.map((phase, i) => (
        <PhaseSection key={phase.id} phase={phase} defaultOpen={i === phases.length - 1} />
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd frontend && npm test -- --run src/test/AgentTimeline.test.tsx
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AgentTimeline.tsx frontend/src/test/AgentTimeline.test.tsx
git commit -m "feat: add AgentTimeline component with phase grouping and expandable tool calls"
```

---

### Task 5: Frontend — Tickets API client and TicketsPanel component

**Files:**
- Create: `frontend/src/api/tickets.ts`
- Create: `frontend/src/components/TicketsPanel.tsx`
- Create: `frontend/src/test/TicketsPanel.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/test/TicketsPanel.test.tsx`:

```typescript
import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { TicketsPanel } from '../components/TicketsPanel'

const mockTickets = [
  {
    id: '2026-04-24-001',
    title: 'GET /items returns 404',
    content: '# GET /items returns 404\nThe endpoint is missing from the router.',
  },
  {
    id: '2026-04-24-002',
    title: 'POST /items ignores body',
    content: '# POST /items ignores body\nInput data is discarded.',
  },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/tickets', () =>
    HttpResponse.json(mockTickets),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('TicketsPanel', () => {
  it('shows no-tickets message when the list is empty', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/tickets', () => HttpResponse.json([])),
    )
    render(<TicketsPanel projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no bug tickets/i)).toBeInTheDocument(),
    )
  })

  it('lists ticket IDs and titles', async () => {
    render(<TicketsPanel projectId={1} />)
    await waitFor(() => expect(screen.getByText('2026-04-24-001')).toBeInTheDocument())
    expect(screen.getByText(/GET \/items returns 404/)).toBeInTheDocument()
    expect(screen.getByText('2026-04-24-002')).toBeInTheDocument()
  })

  it('expands a ticket to show full content when clicked', async () => {
    const user = userEvent.setup()
    render(<TicketsPanel projectId={1} />)
    await waitFor(() => screen.getByText('2026-04-24-001'))
    await user.click(screen.getByText('2026-04-24-001'))
    expect(screen.getByText(/The endpoint is missing from the router/)).toBeInTheDocument()
  })

  it('re-fetches when refreshKey changes', async () => {
    const { rerender } = render(<TicketsPanel projectId={1} refreshKey={0} />)
    await waitFor(() => screen.getByText('2026-04-24-001'))

    server.use(
      http.get('http://localhost/api/projects/1/tickets', () =>
        HttpResponse.json([
          { id: '2026-04-24-003', title: 'New ticket', content: '# New ticket\nNew content.' },
        ]),
      ),
    )

    rerender(<TicketsPanel projectId={1} refreshKey={1} />)
    await waitFor(() => expect(screen.getByText('2026-04-24-003')).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Verify the test fails**

```bash
cd frontend && npm test -- --run src/test/TicketsPanel.test.tsx
```

Expected: FAIL with `Cannot find module '../components/TicketsPanel'`

- [ ] **Step 3: Create `frontend/src/api/tickets.ts`**

```typescript
import { apiUrl } from './client'

export interface Ticket {
  id: string
  title: string
  content: string
}

export async function listTickets(projectId: number): Promise<Ticket[]> {
  const resp = await fetch(apiUrl(`/projects/${projectId}/tickets`))
  if (!resp.ok) throw new Error(`Failed to list tickets: ${resp.status}`)
  return resp.json() as Promise<Ticket[]>
}
```

- [ ] **Step 4: Create `frontend/src/components/TicketsPanel.tsx`**

```typescript
import { useEffect, useState } from 'react'
import { listTickets, type Ticket } from '../api/tickets'

function TicketCard({ ticket }: { ticket: Ticket }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="border rounded overflow-hidden border-orange-200">
      <button
        className="w-full text-left px-3 py-2 flex items-center gap-2 bg-orange-50 hover:bg-orange-100"
        onClick={() => setExpanded((p) => !p)}
      >
        <span className="font-mono text-xs font-medium text-orange-800">{ticket.id}</span>
        <span className="text-sm text-orange-700 truncate ml-1">{ticket.title}</span>
        <span className="ml-auto text-gray-400 shrink-0">{expanded ? '▼' : '▶'}</span>
      </button>
      {expanded && (
        <pre className="p-3 text-xs whitespace-pre-wrap text-gray-700 bg-white font-sans leading-relaxed">
          {ticket.content}
        </pre>
      )}
    </div>
  )
}

export function TicketsPanel({
  projectId,
  refreshKey,
}: {
  projectId: number
  refreshKey?: number
}) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    listTickets(projectId)
      .then(setTickets)
      .catch(() => setTickets([]))
      .finally(() => setLoading(false))
  }, [projectId, refreshKey])

  if (loading) return <p className="text-xs text-gray-400">Loading tickets…</p>
  if (tickets.length === 0)
    return <p className="text-xs text-gray-400 italic">No bug tickets filed.</p>

  return (
    <div className="space-y-2">
      {tickets.map((t) => (
        <TicketCard key={t.id} ticket={t} />
      ))}
    </div>
  )
}
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd frontend && npm test -- --run src/test/TicketsPanel.test.tsx
```

Expected: all 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/tickets.ts frontend/src/components/TicketsPanel.tsx frontend/src/test/TicketsPanel.test.tsx
git commit -m "feat: add Tickets API client and TicketsPanel component"
```

---

### Task 6: Frontend — Refactor LiveAgentView to use AgentTimeline

**Files:**
- Modify: `frontend/src/components/LiveAgentView.tsx`
- Modify: `frontend/src/test/LiveAgentView.test.tsx`

- [ ] **Step 1: Update the tool_result test to use the new expand interaction**

Replace the `'renders tool_result events'` test in `frontend/src/test/LiveAgentView.test.tsx`. Full updated test file:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach, act } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LiveAgentView } from '../components/LiveAgentView'

class MockEventSource {
  static instance: MockEventSource | null = null
  url: string
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  readyState = 1
  closed = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instance = this
  }

  close() {
    this.closed = true
    this.readyState = 2
  }

  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
}

beforeEach(() => {
  MockEventSource.instance = null
  vi.stubGlobal('EventSource', MockEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LiveAgentView', () => {
  it('connects to the correct SSE URL', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    expect(MockEventSource.instance?.url).toBe('/api/projects/1/runs/run-abc-123/stream')
  })

  it('renders text_delta events', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'text_delta',
        text: 'Analyzing source tree…',
        agent: 'reviewer',
      })
    })
    expect(screen.getByText('Analyzing source tree…')).toBeInTheDocument()
  })

  it('renders tool_use events showing tool name', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'tool_use',
        tool: 'list_files',
        input: {},
        agent: 'reviewer',
      })
    })
    expect(screen.getByText(/list_files/i)).toBeInTheDocument()
  })

  it('shows tool result after expanding a tool call row', async () => {
    const user = userEvent.setup()
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'tool_use',
        tool: 'list_files',
        input: { subdir: '' },
        agent: 'reviewer',
      })
      MockEventSource.instance?.emit({
        type: 'tool_result',
        tool: 'list_files',
        result: 'src/main.py',
        agent: 'reviewer',
      })
    })
    expect(screen.getByText(/list_files/i)).toBeInTheDocument()
    await user.click(screen.getByText(/list_files/i))
    expect(screen.getByText(/src\/main\.py/i)).toBeInTheDocument()
  })

  it('shows Audit complete on done event and closes connection', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'done',
        total_input_tokens: 1000,
        total_output_tokens: 500,
        cost_usd: 0.0105,
      })
    })
    expect(screen.getByText(/audit complete/i)).toBeInTheDocument()
    expect(MockEventSource.instance?.closed).toBe(true)
  })

  it('shows budget warning on budget_exceeded event', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({ type: 'budget_exceeded', cost_usd: 1.51 })
    })
    expect(screen.getByText(/budget/i)).toBeInTheDocument()
  })

  it('closes connection on unmount', () => {
    const { unmount } = render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    unmount()
    expect(MockEventSource.instance?.closed).toBe(true)
  })
})
```

- [ ] **Step 2: Run tests to see which ones fail before refactoring**

```bash
cd frontend && npm test -- --run src/test/LiveAgentView.test.tsx
```

Expected: `shows tool result after expanding a tool call row` FAILS (old component doesn't use AgentTimeline)

- [ ] **Step 3: Rewrite `frontend/src/components/LiveAgentView.tsx` using AgentTimeline**

```typescript
import { useEffect, useState } from 'react'
import { AgentTimeline, type AgentEvent } from './AgentTimeline'

export function LiveAgentView({
  projectId,
  runId,
  onComplete,
}: {
  projectId: number
  runId: string
  onComplete?: (status: string) => void
}) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [done, setDone] = useState(false)
  const [summary, setSummary] = useState<string | null>(null)

  useEffect(() => {
    const es = new EventSource(`/api/projects/${projectId}/runs/${runId}/stream`)

    es.onmessage = (e) => {
      const event = JSON.parse(e.data) as AgentEvent
      setEvents((prev) => [...prev, event])

      if (event.type === 'done') {
        setSummary(
          `Audit complete — ${event.total_input_tokens?.toLocaleString()} in / ` +
            `${event.total_output_tokens?.toLocaleString()} out tokens` +
            (event.cost_usd !== undefined ? ` ($${event.cost_usd.toFixed(4)})` : ''),
        )
        setDone(true)
        es.close()
        onComplete?.('done')
      } else if (event.type === 'budget_exceeded') {
        setSummary(`Budget limit reached ($${event.cost_usd?.toFixed(4)})`)
        setDone(true)
        es.close()
        onComplete?.('error')
      } else if (event.type === 'error') {
        setDone(true)
        es.close()
        onComplete?.('error')
      }
    }

    es.onerror = () => {
      setDone(true)
      es.close()
    }

    return () => es.close()
  }, [projectId, runId])

  return (
    <div className="space-y-3">
      <AgentTimeline events={events} defaultLabel="Reviewer" />
      {summary && <p className="text-sm text-gray-500 italic">{summary}</p>}
      {!done && (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="animate-pulse">●</span> Agent running…
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify all pass**

```bash
cd frontend && npm test -- --run src/test/LiveAgentView.test.tsx
```

Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LiveAgentView.tsx frontend/src/test/LiveAgentView.test.tsx
git commit -m "feat: refactor LiveAgentView to use AgentTimeline with expandable tool calls"
```

---

### Task 7: Frontend — Refactor QASessionView to use AgentTimeline

**Files:**
- Modify: `frontend/src/components/QASessionView.tsx`
- Modify: `frontend/src/test/QASessionView.test.tsx` (add one new test)

- [ ] **Step 1: Add a test that verifies tool_use input is displayed after expanding**

Add this test to `frontend/src/test/QASessionView.test.tsx` (append before the closing `})`):

```typescript
  it('shows tool input after expanding a tool call in the timeline', async () => {
    const user = userEvent.setup()
    _sseScenario = [
      { type: 'session_status', status: 'qa_running', fix_attempt: 0, ts: new Date().toISOString() },
      { type: 'tool_use', tool: 'list_files', input: { subdir: '' }, agent: 'qa' },
      { type: 'tool_result', tool: 'list_files', result: '["main.py"]', agent: 'qa' },
      { type: 'done', status: 'done' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => screen.getByText(/list_files/))
    await user.click(screen.getByText(/list_files/))
    expect(screen.getByText(/subdir/)).toBeInTheDocument()
    expect(screen.getByText(/main\.py/)).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npm test -- --run src/test/QASessionView.test.tsx
```

Expected: the new test FAILS (current QASessionView doesn't show tool inputs)

- [ ] **Step 3: Rewrite `frontend/src/components/QASessionView.tsx` using AgentTimeline**

```typescript
import { useState, useEffect } from 'react'
import { approveQASession, skipQASession } from '../api/qa_sessions'
import { AgentTimeline, type AgentEvent } from './AgentTimeline'

interface Props {
  projectId: number
  sessionId: string
  onComplete?: (status: string) => void
}

export function QASessionView({ projectId, sessionId, onComplete }: Props) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [hitlTicket, setHitlTicket] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [actioning, setActioning] = useState(false)
  const [totalCost, setTotalCost] = useState(0)

  useEffect(() => {
    const es = new EventSource(`/api/projects/${projectId}/qa-sessions/${sessionId}/stream`)

    es.onmessage = (evt) => {
      const event: AgentEvent = JSON.parse(evt.data)
      setEvents((prev) => [...prev, event])

      if (event.type === 'hitl_request' && event.ticket_id) {
        setHitlTicket(event.ticket_id)
      }
      if (event.type === 'session_status' && event.status !== 'hitl_waiting') {
        setHitlTicket(null)
      }
      if (event.type === 'qa_done' || event.type === 'coder_done') {
        setTotalCost((prev) => prev + (event.cost_usd ?? 0))
      }
      if (['done', 'error', 'budget_exceeded', 'timeout'].includes(event.type)) {
        setDone(true)
        es.close()
        onComplete?.(event.status ?? event.type)
      }
    }

    es.onerror = () => {
      setDone(true)
      es.close()
    }

    return () => es.close()
  }, [projectId, sessionId])

  async function handleApprove() {
    setActioning(true)
    try {
      await approveQASession(projectId, sessionId)
      setHitlTicket(null)
    } finally {
      setActioning(false)
    }
  }

  async function handleSkip() {
    setActioning(true)
    try {
      await skipQASession(projectId, sessionId)
      setHitlTicket(null)
    } finally {
      setActioning(false)
    }
  }

  return (
    <div className="space-y-3">
      <AgentTimeline events={events} />

      {totalCost > 0 && (
        <p className="text-xs text-gray-400">Running cost: ${totalCost.toFixed(4)}</p>
      )}

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

      {done && <p className="text-xs text-gray-400">Session complete.</p>}
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify all pass**

```bash
cd frontend && npm test -- --run src/test/QASessionView.test.tsx
```

Expected: all 6 tests PASS (5 original + 1 new)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/QASessionView.tsx frontend/src/test/QASessionView.test.tsx
git commit -m "feat: refactor QASessionView to use AgentTimeline with phase headers and expandable tool calls"
```

---

### Task 8: Frontend — ProjectDetailPage integration

**Files:**
- Modify: `frontend/src/pages/ProjectDetailPage.tsx`
- Modify: `frontend/src/test/ProjectDetailPage.test.tsx`

- [ ] **Step 1: Add a test for the Bug Tickets section**

Add this test to `frontend/src/test/ProjectDetailPage.test.tsx`. First, add the MSW handler for tickets to the existing `server` definition, then add the new test. Full updated file:

```typescript
import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { ProjectDetailPage } from '../pages/ProjectDetailPage'

vi.mock('../components/LiveAgentView', () => ({
  LiveAgentView: ({ runId }: { runId: string }) => (
    <div data-testid="live-agent-view">LiveAgentView:{runId}</div>
  ),
}))

vi.mock('../components/QASessionView', () => ({
  QASessionView: ({ sessionId }: { sessionId: string }) => (
    <div data-testid="qa-session-view">QASessionView:{sessionId}</div>
  ),
}))

vi.mock('../components/TicketsPanel', () => ({
  TicketsPanel: ({ projectId }: { projectId: number }) => (
    <div data-testid="tickets-panel">TicketsPanel:{projectId}</div>
  ),
}))

const server = setupServer(
  http.get('http://localhost/api/projects/1', () =>
    HttpResponse.json({
      id: 1,
      name: 'todo-api',
      canonical_path: '/d/projects/todo-api',
      created_at: '2026-04-24T00:00:00Z',
    }),
  ),
  http.get('http://localhost/api/projects/1/runs', () => HttpResponse.json([])),
  http.post('http://localhost/api/projects/1/runs', () =>
    HttpResponse.json({ run_id: 'run-xyz', status: 'pending' }, { status: 202 }),
  ),
  http.post('http://localhost/api/projects/1/qa-sessions', () =>
    HttpResponse.json({ session_id: 'sess-xyz', status: 'pending' }, { status: 202 }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/projects/1']}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProjectDetailPage', () => {
  it('shows project name after loading', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('todo-api')).toBeInTheDocument())
  })

  it('shows Run Init Audit button', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /run init audit/i })).toBeInTheDocument(),
    )
  })

  it('shows LiveAgentView after clicking Run Init Audit', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => screen.getByRole('button', { name: /run init audit/i }))
    await user.click(screen.getByRole('button', { name: /run init audit/i }))
    await waitFor(() =>
      expect(screen.getByTestId('live-agent-view')).toBeInTheDocument(),
    )
  })

  it('shows Run QA Session button', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /run qa session/i })).toBeInTheDocument(),
    )
  })

  it('starts a QA session when button clicked', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => screen.getByRole('button', { name: /run qa session/i }))
    await user.click(screen.getByRole('button', { name: /run qa session/i }))
    await waitFor(() => expect(screen.getByTestId('qa-session-view')).toBeInTheDocument())
  })

  it('renders the TicketsPanel section', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('tickets-panel')).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run the tests to see which fail before the integration**

```bash
cd frontend && npm test -- --run src/test/ProjectDetailPage.test.tsx
```

Expected: `renders the TicketsPanel section` FAILS (TicketsPanel not yet in the page)

- [ ] **Step 3: Update `frontend/src/pages/ProjectDetailPage.tsx` to add TicketsPanel and ticket refresh**

```typescript
import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getProject, listRuns, type Project, type AgentRunSummary } from '../api/projects'
import { createRun } from '../api/runs'
import { LiveAgentView } from '../components/LiveAgentView'
import { createQASession } from '../api/qa_sessions'
import { QASessionView } from '../components/QASessionView'
import { TicketsPanel } from '../components/TicketsPanel'

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === 'done'
      ? 'bg-green-100 text-green-700'
      : status === 'running' || status === 'qa_running' || status === 'coder_running'
      ? 'bg-blue-100 text-blue-700'
      : status === 'error'
      ? 'bg-red-100 text-red-700'
      : status === 'skipped'
      ? 'bg-gray-100 text-gray-500'
      : status === 'hitl_waiting'
      ? 'bg-yellow-100 text-yellow-700'
      : 'bg-gray-100 text-gray-600'
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${cls}`}
    >
      {(status === 'running' || status === 'qa_running' || status === 'coder_running') && (
        <span className="animate-pulse">●</span>
      )}
      {status}
    </span>
  )
}

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)

  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [pastRuns, setPastRuns] = useState<AgentRunSummary[]>([])
  const [qaSessionId, setQaSessionId] = useState<string | null>(null)
  const [qaStatus, setQaStatus] = useState<string | null>(null)
  const [startingQA, setStartingQA] = useState(false)
  const [ticketsRefreshKey, setTicketsRefreshKey] = useState(0)

  useEffect(() => {
    Promise.all([getProject(projectId), listRuns(projectId)])
      .then(([proj, runs]) => {
        setProject(proj)
        setPastRuns(runs)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [projectId])

  async function handleRunAudit() {
    setStarting(true)
    setError(null)
    try {
      const run = await createRun(projectId)
      setRunId(run.run_id)
      setPastRuns((prev) => [
        {
          id: 0,
          run_id: run.run_id,
          project_id: projectId,
          status: 'running',
          total_input_tokens: 0,
          total_output_tokens: 0,
          started_at: new Date().toISOString(),
          completed_at: null,
        },
        ...prev,
      ])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to start run')
    } finally {
      setStarting(false)
    }
  }

  function handleRunComplete(status: string) {
    if (!runId) return
    setPastRuns((prev) => prev.map((r) => (r.run_id === runId ? { ...r, status } : r)))
  }

  async function handleRunQA() {
    setStartingQA(true)
    setQaStatus(null)
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

  function handleQAComplete(status: string) {
    setQaStatus(status)
    setTicketsRefreshKey((k) => k + 1)
  }

  if (loading) return <p className="p-6">Loading project…</p>
  if (error && !project) return <p className="p-6 text-red-600">{error}</p>
  if (!project) return null

  const activeRunStatus = runId ? pastRuns.find((r) => r.run_id === runId)?.status : null

  return (
    <div className="max-w-3xl mx-auto p-6">
      <Link to="/" className="text-blue-600 hover:underline text-sm mb-4 block">
        ← All projects
      </Link>

      <h1 className="text-2xl font-bold mb-1">{project.name}</h1>
      <p className="text-gray-500 text-sm mb-6">{project.canonical_path}</p>

      {/* ── Init Audit ── */}
      <div className="flex items-center gap-3 mb-2">
        {!runId ? (
          <button
            onClick={handleRunAudit}
            disabled={starting}
            className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
          >
            {starting ? 'Starting…' : 'Run Init Audit'}
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 font-mono truncate max-w-[16rem]">{runId}</span>
            {activeRunStatus && <StatusBadge status={activeRunStatus} />}
          </div>
        )}
      </div>

      {error && <p className="text-red-600 mt-3">{error}</p>}

      {runId && (
        <div className="mt-4">
          <LiveAgentView projectId={projectId} runId={runId} onComplete={handleRunComplete} />
        </div>
      )}

      {/* ── Run history ── */}
      {pastRuns.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Run history
          </h2>
          <table className="w-full text-sm border rounded overflow-hidden">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="text-left px-3 py-2">Run ID</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-right px-3 py-2">In tokens</th>
                <th className="text-right px-3 py-2">Out tokens</th>
                <th className="text-left px-3 py-2">Started</th>
              </tr>
            </thead>
            <tbody>
              {pastRuns.map((run) => (
                <tr key={run.run_id} className="border-t hover:bg-gray-50">
                  <td className="px-3 py-2 font-mono text-xs text-gray-600 truncate max-w-[12rem]">
                    {run.run_id}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge status={run.status} />
                  </td>
                  <td className="px-3 py-2 text-right text-gray-600">
                    {run.total_input_tokens.toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-right text-gray-600">
                    {run.total_output_tokens.toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-gray-400 text-xs">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── QA / Test Session ── */}
      <div className="mt-8 border-t pt-6">
        <div className="flex items-center gap-3 mb-3">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
            QA / Test Session
          </h2>
          {qaSessionId && !qaStatus && <StatusBadge status="running" />}
          {qaStatus && <StatusBadge status={qaStatus} />}
        </div>

        {!qaSessionId || qaStatus ? (
          <button
            onClick={handleRunQA}
            disabled={startingQA}
            className="bg-purple-600 text-white px-4 py-2 rounded disabled:opacity-50"
          >
            {startingQA ? 'Starting…' : qaStatus ? 'Run New QA Session' : 'Run QA Session'}
          </button>
        ) : null}

        {qaSessionId && (
          <div className={qaStatus ? 'mt-4 opacity-60 pointer-events-none' : 'mt-4'}>
            <QASessionView
              projectId={projectId}
              sessionId={qaSessionId}
              onComplete={handleQAComplete}
            />
          </div>
        )}
      </div>

      {/* ── Bug Tickets ── */}
      <div className="mt-8 border-t pt-6">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Bug Tickets
        </h2>
        <TicketsPanel projectId={projectId} refreshKey={ticketsRefreshKey} />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify all pass**

```bash
cd frontend && npm test -- --run src/test/ProjectDetailPage.test.tsx
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/ProjectDetailPage.tsx frontend/src/test/ProjectDetailPage.test.tsx
git commit -m "feat: add TicketsPanel to ProjectDetailPage with post-QA refresh"
```

---

### Task 9: Full suite green

**Files:** none (verification only)

- [ ] **Step 1: Run the complete backend test suite**

```bash
docker exec smrt-llm-dev-backend-1 python -m pytest -v
```

Expected: all tests PASS. If any fail, fix them before proceeding.

- [ ] **Step 2: Run the complete frontend test suite**

```bash
cd frontend && npm test -- --run
```

Expected: all tests PASS. If any fail, fix them before proceeding.

- [ ] **Step 3: Run the TypeScript type check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: zero errors

- [ ] **Step 4: Commit if fixes were needed in steps 1–3**

If you had to make any fixes:

```bash
git add -p
git commit -m "fix: ensure full test suite passes after P4 observability changes"
```

- [ ] **Step 5: Create the pull request**

```bash
git push -u origin phase/4-observability
gh pr create \
  --title "P4: Live observability — AgentTimeline, expandable tool calls, Bug Tickets panel" \
  --body "## Summary
- AgentTimeline component groups SSE events into phase sections (Reviewer / QA Agent / Coder Agent) with collapsible tool call rows showing full input + result
- All SSE events now carry \`ts\` (ISO timestamp) and \`agent\` (reviewer/qa/coder) fields; tool result window expanded from 500 → 2000 chars
- New \`GET /projects/{id}/tickets\` endpoint lists \`.smrt/tickets/*.md\` files
- TicketsPanel component displays bug tickets with expandable content, auto-refreshes after QA session completes
- QASessionView shows running cost accumulator from qa_done / coder_done events

## Test plan
- [ ] Backend: \`docker exec smrt-llm-dev-backend-1 python -m pytest -v\` — all pass
- [ ] Frontend: \`cd frontend && npm test -- --run\` — all pass
- [ ] TypeScript: \`cd frontend && npx tsc --noEmit\` — zero errors
- [ ] Manual: run an Init Audit, expand tool call rows, verify inputs + results visible
- [ ] Manual: run a QA session, verify phase headers (QA Agent / Coder Agent) appear
- [ ] Manual: verify Bug Tickets panel shows filed tickets after QA completes

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

## Self-Review

### 1. Spec coverage check

| User requirement | Task that covers it |
|---|---|
| Show tool inputs | T4 (AgentTimeline expandable tool rows) |
| Show tool results | T4 (AgentTimeline expand → shows result) |
| Phase headers per agent | T4 (groupIntoPhases, PhaseSection labels) |
| Timestamps on events | T2 (ts field added to all events) |
| Agent label on all events | T2 (agent: "reviewer" added to reviewer loop) |
| Larger result window | T2 (500 → 2000 chars in all loops) |
| Bug tickets visible in UI | T5 (TicketsPanel) + T3 (API) |
| Ticket content expandable | T5 (TicketCard expand/collapse) |
| Tickets refresh after QA | T8 (ticketsRefreshKey bumped in handleQAComplete) |
| Running cost display | T7 (totalCost accumulated from qa_done/coder_done) |
| Recheck output formatted | T4 (PhaseSection renders recheckEvent in green/red pre) |

### 2. Placeholder scan

No placeholders found — every step contains complete code.

### 3. Type consistency

- `AgentEvent` exported from `AgentTimeline.tsx`, imported in `LiveAgentView.tsx` and `QASessionView.tsx` — consistent throughout
- `Ticket` exported from `tickets.ts`, used in `TicketsPanel.tsx` — consistent
- `groupIntoPhases(events, defaultLabel)` called with both arguments in `AgentTimeline` — matches definition
- `ToolCallPair.use` and `.result` both typed as `AgentEvent | null` — `ToolCallRow` uses `pair.result` with null check — consistent
- `AGENT_STYLES` keys match `agentType` values assigned in `groupIntoPhases` (`reviewer`, `qa`, `coder`, `system`) — consistent
