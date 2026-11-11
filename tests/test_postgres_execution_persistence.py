"""Isolated PostgreSQL acceptance for the execution ledger and PGVector boundary.

These tests run only when an operator exports ``EB_PG_ACCEPTANCE_URL`` pointing at a
throwaway acceptance database, and they refuse any target that could be the configured
application database. Offline unit and contract tests never touch a live server.
"""
from __future__ import annotations

import os
from typing import Iterator
from urllib.parse import urlsplit
import uuid

import psycopg
import pytest

from app.agents.contracts import AgentResult, Evidence
from app.db.migrations import MIGRATIONS
from app.storage.persistence import build_persistence_adapter
from app.trace.records import record_agent_result
from app.trace.store import TraceStore, reset_default_trace_store

DATABASE_URL = os.getenv("EB_PG_ACCEPTANCE_URL", "").strip()

_LEDGER_TABLES = (
    "trace_events",
    "retrieval_traces",
    "model_calls",
    "tool_calls",
    "agent_steps",
    "agent_runs",
    "artifacts",
    "datasets",
    "chunks",
)


def _target_or_skip() -> str:
    if not DATABASE_URL:
        pytest.skip("set EB_PG_ACCEPTANCE_URL to run the isolated PostgreSQL acceptance")
    parsed = urlsplit(DATABASE_URL)
    database = (parsed.path or "").lstrip("/")
    port = parsed.port or 5432
    if not database.startswith("enterprise_brain_accept"):
        raise RuntimeError("acceptance URL must target an enterprise_brain_accept* database")
    if port == 5432 or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("acceptance URL must not target the default application database")
    return DATABASE_URL


@pytest.fixture(scope="module")
def url() -> str:
    return _target_or_skip()


@pytest.fixture
def connection(url) -> Iterator[psycopg.Connection]:
    handle = psycopg.connect(url, connect_timeout=5)
    try:
        yield handle
    finally:
        handle.rollback()
        handle.close()


@pytest.fixture
def owned(connection) -> tuple[str, str]:
    """Return ``(owner_id, tag)`` and remove every row the test wrote for that owner."""
    tag = "acc-" + uuid.uuid4().hex[:10]
    owner_id = f"owner:{tag}"
    yield owner_id, tag
    for table in _LEDGER_TABLES:
        connection.execute(f"DELETE FROM {table} WHERE owner_id = %s", (owner_id,))
    connection.commit()


@pytest.fixture
def adapter(url):
    return build_persistence_adapter(backend="postgres", database_url=url)


def test_migration_ledger_matches_the_checked_in_catalog(connection) -> None:
    rows = connection.execute(
        "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    applied = {str(row[0]): str(row[2]) for row in rows}
    assert set(applied) == {migration.version for migration in MIGRATIONS}
    for migration in MIGRATIONS:
        assert applied[migration.version] == migration.checksum


def test_pgvector_extension_and_distance_operators(connection, owned) -> None:
    extension = connection.execute(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    ).fetchone()
    assert extension is not None and str(extension[0]).startswith("0.")

    owner_id, tag = owned
    vectors = {
        "x_axis": "[1,0]",
        "y_axis": "[0,1]",
        "diagonal": "[0.7,0.7]",
    }
    for name, embedding in vectors.items():
        connection.execute(
            "INSERT INTO chunks (chunk_id, owner_id, resource_type, resource_id,"
            " resource_version_id, content, embedding)"
            " VALUES (%s, %s, 'document', %s, 'v1', %s, %s::vector)",
            (f"{tag}:{name}", owner_id, f"doc-{name}", f"chunk {name}", embedding),
        )
    connection.commit()

    cosine = connection.execute(
        "SELECT chunk_id FROM chunks WHERE owner_id = %s"
        " ORDER BY embedding <=> '[0.95,0.05]'::vector LIMIT 1",
        (owner_id,),
    ).fetchone()
    euclid = connection.execute(
        "SELECT chunk_id FROM chunks WHERE owner_id = %s"
        " ORDER BY embedding <-> '[0.95,0.05]'::vector LIMIT 1",
        (owner_id,),
    ).fetchone()
    assert cosine[0] == f"{tag}:x_axis"
    assert euclid[0] == f"{tag}:x_axis"


def test_persistence_adapter_writes_and_reads_the_execution_ledger(adapter, connection, owned) -> None:
    owner_id, tag = owned
    run_id = f"{tag}:orchestrator"
    step_id = f"{tag}:worker:doc_agent"
    tool_id = f"{tag}:tool:search_docs"
    model_id = f"{tag}:model:qwen"
    retrieval_id = f"{tag}:retrieval"

    adapter.upsert(
        "datasets",
        f"{tag}:dataset",
        {
            "dataset_id": f"{tag}:dataset",
            "owner_id": owner_id,
            "filename": f"{tag}.xlsx",
            "department_ids": ["finance"],
            "classification": "internal",
            "visibility": "department",
            "storage_key": f"datasets/{tag}.xlsx",
            "content_sha256": "a" * 64,
            "status": "active",
            "metadata": {"rows": 12},
        },
    )
    adapter.upsert(
        "artifacts",
        f"{tag}:artifact",
        {
            "artifact_id": f"{tag}:artifact",
            "owner_id": owner_id,
            "resource_type": "chart",
            "resource_id": f"{tag}:chart",
            "source_version_id": f"{tag}:dataset",
            "storage_key": f"charts/{tag}.png",
            "content_sha256": "b" * 64,
            "status": "active",
            "metadata": {"source_dataset_id": f"{tag}:dataset"},
        },
    )
    adapter.upsert(
        "agent_runs",
        run_id,
        {
            "agent_run_id": run_id,
            "owner_id": owner_id,
            "request_id": f"{tag}:req",
            "trace_id": tag,
            "task_id": f"{tag}:task",
            "session_id": f"{tag}:session",
            "worker": "orchestrator",
            "status": "running",
            "metadata": {"entry_point": "queue"},
        },
    )
    adapter.upsert(
        "agent_steps",
        step_id,
        {
            "agent_step_id": step_id,
            "agent_run_id": run_id,
            "owner_id": owner_id,
            "step_id": step_id,
            "worker": "doc_agent",
            "status": "completed",
            "sequence": 1,
            "input_summary": {"question_length": 24},
            "output_summary": {"evidence_count": 3},
        },
    )
    adapter.upsert(
        "tool_calls",
        tool_id,
        {
            "tool_call_id": tool_id,
            "agent_run_id": run_id,
            "agent_step_id": step_id,
            "owner_id": owner_id,
            "tool_name": "search_docs",
            "status": "completed",
            "request_id": f"{tag}:req",
            "arguments": {"query_length": 24},
            "result_summary": {"hit_count": 3},
        },
    )
    adapter.upsert(
        "model_calls",
        model_id,
        {
            "model_call_id": model_id,
            "agent_run_id": run_id,
            "agent_step_id": step_id,
            "owner_id": owner_id,
            "provider": "ollama",
            "model_name": "qwen2.5:14b",
            "status": "completed",
            "request_id": f"{tag}:req",
            "queue_wait_ms": 15,
            "duration_ms": 940,
            "input_tokens": 120,
            "output_tokens": 64,
            "metadata": {"worker": "doc_agent"},
        },
    )
    adapter.upsert(
        "retrieval_traces",
        retrieval_id,
        {
            "retrieval_trace_id": retrieval_id,
            "agent_run_id": run_id,
            "owner_id": owner_id,
            "request_id": f"{tag}:req",
            "trace_id": tag,
            "query_hash": "c" * 64,
            "index_version_id": f"{tag}:index-version",
            "filter_snapshot": {"owner_id": owner_id, "classification": "internal"},
            "result_summary": {"hit_count": 3},
            "status": "completed",
        },
    )
    adapter.upsert(
        "trace_events",
        f"{tag}:orchestrator:1",
        {
            "event_id": f"{tag}:orchestrator:1",
            "trace_id": tag,
            "request_id": f"{tag}:req",
            "task_id": f"{tag}:task",
            "sequence": 1,
            "event_type": "request.started",
            "status": "started",
            "owner_id": owner_id,
            "payload": {"session_id": f"{tag}:session"},
        },
    )

    run_row = adapter.get("agent_runs", run_id)
    assert run_row is not None
    assert run_row["owner_id"] == owner_id
    assert run_row["worker"] == "orchestrator"

    stored = {
        table: connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE owner_id = %s", (owner_id,)
        ).fetchone()[0]
        for table in (
            "datasets",
            "artifacts",
            "agent_runs",
            "agent_steps",
            "tool_calls",
            "model_calls",
            "retrieval_traces",
            "trace_events",
        )
    }
    assert stored == {name: 1 for name in stored}

    assert connection.execute(
        "SELECT jsonb_typeof(department_ids) FROM datasets WHERE dataset_id = %s",
        (f"{tag}:dataset",),
    ).fetchone()[0] == "array"
    assert connection.execute(
        "SELECT metadata -> 'agent_result' FROM agent_runs WHERE agent_run_id = %s",
        (run_id,),
    ).fetchone()[0] is None
    assert connection.execute(
        "SELECT duration_ms, input_tokens FROM model_calls WHERE model_call_id = %s",
        (model_id,),
    ).fetchone() == (940, 120)


def test_execution_rows_cannot_escape_their_owner(adapter, owned) -> None:
    owner_id, tag = owned
    with pytest.raises(ValueError, match="owner_id is required"):
        adapter.upsert(
            "agent_runs",
            f"{tag}:orchestrator",
            {
                "agent_run_id": f"{tag}:orchestrator",
                "request_id": f"{tag}:req",
                "trace_id": tag,
                "task_id": f"{tag}:task",
                "worker": "orchestrator",
                "status": "running",
            },
        )
    with pytest.raises(ValueError, match="owner_id is required"):
        adapter.upsert("datasets", f"{tag}:dataset", {"dataset_id": f"{tag}:dataset", "owner_id": "  "})


def test_child_records_cannot_reference_a_missing_run(connection, owned) -> None:
    owner_id, tag = owned
    with pytest.raises(psycopg.IntegrityError):
        connection.execute(
            "INSERT INTO agent_steps (agent_step_id, agent_run_id, owner_id, step_id,"
            " worker, status, sequence) VALUES (%s, %s, %s, %s, 'doc_agent', 'completed', 1)",
            (f"{tag}:orphan", f"{tag}:missing-run", owner_id, f"{tag}:orphan"),
        )
    connection.rollback()


def test_record_agent_result_projects_a_summary_onto_the_run_row(monkeypatch, tmp_path, url, owned) -> None:
    owner_id, tag = owned
    monkeypatch.setenv("TRACE_STORE_PATH", str(tmp_path / "trace.jsonl"))
    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", url)
    reset_default_trace_store()
    try:
        secret_phrase = "revenue-figures-must-not-enter-the-ledger"
        result = AgentResult(
            worker="doc_agent",
            status="success",
            answer=secret_phrase,
            request_id=f"{tag}:req",
            trace_id=tag,
            task_id=f"{tag}:task",
            duration_ms=1234,
            evidence=[
                Evidence(
                    source_type="document",
                    source_id="doc-acceptance",
                    document_version_id="doc-acceptance:v1",
                    permission_checked=True,
                    provenance_status="verified",
                )
            ],
        )
        summary = record_agent_result(
            result, owner_id=owner_id, session_id=f"{tag}:session", entry_point="queue"
        )
        assert summary["worker"] == "doc_agent"
        assert summary["status"] == "success"
        assert summary["evidence_count"] == 1
        assert summary["document_count"] == 1

        with psycopg.connect(url, connect_timeout=5) as handle:
            row = handle.execute(
                "SELECT metadata, status, session_id, request_id, task_id"
                " FROM agent_runs WHERE agent_run_id = %s",
                (f"{tag}:orchestrator",),
            ).fetchone()
            event_count = handle.execute(
                "SELECT COUNT(*) FROM trace_events"
                " WHERE trace_id = %s AND event_type = 'agent.result.recorded'",
                (tag,),
            ).fetchone()[0]

        assert row is not None
        metadata, status, session_id, request_id, task_id = row
        assert status == "completed"
        assert session_id == f"{tag}:session"
        assert request_id == f"{tag}:req"
        assert task_id == f"{tag}:task"
        assert metadata["entry_point"] == "queue"
        assert metadata["agent_result"]["answer_length"] == len(secret_phrase)
        assert metadata["agent_result"]["evidence_count"] == 1
        assert secret_phrase not in str(metadata), "the answer body must stay out of the ledger"
        assert event_count == 1
    finally:
        reset_default_trace_store()


def test_trace_store_projects_every_lifecycle_event_onto_one_run(tmp_path, url, owned) -> None:
    """A second event for the same trace must read back the run row it just wrote."""
    owner_id, tag = owned
    store = TraceStore(
        tmp_path / "lifecycle.jsonl",
        persistence=build_persistence_adapter(backend="postgres", database_url=url),
    )
    store.record_event(
        trace_id=tag,
        request_id=f"{tag}:req",
        task_id=f"{tag}:task",
        event_type="request.started",
        status="started",
        payload={"owner_id": owner_id, "session_id": f"{tag}:session"},
    )
    store.record_event(
        trace_id=tag,
        request_id=f"{tag}:req",
        task_id=f"{tag}:task",
        event_type="request.completed",
        status="completed",
        payload={"owner_id": owner_id, "worker_count": 2, "has_final_answer": True},
    )

    with psycopg.connect(url, connect_timeout=5) as handle:
        run = handle.execute(
            "SELECT status, session_id, (metadata ->> 'worker_count')::int,"
            " completed_at IS NOT NULL, (SELECT COUNT(*) FROM trace_events WHERE trace_id = %s)"
            " FROM agent_runs WHERE agent_run_id = %s",
            (tag, f"{tag}:orchestrator"),
        ).fetchone()
    assert run[0] == "completed"
    assert run[1] == f"{tag}:session"
    assert run[2] == 2
    assert run[3] is True
    assert run[4] == 2
