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

class TestGitignoreCheck:
    def test_gitignored_file_blocked(self, tmp_path):
        """A file matching .gitignore patterns should be blocked."""
        (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
        result = check_path(tmp_path, "app.log")
        assert result is not None, "app.log should be blocked because *.log is gitignored"

    def test_non_gitignored_file_allowed(self, tmp_path):
        """A file NOT matching .gitignore patterns should be allowed."""
        (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
        result = check_path(tmp_path, "app.py")
        assert result is None, "app.py should not be blocked"

    def test_tests_generated_exception(self, tmp_path):
        """Paths under tests/generated/ are always allowed even if tests/ is gitignored."""
        (tmp_path / ".gitignore").write_text("tests/\n*.py\n", encoding="utf-8")
        # Even though tests/ is gitignored, tests/generated/ is excepted
        result = check_path(tmp_path, "tests/generated/test_foo.py")
        assert result is None, "tests/generated/test_foo.py should NOT be blocked"

    def test_no_gitignore_file_allowed(self, tmp_path):
        """Without a .gitignore, all non-secret files are allowed."""
        result = check_path(tmp_path, "some/arbitrary/file.txt")
        assert result is None

    def test_nested_gitignore_respected(self, tmp_path):
        """A .gitignore in a subdirectory is respected for files under that dir."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / ".gitignore").write_text("*.secret\n", encoding="utf-8")
        result = check_path(tmp_path, "subdir/data.secret")
        assert result is not None, "subdir/data.secret should be blocked by subdir/.gitignore"

    def test_nested_gitignore_does_not_affect_parent(self, tmp_path):
        """A .gitignore in a subdirectory does NOT block files in other directories."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / ".gitignore").write_text("*.secret\n", encoding="utf-8")
        result = check_path(tmp_path, "otherdir/data.secret")
        assert result is None, "otherdir/data.secret should NOT be blocked by subdir/.gitignore"
