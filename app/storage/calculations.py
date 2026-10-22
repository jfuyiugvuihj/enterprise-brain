"""Independent calculation history in the existing PostgreSQL lineage table."""
from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.agents.contracts import Principal, ResourceScope
from app.common.permissions import ACTION_VIEW
from app.common.policy import authorization_decision, is_administrator
from app.storage.artifacts import artifact_registry
from app.storage.datasets import dataset_registry
from app.storage.persistence import PersistenceWriteError


_COLUMNS = (
    "calculation_run_id", "owner_id", "dataset_version_id", "metric_definition_id",
    "request_id", "task_id", "status", "formula", "parameters", "result",
    "error_code", "started_at", "completed_at", "created_at",
)
_SELECT = ", ".join(_COLUMNS)


def _base_session(value: Any) -> str:
    return str(value or "").split(":", 1)[0]


def _record(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    values = dict(row) if isinstance(row, Mapping) else dict(zip(_COLUMNS, row))
    for key in ("parameters", "result"):
        raw = values.get(key)
        if isinstance(raw, str):
            raw = json.loads(raw)
        values[key] = dict(raw) if isinstance(raw, Mapping) else {}
    return {key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in values.items()}


class CalculationStorage:
    def __init__(self, persistence=None):
        self.persistence = persistence if persistence is not None else artifact_registry.persistence

    def _query(self, sql: str, params: tuple = (), *, write: bool = False) -> list[dict]:
        connection = None
        try:
            factory = getattr(self.persistence, "connection_factory", None)
            if factory is None:
                raise PersistenceWriteError("calculation history requires PostgreSQL persistence")
            connection = factory()
            rows = connection.execute(sql, params).fetchall()
            if write:
                connection.commit()
            return [_record(row) for row in rows]
        except Exception as exc:
            if connection is not None and write:
                try:
                    connection.rollback()
                except Exception:
                    pass
            raise PersistenceWriteError("calculation history persistence failed") from exc
        finally:
            if connection is not None:
                connection.close()

    def start_run(self, owner_id: str, dataset_version_id: str, request_id: str | None,
                  parameters: dict, formula: str | None = None) -> dict:
        if not str(owner_id or "").strip() or not str(dataset_version_id or "").strip():
            raise ValueError("owner_id and dataset_version_id are required")
        scope = parameters.get("scope", {})
        if not isinstance(scope, Mapping) or not scope.get("classification"):
            raise ValueError("calculation scope is required")
        if not isinstance(scope.get("department_ids"), list):
            raise ValueError("calculation department_ids are required")
        parameters = dict(parameters)
        parameters["scope"] = dict(scope, visibility="private")
        run_id = "calc_" + uuid.uuid4().hex
        rows = self._query(
            "INSERT INTO calculation_runs "
            "(calculation_run_id,owner_id,dataset_version_id,request_id,status,formula,parameters,started_at) "
            f"VALUES (%s,%s,%s,%s,'running',%s,%s::jsonb,NOW()) RETURNING {_SELECT}",
            (run_id, str(owner_id), str(dataset_version_id), request_id or None, formula,
             json.dumps(parameters, ensure_ascii=False, allow_nan=False, default=str)), write=True,
        )
        return rows[0]

    def _finish(self, run_id: str, status: str, result: dict, error_code: str | None) -> dict:
        rows = self._query(
            "UPDATE calculation_runs SET status=%s,result=%s::jsonb,error_code=%s,completed_at=NOW() "
            f"WHERE calculation_run_id=%s AND status='running' RETURNING {_SELECT}",
            (status, json.dumps(result, ensure_ascii=False, allow_nan=False, default=str),
             error_code, run_id), write=True,
        )
        if rows:
            return rows[0]
        existing = self.get(run_id)
        if existing is None:
            raise ValueError("calculation_run_not_found")
        if existing["status"] != status or existing["result"] != result or existing["error_code"] != error_code:
            raise ValueError("calculation_run_already_finished")
        return existing

    def complete_run(self, run_id: str, result: dict) -> dict:
        return self._finish(run_id, "completed", result, None)

    def fail_run(self, run_id: str, error_code: str) -> dict:
        return self._finish(run_id, "failed", {}, str(error_code))

    def get(self, run_id: str) -> dict | None:
        rows = self._query(f"SELECT {_SELECT} FROM calculation_runs WHERE calculation_run_id=%s", (run_id,))
        return rows[0] if rows else None

    def can_view(self, record: dict, principal: Principal) -> bool:
        # Calculation results are a user's filtered view, not the source dataset's shared contents.
        if record["owner_id"] != principal.user_id and not is_administrator(principal):
            return False
        parameters = record["parameters"]
        if record["owner_id"] == principal.user_id and not is_administrator(principal):
            snapshot = {"role": principal.role, "department": principal.department,
                        "clearance": principal.clearance,
                        "authorization_department_ids": sorted(principal.department_ids)}
            if any(key in parameters and parameters[key] != value for key, value in snapshot.items()):
                return False
        scope = record["parameters"].get("scope", {})
        resource = ResourceScope(
            resource_type="calculation", resource_id=record["calculation_run_id"],
            owner_id=record["owner_id"], department_ids=scope.get("department_ids", []),
            classification=scope.get("classification", ""), visibility="private",
            version_id=record["dataset_version_id"], status=record["status"],
        )
        if not authorization_decision(principal, resource, action=ACTION_VIEW, require_resource_scope=True).allowed:
            return False
        # Historical results survive retirement, but never bypass a tightened input scope.
        source_scope = dataset_registry.scope_for_version(record["dataset_version_id"])
        return authorization_decision(
            principal, source_scope, action=ACTION_VIEW, require_resource_scope=True,
        ).allowed

    def with_artifacts(self, record: dict, principal: Principal, *, candidates=None) -> dict:
        from app.storage.artifacts import artifact_sources_allowed
        candidates = (artifact_registry.list_active(owner_id=record["owner_id"])
                      if candidates is None else candidates)
        session_id = _base_session(record["parameters"].get("session_id"))
        artifacts = []
        for artifact in candidates:
            ids = artifact.metadata.get("calculation_run_ids", [])
            if not isinstance(ids, list) or record["calculation_run_id"] not in ids:
                continue
            if (artifact.owner_id != record["owner_id"] or not record["request_id"]
                    or artifact.request_id != record["request_id"] or not session_id
                    or _base_session(artifact.session_id) != session_id):
                continue
            if authorization_decision(principal, artifact.resource_scope, action=ACTION_VIEW,
                                      require_resource_scope=True).allowed and artifact_sources_allowed(artifact, principal):
                artifacts.append({"artifact_id": artifact.artifact_id, "artifact_type": artifact.artifact_type,
                                  "display_name": artifact.filename, "download_url": artifact.download_url})
        return dict(record, artifacts=artifacts)

    def list_for(self, principal: Principal, *, request_id: str | None = None,
                 trace_id: str | None = None, limit: int = 50) -> list[dict]:
        where, params = [], []
        if not is_administrator(principal):
            where.append("owner_id=%s")
            params.append(principal.user_id)
        if request_id:
            where.append("request_id=%s")
            params.append(request_id)
        if trace_id:
            where.append("parameters->>'trace_id'=%s")
            params.append(trace_id)
        condition = " WHERE " + " AND ".join(where) if where else ""
        limit = max(1, min(int(limit), 100))
        visible, offset = [], 0
        candidates = artifact_registry.list_active()
        while len(visible) < limit:
            rows = self._query(
                f"SELECT {_SELECT} FROM calculation_runs{condition} "
                "ORDER BY created_at DESC,calculation_run_id DESC LIMIT 100 OFFSET %s",
                tuple(params + [offset]),
            )
            for row in rows:
                if self.can_view(row, principal):
                    visible.append(self.with_artifacts(row, principal, candidates=candidates))
                    if len(visible) == limit:
                        break
            if len(rows) < 100:
                break
            offset += 100
        return visible

    def ids_for_turn(self, owner_id: str, session_id: str | None, request_id: str | None) -> list[str]:
        session_id = _base_session(session_id)
        if not owner_id or not session_id or not request_id:
            return []
        rows = self._query(
            f"SELECT {_SELECT} FROM calculation_runs WHERE owner_id=%s AND request_id=%s "
            "AND split_part(COALESCE(parameters->>'session_id',''),':',1)=%s AND status='completed' "
            "ORDER BY created_at,calculation_run_id", (owner_id, request_id, session_id),
        )
        return [row["calculation_run_id"] for row in rows]

    def session_access_denied(self, principal: Principal, session_id: str) -> bool:
        if getattr(self.persistence, "connection_factory", None) is None:
            return False
        rows = self._query(f"SELECT {_SELECT} FROM calculation_runs WHERE owner_id=%s "
            "AND split_part(COALESCE(parameters->>'session_id',''),':',1)=%s AND status='completed'",
            (principal.user_id, _base_session(session_id)))
        return any(not self.can_view(row, principal) for row in rows)


calculation_storage = CalculationStorage()
