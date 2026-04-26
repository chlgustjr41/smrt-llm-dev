"""Coder agent tools: read_source_file, write_source_file."""
from pathlib import Path

from smrt_agent.agents.reviewer.tools import _SECRET_SPEC
from smrt_agent.hooks.secret_guard import is_blocked

_BLOCKED_DIRS = {".smrt", "tests", "docs"}


def read_source_file(project_path: Path, rel_path: str) -> str:
    """Read a source file. Blocks .smrt/, tests/, docs/ and secret files."""
    blocked, reason = is_blocked(project_path, rel_path)
    if blocked:
        return f"Access denied: {reason}"
    first_part = Path(rel_path).parts[0] if Path(rel_path).parts else ""
    if first_part in _BLOCKED_DIRS:
        raise PermissionError(f"read_source_file cannot read from {first_part}/: {rel_path!r}")
    if _SECRET_SPEC.match_file(rel_path):
        raise PermissionError(f"Secret file access denied: {rel_path!r}")
    target = (project_path / rel_path).resolve()
    root = project_path.resolve()
    if not target.is_relative_to(root):
        raise PermissionError(f"Path traversal denied: {rel_path!r}")
    return target.read_text(errors="replace")


def write_source_file(project_path: Path, rel_path: str, content: str) -> str:
    """Write/overwrite a source file. Blocks .smrt/, tests/, docs/."""
    blocked, reason = is_blocked(project_path, rel_path)
    if blocked:
        return f"Access denied: {reason}"
    first_part = Path(rel_path).parts[0] if Path(rel_path).parts else ""
    if first_part in _BLOCKED_DIRS:
        raise PermissionError(f"write_source_file cannot write to {first_part}/: {rel_path!r}")
    if _SECRET_SPEC.match_file(rel_path):
        raise PermissionError(f"Cannot overwrite secret file: {rel_path!r}")
    target = (project_path / rel_path).resolve()
    root = project_path.resolve()
    if not target.is_relative_to(root):
        raise PermissionError(f"Path traversal denied: {rel_path!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {rel_path}"
