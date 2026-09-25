"""The column contract between the trace layer and the six PostgreSQL tables.

``migrations/0002_execution_data_lineage.sql`` created ``agent_runs``, ``agent_steps``,
``tool_calls``, ``model_calls``, ``retrieval_traces`` and ``trace_events``; R250 makes them
the source of truth for a trace. A projection that writes a field the table does not have
would be rejected by PostgreSQL at runtime, and a projection that quietly omits a field
leaves a NULL that the next read reports as "never happened". Both are the same class of
bug, so this module states the column set once and every projection is sealed against it:
``require_columns`` refuses a record whose key set is not exactly the declared column set,
in either direction.

``tests/test_r250_trace_column_alignment.py`` pins this list twice more: against the
checked-in DDL and against ``app/storage/persistence._TABLES``, the adapter that actually
builds the SQL. Three copies, one truth, red the moment any of them drifts.
"""
from __future__ import annotations

import re

#: The six tables a trace is projected onto, in the order the run readout reports them.
TRACE_TABLES = (
    "trace_events",
    "agent_runs",
    "agent_steps",
    "tool_calls",
    "model_calls",
    "retrieval_traces",
)

#: Column sets exactly as ``0002_execution_data_lineage.sql`` declares them.
TRACE_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "trace_events": (
        "event_id",
        "trace_id",
        "request_id",
        "task_id",
        "sequence",
        "event_type",
        "status",
        "owner_id",
        "payload",
        "created_at",
    ),
    "agent_runs": (
        "agent_run_id",
        "owner_id",
        "request_id",
        "trace_id",
        "task_id",
        "session_id",
        "worker",
        "status",
        "started_at",
        "completed_at",
        "error_code",
        "metadata",
    ),
    "agent_steps": (
        "agent_step_id",
        "agent_run_id",
        "owner_id",
        "step_id",
        "worker",
        "status",
        "sequence",
        "started_at",
        "completed_at",
        "error_code",
        "input_summary",
        "output_summary",
    ),
    "tool_calls": (
        "tool_call_id",
        "agent_run_id",
        "agent_step_id",
        "owner_id",
        "tool_name",
        "status",
        "request_id",
        "started_at",
        "completed_at",
        "error_code",
        "arguments",
        "result_summary",
    ),
    "model_calls": (
        "model_call_id",
        "agent_run_id",
        "agent_step_id",
        "owner_id",
        "provider",
        "model_name",
        "status",
        "request_id",
        "started_at",
        "first_token_at",
        "completed_at",
        "queue_wait_ms",
        "duration_ms",
        "input_tokens",
        "output_tokens",
        "error_code",
        "metadata",
    ),
    "retrieval_traces": (
        "retrieval_trace_id",
        "agent_run_id",
        "owner_id",
        "request_id",
        "trace_id",
        "query_hash",
        "index_version_id",
        "filter_snapshot",
        "result_summary",
        "status",
        "created_at",
    ),
}

#: Primary key of each table, which is also the id the adapter upserts on.
TRACE_ID_COLUMNS: dict[str, str] = {
    table: columns[0] for table, columns in TRACE_TABLE_COLUMNS.items()
}

#: JSONB columns: absent means an empty object, never a NULL, because the DDL defaults
#: them to ``'{}'::jsonb`` and a NULL would read back as "this summary never existed".
TRACE_JSON_COLUMNS = frozenset(
    {
        "payload",
        "metadata",
        "input_summary",
        "output_summary",
        "arguments",
        "result_summary",
        "filter_snapshot",
    }
)

#: Tables whose rows hang off a run, so the readout can fetch a whole run by one key.
TRACE_RUN_CHILD_TABLES = ("agent_steps", "tool_calls", "model_calls", "retrieval_traces")

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")

#: The only predicate shape the reader builds: one identifier column compared to a bind
#: parameter. SQL text never contains a value.
_WHERE = re.compile(r"^[a-z_][a-z0-9_]* = %s$")


class TraceSchemaError(ValueError):
    """A trace record does not line up with the table it is written to."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def declared_columns(table: str) -> tuple[str, ...]:
    """The columns one trace table is allowed to receive, or a named refusal."""
    try:
        return TRACE_TABLE_COLUMNS[table]
    except KeyError:
        raise TraceSchemaError(
            "unsupported_trace_table",
            f"{table!r} is not one of the six trace tables: {', '.join(TRACE_TABLES)}",
        ) from None


def require_columns(table: str, keys: object) -> None:
    """Refuse a record whose key set is not exactly the declared column set."""
    columns = set(declared_columns(table))
    given = set(keys or ())
    if not all(_IDENTIFIER.match(str(key)) for key in given):
        raise TraceSchemaError(
            "invalid_column_name",
            f"{table} received a key that is not a column identifier: {sorted(map(str, given))}",
        )
    if given == columns:
        return
    raise TraceSchemaError(
        "trace_column_mismatch",
        (
            f"{table} projection is out of step with the table: "
            f"missing={sorted(columns - given, key=str)} extra={sorted(given - columns, key=str)}"
        ),
    )


def is_identifier(name: str) -> bool:
    """Whether a name is safe to place into SQL text; everything else is a bug or an attack."""
    return bool(_IDENTIFIER.match(str(name or "")))
