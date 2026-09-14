"""Owner-scoped business entity relations.

A relation is a claim about real sources, so every record keeps the Principal that
submitted it, the scope that may read it, and the source locator that justifies it.
"""
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.agents.contracts import Principal, ResourceScope
from app.common.monitoring import ProductionReadOnlyProtection

# A durable store makes relations visible to every worker on this host and survives a
# restart. Without it the graph is a process-local dictionary, so production refuses
# to accept writes instead of pretending the graph is healthy.
_STORE_PATH_ENV = "KNOWLEDGE_GRAPH_STORE_PATH"
_STORE_COLLECTION = "knowledge_graph_relations"
_STORE_ERRORS: dict[str, str] = {}
_PRODUCTION_ENVIRONMENTS = {"production", "prod"}


def _is_production_environment() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


def _resolve_store_path(store_path: "str | Path | None" = None) -> "str | None":
    resolved = str(store_path or os.getenv(_STORE_PATH_ENV, "") or "").strip()
    return resolved or None


@dataclass
class Relation:
    relation_id: str
    source_entity: str
    relation: str
    target: str
    source: str
    owner_id: str
    department_ids: list[str] = field(default_factory=list)
    classification: str = "internal"
    visibility: str = "private"
    status: str = "candidate"
    version: int = 1
    created_at: str = ""

    @property
    def resource_scope(self) -> ResourceScope:
        return ResourceScope(
            resource_type="relation",
            resource_id=self.relation_id,
            owner_id=self.owner_id,
            department_ids=list(self.department_ids),
            classification=self.classification,
            visibility=self.visibility,
            version_id=f"v{self.version}",
            status=self.status,
        )

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["version_id"] = f"v{self.version}"
        return payload


class KnowledgeGraph:
    def __init__(self, store_path: "str | Path | None" = None) -> None:
        self._relations: dict[str, Relation] = {}
        self._lock = RLock()
        self._store_path = _resolve_store_path(store_path)
        self._store_error = ""
        self._store = None
        if self._store_path:
            try:
                from app.storage.persistence import JsonPersistenceAdapter

                self._store = JsonPersistenceAdapter(self._store_path)
            except Exception as exc:  # pragma: no cover - unwritable or missing directory
                self._store_error = f"cannot open relation store: {type(exc).__name__}"
                _STORE_ERRORS[self._store_path] = self._store_error

    # ------------------------------------------------------------------ storage state
    @staticmethod
    def state_for_store(store_path: "str | None", error: str = "") -> dict:
        """Describe the store an instance built on ``store_path`` actually offers."""
        if store_path and not error:
            return {
                "storage_mode": "json",
                "durable": True,
                "shared_across_processes": True,
                "protection": "none",
                "detail": f"relations persisted to collection {_STORE_COLLECTION}",
            }
        if store_path and error:
            return {
                "storage_mode": "unavailable",
                "durable": False,
                "shared_across_processes": False,
                "protection": "read_only",
                "detail": error,
            }
        if _is_production_environment():
            return {
                "storage_mode": "unavailable",
                "durable": False,
                "shared_across_processes": False,
                "protection": "read_only",
                "detail": f"{_STORE_PATH_ENV} is not configured; relation writes are refused",
            }
        return {
            "storage_mode": "memory",
            "durable": False,
            "shared_across_processes": False,
            "protection": "none",
            "detail": "development in-process dictionary",
        }

    def storage_state(self) -> dict:
        return self.state_for_store(self._store_path, self._store_error)

    # ------------------------------------------------------------------- store access
    def _record_failure(self, detail: str) -> None:
        self._store_error = detail
        _STORE_ERRORS[str(self._store_path or "memory")] = detail

    def _persist(self, record: Relation) -> None:
        if self._store is None:
            return
        from app.storage.persistence import PersistenceWriteError

        try:
            self._store.upsert(_STORE_COLLECTION, record.relation_id, asdict(record))
        except (PersistenceWriteError, OSError, ValueError) as exc:
            self._record_failure(f"relation store write failed: {type(exc).__name__}")
            raise ProductionReadOnlyProtection("knowledge_graph_store_write_failed") from exc
        # A successful write clears an earlier failure so health recovers on its own.
        self._store_error = ""
        _STORE_ERRORS.pop(str(self._store_path), None)

    def _sync_from_store(self) -> None:
        """Adopt relations written by another worker or by an earlier run."""
        if self._store is None:
            return
        from app.storage.persistence import PersistenceWriteError

        try:
            records = self._store.list(_STORE_COLLECTION)
        except (PersistenceWriteError, OSError, ValueError) as exc:
            self._record_failure(f"relation store read failed: {type(exc).__name__}")
            return
        known = {item.name for item in fields(Relation)}
        for payload in records:
            if not isinstance(payload, dict):
                continue
            attributes = {key: value for key, value in payload.items() if key in known}
            try:
                record = Relation(**attributes)
            except TypeError:  # pragma: no cover - a corrupted store must not crash reads
                continue
            if not record.relation_id:
                continue
            current = self._relations.get(record.relation_id)
            if current is None or current.version <= record.version:
                self._relations[record.relation_id] = record

    def _reject_in_memory_write(self) -> None:
        """Production only accepts a relation once a durable store can hold it."""
        if self._store is None and _is_production_environment():
            raise ProductionReadOnlyProtection(
                f"knowledge_graph_read_only: {_STORE_PATH_ENV} is required in production"
            )

    def add_relation(
        self,
        source_entity: str,
        relation: str,
        target: str,
        source: str,
        *,
        principal: Principal,
        department_ids: list[str] | None = None,
        classification: str | None = None,
    ) -> Relation:
        """Store one candidate relation owned by the authenticated Principal."""
        owner_id = str(getattr(principal, "user_id", "") or "").strip()
        if not owner_id:
            raise PermissionError("authentication_required")
        if not str(source or "").strip():
            raise ValueError("relation_source_required")

        # A candidate relation may never be marked above its author clearance.
        clearance_level = int(getattr(principal, "clearance", 1) or 1)
        try:
            relation_classification = int(str(classification or clearance_level))
        except ValueError:
            relation_classification = clearance_level
        relation_classification = max(1, min(relation_classification, clearance_level))

        departments = [str(value) for value in (department_ids or []) if str(value)]
        if not departments and str(getattr(principal, "department", "") or ""):
            departments = [str(principal.department)]

        relation_id = uuid4().hex
        record = Relation(
            relation_id=relation_id,
            source_entity=str(source_entity or "").strip(),
            relation=str(relation or "").strip(),
            target=str(target or "").strip(),
            source=str(source or "").strip(),
            owner_id=owner_id,
            department_ids=departments,
            classification=str(relation_classification),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._sync_from_store()
            self._reject_in_memory_write()
            self._relations[relation_id] = record
            self._persist(record)
        return record

    def confirm(self, relation_id: str, *, principal: Principal) -> bool:
        with self._lock:
            self._sync_from_store()
            record = self._relations.get(str(relation_id or ""))
            if record is None:
                return False
            if not self.can_read(record, principal):
                return False
            self._reject_in_memory_write()
            record.status = "confirmed"
            record.version += 1
            self._persist(record)
            return True

    @staticmethod
    def can_read(record: Relation, principal: Principal | None) -> bool:
        from app.common.policy import authorization_decision

        if principal is None:
            return False
        decision = authorization_decision(
            principal,
            record.resource_scope,
            action="resource:view",
            require_resource_scope=True,
        )
        return decision.allowed

    def query(
        self,
        source_entity: str | None = None,
        relation: str | None = None,
        *,
        principal: Principal | None = None,
    ) -> list[dict]:
        """Return only relations the caller is allowed to read; no owner means nothing."""
        if principal is None:
            return []
        with self._lock:
            self._sync_from_store()
            return [
                item.to_dict()
                for item in self._relations.values()
                if (source_entity is None or item.source_entity == source_entity)
                and (relation is None or item.relation == relation)
                and self.can_read(item, principal)
            ]


def knowledge_graph_storage_state() -> dict:
    """State of the default graph store, i.e. what the API process mounts."""
    store_path = _resolve_store_path()
    error = _STORE_ERRORS.get(str(store_path or "memory"), "")
    return KnowledgeGraph.state_for_store(store_path, error)