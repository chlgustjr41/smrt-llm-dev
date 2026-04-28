import asyncio
import inspect

import pytest

from smrt_agent.docs.backends import DocBackend, EndpointDoc, ModuleDoc, DecisionDoc


def test_endpoint_doc_fields():
    ep = EndpointDoc(method="GET", path="/items", auth_required=False, purpose="List items")
    assert ep.method == "GET"
    assert ep.path == "/items"
    assert ep.auth_required is False
    assert ep.purpose == "List items"
    assert ep.tags == []


def test_module_doc_fields():
    mod = ModuleDoc(name="services.auth", description="Handles authentication", file_path="src/auth.py")
    assert mod.name == "services.auth"
    assert mod.tags == []


def test_decision_doc_fields():
    dec = DecisionDoc(
        slug="2026-04-24-chose-jwt",
        title="Use JWT",
        context="Need stateless auth",
        decision="Use JWT tokens",
        consequences="Tokens cannot be revoked without blocklist",
    )
    assert dec.slug == "2026-04-24-chose-jwt"
    assert dec.tags == []


def test_doc_backend_is_abstract():
    assert inspect.isabstract(DocBackend)


def test_github_backend_writes_module_doc(tmp_path):
    from smrt_agent.docs.backends import GitHubBackend
    backend = GitHubBackend(tmp_path)
    mod = ModuleDoc(name="services.auth", description="Auth service", file_path="src/auth.py", tags=["auth"])
    asyncio.run(backend.upsert_module_doc(mod))
    out = (tmp_path / "docs" / "modules" / "services.auth.md").read_text()
    assert "# services.auth" in out
    assert "Auth service" in out
    assert "src/auth.py" in out


def test_github_backend_writes_endpoint_doc(tmp_path):
    from smrt_agent.docs.backends import GitHubBackend
    backend = GitHubBackend(tmp_path)
    ep = EndpointDoc(method="GET", path="/items", auth_required=False, purpose="List items")
    asyncio.run(backend.upsert_endpoint_doc(ep))
    out = (tmp_path / "docs" / "api" / "GET_items.md").read_text()
    assert "# GET /items" in out
    assert "List items" in out
    assert "None" in out  # auth = None (not required)


def test_github_backend_api_index_lists_all_endpoints(tmp_path):
    from smrt_agent.docs.backends import GitHubBackend
    backend = GitHubBackend(tmp_path)
    asyncio.run(backend.upsert_endpoint_doc(EndpointDoc(method="POST", path="/items", auth_required=True, purpose="Create")))
    asyncio.run(backend.upsert_endpoint_doc(EndpointDoc(method="GET", path="/items", auth_required=False, purpose="List")))
    index = (tmp_path / "docs" / "api" / "index.md").read_text()
    assert "GET_items.md" in index
    assert "POST_items.md" in index


def test_github_backend_writes_decision_doc(tmp_path):
    from smrt_agent.docs.backends import GitHubBackend
    backend = GitHubBackend(tmp_path)
    dec = DecisionDoc(
        slug="2026-04-24-chose-jwt",
        title="Use JWT",
        context="Need stateless auth",
        decision="JWT tokens",
        consequences="Tokens persist until expiry",
    )
    asyncio.run(backend.upsert_decision(dec))
    out = (tmp_path / "docs" / "decisions" / "2026-04-24-chose-jwt.md").read_text()
    assert "# Use JWT" in out
    assert "JWT tokens" in out


def test_obsidian_backend_writes_module_doc(tmp_path):
    from smrt_agent.docs.backends import ObsidianBackend
    backend = ObsidianBackend(tmp_path)
    mod = ModuleDoc(name="services.auth", description="Auth service", file_path="src/auth.py", tags=["auth"])
    asyncio.run(backend.upsert_module_doc(mod))
    # dots in name become __ in slug
    out = (tmp_path / "docs" / "modules" / "services__auth.md").read_text()
    assert "type: module" in out
    assert "# services.auth" in out
    assert "Auth service" in out


def test_obsidian_backend_writes_endpoint_doc(tmp_path):
    from smrt_agent.docs.backends import ObsidianBackend
    backend = ObsidianBackend(tmp_path)
    ep = EndpointDoc(method="GET", path="/items", auth_required=True, purpose="List items")
    asyncio.run(backend.upsert_endpoint_doc(ep))
    out = (tmp_path / "docs" / "api" / "GET_items.md").read_text()
    assert "type: endpoint" in out
    assert "# GET /items" in out
    assert "Required" in out


def test_obsidian_backend_frontmatter_has_updated_field(tmp_path):
    from smrt_agent.docs.backends import ObsidianBackend
    import re
    backend = ObsidianBackend(tmp_path)
    asyncio.run(backend.upsert_module_doc(ModuleDoc(name="m", description="d", file_path="f")))
    out = (tmp_path / "docs" / "modules" / "m.md").read_text()
    assert re.search(r"updated: \d{4}-\d{2}-\d{2}", out)


def test_obsidian_backend_writes_decision_doc(tmp_path):
    from smrt_agent.docs.backends import ObsidianBackend
    backend = ObsidianBackend(tmp_path)
    dec = DecisionDoc(
        slug="2026-04-24-chose-jwt",
        title="Use JWT",
        context="Need stateless auth",
        decision="JWT tokens",
        consequences="Tokens persist until expiry",
    )
    asyncio.run(backend.upsert_decision(dec))
    out = (tmp_path / "docs" / "decisions" / "2026-04-24-chose-jwt.md").read_text()
    assert "type: decision" in out
    assert "# Use JWT" in out


def test_jira_backend_raises_not_implemented():
    from smrt_agent.docs.backends import JiraBackend
    backend = JiraBackend()
    with pytest.raises(NotImplementedError, match="v2"):
        asyncio.run(backend.upsert_module_doc(ModuleDoc(name="x", description="x", file_path="x")))


def test_confluence_backend_raises_not_implemented():
    from smrt_agent.docs.backends import ConfluenceBackend
    backend = ConfluenceBackend()
    with pytest.raises(NotImplementedError, match="v2"):
        asyncio.run(backend.upsert_endpoint_doc(EndpointDoc(method="GET", path="/", auth_required=False, purpose="x")))
