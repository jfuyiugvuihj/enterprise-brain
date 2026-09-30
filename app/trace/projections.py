"""Project one trace event onto the six execution tables, without a database in sight.

R250's write path needs one place that decides what a row looks like; the store decides
*when* to write it and which backend takes it. Keeping the decision here buys two things:

* the local fallback journal and PostgreSQL are built from the same bytes, so a run read
  back after a degraded window has the same fields as one read back from ``agent_runs``;
* the column contract (``app/trace/schema.py``) is checked before anything goes over the
  wire, in either direction, so a field that the table does not have is a named refusal
  instead of a database error in the middle of a customer request.

Every builder returns a complete record: all columns of its table, merged with the row
that is already there (``current``) exactly where the previous implementation merged. Two
details are deliberate. ``completed`` clears ``error_code`` on a step, because a step that
finished does not keep an error from an earlier attempt. And a JSON column falls back to
``{}`` rather than ``None``, because the DDL defaults those columns to an empty object and
a NULL would read back as "this summary never existed".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.trace.schema import TRACE_JSON_COLUMNS, TRACE_TABLE_COLUMNS, require_columns

#: Event types that carry one worker step, in either direction.
STEP_EVENT_TYPES = frozenset({"step.started", "step.finished"})

#: Event types that carry one model or tool span.
SPAN_EVENT_TYPES = {
    "model_calls": frozenset({"model.started", "model.finished"}),
    "tool_calls": frozenset({"tool_call.started", "tool_call.finished"}),
}

#: The lifecycle event that folds a worker result into the run row.
TOOL_COMPLETED_EVENT = "tool.completed"


#: The address book of a journal line whose number the tables never confirmed (R263). Such a
#: line is replayed under ``{trace_id}:u{token}``, an id no event addressed by
#: ``(trace_id, sequence)`` can ever produce, so its primary key cannot alias the row another
#: event holds. ``app/trace/store.py`` decides when a line belongs in this book.
PROVISIONAL_ID_PREFIX = "u"


def event_row_id(event: dict[str, Any]) -> str:
    """The ``trace_events`` primary key an event is addressed by."""
    return f"{event['trace_id']}:{event['sequence']}"


def provisional_event_id(trace_id: str, token: str) -> str:
    """The ``trace_events`` primary key of one line whose number is not confirmed."""
    return f"{trace_id}:{PROVISIONAL_ID_PREFIX}{token}"


@dataclass(frozen=True)
class Projection:
    """One row a trace event asks for: which table, which key, which columns."""

    collection: str
    record_id: str
    values: dict[str, Any] = field(default_factory=dict)
    #: Carried for the caller (a refused status transition, say); never a table column,
    #: which is why it lives beside ``values`` instead of inside it.
    notes: dict[str, Any] = field(default_factory=dict)

    def seal(self) -> "Projection":
        """Check the record against the table's column set, and return it unchanged."""
        require_columns(self.collection, self.values)
        return self


def run_id_for(trace_id: str) -> str:
    """The orchestrator run a trace belongs to -- the id an operator queries by."""
    return f"{str(trace_id or '').strip()}:orchestrator"


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _summary(value: Any) -> dict[str, Any]:
    """A JSON summary column: an object, never NULL."""
    return value if isinstance(value, dict) else {}


def _merge_json(incoming: Any, current: Any) -> dict[str, Any]:
    if isinstance(incoming, dict):
        return incoming
    if isinstance(current, dict):
        return current
    return {}


def _metadata_current(current: dict[str, Any]) -> dict[str, Any]:
    metadata = current.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def project_event_row(
    event: dict[str, Any], owner_id: str, *, event_id: str | None = None
) -> Projection:
    """The ``trace_events`` row: the event as recorded, redacted upstream.

    ``event_id`` names the address the row is stored at, and only R263's settlement sweep
    passes it: a fallback line written while PostgreSQL would not answer ``MAX(sequence)`` is
    re-numbered from the tables when it is replayed and stored under its own token id, so a
    number that turned out to be taken is refused by ``UNIQUE (trace_id, sequence)`` instead
    of landing on ``ON CONFLICT (event_id) DO UPDATE`` over somebody else's row.
    """
    record_id = str(event_id or event_row_id(event))
    return Projection(
        "trace_events",
        record_id,
        {
            "event_id": record_id,
            "trace_id": event["trace_id"],
            "request_id": event["request_id"],
            "task_id": event["task_id"],
            "sequence": event["sequence"],
            "event_type": event["event_type"],
            "status": event["status"],
            "owner_id": owner_id,
            "payload": event["payload"],
            "created_at": event["timestamp"],
        },
    )


def project_run(event: dict[str, Any], owner_id: str, current: dict[str, Any]) -> Projection:
    """The ``agent_runs`` row, refreshed by every lifecycle event of one trace."""
    from app.trace.lifecycle import RUN_TERMINAL_EVENT_TYPES, resolve_run_status

    payload = event["payload"]
    trace_id = event["trace_id"]
    record_id = run_id_for(trace_id)
    current_metadata = _metadata_current(current)
    terminal_event = str(event["event_type"]) in RUN_TERMINAL_EVENT_TYPES
    status, refusal = resolve_run_status(
        run_id=record_id,
        current_status=current.get("status"),
        event_type=event["event_type"],
        event_status=event["status"],
    )
    error_code = current.get("error_code")
    if str(event["event_type"]).startswith("request."):
        error_code = payload.get("error_code")
    return Projection(
        "agent_runs",
        record_id,
        {
            "agent_run_id": record_id,
            "owner_id": owner_id,
            "request_id": event["request_id"],
            "trace_id": trace_id,
            "task_id": event["task_id"],
            "session_id": payload.get("session_id") or current.get("session_id"),
            "worker": "orchestrator",
            "status": status,
            "started_at": current.get("started_at") or event["timestamp"],
            # A refused verdict does not get to stamp a completion time either.
            "completed_at": (
                event["timestamp"] if terminal_event and not refusal else current.get("completed_at")
            ),
            "error_code": error_code,
            "metadata": {
                "worker_count": payload.get("worker_count", current_metadata.get("worker_count")),
                "has_final_answer": payload.get(
                    "has_final_answer", current_metadata.get("has_final_answer")
                ),
                "agent_result": payload.get("agent_result") or current_metadata.get("agent_result"),
                "entry_point": payload.get("entry_point") or current_metadata.get("entry_point"),
            },
        },
        {
            "status_refusal": refusal,
            "requested_status": event["status"],
            "current_status": current.get("status"),
        },
    )


def project_step(event: dict[str, Any], owner_id: str, current: dict[str, Any]) -> Projection:
    """One ``step.started`` / ``step.finished`` pair folded onto a single step row."""
    payload = event["payload"]
    trace_id = event["trace_id"]
    step_id = str(payload.get("step_id") or f"{trace_id}:{event['sequence']}")
    status = payload.get("status") or event["status"]
    return Projection(
        "agent_steps",
        step_id,
        {
            "agent_step_id": step_id,
            "agent_run_id": payload.get("agent_run_id") or run_id_for(trace_id),
            "owner_id": owner_id,
            "step_id": step_id,
            "worker": payload.get("worker") or current.get("worker") or "",
            "status": status,
            "sequence": payload.get("sequence") or current.get("sequence") or event["sequence"],
            "started_at": payload.get("started_at")
            or current.get("started_at")
            or event["timestamp"],
            # A step that reports a terminal status gets a terminal timestamp even when the
            # emitter did not send one: ``step.finished`` carries only ``step_id`` / ``worker``
            # / ``summary`` in ``app/agents/orchestrator.py:712``, and a step recorded as
            # completed with no completion time would be indistinguishable from one still
            # running. ``completed_at`` stays NULL for an open step, which is the honest case.
            "completed_at": (
                payload.get("completed_at")
                or current.get("completed_at")
                or (event["timestamp"] if status in {"completed", "success"} else None)
            ),
            "error_code": (
                None if status in {"completed", "success"} else payload.get("error_code")
            ),
            "input_summary": _merge_json(payload.get("input_summary"), current.get("input_summary")),
            "output_summary": _merge_json(payload.get("summary"), current.get("output_summary")),
        },
    )


def project_tool_completed(
    event: dict[str, Any], owner_id: str
) -> list[Projection]:
    """The legacy ``tool.completed`` boundary: one step row and one tool row."""
    payload = event["payload"]
    trace_id = event["trace_id"]
    step_id = f"{trace_id}:{event['sequence']}"
    record_id = run_id_for(trace_id)
    worker = str(payload.get("worker") or "unknown")
    result_summary = {"result_length": payload.get("result_length", 0)}
    return [
        Projection(
            "agent_steps",
            step_id,
            {
                "agent_step_id": step_id,
                "agent_run_id": record_id,
                "owner_id": owner_id,
                "step_id": step_id,
                "worker": worker,
                "status": event["status"],
                "sequence": event["sequence"],
                "started_at": event["timestamp"],
                "completed_at": event["timestamp"],
                "error_code": None,
                "input_summary": {},
                "output_summary": result_summary,
            },
        ),
        Projection(
            "tool_calls",
            f"{step_id}:{worker}",
            {
                "tool_call_id": f"{step_id}:{worker}",
                "agent_run_id": record_id,
                "agent_step_id": step_id,
                "owner_id": owner_id,
                "tool_name": worker,
                "status": event["status"],
                "request_id": event["request_id"],
                "started_at": event["timestamp"],
                "completed_at": event["timestamp"],
                "error_code": None,
                "arguments": {},
                "result_summary": result_summary,
            },
        ),
    ]


def project_span(
    event: dict[str, Any], owner_id: str, current: dict[str, Any], collection: str
) -> Projection | None:
    """Project a model or tool span onto its own execution row."""
    payload = event["payload"]
    record_id = str(payload.get("record_id") or "").strip()
    if not record_id:
        return None
    trace_id = event["trace_id"]
    summary = _summary(payload.get("summary"))
    values: dict[str, Any] = {
        **{column: None for column in TRACE_TABLE_COLUMNS[collection]},
        _id_column(collection): record_id,
        "owner_id": owner_id,
        "request_id": event["request_id"],
        "agent_run_id": payload.get("agent_run_id") or run_id_for(trace_id),
        "agent_step_id": payload.get("agent_step_id") or current.get("agent_step_id"),
        "status": payload.get("status") or event["status"],
        "started_at": payload.get("started_at") or current.get("started_at") or event["timestamp"],
        "completed_at": payload.get("completed_at") or current.get("completed_at"),
        "error_code": payload.get("error_code") or current.get("error_code"),
    }
    if collection == "model_calls":
        values.update(
            {
                "provider": payload.get("provider") or current.get("provider") or "",
                "model_name": payload.get("model_name") or current.get("model_name") or "",
                "first_token_at": payload.get("first_token_at") or current.get("first_token_at"),
                "queue_wait_ms": _first(payload.get("queue_wait_ms"), current.get("queue_wait_ms")),
                "duration_ms": _first(payload.get("duration_ms"), current.get("duration_ms")),
                "input_tokens": _first(summary.get("input_tokens"), current.get("input_tokens")),
                "output_tokens": _first(summary.get("output_tokens"), current.get("output_tokens")),
                # 0018. A key the summary does not carry stays NULL, because spans.py drops
                # it when the reply reported nothing; _first keeps a reported 0 as 0.
                "cached_tokens": _first(summary.get("cached_tokens"), current.get("cached_tokens")),
                "metadata": {"worker": payload.get("worker") or current.get("worker")},
            }
        )
    else:
        values.update(
            {
                "tool_name": payload.get("tool_name") or current.get("tool_name") or "",
                "arguments": _merge_json(payload.get("arguments"), current.get("arguments")),
                "result_summary": _merge_json(summary, current.get("result_summary")),
            }
        )
    return Projection(collection, record_id, values)


def project_retrieval(event: dict[str, Any], owner_id: str) -> Projection:
    """One ``retrieval.completed`` event onto ``retrieval_traces``."""
    payload = event["payload"]
    trace_id = event["trace_id"]
    record_id = f"{trace_id}:{event['sequence']}"
    hits = payload.get("hits") or []
    return Projection(
        "retrieval_traces",
        record_id,
        {
            "retrieval_trace_id": record_id,
            "agent_run_id": payload.get("agent_run_id") or run_id_for(trace_id),
            "owner_id": owner_id,
            "request_id": event["request_id"],
            "trace_id": trace_id,
            "query_hash": str(payload.get("query_hash") or ""),
            "index_version_id": payload.get("index_version_id"),
            "filter_snapshot": _summary(payload.get("filters")),
            "result_summary": {"hit_count": len(hits)},
            "status": event["status"],
            "created_at": event["timestamp"],
        },
    )


def _id_column(collection: str) -> str:
    return TRACE_TABLE_COLUMNS[collection][0]


def project_event(
    event: dict[str, Any],
    *,
    owner_id: str,
    fetch: Callable[[str, str], dict[str, Any] | None],
) -> list[Projection]:
    """Every row one event asks for, in dependency order: run first, children after.

    ``agent_steps`` and the two span tables carry FKs onto ``agent_runs``, so the order is
    not cosmetic -- a child written first would be rejected by the database.
    """
    event_type = str(event["event_type"])
    projections = [project_run(event, owner_id, fetch("agent_runs", run_id_for(event["trace_id"])) or {})]

    if event_type == TOOL_COMPLETED_EVENT:
        projections.extend(project_tool_completed(event, owner_id))

    if event_type in STEP_EVENT_TYPES:
        step_id = str(event["payload"].get("step_id") or f"{event['trace_id']}:{event['sequence']}")
        projections.append(project_step(event, owner_id, fetch("agent_steps", step_id) or {}))

    for collection, types in SPAN_EVENT_TYPES.items():
        if event_type in types:
            record_id = str(event["payload"].get("record_id") or "").strip()
            span = project_span(event, owner_id, fetch(collection, record_id) or {}, collection)
            if span is not None:
                projections.append(span)

    if event_type == "retrieval.completed":
        projections.append(project_retrieval(event, owner_id))

    for projection in projections:
        projection.seal()
    return projections


def json_columns(collection: str) -> frozenset[str]:
    """Which columns of a table are JSONB, so a fallback row is padded the same way."""
    return frozenset(
        column for column in TRACE_TABLE_COLUMNS[collection] if column in TRACE_JSON_COLUMNS
    )
