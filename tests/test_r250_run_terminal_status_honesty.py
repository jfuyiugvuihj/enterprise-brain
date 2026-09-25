"""R250 judgement 5: a run's terminal verdict comes from the vocabulary, or it does not move.

``agent_runs.status`` is the one column that answers "did this request finish", so the two
ways it can lie are pinned here rather than entrusted to a comment:

1. **walking a finished run back** -- ``completed`` -> ``running``. The row keeps its verdict,
   the attempt is counted in the durability ledger as ``illegal_run_status_transition``, and
   the log names it. A silently ignored write and a write that never happened are different
   claims, and the readout reports both the status and whether the store saw the terminal
   event.
2. **an unregistered literal** -- "succeeded", "done", "ok" or any other word. The vocabulary
   is derived from ``AgentResult.status`` (the ratified closed Literal) plus ``completed``,
   the word both ``app/trace/records.py`` and ``app/agents/orchestrator.py`` already fold
   ``success``/``partial`` into, and the event types that end a request come from
   ``app.common.stage_timing.REQUEST_TERMINAL_EVENTS``. Nothing in this file adds a word, and
   a test asserts that it cannot: the derived set is compared against the Literal every time.

Terminal -> terminal deliberately stays allowed (``completed`` -> ``failed`` is how a late
failure survives an optimistic completion), which is also what the store did before R250.
"""
from __future__ import annotations

import logging
from typing import get_args

import pytest

from app.agents.contracts import AgentResult
from app.common.stage_timing import REQUEST_TERMINAL_EVENTS
from app.storage.persistence import PostgresPersistenceAdapter
from app.trace import durability
from app.trace.lifecycle import (
    REFUSAL_TERMINAL_REGRESSION,
    REFUSAL_UNREGISTERED_STATUS,
    RUN_OPEN_STATUSES,
    RUN_STATUSES,
    RUN_TERMINAL_EVENT_TYPES,
    RUN_TERMINAL_STATUSES,
    resolve_run_status,
    terminal_verdict,
)
from app.trace.projections import project_run, run_id_for
from app.trace.store import TraceStore
from tests._r250_fake_postgres import FakePostgres
from tests._r250_run_fixture import emit_full_run

UNREGISTERED = ["succeeded", "done", "ok", "finished", "COMPLETED", "completed ", "", None, 0, "success"]


@pytest.fixture(autouse=True)
def clean_ledger():
    durability.reset_durability_ledger()
    yield
    durability.reset_durability_ledger()


def _store(tmp_path, engine=None):
    engine = engine or FakePostgres()
    store = TraceStore(
        tmp_path / "fallback.jsonl", persistence=PostgresPersistenceAdapter(engine.connection_factory)
    )
    return store, engine


# ------------------------------------------------------------------ the vocabulary itself


def test_the_vocabulary_is_derived_from_the_ratified_agent_status_literal():
    literal = set(get_args(AgentResult.model_fields["status"].annotation))
    assert literal == {
        "success", "partial", "failed", "rejected", "timeout", "cancelled",
        "model_unavailable", "retrieval_unavailable",
    }
    # completed is the fold both records.py:34 and orchestrator.py:1066 already apply.
    assert set(RUN_TERMINAL_STATUSES) == (literal - {"success", "partial"}) | {"completed"}
    assert set(RUN_STATUSES) == set(RUN_TERMINAL_STATUSES) | set(RUN_OPEN_STATUSES)
    assert RUN_TERMINAL_EVENT_TYPES == set(REQUEST_TERMINAL_EVENTS)


@pytest.mark.parametrize("word", UNREGISTERED)
def test_no_unregistered_word_can_be_written(word):
    status, refusal = resolve_run_status(
        run_id="r:orchestrator", current_status="running", event_type="request.completed",
        event_status=word,
    )
    assert status in RUN_STATUSES, status
    if str(word or "") not in RUN_STATUSES:
        assert refusal == REFUSAL_UNREGISTERED_STATUS
    assert status != "succeeded"


def test_a_finished_run_cannot_be_walked_back_to_running():
    status, refusal = resolve_run_status(
        run_id="r:orchestrator", current_status="completed", event_type="step.started",
        event_status="running",
    )
    assert (status, refusal) == ("completed", REFUSAL_TERMINAL_REGRESSION)

    cancelled, reason = resolve_run_status(
        run_id="r:orchestrator", current_status="cancelled", event_type="request.started",
        event_status="started",
    )
    assert (cancelled, reason) == ("cancelled", REFUSAL_TERMINAL_REGRESSION)


def test_a_later_terminal_verdict_still_replaces_an_optimistic_one():
    """The one transition that must stay open: an optimistic completed loses to a real failure."""
    status, refusal = resolve_run_status(
        run_id="r:orchestrator", current_status="completed", event_type="request.failed",
        event_status="failed",
    )
    assert (status, refusal) == ("failed", "")
    assert durability.durability_status()["illegal_status_transitions"] == 0


# --------------------------------------------------------------------- through the store


def test_a_regression_attempt_leaves_the_row_alone_and_is_counted(tmp_path, caplog):
    store, engine = _store(tmp_path)
    trace = "r250-terminal-honest"
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)
    run_id = written["run_id"]
    assert engine.rows("agent_runs")[run_id]["status"] == "completed"
    before = dict(engine.rows("agent_runs")[run_id])

    with caplog.at_level(logging.ERROR, logger="enterprise_brain"):
        store.record_event(
            trace_id=trace, request_id=f"{trace}:req", task_id=f"{trace}:task",
            event_type="step.started", status="running",
            payload={"owner_id": "owner:" + trace, "step_id": f"{trace}:worker:late",
                     "worker": "late", "sequence": 9},
        )

    after = engine.rows("agent_runs")[run_id]
    assert after["status"] == "completed", after
    assert after["completed_at"] == before["completed_at"]
    ledger = durability.durability_status()
    assert ledger["illegal_status_transitions"] == 1
    assert ledger["fallback_by_reason"]["illegal_run_status_transition"] == 1
    assert "not a permitted transition" in caplog.text, caplog.text
    assert run_id in caplog.text


def test_an_unregistered_literal_never_reaches_the_table(tmp_path):
    store, engine = _store(tmp_path)
    trace = "r250-unregistered-word"
    owner = "owner:" + trace
    store.record_event(trace_id=trace, request_id="r", task_id="k",
                       event_type="request.started", status="started", payload={"owner_id": owner})

    store.record_event(trace_id=trace, request_id="r", task_id="k",
                       event_type="request.completed", status="succeeded", payload={"owner_id": owner})

    row = engine.rows("agent_runs")[run_id_for(trace)]
    assert row["status"] == "started", row
    assert row["status"] in RUN_STATUSES
    assert row["completed_at"] is None, "a refused verdict must not stamp a completion time"
    assert durability.durability_status()["illegal_status_transitions"] == 1


def test_a_projected_record_always_holds_a_registered_status():
    event = {
        "trace_id": "t", "request_id": "r", "task_id": "k", "sequence": 1,
        "timestamp": "2026-09-25T00:00:00+00:00", "event_type": "request.completed",
        "status": "lying", "payload": {},
    }
    for current in ({}, {"status": "completed"}, {"status": "running"}):
        projection = project_run(event, "owner-1", current)
        assert projection.values["status"] in RUN_STATUSES, current
        assert projection.notes["status_refusal"] == REFUSAL_UNREGISTERED_STATUS


def test_a_failed_run_reports_the_failure_and_its_timestamp(tmp_path):
    store, _engine = _store(tmp_path)
    trace = "r250-failed-run"
    owner = "owner:" + trace
    store.record_event(trace_id=trace, request_id="r", task_id="k",
                       event_type="request.started", status="started", payload={"owner_id": owner})
    store.record_event(trace_id=trace, request_id="r", task_id="k",
                       event_type="request.failed", status="failed",
                       payload={"owner_id": owner, "error_code": "model_unavailable"})

    readout = store.read_run(run_id_for(trace))

    assert readout["terminal"] == {
        "status": "failed",
        "status_is_terminal": True,
        "status_is_registered": True,
        "completed_at_is_set": True,
        "error_code": "model_unavailable",
    }
    assert readout["run"]["status"] == "failed"


def test_a_verdict_without_a_terminal_event_is_reported_as_such(tmp_path):
    """records.py folds an AgentResult onto the run row without ending the request."""
    store, _engine = _store(tmp_path)
    trace = "r250-verdict-without-event"
    store.record_event(trace_id=trace, request_id="r", task_id="k",
                       event_type="agent.result.recorded", status="completed",
                       payload={"owner_id": "owner:" + trace})

    readout = store.read_run(run_id_for(trace))

    assert readout["terminal"]["status"] == "completed"
    assert readout["terminal"]["completed_at_is_set"] is False, (
        "the store never saw request.completed, so the readout cannot imply it did"
    )
    assert durability.durability_status()["illegal_status_transitions"] == 0


def test_terminal_verdict_needs_no_row_to_answer_honestly():
    assert terminal_verdict(None)["status"] == ""
    assert terminal_verdict(None)["status_is_terminal"] is False
    assert terminal_verdict({"status": "cancelled", "completed_at": "x"})["status_is_terminal"] is True
    assert terminal_verdict({"status": "half_done", "completed_at": None})["status_is_registered"] is False
