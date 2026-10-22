"""The MCP surface must inherit its scope from a registered user, not from env claims."""

import importlib

import pytest

from app.rag.filters import build_document_retrieval_filter


@pytest.fixture(autouse=True)
def _restore_module_env():
    yield
    import app.mcp_server as module

    importlib.reload(module)


def _load(monkeypatch, username: str):
    from app.common import auth

    registered = {
        "svc-mcp": {"id": "7", "username": "svc-mcp", "role": "staff", "department": "sales"}
    }
    monkeypatch.setattr(auth, "get_user", lambda name: registered.get(name))
    monkeypatch.setenv("MCP_USERNAME", username)
    monkeypatch.setenv("MCP_ROLE", "admin")
    monkeypatch.setenv("MCP_DEPARTMENT", "everything")
    from app import mcp_server

    return importlib.reload(mcp_server)


def test_mcp_identity_is_taken_from_the_user_store_not_the_environment(monkeypatch):
    module = _load(monkeypatch, "svc-mcp")

    principal = module._mcp_principal()
    assert principal is not None
    assert principal.username == "svc-mcp"
    assert principal.role == "staff"
    assert principal.clearance == 1
    assert principal.auth_source == "mcp"

    # The env claim MCP_ROLE=admin must not survive into the tool config.
    config = module._mcp_tool_config()
    carried = config["configurable"]["principal"]
    assert carried.user_id == principal.user_id
    assert carried.roles == ["staff"]
    assert carried.clearance == principal.clearance


def test_unregistered_mcp_identity_refuses_before_any_retrieval(monkeypatch):
    from app.agents import tools

    module = _load(monkeypatch, "ghost-caller")

    class _ForbiddenPipeline:
        def search_for_principal(self, *args, **kwargs):
            raise AssertionError("an unregistered caller must not reach the vector store")

    monkeypatch.setattr(tools, "_get_pipeline", lambda: _ForbiddenPipeline())

    assert "拒绝" in module._search_docs_text("残值率是多少")
    assert module._mcp_tool_config() == {"configurable": {}}


def test_missing_username_refuses_retrieval(monkeypatch):
    module = _load(monkeypatch, "")

    assert module._mcp_principal() is None
    assert "拒绝" in module._search_docs_text("残值率是多少")


def test_unscoped_principal_is_reported_instead_of_broadening(monkeypatch):
    from app.agents import tools
    from app.common import auth

    monkeypatch.setattr(
        auth,
        "get_user",
        lambda name: {"id": "8", "username": name, "role": "staff", "department": ""},
    )
    monkeypatch.setenv("MCP_USERNAME", "nodept")
    from app import mcp_server

    module = importlib.reload(mcp_server)

    from app.rag.filters import RetrievalScopeError

    class _ScopeRejectingPipeline:
        def __init__(self):
            self.calls = 0

        def search_for_principal(self, query, principal, top_k=5):
            # Mirrors the real entry point: the scope is built before any recall runs.
            build_document_retrieval_filter(principal)
            self.calls += 1
            return [], []

    pipeline = _ScopeRejectingPipeline()
    monkeypatch.setattr(tools, "_get_pipeline", lambda: pipeline)

    answer = module._search_docs_text("残值率是多少")
    assert "authorization_unavailable" in answer
    assert pipeline.calls == 0
