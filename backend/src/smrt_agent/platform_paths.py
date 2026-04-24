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
    Translates Windows drive letters to /<letter>/.
    """
    if ".." in Path(host_path).parts:
        raise ValueError(f"parent traversal not allowed: {host_path!r}")

    if sys.platform == "win32":
        m = _WIN_DRIVE.match(host_path)
        if m:
            drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
            return str(PurePosixPath(f"/{drive}/{rest}"))
    return str(PurePosixPath(Path(host_path).as_posix()))


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
