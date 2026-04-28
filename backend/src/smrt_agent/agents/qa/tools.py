"""QA agent tools: write_test_file, run_pytest, write_bug_ticket, write_test_status, append_bugs_resolved."""
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from smrt_agent.hooks.secret_guard import is_blocked


def write_test_file(project_path: Path, filename: str, content: str) -> str:
    """Write a test file to .smrt/tests/. filename must end with .py and contain no path separators."""
    blocked, reason = is_blocked(project_path, filename)
    if blocked:
        return f"Access denied: {reason}"
    if not filename.endswith(".py"):
        raise ValueError(f"Test filename must end with .py: {filename!r}")
    if "/" in filename or "\\" in filename:
        raise PermissionError(f"filename must not contain path separators: {filename!r}")
    target = (project_path / ".smrt" / "tests" / filename).resolve()
    expected_root = (project_path / ".smrt" / "tests").resolve()
    if not target.is_relative_to(expected_root):
        raise PermissionError(f"Path traversal denied: {filename!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to .smrt/tests/{filename}"


def run_pytest(project_path: Path, timeout_seconds: int = 120) -> str:
    """Run pytest in .smrt/tests/. Returns raw pytest output (stdout + stderr).

    Catches TimeoutExpired so callers never crash on a hung test suite — the
    timeout message is returned as part of the output, which lets the Coder
    agent see what happened and still attempt a fix. Source-code infinite
    loops in the tested package are the most common trigger for this path.
    """
    tests_dir = project_path / ".smrt" / "tests"
    if not tests_dir.exists() or not list(tests_dir.glob("test_*.py")):
        return "No test files found in .smrt/tests/"
    env = {**os.environ, "PYTHONPATH": str(project_path)}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(tests_dir), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(project_path),
            env=env,
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired as exc:
        partial = ""
        if exc.stdout:
            partial += exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout
        if exc.stderr:
            partial += exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
        return (
            f"PYTEST TIMEOUT: tests did not finish within {timeout_seconds}s. "
            f"This usually means the source code under test has an infinite loop "
            f"or is blocking on I/O. The fix should address whatever is hanging.\n"
            f"--- partial output ---\n{partial}"
        )
    except Exception as exc:
        return f"PYTEST ERROR: {exc}"


def collect_coverage(project_path: Path) -> dict | None:
    """Run pytest with coverage and store results to .smrt/knowledge/coverage.json.

    Also saves .smrt/knowledge/coverage_context.json: a mapping of
    source-file basename → list of test node IDs that touched it, used
    by the Tests tab hover tooltip to show indirect test coverage.

    Requires pytest-cov >= 2.10. Returns the parsed coverage dict on success.
    """
    import json as _json

    tests_dir = project_path / ".smrt" / "tests"
    if not tests_dir.exists() or not list(tests_dir.glob("test_*.py")):
        return None

    cov_out = project_path / ".smrt" / "knowledge" / "coverage.json"
    cov_out.parent.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, "PYTHONPATH": str(project_path)}
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", str(tests_dir),
            "--tb=no", "-q",
            "--cov=.", f"--cov-report=json:{cov_out}",
            "--cov-context=test",  # record test node ID as context per covered line
            "--no-header",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(project_path),
        env=env,
    )
    # returncode 0=all pass, 1=some fail — both are fine; >1 means setup error
    if result.returncode > 1 and "no module named pytest_cov" in (result.stdout + result.stderr).lower():
        return None

    if cov_out.exists():
        try:
            data = _json.loads(cov_out.read_text(encoding="utf-8"))
            # Build source basename → [test_node_ids] from coverage contexts
            file_to_tests: dict[str, list[str]] = {}
            for fpath, finfo in data.get("files", {}).items():
                basename = Path(fpath).name
                test_ids: set[str] = set()
                for line_contexts in finfo.get("contexts", {}).values():
                    for ctx in line_contexts:
                        if "::" in ctx:  # test node IDs always contain ::
                            test_ids.add(ctx)
                if test_ids:
                    file_to_tests[basename] = sorted(test_ids)
            ctx_out = cov_out.parent / "coverage_context.json"
            ctx_out.write_text(
                _json.dumps({"file_tests": file_to_tests}, indent=2), encoding="utf-8"
            )
            return data
        except Exception:
            pass
    return None


def write_bug_ticket(project_path: Path, title: str, description: str, test_output: str) -> str:
    """Write a bug ticket to .smrt/tickets/YYYY-MM-DD-NNN.md. Returns the ticket ID."""
    tickets_dir = project_path / ".smrt" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    seq = 1
    while True:
        ticket_id = f"{today}-{seq:03d}"
        ticket_path = tickets_dir / f"{ticket_id}.md"
        try:
            fd = ticket_path.open("x", encoding="utf-8")
            fd.close()
            break
        except FileExistsError:
            seq += 1
    content = (
        f"# Bug Ticket {ticket_id}\n\n"
        f"**Title:** {title}\n\n"
        f"## Description\n\n{description}\n\n"
        f"## Test Output\n\n```\n{test_output}\n```\n"
    )
    ticket_path.write_text(content, encoding="utf-8")
    return ticket_id


def write_test_status(project_path: Path, content: str) -> str:
    """Overwrite .smrt/test-status.md with the current test run summary."""
    target = project_path / ".smrt" / "test-status.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote test-status.md ({len(content)} bytes)"


def append_bugs_resolved(project_path: Path, ticket_id: str, resolution: str) -> str:
    """Append a resolution entry to .smrt/bugs-resolved.md."""
    target = project_path / ".smrt" / "bugs-resolved.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = f"\n## {ticket_id}\n\n{resolution}\n"
    with open(target, "a", encoding="utf-8") as f:
        f.write(entry)
    return f"Appended resolution for {ticket_id}"
