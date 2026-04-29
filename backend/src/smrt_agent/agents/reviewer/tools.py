"""Reviewer agent tools: list_files, read_file, fetch_url, write_file."""
import os
from pathlib import Path

import pathspec
import requests

from smrt_agent.hooks.secret_guard import is_blocked

_SECRET_SPEC = pathspec.PathSpec.from_lines("gitwildmatch", [
    "*.env", ".env", ".env.*", "*secret*", "*credential*",
    "*.pem", "*.key", "*password*", "*.p12", "*.pfx",
])

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def _agentignore_spec(project_path: Path) -> pathspec.PathSpec:
    """Build a single PathSpec from all .agentignore files in the project tree.

    Nested .agentignore files (e.g. eval-fixtures/todo-api/.agentignore) have
    their patterns prefixed with the relative directory so that patterns are
    always matched against paths relative to project_path.
    """
    patterns: list[str] = []
    for ai_file in sorted(project_path.rglob(".agentignore")):
        try:
            lines = ai_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        try:
            rel_dir = ai_file.parent.relative_to(project_path)
        except ValueError:
            continue
        prefix = str(rel_dir).replace("\\", "/")
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Root-level .agentignore: use the pattern as-is
            # Nested .agentignore: prefix pattern with its directory
            patterns.append(stripped if prefix == "." else f"{prefix}/{stripped}")
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def list_files(project_path: Path, subdir: str = "") -> list[str]:
    """Return sorted relative paths of all non-secret, non-agentignored source files."""
    if subdir:
        blocked, reason = is_blocked(project_path, subdir)
        if blocked:
            return [f"Access denied: {reason}"]
    base = project_path / subdir if subdir else project_path
    spec = _agentignore_spec(project_path)
    result = []
    for root, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        for f in sorted(files):
            full = Path(root) / f
            try:
                rel = str(full.relative_to(project_path)).replace("\\", "/")
            except ValueError:
                continue
            if not spec.match_file(rel) and not _SECRET_SPEC.match_file(rel):
                result.append(rel)
    return sorted(result)


def read_file(project_path: Path, rel_path: str) -> str:
    """Read a project file. Blocks path traversal and secret files."""
    blocked, reason = is_blocked(project_path, rel_path)
    if blocked:
        return f"Access denied: {reason}"
    if _SECRET_SPEC.match_file(rel_path):
        raise PermissionError(f"Secret file access denied: {rel_path!r}")
    target = (project_path / rel_path).resolve()
    root = project_path.resolve()
    if not target.is_relative_to(root):
        raise PermissionError(f"Path traversal denied: {rel_path!r}")
    return target.read_text(errors="replace")


def fetch_url(url: str) -> str:
    """Fetch a URL and return the response body as text."""
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.text


def write_file(project_path: Path, rel_path: str, content: str) -> str:
    """Write a file. ONLY permitted inside .smrt/."""
    blocked, reason = is_blocked(project_path, rel_path)
    if blocked:
        return f"Access denied: {reason}"
    if not rel_path.startswith(".smrt/"):
        raise PermissionError(f"write_file may only write inside .smrt/: {rel_path!r}")
    target = (project_path / rel_path).resolve()
    root = project_path.resolve()
    if not target.is_relative_to(root):
        raise PermissionError(f"Path traversal denied: {rel_path!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {rel_path}"


def write_readme(project_path: Path, content: str) -> str:
    """Write the project's top-level README.md.

    Always targets `<project_root>/README.md`. The agent is responsible for
    deciding *whether* to write — it should `read_file('README.md')` first
    and skip when the existing README is already substantive. We don't
    enforce that policy in the tool because the threshold is fuzzy and
    better expressed in the prompt; here we just guarantee the destination
    is always the project root.

    Returns a status string the agent can act on.
    """
    target = (project_path / "README.md").resolve()
    root = project_path.resolve()
    if not target.is_relative_to(root):
        raise PermissionError("Path traversal denied for README.md")
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to README.md"


def write_docs_file(project_path: Path, rel_path: str, content: str) -> str:
    """Write a technical documentation file inside `docs/`.

    The Reviewer uses this to add file-structure-based documentation that
    complements the auto-generated module/endpoint stubs. Examples:
      - docs/architecture.md       — high-level design and layering
      - docs/modules/auth.md       — deep dive on a specific module
      - docs/data-model.md         — DB schema or domain model overview

    Path restrictions:
      - MUST start with `docs/`
      - MUST end with `.md`
      - No path traversal (resolved path must stay inside project root)
      - Filename must not contain spaces or path separators that break
        Obsidian's vault scanning
    """
    if not rel_path.startswith("docs/"):
        raise PermissionError(
            f"write_docs_file may only write inside docs/: {rel_path!r}"
        )
    if not rel_path.endswith(".md"):
        raise ValueError(
            f"write_docs_file path must end in .md: {rel_path!r}"
        )
    if ".." in rel_path.split("/"):
        raise PermissionError(f"Path traversal denied: {rel_path!r}")

    target = (project_path / rel_path).resolve()
    root = project_path.resolve()
    if not target.is_relative_to(root):
        raise PermissionError(f"Path traversal denied: {rel_path!r}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {rel_path}"
