"""Git integration for SMRT fix sessions.

All public functions are best-effort: they log warnings on failure and never
raise, so the core ticket workflow is never blocked by git issues.
"""
import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace

log = logging.getLogger(__name__)

# Identity used for auto-commits so git never prompts for user config.
_GIT_ID = ["-c", "user.email=smrt@local", "-c", "user.name=SMRT Agent"]


def _run(args: list[str], cwd: Path) -> SimpleNamespace:
    """Run a git command. Returns a SimpleNamespace with returncode/stdout/stderr, never raises."""
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        return SimpleNamespace(returncode=r.returncode, stdout=r.stdout, stderr=r.stderr)
    except FileNotFoundError:
        return SimpleNamespace(returncode=127, stdout="", stderr="git: command not found")
    except Exception as exc:
        log.warning("git command failed: %s", exc)
        return SimpleNamespace(returncode=1, stdout="", stderr=str(exc))


# ── Repo detection / initialisation ───────────────────────────────────────


def is_git_repo(project_path: Path) -> bool:
    return _run(["rev-parse", "--is-inside-work-tree"], project_path).returncode == 0


def ensure_git_repo(project_path: Path) -> None:
    """Initialize a git repo if one doesn't exist, creating an initial baseline commit."""
    if is_git_repo(project_path):
        return

    _run(["init"], project_path)

    # Add .smrt/ to .agentignore so agent tools skip session files,
    # without touching .gitignore (the user controls what git tracks).
    agentignore = project_path / ".agentignore"
    existing = agentignore.read_text(encoding="utf-8") if agentignore.exists() else ""
    if ".smrt" not in existing:
        sep = "" if (not existing or existing.endswith("\n")) else "\n"
        with agentignore.open("a", encoding="utf-8") as f:
            f.write(f"{sep}.smrt/\n")

    _run(["add", "-A"], project_path)
    r = _run(_GIT_ID + ["commit", "-m", "smrt: initial baseline commit"], project_path)
    if r.returncode != 0:
        log.warning("Initial baseline commit failed: %s", r.stderr)


# ── Branch helpers ─────────────────────────────────────────────────────────


def current_branch(project_path: Path) -> str:
    """Return the current branch name, or 'main' if detached or unavailable."""
    r = _run(["rev-parse", "--abbrev-ref", "HEAD"], project_path)
    name = r.stdout.strip()
    return name if (name and name != "HEAD") else "main"


def _fix_branch_name(ticket_id: str) -> str:
    return f"smrt/fix-{ticket_id}"


def create_fix_branch(project_path: Path, ticket_id: str) -> str:
    """Create and switch to smrt/fix-{ticket_id}.

    Deletes any stale branch with the same name (leftover from a prior cancelled
    session) before creating a fresh one. Returns the branch name.
    """
    branch = _fix_branch_name(ticket_id)
    _run(["branch", "-D", branch], project_path)  # delete stale; failure is fine
    r = _run(["checkout", "-b", branch], project_path)
    if r.returncode != 0:
        log.warning("Failed to create fix branch %s: %s", branch, r.stderr)
    return branch


def discard_fix_branch(project_path: Path, base_branch: str, ticket_id: str) -> None:
    """Discard all uncommitted changes and switch back to base_branch.

    Restores tracked files, removes untracked files (preserves .smrt/), then
    force-checks out the base branch and deletes the fix branch.
    """
    fix_branch = _fix_branch_name(ticket_id)
    _run(["checkout", "--", "."], project_path)        # revert tracked files
    _run(["clean", "-fd", "-e", ".smrt"], project_path)  # remove untracked (keep .smrt/)
    r = _run(["checkout", "-f", base_branch], project_path)
    if r.returncode != 0:
        log.warning("Could not checkout %s: %s", base_branch, r.stderr)
    _run(["branch", "-D", fix_branch], project_path)


def commit_and_merge_fix(project_path: Path, base_branch: str, ticket_id: str) -> None:
    """Stage, commit, and merge the fix into base_branch, then delete the fix branch.

    Called on PR accept so the fix lands on the user's working branch.
    No-op if there's nothing to commit (fix already committed or empty change).
    """
    fix_branch = _fix_branch_name(ticket_id)
    _run(["add", "-A"], project_path)
    _run(_GIT_ID + ["commit", "-m", f"smrt: fix {ticket_id}"], project_path)
    r = _run(["checkout", base_branch], project_path)
    if r.returncode != 0:
        log.warning("Could not checkout %s for merge: %s", base_branch, r.stderr)
        return
    _run(
        _GIT_ID + ["merge", "--no-ff", fix_branch, "-m", f"smrt: merge fix for {ticket_id}"],
        project_path,
    )
    _run(["branch", "-d", fix_branch], project_path)


# ── Per-ticket state storage ───────────────────────────────────────────────


def save_base_branch(project_path: Path, ticket_id: str, branch: str) -> None:
    """Persist the base branch name for a ticket's fix session."""
    state_dir = project_path / ".smrt" / "git"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / f"{ticket_id}.branch").write_text(branch, encoding="utf-8")


def load_base_branch(project_path: Path, ticket_id: str) -> str:
    """Read the saved base branch for a ticket, defaulting to 'main'."""
    p = project_path / ".smrt" / "git" / f"{ticket_id}.branch"
    if p.exists():
        v = p.read_text(encoding="utf-8").strip()
        return v if v else "main"
    return "main"


def clear_base_branch(project_path: Path, ticket_id: str) -> None:
    """Remove the saved base branch state file."""
    p = project_path / ".smrt" / "git" / f"{ticket_id}.branch"
    p.unlink(missing_ok=True)
