"""Owner-scoped business entity relations: a candidate-assertion ledger, not an engine.

A relation is a claim about real sources, so every record keeps the Principal that
submitted it, the scope that may read it, and the source locator that justifies it.

What this subsystem is allowed to be, stated so that no reader has to infer it from the
absence of a consumer:

* It collects assertions that a human has to check. Nothing here reasons over a graph,
  and no Agent reads it when answering a question - that is a decided positioning
  (docs/design/knowledge-graph-positioning.md), not a missing feature.
* Its only productive exit is promotion: a relation that somebody with approval
  permission has verified against an uploaded document becomes a formal metric
  definition (app/knowledge_graph/promotion.py, migrations/0009_metric_definition_semantics.sql).
  Verification is what the ledger is for, so an author may never certify their own claim:
  a self-declared flag is not evidence.
* Without ``KNOWLEDGE_GRAPH_STORE_PATH`` a production process has no durable store, and
  every write - relation or verification - is refused rather than kept in a dictionary
  that dies with the worker.
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

# Where a relation got to. ``status`` is the record's own life; ``verification_state`` is
# the separate answer to "has a human checked the source", and only that second answer
# gates promotion, so confirming a record (a scope/typo decision by its author) can never
# masquerade as a reconciliation.
STATUS_CANDIDATE = "candidate"
STATUS_CONFIRMED = "confirmed"
STATUS_PROMOTED = "promoted"
STATUS_REJECTED = "rejected"
RELATION_STATUSES = (STATUS_CANDIDATE, STATUS_CONFIRMED, STATUS_PROMOTED, STATUS_REJECTED)

UNVERIFIED = "unverified"
VERIFIED = "verified"
REJECTED = "rejected"
VERIFICATION_OUTCOMES = (VERIFIED, REJECTED)


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
    status: str = STATUS_CANDIDATE
    version: int = 1
    created_at: str = ""
    # Review bookkeeping. Every default is the untouched state, so records written before
    # this existed load unchanged out of a JSON store that has no such keys.
    verification_state: str = UNVERIFIED
    verified_document: str = ""
    verified_section: str = ""
    verified_by: str = ""
    verified_at: str = ""
    verification_note: str = ""
    promoted_definition_id: str = ""

    @property
    def verified(self) -> bool:
        """True only for a relation whose certification names a document and a section."""
        return self.verification_state == VERIFIED and bool(
            self.verified_document and self.verified_section and self.verified_by
        )

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

    def get(self, relation_id: str, *, principal: Principal | None = None) -> Relation | None:
        """One readable relation, or None. An unreadable id and an unknown id look alike."""
        with self._lock:
            self._sync_from_store()
            record = self._relations.get(str(relation_id or ""))
            if record is None or not self.can_read(record, principal):
                return None
            return record

    def confirm(self, relation_id: str, *, principal: Principal) -> bool:
        """Author-side tidying of a record: it says the claim is well-formed, not checked."""
        with self._lock:
            self._sync_from_store()
            record = self._relations.get(str(relation_id or ""))
            if record is None:
                return False
            if not self.can_read(record, principal):
                return False
            self._reject_in_memory_write()
            record.status = STATUS_CONFIRMED
            record.version += 1
            self._persist(record)
            return True

    # --------------------------------------------------------------- review and promotion
    @staticmethod
    def _require_approval(principal: Principal | None) -> str:
        """The reviewer identity behind an approval action, or the refusal that says why."""
        from app.common.permissions import ACTION_APPROVE

        verifier = str(getattr(principal, "user_id", "") or "").strip()
        if not verifier:
            raise PermissionError("authentication_required")
        if ACTION_APPROVE not in set(getattr(principal, "permissions", None) or ()):
            raise PermissionError("approval_permission_required")
        return verifier

    def _look_up(self, relation_id: str) -> Relation:
        self._sync_from_store()
        record = self._relations.get(str(relation_id or ""))
        if record is None:
            raise LookupError("relation_not_found")
        return record

    def reviewable(self, relation_id: str, *, principal: Principal) -> Relation:
        """One verified relation this principal is allowed to act on.

        Promotion has to write the definition row before it can close the ledger, so the
        three questions (does it exist, may you read it, may you approve) must be answered
        before any write happens. record_verification and record_promotion ask them again
        rather than trusting this answer, because the lock is not held between calls.
        """
        with self._lock:
            record = self._look_up(relation_id)
            self._require_approval(principal)
            if not self.can_read(record, principal):
                raise PermissionError("permission_denied")
            if not record.verified:
                raise ValueError("relation_not_verified")
            return record

    def record_verification(
        self,
        relation_id: str,
        *,
        principal: Principal,
        outcome: str = VERIFIED,
        document: str = "",
        section: str = "",
        note: str = "",
    ) -> Relation:
        """Record what a reviewer concluded about one relation's source.

        The reviewer needs ``resource:approve`` and must be able to read the relation, so
        a cross-department certification is refused by the same rule that hides it. The
        author may not review their own record: the point of this ledger is that a claim
        gets checked by somebody else, and a self-declared flag is not evidence.

        A verification names the document and the section it was checked against, because
        "verified" without a locator is what the semantic layer already had and could not
        remove. A rejection records who said no and when, and deliberately keeps the
        verified_document/verified_section pair empty: nothing was certified.

        Stable codes: relation_not_found, authentication_required,
        approval_permission_required, permission_denied, self_verification_refused,
        relation_verification_evidence_required, relation_verification_outcome.
        """
        if outcome not in VERIFICATION_OUTCOMES:
            raise ValueError("relation_verification_outcome")
        with self._lock:
            record = self._look_up(relation_id)
            # Authenticate and authorise the action first, then the data scope: an
            # anonymous or unauthorised caller learns about the permission they lack, and
            # only a legitimate reviewer learns whether this record is out of scope.
            verifier = self._require_approval(principal)
            if not self.can_read(record, principal):
                raise PermissionError("permission_denied")
            if record.owner_id and record.owner_id == verifier:
                raise PermissionError("self_verification_refused")
            checked_document = str(document or "").strip()
            checked_section = str(section or "").strip()
            if outcome == VERIFIED and not (checked_document and checked_section):
                raise ValueError("relation_verification_evidence_required")
            self._reject_in_memory_write()
            record.verification_state = outcome
            record.verified_by = verifier
            record.verified_at = datetime.now(timezone.utc).isoformat()
            record.verified_document = checked_document if outcome == VERIFIED else ""
            record.verified_section = checked_section if outcome == VERIFIED else ""
            record.verification_note = str(note or "").strip()
            if outcome == REJECTED:
                record.status = STATUS_REJECTED
            elif record.status != STATUS_PROMOTED:
                # Already-promoted records keep their status: the definition they became is
                # the fact, and a later re-check does not undo the lineage link.
                record.status = STATUS_CONFIRMED
            record.version += 1
            self._persist(record)
            return record

    def record_promotion(
        self,
        relation_id: str,
        *,
        principal: Principal,
        definition_id: str,
    ) -> Relation:
        """Close the loop: this relation is now a formal definition with this key.

        Promotion is only ever recorded after the definition row exists, and only for a
        relation a reviewer verified, so the ledger and the catalog cannot disagree about
        what became what.
        """
        definition = str(definition_id or "").strip()
        if not definition:
            raise ValueError("relation_definition_id_required")
        with self._lock:
            record = self._look_up(relation_id)
            self._require_approval(principal)
            if not self.can_read(record, principal):
                raise PermissionError("permission_denied")
            if not record.verified:
                raise ValueError("relation_not_verified")
            # Re-promotion is allowed and keeps the latest key: a definition revised under a
            # new definition_version is a new row, and metric_definitions carries
            # source_relation_id on every one of them, so the table - not this single
            # pointer - is the authority on "which definitions came from this relation".
            self._reject_in_memory_write()
            record.status = STATUS_PROMOTED
            record.promoted_definition_id = definition
            record.version += 1
            self._persist(record)
            return record

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