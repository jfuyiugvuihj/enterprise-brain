"""R71: the open platform decides which department an application speaks for, not the caller.

R67 stopped trusting the ``department`` in a signed body and started deriving it from the
verified caller. It did not stop the verified caller itself from being self-reported:
``verify_open_request`` builds its Principal out of ``X-Open-Department``, and the signature
base string covers ``app_id.timestamp.body`` only -- not one identity header. So any
application holding a legitimate ``approval`` token had only to add one header to be told, by
``verify_department_self_report``, that it had always belonged to that department. R67's guard
was comparing a claim against a value that came from the same unauthenticated place.

The registry already holds the server-side answer in ``allowed_departments``, so the fix
converges on it and changes no wire format:

- a header value outside the granted set is refused with the platform's existing
  ``department_override_denied`` code, with an audit row, before the index is asked;
- an empty grant is no department at all -- the header is never consulted, and the request
  falls into the fail-closed R17 already gave it, which stays broken-on-purpose;
- one grant makes the header optional; several grants with no header do not silently pick one;
- ``/insights`` and ``/dashboard/summary`` label their rows with the converged department
  instead of ``params["department"]``, the same hole one transport over.

The skeleton is R67's on purpose: ``_register`` / ``_signed_headers`` / ``_body`` /
``_preview`` and one judgment, not a second policy with a second test language.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.approval import assistant
from app.approval.assistant import STANDARD_SOURCE_AUTO
from app.common.authorization import DEPARTMENT_SELF_REPORT_DENIED, verify_department_self_report
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
FORGED_DEPARTMENT = "marketing"  # a header value, so it must survive a latin-1 transport

STANDARD_CHUNKS = [
    {"content": "员工出差住宿标准：四星级以下酒店上限 500 元/晚。", "source": "差旅费报销制度.pdf", "chunk_index": 3},
    {"content": "住宿费不得超过 800 元/晚，超出部分自理。", "source": "财务审批细则.docx", "chunk_index": 7},
]


def _register(*, actions=("approval",), departments=()):
    clear_app_registry()
    return register_application(
        "r71-caller",
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
    data = {
        "amount": 680,
        "standard": 999999,
        "department": FORGED_DEPARTMENT,
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


# ------------------------------------------- the bypass itself, at the signature boundary
def test_one_invented_header_no_longer_buys_a_department_the_application_was_never_granted():
    """The §2 bypass, stated where it was created: nothing signs the identity headers.

    An application holding a legitimate ``approval`` token and granted no department used to
    walk out of ``verify_open_request`` owning whatever department it typed, and R67's guard
    then agreed with it -- the claim was being checked against a value from the same header.
    """
    app_info = _register()  # a legitimate approval token, granted no department at all
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body, department=FORGED_DEPARTMENT)

    principal, _record = verify_open_request(headers, body, required_action="approval")

    assert principal.department == "", "an unsigned header cannot mint an identity"
    with pytest.raises(HTTPException) as raised:
        verify_department_self_report(
            principal, FORGED_DEPARTMENT, action=ACTION_VIEW, resource_name="open_approval_preview"
        )
    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == DEPARTMENT_SELF_REPORT_DENIED
    assert _CODE.match(raised.value.detail["code"]), raised.value.detail


def test_a_forged_department_header_on_an_ungranted_application_answers_with_one_stable_code(monkeypatch):
    """The same bypass all the way through the route R67 was written to close."""
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)
    app_info = _register()

    response = _preview(_body(department=FORGED_DEPARTMENT), app_info=app_info, department=FORGED_DEPARTMENT)

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED
    assert index.calls == [], "a refusal must not spend a retrieval the caller had no standing for"


def test_a_department_header_outside_a_non_empty_grant_is_refused():
    app_info = _register(departments=[CALLER_DEPARTMENT])
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body, department="财务部")

    with pytest.raises(HTTPException) as raised:
        verify_open_request(headers, body, required_action="approval")

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == DEPARTMENT_SELF_REPORT_DENIED


@pytest.mark.parametrize(
    "claimed",
    [FORGED_DEPARTMENT, "市场部", "财务部", "总裁办", f"  {CALLER_DEPARTMENT}隔壁部  "])
def test_a_department_that_was_never_granted_is_refused_with_one_stable_code(claimed):
    app_info = _register(departments=[CALLER_DEPARTMENT])
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body, department=claimed)

    with pytest.raises(HTTPException) as raised:
        verify_open_request(headers, body, required_action="approval")

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == DEPARTMENT_SELF_REPORT_DENIED


def test_the_refused_department_header_is_written_to_the_audit_journal(monkeypatch):
    from app.common import open_platform as open_platform_module

    events = []
    monkeypatch.setattr(open_platform_module, "record_audit", lambda *args, **kwargs: events.append(args))
    app_info = _register(departments=[CALLER_DEPARTMENT])
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body, department="财务部")

    with pytest.raises(HTTPException):
        verify_open_request(headers, body, required_action="approval")

    assert [(event[1], event[2], event[3], event[4]) for event in events] == [
        ("open:approval", "denied", "r71-caller", DEPARTMENT_SELF_REPORT_DENIED)
    ]


def test_a_granted_department_still_becomes_the_effective_one():
    app_info = _register(departments=[CALLER_DEPARTMENT])
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body)

    principal, record = verify_open_request(headers, body, required_action="approval")

    assert record["app_name"] == "r71-caller"
    assert principal.department == CALLER_DEPARTMENT


# ---------------------------------- an empty grant is no department, not an open invitation
def test_a_registry_entry_that_grants_no_department_ignores_the_header():
    """Judgment ②: the header names a department, the registry granted none, so there is none."""
    app_info = _register()
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body, department=CALLER_DEPARTMENT)

    principal, _record = verify_open_request(headers, body, required_action="approval")

    assert principal.department == ""
    assert list(principal.department_ids) == []


# -------------------------------------------------- the same judgment through the R67 route
def test_a_signed_token_cannot_file_its_conclusion_under_a_department_it_named_itself(monkeypatch):
    index = _install(monkeypatch, hits=STANDARD_CHUNKS)
    app_info = _register(departments=[CALLER_DEPARTMENT])

    response = _preview(_body(department=FORGED_DEPARTMENT), app_info=app_info, department=FORGED_DEPARTMENT)

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED
    assert index.calls == [], "a refusal must not spend a retrieval the caller had no standing for"


def test_a_forged_department_header_is_refused_even_when_the_body_agrees_with_it(monkeypatch):
    """The R67 guard could not see this: header and body matched, and both were the caller's."""
    _install(monkeypatch, hits=STANDARD_CHUNKS)
    app_info = _register(departments=[CALLER_DEPARTMENT])

    response = _preview(_body(department=FORGED_DEPARTMENT), app_info=app_info, department=FORGED_DEPARTMENT)

    assert response.status_code == 403, response.text
    result_department = response.json()["detail"].get("code") if response.status_code >= 400 else None
    assert result_department == DEPARTMENT_SELF_REPORT_DENIED


def test_the_converged_department_is_the_label_on_the_answer(monkeypatch):
    _install(monkeypatch, hits=STANDARD_CHUNKS)
    app_info = _register(departments=[CALLER_DEPARTMENT])

    response = _preview(_body(department=CALLER_DEPARTMENT), app_info=app_info)

    assert response.status_code == 200, response.text
    assert response.json()["department"] == CALLER_DEPARTMENT
    assert Decimal(response.json()["standard"]) == Decimal("500")

def _signed_get(path, *, app_info, params, action, department=CALLER_DEPARTMENT):
    """A GET whose signature covers the empty body it actually sends, plus identity headers."""
    headers = _signed_headers(app_info, "", action=action, department=department)
    return client.get(f"{path}?{urlencode(params)}", headers=headers)


# ---------------------------------------- several grants do not quietly pick one of them
def test_several_grants_and_no_header_do_not_default_to_the_first_one():
    """An application acting for two departments has to say which, on a channel it does not own."""
    app_info = _register(departments=[CALLER_DEPARTMENT, "finance"])
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body, department="")

    principal, _record = verify_open_request(headers, body, required_action="approval")

    assert principal.department == ""


def test_the_granted_set_is_the_only_way_an_application_acts_for_a_second_department():
    app_info = _register(departments=[CALLER_DEPARTMENT, "finance"])
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body, department="finance")

    principal, _record = verify_open_request(headers, body, required_action="approval")

    assert principal.department == "finance"


# ------------------------------------------ the same hole, one transport over: /insights
@pytest.mark.parametrize("claimed", [FORGED_DEPARTMENT, "finance"])
def test_insights_refuse_a_department_the_application_was_never_granted(claimed):
    """One shape with the bypass in ①: header and query string agree on a department nobody granted."""
    app_info = _register(actions=["insights"], departments=[CALLER_DEPARTMENT])

    response = _signed_get(
        "/api/v1/open/insights",
        app_info=app_info,
        action="insights",
        department=claimed,
        params={"metric": "营收", "current": "150", "previous": "100", "department": claimed},
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED


def test_an_insight_is_labelled_with_the_server_s_own_department_when_the_caller_says_none():
    """The label on the answer is never missing-and-never-the-caller-s: it is the registry's."""
    app_info = _register(actions=["insights"], departments=[CALLER_DEPARTMENT])

    response = _signed_get(
        "/api/v1/open/insights",
        app_info=app_info,
        action="insights",
        params={"metric": "营收", "current": "150", "previous": "100"},
    )

    assert response.status_code == 200, response.text
    insight = response.json()["insights"][0]
    assert insight["department"] == CALLER_DEPARTMENT
    assert insight["title"] == f"{CALLER_DEPARTMENT}营收异常"


def test_an_insight_still_works_when_the_caller_repeats_its_own_department():
    app_info = _register(actions=["insights"], departments=[CALLER_DEPARTMENT])

    response = _signed_get(
        "/api/v1/open/insights",
        app_info=app_info,
        action="insights",
        params={"metric": "营收", "current": "150", "previous": "100", "department": CALLER_DEPARTMENT},
    )

    assert response.status_code == 200, response.text
    assert response.json()["insights"][0]["department"] == CALLER_DEPARTMENT


# ------------------------------------ the same hole again: /dashboard/summary
def test_dashboard_summary_refuses_a_department_the_application_was_never_granted():
    """The same bypass, one route over: a header and a query string that vouch for each other."""
    app_info = _register(actions=["dashboard"], departments=[CALLER_DEPARTMENT])

    response = _signed_get(
        "/api/v1/open/dashboard/summary",
        app_info=app_info,
        action="dashboard",
        department=FORGED_DEPARTMENT,
        params={"metric": "营收", "value": "12", "department": FORGED_DEPARTMENT},
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED


def test_dashboard_summary_groups_by_the_server_s_own_department_when_none_is_named():
    app_info = _register(actions=["dashboard"], departments=[CALLER_DEPARTMENT])

    response = _signed_get(
        "/api/v1/open/dashboard/summary",
        app_info=app_info,
        action="dashboard",
        params={"metric": "营收", "value": "12"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["departments"] == {CALLER_DEPARTMENT: {"营收": 12.0}}


def test_dashboard_summary_still_works_when_the_caller_repeats_its_own_department():
    app_info = _register(actions=["dashboard"], departments=[CALLER_DEPARTMENT])

    response = _signed_get(
        "/api/v1/open/dashboard/summary",
        app_info=app_info,
        action="dashboard",
        params={"metric": "营收", "value": "12", "department": CALLER_DEPARTMENT},
    )

    assert response.status_code == 200, response.text
    assert response.json()["departments"] == {CALLER_DEPARTMENT: {"营收": 12.0}}


def test_insights_refuse_a_granted_caller_naming_another_department_in_a_query_string():
    """The hole §2 describes for this route, with an identity the registry did grant.

    Here the convergence is innocent: the header is fine, and only the query string lies.
    Reverting the route to ``params.get("department")`` answers 200 and stamps the forged
    label on the insight, which is what makes this case worth pinning on its own.
    """
    app_info = _register(actions=["insights"], departments=[CALLER_DEPARTMENT])

    response = _signed_get(
        "/api/v1/open/insights",
        app_info=app_info,
        action="insights",
        params={"metric": "营收", "current": "150", "previous": "100", "department": FORGED_DEPARTMENT},
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED


def test_dashboard_summary_refuses_a_granted_caller_naming_another_department_in_a_query_string():
    app_info = _register(actions=["dashboard"], departments=[CALLER_DEPARTMENT])

    response = _signed_get(
        "/api/v1/open/dashboard/summary",
        app_info=app_info,
        action="dashboard",
        params={"metric": "营收", "value": "12", "department": FORGED_DEPARTMENT},
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED


@pytest.mark.parametrize(
    ("path", "action"),
    [
        pytest.param("/api/v1/open/insights", "insights", id="insights"),
        pytest.param("/api/v1/open/dashboard/summary", "dashboard", id="dashboard-summary"),
    ],
)
def test_a_department_outside_the_grant_is_refused_even_when_it_would_not_be_used(path, action):
    """The claim is the judgment, not the label: an unread query parameter is still a claim."""
    app_info = _register(actions=[action], departments=[CALLER_DEPARTMENT])

    response = _signed_get(path, app_info=app_info, action=action, params={"department": FORGED_DEPARTMENT})

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED


# ------------------------------- ④ the wire format stays put: no identity header is signed
def test_the_signature_base_string_still_covers_app_timestamp_and_body_only():
    """Pinned by text, not by line number, so a later edit that signs the headers goes red.

    Signing ``X-Open-Department`` would be the tidy fix and would silently break every
    third-party integration already deployed, because there is no version negotiation
    here: the refusal would land as a 401 signature failure on clients that cannot be asked.
    """
    source = (Path(__file__).resolve().parents[1] / "app" / "common" / "open_platform.py").read_text(
        encoding="utf-8-sig"
    )
    match = re.search(r"def build_request_signature\(.*?\n((?:    .*\n)+)", source)
    assert match, "build_request_signature no longer looks like the function this pin reads"
    base = match.group(1)
    assert 'payload = f"{app_id}.{timestamp}.{body}"' in base, base
    assert not re.search(r"x-open-", base, re.IGNORECASE), "an identity header entered the base string"


def test_a_signature_issued_without_the_department_header_still_verifies_when_it_is_added():
    """Behaviour, not text: the header rides outside the signature, and clients depend on that."""
    app_info = _register(departments=[CALLER_DEPARTMENT])
    body = json.dumps(_body(), ensure_ascii=False)
    timestamp = str(int(time.time()))
    signature = build_request_signature(app_info["app_id"], app_info["secret"], body, timestamp)
    headers = {
        "X-Open-App-Id": app_info["app_id"],
        "X-Open-Timestamp": timestamp,
        "X-Open-Signature": signature,
        "X-Open-Department": CALLER_DEPARTMENT,
    }

    principal, _record = verify_open_request(headers, body, required_action="approval")

    assert principal.department == CALLER_DEPARTMENT
