"""R40: where a pre-check standard comes from, and whose department it is filed under.

Three properties, each with the test that pins it:
- a conclusion comes out without the caller naming a department, and it is reported for
  the caller's own department;
- naming somebody else's department is refused with one stable code, before the
  knowledge base is even asked;
- ``standard_source=auto_from_knowledge_base`` reads both the figure and its provenance
  out of retrieved policy text -- and invents neither: no passage stating a limit, no
  standard; no index, no conclusion at all.
"""

import asyncio
import json
import re
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.agents.contracts import Principal
from app.approval import assistant
from app.approval.assistant import STANDARD_SOURCE_AUTO, STANDARD_SOURCE_EXPLICIT
from app.common.authorization import DEPARTMENT_SELF_REPORT_DENIED
from app.common.permissions import ACTION_VIEW

# A stable code is a token the client can branch on, not a sentence.
_CODE = re.compile(r"^[a-z][a-z0-9_]*$")

STANDARD_CHUNKS = [
    {"content": "员工出差住宿标准：四星级以下酒店上限 500 元/晚。", "source": "差旅费报销制度.pdf", "chunk_index": 3},
    {"content": "住宿费不得超过 800 元/晚，超出部分自理。", "source": "财务审批细则.docx", "chunk_index": 7},
    {"content": "本章只描述申请流程，不含任何金额。", "source": "报销流程说明.md", "chunk_index": 1},
]


def _principal(username, *, role="staff", department="研发部", **overrides):
    from app.common.permissions import ROLE_PERMISSIONS
    from app.common.rbac import clearance_for

    data = {
        "user_id": f"u-{username}",
        "username": username,
        "roles": [role],
        "permissions": sorted(ROLE_PERMISSIONS[role]),
        "department": department,
        "clearance": clearance_for(role),
    }
    data.update(overrides)
    return Principal(**data)


def _request(principal):
    state = type("State", (), {"principal": principal, "username": principal.username})()
    return type("Request", (), {"state": state})()


def _body(**overrides):
    from app.api.v1.intelligence import ApprovalRequest

    data = {
        "amount": Decimal("680"),
        "standard": Decimal("500"),
        "department": "研发部",
        "expense_type": "住宿费",
        "evidence": ["差旅费报销制度.pdf 第3页"],
    }
    data.update(overrides)
    return ApprovalRequest(**data)


def _precheck(body, principal):
    from app.api.v1.intelligence import approval_precheck

    return asyncio.run(approval_precheck(body, _request(principal)))


class _Index:
    """The retrieval seam: records the query the route asked, answers with fixed chunks."""

    def __init__(self, hits=(), error=None):
        self.hits = list(hits)
        self.error = error
        self.calls = []

    def __call__(self, query, principal, *, top_k):
        if self.error is not None:
            raise self.error
        self.calls.append({"query": query, "principal": principal, "top_k": top_k})
        return self.hits


def _install(monkeypatch, hits=(), error=None):
    index = _Index(hits, error)
    monkeypatch.setattr(assistant, "retrieve_expense_hits", index)
    return index


# ------------------------------------------------------ the department belongs to the caller
def test_a_conclusion_without_any_department_is_filed_under_the_caller_s_own():
    from app.api.v1.intelligence import ApprovalRequest

    body = ApprovalRequest(
        amount=Decimal("680"),
        standard=Decimal("500"),
        expense_type="住宿费",
        evidence=["差旅费报销制度.pdf 第3页"],
    )
    result = _precheck(body, _principal("staff-omitted-department"))

    assert result["department"] == "研发部"
    assert result["status"] == "需人工审批", "a conclusion came out even though nobody named a department"
    assert Decimal(result["excess_amount"]) == Decimal("180.00")
    assert result["approved"] is False


def test_repeating_your_own_department_keeps_working_and_answers_with_the_server_value():
    from app.common.authorization import verify_department_self_report

    principal = _principal("staff-same-department")

    assert verify_department_self_report(principal, "研发部 ", action=ACTION_VIEW) == "研发部"
    assert verify_department_self_report(principal, "", action=ACTION_VIEW) == "研发部"


def test_a_forged_department_is_refused_with_one_stable_code():
    with pytest.raises(HTTPException) as excinfo:
        _precheck(_body(department="市场部"), _principal("staff-forged-department"))

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail["code"] == "department_override_denied"
    assert excinfo.value.detail["code"] == DEPARTMENT_SELF_REPORT_DENIED
    assert _CODE.match(excinfo.value.detail["code"]), excinfo.value.detail


def test_the_refused_department_claim_is_written_to_the_audit_journal(monkeypatch):
    from app.common import authorization

    events = []
    monkeypatch.setattr(authorization, "record_audit", lambda *args, **kwargs: events.append(args))

    with pytest.raises(HTTPException) as excinfo:
        _precheck(_body(department="市场部"), _principal("staff-audited-refusal"))

    assert excinfo.value.status_code == 403
    assert [(event[1], event[2], event[3], event[4]) for event in events] == [
        (ACTION_VIEW, "denied", "approval_precheck", DEPARTMENT_SELF_REPORT_DENIED)
    ]


def test_a_forged_department_is_refused_before_the_index_is_asked(monkeypatch):
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)

    with pytest.raises(HTTPException) as excinfo:
        _precheck(
            _body(department="市场部", standard_source=STANDARD_SOURCE_AUTO),
            _principal("staff-refusal-order"),
        )

    assert excinfo.value.detail["code"] == DEPARTMENT_SELF_REPORT_DENIED
    assert index.calls == [], "a refusal must not spend a retrieval the caller had no standing for"


def test_a_principal_without_a_department_may_not_borrow_one():
    from app.common.authorization import verify_department_self_report

    with pytest.raises(HTTPException) as excinfo:
        verify_department_self_report(
            _principal("staff-departmentless", department=""), "市场部", action=ACTION_VIEW
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail["code"] == DEPARTMENT_SELF_REPORT_DENIED


def test_a_principal_in_several_departments_may_name_any_of_them():
    from app.common.authorization import verify_department_self_report

    principal = _principal("staff-seconded", department="研发部", department_ids=["研发部", "平台部"])

    assert verify_department_self_report(principal, "平台部", action=ACTION_VIEW) == "研发部"


def test_an_administrator_names_the_department_it_queried_for():
    """The one exemption, and why it is not the hole this route closes.

    The bootstrap administrator owns no department at all, and an account that acts for
    the whole tenant already retrieves every department's policy text: a label on its
    own conclusion is not a scope it lacks. The exemption reuses the platform's single
    administrator test -- the same one the resource policy applies -- so no second
    definition of "administrator" enters the codebase here.
    """
    result = _precheck(_body(department="市场部"), _principal("boss", role="admin"))

    assert result["department"] == "市场部"
    assert result["approved"] is False


# --------------------------------------------------------------- where the standard came from
def test_auto_source_reads_the_standard_and_its_provenance_out_of_the_knowledge_base(monkeypatch):
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)
    principal = _principal("staff-auto-hit")

    result = _precheck(
        _body(standard=Decimal("999999"), department="", standard_source=STANDARD_SOURCE_AUTO),
        principal,
    )

    assert index.calls == [{"query": "住宿费 标准 上限 限额", "principal": principal, "top_k": 3}]
    assert result["standard_source"] == STANDARD_SOURCE_AUTO
    assert Decimal(result["standard"]) == Decimal("500"), "the strictest stated limit binds"
    assert result["matched_expense_type"] == "住宿费"
    assert result["standard_evidence"] == ["差旅费报销制度.pdf chunk=3", "财务审批细则.docx chunk=7"]
    assert result["evidence"] == result["standard_evidence"], "the cited source is the server's own"
    assert json.dumps(result), "the response is JSON-safe: no Decimal left unstringified"
    assert result["status"] == "需人工审批"
    assert result["approved"] is False




def test_the_stricest_stated_limit_binds_whichever_chunk_came_first():
    """``min`` is the reading, not "the first hit": the loose limit must not win by ordering.

    One algorithm with the approval worker means the same aggregation rule, so it is
    pinned against the resolver directly, without the route in between.
    """
    resolved = assistant.resolve_standard_from_knowledge_base(
        "住宿费",
        _principal("staff-ordering"),
        search=lambda query, principal, *, top_k: [
            {"content": "住宿费不得超过 800 元/晚，超出部分自理。", "source": "集团细则.docx", "chunk_index": 1},
            {"content": "员工出差住宿标准：四星级以下酒店上限 500 元/晚。", "source": "差旅费报销制度.pdf", "chunk_index": 3},
        ],
    )

    assert resolved["standard"] == Decimal("500")
    assert resolved["evidence"] == ["集团细则.docx chunk=1", "差旅费报销制度.pdf chunk=3"]


def test_auto_source_keeps_only_the_passages_that_actually_state_a_figure(monkeypatch):
    _install(monkeypatch, hits=STANDARD_CHUNKS)

    result = _precheck(
        _body(department="", standard_source=STANDARD_SOURCE_AUTO),
        _principal("staff-auto-evidence"),
    )

    assert result["standard_evidence"] == ["差旅费报销制度.pdf chunk=3", "财务审批细则.docx chunk=7"]
    assert all("流程" not in item for item in result["standard_evidence"]), result["standard_evidence"]


def test_auto_source_invents_no_standard_when_no_passage_states_one(monkeypatch):
    index = _install(
        monkeypatch,
        hits=[{"content": "住宿需提前在系统内申请。", "source": "差旅费报销制度.pdf", "chunk_index": 2}],
    )

    result = _precheck(
        _body(standard=Decimal("500"), department="", standard_source=STANDARD_SOURCE_AUTO),
        _principal("staff-auto-miss"),
    )

    assert index.calls, "the index was asked, and answered without a figure"
    assert result["standard"] is None, "the number that came in is not a standard the server found"
    assert result["excess_amount"] is None
    assert result["risk_level"] == "unknown"
    assert result["status"] == "无法确认"
    assert result["standard_evidence"] == []
    assert result["approved"] is False
    assert "500" not in repr(result)


def test_an_unaskable_index_fails_closed_instead_of_reusing_the_request(monkeypatch):
    from app.api.v1 import intelligence

    _install(monkeypatch, error=RuntimeError("the vector store is not reachable"))
    computed = []
    monkeypatch.setattr(intelligence, "build_precheck", lambda *args, **kwargs: computed.append(args))

    with pytest.raises(HTTPException) as excinfo:
        _precheck(
            _body(department="", standard=Decimal("500"), standard_source=STANDARD_SOURCE_AUTO),
            _principal("staff-index-down", department="市场部"),
        )

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail["code"] == "retrieval_unavailable"
    assert _CODE.match(excinfo.value.detail["code"])
    assert computed == [], "no conclusion is computed from the values that came in"


@pytest.mark.parametrize(
    "value",
    ["auto", "AUTO", "knowledge_base", "from_kb", "standard", "从知识库", "explicit_auto"],
)
def test_an_unknown_standard_source_is_refused_with_a_stable_code(value, monkeypatch):
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)

    with pytest.raises(HTTPException) as excinfo:
        _precheck(_body(standard_source=value), _principal("staff-bad-source"))

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["code"] == "invalid_standard_source"
    assert _CODE.match(excinfo.value.detail["code"])
    assert index.calls == [], "a refused spelling must not reach the index"


def test_the_source_spelling_is_case_insensitive_but_not_fuzzy(monkeypatch):
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)

    result = _precheck(_body(standard_source=" Auto_From_Knowledge_Base "), _principal("staff-casing"))

    assert result["standard_source"] == STANDARD_SOURCE_AUTO
    assert index.calls, "the padded spelling names the same contract value"


def test_a_client_that_sends_no_standard_source_stays_on_the_old_path(monkeypatch):
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)

    result = _precheck(_body(standard_source=""), _principal("staff-legacy-client"))

    assert result["standard_source"] == STANDARD_SOURCE_EXPLICIT
    assert index.calls == []
    assert Decimal(result["standard"]) == Decimal("500")
    assert result["standard_evidence"] == []


def test_explicit_source_reports_the_category_without_touching_the_index(monkeypatch):
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)

    result = _precheck(_body(expense_type="酒店住宿"), _principal("staff-alias"))

    assert index.calls == []
    assert result["matched_expense_type"] == "住宿费"


def test_no_category_is_claimed_for_wording_the_alias_table_does_not_know(monkeypatch):
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)

    result = _precheck(
        _body(expense_type="其他", standard_source=STANDARD_SOURCE_AUTO),
        _principal("staff-unmatched-type"),
    )

    assert index.calls[0]["query"] == "其他 标准 上限 限额"
    assert result["matched_expense_type"] == ""


def test_match_expense_type_recognises_the_alias_table_only():
    assert assistant.match_expense_type("高铁票") == "交通费"
    assert assistant.match_expense_type("") == ""
    assert assistant.match_expense_type("培训") == ""
