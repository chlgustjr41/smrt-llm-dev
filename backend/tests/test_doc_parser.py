from pathlib import Path
from smrt_agent.docs.parser import parse_endpoints, parse_module_doc, load_and_parse

SAMPLE_MD = """\
# Project: todo-api

## Purpose
A simple todo list API for managing tasks.

## Endpoints
| Method | Path | Auth required | Purpose |
|--------|------|---------------|---------|
| GET | /items | No | List all items |
| POST | /items | Yes | Create a new item |
| DELETE | /items/{id} | Yes | Delete an item |

## Lessons
<!-- empty -->
"""


def test_parse_endpoints_count():
    eps = parse_endpoints(SAMPLE_MD)
    assert len(eps) == 3


def test_parse_endpoints_methods():
    eps = parse_endpoints(SAMPLE_MD)
    methods = {e.method for e in eps}
    assert methods == {"GET", "POST", "DELETE"}


def test_parse_endpoints_auth_required():
    eps = parse_endpoints(SAMPLE_MD)
    get_ep = next(e for e in eps if e.method == "GET")
    post_ep = next(e for e in eps if e.method == "POST")
    assert get_ep.auth_required is False
    assert post_ep.auth_required is True


def test_parse_endpoints_purpose():
    eps = parse_endpoints(SAMPLE_MD)
    get_ep = next(e for e in eps if e.method == "GET")
    assert get_ep.purpose == "List all items"


def test_parse_endpoints_skips_header_row():
    eps = parse_endpoints(SAMPLE_MD)
    assert all(e.method != "Method" for e in eps)


def test_parse_module_doc_name_and_description():
    mod = parse_module_doc(SAMPLE_MD, "todo-api")
    assert mod.name == "todo-api"
    assert "todo list" in mod.description.lower()


def test_load_and_parse_reads_file(tmp_path):
    smrt_dir = tmp_path / ".smrt"
    smrt_dir.mkdir()
    (smrt_dir / "Project.md").write_text(SAMPLE_MD, encoding="utf-8")
    module, endpoints = load_and_parse(tmp_path)
    assert module.name == "todo-api"
    assert len(endpoints) == 3


def test_load_and_parse_missing_returns_empty(tmp_path):
    module, endpoints = load_and_parse(tmp_path)
    assert endpoints == []
    assert module.name == tmp_path.name
