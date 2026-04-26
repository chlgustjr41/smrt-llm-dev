"""Verify the Coder agent cannot read or write the tests/ directory (blackbox invariant)."""
import pytest
from smrt_agent.agents.coder.tools import read_source_file, write_source_file


def test_read_source_file_blocks_tests_directory(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_foo.py").write_text("def test_foo(): pass", encoding="utf-8")
    with pytest.raises(PermissionError, match="tests"):
        read_source_file(tmp_path, "tests/test_foo.py")


def test_write_source_file_blocks_tests_directory(tmp_path):
    (tmp_path / "tests").mkdir()
    with pytest.raises(PermissionError, match="tests"):
        write_source_file(tmp_path, "tests/test_foo.py", "def test_injected(): pass")


def test_read_source_file_blocks_smrt_directory(tmp_path):
    (tmp_path / ".smrt").mkdir()
    (tmp_path / ".smrt" / "secret.json").write_text("{}", encoding="utf-8")
    with pytest.raises(PermissionError, match=r"\.smrt"):
        read_source_file(tmp_path, ".smrt/secret.json")


def test_write_source_file_blocks_smrt_directory(tmp_path):
    with pytest.raises(PermissionError, match=r"\.smrt"):
        write_source_file(tmp_path, ".smrt/injected.json", "{}")


def test_read_source_file_allows_normal_source(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("# app entry point", encoding="utf-8")
    result = read_source_file(tmp_path, "src/main.py")
    assert "app entry point" in result


def test_write_source_file_allows_normal_source(tmp_path):
    result = write_source_file(tmp_path, "main.py", "# fixed content")
    assert "Wrote" in result
    assert (tmp_path / "main.py").read_text() == "# fixed content"
