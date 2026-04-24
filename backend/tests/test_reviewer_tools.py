import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from smrt_agent.agents.reviewer.tools import list_files, read_file, fetch_url, write_file


def _make_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
    (tmp_path / "src" / "models.py").write_text("class User: pass")
    (tmp_path / "requirements.txt").write_text("fastapi\n")
    (tmp_path / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    (tmp_path / "src" / "__pycache__").mkdir()
    (tmp_path / "src" / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"")
    return tmp_path


def test_list_files_returns_source_files(tmp_path):
    project = _make_project(tmp_path)
    files = list_files(project)
    assert "src/main.py" in files
    assert "src/models.py" in files
    assert "requirements.txt" in files


def test_list_files_excludes_gitignored(tmp_path):
    project = _make_project(tmp_path)
    files = list_files(project)
    assert not any("__pycache__" in f for f in files)
    assert not any(".pyc" in f for f in files)


def test_list_files_excludes_secrets(tmp_path):
    project = _make_project(tmp_path)
    (tmp_path / ".env").write_text("SECRET=abc")
    (tmp_path / "secrets.yaml").write_text("password: abc")
    files = list_files(project)
    assert ".env" not in files
    assert "secrets.yaml" not in files


def test_read_file_returns_content(tmp_path):
    project = _make_project(tmp_path)
    content = read_file(project, "src/main.py")
    assert "FastAPI" in content


def test_read_file_blocks_path_traversal(tmp_path):
    project = _make_project(tmp_path)
    with pytest.raises(PermissionError):
        read_file(project, "../../etc/passwd")


def test_read_file_blocks_secret_files(tmp_path):
    project = _make_project(tmp_path)
    (tmp_path / ".env").write_text("SECRET=abc")
    with pytest.raises(PermissionError):
        read_file(project, ".env")


def test_fetch_url_returns_text():
    mock_resp = MagicMock()
    mock_resp.text = '{"openapi": "3.0.0"}'
    mock_resp.raise_for_status = MagicMock()
    with patch("smrt_agent.agents.reviewer.tools.requests.get", return_value=mock_resp) as mock_get:
        result = fetch_url("http://172.18.0.2:8080/openapi.json")
    assert '{"openapi"' in result
    mock_get.assert_called_once_with("http://172.18.0.2:8080/openapi.json", timeout=10)


def test_write_file_creates_smrt_file(tmp_path):
    project = _make_project(tmp_path)
    result = write_file(project, ".smrt/Project.md", "# My Project\n")
    assert "Wrote" in result
    assert (tmp_path / ".smrt" / "Project.md").read_text() == "# My Project\n"


def test_write_file_creates_parent_dirs(tmp_path):
    project = _make_project(tmp_path)
    write_file(project, ".smrt/nested/dir/file.md", "content")
    assert (tmp_path / ".smrt" / "nested" / "dir" / "file.md").exists()


def test_write_file_blocks_writes_outside_smrt(tmp_path):
    project = _make_project(tmp_path)
    with pytest.raises(PermissionError):
        write_file(project, "src/injected.py", "import os; os.system('rm -rf /')")


def test_write_file_blocks_path_traversal(tmp_path):
    project = _make_project(tmp_path)
    with pytest.raises(PermissionError):
        write_file(project, ".smrt/../../outside.txt", "bad")
