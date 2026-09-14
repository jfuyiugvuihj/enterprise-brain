from __future__ import annotations

import json

import pytest


def test_json_persistence_round_trips_versioned_records(tmp_path):
    from app.storage.persistence import JsonPersistenceAdapter

    adapter = JsonPersistenceAdapter(tmp_path / "records.json")
    record = {
        "dataset_id": "dataset-1",
        "version_id": "dataset-1:v1",
        "owner_id": "user-1",
        "status": "active",
    }

    adapter.upsert("datasets", "dataset-1", record)

    assert adapter.get("datasets", "dataset-1") == record
    assert adapter.list("datasets") == [record]
    assert json.loads((tmp_path / "records.json").read_text(encoding="utf-8"))["datasets"]


def test_json_persistence_requires_explicit_owner_for_protected_records(tmp_path):
    from app.storage.persistence import JsonPersistenceAdapter

    adapter = JsonPersistenceAdapter(tmp_path / "records.json")
    with pytest.raises(ValueError, match="owner_id"):
        adapter.upsert("artifacts", "artifact-1", {"status": "active"})


def test_postgres_adapter_supports_execution_trace_collections():
    from app.storage.persistence import PostgresPersistenceAdapter

    observed = []

    class Result:
        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class Connection:
        def execute(self, sql, params=None):
            observed.append((sql, params))
            return Result()

        def commit(self):
            return None

        def close(self):
            return None

    adapter = PostgresPersistenceAdapter(lambda: Connection())

    records = {
        "agent_runs": {
            "agent_run_id": "run-1",
            "owner_id": "user-1",
            "request_id": "req-1",
            "trace_id": "trace-1",
            "task_id": "task-1",
            "worker": "orchestrator",
            "status": "running",
        },
        "agent_steps": {
            "agent_step_id": "step-1",
            "agent_run_id": "run-1",
            "owner_id": "user-1",
            "step_id": "step-1",
            "worker": "doc",
            "status": "completed",
            "sequence": 1,
        },
        "tool_calls": {
            "tool_call_id": "tool-1",
            "owner_id": "user-1",
            "tool_name": "doc",
            "status": "completed",
        },
        "model_calls": {
            "model_call_id": "model-1",
            "owner_id": "user-1",
            "provider": "ollama",
            "model_name": "qwen",
            "status": "completed",
        },
        "retrieval_traces": {
            "retrieval_trace_id": "retrieval-1",
            "owner_id": "user-1",
            "trace_id": "trace-1",
            "query_hash": "0" * 64,
            "status": "completed",
        },
    }

    for collection, record in records.items():
        adapter.upsert(collection, next(iter(record.values())), record)

    sql = "\n".join(statement for statement, _params in observed)
    for table_name in records:
        assert f"INSERT INTO {table_name}" in sql


def test_postgres_adapter_surfaces_write_failures():
    from app.storage.persistence import PersistenceWriteError, PostgresPersistenceAdapter

    class BrokenConnection:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("database write failed")

        def close(self):
            return None

    adapter = PostgresPersistenceAdapter(lambda: BrokenConnection())
    with pytest.raises(PersistenceWriteError, match="database write failed"):
        adapter.upsert("datasets", "dataset-1", {"owner_id": "user-1", "status": "active"})
