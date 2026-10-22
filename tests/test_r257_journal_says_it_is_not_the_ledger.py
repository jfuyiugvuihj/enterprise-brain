"""R257 judgement 2: the fallback journal says out loud that it is not the total ledger.

Since R250 the file behind ``TRACE_STORE_PATH`` holds one kind of line: an event PostgreSQL
refused. Nothing in its name or its shape says so, which turns anybody's honest count of it
into a wrong number -- ``docs/testing/r59c-window-ops-2026-09-25.md`` still calls it the
total ledger, and ``scripts/r59c_recall_compare.py`` tells an operator to count events by
grepping it. Both now over-count in the direction of "it never happened", and neither is in
this ticket's write domain, so the fix has to live on the face instead:

* every refused line carries its own admission -- that it is a fallback copy, the reason
  code it exists under, and a pointer at the six tables as the complete ledger;
* the admission repeats no trace id, so counting ids in the file still returns the number
  of events the file holds, exactly once;
* a settlement receipt is a receipt and not an event, and neither one leaks into the
  trace-event contract that ``replay`` and the readout serve;
* a line the journal annotates itself is read the same way as one it inherited from before
  the marker existed, so recovery does not depend on when a line was written;
* a torn line is loud on the read path and survivable on the settlement path, and is never
  deleted by either.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.api.v1 import observability
from app.storage.persistence import PostgresPersistenceAdapter
from app.trace import durability
from app.trace.durability import (
    LOCAL_FALLBACK_NAME,
    POSTGRES_SOURCE,
    REASON_WRITE_FAILED,
    _FALLBACK_REASONS,
)
from app.trace.projections import run_id_for
from app.trace.store import (
    BACKFILL_RECEIPT_MARKER,
    FALLBACK_LINE_MARKER,
    FULL_LEDGER_STATEMENT,
    TraceStore,
)
from tests._r250_fake_postgres import FakePostgres
from tests._r250_route_client import app_client, headers_for, users  # noqa: F401 - fixtures
from tests._r250_run_fixture import emit_full_run

EVENT_KEYS = {
    "trace_id", "request_id", "task_id", "sequence", "timestamp", "event_type", "status", "payload",
}


@pytest.fixture(autouse=True)
def clean_ledger():
    durability.reset_durability_ledger()
    yield
    durability.reset_durability_ledger()


def _store(tmp_path, engine):
    return TraceStore(
        tmp_path / "fallback.jsonl",
        persistence=PostgresPersistenceAdapter(engine.connection_factory),
    )


def _lines(store):
    text = store.path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.fixture()
def degraded_store(tmp_path):
    """A store whose PostgreSQL cannot take writes, with one whole run inside the window."""
    engine = FakePostgres()
    store = _store(tmp_path, engine)
    engine.set_unavailable(True)
    trace = "r257-face-" + uuid.uuid4().hex[:6]
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)
    return engine, store, trace, written


def test_every_fallback_line_admits_that_it_is_a_fallback_line(degraded_store):
    _engine, store, _trace, written = degraded_store

    lines = _lines(store)

    assert len(lines) == written["counts"]["trace_events"]
    for line in lines:
        marker = line[FALLBACK_LINE_MARKER]
        assert marker["is_fallback"] is True
        assert marker["reason"] in _FALLBACK_REASONS, marker["reason"]
        assert marker["recorded_at"], "an operator is owed the window, not just the exception"
        assert "not the full trace ledger" in marker["full_ledger"]
        assert "trace_events" in marker["full_ledger"]
    assert FULL_LEDGER_STATEMENT in store.path.read_text(encoding="utf-8")


def test_the_admission_costs_an_event_id_no_count(degraded_store):
    """A grep for one id must still return the events that carry it, once each.

    This is the failure the annotation could have introduced: an id repeated inside its own
    marker line would make every count of the file double, which is a new wrong number in
    place of the old one.
    """
    _engine, store, trace, written = degraded_store
    text = store.path.read_text(encoding="utf-8")

    assert text.count(trace) >= written["counts"]["trace_events"]
    for line in _lines(store):
        assert trace not in json.dumps(line[FALLBACK_LINE_MARKER], ensure_ascii=False)


def test_a_settlement_receipt_is_not_an_event_and_says_what_it_covered(degraded_store):
    """The page has to be able to say "these lines are in the tables now"."""
    engine, store, trace, written = degraded_store
    engine.set_unavailable(False)

    store.backfill_fallback_journal()

    lines = _lines(store)
    assert len(lines) == written["counts"]["trace_events"] + 1
    receipt = lines[-1][BACKFILL_RECEIPT_MARKER]
    assert receipt["settled_events"] == written["counts"]["trace_events"]
    assert receipt["covered_through_line"] == len(lines) - 1
    assert receipt["still_local_lines"] == 0
    assert "no journal line was deleted" in receipt["note"]
    events = store.replay(trace)
    assert len(events) == written["counts"]["trace_events"]
    for event in events:
        assert set(event) == EVENT_KEYS, sorted(set(event) ^ EVENT_KEYS)
        assert FALLBACK_LINE_MARKER not in event
    folded = store.read_run(run_id_for(trace))
    assert folded["counts"]["trace_events"] == written["counts"]["trace_events"]


def test_an_unannotated_line_from_the_old_journal_still_settles(tmp_path):
    """The file was once the only store; those lines are recoverable too.

    Lines written before R257 carry no marker, and a sweep that required one would leave
    every pre-R250 trace in the same place it is today -- which is the debt, not a detail.
    """
    engine = FakePostgres()
    path = tmp_path / "fallback.jsonl"
    trace = "r257-legacy-" + uuid.uuid4().hex[:6]
    legacy = {
        "trace_id": trace, "request_id": f"{trace}:req", "task_id": f"{trace}:task",
        "sequence": 1, "timestamp": "2026-09-25T10:00:00+00:00",
        "event_type": "request.started", "status": "started",
        "payload": {"owner_id": "owner:" + trace},
    }
    text = json.dumps(legacy) + "\n"
    path.write_text(text, encoding="utf-8")
    store = _store(tmp_path, engine)

    report = store.backfill_fallback_journal()

    assert report["settled_events"] == 1
    assert report["journal_events"] == 1
    row = engine.rows("trace_events")[f"{trace}:1"]
    assert row["event_type"] == "request.started"
    assert engine.rows("agent_runs")[run_id_for(trace)]["owner_id"] == "owner:" + trace
    assert path.read_text(encoding="utf-8").startswith(text), (
        "settling a line must not go back and rewrite it: the receipt is appended, the "
        "annotated legacy line stays byte for byte the only copy this machine has"
    )
    assert _lines(store)[0] == legacy


def test_a_torn_line_stops_a_reader_but_not_a_sweep(tmp_path):
    """Strict where a silent short read would lie, tolerant where one bad line is not an excuse."""
    engine = FakePostgres()
    store = _store(tmp_path, engine)
    trace = "r257-torn-" + uuid.uuid4().hex[:6]
    record = _recorder(store, trace)
    engine.set_unavailable(True)
    record("request.started", "started")
    record("step.started", "running", step_id=f"{trace}:worker:doc", worker="doc", sequence=1)
    record("request.completed", "completed")
    with store.path.open("a", encoding="utf-8") as handle:
        handle.write('{"trace_id": "torn\n')
    engine.set_unavailable(False)

    with pytest.raises(ValueError):
        store.replay(trace)

    report = store.backfill_fallback_journal()

    assert report["unreadable_lines"] == 1
    assert report["settled_events"] == 3
    assert report["still_local_lines"] == 0
    assert report["covered_through_line"] == 3
    # Still unreadable afterwards: the sweep worked around the torn line, it did not
    # pretend the trace is shorter than it is.
    with pytest.raises(ValueError, match="torn|Unterminated|Expecting"):
        store.replay(trace)
    assert '"trace_id": "torn' in store.path.read_text(encoding="utf-8"), (
        "a sweep that cannot read a line does not get to remove it"
    )


def test_the_readout_reports_a_gap_only_while_one_is_open(tmp_path, monkeypatch, app_client, users):
    """The admin-facing half: the body says which events the tables do not hold yet.

    The auto-trigger is held off so the window can be read open; ``test_r257_fallback_journal_is_settled``
    pins that it closes by itself.
    """
    engine = FakePostgres()
    store = _store(tmp_path, engine)
    trace = "r257-body-" + uuid.uuid4().hex[:6]
    record = _recorder(store, trace, "owner:" + trace)
    monkeypatch.setattr(TraceStore, "maybe_backfill_fallback_journal", lambda self: None)
    engine.set_unavailable(True)
    record("request.started", "started")
    record("step.started", "running", step_id=f"{trace}:worker:doc", worker="doc", sequence=1)
    engine.set_unavailable(False)
    record("request.completed", "completed")
    monkeypatch.setattr(observability, "_trace_store", lambda: store)
    headers = headers_for(users("r257-admin-face", "admin"))

    during = app_client.get(f"/api/v1/runs/{run_id_for(trace)}", headers=headers)

    assert during.status_code == 200, during.text
    body = during.json()
    assert body["source"] == POSTGRES_SOURCE
    assert body["local_only"]["name"] == LOCAL_FALLBACK_NAME
    assert body["local_only"]["events"] == 2
    assert body["local_only"]["reasons"] == [REASON_WRITE_FAILED]

    store.backfill_fallback_journal()
    after = app_client.get(f"/api/v1/runs/{run_id_for(trace)}", headers=headers)

    assert after.status_code == 200, after.text
    assert "local_only" not in after.json(), "a settled run must not keep advertising a gap"
    assert after.json()["counts"]["trace_events"] == 3


def _recorder(store, trace, owner=""):
    owner_id = owner or "owner:" + trace

    def record(event_type, status, **payload):
        return store.record_event(
            trace_id=trace, request_id=f"{trace}:req", task_id=f"{trace}:task",
            event_type=event_type, status=status, payload={"owner_id": owner_id, **payload},
        )

    return record