"""Assemble the readout an administrator asks for: one run, its steps, its calls.

Two producers feed this module and they must not produce two shapes. PostgreSQL is the
source of truth (``run_reader.TraceDatabase.read_run_rows``); the local fallback journal is
replayed through the *same* projections (``fold_events``), so a run read back after a
degraded window carries the same fields as one read back from ``agent_runs``. What differs
is ``source``, which is the point of R250's second requirement: an operator has to be able
to tell the two apart without opening a filesystem.

The ``joined`` block is deliberately blunt. A child row that does not hang off this run, or
a tool call whose ``agent_step_id`` matches no step of this run, is reported as a number
instead of being quietly dropped -- a run whose three sections do not stitch together is a
trace bug, and the readout is where somebody should find out.
"""
from __future__ import annotations

from typing import Any

from app.trace.durability import LOCAL_FALLBACK_NAME, durability_status
from app.trace.lifecycle import terminal_verdict
from app.trace.projections import project_event, project_event_row
from app.trace.schema import TRACE_TABLE_COLUMNS

#: Every table the readout reports, in the order the sections appear.
READOUT_TABLES = ("trace_events", "agent_steps", "tool_calls", "model_calls", "retrieval_traces")

#: The suffix that turns a trace id into the orchestrator run of that trace.
RUN_ID_SUFFIX = ":orchestrator"


def trace_id_from_run_id(run_id: str) -> str:
    """The trace a run id belongs to, or the id itself when it carries no suffix."""
    run_id = str(run_id or "").strip()
    if run_id.endswith(RUN_ID_SUFFIX):
        return run_id[: -len(RUN_ID_SUFFIX)]
    return run_id


def empty_bundle() -> dict[str, Any]:
    return {"run": None, "tables": {table: [] for table in READOUT_TABLES}, "events": []}


def fold_events(events: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    """Rebuild one run's rows from recorded events, with no database in the loop.

    This is the fallback read path: the local journal holds events, the tables hold rows,
    and the only honest way to serve a run from events is to run the projection again.
    Rows are keyed by their primary key, so replaying an event twice lands once.
    """
    rows: dict[str, dict[str, Any]] = {table: {} for table in TRACE_TABLE_COLUMNS}

    def fetch(collection: str, record_id: str) -> dict[str, Any] | None:
        return rows[collection].get(record_id)

    ordered = sorted(events or [], key=lambda event: int(event.get("sequence") or 0))
    for event in ordered:
        owner_id = str((event.get("payload") or {}).get("owner_id") or "").strip()
        if not owner_id:
            # The write path refused these rows for the same reason: an invented owner
            # would attribute someone else's run to a principal that never saw it.
            continue
        writes = [project_event_row(event, owner_id)] + list(
            project_event(event, owner_id=owner_id, fetch=fetch)
        )
        for projection in writes:
            rows[projection.collection][projection.record_id] = dict(projection.values)

    table_rows = {
        table: [
            row
            for row in rows[table].values()
            if str(row.get("agent_run_id") or "") == run_id or (
                table == "trace_events" and str(row.get("trace_id") or "") == trace_id_from_run_id(run_id)
            )
        ]
        for table in READOUT_TABLES
    }
    events_out = [
        {
            "trace_id": row.get("trace_id"),
            "request_id": row.get("request_id"),
            "task_id": row.get("task_id"),
            "sequence": row.get("sequence"),
            "timestamp": row.get("created_at"),
            "event_type": row.get("event_type"),
            "status": row.get("status"),
            "payload": row.get("payload") if isinstance(row.get("payload"), dict) else {},
        }
        for row in sorted(table_rows["trace_events"], key=lambda row: int(row.get("sequence") or 0))
    ]
    return {
        "run": rows["agent_runs"].get(run_id),
        "tables": table_rows,
        "events": events_out,
    }


def _step_keys(steps: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for step in steps:
        for field in ("step_id", "agent_step_id"):
            value = str(step.get(field) or "")
            if value:
                keys.add(value)
    return keys


def assemble_run_readout(
    run_id: str,
    bundle: dict[str, Any] | None,
    *,
    source: str,
    requested_by: dict[str, Any] | None = None,
    durability_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The administrator's document for one run, with its durability named in the body."""
    run_id = str(run_id or "").strip()
    bundle = bundle or empty_bundle()
    run = bundle.get("run")
    tables = {
        table: list((bundle.get("tables") or {}).get(table) or []) for table in READOUT_TABLES
    }
    events = list(bundle.get("events") or [])
    steps = tables["agent_steps"]
    step_keys = _step_keys(steps)
    calls = {table: tables[table] for table in ("tool_calls", "model_calls")}

    joined = {
        "steps_belonging_to_run": sum(
            1 for step in steps if str(step.get("agent_run_id") or "") == run_id
        ),
        "calls_belonging_to_run": sum(
            1
            for rows in calls.values()
            for row in rows
            if str(row.get("agent_run_id") or "") == run_id
        ),
        "calls_linked_to_a_step": sum(
            1
            for rows in calls.values()
            for row in rows
            if str(row.get("agent_step_id") or "") in step_keys
        ),
        "orphan_calls": sum(
            1
            for rows in calls.values()
            for row in rows
            if str(row.get("agent_step_id") or "") and str(row.get("agent_step_id") or "") not in step_keys
        ),
        "events_for_this_trace": len(events),
    }

    return {
        "run_id": run_id,
        "trace_id": trace_id_from_run_id(run_id),
        "found": bool(run),
        "source": source,
        "fallback": source == LOCAL_FALLBACK_NAME,
        #: Where this particular document came from, which is not the same question as
        #: "which backend is configured": a configured PostgreSQL that is down for a minute
        #: answers from the journal, and the body has to say so.
        "answered_from": source,
        "requested_by": requested_by or {},
        "run": run,
        "terminal": terminal_verdict(run),
        "counts": {
            "agent_runs": 1 if run else 0,
            "agent_steps": len(steps),
            "tool_calls": len(tables["tool_calls"]),
            "model_calls": len(tables["model_calls"]),
            "retrieval_traces": len(tables["retrieval_traces"]),
            "trace_events": len(events),
        },
        "steps": steps,
        "tool_calls": tables["tool_calls"],
        "model_calls": tables["model_calls"],
        "retrieval_traces": tables["retrieval_traces"],
        "joined": joined,
        "durability": durability_block if durability_block is not None else durability_status(),
    }
