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
