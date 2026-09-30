"""R250 judgement 2: the trace field set and the table column set agree, in both directions.

Three copies of the same list exist and the point of this file is that they cannot drift:

1. ``migrations/0002_execution_data_lineage.sql`` -- what the database actually has,
   plus every ``ALTER TABLE ... ADD COLUMN`` later migrations append to those tables
   (0018 adds ``model_calls.cached_tokens``; R509 set the precedent in
   ``tests/test_r248_artifact_column_alignment.py`` -- reading only the CREATE would
   make this pin judge the shape of a two-year-old table);
2. ``app.trace.schema.TRACE_TABLE_COLUMNS`` -- what the trace plane writes and reads;
3. ``app.storage.persistence._TABLES`` -- the columns the adapter puts into its SQL.

A fourth check is behavioural: every projection the canonical run produces is sealed against
the contract, and the rows the readout returns carry exactly the table's columns -- no field
invented by the read path, no column dropped because a builder forgot it. The store refuses a
mismatch at write time too, so a drift fails loudly rather than as a NULL two days later.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.storage.persistence import PostgresPersistenceAdapter, _TABLES
from app.trace import durability
from app.trace.projections import project_event, project_event_row
from app.trace.schema import (
    TRACE_ID_COLUMNS,
    TRACE_TABLE_COLUMNS,
    TRACE_TABLES,
    TraceSchemaError,
    declared_columns,
    require_columns,
)
from app.trace.store import TraceStore
from tests._r250_fake_postgres import FakePostgres
from tests._r250_run_fixture import emit_full_run

MIGRATION = Path("migrations/0002_execution_data_lineage.sql")
MIGRATIONS_DIR = Path("migrations")
#: 后续迁移往这六张表上追加的列，形状与 0002 里的出生同等有效。
_ALTER_ADD = re.compile(
    r"ALTER TABLE IF EXISTS (?P<table>\w+)\s+ADD COLUMN IF NOT EXISTS (?P<name>\w+)",
    re.S,
)
_CREATE = re.compile(
    r"CREATE TABLE IF NOT EXISTS (?P<name>\w+) \((?P<body>.*?)\n\);",
    re.S,
)
_CONSTRAINT_WORDS = ("primary key", "unique", "check", "foreign key", "constraint", "exclude")


def _added_columns() -> dict[str, list[str]]:
    """Column names appended by later migrations, in file order -- nothing hard-coded.

    The count is deliberately not written into this file: whoever adds another column to a
    trace table in 0019, 0020... lands here automatically, which is the whole point of reading
    DDL instead of copying a list.
    """
    added: dict[str, list[str]] = {}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        for match in _ALTER_ADD.finditer(path.read_text(encoding="utf-8")):
            added.setdefault(match.group("table"), []).append(match.group("name"))
    return added


def _ddl_columns() -> dict[str, tuple[str, ...]]:
    """Column names straight out of the checked-in DDL, in declaration order."""
    text = MIGRATION.read_text(encoding="utf-8")
    tables: dict[str, tuple[str, ...]] = {}
    for match in _CREATE.finditer(text):
        columns = []
        for line in match.group("body").splitlines():
            stripped = line.strip().rstrip(",")
            if not stripped or stripped.startswith("--"):
                continue
            if any(stripped.lower().startswith(word) for word in _CONSTRAINT_WORDS):
                continue
            columns.append(stripped.split()[0].lower())
        tables[match.group("name")] = tuple(columns)
    for table, names in _added_columns().items():
        if table in tables:
            # ADD COLUMN appends: the physical order of a column the table grew later is the
            # order both schema.py and persistence.py put it in.
            tables[table] = tables[table] + tuple(
                name for name in names if name not in tables[table]
            )
    return tables


@pytest.fixture(autouse=True)
def clean_ledger():
    durability.reset_durability_ledger()
    yield
    durability.reset_durability_ledger()


def test_the_six_tables_are_the_tables_the_migration_created():
    ddl = _ddl_columns()
    assert set(TRACE_TABLES) <= set(ddl), sorted(set(TRACE_TABLES) - set(ddl))
    for table in TRACE_TABLES:
        assert TRACE_ID_COLUMNS[table] == ddl[table][0], table


@pytest.mark.parametrize("table", TRACE_TABLES)
def test_the_declared_columns_equal_the_ddl_columns_in_both_directions(table):
    ddl = _ddl_columns()[table]
    declared = TRACE_TABLE_COLUMNS[table]
    assert set(declared) - set(ddl) == set(), f"{table}: the trace plane names a column the table lacks"
    assert set(ddl) - set(declared) == set(), f"{table}: the table has a column the trace plane omits"
    assert declared == ddl, f"{table}: column order drifted from the migration"


@pytest.mark.parametrize("table", TRACE_TABLES)
def test_the_adapter_and_the_trace_plane_name_the_same_columns(table):
    adapter_columns = tuple(_TABLES[table].columns)
    assert adapter_columns == TRACE_TABLE_COLUMNS[table], table


def test_require_columns_refuses_a_record_that_is_off_in_either_direction():
    complete = TRACE_TABLE_COLUMNS["agent_steps"]
    require_columns("agent_steps", complete)

    with pytest.raises(TraceSchemaError) as extra:
        require_columns("agent_steps", complete + ("invented_column",))
    assert "extra=" in str(extra.value)

    with pytest.raises(TraceSchemaError) as missing:
        require_columns("agent_steps", tuple(column for column in complete if column != "worker"))
    assert "missing=" in str(missing.value)

    with pytest.raises(TraceSchemaError):
        declared_columns("not_a_trace_table")


def test_every_projection_of_one_run_is_sealed_against_its_table(tmp_path):
    engine = FakePostgres()
    store = TraceStore(tmp_path / "fallback.jsonl", persistence=PostgresPersistenceAdapter(engine.connection_factory))
    trace = "r250-align-" + trace_id_suffix()
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)

    sealed_tables = {
        statement.split()[2] for statement, _params in engine.statements if statement.startswith("INSERT INTO")
    }
    assert sealed_tables == set(TRACE_TABLES), sorted(set(TRACE_TABLES) ^ sealed_tables)
    assert durability.durability_status()["fallback_events"] == 0
    assert written["counts"]["trace_events"] >= 15

    # A builder that forgets a column is refused before it reaches the adapter.
    event = {
        "trace_id": trace,
        "request_id": "r",
        "task_id": "t",
        "sequence": 1,
        "timestamp": "2026-09-25T00:00:00+00:00",
        "event_type": "request.started",
        "status": "started",
        "payload": {},
    }
    projection = project_run_without_error_code(event, "owner:" + trace)
    with pytest.raises(TraceSchemaError) as refused:
        projection.seal()
    assert "missing=['error_code']" in str(refused.value)


def test_the_readout_rows_carry_exactly_the_table_columns(tmp_path):
    engine = FakePostgres()
    store = TraceStore(tmp_path / "fallback.jsonl", persistence=PostgresPersistenceAdapter(engine.connection_factory))
    trace = "r250-shape-" + trace_id_suffix()
    written = emit_full_run(store, trace=trace, owner="owner:" + trace)

    readout = store.read_run(written["run_id"])

    assert set(readout["run"]) == set(TRACE_TABLE_COLUMNS["agent_runs"])
    for step in readout["steps"]:
        assert set(step) == set(TRACE_TABLE_COLUMNS["agent_steps"])
    for call in readout["tool_calls"]:
        assert set(call) == set(TRACE_TABLE_COLUMNS["tool_calls"])
    for call in readout["model_calls"]:
        assert set(call) == set(TRACE_TABLE_COLUMNS["model_calls"])
    for row in readout["retrieval_traces"]:
        assert set(row) == set(TRACE_TABLE_COLUMNS["retrieval_traces"])
    for event in store.replay(trace):
        assert set(event) == {
            "trace_id", "request_id", "task_id", "sequence", "timestamp", "event_type", "status", "payload",
        }


def test_the_reader_refuses_an_unsafe_identifier():
    from app.trace.run_reader import _select

    with pytest.raises(Exception):
        _select("trace_events", "trace_id = %s; DROP TABLE agent_runs")


def trace_id_suffix() -> str:
    import uuid

    return uuid.uuid4().hex[:10]


def project_run_without_error_code(event, owner_id):
    from app.trace.projections import project_run

    projection = project_run(event, owner_id, {})
    values = dict(projection.values)
    values.pop("error_code")
    projection.values.clear()
    projection.values.update(values)
    return projection
