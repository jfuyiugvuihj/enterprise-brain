"""Owner-scoped business entity relations.

A relation is a claim about real sources, so every record keeps the Principal that
submitted it, the scope that may read it, and the source locator that justifies it.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from app.agents.contracts import Principal, ResourceScope


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
    def __init__(self):
        self._relations: dict[str, Relation] = {}

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
        self._relations[relation_id] = record
        return record

    def confirm(self, relation_id: str, *, principal: Principal) -> bool:
        record = self._relations.get(str(relation_id or ""))
        if record is None:
            return False
        if not self.can_read(record, principal):
            return False
        record.status = "confirmed"
        record.version += 1
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
        return [
            item.to_dict()
            for item in self._relations.values()
            if (source_entity is None or item.source_entity == source_entity)
            and (relation is None or item.relation == relation)
            and self.can_read(item, principal)
        ]