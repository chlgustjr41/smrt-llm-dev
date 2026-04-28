"""Secret guard hook: prevents agents from reading sensitive files.

check_path(project_path, file_path) -> str | None
    Returns None if access is allowed, or a denial reason string if blocked.

is_blocked(project_path, file_path) -> tuple[bool, str]
    Returns (blocked, reason); reason is empty string when not blocked.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath

try:
    import pathspec as _pathspec

    _PATHSPEC_AVAILABLE = True
except ImportError:
    _pathspec = None  # type: ignore[assignment]
    _PATHSPEC_AVAILABLE = False

# ---------------------------------------------------------------------------
# Always-deny patterns (applied to basename AND full relative path)
# ---------------------------------------------------------------------------

# Exact name matches
_EXACT_DENY: frozenset[str] = frozenset(
    {
        ".env",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "credentials.json",
        "secrets.yaml",
        "secrets.yml",
        "secret.yml",
        "secret.yaml",
        ".netrc",
        ".npmrc",
        ".pypirc",
    }
)

# Glob patterns matched against the basename
_GLOB_DENY: tuple[str, ...] = (
    ".env.*",
    ".env_*",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.crt",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "*.ppk",
    "service-account*.json",
    "gcloud-key*.json",
)

# Path prefix segments that are always blocked (applied to the full path)
_PREFIX_DENY: tuple[str, ...] = (
    ".aws/",
    ".azure/",
    ".gcloud/",
    ".git/",
)

# Exact relative sub-paths (anywhere in the tree)
_SUBPATH_DENY: tuple[str, ...] = (
    ".kube/config",
)

def _normalise(file_path: str) -> str:
    """Return the path with forward slashes, no leading slash."""
    return file_path.replace("\\", "/").lstrip("/")


def _basename(file_path: str) -> str:
    return PurePosixPath(_normalise(file_path)).name


def _check_always_deny(norm_path: str) -> str | None:
    """Return a denial reason if the path hits any always-deny rule."""
    name = _basename(norm_path)

    # Exact name check
    if name in _EXACT_DENY:
        return f"sensitive file '{name}' is always blocked"

    # Glob pattern check on basename
    for pat in _GLOB_DENY:
        if fnmatch.fnmatch(name, pat):
            return f"filename '{name}' matches sensitive pattern '{pat}'"

    # Also match glob patterns against the full relative path
    for pat in _GLOB_DENY:
        if fnmatch.fnmatch(norm_path, pat):
            return f"path '{norm_path}' matches sensitive pattern '{pat}'"

    # Prefix checks (full path)
    for prefix in _PREFIX_DENY:
        if norm_path == prefix.rstrip("/") or norm_path.startswith(prefix):
            return f"path is inside always-blocked directory '{prefix}'"

    # Sub-path checks
    for sub in _SUBPATH_DENY:
        # Check if path equals sub, or any trailing component equals sub
        if norm_path == sub or norm_path.endswith("/" + sub):
            return f"path '{norm_path}' matches always-blocked path '{sub}'"

    return None


def _load_agentignore_specs(project_path: Path) -> "list[tuple[str, object]]":
    """Walk project_path and collect (base_dir_prefix, PathSpec) pairs from .agentignore files.

    Returns an empty list if pathspec is not available or no .agentignore files exist.
    """
    if not _PATHSPEC_AVAILABLE:
        return []

    specs: list[tuple[str, object]] = []

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
        if prefix == ".":
            prefix = ""
        spec = _pathspec.PathSpec.from_lines("gitwildmatch", lines)  # type: ignore[union-attr]
        specs.append((prefix, spec))

    return specs


def _check_agentignore(
    specs: "list[tuple[str, object]]",
    norm_path: str,
) -> str | None:
    """Return a denial reason if norm_path is matched by any loaded .agentignore spec."""
    if not specs:
        return None

    for base_prefix, spec in specs:
        if base_prefix:
            if not norm_path.startswith(base_prefix + "/"):
                continue
            relative_to_spec = norm_path[len(base_prefix) + 1 :]
        else:
            relative_to_spec = norm_path

        if spec.match_file(relative_to_spec):  # type: ignore[union-attr]
            return f"path '{norm_path}' is matched by .agentignore"

    return None


def check_path(project_path: Path, file_path: str) -> str | None:
    """Return denial reason string, or None if access is allowed."""
    norm = _normalise(file_path)

    # 1. Always-deny list
    reason = _check_always_deny(norm)
    if reason:
        return reason

    # 2. .agentignore check (project-specific deny list for secrets)
    specs = _load_agentignore_specs(project_path)
    reason = _check_agentignore(specs, norm)
    if reason:
        return reason

    return None


def is_blocked(project_path: Path, file_path: str) -> tuple[bool, str]:
    """Return (blocked, reason). reason is empty string when not blocked."""
    reason = check_path(project_path, file_path)
    if reason is None:
        return False, ""
    return True, reason
