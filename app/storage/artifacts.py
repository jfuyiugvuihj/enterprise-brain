"""Durable metadata and delivery boundary for generated artifacts.

R248 moved this registry off its own JSON sidecar and onto the canonical ``artifacts``
table (``migrations/0001_core_resource_versions.sql``). The table is the only source of
truth: every read asks it, every write goes through it, and nothing is kept in a private
copy between calls. Stable id, owner and lifecycle are columns - ``artifact_id``,
``owner_id`` and ``status`` / ``created_at`` / ``expires_at`` / ``deleted_at`` - rather
than keys inside a JSON blob, which is what roadmap V2 asks for.

What ``static/.artifact-metadata.json`` is now: a read-once import source, because a
deployment has bytes already registered under the old scheme. Nothing in this module
opens it for writing, and an import never overwrites a row the table already answers for
- the sidecar stopped being updated, so replaying it would turn a retired artifact back
into an active one.

Two limits stated rather than discovered:

* Which store is behind ``persistence`` is decided by ``build_persistence_adapter()``:
  PostgreSQL when ``PERSISTENCE_BACKEND=postgres`` (the shipped target), the shared
  control-plane journal otherwise. ``app/storage/persistence.py`` owns that switch; what
  this ticket removed is the *second*, per-registry copy this module used to keep.
* ``persistence=None`` selects :class:`InProcessArtifactStore`, durable for neither a
  restart nor a second worker. It exists so a caller that explicitly declines storage
  (the test registries) still sees one consistent view of its own rows. It is not a
  deployment option, and ``tests/test_r248_artifact_table_source.py`` pins that the
  shipped singleton never falls back to it.

Authorization is unchanged and lives elsewhere: ``resource_scope`` still hands the same
``ResourceScope`` to ``app.common.policy.authorization_decision``, and ``app/common/rbac.py``
remains the only source of the clearance and row-scope rules. This module calls those, it
does not restate them.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import uuid
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from app.agents.contracts import Principal, ResourceScope
from app.common.logger import logger
from app.storage.persistence import PersistenceWriteError, build_persistence_adapter

#: The collection name of the canonical table, and the ``resource_type`` its rows carry.
ARTIFACT_COLLECTION = "artifacts"
ARTIFACT_RESOURCE_TYPE = "artifact"

#: The sidecar this registry used to own. Read once at construction; never written again.
LEGACY_METADATA_NAME = ".artifact-metadata.json"

#: The columns of ``artifacts``, exactly as migration 0001 declares them.
#: ``tests/test_r248_artifact_column_alignment.py`` compares this tuple, the field set of
#: :class:`ArtifactRecord` and the ``CREATE TABLE`` text against each other, so a column
#: the code never writes and a field no column can hold are both a red instead of a
#: surprise found the first time a restore is attempted.
ARTIFACT_COLUMNS = (
    "artifact_id",
    "owner_id",
    "resource_type",
    "resource_id",
    "source_version_id",
    "storage_key",
    "content_sha256",
    "status",
    "expires_at",
    "deleted_at",
    "created_at",
    "metadata",
)

#: The scope dimensions the ``artifacts`` table has no column for. They travel inside the
#: ``metadata`` jsonb, which is the only place this table can hold them - inventing a
#: second identity concept for them is what this list exists to prevent.
SCOPE_METADATA_KEYS = (
    "artifact_type",
    "filename",
    "department_ids",
    "classification",
    "visibility",
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_datetime(value: Any) -> datetime | None:
    """One instant, however the store surfaced it: a ``TIMESTAMPTZ`` or ISO text.

    A naive timestamp stays an error on purpose. ``expires_at`` is compared against the
    wall clock to decide whether bytes may still be handed out, and "noon" in an
    unspecified zone is not an answer to that question.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("artifact timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def _to_iso(value: Any) -> str | None:
    """Fold every timestamp leg onto one canonical UTC ISO string.

    PostgreSQL answers a ``TIMESTAMPTZ`` column with a ``datetime`` and the control-plane
    journal answers with the text it was given. Left as is, "did this record survive the
    restart" becomes a question about Python types, so both legs are normalized here -
    before the write as well as after the read, which is why a row this module stores
    reads back byte-identical.
    """
    parsed = _as_datetime(value)
    return None if parsed is None else parsed.isoformat()


def _as_mapping(value: Any) -> dict[str, Any]:
    """Read the ``metadata`` column whichever shape the backend used (jsonb, text, dict)."""
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (str, bytes, bytearray)):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("[Artifacts] metadata column is not readable JSON; scope treated as empty")
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ArtifactRecord:
    """One row of the ``artifacts`` table, with its fields named after its columns.

    The scope dimensions the table keeps inside ``metadata`` are exposed as the attributes
    the delivery code already reads - ``artifact_type``, ``filename``, ``storage_path``,
    ``department_ids``, ``classification``, ``visibility``. They are views of stored
    columns, not a second set of state that could disagree with the row: which is also why
    ``dataclasses.fields()`` of this class and the ``CREATE TABLE`` column list are
    expected to be the same set (R248 J-2).
    """

    artifact_id: str
    owner_id: str
    resource_type: str
    resource_id: str
    storage_key: str
    content_sha256: str
    status: str
    created_at: str
    source_version_id: str | None = None
    expires_at: str | None = None
    deleted_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def artifact_type(self) -> str:
        return str(self.metadata.get("artifact_type") or "")

    @property
    def filename(self) -> str:
        stored = str(self.metadata.get("filename") or "")
        return stored or Path(self.storage_key).name

    @property
    def storage_path(self) -> str:
        """The delivery path: the ``storage_key`` column under another name.

        Kept because every caller of this registry - the content route, the delete route,
        the export route - reads ``storage_path``. Renaming it here would be a second
        change with no bearing on where the bytes are.
        """
        return self.storage_key

    @property
    def department_ids(self) -> list[str]:
        values = self.metadata.get("department_ids")
        if not isinstance(values, (list, tuple, set)):
            return []
        return sorted({str(value) for value in values if str(value)})

    @property
    def classification(self) -> str:
        return str(self.metadata.get("classification") or "internal")

    @property
    def visibility(self) -> str:
        return str(self.metadata.get("visibility") or "private")

    @property
    def content_url(self) -> str:
        return f"/api/v1/artifacts/{self.artifact_id}/content"

    @property
    def download_url(self) -> str:
        return f"/api/v1/artifacts/{self.artifact_id}/download"

    @property
    def resource_scope(self) -> ResourceScope:
        return ResourceScope(
            resource_type="artifact",
            resource_id=self.artifact_id,
            owner_id=self.owner_id,
            department_ids=list(self.department_ids),
            classification=self.classification,
            visibility=self.visibility,
            version_id=self.source_version_id,
            status=self.status,
        )

    @property
    def media_type(self) -> str:
        return mimetypes.guess_type(self.filename)[0] or "application/octet-stream"

    def is_active(self, now: datetime | None = None) -> bool:
        if self.status != "active":
            return False
        expiry = _as_datetime(self.expires_at)
        return expiry is None or expiry > (now or _utc_now())

    def public_payload(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "content_url": self.content_url,
            "download_url": self.download_url,
            "expires_at": self.expires_at,
        }


class InProcessArtifactStore:
    """Rows held for the life of the process, for callers that decline durable storage.

    It mirrors the shape of the persistence adapters - ``upsert``/``get``/``list`` over a
    collection name, the same refusal of an ``artifacts`` row with no owner, copies handed
    back so a caller cannot mutate a stored row through a record - so a registry built on it
    behaves the way it behaves on the table, only with the table missing.

    That is also its whole limit: a restart loses it and a second worker never sees it,
    which is the failure R248 was written to remove. Production passes
    ``build_persistence_adapter()``; nothing here is a substitute for that, and the shipped
    singleton is pinned not to use it.
    """

    #: Read by callers that have to say honestly whether a record outlives this process.
    durable = False

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def _collection(self, collection: str) -> str:
        name = str(collection or "").strip()
        if name != ARTIFACT_COLLECTION:
            raise ValueError(f"unsupported in-process collection: {name}")
        return name

    def upsert(self, collection: str, record_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
        self._collection(collection)
        if not str(record.get("owner_id") or "").strip():
            raise ValueError("owner_id is required for protected records")
        row = deepcopy(dict(record))
        row["artifact_id"] = str(record_id)
        with self._lock:
            self._rows[row["artifact_id"]] = row
        # 交回副本：调用方改 returned["metadata"] 不许顺着改到存着的那一行。
        return deepcopy(row)

    def get(self, collection: str, record_id: str) -> dict[str, Any] | None:
        self._collection(collection)
        with self._lock:
            row = self._rows.get(str(record_id))
        return deepcopy(row) if row is not None else None

    def list(self, collection: str) -> list[dict[str, Any]]:
        self._collection(collection)
        with self._lock:
            rows = [deepcopy(row) for row in self._rows.values()]
        # Same order the adapters answer in, so a registry cannot depend on insertion order.
        return sorted(rows, key=lambda row: _to_iso(row.get("created_at")) or "", reverse=True)


def _to_row(record: ArtifactRecord) -> dict[str, Any]:
    """One record as the table wants it: every column, named, including the nullable ones.

    The key set *is* :data:`ARTIFACT_COLUMNS`, which is what makes "the table is the source
    of truth" a checkable statement rather than a claim - a column dropped here is a value
    that quietly stops surviving a restart, and
    ``tests/test_r248_artifact_column_alignment.py`` fails on that.
    """
    return {
        "artifact_id": record.artifact_id,
        "owner_id": record.owner_id,
        "resource_type": record.resource_type or ARTIFACT_RESOURCE_TYPE,
        "resource_id": record.resource_id or record.artifact_id,
        "source_version_id": record.source_version_id,
        "storage_key": record.storage_key,
        "content_sha256": record.content_sha256,
        "status": record.status,
        "expires_at": record.expires_at,
        "deleted_at": record.deleted_at,
        "created_at": record.created_at,
        # 深拷贝：``dict(metadata)`` 只挡一层，部门列表仍会与记录共享同一枚对象。
        "metadata": deepcopy(record.metadata),
    }


class ArtifactRegistry:
    """The ``artifacts`` table, read on every call and written on every change.

    There is no cache of records behind this class: ``get`` and ``list_active`` ask the
    store each time, so a second worker and the next restart answer with the same rows, and
    a record retired by one of them cannot be served from another's memory. ``_lock``
    serializes a write with its own read-back inside this process; it is not cross-process
    concurrency control and does not claim to be - the table is what two processes
    reconcile against.
    """

    def __init__(
        self,
        root: str | Path,
        metadata_path: str | Path | None = None,
        persistence=None,
        *,
        import_legacy_metadata: bool = True,
    ):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path = Path(metadata_path or self.root / LEGACY_METADATA_NAME).resolve()
        self._lock = RLock()
        self.persistence = persistence if persistence is not None else InProcessArtifactStore()
        #: Read-only import accounting for the retired sidecar (R248): what was carried
        #: into the table, what the table already answered for, what was unreadable.
        self.legacy_imported = 0
        self.legacy_skipped = 0
        self.legacy_rejected = 0
        if import_legacy_metadata:
            self._import_legacy_metadata()

    def _contained_path(self, value: str | Path, *, must_exist: bool) -> Path:
        path = Path(value).resolve(strict=must_exist)
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("artifact storage path escapes registry root") from exc
        return path

    # --------------------------------------------------------------- the retired sidecar
    def _import_legacy_metadata(self) -> None:
        """Copy the retired JSON sidecar into the table once, then never write to it.

        The file is opened with ``read_text`` and nothing in this module can create, rename
        or replace it (pinned by ``tests/test_r248_json_writepoints.py``). A row the store
        already answers for is *skipped*, not overwritten: the table is the source of truth
        and the sidecar stopped being updated when writes moved, so replaying it over a
        live row would turn a retired artifact back into an active one.

        Failures are logged and counted rather than raised. This runs while the module is
        imported, and a malformed file left over from the old scheme is not a reason the
        platform cannot start.
        """
        if not self.metadata_path.exists():
            return
        try:
            payload = _as_mapping(json.loads(self.metadata_path.read_text(encoding="utf-8")))
            entries = payload.get("artifacts", [])
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning(
                f"[Artifacts] legacy sidecar could not be read, import skipped: {type(exc).__name__}: {exc}"
            )
            return
        if not isinstance(entries, list):
            logger.warning("[Artifacts] legacy sidecar has no artifact list, import skipped")
            return
        for raw in entries:
            record = self._coerce_record(raw)
            if record is None:
                self.legacy_rejected += 1
                continue
            with self._lock:
                if self.persistence.get(ARTIFACT_COLLECTION, record.artifact_id) is not None:
                    self.legacy_skipped += 1
                    continue
                self.persistence.upsert(ARTIFACT_COLLECTION, record.artifact_id, _to_row(record))
                self.legacy_imported += 1
        if self.legacy_imported or self.legacy_rejected:
            logger.warning(
                f"[Artifacts] legacy sidecar import: {self.legacy_imported} carried into the "
                f"{ARTIFACT_COLLECTION} table, {self.legacy_skipped} already present, "
                f"{self.legacy_rejected} rejected"
            )

    # ------------------------------------------------------------------ rows <-> records
    def _coerce_record(self, raw: Any) -> ArtifactRecord | None:
        """Build a record from a stored row, or from one entry of the retired sidecar.

        Both shapes arrive here because both were written by this module. The flat keys
        (``storage_path``, ``artifact_type``, ``department_ids`` ...) belong to the sidecar;
        the column names belong to the table. Nothing else accepts the flat vocabulary, so
        the format that is being retired stays confined to this function.

        A row that cannot be described is refused rather than delivered: no id, no owner,
        no digest or a ``storage_key`` outside the registry root is not a weakened record,
        it is a record this process should not hand bytes for.
        """
        if not isinstance(raw, Mapping):
            return None
        metadata = _as_mapping(raw.get("metadata"))
        scope: dict[str, Any] = {}
        for key in SCOPE_METADATA_KEYS:
            if key in metadata:
                scope[key] = metadata[key]
            elif key in raw:
                scope[key] = raw[key]
        artifact_id = str(raw.get("artifact_id") or "")
        storage_key = str(raw.get("storage_key") or raw.get("storage_path") or "")
        try:
            record = ArtifactRecord(
                artifact_id=artifact_id,
                owner_id=str(raw.get("owner_id") or ""),
                resource_type=str(raw.get("resource_type") or ARTIFACT_RESOURCE_TYPE),
                resource_id=str(raw.get("resource_id") or artifact_id),
                storage_key=storage_key,
                content_sha256=str(raw.get("content_sha256") or ""),
                status=str(raw.get("status") or ""),
                created_at=_to_iso(raw.get("created_at")) or "",
                source_version_id=str(raw["source_version_id"]) if raw.get("source_version_id") else None,
                expires_at=_to_iso(raw.get("expires_at")),
                deleted_at=_to_iso(raw.get("deleted_at")),
                metadata=scope,
            )
        except (TypeError, ValueError) as exc:
            logger.warning(
                f"[Artifacts] artifact {artifact_id or '<missing id>'} is unreadable: "
                f"{type(exc).__name__}: {exc}"
            )
            return None
        missing = [
            name
            for name, value in (
                ("artifact_id", record.artifact_id),
                ("owner_id", record.owner_id),
                ("status", record.status),
                ("storage_key", record.storage_key),
                ("content_sha256", record.content_sha256),
            )
            if not value
        ]
        if missing:
            logger.warning(
                f"[Artifacts] artifact {artifact_id or '<missing id>'} refused: required "
                f"column(s) empty: {', '.join(missing)}"
            )
            return None
        try:
            self._contained_path(record.storage_key, must_exist=False)
        except ValueError as exc:
            logger.warning(f"[Artifacts] artifact {record.artifact_id} refused: {exc}")
            return None
        return record

    def _read(self, artifact_id: str) -> ArtifactRecord | None:
        row = self.persistence.get(ARTIFACT_COLLECTION, str(artifact_id))
        if row is None:
            return None
        record = self._coerce_record(row)
        if record is None:
            logger.warning(f"[Artifacts] stored row {artifact_id} is not deliverable and was skipped")
        return record

    def _read_all(self) -> list[ArtifactRecord]:
        records = []
        for row in self.persistence.list(ARTIFACT_COLLECTION) or []:
            record = self._coerce_record(row)
            if record is not None:
                records.append(record)
        return records

    def _write(self, record: ArtifactRecord) -> ArtifactRecord:
        """Store one row, then hand back what the store says about it.

        The read-back is the point, not a spare query. ``register`` used to return the
        object it had just built, which let the write shape and the read shape drift apart
        without anything noticing - the exact failure this ticket exists to remove. If a
        row is not there after its write was accepted, the write did not land, and that is
        reported as a persistence failure rather than answered with an artifact nobody can
        find again.
        """
        self.persistence.upsert(ARTIFACT_COLLECTION, record.artifact_id, _to_row(record))
        stored = self._read(record.artifact_id)
        if stored is None:
            raise PersistenceWriteError(
                f"artifact row {record.artifact_id} is not readable after its write was accepted"
            )
        return stored

    def register(
        self,
        storage_path: str | Path,
        *,
        artifact_type: str,
        principal: Principal,
        classification: str = "internal",
        visibility: str = "private",
        source_version_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> ArtifactRecord:
        if principal.status != "active" or not principal.user_id:
            raise PermissionError("active principal is required to create an artifact")
        if not artifact_type.strip():
            raise ValueError("artifact type is required")
        path = self._contained_path(storage_path, must_exist=True)
        departments = sorted(
            {
                value
                for value in [principal.department, *principal.department_ids]
                if value
            }
        )
        if not departments:
            raise ValueError("artifact owner must have a department scope")
        if expires_at is not None and expires_at.tzinfo is None:
            raise ValueError("artifact expiry must include a timezone")

        artifact_id = uuid.uuid4().hex
        record = ArtifactRecord(
            artifact_id=artifact_id,
            owner_id=str(principal.user_id),
            resource_type=ARTIFACT_RESOURCE_TYPE,
            resource_id=artifact_id,
            source_version_id=source_version_id,
            storage_key=str(path),
            content_sha256=_hash_file(path),
            status="active",
            created_at=_to_iso(_utc_now()) or "",
            expires_at=_to_iso(expires_at),
            deleted_at=None,
            metadata={
                "artifact_type": artifact_type,
                "filename": path.name,
                "department_ids": departments,
                "classification": classification,
                "visibility": visibility,
            },
        )
        with self._lock:
            return self._write(record)

    # ------------------------------------------------------------------------ read paths
    # ``get`` answers for any id and ``get_active`` for one id; the access rule is not
    # restated in either, it is ``app.common.policy.authorization_decision``'s.

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        """Read one row back from the table, or ``None`` when there is no such row.

        A store that cannot answer raises: when the source of truth is unreachable, "there
        is no such artifact" is a statement about the table and this module is not allowed
        to make it up. The delivery routes turn that into a 500, which is the honest
        reading of an outage; a 404 would report a deletion nobody performed.
        """
        with self._lock:
            return self._read(artifact_id)

    def get_active(self, artifact_id: str) -> ArtifactRecord | None:
        record = self.get(artifact_id)
        if record is None or not record.is_active():
            return None
        path = self._contained_path(record.storage_path, must_exist=False)
        if not path.is_file():
            return None
        return record

    def list_active(
        self,
        *,
        artifact_type: str | None = None,
        owner_id: str | None = None,
    ) -> list[ArtifactRecord]:
        """Every record that could actually be delivered right now, newest first.

        ``get`` answers for any id and ``get_active`` for one id; a list needs the same
        two liveliness checks ``get_active`` already makes - the record has not been
        retired, has not expired, and its bytes are still on disk - because a catalogue
        that advertises an artifact which 404s on open has described a state this process
        did not produce. Deciding *who* may see a record stays out of here on purpose:
        that is the policy's job, and a second copy of the access rule in the registry is
        how two chains start disagreeing.
        """
        with self._lock:
            candidates = [
                record
                for record in self._read_all()
                if record.status == "active"
                and (artifact_type is None or record.artifact_type == artifact_type)
                and (owner_id is None or record.owner_id == str(owner_id))
            ]
        deliverable = [
            record
            for record in candidates
            if record.is_active()
            and self._contained_path(record.storage_path, must_exist=False).is_file()
        ]
        return sorted(deliverable, key=lambda item: (item.created_at, item.artifact_id), reverse=True)

    def soft_delete(self, artifact_id: str) -> bool:
        """Retire the row: ``status`` flips to ``deleted``, the row itself stays.

        Erasing it would take the audit trail with it, which is what the delete route
        reconstructs its ``before_summary`` from. ``deleted_at`` is stamped because the
        table has the column; whether it comes back depends on the store (see
        :func:`_to_row`), so ``status`` remains the lifecycle fact every read path tests.
        """
        with self._lock:
            record = self._read(artifact_id)
            if record is None or record.status != "active":
                return False
            record.status = "deleted"
            record.deleted_at = _to_iso(_utc_now())
            self._write(record)
            return True


_STATIC_ROOT = Path(__file__).resolve().parents[2] / "static"
#: The control-plane store the shipped registry reads and writes: the ``artifacts`` table
#: when ``PERSISTENCE_BACKEND=postgres``, the shared journal otherwise. Never
#: :class:`InProcessArtifactStore` - that one exists only for a caller that asks for it by
#: passing no store at all, and tests/test_r248_artifact_table_source.py holds that line.
_PERSISTENCE = build_persistence_adapter()
artifact_registry = ArtifactRegistry(_STATIC_ROOT, persistence=_PERSISTENCE)


def register_artifact(
    storage_path: str | Path,
    *,
    artifact_type: str,
    principal: Principal,
    classification: str = "internal",
    visibility: str = "private",
    source_version_id: str | None = None,
    expires_at: datetime | None = None,
) -> ArtifactRecord:
    return artifact_registry.register(
        storage_path,
        artifact_type=artifact_type,
        principal=principal,
        classification=classification,
        visibility=visibility,
        source_version_id=source_version_id,
        expires_at=expires_at,
    )
