import sys
import pytest
from smrt_agent.platform_paths import canonicalize, to_docker_mount


def test_canonicalize_returns_posix_string():
    if sys.platform == "win32":
        assert canonicalize("D:\\web-project\\foo") == "/d/web-project/foo"
    else:
        assert canonicalize("/Users/jdoe/foo") == "/Users/jdoe/foo"


def test_canonicalize_rejects_dotdot():
    with pytest.raises(ValueError, match="parent traversal"):
        canonicalize("/foo/../bar")


def test_to_docker_mount_windows_form(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    assert to_docker_mount("D:\\web-project\\foo") == "//d/web-project/foo"


def test_to_docker_mount_posix_passthrough(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    assert to_docker_mount("/Users/jdoe/foo") == "/Users/jdoe/foo"
