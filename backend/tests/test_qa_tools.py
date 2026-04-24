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
    append_bugs_resolved(tmp_path, "2026-04-24-002", "Fixed second bug")
    content = (tmp_path / ".smrt" / "bugs-resolved.md").read_text()
    assert "2026-04-24-001" in content
    assert "2026-04-24-002" in content
    assert "Fixed null pointer" in content
    assert "Fixed second bug" in content


from smrt_agent.agents.qa.budget import TOOL_DEFINITIONS as QA_TOOLS
from smrt_agent.agents.coder.budget import TOOL_DEFINITIONS as CODER_TOOLS

def test_qa_tool_definitions():
    names = {t["name"] for t in QA_TOOLS}
    assert names == {"list_files", "read_file", "write_test_file", "run_pytest",
                     "write_bug_ticket", "write_test_status", "append_bugs_resolved"}

def test_coder_tool_definitions():
    names = {t["name"] for t in CODER_TOOLS}
    assert names == {"list_files", "read_source_file", "write_source_file"}


from pathlib import Path

def test_qa_prompt_exists():
    prompt = Path(__file__).parent.parent / "src/smrt_agent/prompts/qa.md"
    assert prompt.exists(), "qa.md prompt missing"
    assert len(prompt.read_text()) > 100

def test_coder_prompt_exists():
    prompt = Path(__file__).parent.parent / "src/smrt_agent/prompts/coder.md"
    assert prompt.exists(), "coder.md prompt missing"
    assert len(prompt.read_text()) > 100


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
