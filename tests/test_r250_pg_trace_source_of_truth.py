"""R250 judgement 1: one run is written once and read back whole, by run_id.

The claim being tested is narrow and countable: after ``TraceStore.record_event`` has
finished, the six PostgreSQL tables hold the run, and ``read_run`` returns the same numbers
the write side produced -- four sections (run / steps / tool calls / model calls), not just
the run row. Two harnesses run the identical assertions:

* a strict in-process PostgreSQL double (``tests/_r250_fake_postgres.py``), which executes
  the real adapter SQL and the real reader SQL, enforces the DDL's NOT NULL / UNIQUE /
  foreign-key rules, and therefore runs inside the full regression gate;
* a throwaway acceptance cluster, when ``EB_PG_ACCEPTANCE_URL`` is exported -- the same
  opt-in guard ``tests/test_postgres_execution_persistence.py`` uses, so no run can touch a
  configured application database.

The second harness also covers the reason R250 exists: a *different* store, on a *different*
fallback file, sees the same run. Before this ticket the trace lived in whichever process's
``events.jsonl`` wrote it, so nothing here would have been visible across a restart.
"""
from __future__ import annotations

import os
import uuid

import pytest

from app.storage.persistence import PostgresPersistenceAdapter
from app.trace import durability
from app.trace.durability import LOCAL_FALLBACK_NAME, POSTGRES_SOURCE
from app.trace.run_reader import TraceDatabase
from app.trace.store import TraceStore
from tests._r250_fake_postgres import FakePostgres
from tests._r250_run_fixture import emit_full_run

ACCEPTANCE_URL = os.getenv("EB_PG_ACCEPTANCE_URL", "").strip()

EVENT_KEYS = {"trace_id", "request_id", "task_id", "sequence", "timestamp", "event_type", "status", "payload"}


def _trace(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@pytest.fixture(autouse=True)
def clean_ledger():
    durability.reset_durability_ledger()
    yield
    durability.reset_durability_ledger()


def _hermetic_store(tmp_path, engine=None):
    """A store on a real PostgresPersistenceAdapter, served by the in-process double."""
    engine = engine or FakePostgres()
    store = TraceStore(
        tmp_path / "fallback.jsonl",
        persistence=PostgresPersistenceAdapter(engine.connection_factory),
    )
    return store, engine


def test_the_store_recognises_the_postgres_backend(tmp_path):
    store, _engine = _hermetic_store(tmp_path)
    assert store.is_postgres_backed() is True
    assert store.durability_status()["source_of_truth"] == POSTGRES_SOURCE
    assert store.durability_status()["degraded"] is False


def test_one_run_reads_back_with_every_section_matching_the_write(tmp_path):
    store, engine = _hermetic_store(tmp_path)
    trace = _trace("r250-counts")
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)

    readout = store.read_run(written["run_id"])

    assert readout["found"] is True, readout
    assert readout["source"] == POSTGRES_SOURCE
    assert readout["counts"]["agent_runs"] == 1
    assert readout["counts"]["agent_steps"] == written["counts"]["agent_steps"]
    assert readout["counts"]["tool_calls"] == written["counts"]["tool_calls"]
    assert readout["counts"]["model_calls"] == written["counts"]["model_calls"]
    assert readout["counts"]["retrieval_traces"] == written["counts"]["retrieval_traces"]
    assert readout["counts"]["trace_events"] == written["counts"]["trace_events"]
    assert readout["counts"]["agent_steps"] >= 2, "the pin must not degrade to one step"
    assert readout["counts"]["tool_calls"] >= 3
    assert readout["counts"]["model_calls"] >= 2

    assert sorted(step["step_id"] for step in readout["steps"]) == sorted(written["written"]["agent_steps"])
    assert sorted(row["tool_call_id"] for row in readout["tool_calls"]) == sorted(
        written["written"]["tool_calls"]
    )
    assert sorted(row["model_call_id"] for row in readout["model_calls"]) == sorted(
        written["written"]["model_calls"]
    )
    assert sorted(row["retrieval_trace_id"] for row in readout["retrieval_traces"]) == sorted(
        written["written_retrieval_ids"]
    )
    # The rows really are in the six tables, not only in the readout's arithmetic.
    assert engine.rows("agent_runs")[written["run_id"]]["status"] == "completed"
    assert len(engine.rows("trace_events")) == written["counts"]["trace_events"]


def test_the_three_sections_stitch_together(tmp_path):
    store, _engine = _hermetic_store(tmp_path)
    trace = _trace("r250-join")
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)

    readout = store.read_run(written["run_id"])

    step_keys = {key for step in readout["steps"] for key in (step["step_id"], step["agent_step_id"])}
    assert readout["joined"]["steps_belonging_to_run"] == len(readout["steps"])
    assert readout["joined"]["orphan_calls"] == 0
    assert readout["joined"]["calls_linked_to_a_step"] == len(readout["tool_calls"]) + len(
        readout["model_calls"]
    )
    for call in readout["tool_calls"] + readout["model_calls"]:
        assert call["agent_run_id"] == written["run_id"]
        assert call["agent_step_id"] in step_keys, call
    assert readout["run"]["owner_id"] == "owner:" + trace
    assert readout["run"]["session_id"] == f"{trace}:session"
    # A finished section reports a finish time; an open one does not pretend to.
    for step in readout["steps"]:
        assert step["completed_at"], step["step_id"]
    for call in readout["model_calls"]:
        assert call["completed_at"], call["model_call_id"]
    assert isinstance(readout["counts"]["agent_steps"], int)


def test_a_replay_returns_the_same_event_shape_the_write_side_produced(tmp_path):
    store, _engine = _hermetic_store(tmp_path)
    trace = _trace("r250-shape")
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)

    events = store.replay(trace)

    assert len(events) == written["counts"]["trace_events"]
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    for event in events:
        assert set(event) == EVENT_KEYS, sorted(set(event) ^ EVENT_KEYS)
    assert events[0]["event_type"] == "request.started"
    assert events[-1]["event_type"] == "request.completed"


def test_another_process_sees_the_same_run(tmp_path):
    """The defect R250 closes: a second store, its own file, one database."""
    engine = FakePostgres()
    writer, _ = _hermetic_store(tmp_path / "writer", engine)
    trace = _trace("r250-cross")
    written = emit_full_run(writer, trace=trace, owner="owner:" + trace)

    reader = TraceStore(
        tmp_path / "other-process" / "fallback.jsonl",
        persistence=PostgresPersistenceAdapter(engine.connection_factory),
    )

    readout = reader.read_run(written["run_id"])
    assert readout["found"] is True
    assert readout["counts"] == dict(written["counts"], agent_runs=1)
    assert reader.replay(trace), "a restart must not lose the trace"
    assert not reader.path.exists(), "a readable trace stays out of the fallback journal"
    assert not writer.path.exists()


def test_two_writers_do_not_collide_on_event_sequence(tmp_path):
    """Sequence comes from the tables, so two stores cannot both claim trace:1."""
    engine = FakePostgres()
    first, _ = _hermetic_store(tmp_path / "first", engine)
    second = TraceStore(
        tmp_path / "second" / "fallback.jsonl",
        persistence=PostgresPersistenceAdapter(engine.connection_factory),
    )
    trace = _trace("r250-seq")
    owner = "owner:" + trace

    first.record_event(trace_id=trace, request_id="r1", task_id="t", event_type="request.started",
                       status="started", payload={"owner_id": owner})
    second.record_event(trace_id=trace, request_id="r1", task_id="t", event_type="step.started",
                       status="running", payload={"owner_id": owner, "step_id": f"{trace}:worker:doc",
                                                  "worker": "doc", "sequence": 1})
    first.record_event(trace_id=trace, request_id="r1", task_id="t", event_type="request.completed",
                       status="completed", payload={"owner_id": owner})

    sequences = sorted(int(row["sequence"]) for row in engine.rows("trace_events").values())
    assert sequences == [1, 2, 3], sequences
    assert durability.durability_status()["fallback_events"] == 0
    assert not first.path.exists() and not second.path.exists()


def test_the_reader_reads_the_six_tables_by_run_id(tmp_path):
    """The read path is SQL against the tables, and it is exercised directly here."""
    engine = FakePostgres()
    store, _ = _hermetic_store(tmp_path, engine)
    trace = _trace("r250-sql")
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)

    database = TraceDatabase(engine.connection_factory)
    bundle = database.read_run_rows(written["run_id"])

    assert bundle["run"]["agent_run_id"] == written["run_id"]
    assert len(bundle["tables"]["agent_steps"]) == written["counts"]["agent_steps"]
    assert len(bundle["tables"]["tool_calls"]) == written["counts"]["tool_calls"]
    assert len(bundle["tables"]["model_calls"]) == written["counts"]["model_calls"]
    assert database.max_sequence(trace) == written["counts"]["trace_events"]


# --------------------------------------------------------------- live PostgreSQL leg


def _acceptance_url() -> str:
    from tests.test_postgres_execution_persistence import _target_or_skip

    return _target_or_skip()


@pytest.mark.skipif(not ACCEPTANCE_URL, reason="set EB_PG_ACCEPTANCE_URL for the live trace acceptance")
def test_live_postgres_holds_the_run_and_the_reader_returns_it():  # pragma: no cover - needs a server
    import psycopg

    url = _acceptance_url()
    trace = _trace("r250-live")
    owner = "owner:" + trace
    adapter = PostgresPersistenceAdapter(lambda: psycopg.connect(url, connect_timeout=5))
    store = TraceStore(os.devnull, persistence=adapter)
    written = emit_full_run(store, trace=trace, owner=owner)

    readout = store.read_run(written["run_id"])

    assert readout["source"] == POSTGRES_SOURCE
    assert readout["found"] is True
    assert readout["counts"]["agent_runs"] == 1
    assert readout["counts"]["agent_steps"] == written["counts"]["agent_steps"]
    assert readout["counts"]["tool_calls"] == written["counts"]["tool_calls"]
    assert readout["counts"]["model_calls"] == written["counts"]["model_calls"]
    assert readout["counts"]["trace_events"] == written["counts"]["trace_events"]
    assert LOCAL_FALLBACK_NAME not in str(readout)
    assert durability.durability_status()["fallback_events"] == 0

    with psycopg.connect(url, connect_timeout=5) as handle:
        for table, key in (
            ("agent_steps", "agent_run_id"),
            ("tool_calls", "agent_run_id"),
            ("model_calls", "agent_run_id"),
        ):
            rows = handle.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {key} = %s", (written["run_id"],)
            ).fetchone()[0]
            assert rows == readout["counts"][table], (table, rows, readout["counts"])
        status = handle.execute(
            "SELECT status FROM agent_runs WHERE agent_run_id = %s", (written["run_id"],)
        ).fetchone()[0]
        assert status == "completed"
        for table in ("trace_events", "retrieval_traces", "model_calls", "tool_calls", "agent_steps"):
            handle.execute(f"DELETE FROM {table} WHERE owner_id = %s", (owner,))
        handle.execute("DELETE FROM agent_runs WHERE owner_id = %s", (owner,))
        handle.commit()
