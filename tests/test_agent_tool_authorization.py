from app.agents.tools import _get_user_context
from app.common.identity import Principal
from app.common.permissions import ACTION_ANALYZE


def test_agent_tool_context_contains_principal_permissions():
    context = _get_user_context({"username": "alice", "role": "manager", "department": "finance"})
    assert context["username"] == "alice"
    assert ACTION_ANALYZE in context["permissions"]


def test_staff_tool_context_does_not_include_admin_actions():
    context = _get_user_context({"username": "alice", "role": "staff", "department": "finance"})
    assert "admin:users" not in context["permissions"]


def test_agent_tools_reject_missing_identity_without_admin_fallback():
    from app.agents.tools import search_docs

    result = search_docs.invoke("制度查询")

    assert "authorization_required" in result
    assert "admin" not in result.lower()


def test_search_docs_uses_principal_aware_retrieval_pipeline(monkeypatch):
    from app.agents import tools

    class Pipeline:
        def __init__(self):
            self.query = None
            self.principal = None

        def search_for_principal(self, query, principal, top_k):
            self.query = query
            self.principal = principal
            assert top_k == 5
            return (
                [
                    {
                        "source": "travel-policy.md",
                        "content": "Travel reimbursement requires manager approval.",
                        "_score": 0.9,
                    }
                ],
                [],
            )

    pipeline = Pipeline()
    monkeypatch.setattr(tools, "_get_pipeline", lambda: pipeline)

    result = tools.search_docs.invoke(
        {"query": "travel reimbursement policy"},
        config={
            "configurable": {
                "username": "alice",
                "role": "staff",
                "department": "finance",
            }
        },
    )

    assert "travel-policy.md" in result
    assert pipeline.query == "travel reimbursement policy"
    assert pipeline.principal.username == "alice"
    assert pipeline.principal.department == "finance"
