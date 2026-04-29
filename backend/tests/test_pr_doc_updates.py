"""Unit tests for the doc-update applier in api/pr.py.

The Reviewer's final summary pass queues `proposed_doc_updates` into the
persisted Fix Summary. When the user accepts a Needs Review ticket, the
applier reads those proposals and writes them to disk via the existing
Reviewer tools (write_readme / write_docs_file / write_file).

This test isolates the applier from the full HTTP flow so the policy is
verified end-to-end at the file-system level."""
from pathlib import Path

from smrt_agent.api.pr import _apply_proposed_doc_updates
from smrt_agent.fix_summary import save_fix_summary


def _save_summary_with_updates(project_path: Path, ticket_id: str, updates: list[dict]) -> None:
    """Stage a Fix Summary that the applier can read."""
    summary = {
        "ticket_id": ticket_id,
        "session_id": "sess-test",
        "final_status": "done",
        "pr_ready": True,
        "recommendation": None,
        "analysis": None,
        "qa_early_exit": None,
        "qa_final_summary": None,
        "reviewer_final_summary": "test summary",
        "proposed_doc_updates": updates,
        "recheck_output": "1 passed",
        "changes": [],
        "completed_at": "2026-04-28T12:00:00Z",
    }
    save_fix_summary(project_path, summary)


def test_apply_proposed_doc_updates_writes_readme(tmp_path):
    _save_summary_with_updates(tmp_path, "T-1", [
        {"path": "README.md", "reason": "freshen overview", "new_content": "# Project\n\nNew overview."},
    ])
    report = _apply_proposed_doc_updates(tmp_path, "T-1")
    assert (tmp_path / "README.md").read_text(encoding="utf-8").startswith("# Project")
    assert report["applied"] == [{"path": "README.md"}]
    assert report["skipped"] == []
    assert report["errors"] == []


def test_apply_proposed_doc_updates_writes_docs_file(tmp_path):
    _save_summary_with_updates(tmp_path, "T-2", [
        {
            "path": "docs/architecture.md",
            "reason": "document the new flow",
            "new_content": "# Architecture\n\nThe new layered flow.",
        },
    ])
    report = _apply_proposed_doc_updates(tmp_path, "T-2")
    assert (tmp_path / "docs" / "architecture.md").read_text(encoding="utf-8").startswith("# Architecture")
    assert report["applied"] == [{"path": "docs/architecture.md"}]


def test_apply_proposed_doc_updates_writes_project_md(tmp_path):
    _save_summary_with_updates(tmp_path, "T-3", [
        {
            "path": ".smrt/Project.md",
            "reason": "refresh invariants",
            "new_content": "# Project\n\nRefreshed.",
        },
    ])
    report = _apply_proposed_doc_updates(tmp_path, "T-3")
    assert (tmp_path / ".smrt" / "Project.md").read_text(encoding="utf-8").startswith("# Project")
    assert report["applied"] == [{"path": ".smrt/Project.md"}]


def test_apply_proposed_doc_updates_skips_disallowed_paths(tmp_path):
    """The Reviewer should never propose paths outside the doc allow-list,
    but if it does, the applier must skip them (not crash, not write)."""
    _save_summary_with_updates(tmp_path, "T-4", [
        {"path": "src/main.py", "reason": "sneaky", "new_content": "# malicious"},
        {"path": "/etc/passwd", "reason": "very sneaky", "new_content": "root::"},
        {"path": "docs/legit.md", "reason": "valid", "new_content": "# OK"},
    ])
    report = _apply_proposed_doc_updates(tmp_path, "T-4")
    # Only the legit doc was applied.
    assert report["applied"] == [{"path": "docs/legit.md"}]
    assert (tmp_path / "docs" / "legit.md").exists()
    # The two illegal paths were skipped explicitly.
    skipped_paths = [s["path"] for s in report["skipped"]]
    assert "src/main.py" in skipped_paths
    assert "/etc/passwd" in skipped_paths
    # And no files appeared at the illegal locations.
    assert not (tmp_path / "src" / "main.py").exists()


def test_apply_proposed_doc_updates_returns_empty_when_no_summary(tmp_path):
    """Tickets with no persisted summary (e.g. legacy or never-fixed) should
    produce an empty report rather than crashing the Accept handler."""
    report = _apply_proposed_doc_updates(tmp_path, "T-ghost")
    assert report == {"applied": [], "skipped": [], "errors": []}


def test_apply_proposed_doc_updates_handles_empty_updates_list(tmp_path):
    """Reviewer correctly emitted an empty updates list — no work to do,
    no error to surface."""
    _save_summary_with_updates(tmp_path, "T-5", [])
    report = _apply_proposed_doc_updates(tmp_path, "T-5")
    assert report == {"applied": [], "skipped": [], "errors": []}
