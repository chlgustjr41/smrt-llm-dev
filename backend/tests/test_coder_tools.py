import pytest
from pathlib import Path
from smrt_agent.agents.coder.tools import read_source_file, write_source_file


def test_read_source_file(tmp_path):
    (tmp_path / "app.py").write_text("print('hello')", encoding="utf-8")
    result = read_source_file(tmp_path, "app.py")
    assert result == "print('hello')"


def test_read_source_file_blocks_smrt(tmp_path):
    (tmp_path / ".smrt").mkdir()
    (tmp_path / ".smrt" / "notes.md").write_text("secret", encoding="utf-8")
    with pytest.raises(PermissionError, match=".smrt"):
        read_source_file(tmp_path, ".smrt/notes.md")


def test_read_source_file_blocks_traversal(tmp_path):
    with pytest.raises(PermissionError):
        read_source_file(tmp_path, "../outside.py")


def test_write_source_file(tmp_path):
    result = write_source_file(tmp_path, "src/fix.py", "x = 1\n")
    assert "6 bytes" in result
    assert "src/fix.py" in result
    assert (tmp_path / "src" / "fix.py").read_text(encoding="utf-8") == "x = 1\n"


def test_read_source_file_blocks_tests(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_private.py").write_text("pass", encoding="utf-8")
    with pytest.raises(PermissionError, match="tests"):
        read_source_file(tmp_path, "tests/test_private.py")


def test_read_source_file_blocks_docs(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "internal.md").write_text("internal", encoding="utf-8")
    with pytest.raises(PermissionError, match="docs"):
        read_source_file(tmp_path, "docs/internal.md")


def test_write_source_file_blocks_smrt(tmp_path):
    with pytest.raises(PermissionError, match=".smrt"):
        write_source_file(tmp_path, ".smrt/injected.py", "bad")


def test_write_source_file_blocks_tests(tmp_path):
    with pytest.raises(PermissionError, match="tests"):
        write_source_file(tmp_path, "tests/test_fake.py", "bad")


def test_write_source_file_blocks_docs(tmp_path):
    with pytest.raises(PermissionError, match="docs"):
        write_source_file(tmp_path, "docs/README.md", "bad")
