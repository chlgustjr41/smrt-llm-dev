import asyncio
import pytest
from pathlib import Path
from smrt_agent.docs.service import generate_docs

SAMPLE_MD = """\
# Project: todo-api

## Purpose
A simple todo API.

## Endpoints
| Method | Path | Auth required | Purpose |
|--------|------|---------------|---------|
| GET | /items | No | List items |
| POST | /items | Yes | Create item |
"""


def test_generate_docs_creates_obsidian_files(tmp_path):
    smrt_dir = tmp_path / ".smrt"
    smrt_dir.mkdir()
    (smrt_dir / "Project.md").write_text(SAMPLE_MD, encoding="utf-8")
    result = asyncio.run(generate_docs(tmp_path))
    assert result["backends"] == 1
    assert result["endpoints"] == 2
    assert (tmp_path / "docs" / "modules" / "todo-api.md").exists()
    assert (tmp_path / "docs" / "api" / "GET_items.md").exists()
    assert (tmp_path / "docs" / "api" / "POST_items.md").exists()


def test_generate_docs_no_project_md_returns_zero_endpoints(tmp_path):
    result = asyncio.run(generate_docs(tmp_path))
    assert result["backends"] == 1
    assert result["endpoints"] == 0
