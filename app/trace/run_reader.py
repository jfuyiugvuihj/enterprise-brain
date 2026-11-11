"""Read a trace back out of the six PostgreSQL tables.

R250's read path, and the reason the local journal stopped being the source of truth: a
second API process, a worker, or a restarted container could not see what another process
appended. Everything here reads the tables the migrations created, through the *same*
connection factory the write path uses, so there is no second database to misconfigure --
``app.storage.persistence.PostgresPersistenceAdapter`` owns the credentials, this module
only asks it for connections.

Two rules hold the boundary:

* every column list comes from ``app.trace.schema``, and every name is checked as an
  identifier before it reaches SQL text -- there is no user-controlled identifier here, and
  that stays true;
* a database that cannot answer raises ``TraceDatabaseUnavailable``. A caller that then
  reads the fallback journal has to say so (``app.trace.durability``), because "empty" and
  "unreachable" are different answers to an operator's question.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Callable

from app.trace.schema import (
    TRACE_ID_COLUMNS,
    TRACE_RUN_CHILD_TABLES,
    TRACE_TABLE_COLUMNS,
    declared_columns,
    is_identifier,
)


#: How one table's rows are ordered inside a readout. Deterministic, so two reads of the
#: same run return the same document.
_ORDERINGS: dict[str, str] = {
    "trace_events": "sequence ASC",
    "agent_runs": "started_at ASC",
    "agent_steps": "sequence ASC",
    "tool_calls": "started_at ASC, tool_call_id ASC",
    "model_calls": "started_at ASC, model_call_id ASC",
    "retrieval_traces": "created_at ASC, retrieval_trace_id ASC",
}


#: The only predicate shape this module builds: one identifier column compared to a bind
#: parameter. No value, and no caller-supplied fragment, ever reaches SQL text.
_WHERE = re.compile(r"^[a-z_][a-z0-9_]* = %s$")


class TraceDatabaseUnavailable(RuntimeError):
    """PostgreSQL could not answer; anything read after this came from the fallback."""

    def __init__(self, message: str, *, reason: str = "postgres_read_failed"):
        super().__init__(message)
        self.reason = reason


def database_for(adapter: Any) -> "TraceDatabase | None":
    """Wrap an adapter's PostgreSQL connection factory, when it has one.

    Only ``PostgresPersistenceAdapter`` exposes ``connection_factory``. A JSON adapter
    deliberately returns ``None`` here: it is a durable journal on one host, not the six
    tables, and pretending otherwise would let a notebook box report "trace is in
    PostgreSQL".
    """
    factory = getattr(adapter, "connection_factory", None)
    if not callable(factory):
        return None
    return TraceDatabase(factory)


def _normalized(value: Any) -> Any:
    """Keep the readout in the same shapes the trace events already use."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _select(table: str, where: str) -> str:
    columns = declared_columns(table)
    if not all(is_identifier(column) for column in columns) or not is_identifier(table):
        raise TraceDatabaseUnavailable(f"{table} is not a safe identifier", reason="unsafe_identifier")
    if not _WHERE.match(str(where or "")):
        # Every predicate this module builds is "<column> = %s"; anything else is either a
        # bug or an injection attempt, and neither belongs in SQL text.
        raise TraceDatabaseUnavailable(f"{where!r} is not a safe predicate", reason="unsafe_identifier")
    ordering = _ORDERINGS.get(table, f"{columns[0]} ASC")
    return f"SELECT {', '.join(columns)} FROM {table} WHERE {where} ORDER BY {ordering}"


class TraceDatabase:
    """The six trace tables, read-only."""

    def __init__(self, connection_factory: Callable[[], Any], *, describe: str = "postgres"):
        self.connection_factory = connection_factory
        self.describe = describe

    # ------------------------------------------------------------------ primitives

    def _rows(self, sql: str, params: tuple[Any, ...], table: str) -> list[dict[str, Any]]:
        columns = declared_columns(table)
        connection = None
        try:
            connection = self.connection_factory()
            rows = connection.execute(sql, params).fetchall()
        except Exception as exc:  # a driver or connection error is an unavailable database
            raise TraceDatabaseUnavailable(
                f"{table} read failed: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            if connection is not None and hasattr(connection, "close"):
                try:
                    connection.close()
                except Exception:
                    pass
        return [{column: _normalized(value) for column, value in zip(columns, row)} for row in rows]

    def _one(self, sql: str, params: tuple[Any, ...]) -> Any:
        connection = None
        try:
            connection = self.connection_factory()
            row = connection.execute(sql, params).fetchone()
        except Exception as exc:
            raise TraceDatabaseUnavailable(
                f"trace read failed: {type(exc).__name__}: {exc}"
            ) from exc
        finally:
            if connection is not None and hasattr(connection, "close"):
                try:
                    connection.close()
                except Exception:
                    pass
        return row[0] if row else None

    # -------------------------------------------------------------------- readers

    def max_sequence(self, trace_id: str) -> int:
        """The highest event sequence PostgreSQL holds for one trace.

        Sequence allocation has to come from the same ledger the rows live in: two API
        processes reading one local file was exactly how duplicate event ids appeared.
        """
        value = self._one(
            "SELECT COALESCE(MAX(sequence), 0) FROM trace_events WHERE trace_id = %s",
            (trace_id,),
        )
        return int(value or 0)

    def fetch_events(self, trace_id: str) -> list[dict[str, Any]]:
        """Every ``trace_events`` row of one trace, in the event shape the writer speaks."""
        rows = self._rows(
            _select("trace_events", "trace_id = %s"), (trace_id,), "trace_events"
        )
        return [self._as_event(row) for row in rows]

    def fetch_table(self, table: str, where: str, value: str) -> list[dict[str, Any]]:
        return self._rows(_select(table, where), (value,), table)

    def read_run_rows(self, run_id: str) -> dict[str, Any]:
        """The whole run: the row, its children, and the events that produced them."""
        run_id = str(run_id or "").strip()
        if not run_id:
            raise TraceDatabaseUnavailable("run_id is required", reason="validation_error")
        run_rows = self.fetch_table("agent_runs", "agent_run_id = %s", run_id)
        tables: dict[str, list[dict[str, Any]]] = {
            table: self.fetch_table(table, "agent_run_id = %s", run_id)
            for table in TRACE_RUN_CHILD_TABLES
        }
        events: list[dict[str, Any]] = []
        if run_rows:
            events = self.fetch_events(str(run_rows[0].get("trace_id") or ""))
        return {
            "run": run_rows[0] if run_rows else None,
            "tables": tables,
            "events": events,
        }

    @staticmethod
    def _as_event(row: dict[str, Any]) -> dict[str, Any]:
        """Map a ``trace_events`` row back onto the event dict the store produced.

        Same keys as the local journal, because the consumers of ``replay`` -- the stage
        latency report and ``/api/v1/traces/{trace_id}`` -- read those keys, and R250 is
        not a licence to change a contract they depend on.
        """
        return {
            "trace_id": row.get("trace_id"),
            "request_id": row.get("request_id"),
            "task_id": row.get("task_id"),
            "sequence": row.get("sequence"),
            "timestamp": row.get("created_at"),
            "event_type": row.get("event_type"),
            "status": row.get("status"),
            "payload": row.get("payload") if isinstance(row.get("payload"), dict) else {},
        }


def id_column(table: str) -> str:
    return TRACE_ID_COLUMNS[table]
