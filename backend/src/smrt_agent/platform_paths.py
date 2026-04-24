"""Cross-platform path normalization at the registration boundary.

All internal logic uses POSIX-style strings. Windows drive letters are
rewritten as /d/, /c/, etc. so Docker bind-mounts work uniformly.
"""
import re
import sys
from pathlib import Path, PurePosixPath

_WIN_DRIVE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def canonicalize(host_path: str) -> str:
    """Convert a host-OS path to a canonical POSIX-style string.

    Rejects any input containing parent-traversal segments (`..`).
    Translates Windows drive letters to /<letter>/ regardless of platform,
    so that allowlist entries and user inputs are normalized consistently even
    when the backend runs on Linux inside Docker.
    """
    # Always try the Windows drive-letter regex first so that both the
    # submitted path and any allowlist roots (which may be Windows-style)
    # round-trip through the same canonical form.
    m = _WIN_DRIVE.match(host_path)
    if m:
        drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
        canonical = str(PurePosixPath(f"/{drive}/{rest}"))
    else:
        canonical = str(PurePosixPath(host_path.replace("\\", "/")))

    if ".." in PurePosixPath(canonical).parts:
        raise ValueError(f"parent traversal not allowed: {host_path!r}")

    return canonical


def to_docker_mount(host_path: str) -> str:
    """Translate a host path into a string usable in a Docker bind-mount.

    Windows uses //d/foo form; POSIX uses the path as-is.
    """
    if sys.platform == "win32":
        m = _WIN_DRIVE.match(host_path)
        if m:
            drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
            return f"//{drive}/{rest}"
    return host_path
