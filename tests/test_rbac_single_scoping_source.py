"""C-4 守卫：文档可见性只允许存在一处判定。

被删的三件（``app/common/rbac.py`` 的 ``doc_visible`` / ``build_where`` / ``make_pred``）
在删除时**零生产调用点**，只被 ``tests/test_phase2_rbac.py`` 与 ``tests/test_phase7_mcp.py``
养着；它们编码「部门为空串＝全部门可见」，与线上唯一判定
``app/rag/filters.py::resolve_document_retrieval_scope`` 的 fail-closed 口径**相反**。
留着它，任何读到 ``rbac.py`` 的人都会以为那是现行规则——这就是「两套相反规则」的来历。

这里同时钉住 e2 裁定落成的三件事实：管理员走 ``administrator_scope``（不受部门限制）、
普通账号对「部门为空的文档」看不见、普通账号没有部门时直接拒而不是被放宽。
"""
from __future__ import annotations

import inspect

import pytest

from app.agents.contracts import Principal
from app.common import rbac
from app.rag.filters import RetrievalScopeError, resolve_document_retrieval_scope

DEAD_DOC_RULES = ("doc_visible", "build_where", "make_pred")


def _principal(role: str, department: str = "sales") -> Principal:
    return Principal.from_user(
        {"id": "u-c4", "username": f"{role}-c4", "role": role, "department": department}
    )


@pytest.mark.parametrize("name", DEAD_DOC_RULES)
def test_the_second_document_rule_must_not_come_back(name: str) -> None:
    assert not hasattr(rbac, name), (
        f"rbac.{name} 复活了：文档判定只许在 app/rag/filters.py 一处"
    )


def test_rbac_source_no_longer_carries_a_department_rule() -> None:
    source = inspect.getsource(rbac)
    assert '{"department": ""}' not in source, "旧的「空部门＝公开」下推条件不许回来"
    assert "admin 直接放行（不设过滤）" not in source
    legacy_half = source.split("def filter_dataframe_rows")[0]
    assert '("", dept)' not in legacy_half


def test_administrator_scope_carries_no_department_predicate() -> None:
    scope = resolve_document_retrieval_scope(_principal("admin"))
    assert scope.departments is None
    assert scope.reason_code == "administrator_scope"
    assert "department" not in scope.filters
    assert scope.allows({"classification": 3, "department": ""}) is True


def test_staff_is_fail_closed_on_documents_without_department() -> None:
    scope = resolve_document_retrieval_scope(_principal("staff"))
    assert scope.departments == frozenset({"sales"})
    assert scope.allows({"classification": 1, "department": ""}) is False
    assert scope.allows({"classification": 1, "department": "sales"}) is True
    assert scope.allows({"classification": 2, "department": "sales"}) is False


def test_staff_without_department_is_refused_instead_of_widened() -> None:
    with pytest.raises(RetrievalScopeError) as caught:
        resolve_document_retrieval_scope(_principal("staff", ""))
    assert caught.value.code == "authorization_unavailable"


def test_anonymous_caller_is_refused() -> None:
    with pytest.raises(RetrievalScopeError) as caught:
        resolve_document_retrieval_scope(None)
    assert caught.value.code == "authentication_required"
