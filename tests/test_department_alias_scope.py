"""An operator-approved department alias must agree across file, row and search gates."""

import pandas as pd

from app.agents.contracts import Principal
from app.common.policy import authorization_decision
from app.common.rbac import filter_dataframe_rows
from app.rag.filters import resolve_document_retrieval_scope


def _scope(principal):
    return authorization_decision(principal, {
        "resource_type": "dataset", "resource_id": "sample", "owner_id": "someone-else",
        "department_ids": ["财务部"], "classification": 1, "visibility": "private",
    }, require_resource_scope=True)


def test_explicit_alias_unifies_file_row_and_retrieval_permissions(monkeypatch):
    principal = Principal.from_user({"id": "staff-1", "username": "staff-1", "role": "staff", "department": "finance"})
    frame = pd.DataFrame({"部门": ["财务部", "销售部", ""], "金额": [120, 80, 30]})
    document = {"classification": 1, "department": "财务部", "visibility": "private"}

    monkeypatch.delenv("DEPARTMENT_ALIASES_JSON", raising=False)
    assert not _scope(principal).allowed
    assert filter_dataframe_rows(frame, "staff", "finance").empty
    assert not resolve_document_retrieval_scope(principal).allows(document)

    monkeypatch.setenv("DEPARTMENT_ALIASES_JSON", '{"财务部":"finance","财务":"finance","销售部":"sales"}')
    assert _scope(principal).allowed
    assert filter_dataframe_rows(frame, "staff", "finance")["金额"].tolist() == [120]
    scope = resolve_document_retrieval_scope(principal)
    assert scope.allows(document)
    assert scope.allows({**document, "department": "销售部"}) is False
    assert "财务部" in str(scope.filters)
    assert "财务" in str(scope.filters)


def test_invalid_alias_configuration_cannot_widen_scope(monkeypatch):
    principal = Principal.from_user({"id": "staff-1", "username": "staff-1", "role": "staff", "department": "finance"})
    monkeypatch.setenv("DEPARTMENT_ALIASES_JSON", '{invalid')
    assert not _scope(principal).allowed
    assert filter_dataframe_rows(pd.DataFrame({"部门": ["财务部"]}), "staff", "finance").empty


def test_chained_or_empty_aliases_are_rejected_entirely(monkeypatch):
    from app.common.departments import department_aliases

    for value in ('{"财务部":"finance","finance":"other"}', '{"财务部":""}', '[]'):
        monkeypatch.setenv("DEPARTMENT_ALIASES_JSON", value)
        assert department_aliases() == {}
