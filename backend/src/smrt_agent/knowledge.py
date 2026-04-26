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
    except Exception:
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


def append_lesson(project_path: Path, ticket_id: str, action: str, entry_text: str) -> None:
    """Append a lesson entry to ## Lessons section of .smrt/Project.md.

    Creates the file and section if either doesn't exist.
    """
    project_md_path = project_path / ".smrt" / "Project.md"
    project_md_path.parent.mkdir(parents=True, exist_ok=True)

    if project_md_path.exists():
        text = project_md_path.read_text(encoding="utf-8")
    else:
        text = f"# Project: {project_path.name}\n"

    lesson_line = f"- **{ticket_id} ({action})**: {entry_text}"

    if "## Lessons" in text:
        lines = text.splitlines()
        out: list[str] = []
        in_lessons = False
        inserted = False
        for line in lines:
            if line.startswith("## Lessons"):
                in_lessons = True
                out.append(line)
                continue
            if in_lessons and line.startswith("## ") and not inserted:
                out.append(lesson_line)
                inserted = True
                in_lessons = False
            out.append(line)
        if not inserted:
            out.append(lesson_line)
        text = "\n".join(out) + "\n"
    else:
        text = text.rstrip() + f"\n\n## Lessons\n\n{lesson_line}\n"

    project_md_path.write_text(text, encoding="utf-8")


def sync_wiki_log(project_path: Path, ticket_id: str, ticket_title: str, action: str) -> None:
    """Append a log entry to wiki/log.md on PR accept/reject. Silent no-op if wiki/ absent."""
    from datetime import datetime, timezone
    wiki_log = project_path / "wiki" / "log.md"
    if not wiki_log.parent.exists():
        return
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"- `{ts}` **{ticket_id} ({action})**: {ticket_title}\n"
    with wiki_log.open("a", encoding="utf-8") as f:
        f.write(entry)


def append_rejection(project_path: Path, ticket_id: str, ticket_title: str, reason: str) -> None:
    """Append a rejection record to .smrt/rejections.jsonl."""
    from datetime import datetime, timezone
    smrt_dir = project_path / ".smrt"
    smrt_dir.mkdir(exist_ok=True)
    entry = {
        "ticket_id": ticket_id,
        "ticket_title": ticket_title,
        "reason": reason,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(smrt_dir / "rejections.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
