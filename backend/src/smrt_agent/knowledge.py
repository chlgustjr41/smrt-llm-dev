import json
from pathlib import Path

from smrt_agent.docs.parser import load_and_parse


def compute_doc_score(project_path: Path) -> dict:
    """Compute documentation completeness score 0–100.

    Score = (ep_documented / max(ep_total, 1)) * 50
           + (mod_documented / max(mod_total, 1)) * 50
    """
    try:
        _, endpoints = load_and_parse(project_path)
        ep_total = len(endpoints)
    except (FileNotFoundError, ValueError):
        ep_total = 0

    mod_total = 1  # one primary module doc per project

    api_dir = project_path / "docs" / "api"
    ep_documented = (
        len([f for f in api_dir.glob("*.md") if f.name != "index.md"])
        if api_dir.exists()
        else 0
    )

    modules_dir = project_path / "docs" / "modules"
    mod_documented = (
        len(list(modules_dir.glob("*.md"))) if modules_dir.exists() else 0
    )

    ep_score = (ep_documented / max(ep_total, 1)) * 50
    mod_score = (mod_documented / max(mod_total, 1)) * 50
    score = round(min(ep_score + mod_score, 100.0), 1)

    return {
        "ep_documented": ep_documented,
        "ep_total": ep_total,
        "mod_documented": mod_documented,
        "mod_total": mod_total,
        "score": score,
    }


def record_doc_score(project_path: Path, entry: dict) -> None:
    """Append a doc score entry to .smrt/doc_scores.jsonl."""
    smrt_dir = project_path / ".smrt"
    smrt_dir.mkdir(exist_ok=True)
    with open(smrt_dir / "doc_scores.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def record_provenance(project_path: Path, entry: dict) -> None:
    """Append a [smrt-provenance] entry to .smrt/provenance.jsonl."""
    smrt_dir = project_path / ".smrt"
    smrt_dir.mkdir(exist_ok=True)
    with open(smrt_dir / "provenance.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
