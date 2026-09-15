"""e2: the retrieval chain admits an administrator through the policy''s own test.

``docs/handoff/2026-09-15-backend-followup-requests.md`` 6.2 settled the ruling and its
six landing requirements. These cases pin all six so the next reader cannot re-narrow or
re-widen the rule by accident: the administrator predicate must come from
``app.common.policy``, only the department clause may disappear, the classification clause
must stay, an override must be auditable as itself, and every refusal that existed before
e2 must still read exactly as it did.
"""

import pytest

from app.common.identity import Principal
from app.common.permissions import ACTION_VIEW, ACTION_MANAGE_USERS
from app.common.policy import is_administrator
from app.common.rbac import ROLE_CLEARANCE, clearance_for
from app.rag import filters as filters_module
from app.rag.filters import (
    RetrievalScopeError,
    build_document_retrieval_filter,
    record_retrieval_scope,
    resolve_document_retrieval_scope,
)


def _principal(**fields) -> Principal:
    base = {"user_id": "u-1", "username": "caller", "permissions": [ACTION_VIEW]}
    return Principal(**{**base, **fields})


def _admin(**fields) -> Principal:
    """An administrator built the way production builds one: through ``Principal.from_user``."""
    user = {"id": "u-9", "username": "owner", "role": "admin"}
    return Principal.from_user({**user, **fields})


# --------------------------------------------------------------- 要求 1：判据同源


def test_the_retrieval_chain_uses_the_policys_administrator_test():
    assert filters_module.is_administrator is is_administrator


def test_an_administrator_by_permission_alone_is_recognised():
    """``users:manage`` without the role name: the policy test, not a string compare."""
    granted = _principal(permissions=[ACTION_VIEW, ACTION_MANAGE_USERS], clearance=1)

    assert resolve_document_retrieval_scope(granted).reason_code == "administrator_scope"


def test_an_administrator_by_role_alone_is_recognised():
    """The role name without the permission list: still the same answer."""
    by_role = _principal(roles=["admin"], permissions=[], clearance=3)

    assert resolve_document_retrieval_scope(by_role).reason_code == "administrator_scope"


def test_a_manager_is_never_promoted_through_the_shared_test():
    manager = _principal(roles=["manager"], department="finance", clearance=2)

    scope = resolve_document_retrieval_scope(manager)

    assert scope.reason_code == "department_scope"
    assert scope.departments == frozenset({"finance"})


def test_the_scope_is_decided_at_call_time_not_by_a_copy_of_the_rule(monkeypatch):
    """Flipping the shared predicate must flip this chain, or a fourth definition exists."""
    monkeypatch.setattr(filters_module, "is_administrator", lambda principal: False)

    with pytest.raises(RetrievalScopeError) as exc:
        resolve_document_retrieval_scope(_admin())

    assert exc.value.code == "authorization_unavailable"


# ------------------------------------------------------------- 要求 2：只放开部门


def test_an_administrator_without_a_department_retrieves_without_a_department_clause():
    admin = _admin()

    scope = resolve_document_retrieval_scope(admin)

    assert scope.filters == {"classification": {"$in": [1, 2, 3]}}
    assert "department" not in str(scope.filters)
    assert scope.departments is None
    assert build_document_retrieval_filter(admin) == scope.filters


def test_an_administrator_with_a_department_gets_exactly_the_scopeless_filter():
    """A department an administrator happens to have is dropped, never narrowed to."""
    owner = _admin()
    placed = _admin(department="finance", department_ids=["shared-services"])

    assert resolve_document_retrieval_scope(placed).filters == (
        resolve_document_retrieval_scope(owner).filters
    )
    assert resolve_document_retrieval_scope(placed).departments is None


def test_the_classification_clause_survives_for_an_administrator():
    levels = resolve_document_retrieval_scope(_admin()).filters["classification"]["$in"]

    assert levels == [1, 2, 3]


def test_the_local_recheck_matches_the_pushed_down_filter():
    """A recalled chunk is judged by the same scope, including one from another department."""
    admin_scope = resolve_document_retrieval_scope(_admin())
    staff_scope = resolve_document_retrieval_scope(
        _principal(department="finance", clearance=2)
    )

    assert admin_scope.allows({"classification": 3, "department": "hr"}) is True
    assert admin_scope.allows({"classification": 4, "department": "hr"}) is False
    assert admin_scope.allows({"department": "hr"}) is False
    assert staff_scope.allows({"classification": 2, "department": "hr"}) is False
    assert staff_scope.allows({"classification": 2, "department": "finance"}) is True


# ------------------------------------------------------ 要求 3：docstring 写死的事实


def test_the_ceiling_that_is_kept_is_the_one_an_administrator_already_holds():
    """The kept clause restricts nothing today: that is a fact about the mapping, not the rule."""
    admin = _admin()
    levels = set(resolve_document_retrieval_scope(admin).filters["classification"]["$in"])

    assert admin.clearance == clearance_for("admin") == ROLE_CLEARANCE["admin"] == 3
    assert levels == set(range(1, ROLE_CLEARANCE["admin"] + 1))


def test_the_docstring_carries_the_fact_so_nobody_re_derives_it():
    doc = resolve_document_retrieval_scope.__doc__ or ""

    for keyword in ("clearance_for", 'ROLE_CLEARANCE["admin"]', "cross-department"):
        assert keyword in doc


# -------------------------------------------- 要求 4：管理员路径独立可追溯


def _audit_capture(monkeypatch):
    calls: list[tuple] = []

    def capture(*args, **kwargs):
        calls.append((args, kwargs))
        return {}

    monkeypatch.setattr(filters_module, "record_audit", capture)
    return calls


def test_an_administrator_scope_is_audited_under_its_own_reason(monkeypatch):
    calls = _audit_capture(monkeypatch)
    admin = _admin()

    scope = resolve_document_retrieval_scope(admin)
    record_retrieval_scope(admin, scope, hit_count=7, request_id="req-1")

    assert len(calls) == 1
    (args, kwargs) = calls[0]
    assert args[1:5] == (ACTION_VIEW, "allowed", "document_retrieval", "administrator_scope")
    assert kwargs["request_id"] == "req-1"
    assert kwargs["after_summary"] == {"hit_count": 7}


def test_a_department_hit_is_never_recorded_as_an_override(monkeypatch):
    calls = _audit_capture(monkeypatch)
    staff = _principal(department="finance", clearance=2)

    record_retrieval_scope(staff, resolve_document_retrieval_scope(staff), hit_count=3)

    assert calls == []


def test_the_reason_code_distinguishes_the_two_grants():
    assert resolve_document_retrieval_scope(_admin()).reason_code == "administrator_scope"
    assert (
        resolve_document_retrieval_scope(_principal(department="finance")).reason_code
        == "department_scope"
    )


# ---------------------------- 要求 5：非管理员行为一字不变（含改动前的形状）


def test_a_staff_filter_is_the_pre_e2_shape_byte_for_byte():
    staff = _principal(department="finance", department_ids=["shared-services"], clearance=2)

    assert build_document_retrieval_filter(staff) == {
        "$and": [
            {"classification": {"$in": [1, 2]}},
            {"department": {"$in": ["finance", "shared-services"]}},
        ]
    }


def test_a_staff_principal_without_a_department_is_still_refused():
    with pytest.raises(RetrievalScopeError) as exc:
        build_document_retrieval_filter(_principal(clearance=2))

    assert exc.value.code == "authorization_unavailable"


def test_an_anonymous_caller_is_still_refused():
    with pytest.raises(RetrievalScopeError) as exc:
        build_document_retrieval_filter(None)

    assert exc.value.code == "authentication_required"


@pytest.mark.parametrize(
    "principal, expected_code",
    [
        (_principal(department="finance", clearance=2, status="disabled"), "permission_denied"),
        (_principal(department="finance", clearance=0), "authorization_unavailable"),
        (_principal(department="finance", clearance=-1), "authorization_unavailable"),
    ],
)
def test_the_pre_existing_refusals_are_untouched(principal, expected_code):
    with pytest.raises(RetrievalScopeError) as exc:
        build_document_retrieval_filter(principal)

    assert exc.value.code == expected_code


@pytest.mark.parametrize(
    "principal, expected_code",
    [
        (_principal(roles=["admin"], clearance=0), "authorization_unavailable"),
        (_principal(roles=["admin"], clearance=3, status="disabled"), "permission_denied"),
    ],
)
def test_the_refusals_still_outrank_the_administrator_grant(principal, expected_code):
    """A frozen or level-less administrator is refused before the department is dropped.

    Built directly rather than through ``Principal.from_user``, which cannot express a zero
    clearance for an administrator: it reads ``user["clearance"] or clearance_for(role)``.
    """
    with pytest.raises(RetrievalScopeError) as exc:
        build_document_retrieval_filter(principal)

    assert exc.value.code == expected_code


# -------------------------------------- 检索链端到端：下推与本地复核同源


def test_the_principal_aware_pipeline_pushes_the_administrator_filter(monkeypatch):
    from app.rag import retrieval_pipeline as pipeline_module
    from app.rag.retrieval_pipeline import RetrievalPipeline

    _audit_capture(monkeypatch)
    documents = [
        {"content": "hr policy", "classification": 3, "department": "hr"},
        {"content": "finance policy", "classification": 1, "department": "finance"},
        {"content": "legacy chunk", "classification": None, "department": "finance"},
    ]

    class _Semantic:
        def __init__(self):
            self.where = None

        def search(self, query, k, where):
            self.where = where
            return [doc for doc in documents if doc["classification"]]

    class _BM25:
        def __init__(self):
            self.pred = None

        def search(self, query, k, pred):
            self.pred = pred
            return [doc for doc in documents if pred(doc)]

    class _Rewriter:
        @staticmethod
        def rewrite(query):
            return {"rewrites": [], "sub_questions": []}

    class _Reranker:
        @staticmethod
        def rerank(query, docs, top_k):
            return docs[:top_k]

    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    pipeline.semantic = _Semantic()
    pipeline.bm25 = _BM25()
    pipeline.rewriter = _Rewriter()
    pipeline.reranker = _Reranker()

    docs, rewrites = pipeline.search_for_principal("policy", _admin(), top_k=5)

    assert pipeline.semantic.where == {"classification": {"$in": [1, 2, 3]}}
    assert {doc["content"] for doc in docs} == {"hr policy", "finance policy"}
    assert rewrites == []
    assert pipeline_module.record_retrieval_scope is filters_module.record_retrieval_scope