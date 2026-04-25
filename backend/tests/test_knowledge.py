import json
from pathlib import Path
import pytest
from smrt_agent.knowledge import compute_doc_score, record_doc_score, record_provenance


def test_compute_doc_score_empty_project(tmp_path):
    score = compute_doc_score(tmp_path)
    assert score["score"] == 0.0
    assert score["ep_documented"] == 0
    assert score["ep_total"] == 0
    assert score["mod_documented"] == 0
    assert score["mod_total"] == 1


def test_compute_doc_score_with_endpoint_docs(tmp_path):
    api_dir = tmp_path / "docs" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "GET_items.md").write_text("# GET /items", encoding="utf-8")
    (api_dir / "POST_items.md").write_text("# POST /items", encoding="utf-8")
    (api_dir / "index.md").write_text("# API Index", encoding="utf-8")

    score = compute_doc_score(tmp_path)
    assert score["ep_documented"] == 2
    # index.md excluded


def test_compute_doc_score_with_module_docs(tmp_path):
    mod_dir = tmp_path / "docs" / "modules"
    mod_dir.mkdir(parents=True)
    (mod_dir / "todo-api.md").write_text("# Module", encoding="utf-8")

    score = compute_doc_score(tmp_path)
    assert score["mod_documented"] == 1
    # mod_total is always 1; score contribution = 50
    assert score["score"] >= 50.0


def test_compute_doc_score_max_100(tmp_path):
    api_dir = tmp_path / "docs" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "GET_items.md").write_text("# GET /items", encoding="utf-8")
    mod_dir = tmp_path / "docs" / "modules"
    mod_dir.mkdir(parents=True)
    (mod_dir / "todo-api.md").write_text("# Module", encoding="utf-8")

    score = compute_doc_score(tmp_path)
    assert score["score"] <= 100.0


def test_record_doc_score_creates_file(tmp_path):
    entry = {"ts": "2026-04-25T00:00:00Z", "score": 75.0, "ep_documented": 3, "ep_total": 4, "mod_documented": 1, "mod_total": 1}
    record_doc_score(tmp_path, entry)

    path = tmp_path / ".smrt" / "doc_scores.jsonl"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8").strip())
    assert data["score"] == 75.0


def test_record_doc_score_appends(tmp_path):
    record_doc_score(tmp_path, {"ts": "2026-04-25T00:00:00Z", "score": 50.0})
    record_doc_score(tmp_path, {"ts": "2026-04-25T01:00:00Z", "score": 75.0})

    path = tmp_path / ".smrt" / "doc_scores.jsonl"
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[1])["score"] == 75.0


def test_record_provenance_creates_file(tmp_path):
    entry = {
        "ticket": "BUG-001",
        "subagent": "coder_agent",
        "reasoning": "Fixed null pointer dereference in handler",
        "sources_consulted": ["src/main.py", "src/handlers.py"],
        "attempts": 2,
        "related_lessons_applied": [],
    }
    record_provenance(tmp_path, entry)

    path = tmp_path / ".smrt" / "provenance.jsonl"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8").strip())
    assert data["ticket"] == "BUG-001"
    assert data["attempts"] == 2


def test_record_provenance_appends(tmp_path):
    record_provenance(tmp_path, {"ticket": "BUG-001", "subagent": "coder_agent", "reasoning": "r1", "sources_consulted": [], "attempts": 1, "related_lessons_applied": []})
    record_provenance(tmp_path, {"ticket": "BUG-002", "subagent": "coder_agent", "reasoning": "r2", "sources_consulted": [], "attempts": 1, "related_lessons_applied": []})

    path = tmp_path / ".smrt" / "provenance.jsonl"
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[1])["ticket"] == "BUG-002"
