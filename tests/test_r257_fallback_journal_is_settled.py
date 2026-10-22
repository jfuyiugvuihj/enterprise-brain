"""R257 judgement 1: a fallback window is settled into the six tables, not left in a file.

R250 made ``trace_events`` and its five siblings the source of truth and named the one thing
that still broke the sentence: while PostgreSQL refused a write, events went to
``TRACE_STORE_PATH`` and *stayed* there. The degraded stretch of time was permanently absent
from the tables, so an administrator querying the run by id read back a smaller trace and
was told nothing -- the direction of the error was "it never happened". These are the pins
for the window closing by itself:

* a sweep replays the journal through the live write path, so the rows are the rows the
  write would have made -- same counts, same terminal verdict;
* the sweep is idempotent because ``trace_events`` makes ``(trace_id, sequence)`` unique.
  That is proved twice: once by replaying the journal twice, and once with the sweep's own
  "is it already there?" question switched off, so the guard being tested is the database's
  rather than a memo;
* nothing is erased. The event lines stay and a receipt line is appended naming what was
  settled, because on a private host this file is the only copy until the tables say
  otherwise;
* the auto-trigger fires on the first write PostgreSQL takes again, and a process whose
  PostgreSQL never went away neither creates the file nor counts anything.
"""
from __future__ import annotations

import json
import os
import uuid

import pytest

from app.storage.persistence import JsonPersistenceAdapter, PostgresPersistenceAdapter
from app.trace import durability
from app.trace.durability import (
    LOCAL_FALLBACK_NAME,
    POSTGRES_SOURCE,
    REASON_BACKEND_NOT_POSTGRES,
    REASON_OWNER_MISSING,
    REASON_WRITE_FAILED,
)
from app.trace.projections import run_id_for
from app.trace.store import BACKFILL_RECEIPT_MARKER, FALLBACK_LINE_MARKER, TraceStore
from tests._r250_fake_postgres import FakePostgres
from tests._r250_run_fixture import emit_full_run

ACCEPTANCE_URL = os.getenv("EB_PG_ACCEPTANCE_URL", "").strip()

EVENT_KEYS = {
    "trace_id", "request_id", "task_id", "sequence", "timestamp", "event_type", "status", "payload",
}


@pytest.fixture(autouse=True)
def clean_ledger():
    durability.reset_durability_ledger()
    yield
    durability.reset_durability_ledger()


def _store(tmp_path, engine):
    """A store on the real adapter, plus the switch that makes PostgreSQL flap."""
    return TraceStore(
        tmp_path / "fallback.jsonl",
        persistence=PostgresPersistenceAdapter(engine.connection_factory),
    )


def _lines_of(text):
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _lines(store):
    return _lines_of(store.path.read_text(encoding="utf-8"))


def _event_lines(store):
    return [line for line in _lines(store) if BACKFILL_RECEIPT_MARKER not in line]


def _degraded_run(tmp_path):
    """One whole run written while PostgreSQL could not take it, on a store that can."""
    engine = FakePostgres()
    store = _store(tmp_path, engine)
    trace = "r257-window-" + uuid.uuid4().hex[:6]
    engine.set_unavailable(True)
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)
    engine.set_unavailable(False)
    assert engine.rows("trace_events") == {}, "the whole run degraded, that is the premise"
    return engine, store, trace, written


def _recorder(store, trace, owner):
    def record(event_type, status, **payload):
        return store.record_event(
            trace_id=trace, request_id=f"{trace}:req", task_id=f"{trace}:task",
            event_type=event_type, status=status, payload={"owner_id": owner, **payload},
        )

    return record


def test_a_degraded_window_replays_into_the_six_tables(tmp_path):
    engine, store, _trace, written = _degraded_run(tmp_path)

    report = store.backfill_fallback_journal()

    assert report["attempted"] is True
    assert report["journal_events"] == written["counts"]["trace_events"]
    assert report["settled_events"] == written["counts"]["trace_events"]
    assert report["still_local_lines"] == 0
    readout = store.read_run(written["run_id"])
    assert readout["source"] == POSTGRES_SOURCE
    assert "local_only" not in readout, "a settled window leaves no gap to report"
    assert readout["counts"] == dict(written["counts"], agent_runs=1)
    assert readout["run"]["status"] == "completed"
    assert durability.durability_status()["backfilled_events"] == written["counts"]["trace_events"]


def test_the_first_write_postgres_takes_again_settles_the_journal_unasked(tmp_path):
    """R250 promised a reachable PostgreSQL stops the name appearing; R257 adds that it also
    stops the events themselves living in a file."""
    engine = FakePostgres()
    store = _store(tmp_path, engine)
    trace = "r257-auto-" + uuid.uuid4().hex[:6]
    record = _recorder(store, trace, "owner:" + trace)

    engine.set_unavailable(True)
    record("request.started", "started", session_id=f"{trace}:session")
    record("step.started", "running", step_id=f"{trace}:worker:doc", worker="doc", sequence=1)
    assert len(_event_lines(store)) == 2 and engine.rows("trace_events") == {}

    engine.set_unavailable(False)
    record("request.completed", "completed", worker_count=1, has_final_answer=True)

    sequences = sorted(int(row["sequence"]) for row in engine.rows("trace_events").values())
    assert sequences == [1, 2, 3], "the two refused lines settled with the third, unasked"
    assert durability.durability_status()["backfilled_events"] == 2
    readout = store.read_run(run_id_for(trace))
    assert readout["source"] == POSTGRES_SOURCE
    assert readout["counts"]["trace_events"] == 3
    assert readout["run"]["status"] == "completed"


def test_replaying_the_same_journal_twice_still_leaves_one_row_per_event(tmp_path):
    """The idempotency nail: a second sweep must not double-write the six tables."""
    engine, store, _trace, written = _degraded_run(tmp_path)
    first = store.backfill_fallback_journal()
    snapshot = {table: dict(rows) for table, rows in engine.tables.items()}

    second = store.backfill_fallback_journal()

    assert first["settled_events"] == written["counts"]["trace_events"]
    assert second["settled_events"] == 0
    assert second["already_in_tables"] == written["counts"]["trace_events"]
    assert second["still_local_lines"] == 0
    for table, rows in snapshot.items():
        assert set(engine.rows(table)) == set(rows), table
    assert len(engine.rows("trace_events")) == written["counts"]["trace_events"]
    assert sorted(int(row["sequence"]) for row in engine.rows("trace_events").values()) == list(
        range(1, written["counts"]["trace_events"] + 1)
    )
    assert second["receipt"] is False, "a sweep that moved nothing appends nothing"
    assert durability.durability_status()["illegal_status_transitions"] == 0


def test_the_unique_key_is_what_makes_a_second_sweep_safe(tmp_path, monkeypatch):
    """The same nail without the sweep remembering its own work: the tables have to hold.

    ``trace_events`` refuses a second row for one ``(trace_id, sequence)`` pair, and that is
    the load bearing detail this feature leans on, so it is asked of the database here: the
    sweep is asked to forget its own lookup, and the insert has to land on one row anyway.
    """
    engine, store, _trace, written = _degraded_run(tmp_path)
    store.backfill_fallback_journal()
    monkeypatch.setattr(TraceStore, "_durable_event_row", lambda self, event: None)

    report = store.backfill_fallback_journal()

    assert report["still_local_lines"] == 0
    assert len(engine.rows("trace_events")) == written["counts"]["trace_events"], (
        "a replayed fallback line produced a second row: UNIQUE (trace_id, sequence) was bypassed"
    )
    assert len(engine.rows("agent_steps")) == written["counts"]["agent_steps"]
    assert len(engine.rows("tool_calls")) == written["counts"]["tool_calls"]
    assert len(engine.rows("model_calls")) == written["counts"]["model_calls"]


def test_a_settled_line_stays_in_the_journal_and_a_receipt_answers_for_it(tmp_path):
    engine, store, trace, written = _degraded_run(tmp_path)
    before = store.path.read_text(encoding="utf-8")

    store.backfill_fallback_journal()

    after = store.path.read_text(encoding="utf-8")
    assert after.startswith(before), (
        "a backfill that rewrote the journal would be destroying the only copy of these "
        "events this machine holds"
    )
    lines = _lines(store)
    assert len(lines) == len(_event_lines(store)) + 1
    receipt = lines[-1][BACKFILL_RECEIPT_MARKER]
    assert receipt["settled_events"] == written["counts"]["trace_events"]
    assert receipt["still_local_lines"] == 0
    assert trace not in json.dumps(receipt, ensure_ascii=False), (
        "a receipt that echoed trace ids would make a count of this file double them"
    )
    events = store.replay(trace)
    assert len(events) == written["counts"]["trace_events"], "a receipt is not an event"
    for event in events:
        assert set(event) == EVENT_KEYS, sorted(set(event) ^ EVENT_KEYS)


def test_an_unsettled_window_is_a_gap_on_the_readout_and_the_gap_closes(tmp_path, monkeypatch):
    """The face an admin sees while the window is still open, and after it is closed.

    The auto-trigger is pinned by its own test; here it is held off on purpose so the gap
    can be read while it is still there.
    """
    engine = FakePostgres()
    store = _store(tmp_path, engine)
    trace = "r257-gap-" + uuid.uuid4().hex[:6]
    record = _recorder(store, trace, "owner:" + trace)
    monkeypatch.setattr(TraceStore, "maybe_backfill_fallback_journal", lambda self: None)

    engine.set_unavailable(True)
    record("request.started", "started", session_id=f"{trace}:session")
    record("step.started", "running", step_id=f"{trace}:worker:doc", worker="doc", sequence=1)
    record("step.finished", "completed", step_id=f"{trace}:worker:doc", worker="doc")
    engine.set_unavailable(False)
    record("request.completed", "completed", worker_count=1, has_final_answer=True)

    during = store.read_run(run_id_for(trace))
    assert during["source"] == POSTGRES_SOURCE, "the tables answered, and they are short"
    assert during["counts"]["trace_events"] == 1
    gap = during["local_only"]
    assert gap["name"] == LOCAL_FALLBACK_NAME
    assert gap["events"] == 3
    assert gap["will_reach_tables"] == 3 and gap["will_not_reach_tables"] == 0
    assert gap["first_event_at"] <= gap["last_event_at"]
    assert gap["reasons"] == [REASON_WRITE_FAILED]
    assert LOCAL_FALLBACK_NAME in json.dumps(during, default=str)

    report = store.backfill_fallback_journal()
    assert report["settled_events"] == 3

    after = store.read_run(run_id_for(trace))
    assert "local_only" not in after
    assert after["counts"]["trace_events"] == 4
    assert after["run"]["status"] == "completed"
    assert durability.durability_status()["local_only_lines"] == 0


def test_a_line_that_cannot_prove_its_id_settles_at_a_number_of_its_own(tmp_path):
    """R263 changed the verdict recorded here; the borrowed id is still the premise.

    A trace that degrades midway hands the journal numbers the tables already hold,
    because the sequence read is the one thing that says what is stored, and it is the
    thing that is down. R257 answered that by refusing the lines: nothing was recovered
    and the gap stayed open for good. R263 answers it by never borrowing a number -- an
    unprovable line is addressed by its own token and, once the tables can answer for
    themselves, is renumbered at the floor they report. So the honest counter-evidence
    is no longer "refused forever": it is "settled, and without overwriting a row".
    """
    engine = FakePostgres()
    store = _store(tmp_path, engine)
    trace = "r257-collision-" + uuid.uuid4().hex[:6]
    record = _recorder(store, trace, "owner:" + trace)

    record("request.started", "started", session_id=f"{trace}:session")
    record("step.started", "running", step_id=f"{trace}:worker:doc", worker="doc", sequence=1)
    engine.set_unavailable(True)
    record("step.finished", "completed", step_id=f"{trace}:worker:doc", worker="doc")
    record("request.completed", "completed", worker_count=1, has_final_answer=True)
    engine.set_unavailable(False)

    lines = _event_lines(store)
    assert [line["sequence"] for line in lines] == [1, 2], (
        "the premise R263 keeps: a degraded writer still hands out borrowed numbers"
    )
    assert all(line[FALLBACK_LINE_MARKER]["sequence_proven"] is False for line in lines), (
        "and admits it on the line, which is the only thing the sweep may key on"
    )

    report = store.backfill_fallback_journal()

    assert report["settled_events"] == 2
    assert report["already_in_tables"] == 0
    assert report["refused"] == {}
    assert report["still_local_lines"] == 0
    assert report["unproven_lines"] == 2
    assert report["renumbered_lines"] == 2
    assert report["never_in_tables"] == 0, "no line in this journal is missing an owner"

    rows = engine.rows("trace_events")
    assert len(rows) == 4, "the two durable rows plus the two lines that arrived late"
    assert sorted(row["sequence"] for row in rows.values()) == [1, 2, 3, 4], (
        "the late lines continue past the floor instead of landing on it"
    )
    assert rows[f"{trace}:1"]["event_type"] == "request.started", (
        "a sweep must not overwrite a durable row to settle a late line"
    )
    assert rows[f"{trace}:2"]["event_type"] == "step.started"
    assert BACKFILL_RECEIPT_MARKER in store.path.read_text(encoding="utf-8"), (
        "a sweep that settled both lines must say so in the journal"
    )

    readout = store.read_run(run_id_for(trace))
    assert readout["counts"]["trace_events"] == 4
    assert "local_only" not in readout, "nothing is left held only by the file"
    assert readout["run"]["status"] == "completed", (
        "the terminal event reaches the tables, so the run row stops being cut short"
    )

    ledger = durability.durability_status()
    assert ledger["local_only_lines"] == 0
    assert ledger["unproven_sequence_events"] == 2
    assert ledger["sequence_renumbered_events"] == 2
    assert ledger["degraded"] is True, "the window itself is still reported as degraded"


def test_a_line_the_tables_can_never_own_is_counted_rather_than_retried(tmp_path):
    """Rows are attributed or not written at all; a sweep does not invent an owner."""
    engine = FakePostgres()
    store = _store(tmp_path, engine)
    trace = "r257-noowner-" + uuid.uuid4().hex[:6]
    engine.set_unavailable(True)
    store.record_event(
        trace_id=trace, request_id=f"{trace}:req", task_id=f"{trace}:task",
        event_type="request.started", status="started", payload={"owner_id": "owner:" + trace},
    )
    store.record_event(
        trace_id=trace, request_id=f"{trace}:req", task_id=f"{trace}:task",
        event_type="step.started", status="running",
        payload={"step_id": f"{trace}:worker:doc", "worker": "doc", "sequence": 1},
    )
    engine.set_unavailable(False)

    report = store.backfill_fallback_journal()

    assert report["settled_events"] == 1
    assert report["never_in_tables"] == 1
    assert report["still_local_lines"] == 1
    ledger = durability.durability_status()
    assert ledger["local_only_lines"] == 1
    assert ledger["never_in_tables"] == 1
    gap = store.read_run(run_id_for(trace))["local_only"]
    assert gap["events"] == 1
    assert gap["will_reach_tables"] == 0
    assert gap["will_not_reach_tables"] == 1
    assert gap["reasons"] == [REASON_OWNER_MISSING]
    assert engine.rows("agent_steps") == {}, "an unattributed event must not create a step row"


def test_a_host_without_the_tables_has_nothing_to_backfill_into(tmp_path):
    """``PERSISTENCE_BACKEND=json`` is not a database waiting to be filled."""
    store = TraceStore(
        tmp_path / "fallback.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / "records.json"),
    )
    store.record_event(
        trace_id="r257-json", request_id="r", task_id="k", event_type="request.started",
        status="started", payload={"owner_id": "owner-1"},
    )

    assert store.backfill_fallback_journal() == {
        "attempted": False,
        "skipped_reason": REASON_BACKEND_NOT_POSTGRES,
    }
    assert store.maybe_backfill_fallback_journal() is None
    ledger = durability.durability_status()
    assert ledger["fallback_events"] == 1
    assert ledger["backfilled_events"] == 0
    assert len(_event_lines(store)) == 1


def test_a_process_whose_postgres_always_answered_settles_nothing(tmp_path):
    """The negative that keeps R250's promise: no window, no sweep, no name, no file."""
    engine = FakePostgres()
    store = _store(tmp_path, engine)
    trace = "r257-healthy-" + uuid.uuid4().hex[:6]
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)

    assert not store.path.exists(), "a settlement sweep never creates the journal"
    assert LOCAL_FALLBACK_NAME not in json.dumps(store.read_run(written["run_id"]), default=str)
    empty = store.backfill_fallback_journal()
    assert empty["attempted"] is True and empty["journal_events"] == 0
    assert not store.path.exists()
    ledger = durability.durability_status()
    assert ledger["backfilled_events"] == 0
    assert ledger["local_only_lines"] == 0
    assert ledger["backfill_errors"] == 0
    assert ledger["fallback_events"] == 0


@pytest.mark.skipif(not ACCEPTANCE_URL, reason="set EB_PG_ACCEPTANCE_URL for the live settlement acceptance")
def test_live_postgres_settles_a_degraded_window_and_holds_at_one_row(tmp_path):  # pragma: no cover - a server
    """The same sweep against a real server, where the unique key is the DDL\'s own.

    The offline nail proves the shape; this one proves the two things a dictionary cannot:
    that ``ON CONFLICT (event_id)`` and ``trace_events_trace_id_sequence_key`` really leave
    one row per replayed event, and that a ``trace_events`` row read back through psycopg
    still answers the "is this the same event?" question the sweep asks. The degraded window
    is made honest here rather than simulated: the writer\'s connection factory raises, so
    every event really is refused and really is only in the file.
    """
    import psycopg

    from tests.test_postgres_execution_persistence import _target_or_skip

    url = _target_or_skip()
    trace = "r257-live-" + uuid.uuid4().hex[:10]
    owner = "owner:" + trace
    journal = tmp_path / "fallback.jsonl"

    def refused():
        raise psycopg.OperationalError("the acceptance window: PostgreSQL is not reachable")

    writer = TraceStore(journal, persistence=PostgresPersistenceAdapter(refused))
    written = emit_full_run(writer, trace=trace, owner=owner)
    assert len(_event_lines(writer)) == written["counts"]["trace_events"]
    assert durability.durability_status()["fallback_events"] == written["counts"]["trace_events"]

    reader = TraceStore(
        journal,
        persistence=PostgresPersistenceAdapter(lambda: psycopg.connect(url, connect_timeout=5)),
    )
    first = reader.backfill_fallback_journal()
    second = reader.backfill_fallback_journal()

    assert first["settled_events"] == written["counts"]["trace_events"]
    assert first["still_local_lines"] == 0
    assert second["settled_events"] == 0, "a settled line must not be replayed as a new one"
    assert second["already_in_tables"] == written["counts"]["trace_events"]

    readout = reader.read_run(written["run_id"])
    assert readout["source"] == POSTGRES_SOURCE
    assert "local_only" not in readout, "the tables answer for every event of this run now"
    assert readout["counts"] == dict(written["counts"], agent_runs=1)
    assert LOCAL_FALLBACK_NAME not in json.dumps(readout, default=str)
    lines = _lines_of(journal.read_text(encoding="utf-8"))
    assert len([line for line in lines if BACKFILL_RECEIPT_MARKER not in line]) == (
        written["counts"]["trace_events"]
    ), "a live sweep must not touch the event lines it settled"
    assert sum(1 for line in lines if BACKFILL_RECEIPT_MARKER in line) == 1, (
        "one receipt for the sweep that settled, none for the sweep that did nothing"
    )

    with psycopg.connect(url, connect_timeout=5) as handle:
        rows = handle.execute(
            "SELECT COUNT(*) FROM trace_events WHERE trace_id = %s", (trace,)
        ).fetchone()[0]
        assert rows == written["counts"]["trace_events"], "a replayed line produced a second row"
        for table in ("trace_events", "retrieval_traces", "model_calls", "tool_calls", "agent_steps"):
            handle.execute(f"DELETE FROM {table} WHERE owner_id = %s", (owner,))
        handle.execute("DELETE FROM agent_runs WHERE owner_id = %s", (owner,))
        handle.commit()
