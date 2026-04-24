"""Reviewer agent tools: list_files, read_file, fetch_url, write_file."""
import os
from pathlib import Path

import pathspec
import requests

_SECRET_SPEC = pathspec.PathSpec.from_lines("gitwildmatch", [
    "*.env", ".env", ".env.*", "*secret*", "*credential*",
    "*.pem", "*.key", "*password*", "*.p12", "*.pfx",
])

_SKIP_DIRS = {".git", ".smrt", "__pycache__", "node_modules", ".venv", "venv"}


def _gitignore_spec(project_path: Path) -> pathspec.PathSpec:
    gi = project_path / ".gitignore"
    if gi.exists():
        return pathspec.PathSpec.from_lines("gitwildmatch", gi.read_text().splitlines())
    return pathspec.PathSpec.from_lines("gitwildmatch", [])


def list_files(project_path: Path, subdir: str = "") -> list[str]:
    """Return sorted relative paths of all non-secret, non-gitignored source files."""
    base = project_path / subdir if subdir else project_path
    spec = _gitignore_spec(project_path)
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
    if not rel_path.startswith(".smrt/"):
        raise PermissionError(f"write_file may only write inside .smrt/: {rel_path!r}")
    target = (project_path / rel_path).resolve()
    root = project_path.resolve()
    if not target.is_relative_to(root):
        raise PermissionError(f"Path traversal denied: {rel_path!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {rel_path}"
