"""R250 judgement 3: a degraded trace is named, never silently local.

The fallback journal stayed on disk for one reason -- a host that cannot reach PostgreSQL
must not lose the trace -- but "we kept a copy" is only safe if somebody can find out. Four
surfaces are pinned here:

* the write: the event lands in ``TRACE_STORE_PATH`` and the durability ledger counts it
  with a stable reason code;
* the log: the first occurrence of each degradation writes the name
  ``trace_local_fallback``;
* the response body: ``source`` / ``answered_from`` carry the same name, and
  ``fallback`` is true;
* the negative: when PostgreSQL answers, the name appears nowhere in the body and nothing
  is written to the journal.

The route leg runs the real ASGI stack with the real trace store, so a body that only looks
right in a unit test does not pass.
"""
from __future__ import annotations

import json
import logging
import uuid

import pytest

from app.api.v1 import observability
from app.storage.persistence import JsonPersistenceAdapter, PostgresPersistenceAdapter
from app.trace import durability
from app.trace.durability import (
    LOCAL_FALLBACK_NAME,
    POSTGRES_SOURCE,
    REASON_BACKEND_NOT_POSTGRES,
    REASON_OWNER_MISSING,
    REASON_WRITE_FAILED,
)
from app.trace.store import TraceStore
from tests._r250_fake_postgres import FakePostgres
from tests._r250_route_client import app_client, headers_for, users  # noqa: F401 - fixtures
from tests._r250_run_fixture import emit_full_run


@pytest.fixture(autouse=True)
def clean_ledger():
    durability.reset_durability_ledger()
    yield
    durability.reset_durability_ledger()


def _store(tmp_path, engine, *, available=True):
    engine.set_unavailable(not available)
    return TraceStore(tmp_path / "fallback.jsonl", persistence=PostgresPersistenceAdapter(engine.connection_factory))


def test_a_failed_postgresql_write_goes_to_the_journal_and_is_named(tmp_path, caplog):
    engine = FakePostgres()
    store = _store(tmp_path, engine, available=False)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        event = store.record_event(
            trace_id="t-down", request_id="r-1", task_id="k-1",
            event_type="request.started", status="started", payload={"owner_id": "owner-1"},
        )

    assert event["sequence"] == 1
    assert store.path.exists(), "the fallback journal has to hold what PostgreSQL refused"
    assert store.path.read_text(encoding="utf-8").count("t-down") == 1
    ledger = durability.durability_status()
    assert ledger["fallback_events"] == 1
    assert ledger["degraded"] is True
    assert ledger["degraded_reason"] == REASON_WRITE_FAILED
    assert ledger["health"] == "fallback_active"
    assert store.durability_status()["durable"] is False, (
        "a backend that refused a write does not get to call itself durable"
    )
    assert LOCAL_FALLBACK_NAME in caplog.text, caplog.text


def test_the_readout_names_the_fallback_and_can_still_answer(tmp_path):
    engine = FakePostgres()
    store = _store(tmp_path, engine, available=False)
    trace = "r250-fallback-" + uuid.uuid4().hex[:8]
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)

    readout = store.read_run(written["run_id"])
    body = json.dumps(readout, ensure_ascii=False, default=str)

    assert readout["source"] == LOCAL_FALLBACK_NAME
    assert readout["answered_from"] == LOCAL_FALLBACK_NAME
    assert readout["fallback"] is True
    assert LOCAL_FALLBACK_NAME in body
    assert readout["found"] is True
    # The fallback is a ledger, not a shrug: replaying it rebuilds every section.
    assert readout["counts"]["agent_steps"] == written["counts"]["agent_steps"]
    assert readout["counts"]["tool_calls"] == written["counts"]["tool_calls"]
    assert readout["counts"]["model_calls"] == written["counts"]["model_calls"]
    assert readout["counts"]["trace_events"] == written["counts"]["trace_events"]


def test_the_name_disappears_when_postgres_answers(tmp_path):
    engine = FakePostgres()
    store = _store(tmp_path, engine, available=True)
    trace = "r250-durable-" + uuid.uuid4().hex[:8]
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)

    readout = store.read_run(written["run_id"])
    body = json.dumps(readout, ensure_ascii=False, default=str)

    assert readout["source"] == POSTGRES_SOURCE
    assert readout["fallback"] is False
    assert LOCAL_FALLBACK_NAME not in body, "a durable answer must not advertise a fallback"
    assert not store.path.exists()
    assert durability.durability_status()["fallback_events"] == 0
    assert store.durability_status()["durable"] is True
    assert store.durability_status()["health"] == "ok"


def test_a_backend_that_is_not_postgres_is_named_on_every_event(tmp_path):
    """``PERSISTENCE_BACKEND=json`` is a durability statement, not a working mode."""
    store = TraceStore(
        tmp_path / "fallback.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / "records.json"),
    )
    trace = "r250-json-backend"
    store.record_event(
        trace_id=trace, request_id="r-1", task_id="k-1",
        event_type="request.started", status="started", payload={"owner_id": "owner-1"},
    )

    ledger = durability.durability_status()
    assert ledger["fallback_events"] == 1
    assert ledger["degraded_reason"] == REASON_BACKEND_NOT_POSTGRES
    assert store.durability_status()["source_of_truth"] == LOCAL_FALLBACK_NAME
    assert store.read_run(f"{trace}:orchestrator")["source"] == LOCAL_FALLBACK_NAME
    assert store.durability_status()["durable"] is False
    assert store.persistence.get("trace_events", f"{trace}:1") is not None


def test_an_event_without_an_owner_is_refused_by_name(tmp_path):
    engine = FakePostgres()
    store = _store(tmp_path, engine, available=True)

    store.record_event(
        trace_id="t-no-owner", request_id="r-1", task_id="k-1",
        event_type="request.started", status="started", payload={},
    )

    assert durability.durability_status()["fallback_by_reason"][REASON_OWNER_MISSING] == 1
    assert engine.rows("trace_events") == {}


# --------------------------------------------------------------------- route surface


@pytest.fixture()
def seeded_store(tmp_path, monkeypatch):
    """The management plane reads through a store the test controls, backend included."""

    def build(*, available: bool):
        engine = FakePostgres()
        store = _store(tmp_path / ("up" if available else "down"), engine, available=available)
        trace = "r250-route-" + ("up" if available else "down")
        written = emit_full_run(store, trace=trace, owner="owner-route")
        monkeypatch.setattr(observability, "_trace_store", lambda: store)
        return store, written

    return build


def test_the_route_body_carries_the_fallback_name_when_postgres_is_down(app_client, users, seeded_store):
    _store_obj, written = seeded_store(available=False)
    username = users("r250-admin-down", "admin")

    response = app_client.get(f"/api/v1/runs/{written['run_id']}", headers=headers_for(username))

    assert response.status_code == 200, response.text
    body = response.text
    payload = response.json()
    assert payload["source"] == LOCAL_FALLBACK_NAME
    assert payload["fallback"] is True
    assert LOCAL_FALLBACK_NAME in body


def test_the_route_body_stays_clean_while_postgres_answers(app_client, users, seeded_store):
    _store_obj, written = seeded_store(available=True)
    username = users("r250-admin-up", "admin")

    response = app_client.get(f"/api/v1/runs/{written['run_id']}", headers=headers_for(username))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["source"] == POSTGRES_SOURCE
    assert payload["fallback"] is False
    assert LOCAL_FALLBACK_NAME not in response.text
    assert payload["counts"]["agent_steps"] == written["counts"]["agent_steps"]
