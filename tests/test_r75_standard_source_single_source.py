"""R75: one standard-source validator, two transports.

The question "what is this ``standard_source``, and do we accept it" used to be answered
twice: ``app/api/v1/intelligence.py`` had ``_standard_source`` and
``app/api/v1/open_platform.py`` had ``_open_standard_source`` -- same vocabulary, same
stable code, and a refusal message written down twice. Both bodies are deleted here; the
judgment is made once in ``app/approval.assistant``.

What this file pins, and what it therefore refuses to accept as done:

- one body decides. A "shared function plus two wrappers that each raise their own copy"
  is still two judgments, so the wording, the code, and the vocabulary test are shown to
  exist exactly once, and each transport is shown at runtime to read the *shared* string
  and the *shared* tuple rather than a private copy of either;
- the settled R40 / R67 answers do not move: the two transports must answer every legal
  and illegal spelling identically, character for character;
- silence is the one legal divergence -- session means ``explicit``, the open platform
  means ``auto_from_knowledge_base`` -- so it is pinned here as a deliberate difference
  instead of being smoothed away.
"""

import asyncio
import json
import re
import time
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agents.contracts import Principal
from app.api.v1 import intelligence, open_platform
from app.approval import assistant
from app.approval.assistant import (
    STANDARD_SOURCES,
    STANDARD_SOURCE_AUTO,
    STANDARD_SOURCE_EXPLICIT,
    resolve_standard_source,
)
from app.common.open_platform import (
    build_request_signature,
    clear_app_registry,
    register_application,
)
from app.main import app

client = TestClient(app)

# A stable code is a token the client can branch on, not a sentence.
_CODE = re.compile(r"^[a-z][a-z0-9_]*$")

# Settled in R40 and re-settled in R67. Client-visible, so this line may not reword it
# either -- it may only be *written* once.
REFUSAL_MESSAGE = "standard_source must be explicit or auto_from_knowledge_base"
REFUSAL_CODE = "invalid_standard_source"

_APP_DIR = Path(assistant.__file__).resolve().parent.parent
_OMITTED = object()

# Every one of these was refused before this line and must still be refused, by the same
# code, with the same sentence, on both transports. Type coercions are left out on
# purpose: the session body is a Pydantic model and the open body is raw JSON, so an
# integer is rejected a layer earlier there -- a difference of envelopes, not of this
# judgment, and pinned at the shared function instead (see test below).
ILLEGAL_SPELLINGS = [
    "auto",
    "AUTO",
    "Auto",
    "knowledge_base",
    "from_kb",
    "standard",
    "从知识库",
    "explicit_auto",
    "auto_from_knowledge",
    "auto_from_knowledge_bases",
    "explicitly",
    "expense",
    "default",
    "none",
]

# Legal values in other spellings: folded by case and padding, never by approximation.
FOLDED_SPELLINGS = [
    ("EXPLICIT", STANDARD_SOURCE_EXPLICIT),
    (" Explicit ", STANDARD_SOURCE_EXPLICIT),
    ("explicit", STANDARD_SOURCE_EXPLICIT),
    ("\tAuto_From_Knowledge_Base\n", STANDARD_SOURCE_AUTO),
    ("AUTO_FROM_KNOWLEDGE_BASE", STANDARD_SOURCE_AUTO),
    ("auto_from_knowledge_base", STANDARD_SOURCE_AUTO),
]

CALLER_DEPARTMENT = "rnd"

STANDARD_CHUNKS = [
    {"content": "员工出差住宿标准：四星级以下酒店上限 500 元/晚。", "source": "差旅费报销制度.pdf", "chunk_index": 3},
    {"content": "住宿费不得超过 800 元/晚，超出部分自理。", "source": "财务审批细则.docx", "chunk_index": 7},
]


class _Index:
    """The retrieval seam: records the query a route asked, answers with fixed chunks."""

    def __init__(self, hits=(), error=None):
        self.hits = list(hits)
        self.error = error
        self.calls = []

    def __call__(self, query, principal, *, top_k):
        if self.error is not None:
            raise self.error
        self.calls.append({"query": query, "principal": principal, "top_k": top_k})
        return self.hits


@pytest.fixture(autouse=True)
def _clean_surfaces(monkeypatch):
    """Own the two process-global surfaces this file touches, in both directions.

    The open-platform application registry is module state (the R68 lesson: a test that
    writes a shared store leaks it into whoever runs next), and the retrieval seam is a
    module global both routes read at call time.
    """
    clear_app_registry()
    index = _Index(STANDARD_CHUNKS)
    monkeypatch.setattr(assistant, "retrieve_expense_hits", index)
    yield index
    clear_app_registry()


# ------------------------------------------------------------- the two transports, one table
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


def _session_answer(value):
    """One spelling, put to the session transport, as an answer comparable with the other."""
    data = {
        "amount": Decimal("680"),
        "standard": Decimal("500"),
        "department": "研发部",
        "expense_type": "住宿费",
        "evidence": ["差旅费报销制度.pdf 第3页"],
    }
    if value is not _OMITTED:
        data["standard_source"] = value
    body = intelligence.ApprovalRequest(**data)
    try:
        result = asyncio.run(intelligence.approval_precheck(body, _request(_principal("staff-r75"))))
    except HTTPException as exc:
        return _refusal(exc.status_code, exc.detail)
    return _acceptance(result["standard_source"])


def _register(*, departments=(CALLER_DEPARTMENT,)):
    clear_app_registry()
    return register_application(
        "r75-caller",
        allowed_actions=["approval"],
        allowed_departments=list(departments),
    )


def _open_answer(value):
    app_info = _register()
    data = {
        "amount": 680,
        "standard": 500,
        "department": CALLER_DEPARTMENT,
        "expense_type": "住宿费",
        "evidence": ["差旅费报销制度.pdf 第3页"],
    }
    if value is not _OMITTED:
        data["standard_source"] = value
    body = json.dumps(data, ensure_ascii=False)
    timestamp = str(int(time.time()))
    headers = {
        "X-Open-App-Id": app_info["app_id"],
        "X-Open-Timestamp": timestamp,
        "X-Open-Signature": build_request_signature(app_info["app_id"], app_info["secret"], body, timestamp),
        "X-Open-Action": "approval",
        "X-Open-User": "svc-r75",
        "X-Open-Department": CALLER_DEPARTMENT,
    }
    response = client.post("/api/v1/open/approval/preview", content=body, headers=headers)
    detail = response.json().get("detail")
    if response.status_code != 200:
        return _refusal(response.status_code, detail)
    return _acceptance(response.json()["standard_source"])


def _refusal(status_code, detail):
    detail = detail if isinstance(detail, dict) else {"code": None, "message": str(detail)}
    return {
        "status": status_code,
        "code": detail.get("code"),
        "message": detail.get("message"),
        "resolved": None,
    }


def _acceptance(resolved):
    return {"status": 200, "code": None, "message": None, "resolved": resolved}


_ANSWERS = {"session": _session_answer, "open": _open_answer}


# ------------------------------------------------------------------------ written once
def _app_sources():
    return sorted(p for p in _APP_DIR.rglob("*.py") if p.is_file())


def test_the_refusal_wording_is_written_once_in_the_whole_application():
    # The exact shape this line exists to remove: two bodies that both raise the same
    # sentence. Rewording is not on the table (R40), so the only legal edit is one copy.
    hits = [
        str(p.relative_to(_APP_DIR))
        for p in _app_sources()
        if REFUSAL_MESSAGE in p.read_text(encoding="utf-8-sig")
    ]
    assert hits == [str(Path("approval") / "assistant.py")], hits


def test_the_stable_code_is_written_once_in_the_whole_application():
    hits = [
        str(p.relative_to(_APP_DIR))
        for p in _app_sources()
        if f'"{REFUSAL_CODE}"' in p.read_text(encoding="utf-8-sig")
    ]
    assert hits == [str(Path("approval") / "assistant.py")], hits


def test_the_vocabulary_test_is_written_once_in_the_whole_application():
    hits = [
        str(p.relative_to(_APP_DIR))
        for p in _app_sources()
        if "in STANDARD_SOURCES" in p.read_text(encoding="utf-8-sig")
    ]
    assert hits == [str(Path("approval") / "assistant.py")], hits


def test_both_duplicate_bodies_are_deleted_not_left_as_shells():
    # "A shared function plus a private copy that calls it" would still be two judgments,
    # so neither transport keeps a body, a vocabulary binding, or a raise of its own.
    assert not hasattr(intelligence, "_standard_source")
    assert not hasattr(open_platform, "_open_standard_source")
    assert not hasattr(intelligence, "STANDARD_SOURCES")
    assert not hasattr(open_platform, "STANDARD_SOURCES")
    assert intelligence.resolve_standard_source is assistant.resolve_standard_source
    assert open_platform.resolve_standard_source is assistant.resolve_standard_source


# ------------------------------------------------------------------ one code path at runtime
@pytest.mark.parametrize("transport", sorted(_ANSWERS))
def test_a_refusal_comes_out_of_the_shared_function_not_the_transport(transport, monkeypatch):
    # The decisive anti-fake-green test: a wrapper that raised its own copy would keep its
    # own string. Patching the shared module's constants must change what the client sees.
    monkeypatch.setattr(assistant, "INVALID_STANDARD_SOURCE_MESSAGE", "SENTINEL-shared-message")
    monkeypatch.setattr(assistant, "INVALID_STANDARD_SOURCE_CODE", "sentinel_shared_code")

    answer = _ANSWERS[transport]("auto")

    assert answer == {
        "status": 400,
        "code": "sentinel_shared_code",
        "message": "SENTINEL-shared-message",
        "resolved": None,
    }


@pytest.mark.parametrize("transport", sorted(_ANSWERS))
def test_the_vocabulary_is_read_from_the_shared_tuple(transport, monkeypatch):
    # Shrink the one table and both transports must shrink together. Two implementations
    # -- even two wrappers around one -- would disagree the moment this tuple changes.
    monkeypatch.setattr(assistant, "STANDARD_SOURCES", (STANDARD_SOURCE_EXPLICIT,))

    answer = _ANSWERS[transport](STANDARD_SOURCE_AUTO)

    assert answer["status"] == 400
    assert answer["code"] == REFUSAL_CODE
    assert answer["message"] == REFUSAL_MESSAGE


def test_the_vocabulary_itself_did_not_grow():
    # R75 moves a judgment; it does not get to widen what counts as a standard source.
    assert STANDARD_SOURCES == (STANDARD_SOURCE_EXPLICIT, STANDARD_SOURCE_AUTO)


# ------------------------------------------------------------- the transports agree
@pytest.mark.parametrize("value", ILLEGAL_SPELLINGS)
def test_both_transports_refuse_the_same_illegal_spelling_with_the_same_answer(value):
    session = _session_answer(value)
    open_ = _open_answer(value)

    assert session == open_, (session, open_)
    assert session == {
        "status": 400,
        "code": REFUSAL_CODE,
        "message": REFUSAL_MESSAGE,
        "resolved": None,
    }
    assert _CODE.match(session["code"])


@pytest.mark.parametrize("value", ILLEGAL_SPELLINGS)
def test_a_refused_spelling_never_reaches_the_knowledge_base_on_either_transport(value, _clean_surfaces):
    _session_answer(value)
    _open_answer(value)

    assert _clean_surfaces.calls == [], "a spelling the server refuses must not buy a retrieval"


@pytest.mark.parametrize(("value", "resolved"), FOLDED_SPELLINGS)
def test_both_transports_accept_the_same_variant_and_resolve_the_same_value(value, resolved):
    session = _session_answer(value)
    open_ = _open_answer(value)

    assert session == open_ == _acceptance(resolved), (session, open_)


@pytest.mark.parametrize(
    ("value", "session_resolved", "open_resolved"),
    [
        ("", STANDARD_SOURCE_EXPLICIT, STANDARD_SOURCE_AUTO),
        ("   ", STANDARD_SOURCE_EXPLICIT, STANDARD_SOURCE_AUTO),
        (_OMITTED, STANDARD_SOURCE_EXPLICIT, STANDARD_SOURCE_AUTO),
    ],
)
def test_silence_is_the_one_place_the_two_transports_may_diverge(value, session_resolved, open_resolved):
    # Pinned as designed, not as an accident of the merge: R40 keeps the session route on
    # the pre-field behaviour, R67 put the open platform on the server's own standard.
    session = _session_answer(value)
    open_ = _open_answer(value)

    assert session == _acceptance(session_resolved)
    assert open_ == _acceptance(open_resolved)
    assert session["resolved"] != open_["resolved"]


def test_nothing_but_silence_diverges_between_the_two_transports():
    # The table, in one assertion: for every spelling that is not silence, the two
    # transports answer identically; the silence rows are the only ones allowed to differ.
    probe = ILLEGAL_SPELLINGS + [value for value, _ in FOLDED_SPELLINGS]

    for value in probe:
        assert _session_answer(value) == _open_answer(value), value

    assert _session_answer("")["resolved"] != _open_answer("")["resolved"]


# ------------------------------------------------------------------ the shared function alone
@pytest.mark.parametrize("silent_default", [STANDARD_SOURCE_EXPLICIT, STANDARD_SOURCE_AUTO])
@pytest.mark.parametrize("value", list(STANDARD_SOURCES))
def test_a_spelling_in_the_vocabulary_is_accepted_verbatim(value, silent_default):
    assert resolve_standard_source(value, silent_default=silent_default) == value


@pytest.mark.parametrize("silent_default", [STANDARD_SOURCE_EXPLICIT, STANDARD_SOURCE_AUTO])
@pytest.mark.parametrize("value", ["", "   ", "\t\n", None, 0, [], {}])
def test_silence_keeps_the_calling_transports_own_default(value, silent_default):
    # Envelope-empty is silence on both transports: ``None`` is an absent JSON value,
    # ``0`` / ``[]`` / ``{}`` are what ``str(value or "")`` has always folded to "".
    assert resolve_standard_source(value, silent_default=silent_default) == silent_default


@pytest.mark.parametrize("silent_default", [STANDARD_SOURCE_EXPLICIT, STANDARD_SOURCE_AUTO])
@pytest.mark.parametrize("value", ["auto", "Auto", "knowledge_base", "explicit_auto", "auto_from_knowledge", "1", True])
def test_anything_outside_the_vocabulary_is_refused_with_the_stable_code(value, silent_default):
    with pytest.raises(HTTPException) as excinfo:
        resolve_standard_source(value, silent_default=silent_default)

    assert excinfo.value.status_code == 400
    detail = excinfo.value.detail
    assert detail["code"] == REFUSAL_CODE
    assert _CODE.match(detail["code"])
    assert detail["message"] == REFUSAL_MESSAGE


@pytest.mark.parametrize("silent_default", [STANDARD_SOURCE_EXPLICIT, STANDARD_SOURCE_AUTO])
@pytest.mark.parametrize(
    ("value", "resolved"),
    FOLDED_SPELLINGS + [(" expense ", "expense"), ("AUTO", "auto")],
)
def test_folding_covers_spelling_and_never_meaning(value, resolved, silent_default):
    # R67 pinned this on the open transport, R40 on the session one; a fuzzy match would
    # read "auto" as "auto_from_knowledge_base" and grade an amount against a standard
    # nobody stated. Both refusals below come from the same fold, not from a guess.
    if resolved in STANDARD_SOURCES:
        assert resolve_standard_source(value, silent_default=silent_default) == resolved
    else:
        with pytest.raises(HTTPException) as excinfo:
            resolve_standard_source(value, silent_default=silent_default)
        assert excinfo.value.detail["code"] == REFUSAL_CODE


def test_the_silent_default_is_a_keyword_argument_so_no_transport_can_forget_to_choose_one():
    # Positional-by-accident would let a new transport inherit somebody else's default.
    with pytest.raises(TypeError):
        resolve_standard_source("auto", STANDARD_SOURCE_EXPLICIT)
    with pytest.raises(TypeError):
        resolve_standard_source("auto")