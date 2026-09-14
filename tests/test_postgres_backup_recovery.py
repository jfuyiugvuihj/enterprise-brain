"""Isolated PostgreSQL backup and restore drill.

The same opt-in acceptance database used by the execution persistence tests is dumped,
restored into a freshly created sibling database, and compared. A restore therefore
never overwrites the source and never touches the configured application database.

Requires ``EB_PG_ACCEPTANCE_URL`` plus ``EB_PG_BIN_DIR`` pointing at the matching
PostgreSQL client tools.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import uuid

import psycopg
import pytest

from scripts.backup_database import backup_database
from scripts.restore_database import list_backup, restore_database
from tests.test_postgres_execution_persistence import _target_or_skip

PG_BIN = os.getenv("EB_PG_BIN_DIR", "").strip()

pytestmark = pytest.mark.skipif(
    not PG_BIN,
    reason="set EB_PG_BIN_DIR to run the PostgreSQL backup and restore drill",
)

_LEDGER_TABLES = (
    "datasets",
    "artifacts",
    "agent_runs",
    "agent_steps",
    "tool_calls",
    "model_calls",
    "retrieval_traces",
    "trace_events",
    "chunks",
)


def _tool(name: str) -> str:
    candidate = Path(PG_BIN) / (name + (".exe" if os.name == "nt" else ""))
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    if not found:
        pytest.skip(name + " was not found; point EB_PG_BIN_DIR at the PostgreSQL bin directory")
    return found


@pytest.fixture(scope="module")
def targets() -> tuple[str, str, str]:
    source = _target_or_skip()
    if "://" not in source:
        raise RuntimeError("acceptance URL must be absolute")
    scheme, _, rest = source.partition("://")
    credentials, _, location = rest.rpartition("@")
    host_port, _, database = location.partition("/")
    restore_name = database + "_restore"
    if not restore_name.startswith("enterprise_brain_accept"):
        raise RuntimeError("the restore target must stay inside the acceptance namespace")
    target = scheme + "://" + credentials + "@" + host_port + "/" + restore_name
    return source, restore_name, target


@pytest.fixture
def administrator(targets):
    source, restore_name, _target = targets
    scheme, _, rest = source.partition("://")
    credentials, _, location = rest.rpartition("@")
    host_port, _, _database = location.partition("/")
    handle = psycopg.connect(
        scheme + "://" + credentials + "@" + host_port + "/postgres",
        autocommit=True,
        connect_timeout=5,
    )
    yield handle, restore_name
    handle.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
        (restore_name,),
    )
    handle.execute("DROP DATABASE IF EXISTS " + restore_name)
    handle.close()


def _seed(source: str, tag: str) -> str:
    owner_id = "owner:" + tag
    with psycopg.connect(source, connect_timeout=5) as handle:
        handle.execute(
            "INSERT INTO datasets (dataset_id, owner_id, filename, department_ids,"
            " classification, visibility, storage_key, content_sha256, status, metadata)"
            " VALUES (%s, %s, %s, %s::jsonb, 'confidential', 'department', %s, %s, 'active',"
            " '{\"rows\": 7}'::jsonb)",
            (
                tag + ":dataset",
                owner_id,
                tag + ".xlsx",
                '["finance", "board"]',
                "datasets/" + tag + ".xlsx",
                "d" * 64,
            ),
        )
        handle.execute(
            "INSERT INTO agent_runs (agent_run_id, owner_id, request_id, trace_id, task_id,"
            " session_id, worker, status, error_code, metadata)"
            " VALUES (%s, %s, %s, %s, %s, %s, 'orchestrator', 'failed', 'model_unavailable',"
            " '{\"agent_result\": {\"evidence_count\": 2}}'::jsonb)",
            (tag + ":run", owner_id, tag + ":req", tag, tag + ":task", tag + ":session"),
        )
        for name, embedding in (("near", "[1,0]"), ("far", "[0,1]")):
            handle.execute(
                "INSERT INTO chunks (chunk_id, owner_id, resource_type, resource_id,"
                " resource_version_id, content, embedding)"
                " VALUES (%s, %s, 'document', %s, 'v1', %s, %s::vector)",
                (tag + ":" + name, owner_id, tag + ":doc", "chunk " + name, embedding),
            )
        handle.commit()
    return owner_id


def _counts(handle) -> dict[str, int]:
    return {
        table: handle.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in _LEDGER_TABLES
    }


def test_backup_restores_schema_ownership_and_vectors(administrator, targets, tmp_path) -> None:
    source, restore_name, target = targets
    admin, _name = administrator
    tag = "brp-" + uuid.uuid4().hex[:8]
    owner_id = _seed(source, tag)
    try:
        archive = tmp_path / "acceptance.dump"
        backup_database(source, archive, pg_dump_path=_tool("pg_dump"))
        assert archive.stat().st_size > 0

        entries = list_backup(archive, pg_restore_path=_tool("pg_restore"))
        joined = "\n".join(entries)
        for table in ("datasets", "agent_runs", "chunks", "schema_migrations"):
            assert table in joined, "the archive must contain " + table

        admin.execute("CREATE DATABASE " + restore_name)
        assert restore_database(archive, target, pg_restore_path=_tool("pg_restore")) == restore_name

        with psycopg.connect(source, connect_timeout=5) as original, psycopg.connect(target, connect_timeout=5) as copy:
            assert _counts(original) == _counts(copy)
            assert original.execute(
                "SELECT version, checksum FROM schema_migrations ORDER BY version").fetchall() == copy.execute(
                "SELECT version, checksum FROM schema_migrations ORDER BY version").fetchall()
            assert copy.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone() is not None

            source_row = original.execute(
                "SELECT owner_id, classification, visibility, jsonb_array_elements_text(department_ids)"
                " FROM datasets WHERE dataset_id = %s", (tag + ":dataset",)).fetchall()
            copy_row = copy.execute(
                "SELECT owner_id, classification, visibility, jsonb_array_elements_text(department_ids)"
                " FROM datasets WHERE dataset_id = %s", (tag + ":dataset",)).fetchall()
            assert source_row == copy_row
            assert [row[0] for row in copy_row] == [owner_id, owner_id]
            assert {row[3] for row in copy_row} == {"finance", "board"}

            run = copy.execute(
                "SELECT status, error_code, metadata -> 'agent_result' ->> 'evidence_count'"
                " FROM agent_runs WHERE agent_run_id = %s", (tag + ":run",)).fetchone()
            assert run == ("failed", "model_unavailable", "2")

            query = (
                "SELECT chunk_id FROM chunks WHERE owner_id = %s"
                " ORDER BY embedding <=> %s::vector LIMIT 1"
            )
            assert original.execute(query, (owner_id, "[0.9,0.1]")).fetchone() == copy.execute(
                query, (owner_id, "[0.9,0.1]")
            ).fetchone()

            with pytest.raises(psycopg.IntegrityError):
                copy.execute(
                    "INSERT INTO agent_steps (agent_step_id, agent_run_id, owner_id,"
                    " step_id, worker, status, sequence) VALUES (%s, %s, %s, %s,"
                    " 'doc_agent', 'completed', 1)",
                    (tag + ":orphan", tag + ":nope", owner_id, tag + ":orphan"),
                )
            copy.rollback()
    finally:
        with psycopg.connect(source, connect_timeout=5) as handle:
            for table in _LEDGER_TABLES:
                handle.execute("DELETE FROM " + table + " WHERE owner_id = %s", (owner_id,))
            handle.commit()


def test_restore_refuses_an_empty_archive(tmp_path, targets) -> None:
    empty = tmp_path / "empty.dump"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="missing or empty"):
        list_backup(empty, pg_restore_path=_tool("pg_restore"))
    with pytest.raises(ValueError, match="missing or empty"):
        restore_database(empty, targets[2], pg_restore_path=_tool("pg_restore"))


def test_restore_rejects_a_non_postgres_url() -> None:
    with pytest.raises(ValueError, match="PostgreSQL scheme"):
        restore_database("ignored.dump", "mysql://user:***@127.0.0.1:3306/anything")