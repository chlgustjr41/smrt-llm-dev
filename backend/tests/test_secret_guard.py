"""Tests for smrt_agent.hooks.secret_guard."""
import pytest
from pathlib import Path

from smrt_agent.hooks.secret_guard import check_path, is_blocked


# ---------------------------------------------------------------------------
# Always-deny: blocked paths
# ---------------------------------------------------------------------------

class TestAlwaysDenyBlocked:
    def test_dotenv_blocked(self, tmp_path):
        assert check_path(tmp_path, ".env") is not None

    def test_dotenv_local_blocked(self, tmp_path):
        assert check_path(tmp_path, ".env.local") is not None

    def test_dotenv_underscore_blocked(self, tmp_path):
        assert check_path(tmp_path, ".env_production") is not None

    def test_git_config_blocked(self, tmp_path):
        assert check_path(tmp_path, ".git/config") is not None

    def test_git_subdir_blocked(self, tmp_path):
        assert check_path(tmp_path, ".git/objects/abc123") is not None

    def test_private_key_blocked(self, tmp_path):
        assert check_path(tmp_path, "private.key") is not None

    def test_pem_blocked(self, tmp_path):
        assert check_path(tmp_path, "server.pem") is not None

    def test_p12_blocked(self, tmp_path):
        assert check_path(tmp_path, "cert.p12") is not None

    def test_pfx_blocked(self, tmp_path):
        assert check_path(tmp_path, "cert.pfx") is not None

    def test_crt_blocked(self, tmp_path):
        assert check_path(tmp_path, "server.crt") is not None

    def test_id_rsa_blocked(self, tmp_path):
        assert check_path(tmp_path, "id_rsa") is not None

    def test_id_ed25519_blocked(self, tmp_path):
        assert check_path(tmp_path, "id_ed25519") is not None

    def test_id_ecdsa_blocked(self, tmp_path):
        assert check_path(tmp_path, "id_ecdsa") is not None

    def test_ppk_blocked(self, tmp_path):
        assert check_path(tmp_path, "mykey.ppk") is not None

    def test_credentials_json_blocked(self, tmp_path):
        assert check_path(tmp_path, "credentials.json") is not None

    def test_service_account_json_blocked(self, tmp_path):
        assert check_path(tmp_path, "service-account-prod.json") is not None

    def test_gcloud_key_json_blocked(self, tmp_path):
        assert check_path(tmp_path, "gcloud-key-main.json") is not None

    def test_secrets_yaml_blocked(self, tmp_path):
        assert check_path(tmp_path, "secrets.yaml") is not None

    def test_secrets_yml_blocked(self, tmp_path):
        assert check_path(tmp_path, "secrets.yml") is not None

    def test_secret_yml_blocked(self, tmp_path):
        assert check_path(tmp_path, "secret.yml") is not None

    def test_secret_yaml_blocked(self, tmp_path):
        assert check_path(tmp_path, "secret.yaml") is not None

    def test_aws_dir_blocked(self, tmp_path):
        assert check_path(tmp_path, ".aws/credentials") is not None

    def test_azure_dir_blocked(self, tmp_path):
        assert check_path(tmp_path, ".azure/something") is not None

    def test_gcloud_dir_blocked(self, tmp_path):
        assert check_path(tmp_path, ".gcloud/application_default_credentials.json") is not None

    def test_kube_config_blocked(self, tmp_path):
        assert check_path(tmp_path, ".kube/config") is not None

    def test_netrc_blocked(self, tmp_path):
        assert check_path(tmp_path, ".netrc") is not None

    def test_npmrc_blocked(self, tmp_path):
        assert check_path(tmp_path, ".npmrc") is not None

    def test_pypirc_blocked(self, tmp_path):
        assert check_path(tmp_path, ".pypirc") is not None


# ---------------------------------------------------------------------------
# Always-deny: allowed paths
# ---------------------------------------------------------------------------

class TestAlwaysDenyAllowed:
    def test_normal_config_yaml_allowed(self, tmp_path):
        assert check_path(tmp_path, "config.yaml") is None

    def test_src_main_py_allowed(self, tmp_path):
        assert check_path(tmp_path, "src/main.py") is None

    def test_readme_md_allowed(self, tmp_path):
        assert check_path(tmp_path, "README.md") is None

    def test_py_file_not_blocked_by_crt_rule(self, tmp_path):
        # .py files must NOT be blocked (*.crt should not catch *.py)
        assert check_path(tmp_path, "main.py") is None

    def test_nested_py_allowed(self, tmp_path):
        assert check_path(tmp_path, "src/utils/helpers.py") is None


# ---------------------------------------------------------------------------
# is_blocked convenience wrapper
# ---------------------------------------------------------------------------

class TestIsBlocked:
    def test_returns_true_and_reason_for_blocked(self, tmp_path):
        blocked, reason = is_blocked(tmp_path, ".env")
        assert blocked is True
        assert reason != ""

    def test_returns_false_and_empty_for_allowed(self, tmp_path):
        blocked, reason = is_blocked(tmp_path, "src/main.py")
        assert blocked is False
        assert reason == ""


# ---------------------------------------------------------------------------
# Gitignore integration
# ---------------------------------------------------------------------------

class TestAgentignoreCheck:
    def test_agentignored_file_blocked(self, tmp_path):
        """A file matching .agentignore patterns should be blocked."""
        (tmp_path / ".agentignore").write_text("*.log\n", encoding="utf-8")
        result = check_path(tmp_path, "app.log")
        assert result is not None, "app.log should be blocked because *.log is in .agentignore"

    def test_non_agentignored_file_allowed(self, tmp_path):
        """A file NOT matching .agentignore patterns should be allowed."""
        (tmp_path / ".agentignore").write_text("*.log\n", encoding="utf-8")
        result = check_path(tmp_path, "app.py")
        assert result is None, "app.py should not be blocked"

    def test_gitignore_does_not_block(self, tmp_path):
        """.gitignore entries no longer block agent access — only .agentignore does."""
        (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
        result = check_path(tmp_path, "app.log")
        assert result is None, "app.log should NOT be blocked by .gitignore — only .agentignore matters"

    def test_smrt_dir_accessible(self, tmp_path):
        """.smrt/ directory is accessible even when listed in .gitignore."""
        (tmp_path / ".gitignore").write_text(".smrt/\n.smrt/runs/\n", encoding="utf-8")
        result = check_path(tmp_path, ".smrt/state.db")
        assert result is None, ".smrt/ should NOT be blocked — gitignore no longer gates agent access"

    def test_no_agentignore_file_allowed(self, tmp_path):
        """Without a .agentignore, all non-secret files are allowed."""
        result = check_path(tmp_path, "some/arbitrary/file.txt")
        assert result is None

    def test_nested_agentignore_respected(self, tmp_path):
        """A .agentignore in a subdirectory is respected for files under that dir."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / ".agentignore").write_text("*.secret\n", encoding="utf-8")
        result = check_path(tmp_path, "subdir/data.secret")
        assert result is not None, "subdir/data.secret should be blocked by subdir/.agentignore"

    def test_nested_agentignore_does_not_affect_parent(self, tmp_path):
        """A .agentignore in a subdirectory does NOT block files in other directories."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / ".agentignore").write_text("*.secret\n", encoding="utf-8")
        result = check_path(tmp_path, "otherdir/data.secret")
        assert result is None, "otherdir/data.secret should NOT be blocked by subdir/.agentignore"


class TestReviewerAgentignoreSpec:
    """Verify that reviewer list_files honours nested .agentignore files."""

    def test_root_agentignore_hides_file_from_listing(self, tmp_path):
        from smrt_agent.agents.reviewer.tools import list_files
        (tmp_path / ".agentignore").write_text("BUGS.md\n", encoding="utf-8")
        (tmp_path / "BUGS.md").write_text("secret", encoding="utf-8")
        (tmp_path / "main.py").write_text("pass", encoding="utf-8")
        files = list_files(tmp_path)
        assert "BUGS.md" not in files
        assert "main.py" in files

    def test_nested_agentignore_hides_file_from_listing(self, tmp_path):
        """A .agentignore in a subdir hides files relative to that subdir."""
        from smrt_agent.agents.reviewer.tools import list_files
        subdir = tmp_path / "eval"
        subdir.mkdir()
        (subdir / ".agentignore").write_text("BUGS.md\n", encoding="utf-8")
        (subdir / "BUGS.md").write_text("secret", encoding="utf-8")
        (subdir / "main.py").write_text("pass", encoding="utf-8")
        files = list_files(tmp_path)
        assert "eval/BUGS.md" not in files
        assert "eval/main.py" in files

    def test_nested_agentignore_does_not_hide_sibling_dirs(self, tmp_path):
        """A nested .agentignore does NOT hide matching names in sibling directories."""
        from smrt_agent.agents.reviewer.tools import list_files
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir(); b.mkdir()
        # Use a name that doesn't match _SECRET_SPEC so only agentignore gates it.
        (a / ".agentignore").write_text("notes.txt\n", encoding="utf-8")
        (a / "notes.txt").write_text("hidden", encoding="utf-8")
        (b / "notes.txt").write_text("visible", encoding="utf-8")
        files = list_files(tmp_path)
        assert "a/notes.txt" not in files
        assert "b/notes.txt" in files
