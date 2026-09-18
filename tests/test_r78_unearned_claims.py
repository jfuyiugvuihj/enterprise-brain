"""R78: four claims the open platform makes about itself that it cannot keep.

R71 closed the loudest one -- an unsigned ``X-Open-Department`` header could mint an
identity, while the registry already held the server's own answer. This file closes the
remaining shapes of the same bug, where the surface says one thing and the code does
another:

* ``max_clearance`` is registered, stored, listed, and read by nobody. Whether a level 2
  application may read a level 3 chunk is open decision **H13**, the owner's to make; the
  honest move today is to stop the field from reading like a control and to pin that a
  different value changes nothing. Not to invent a comparison.
* ``X-Open-User`` is a claim, not a credential: ``build_request_signature`` covers
  ``app_id.timestamp.body``, and that base string is frozen by wire compatibility, so this
  header is signed exactly as much as the department header was. The claim stays -- a
  gateway does want its operator in the log -- but it is filed as what it is, under its own
  key, and never as the actor of a journal row.
* A registration made without ``OPEN_PLATFORM_APP_STORE_PATH`` disappears on restart. The
  controller measured that it answers 401 "未注册应用" rather than a quieter lie; nothing
  here changes that, and it is pinned so nobody turns it into a 503 or into an application
  that lost only its departments.
* ``/query``, ``/analyze`` and ``/provenance/summary`` never consulted a department. R71
  ruled they must not start refusing on one either, so what was left is the impression:
  these three now say in the answer and in the documentation that nothing was narrowed, and
  a test holds both halves of that deal.

The last item is **H18**, also unruled: an application that is registered, honest, and
never granted a department asks for a preview and is answered ``503
retrieval_unavailable`` when the true reason is that it represents no department at all.
That behaviour is the owner's to change, so the case recovering the controller's probe
expects *today's* answer, and is meant to go red the day someone tells the truth early.

The skeleton is R67's and R71's on purpose: same ``_register`` / ``_signed_headers`` /
``_body`` shape, one judgment per case, not a second policy in a second language.
"""

import ast
import asyncio
import inspect
import json
import re
import textwrap
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.agents import tools as agent_tools
from app.approval import assistant
from app.common import audit
from app.common import open_platform
from app.common.authorization import DEPARTMENT_SELF_REPORT_DENIED
from app.common.open_platform import (
    OPEN_USER_CLAIM_KEY,
    build_request_signature,
    clear_app_registry,
    configure_app_store,
    list_applications,
    load_app_registry,
    register_application,
    verify_open_request,
)
from app.common.policy import is_administrator
from app.main import app
from app.storage.persistence import JsonPersistenceAdapter

client = TestClient(app)

REPO = Path(__file__).resolve().parents[1]
APP_DIR = REPO / "app"
COLLECTION = "open_platform_apps"


# A real-looking login name is the point: that is what an unverified claim gets to wear.
IMPERSONATED = "alice"
CALLER_DEPARTMENT = "rnd"
OTHER_DEPARTMENT = "ops"
FORGED_DEPARTMENT = "marketing"

STANDARD_CHUNKS = [
    {"content": "员工出差住宿标准：四星级以下酒店上限 500 元/晚。", "source": "差旅费报销制度.pdf", "chunk_index": 3},
    {"content": "住宿费不得超过 800 元/晚，超出部分自理。", "source": "财务审批细则.docx", "chunk_index": 7},
]


# The three handlers R71 ruled must neither filter on a department nor refuse one.
UNSCOPED_HANDLERS = (
    "open_query",
    "open_analyze",
    "open_provenance_summary",
)


@pytest.fixture(autouse=True)
def _own_the_shared_surfaces(monkeypatch):
    """Own every process-global this file touches, in both directions (the R68 lesson).

    The application registry and the audit journal are module state: a case that writes
    one leaks it into whichever test runs next, and a case that leaves the store path
    pointing at a temporary file has quietly changed everyone's persistence.
    """
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("OPEN_PLATFORM_APP_STORE_PATH", raising=False)
    monkeypatch.setenv("AUDIT_PERSISTENCE", "disabled")
    audit.reset_audit_storage()
    configure_app_store("")
    clear_app_registry()
    audit.clear_audit_events()
    yield
    configure_app_store("")
    clear_app_registry()
    audit.clear_audit_events()
    monkeypatch.undo()
    audit.reset_audit_storage()


def _register(name="r78-caller", *, actions=("approval",), departments=(CALLER_DEPARTMENT,), max_clearance=3):
    clear_app_registry()
    return register_application(
        name,
        allowed_actions=list(actions),
        allowed_departments=list(departments),
        max_clearance=max_clearance,
    )


def _signed_headers(app_info, body, *, action="approval", user=IMPERSONATED, department=CALLER_DEPARTMENT):
    timestamp = str(int(time.time()))
    headers = {
        "X-Open-App-Id": app_info["app_id"],
        "X-Open-Timestamp": timestamp,
        "X-Open-Signature": build_request_signature(app_info["app_id"], app_info["secret"], body, timestamp),
        "X-Open-Action": action,
    }
    if user is not None:
        headers["X-Open-User"] = user
    if department is not None:
        headers["X-Open-Department"] = department
    return headers


def _body(**overrides):
    data = {
        "amount": 680,
        "standard": 999999,
        "department": CALLER_DEPARTMENT,
        "expense_type": "住宿费",
        "evidence": ["伪造的制度出处.pdf"],
    }
    data.update(overrides)
    return data


class _Index:
    """The retrieval seam: records the query and the subject a route asked with."""

    def __init__(self, hits=(), error=None):
        self.hits = list(hits)
        self.error = error
        self.calls = []

    def __call__(self, query, principal, *, top_k):
        if self.error is not None:
            raise self.error
        self.calls.append({"query": query, "principal": principal, "top_k": top_k})
        return self.hits


def _install_index(monkeypatch, hits=(), error=None):
    index = _Index(hits, error)
    monkeypatch.setattr(assistant, "retrieve_expense_hits", index)
    return index


def _preview(payload, *, app_info=None, user=IMPERSONATED, department=CALLER_DEPARTMENT):
    app_info = app_info or _register()
    body = json.dumps(payload, ensure_ascii=False)
    headers = _signed_headers(app_info, body, user=user, department=department)
    return client.post("/api/v1/open/approval/preview", content=body, headers=headers)


def _admin_request(role="admin", username="root"):
    """A signed-in administrator, built the way ``test_deployment_guards`` builds one."""
    from types import SimpleNamespace

    from app.agents.contracts import Principal

    principal = Principal.from_user({"id": username, "username": username, "role": role, "department": "it"})
    return SimpleNamespace(state=SimpleNamespace(username=principal.username, principal=principal), headers={})


def _register_through_the_api(**grant):
    from app.api.v1 import open_platform as routes

    request = _admin_request()
    data = routes.ApplicationRegisterRequest(**grant)
    return asyncio.run(routes.register_open_application(data, request))


def _list_through_the_api():
    from app.api.v1 import open_platform as routes

    return asyncio.run(routes.list_open_applications(_admin_request()))


def _app_sources():
    return sorted(p for p in APP_DIR.rglob("*.py") if p.is_file())

def _names_the_field(path) -> bool:
    """Does this module name the field in code, or merely talk about it in a comment?

    Rewritten by the controller on acceptance (09-18). The guard started as a raw substring
    scan of the source text, and R64 reddened it with a *comment* in app/agents/contracts.py
    explaining why the clearance error code was deliberately not added. Naming a field in
    prose rules nothing, which is exactly what this file is willing to live with; a module
    that stores, reads or compares the field is what it refuses. Parsing the tree keeps the
    second and drops the first -- dict keys, attribute reads and string constants are all
    still visible here, so the two legitimate holders stay on the list unchanged.
    """
    source = path.read_text(encoding="utf-8-sig")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "max_clearance" in source
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "max_clearance":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "max_clearance":
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "max_clearance" in node.value:
            return True
    return False




# ------------------------------------------------- ① a stored number that rules nothing
#: Every surface that shows the field shows these four together, so the number can never
#: be read without the sentence that says what it is worth.
CLEARANCE_STATEMENT_KEYS = (
    "max_clearance",
    "max_clearance_effect",
    "max_clearance_enforced",
    "max_clearance_note",
)


def _bump_stored_clearance(store: Path, app_id: str, value: int) -> int:
    """Rewrite the one figure an administrator could rewrite, and nothing else about the row."""
    adapter = JsonPersistenceAdapter(str(store))
    rows = [row for row in adapter.list(COLLECTION) if str(row.get("app_id")) == app_id]
    assert len(rows) == 1, rows
    payload = dict(rows[0])
    payload["max_clearance"] = value
    adapter.upsert(COLLECTION, app_id, payload)
    return int(JsonPersistenceAdapter(str(store)).list(COLLECTION)[0]["max_clearance"])


def test_the_registration_response_labels_the_clearance_it_stores():
    issued = _register_through_the_api(
        app_name="r78-honest",
        allowed_actions=["query"],
        allowed_departments=[CALLER_DEPARTMENT],
        max_clearance=5,
    )

    for key in CLEARANCE_STATEMENT_KEYS:
        assert key in issued, key
    assert issued["max_clearance"] == 5
    assert issued["max_clearance_effect"] == "registered_only"
    assert issued["max_clearance_enforced"] is False
    note = issued["max_clearance_note"]
    assert "no retrieval" in note.lower(), note
    assert "H13" in note, "the field has to say which ruling it is waiting for, not just that it waits"


def test_the_application_list_labels_the_same_field_the_same_way():
    issued = _register_through_the_api(
        app_name="r78-listed",
        allowed_actions=["query"],
        allowed_departments=[CALLER_DEPARTMENT],
        max_clearance=2,
    )

    rows = _list_through_the_api()["applications"]

    assert [row["app_name"] for row in rows] == ["r78-listed"]
    row = rows[0]
    assert "secret" not in row
    for key in CLEARANCE_STATEMENT_KEYS:
        assert key in row, key
    assert row["max_clearance"] == 2
    assert row["max_clearance_effect"] == issued["max_clearance_effect"]
    assert row["max_clearance_enforced"] == issued["max_clearance_enforced"] is False
    assert row["max_clearance_note"] == issued["max_clearance_note"]


def test_the_api_documentation_says_the_same_thing_to_the_client_that_reads_it():
    """A response field can be dropped by a UI; the published contract cannot be unread."""
    schema = app.openapi()

    properties = schema["components"]["schemas"]["ApplicationRegisterRequest"]["properties"]
    description = properties["max_clearance"]["description"]
    assert "registered only" in description.lower(), description
    assert "changes no result" in description.lower(), description
    assert "H13" in description, description
    for verb in ("post", "get"):
        documented = schema["paths"]["/api/v1/apps"][verb]["description"]
        assert "max_clearance" in documented, verb


def test_the_registered_clearance_changes_nothing_a_caller_can_measure(tmp_path, monkeypatch):
    """The claim ``max_clearance`` makes, tested the only way it can be: change it, measure."""
    store = tmp_path / "apps.json"
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", str(store))
    configure_app_store(str(store))
    app_info = register_application(
        "r78-clearance",
        allowed_actions=["approval"],
        allowed_departments=[CALLER_DEPARTMENT],
        max_clearance=1,
    )
    _install_index(monkeypatch, hits=STANDARD_CHUNKS)

    before = _preview(_body(), app_info=app_info)

    assert before.status_code == 200, before.text

    assert _bump_stored_clearance(store, app_info["app_id"], 5) == 5
    clear_app_registry()
    assert load_app_registry() == 1
    assert list_applications()[0]["max_clearance"] == 5, "the value never changed, so this proved nothing"

    after = _preview(_body(), app_info=app_info)

    assert after.status_code == 200, after.text
    assert after.json() == before.json(), "a figure documented as inert moved a conclusion"


def test_a_higher_registered_clearance_never_reaches_the_subject_that_would_have_to_use_it(tmp_path, monkeypatch):
    """The other half: enforcement needs a Principal, and the registry has never handed it one.

    Clearance on the subject comes from the role, so a value that reached it would show up
    here before it ever reached a document.
    """
    store = tmp_path / "apps.json"
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", str(store))
    configure_app_store(str(store))
    app_info = register_application(
        "r78-subject",
        allowed_actions=["approval"],
        allowed_departments=[CALLER_DEPARTMENT],
        max_clearance=1,
    )
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body)

    low, _low_record = verify_open_request(headers, body, required_action="approval")

    assert low.clearance == 1, low.clearance
    assert _bump_stored_clearance(store, app_info["app_id"], 5) == 5
    clear_app_registry()
    load_app_registry()

    high, _high_record = verify_open_request(headers, body, required_action="approval")

    assert high.model_dump() == low.model_dump()
    assert high.clearance == low.clearance
    assert high.clearance_label == low.clearance_label


def test_max_clearance_is_written_down_by_exactly_two_files_and_decided_by_neither():
    """Source, not sentiment: the field may live in a registry and a response, nowhere else.

    ``H13`` will eventually put a comparison somewhere. When it does it belongs in the one
    policy that already decides classification, with a ruling attached to it -- not in the
    module that stores credentials, which is what this case refuses.
    """
    holders = sorted(
        path.relative_to(REPO).as_posix()
        for path in _app_sources()
        if _names_the_field(path)
    )
    assert holders == ["app/api/v1/open_platform.py", "app/common/open_platform.py"], holders

    offenders = []
    for name in holders:
        tree = ast.parse((REPO / name).read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            # A condition or a comparison is a judgment. Reading a stored figure out of a
            # payload with an ``or`` default is not, so BoolOp stays off this list
            # ``_record_from_payload`` would read as a verdict if it were on it.
            if not isinstance(node, (ast.Compare, ast.If, ast.IfExp, ast.While, ast.Assert)):
                continue
            touched = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Name):
                    touched.add(child.id.lower())
                elif isinstance(child, ast.Attribute):
                    touched.add(child.attr.lower())
                elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                    touched.add(child.value.lower())
            if any("max_clearance" in item for item in touched):
                offenders.append(f"{name}:{node.lineno}")

    assert offenders == [], offenders


# --------------------------------------------- ② a name the caller typed is not a subject


def _journal_rows(action):
    return [event for event in audit.get_audit_events() if event["action"] == action]


def _actor_of(app_info):
    return f"open-app:{app_info['app_id']}"


def test_a_signed_application_cannot_file_its_work_under_somebody_elses_name():
    """The harm, stated where it happened: the journal used to take the header as the actor.

    ``get_audit_events(username=...)`` is how an investigator asks what one account did, so
    an unsigned header naming an account was a way of writing into that account's history.
    """
    app_info = _register(actions=("query",), departments=[CALLER_DEPARTMENT])
    body = json.dumps({"query": "本月差旅费是否超标"}, ensure_ascii=False)
    headers = _signed_headers(app_info, body, action="query", user=IMPERSONATED)

    response = client.post("/api/v1/open/query", content=body, headers=headers)

    assert response.status_code == 200, response.text
    rows = _journal_rows("open:query")
    assert [row["outcome"] for row in rows] == ["allowed"], rows
    row = rows[0]
    assert row["username"] == _actor_of(app_info), row["username"]
    assert row["owner_id"] == app_info["app_id"]
    assert row["auth_source"] == "open_platform"
    assert row["resource"] == "r78-caller", "the registry name is still the resource"
    assert row["after_summary"]["open_user_claimed"] == IMPERSONATED
    assert row["after_summary"]["open_user_signed"] is False
    assert audit.get_audit_events(username=IMPERSONATED) == [], "the claim joined alice's history"


def test_a_refused_department_header_is_journalled_against_the_application_too():
    app_info = _register(departments=[CALLER_DEPARTMENT])
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body, department=FORGED_DEPARTMENT)

    with pytest.raises(HTTPException) as raised:
        verify_open_request(headers, body, required_action="approval")

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == DEPARTMENT_SELF_REPORT_DENIED
    rows = _journal_rows("open:approval")
    assert [(row["outcome"], row["reason"]) for row in rows] == [
        ("denied", DEPARTMENT_SELF_REPORT_DENIED)
    ], rows
    assert rows[0]["username"] == _actor_of(app_info)
    assert rows[0]["after_summary"]["open_user_claimed"] == IMPERSONATED
    assert audit.get_audit_events(username=IMPERSONATED) == []


def test_the_department_guard_writes_its_refusal_under_the_application_and_not_the_claim():
    """R67's guard lives in another module, so this transport hands it the subject to blame.

    The row that guard files on its own is where the claim used to survive: same forged
    header, same ``username`` column, and an investigator filtering by that username has no
    way to tell it was an application speaking.
    """
    from app.common.permissions import ACTION_VIEW

    app_info = _register(departments=[CALLER_DEPARTMENT])

    response = _preview(_body(department=FORGED_DEPARTMENT), app_info=app_info)

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED
    rows = _journal_rows(ACTION_VIEW)
    assert [(row["outcome"], row["resource"]) for row in rows] == [
        ("denied", "open_approval_preview")
    ], rows
    assert rows[0]["username"] == _actor_of(app_info), rows[0]["username"]
    assert audit.get_audit_events(username=IMPERSONATED) == []


def test_a_claimed_name_buys_no_id_no_role_and_no_scope():
    """What the claim was never able to buy, pinned so a later edit cannot sell it: authority."""
    app_info = _register(departments=[CALLER_DEPARTMENT])
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body, user="root")

    principal, record = verify_open_request(headers, body, required_action="approval")

    assert principal.user_id == app_info["app_id"], "the subject is the application, whatever it says"
    assert principal.auth_source == "open_platform"
    assert principal.role == "staff"
    assert is_administrator(principal) is False
    assert principal.department == CALLER_DEPARTMENT, "the grant, not the header"
    assert record["actor"] == _actor_of(app_info)
    assert record[OPEN_USER_CLAIM_KEY] == "root"


def test_the_claim_is_still_the_label_two_transports_already_read():
    """The value stays where it is read today; only what it is allowed to mean changed.

    ``tests/test_open_platform.py:48`` and R67's "the index is asked as the verified caller"
    both read ``principal.username``, and neither decides anything with it: the department is
    the grant's, the id is the signature's, the clearance is the role's. Deleting the label
    would break two clients for a field that is now explicitly marked a claim everywhere it
    is recorded, so it stays -- with its name next to it.
    """
    app_info = _register(departments=[CALLER_DEPARTMENT])
    body = json.dumps(_body(), ensure_ascii=False)

    named, _named_record = verify_open_request(
        _signed_headers(app_info, body, user=IMPERSONATED), body, required_action="approval"
    )
    anonymous, _anonymous_record = verify_open_request(
        _signed_headers(app_info, body, user=None), body, required_action="approval"
    )

    assert named.username == IMPERSONATED
    assert anonymous.username == "r78-caller", "no claim, no forgery: the registry name stands"
    assert named.user_id == anonymous.user_id == app_info["app_id"]
    assert _named_record[OPEN_USER_CLAIM_KEY] == IMPERSONATED
    assert _anonymous_record[OPEN_USER_CLAIM_KEY] == ""
    assert _named_record["actor"] == _anonymous_record["actor"] == _actor_of(app_info)


def test_an_answer_says_which_of_its_names_the_server_actually_verified():
    """``/query`` used to print the claim under the key ``principal`` and nothing else."""
    app_info = _register(actions=("query",), departments=[CALLER_DEPARTMENT])
    body = json.dumps({"query": "本月差旅费是否超标"}, ensure_ascii=False)

    claimed = client.post("/api/v1/open/query", content=body, headers=_signed_headers(app_info, body, action="query"))
    silent = client.post(
        "/api/v1/open/query",
        content=body,
        headers=_signed_headers(app_info, body, action="query", user=None),
    )

    assert claimed.status_code == 200, claimed.text
    assert silent.status_code == 200, silent.text
    assert claimed.json()["actor"] == _actor_of(app_info)
    assert claimed.json()[OPEN_USER_CLAIM_KEY] == IMPERSONATED
    assert claimed.json()["principal"] == IMPERSONATED, "kept for clients that already read it"
    assert silent.json()[OPEN_USER_CLAIM_KEY] == ""
    assert silent.json()["principal"] == "r78-caller"


def test_the_signature_still_covers_nothing_but_the_application_the_moment_and_the_body():
    """R78 must not "fix" an unsigned header by signing it: clients already in the field break.

    So the claim stays unverifiable, and this case shows it -- a signature issued without any
    identity header still verifies after one is added, which is exactly why the journal may
    not treat it as an actor.
    """
    source = inspect.getsource(open_platform.build_request_signature)
    assert 'payload = f"{app_id}.{timestamp}.{body}"' in source, source
    assert not re.search(r"x-open-", source, re.IGNORECASE), "an identity header entered the base string"

    app_info = _register(departments=[CALLER_DEPARTMENT])
    body = json.dumps(_body(), ensure_ascii=False)
    bare = _signed_headers(app_info, body, user=None, department=None)

    principal, record = verify_open_request(
        {**bare, "X-Open-User": "someone-else"}, body, required_action="approval"
    )

    assert principal.username == "someone-else", "the header was not signed, and still arrived"
    assert principal.department == CALLER_DEPARTMENT, "and the grant still decided the scope"
    assert record["actor"] == _actor_of(app_info)
    assert record[OPEN_USER_CLAIM_KEY] == "someone-else"


# --------------------------------- ③ a registration that is gone is gone, and says so


def test_a_restart_that_keeps_the_store_path_keeps_every_grant_that_was_written_to_it(tmp_path, monkeypatch):
    """The control for the case below: the persistence chain does not drop the grant.

    The台账 that filed "authorizations evaporate on restart" was wrong about the grant, and
    this is the half that shows why: a second worker with the same path reads the same
    ``allowed_departments`` back out of disk.
    """
    store = tmp_path / "apps.json"
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", str(store))
    configure_app_store(str(store))
    app_info = register_application(
        "r78-durable",
        allowed_actions=["approval"],
        allowed_departments=[CALLER_DEPARTMENT],
    )

    clear_app_registry()
    assert load_app_registry() == 1

    body = json.dumps(_body(), ensure_ascii=False)
    principal, record = verify_open_request(
        _signed_headers(app_info, body), body, required_action="approval"
    )

    assert list(record["allowed_departments"]) == [CALLER_DEPARTMENT]
    assert principal.department == CALLER_DEPARTMENT


def test_a_restart_that_never_learned_the_store_path_answers_401_and_not_a_quieter_lie(tmp_path, monkeypatch):
    """Pinned as measured, because the tempting repair is the wrong one.

    Without ``OPEN_PLATFORM_APP_STORE_PATH`` the whole row is missing, not just its
    departments: an application that cannot be found is an authentication failure. The two
    answers to avoid are a 503 (which blames an index that was never asked) and a 200 built
    from an application whose grant silently became empty.
    """
    store = tmp_path / "apps.json"
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", str(store))
    configure_app_store(str(store))
    app_info = register_application(
        "r78-orphan",
        allowed_actions=["approval"],
        allowed_departments=[CALLER_DEPARTMENT],
    )
    body = json.dumps(_body(), ensure_ascii=False)
    headers = _signed_headers(app_info, body)

    monkeypatch.delenv("OPEN_PLATFORM_APP_STORE_PATH")
    configure_app_store("")
    clear_app_registry()

    assert list_applications() == [], "the row is absent, and must not reappear as an empty grant"

    with pytest.raises(HTTPException) as raised:
        verify_open_request(headers, body, required_action="approval")

    assert raised.value.status_code == 401
    assert raised.value.detail == "未注册应用"

    response = client.post("/api/v1/open/approval/preview", content=body, headers=headers)

    assert response.status_code == 401, response.text
    assert "retrieval_unavailable" not in response.text
    assert "department" not in response.text.lower()


# ------------------------------------- ④ three handlers that were never scoped to anything


def _handler_tree(name):
    from app.api.v1 import open_platform as routes

    return ast.parse(textwrap.dedent(inspect.getsource(getattr(routes, name))))


def _docstring_of(tree):
    body = tree.body[0].body
    first = body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first, first.value.value
    return None, ""


def test_the_three_handlers_that_never_had_a_department_still_read_nothing():
    """The negative half of R71's ruling: these three must not start using one either.

    Identifier or string, a mention inside a handler body is a handler that has begun to
    read a scope. The sentence about the absence belongs in the docstring and in the shared
    constant, which is exactly where this case does not look.
    """
    offenders = []
    for name in UNSCOPED_HANDLERS:
        tree = _handler_tree(name)
        docstring, _text = _docstring_of(tree)
        for statement in tree.body[0].body:
            if statement is docstring:
                continue
            for node in ast.walk(statement):
                words = set()
                if isinstance(node, ast.Name):
                    words.add(node.id.lower())
                elif isinstance(node, ast.Attribute):
                    words.add(node.attr.lower())
                elif isinstance(node, ast.arg):
                    words.add(node.arg.lower())
                elif isinstance(node, ast.keyword) and node.arg:
                    words.add(node.arg.lower())
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    words.add(node.value.lower())
                hits = sorted(word for word in words if "department" in word)
                if hits:
                    offenders.append(f"{name}:{node.lineno}:{hits}")

    assert offenders == [], offenders


def test_the_three_unscoped_handlers_say_so_in_their_documentation_and_in_their_answers():
    """The positive half. A field that is only in the code is a field nobody reads."""
    from app.api.v1 import open_platform as routes

    schema = app.openapi()
    documented = {
        "open_query": "/api/v1/open/query",
        "open_analyze": "/api/v1/open/analyze",
        "open_provenance_summary": "/api/v1/open/provenance/summary",
    }

    for name, path in documented.items():
        handler = getattr(routes, name)
        doc = inspect.getdoc(handler) or ""
        assert "department" in doc.lower(), name
        assert "_UNSCOPED_NOTICE" in doc, f"{name} must point at the one sentence it is saying"
        published = json.dumps(schema["paths"][path], ensure_ascii=False)
        assert "department" in published.lower(), f"{path} documents nothing about its scope"


def test_the_three_unscoped_handlers_answer_the_same_whichever_department_the_caller_selected():
    """Selecting a granted department is a routing choice these three never had. Same body,
    same signature, different selector: byte for byte the same answer, or the notice lied."""
    app_info = _register(actions=("query", "analyze"), departments=[CALLER_DEPARTMENT, OTHER_DEPARTMENT])
    cases = (
        ("/api/v1/open/query", "query", json.dumps({"query": "本月差旅费是否超标"}, ensure_ascii=False)),
        (
            "/api/v1/open/analyze",
            "analyze",
            json.dumps(
                {"rows": [{"department": CALLER_DEPARTMENT, "metric": "营收", "value": 12}], "insights": []},
                ensure_ascii=False,
            ),
        ),
        ("/api/v1/open/provenance/summary", "query", json.dumps({"results": []}, ensure_ascii=False)),
    )

    for path, action, body in cases:
        answers = []
        for selected in (CALLER_DEPARTMENT, OTHER_DEPARTMENT, None):
            response = client.post(
                path, content=body, headers=_signed_headers(app_info, body, action=action, department=selected)
            )
            assert response.status_code == 200, f"{path} as {selected}: {response.text}"
            answers.append(response.json())

        assert answers[0] == answers[1] == answers[2], f"{path} changed with the selected department"
        assert answers[0]["department_scoped"] is False, path
        assert "no department" in answers[0]["department_scope_note"], path

    # Not a vacuity: the three selections really did put three different subjects on the
    # wire, which is what makes the identical answers above worth anything.
    subjects = []
    query_body = json.dumps({"query": "本月差旅费是否超标"}, ensure_ascii=False)
    for selected in (CALLER_DEPARTMENT, OTHER_DEPARTMENT, None):
        principal, _record = verify_open_request(
            _signed_headers(app_info, query_body, action="query", department=selected),
            query_body,
            required_action="query",
        )
        subjects.append(principal.department)
    assert subjects == [CALLER_DEPARTMENT, OTHER_DEPARTMENT, ""], subjects


def test_a_grant_changes_nothing_in_an_answer_that_never_used_one():
    """Non-vacuity: the two requests below really do carry different departments."""
    # Two names, because ``app_id`` is a hash of name plus ``time.time_ns()`` and this clock
    # repeats a tick often enough that a same-name pair collapses into one row.
    clear_app_registry()
    granted = register_application(
        "r78-granted", allowed_actions=["query"], allowed_departments=[CALLER_DEPARTMENT, OTHER_DEPARTMENT]
    )
    ungranted = register_application("r78-ungranted", allowed_actions=["query"], allowed_departments=[])
    body = json.dumps({"query": "本月差旅费是否超标"}, ensure_ascii=False)
    granted_headers = _signed_headers(granted, body, action="query", department=OTHER_DEPARTMENT)
    ungranted_headers = _signed_headers(ungranted, body, action="query", department=FORGED_DEPARTMENT)

    granted_principal, _record = verify_open_request(granted_headers, body, required_action="query")
    ungranted_principal, _record = verify_open_request(ungranted_headers, body, required_action="query")
    assert (granted_principal.department, ungranted_principal.department) == (OTHER_DEPARTMENT, "")

    first = client.post("/api/v1/open/query", content=body, headers=granted_headers)
    second = client.post("/api/v1/open/query", content=body, headers=ungranted_headers)

    assert first.status_code == second.status_code == 200, (first.text, second.text)
    assert first.json()["context"]["metric_name"] == "住宿费标准"

    def without_identity(payload):
        # The two applications are different rows, so their ids differ by construction; the
        # answer is what has to be the same.
        return {
            key: value
            for key, value in payload.items()
            if key not in {"app", "actor", "principal", OPEN_USER_CLAIM_KEY}
        }

    assert without_identity(first.json()) == without_identity(second.json())


# --------------------------------- ⑤ H18: the 503 that is not about the index, pinned as-is
#
# 待裁项 H18 —— 本段两条用例的期望值是 **2026-09-18 实测值**，不是"正确答案"。
#
# 一个已注册、未说谎、但从未被授予任何部门的应用请求 /open/approval/preview，真因是
# "它不代表任何部门"（app/rag/filters.py 在 self.search 之前抛 RetrievalScopeError，
# code=authorization_unavailable），而它听到的是 503 retrieval_unavailable —— 一口
# 从没被问过的索引替授权背了锅。业主一句话才能改这个口径（R71 结案时总控已裁"不在
# 边界硬拒"，本单不动行为），所以这里只负责把今天的谎钉住：将来有人改成 403，或者
# 悄悄把真因塞进消息里，这两条必须响 —— 这就是它们现在的价值。
#
# 探针来源（按绝对路径只读复核后改写至此，_quarantine 目录本身未改动、未纳入仓库）：
#   C:\Users\fengx\PycharmProjects\_quarantine\2026-09-18-controller-probes\
#       test_zz_controller_probe_r71.py（1863 B）
# 该探针只 print 断言外的三件事（状态码、响应体、索引到达数）。这里把它的桩换成
# 更结实的一层：探针替掉的是整条 pipeline，于是 503 也可能只是"替身少了个方法"；
# 本用例把真实的 search_for_principal 留在原地，只把召回那一步换成记录器，
# 所以 reached==0 说的是"索引一次都没被问到"，而不是"替身长得不对"。


def _install_pipeline_probe(monkeypatch):
    """The real pipeline, minus its vector stores, with any attempted recall recorded.

    ``__new__`` is the seam the R17 scope tests already use: the pipeline's own
    ``search_for_principal`` runs -- scope resolution included -- and only the recall step
    under it is a recorder. If scope resolution ever moves behind the recall, the recorder
    fires and the case below stops passing quietly.
    """
    from app.rag.retrieval_pipeline import RetrievalPipeline

    reached = []

    def _search(query, **kwargs):
        reached.append({"query": query, **kwargs})
        return [], []

    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    pipeline.search = _search
    monkeypatch.setattr(agent_tools, "_get_pipeline", lambda *args, **kwargs: pipeline)
    return reached


def _ungranted_request():
    """One honest call: a registered application, granted nothing, asking for a preview."""
    app_info = _register(departments=())
    body = json.dumps({"amount": 680, "expense_type": "住宿费"}, ensure_ascii=False)
    return app_info, body, _signed_headers(app_info, body, department=None)


def test_an_application_granted_no_department_is_answered_503_by_an_index_it_never_reached(monkeypatch):
    reached = _install_pipeline_probe(monkeypatch)
    app_info, body, headers = _ungranted_request()

    response = client.post("/api/v1/open/approval/preview", content=body, headers=headers)

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "retrieval_unavailable"
    assert response.json()["detail"]["message"] == "the policy standard could not be retrieved"
    assert reached == [], "the answer blames the index; the index was never asked"


def test_the_real_reason_is_a_missing_grant_and_the_answer_names_the_index_instead(monkeypatch, caplog):
    """The whole of H18 in one case: the truth is available two lines away and unused."""
    from app.rag.filters import RetrievalScopeError, resolve_document_retrieval_scope

    reached = _install_pipeline_probe(monkeypatch)
    app_info, body, headers = _ungranted_request()

    principal, _record = verify_open_request(headers, body, required_action="approval")
    assert principal.department == ""

    with pytest.raises(RetrievalScopeError) as raised:
        resolve_document_retrieval_scope(principal)
    assert raised.value.code == "authorization_unavailable"

    response = client.post("/api/v1/open/approval/preview", content=body, headers=headers)

    assert response.status_code == 503
    assert "authorization_unavailable" not in json.dumps(response.json(), ensure_ascii=False)
    assert "department" not in json.dumps(response.json(), ensure_ascii=False)
    assert reached == []
    # The server did work the reason out and wrote it where only an operator can read it:
    # the log says a scope was missing, the caller is told an index is down. That is one
    # failure translated into another, not an unavailable index.
    assert any("RetrievalScopeError" in message for message in caplog.messages), caplog.messages
    assert not any("retrieval_unavailable" in message for message in caplog.messages)


def test_the_lie_is_specific_to_the_missing_grant_and_does_not_follow_a_granted_call(monkeypatch):
    """Both sides of the boundary, so the two cases above cannot pass for the wrong reason.

    Grant the same application one department and the same route answers 200 out of the same
    stub: what produced the 503 was the empty scope, not a broken seam.
    """
    index = _install_index(monkeypatch, hits=STANDARD_CHUNKS)
    granted = _register(departments=[CALLER_DEPARTMENT])

    response = _preview(_body(), app_info=granted)

    assert response.status_code == 200, response.text
    assert index.calls, "the granted call was never retrieved, so the contrast proved nothing"
    assert response.json()["standard"] == "500"
