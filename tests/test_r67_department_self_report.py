"""R67: an open-platform conclusion is filed under the server's own department and standard.

R40 closed this on one transport and the same judgment was left open on the other: a
signed open-platform token reached ``POST /open/approval/preview`` and supplied its own
department, its own standard, and its own provenance in the body. Three properties, each
with the test that pins it:

- ``department`` is the verified caller's own. Repeating it keeps working, naming another
  one is refused with one stable code before the index is even asked;
- the number a conclusion is compared against is read out of the knowledge base, so a
  figure left in the body is never a fallback and an unaskable index answers 503;
- ``explicit`` is the only way a caller states a number, and it has to say where that
  number came from.

The skeleton is deliberately the same one used by
``tests/test_approval_precheck_standard_source.py``: one judgment reaching two
transports, not a second policy with a second test language.
"""

import json
import re
import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.approval import assistant
from app.approval.assistant import STANDARD_SOURCE_AUTO, STANDARD_SOURCE_EXPLICIT
from app.common.authorization import DEPARTMENT_SELF_REPORT_DENIED, is_administrator
from app.common.open_platform import (
    build_request_signature,
    clear_app_registry,
    register_application,
    verify_open_request,
)
from app.common.permissions import ACTION_VIEW
from app.main import app

client = TestClient(app)

# A stable code is a token the client can branch on, not a sentence.
_CODE = re.compile(r"^[a-z][a-z0-9_]*$")

# Identity headers ride a latin-1 transport, so the caller's own department is an id.
CALLER_DEPARTMENT = "rnd"

STANDARD_CHUNKS = [
    {"content": "员工出差住宿标准：四星级以下酒店上限 500 元/晚。", "source": "差旅费报销制度.pdf", "chunk_index": 3},
    {"content": "住宿费不得超过 800 元/晚，超出部分自理。", "source": "财务审批细则.docx", "chunk_index": 7},
    {"content": "本章只描述申请流程，不含任何金额。", "source": "报销流程说明.md", "chunk_index": 1},
]

SILENT_CHUNKS = [
    {"content": "申请单须在费用发生后三十天内提交。", "source": "报销流程说明.md", "chunk_index": 1},
]


def _register(*, actions=("approval",), departments=(CALLER_DEPARTMENT,)):
    clear_app_registry()
    return register_application(
        "r67-caller",
        allowed_actions=list(actions),
        allowed_departments=list(departments),
    )


def _signed_headers(app_info, body, *, action="approval", user="svc-oa", department=CALLER_DEPARTMENT):
    timestamp = str(int(time.time()))
    headers = {
        "X-Open-App-Id": app_info["app_id"],
        "X-Open-Timestamp": timestamp,
        "X-Open-Signature": build_request_signature(app_info["app_id"], app_info["secret"], body, timestamp),
        "X-Open-Action": action,
    }
    if user:
        headers["X-Open-User"] = user
    if department:
        headers["X-Open-Department"] = department
    return headers


def _body(**overrides):
    """One preview request as it looks today: every field the caller chooses to state.

    ``standard`` is a figure no caller may supply, so it is planted here as bait: any
    conclusion that comes back with it did not get its standard from the knowledge base.
    """
    data = {
        "amount": 680,
        "standard": 999999,
        "department": CALLER_DEPARTMENT,
        "expense_type": "住宿费",
        "evidence": ["伪造的制度出处.pdf"],
        "standard_source": STANDARD_SOURCE_AUTO,
    }
    data.update(overrides)
    return data


def _preview(payload, *, app_info=None, user="svc-oa", department=CALLER_DEPARTMENT):
    app_info = app_info or _register()
    body = json.dumps(payload, ensure_ascii=False)
    headers = _signed_headers(app_info, body, user=user, department=department)
    return client.post("/api/v1/open/approval/preview", content=body, headers=headers)


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


# ------------------------------------------------------ the open surface answers for its caller
def test_a_preview_without_any_department_is_filed_under_the_caller_s_own(monkeypatch):
    _install(monkeypatch, hits=STANDARD_CHUNKS)
    payload = _body()
    del payload["department"]

    response = _preview(payload)

    assert response.status_code == 200, response.text
    assert response.json()["department"] == CALLER_DEPARTMENT


def test_repeating_your_own_department_keeps_working_and_answers_with_the_server_value(monkeypatch):
    _install(monkeypatch, hits=STANDARD_CHUNKS)

    response = _preview(_body(department=f"  {CALLER_DEPARTMENT} "))

    assert response.status_code == 200, response.text
    assert response.json()["department"] == CALLER_DEPARTMENT


def test_a_forged_department_is_refused_with_one_stable_code():
    response = _preview(_body(department="市场部"))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "department_override_denied"
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED
    assert _CODE.match(response.json()["detail"]["code"]), response.json()


@pytest.mark.parametrize(
    "claimed",
    ["市场部", "财务部", "总裁办", f"  {CALLER_DEPARTMENT}隔壁部  "],
)
def test_a_department_that_is_not_the_caller_s_is_refused_with_one_stable_code(claimed):
    response = _preview(_body(department=claimed))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED


def test_the_refused_department_claim_is_written_to_the_audit_journal(monkeypatch):
    from app.common import authorization

    events = []
    monkeypatch.setattr(authorization, "record_audit", lambda *args, **kwargs: events.append(args))

    response = _preview(_body(department="市场部"))

    assert response.status_code == 403
    assert [(event[1], event[2], event[3], event[4]) for event in events] == [
        (ACTION_VIEW, "denied", "open_approval_preview", DEPARTMENT_SELF_REPORT_DENIED)
    ]


def test_a_forged_department_is_refused_before_the_index_is_asked(monkeypatch):
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)

    response = _preview(_body(department="市场部", standard_source=STANDARD_SOURCE_AUTO))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED
    assert index.calls == [], "a refusal must not spend a retrieval the caller had no standing for"


def test_a_caller_without_a_department_may_not_borrow_one():
    # R71: the identity department now comes from the grant, so this case has to ask
    # for the zero-grant application explicitly rather than inherit the skeleton default.
    ungranted = _register(departments=())
    response = _preview(
        _body(department=CALLER_DEPARTMENT),
        app_info=ungranted,
        department="",
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED


def test_an_open_platform_caller_cannot_reach_the_administrator_exemption():
    """The one R40 exemption stays unreachable here, whatever the app record is granted.

    The exemption is the platform's single administrator test, and a signed application
    is never an administrator account: its identity is built by the signature path, so a
    token that names another department is refused exactly like a staff session is.
    """
    app_info = _register()
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body, user="svc-oa")

    principal, record = verify_open_request(headers, body, required_action="approval")

    assert record["app_name"] == "r67-caller"
    assert principal.department == CALLER_DEPARTMENT
    assert is_administrator(principal) is False


# --------------------------------------------------------------- where the standard came from
def test_a_preview_that_asks_for_nothing_is_compared_against_the_knowledge_base(monkeypatch):
    _install(monkeypatch, hits=STANDARD_CHUNKS)
    payload = _body()
    del payload["standard_source"]

    response = _preview(payload)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["standard_source"] == STANDARD_SOURCE_AUTO
    assert Decimal(result["standard"]) == Decimal("500"), "the body figure was used as the standard"
    assert Decimal(result["excess_amount"]) == Decimal("180.00")


def test_an_auto_standard_carries_the_provenance_the_index_returned(monkeypatch):
    _install(monkeypatch, hits=STANDARD_CHUNKS)

    response = _preview(_body(evidence=["伪造的制度出处.pdf"]))

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["standard_evidence"] == ["差旅费报销制度.pdf chunk=3", "财务审批细则.docx chunk=7"]
    assert "伪造的制度出处.pdf" not in result["evidence"], result["evidence"]


def test_a_number_in_the_body_is_not_a_fallback_when_no_passage_states_one(monkeypatch):
    _install(monkeypatch, hits=SILENT_CHUNKS)

    response = _preview(_body())

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["standard"] is None
    assert result["status"] == "无法确认"
    assert result["approved"] is False
    assert result["standard_evidence"] == []


def test_an_unaskable_index_fails_closed_instead_of_continuing_with_the_body_number(monkeypatch):
    _install(monkeypatch, error=RuntimeError("collection unavailable"))

    response = _preview(_body())

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "retrieval_unavailable"


def test_explicit_source_states_the_number_it_was_given_without_touching_the_index(monkeypatch):
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)

    response = _preview(_body(standard_source=STANDARD_SOURCE_EXPLICIT, standard=500))

    assert response.status_code == 200, response.text
    result = response.json()
    assert index.calls == [], "an explicit standard must not spend a retrieval"
    assert result["standard_source"] == STANDARD_SOURCE_EXPLICIT
    assert Decimal(result["standard"]) == Decimal("500")
    assert result["standard_evidence"] == [], "no retrieved passage stood behind this number"


def test_an_explicit_standard_that_names_no_origin_is_refused():
    response = _preview(_body(standard_source=STANDARD_SOURCE_EXPLICIT, evidence=[]))

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "validation_error"
    assert _CODE.match(response.json()["detail"]["code"]), response.json()


@pytest.mark.parametrize("value", ["auto", "knowledge_base", "from_knowledge_base", "检索"])
def test_an_unknown_standard_source_is_refused_with_a_stable_code(value):
    response = _preview(_body(standard_source=value))

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_standard_source"


def test_the_source_spelling_is_case_insensitive_but_not_fuzzy(monkeypatch):
    _install(monkeypatch, hits=STANDARD_CHUNKS)

    response = _preview(_body(standard_source=f"  {STANDARD_SOURCE_AUTO.upper()} "))

    assert response.status_code == 200, response.text
    assert Decimal(response.json()["standard"]) == Decimal("500")


def test_the_index_is_asked_as_the_verified_caller(monkeypatch):
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)

    response = _preview(_body(), user="svc-finance")

    assert response.status_code == 200, response.text
    assert index.calls, "the standard was never retrieved"
    asked = index.calls[0]["principal"]
    assert (asked.username, asked.department) == ("svc-finance", CALLER_DEPARTMENT)

