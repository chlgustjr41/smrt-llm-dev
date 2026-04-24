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
