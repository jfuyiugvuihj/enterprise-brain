"""R250 judgement 4: the run readout is admin-only, and a refusal shows nothing.

The route is the first place an operator can ask "what did run X do", which makes it the
most interesting thing on the management plane to leave unauthenticated. Two properties are
pinned, and the second one is the reason this file exists separately:

* ``_require_admin`` is the gate -- the same primitive the rest of the module uses, not a
  second role check invented here. All four roles the platform actually issues are covered:
  admin passes, manager / staff / auditor are refused with ``admin_role_required``, an
  inactive admin is refused with ``principal_inactive``, and nobody at all gets 401.
* a refusal never touches the database and never quotes the run. The test asserts the store
  is not even called, then asserts that none of the run's own identifiers -- run id, step
  ids, tool names, model name, owner -- appear anywhere in the response body.
"""
from __future__ import annotations

import json

import pytest

from app.api.v1 import observability
from app.common import audit as audit_log
from app.storage.persistence import PostgresPersistenceAdapter
from app.trace import durability
from app.trace.store import TraceStore
from tests._r250_fake_postgres import FakePostgres
from tests._r250_route_client import ROLE_MATRIX, app_client, headers_for, users  # noqa: F401
from tests._r250_run_fixture import emit_full_run

RUNS_PATH = "/api/v1/runs/{run_id}"
SECRET_TOOL = "search_documents_r250_probe"
SECRET_MODEL = "qwen3_r250_probe"


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    """One real run in a PostgreSQL-backed store, plus the identifiers it should never leak."""
    durability.reset_durability_ledger()
    engine = FakePostgres()
    store = TraceStore(
        tmp_path / "fallback.jsonl", persistence=PostgresPersistenceAdapter(engine.connection_factory)
    )
    trace = "r250-perm"
    owner = "owner-r250-perm"
    written = _emit_with_secrets(store, trace=trace, owner=owner)
    monkeypatch.setattr(observability, "_trace_store", lambda: store)

    def refuse_read(*_args, **_kwargs):
        raise AssertionError("a refused request must not read a run")

    # A denial that still queried the store would be caught by this tripwire.
    yield {"store": store, "written": written, "owner": owner, "trip": refuse_read}
    durability.reset_durability_ledger()


def _emit_with_secrets(store, *, trace: str, owner: str) -> dict:
    written = emit_full_run(store, trace=trace, owner=owner)
    first_step = written["written"]["agent_steps"][0]
    store.record_event(
        trace_id=trace, request_id=f"{trace}:req", task_id=f"{trace}:task",
        event_type="tool_call.finished", status="completed",
        payload={
            "owner_id": owner, "record_id": f"{trace}:tool:secret", "agent_step_id": first_step,
            "tool_name": SECRET_TOOL, "status": "completed",
        },
    )
    store.record_event(
        trace_id=trace, request_id=f"{trace}:req", task_id=f"{trace}:task",
        event_type="model.finished", status="completed",
        payload={
            "owner_id": owner, "record_id": f"{trace}:model:secret", "agent_step_id": first_step,
            "provider": "ollama", "model_name": SECRET_MODEL, "status": "completed",
        },
    )
    written["counts"]["tool_calls"] += 1
    written["counts"]["model_calls"] += 1
    written["counts"]["trace_events"] += 2
    return written


def _run_content_tokens(seeded) -> list[str]:
    written = seeded["written"]
    return [
        written["run_id"],
        seeded["owner"],
        SECRET_TOOL,
        SECRET_MODEL,
        *written["written"]["agent_steps"],
        *written["written"]["model_calls"],
    ]


@pytest.fixture()
def audit_recorder(monkeypatch):
    recorded = []

    def fake_record(principal, action, outcome, resource="", reason=""):
        recorded.append({"username": getattr(principal, "username", "-"), "action": action,
                         "outcome": outcome, "resource": resource, "reason": reason})
        return dict(recorded[-1])

    monkeypatch.setattr(audit_log, "record_audit", fake_record)
    return recorded


def _envelope(response) -> dict:
    """The handler's own error body, asserted as an ``ErrorEnvelope`` and nothing else."""
    detail = response.json()["detail"]
    assert set(detail) == {"code", "message", "retryable", "details"}, detail
    return detail


def _status_code(response) -> str:
    """Whatever layer answered: a middleware plain code, or the handler's envelope.

    The full app runs its authentication middleware in front of every ``/api/v1`` route, so
    a request with no principal at all is refused before the handler and its ``detail`` is a
    bare code string. That is the fail-closed behaviour R250 depends on, so the test reads
    both shapes instead of forcing one layer to look like the other.
    """
    detail = response.json()["detail"]
    return detail["code"] if isinstance(detail, dict) else str(detail)


# --------------------------------------------------------------------- the four tiers


@pytest.mark.parametrize("role", ROLE_MATRIX)
def test_only_the_admin_role_reaches_the_run_readout(app_client, users, seeded, role, audit_recorder):
    username = users(f"r250-{role}", role)
    path = RUNS_PATH.format(run_id=seeded["written"]["run_id"])

    response = app_client.get(path, headers=headers_for(username))

    if role == "admin":
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["found"] is True
        assert payload["counts"]["agent_steps"] == seeded["written"]["counts"]["agent_steps"]
        assert [event["outcome"] for event in audit_recorder] == ["allowed"]
        return

    assert response.status_code == 403, response.text
    envelope = _envelope(response)
    assert envelope["code"] == "permission_denied"
    assert envelope["details"]["reason_code"] == "admin_role_required"
    assert envelope["details"]["action"] == "audit:read"
    assert [event["outcome"] for event in audit_recorder] == ["denied"]


def test_an_anonymous_request_never_reaches_the_handler(app_client, seeded):
    response = app_client.get(RUNS_PATH.format(run_id=seeded["written"]["run_id"]))

    assert response.status_code == 401
    assert _status_code(response) == "authentication_required"
    for token in _run_content_tokens(seeded):
        assert token not in response.text, token


def test_an_inactive_account_is_refused_before_the_read(app_client, users, seeded):
    """The stack refuses a closed account; ``_require_admin`` refuses it again behind it."""
    username = users("r250-inactive", "admin", status="inactive")

    response = app_client.get(
        RUNS_PATH.format(run_id=seeded["written"]["run_id"]), headers=headers_for(username)
    )

    assert response.status_code == 403, response.text
    assert _status_code(response) == "account_unavailable"
    for token in _run_content_tokens(seeded):
        assert token not in response.text, token


def test_require_admin_itself_refuses_an_inactive_principal():
    """The branch the middleware hides is still pinned, against the shared primitive."""
    from types import SimpleNamespace

    from app.agents.contracts import Principal
    from fastapi import HTTPException

    request = SimpleNamespace(
        state=SimpleNamespace(
            principal=Principal(
                user_id="u-r250-ghost", username="r250-ghost", role="admin",
                roles=["admin"], status="inactive",
            ),
            username="r250-ghost",
        )
    )

    with pytest.raises(HTTPException) as refused:
        observability._require_admin(request, "audit:read", observability.RUN_READOUT_RESOURCE)

    assert refused.value.status_code == 403
    assert refused.value.detail["details"]["reason_code"] == "principal_inactive"


def test_a_refusal_shows_no_run_content(app_client, users, seeded, monkeypatch):
    """The body is error codes only: no run id, no steps, no tool or model names."""
    monkeypatch.setattr(TraceStore, "read_run", seeded["trip"], raising=True)
    username = users("r250-auditor-refused", "auditor")

    response = app_client.get(
        RUNS_PATH.format(run_id=seeded["written"]["run_id"]), headers=headers_for(username)
    )

    assert response.status_code == 403, response.text
    body = response.text
    for token in _run_content_tokens(seeded):
        assert token not in body, token
    assert "steps" not in body and "tool_calls" not in body
    assert set(response.json()) == {"detail"}, response.json()
    assert set(_envelope(response)["details"]) == {
        "resource", "action", "reason_code", "username"
    }


def test_an_unknown_run_is_a_bare_not_found(app_client, users, seeded):
    username = users("r250-admin-404", "admin")

    response = app_client.get(RUNS_PATH.format(run_id="no-such-trace:orchestrator"),
                              headers=headers_for(username))

    assert response.status_code == 404, response.text
    envelope = _envelope(response)
    assert envelope["code"] == "resource_not_found"
    assert envelope["details"] == {"run_id": "no-such-trace:orchestrator", "source": "postgres"}
    assert not any(token in response.text for token in _run_content_tokens(seeded))


def test_an_empty_run_id_is_a_validation_error(app_client, users, seeded):
    username = users("r250-admin-empty", "admin")

    response = app_client.get("/api/v1/runs/%20", headers=headers_for(username))

    assert response.status_code == 400, response.text
    assert _envelope(response)["code"] == "validation_error"


def test_the_run_id_is_not_placed_into_sql(app_client, users, seeded):
    """A hostile id is a lookup key, and the reader will not build SQL out of it."""
    username = users("r250-admin-inject", "admin")
    hostile = "x:orchestrator'); DROP TABLE agent_runs; --"

    response = app_client.get(f"/api/v1/runs/{hostile}", headers=headers_for(username))

    assert response.status_code in (400, 404), response.text
    assert json.dumps(seeded["store"].read_run(seeded["written"]["run_id"])["counts"])


def test_the_readout_is_bounded(app_client, users, seeded):
    username = users("r250-admin-bounds", "admin")

    payload = app_client.get(
        RUNS_PATH.format(run_id=seeded["written"]["run_id"]), headers=headers_for(username)
    ).json()

    assert payload["bounds"] in (True, False)
    assert payload["requested_by"]["roles"] == ["admin"]
    assert payload["terminal"]["status"] == "completed"
    assert payload["terminal"]["status_is_terminal"] is True
    assert payload["terminal"]["completed_at_is_set"] is True
    assert len(json.dumps(payload)) < 200_000
