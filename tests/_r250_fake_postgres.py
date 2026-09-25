"""A PostgreSQL double strict enough to be evidence, not a stub that agrees to anything.

R250's judgement asks for a write-then-read round trip whose four sections line up, and the
full regression gate has no database. This module answers that by executing the SQL the real
``PostgresPersistenceAdapter`` builds and the real ``app.trace.run_reader.TraceDatabase``
builds, against dictionaries:

* an unrecognised statement raises instead of returning an empty list, so a change in SQL
  shape shows up as a red test rather than as a silent "no rows";
* the constraints the DDL actually has are enforced: ``NOT NULL`` on the identity and status
  columns, ``UNIQUE (trace_id, sequence)`` on ``trace_events``, and the
  ``agent_steps`` / ``tool_calls`` / ``model_calls`` / ``retrieval_traces`` foreign keys onto
  ``agent_runs`` -- which is why write ordering is tested here and not assumed;
* JSONB columns come back as objects and timestamp columns as aware datetimes, the same two
  shapes psycopg hands the reader.

This is not a database. It is a hermetic contract check; ``tests/test_r250_pg_trace_source
_of_truth.py`` runs the identical assertions against a real PostgreSQL when
``EB_PG_ACCEPTANCE_URL`` is exported.
"""
from __future__ import annotations

import json
import re
from typing import Any


#: Statements this double refuses to guess about.
_UNKNOWN = "unrecognised statement: {sql}"

_INSERT = re.compile(
    r"^INSERT INTO (?P<table>\w+) \((?P<columns>[^)]*)\) VALUES \((?P<placeholders>[^)]*)\) "
    r"ON CONFLICT \((?P<key>\w+)\) DO UPDATE SET (?P<assignments>.*)$",
    re.S,
)
_SELECT_WHERE = re.compile(
    r"^SELECT (?P<columns>.*) FROM (?P<table>\w+) WHERE (?P<column>\w+) = %s"
    r"(?: ORDER BY (?P<order>.*))?$",
    re.S,
)
_MAX_SEQUENCE = re.compile(
    r"^SELECT COALESCE\(MAX\(sequence\), 0\) FROM trace_events WHERE trace_id = %s$", re.S
)

#: Columns the checked-in DDL declares NOT NULL, grouped by table.
_NOT_NULL = {
    "trace_events": ("event_id", "trace_id", "request_id", "sequence", "event_type", "status", "owner_id"),
    "agent_runs": (
        "agent_run_id",
        "owner_id",
        "request_id",
        "trace_id",
        "task_id",
        "worker",
        "status",
        "started_at",
    ),
    "agent_steps": (
        "agent_step_id",
        "agent_run_id",
        "owner_id",
        "step_id",
        "worker",
        "status",
        "sequence",
    ),
    "tool_calls": ("tool_call_id", "owner_id", "tool_name", "status"),
    "model_calls": ("model_call_id", "owner_id", "provider", "model_name", "status"),
    "retrieval_traces": (
        "retrieval_trace_id",
        "agent_run_id",
        "owner_id",
        "trace_id",
        "query_hash",
        "status",
    ),
}

#: Child tables and the column that must point at an ``agent_runs`` row.
_FOREIGN_KEYS = {
    "agent_steps": "agent_run_id",
    "tool_calls": "agent_run_id",
    "model_calls": "agent_run_id",
    "retrieval_traces": "agent_run_id",
}


class FakePostgresError(RuntimeError):
    """A constraint the fake enforces, raised in the driver's name."""


class FakePostgres:
    """The in-memory tables plus the switch that makes PostgreSQL "unavailable"."""

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict[str, Any]]] = {}
        self.statements: list[tuple[str, tuple]] = []
        self.unavailable = False

    # ------------------------------------------------------------------ the handle

    def connection(self) -> "FakeConnection":
        return FakeConnection(self)

    def connection_factory(self):
        """A zero-argument factory, exactly like the adapter's ``lambda: psycopg.connect(...)``."""
        return self.connection()

    # --------------------------------------------------------------------- helpers

    def rows(self, table: str) -> dict[str, dict[str, Any]]:
        return self.tables.setdefault(table, {})

    def set_unavailable(self, unavailable: bool) -> None:
        self.unavailable = bool(unavailable)


class FakeConnection:
    def __init__(self, engine: FakePostgres):
        self.engine = engine

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> "FakeResult":
        statement = " ".join(str(sql or "").split())
        values = tuple(params or ())
        self.engine.statements.append((statement, values))
        if self.engine.unavailable:
            raise FakePostgresError("PROBE: PostgreSQL is unavailable (connection timeout)")
        match = _INSERT.match(statement)
        if match:
            self._insert(match, values)
            return FakeResult([], [])
        match = _MAX_SEQUENCE.match(statement)
        if match:
            rows = self.engine.rows("trace_events").values()
            highest = max(
                (int(row["sequence"]) for row in rows if row.get("trace_id") == values[0]),
                default=0,
            )
            return FakeResult([("max",)], [(highest,)])
        match = _SELECT_WHERE.match(statement)
        if match:
            return self._select(match, values)
        raise AssertionError(_UNKNOWN.format(sql=statement[:220]))

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None

    # ---------------------------------------------------------------------- kernels

    def _insert(self, match: re.Match[str], values: tuple[Any, ...]) -> None:
        table = match.group("table")
        columns = [column.strip() for column in match.group("columns").split(",")]
        placeholders = [item.strip() for item in match.group("placeholders").split(",")]
        if len(columns) != len(placeholders) or len(columns) != len(values):
            raise AssertionError(
                f"{table}: {len(columns)} columns, {len(placeholders)} placeholders, "
                f"{len(values)} params"
            )
        key_column = match.group("key")
        if key_column not in columns:
            raise AssertionError(f"{table}: ON CONFLICT on a column the insert omits")
        record = dict(zip(columns, values))
        for column in _NOT_NULL.get(table, ()):
            if record.get(column) in (None, ""):
                raise FakePostgresError(
                    f"null value in column {column!r} of {table} violates not-null constraint"
                )
        foreign = _FOREIGN_KEYS.get(table)
        if foreign and record.get(foreign):
            if record[foreign] not in self.engine.rows("agent_runs"):
                raise FakePostgresError(
                    f"insert on {table} violates foreign key {foreign} -> agent_runs"
                )
        if table == "trace_events":
            for event_id, row in self.engine.rows(table).items():
                if (
                    event_id != record["event_id"]
                    and row.get("trace_id") == record["trace_id"]
                    and row.get("sequence") == record["sequence"]
                ):
                    raise FakePostgresError(
                        "duplicate key value violates unique constraint "
                        '"trace_events_trace_id_sequence_key"'
                    )
        # ON CONFLICT DO UPDATE SET col = EXCLUDED.col: last write wins, the id stays.
        self.engine.rows(table)[record[key_column]] = record

    def _select(self, match: re.Match[str], values: tuple[Any, ...]) -> "FakeResult":
        table = match.group("table")
        columns = [column.strip() for column in match.group("columns").split(",")]
        where = match.group("column")
        order = (match.group("order") or "").strip()
        selected = [
            row for row in self.engine.rows(table).values() if row.get(where) == values[0]
        ]
        for clause in reversed([item.strip() for item in order.split(",") if item.strip()]):
            name, _, direction = clause.partition(" ")
            selected.sort(
                key=lambda row: (row.get(name) is None, _orderable(row.get(name))),
                reverse=direction.upper() == "DESC",
            )
        return FakeResult(
            columns,
            [tuple(_returned(row.get(column)) for column in columns) for row in selected],
        )


def _orderable(value: Any) -> Any:
    if isinstance(value, int):
        return f"{value:012d}"
    return str(value or "")


def _returned(value: Any) -> Any:
    """Return a stored value the way psycopg would: JSONB decoded, timestamps aware."""
    if isinstance(value, str) and value[:1] in ("{", "["):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


class FakeResult:
    def __init__(self, columns: list[str], rows: list[tuple[Any, ...]]):
        self.columns = columns
        self.rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None
