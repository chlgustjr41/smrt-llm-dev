import pytest
import asyncio
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
    import inspect
    assert inspect.isabstract(DocBackend)
