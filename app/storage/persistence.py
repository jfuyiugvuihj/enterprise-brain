"""Explicit persistence adapters for resource metadata and execution traces.

The local adapter is intentionally atomic and suitable for offline development. The
PostgreSQL adapter is selected explicitly through ``PERSISTENCE_BACKEND=postgres`` and
surfaces write errors instead of silently falling back after a configured database
fails.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Any, Callable


class PersistenceWriteError(RuntimeError):
    """A configured persistence backend failed to store a record."""


def _json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class JsonPersistenceAdapter:
    """Atomic JSON persistence used when PostgreSQL is intentionally unavailable."""

    _OWNER_REQUIRED = {
        "datasets",
        "dataset_versions",
        "artifacts",
        "agent_runs",
        "agent_steps",
        "tool_calls",
        "model_calls",
        "retrieval_traces",
    }

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _read(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise PersistenceWriteError(f"cannot read persistence file: {exc}") from exc
        if not isinstance(value, dict):
            raise PersistenceWriteError("persistence file must contain an object")
        return value

    def _write(self, payload: dict[str, Any]) -> None:
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise PersistenceWriteError(f"cannot write persistence file: {exc}") from exc
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def upsert(self, collection: str, record_id: str, record: dict[str, Any]) -> dict[str, Any]:
        collection = str(collection or "").strip()
        record_id = str(record_id or "").strip()
        if not collection or not record_id or not isinstance(record, dict):
            raise ValueError("collection, record_id and record are required")
        if collection in self._OWNER_REQUIRED and not str(record.get("owner_id") or "").strip():
            raise ValueError("owner_id is required for protected records")
        with self._lock:
            payload = self._read()
            bucket = payload.setdefault(collection, {})
            if not isinstance(bucket, dict):
                raise PersistenceWriteError(f"persistence collection is invalid: {collection}")
            bucket[record_id] = dict(record)
            self._write(payload)
        return dict(record)

    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._read().get(collection, {}).get(record_id)
            return dict(value) if isinstance(value, dict) else None

    def list(self, collection: str) -> list[dict[str, Any]]:
        with self._lock:
            bucket = self._read().get(collection, {})
            if not isinstance(bucket, dict):
                return []
            return [dict(value) for value in bucket.values() if isinstance(value, dict)]


@dataclass(frozen=True)
class _PostgresTable:
    table: str
    id_column: str
    columns: tuple[str, ...]
    order_column: str = "created_at"


_TABLES = {
    "datasets": _PostgresTable(
        "datasets",
        "dataset_id",
        (
            "dataset_id",
            "owner_id",
            "filename",
            "department_ids",
            "classification",
            "visibility",
            "storage_key",
            "content_sha256",
            "status",
            "current_version_id",
            "created_at",
            "metadata",
        ),
    ),
    "artifacts": _PostgresTable(
        "artifacts",
        "artifact_id",
        (
            "artifact_id",
            "owner_id",
            "resource_type",
            "resource_id",
            "source_version_id",
            "storage_key",
            "content_sha256",
            "status",
            "expires_at",
            "created_at",
            "metadata",
        ),
    ),
    "trace_events": _PostgresTable(
        "trace_events",
        "event_id",
        (
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
    ),
    "agent_runs": _PostgresTable(
        "agent_runs",
        "agent_run_id",
        (
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
    ),
    "agent_steps": _PostgresTable(
        "agent_steps",
        "agent_step_id",
        (
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
    ),
    "tool_calls": _PostgresTable(
        "tool_calls",
        "tool_call_id",
        (
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
    ),
    "model_calls": _PostgresTable(
        "model_calls",
        "model_call_id",
        (
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
    ),
    "retrieval_traces": _PostgresTable(
        "retrieval_traces",
        "retrieval_trace_id",
        (
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
    ),
    "audit_events": _PostgresTable(
        "audit_events",
        "event_id",
        (
            "event_id",
            "request_id",
            "actor_username",
            "actor_role",
            "owner_id",
            "action",
            "resource",
            "resource_scope",
            "outcome",
            "reason_code",
            "policy_version",
            "before_summary",
            "after_summary",
            "payload",
            "retention_days",
            "expires_at",
            "created_at",
        ),
    ),
}


# The execution ledger records timing on started_at rather than created_at.
for _name in ("agent_runs", "agent_steps", "tool_calls", "model_calls"):
    _TABLES[_name] = replace(_TABLES[_name], order_column="started_at")


class PostgresPersistenceAdapter:
    """Small DB-API adapter with deterministic SQL and explicit error propagation."""

    def __init__(self, connection_factory: Callable[[], Any]):
        self.connection_factory = connection_factory

    def upsert(self, collection: str, record_id: str, record: dict[str, Any]) -> dict[str, Any]:
        definition = _TABLES.get(collection)
        if definition is None:
            raise ValueError(f"unsupported PostgreSQL collection: {collection}")
        values = dict(record)
        values[definition.id_column] = record_id
        if collection in {
            "datasets",
            "artifacts",
            "trace_events",
            "agent_runs",
            "agent_steps",
            "tool_calls",
            "model_calls",
            "retrieval_traces",
        } and not str(
            values.get("owner_id") or ""
        ).strip():
            raise ValueError("owner_id is required for protected records")
        now = datetime.now(timezone.utc)
        for timestamp_field in ("created_at", "started_at"):
            if timestamp_field in definition.columns and values.get(timestamp_field) is None:
                values[timestamp_field] = now
        columns = definition.columns
        placeholders = ", ".join(["%s"] * len(columns))
        assignments = ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in columns
            if column != definition.id_column
        )
        sql = (
            f"INSERT INTO {definition.table} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) ON CONFLICT ({definition.id_column}) DO UPDATE SET {assignments}"
        )
        params = tuple(
            _json_value(values.get(column, {}))
            if column in {
                "department_ids",
                "metadata",
                "payload",
                "input_summary",
                "output_summary",
                "arguments",
                "result_summary",
                "filter_snapshot",
                "resource_scope",
                "before_summary",
                "after_summary",
            }
            else values.get(column)
            for column in columns
        )
        connection = None
        try:
            connection = self.connection_factory()
            connection.execute(sql, params)
            if hasattr(connection, "commit"):
                connection.commit()
        except Exception as exc:
            if connection is not None and hasattr(connection, "rollback"):
                try:
                    connection.rollback()
                except Exception:
                    pass
            raise PersistenceWriteError(f"{collection} write failed: {exc}") from exc
        finally:
            if connection is not None and hasattr(connection, "close"):
                connection.close()
        return dict(record)

    @staticmethod
    def _as_record(definition: _PostgresTable, row: Any) -> dict[str, Any]:
        """Key a driver row by the declared column order instead of assuming dict rows."""
        if isinstance(row, Mapping):
            return dict(row)
        return dict(zip(definition.columns, row))

    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        definition = _TABLES.get(collection)
        if definition is None:
            raise ValueError(f"unsupported PostgreSQL collection: {collection}")
        connection = None
        try:
            connection = self.connection_factory()
            row = connection.execute(
                f"SELECT {', '.join(definition.columns)} FROM {definition.table} WHERE {definition.id_column} = %s",
                (record_id,),
            ).fetchone()
            return self._as_record(definition, row) if row else None
        except Exception as exc:
            raise PersistenceWriteError(f"{collection} read failed: {exc}") from exc
        finally:
            if connection is not None and hasattr(connection, "close"):
                connection.close()

    def list(self, collection: str) -> list[dict[str, Any]]:
        definition = _TABLES.get(collection)
        if definition is None:
            raise ValueError(f"unsupported PostgreSQL collection: {collection}")
        connection = None
        try:
            connection = self.connection_factory()
            rows = connection.execute(
                f"SELECT {', '.join(definition.columns)} FROM {definition.table} ORDER BY {definition.order_column} DESC"
            ).fetchall()
            return [self._as_record(definition, row) for row in rows]
        except Exception as exc:
            raise PersistenceWriteError(f"{collection} list failed: {exc}") from exc
        finally:
            if connection is not None and hasattr(connection, "close"):
                connection.close()


def build_persistence_adapter(
    *,
    backend: str | None = None,
    database_url: str | None = None,
    fallback_path: str | Path | None = None,
):
    selected = (backend or os.getenv("PERSISTENCE_BACKEND", "json")).strip().lower()
    if selected == "postgres":
        url = (database_url or os.getenv("DATABASE_URL") or "").strip()
        if not url:
            raise ValueError("DATABASE_URL is required for PostgreSQL persistence")
        import psycopg

        return PostgresPersistenceAdapter(
            lambda: psycopg.connect(url, connect_timeout=2)
        )
    if selected not in {"json", "local"}:
        raise ValueError(f"unsupported persistence backend: {selected}")
    return JsonPersistenceAdapter(
        fallback_path
        or os.getenv("PERSISTENCE_FALLBACK_PATH", "./data/.persistence.json")
    )
