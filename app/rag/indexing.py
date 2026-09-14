"""Versioned index publication with atomic local metadata and rollback.

The local JSON metadata file is the authority for what this process believes is
published. ``PostgresIndexStore`` mirrors one publication into ``index_registry``,
``index_versions`` and ``chunks`` inside a single database transaction, so a publication
that fails halfway leaves neither a published version nor a stranded chunk row behind.
Chroma stays the only retrieval path: this module records chunks, it never embeds them,
and every row it writes leaves ``chunks.embedding`` NULL.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from uuid import uuid4

from app.common.logger import logger

RESOURCE_TYPE_DOCUMENT = "document"
INDEX_BACKEND = "chroma"
INDEX_METADATA_ENV = "INDEX_METADATA_PATH"
DEFAULT_INDEX_METADATA_PATH = "./data/index-versions.json"

# What the mirror needs to be able to write at all. An unmigrated database is a
# deployment state, not a failed upload: a document that already reached Chroma must not
# be reported as unparsable because index bookkeeping tables are missing, so the mirror
# degrades with a warning and the publication stays local.
_MIRROR_TABLES = ("index_registry", "index_versions", "chunks", "resource_versions")
_MIRROR_COLUMNS = {
    "index_registry": (
        "index_id",
        "owner_id",
        "resource_type",
        "status",
        "current_version_id",
        "metadata",
    ),
    "index_versions": (
        "index_version_id",
        "index_id",
        "owner_id",
        "source_version_id",
        "backend",
        "chunk_count",
        "checksum",
        "status",
        "published_at",
        "superseded_at",
        "metadata",
    ),
    "chunks": (
        "chunk_id",
        "owner_id",
        "resource_type",
        "resource_id",
        "resource_version_id",
        "index_version_id",
        "content",
        "metadata",
    ),
    "resource_versions": (
        "resource_type",
        "resource_id",
        "version_id",
        "owner_id",
        "department_ids",
        "classification",
        "visibility",
        "status",
        "content_sha256",
        "metadata",
        "superseded_at",
    ),
}
_COUNTER_TABLES = ("documents", "document_versions")
_COUNTER_COLUMN = "chunk_count"
_SCHEMA_SQL = "SELECT table_name, column_name FROM information_schema.columns WHERE table_name = ANY(%s)"
_INSERT_CHUNK_SQL = """
INSERT INTO chunks
(chunk_id, owner_id, resource_type, resource_id, resource_version_id, index_version_id, content, metadata)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
ON CONFLICT (chunk_id) DO UPDATE SET
    owner_id = COALESCE(EXCLUDED.owner_id, chunks.owner_id),
    content = EXCLUDED.content,
    index_version_id = EXCLUDED.index_version_id,
    metadata = EXCLUDED.metadata
"""


def default_metadata_path() -> str:
    return str(os.getenv(INDEX_METADATA_ENV, DEFAULT_INDEX_METADATA_PATH) or DEFAULT_INDEX_METADATA_PATH)


def document_index_id(filename: str) -> str:
    """One index stream per logical document, keyed the way the catalog keys one."""
    return f"{RESOURCE_TYPE_DOCUMENT}:{filename}"


def document_resource_version_id(filename: str, version: int) -> str:
    """The catalog key of one stored version, in the shape the sidecar already uses."""
    return f"{filename}|v{int(version)}"


def index_chunk_id(resource_version_id: str, ordinal: int) -> str:
    return f"{resource_version_id}#{int(ordinal)}"


def _scope_int(value, default: int = 1) -> int:
    """Read a scope integer without trusting the caller's form binding.

    The upload route is also called in-process, where a FastAPI ``Form`` default is still
    a descriptor object rather than the value it declares. A publication must record a
    usable scope or fall back to the public default, never carry the object itself.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _scope_text(value) -> str:
    return value if isinstance(value, str) else ""


def _json_value(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


@dataclass
class IndexVersion:
    index_version_id: str
    index_id: str
    source_version_id: str
    backend: str
    chunk_count: int
    checksum: str
    status: str
    created_at: str
    published_at: str | None = None
    retirement: bool = False


class IndexRegistry:
    def __init__(self, metadata_path: str | Path):
        self.metadata_path = Path(metadata_path).resolve()
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._versions: dict[str, IndexVersion] = {}
        self._current: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.metadata_path.exists():
            return
        payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        self._versions = {
            raw["index_version_id"]: IndexVersion(**raw)
            for raw in payload.get("versions", [])
        }
        self._current = {
            str(key): str(value)
            for key, value in (payload.get("current") or {}).items()
        }

    def _save(self) -> None:
        payload = {
            "versions": [asdict(version) for version in self._versions.values()],
            "current": self._current,
        }
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.metadata_path.name}.",
            suffix=".tmp",
            dir=self.metadata_path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.metadata_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def create_version(
        self,
        *,
        index_id: str,
        source_version_id: str,
        backend: str,
        chunk_count: int,
        checksum: str,
        retirement: bool = False,
    ) -> IndexVersion:
        if not index_id.strip() or not source_version_id.strip():
            raise ValueError("index_id and source_version_id are required")
        if backend not in {"chroma", "pgvector"}:
            raise ValueError("unsupported index backend")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("index checksum must be a SHA-256 hex digest")
        if retirement and int(chunk_count) != 0:
            raise ValueError("a retirement index version carries zero chunks")
        version = IndexVersion(
            index_version_id=f"{index_id}:v{uuid4().hex}",
            index_id=index_id,
            source_version_id=source_version_id,
            backend=backend,
            chunk_count=int(chunk_count),
            checksum=checksum,
            status="building",
            created_at=datetime.now(timezone.utc).isoformat(),
            retirement=bool(retirement),
        )
        with self._lock:
            self._versions[version.index_version_id] = version
            self._save()
        return version

    def validate(self, index_version_id: str) -> IndexVersion:
        with self._lock:
            version = self._versions[index_version_id]
            if not version.retirement and version.chunk_count <= 0:
                raise ValueError("index chunk_count must be greater than zero")
            if version.chunk_count < 0:
                raise ValueError("index chunk_count must not be negative")
            if not re.fullmatch(r"[0-9a-f]{64}", version.checksum):
                raise ValueError("index checksum is invalid")
            version.status = "validated"
            self._save()
            return version

    def publish(self, index_version_id: str) -> IndexVersion:
        with self._lock:
            version = self.validate(index_version_id)
            previous_id = self._current.get(version.index_id)
            if previous_id and previous_id in self._versions:
                self._versions[previous_id].status = "superseded"
            version.status = "published"
            version.published_at = datetime.now(timezone.utc).isoformat()
            self._current[version.index_id] = version.index_version_id
            self._save()
            return version

    def current(self, index_id: str) -> IndexVersion:
        with self._lock:
            version_id = self._current.get(index_id)
            if not version_id:
                raise KeyError(index_id)
            return self._versions[version_id]

    def rollback(self, index_id: str, index_version_id: str) -> IndexVersion:
        with self._lock:
            version = self._versions[index_version_id]
            if version.index_id != index_id:
                raise ValueError("index version belongs to another index")
            if version.status not in {"published", "superseded"}:
                raise ValueError("only a published index version can be restored")
            current_id = self._current.get(index_id)
            if current_id and current_id in self._versions:
                self._versions[current_id].status = "superseded"
            version.status = "published"
            version.published_at = datetime.now(timezone.utc).isoformat()
            self._current[index_id] = version.index_version_id
            self._save()
            return version

    def discard(self, index_version_id: str) -> None:
        """Forget a version that never reached the published state.

        A failed publication restores the pointer to the last version that really was
        published; when there was none, the dangling version and its pointer both go, so
        the registry can never report a current version that does not exist.
        """
        with self._lock:
            version = self._versions.pop(index_version_id, None)
            if version is None:
                return
            if self._current.get(version.index_id) == index_version_id:
                del self._current[version.index_id]
            self._save()


class IndexPublicationError(RuntimeError):
    """One publication step failed, so nothing about this version may be called done."""

    def __init__(self, stage: str, message: str, cause: BaseException | None = None):
        super().__init__(message)
        self.stage = stage
        self.cause_name = type(cause).__name__ if cause is not None else ""
        if cause is not None:
            self.__cause__ = cause


@dataclass(frozen=True)
class IndexChunk:
    """One chunk row of the published record. ``embedding`` is deliberately absent."""

    chunk_id: str
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentIndexPublication:
    """One document version's index state, expressed in catalog coordinates.

    ``filename`` and ``version`` are the catalog key of the row this publication describes
    (``documents.filename`` / ``document_versions.version``), so an index version can
    always be traced back to the row that produced it. ``owner_id`` is the owner the
    catalog recorded; None stays None, which is what keeps a legacy unowned document from
    looking owned by whoever happened to re-index it.
    """

    filename: str
    version: int
    owner_id: str | None = None
    classification: int = 1
    department: str = ""
    chunks: tuple[str, ...] = ()
    vector_ids: tuple[str, ...] = ()
    content_hash: str = ""
    visibility: str = "private"
    department_ids: tuple[str, ...] = ()
    resource_status: str = "active"
    retirement: bool = False

    @property
    def resource_id(self) -> str:
        return self.filename

    @property
    def resource_version_id(self) -> str:
        return document_resource_version_id(self.filename, self.version)

    @property
    def index_id(self) -> str:
        return document_index_id(self.filename)

    @property
    def chunk_count(self) -> int:
        return 0 if self.retirement else len(self.chunks)

    @property
    def ownership(self) -> str:
        return "owned" if self.owner_id else "legacy"

    @property
    def resource_department_ids(self) -> tuple[str, ...]:
        """The departments that scope the resource version.

        ``resource_versions`` scopes by department, while the catalog carries one
        department string per version. When a row names no explicit list, its own
        department is the list: a version that belongs to finance scopes to finance,
        and a version that belongs to nothing scopes to nothing rather than to everyone.
        """
        listed = tuple(_scope_text(value) for value in self.department_ids if _scope_text(value))
        if listed:
            return listed
        department = _scope_text(self.department)
        return (department,) if department else ()

    @property
    def resource_status_value(self) -> str:
        """The catalog's own status for a live version, and retired for a retirement."""
        if self.retirement:
            return "retired"
        return _scope_text(self.resource_status) or "active"

    def scope_metadata(self) -> dict:
        """The scope carried in every chunk row: classification and department live here."""
        return {
            "filename": str(self.filename),
            "version": _scope_int(self.version, 1),
            "classification": _scope_int(self.classification, 1),
            "department": _scope_text(self.department),
            "ownership": self.ownership,
            "retirement": self.retirement,
        }

    def chunk_rows(self) -> tuple[IndexChunk, ...]:
        resource_version_id = self.resource_version_id
        rows: list[IndexChunk] = []
        for ordinal, text in enumerate(self.chunks):
            metadata = self.scope_metadata()
            metadata["ordinal"] = ordinal
            if ordinal < len(self.vector_ids):
                metadata["vector_id"] = str(self.vector_ids[ordinal])
            if self.content_hash:
                metadata["content_hash"] = self.content_hash
            rows.append(
                IndexChunk(
                    chunk_id=index_chunk_id(resource_version_id, ordinal),
                    content=str(text),
                    metadata=metadata,
                )
            )
        return tuple(rows)


def publication_checksum(publication: DocumentIndexPublication) -> str:
    """A SHA-256 over the version key and its chunk texts, in stored order."""
    digest = hashlib.sha256()
    digest.update(publication.resource_version_id.encode("utf-8"))
    for text in publication.chunks:
        digest.update(b"\x00")
        digest.update(str(text).encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True)
class PublicationOutcome:
    index_id: str
    index_version_id: str
    source_version_id: str
    chunk_count: int
    checksum: str
    status: str
    mirrored: bool
    retirement: bool
    previous_index_version_id: str | None = None
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        """The public shape: enough to trace a publication without a server path."""
        return {
            "status": "retired" if self.retirement else "published",
            "index_id": self.index_id,
            "index_version_id": self.index_version_id,
            "source_version_id": self.source_version_id,
            "backend": INDEX_BACKEND,
            "chunk_count": self.chunk_count,
            "checksum": self.checksum,
            "mirrored": self.mirrored,
            "warnings": list(self.warnings),
        }


class IndexMirrorSession:
    """One publication's worth of mirror writes, held in one database transaction.

    The session owns the connection. That is the whole reason it exists: a store is shared
    by every thread in the process, and two concurrent uploads that each kept their
    statements on the store would commit and roll back through each other's transaction.
    """

    def __init__(self, connection, *, counters_enabled: bool, degraded_reason: str = ""):
        self._connection = connection
        self.enabled = connection is not None
        self.counters_enabled = counters_enabled
        self.degraded_reason = degraded_reason

    def commit(self) -> None:
        if self._connection is not None:
            self._connection.commit()

    def abort(self) -> None:
        """Undo every statement of this publication, chunk rows and counters included."""
        if self._connection is None:
            return
        try:
            self._connection.rollback()
        except Exception as exc:
            logger.error(f"[Index] index mirror rollback failed: {exc}")

    def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is None:
            return
        self.enabled = False
        try:
            connection.close()
        except Exception:
            pass

    def _execute(self, sql: str, params=()):
        return self._connection.execute(sql, params)

    def _count(self, sql: str, params=()) -> int:
        row = self._execute(sql, params).fetchone()
        if row is None:
            return 0
        value = next(iter(row.values())) if isinstance(row, dict) else row[0]
        return int(value or 0)

    def _execute_many(self, sql, parameters):
        self._connection.executemany(sql, parameters)

    def register_index(self, publication: DocumentIndexPublication, version: IndexVersion) -> None:
        self._execute(
            """
INSERT INTO index_registry (index_id, owner_id, resource_type, status, current_version_id, metadata)
VALUES (%s, %s, %s, %s, %s, %s::jsonb)
ON CONFLICT (index_id) DO UPDATE SET
    owner_id = COALESCE(index_registry.owner_id, EXCLUDED.owner_id),
    resource_type = EXCLUDED.resource_type,
    metadata = EXCLUDED.metadata
""",
            (
                publication.index_id,
                publication.owner_id,
                RESOURCE_TYPE_DOCUMENT,
                version.status,
                None,
                _json_value({**publication.scope_metadata(), "resource_type": RESOURCE_TYPE_DOCUMENT}),
            ),
        )

    def insert_version(self, publication: DocumentIndexPublication, version: IndexVersion) -> None:
        self._execute(
            """
INSERT INTO index_versions
(index_version_id, index_id, owner_id, source_version_id, backend, chunk_count, checksum, status, metadata)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
ON CONFLICT (index_version_id) DO UPDATE SET status = EXCLUDED.status
""",
            (
                version.index_version_id,
                version.index_id,
                publication.owner_id,
                version.source_version_id,
                version.backend,
                version.chunk_count,
                version.checksum,
                version.status,
                _json_value(publication.scope_metadata()),
            ),
        )

    def register_resource_version(
        self, publication: DocumentIndexPublication, version: IndexVersion
    ) -> None:
        """Mirror the catalog version into the control-plane resource table.

        ``chunks.resource_version_id`` names the resource version every chunk belongs to,
        and until this statement existed that name resolved to nothing: the chunks pointed
        at a version row that was never written. The row is the authorization view of the
        version, so owner, classification, visibility and departments are copied from the
        catalog projection rather than re-derived here. ``superseded_at`` only ever moves
        forward, which keeps a re-index of a retired document from pretending it is live.
        """
        self._execute(
            """
INSERT INTO resource_versions
(resource_type, resource_id, version_id, owner_id, department_ids, classification,
 visibility, status, content_sha256, metadata, superseded_at)
VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s)
ON CONFLICT (resource_type, resource_id, version_id) DO UPDATE SET
    owner_id = COALESCE(resource_versions.owner_id, EXCLUDED.owner_id),
    department_ids = EXCLUDED.department_ids,
    classification = EXCLUDED.classification,
    visibility = EXCLUDED.visibility,
    status = EXCLUDED.status,
    content_sha256 = COALESCE(EXCLUDED.content_sha256, resource_versions.content_sha256),
    metadata = EXCLUDED.metadata,
    superseded_at = COALESCE(resource_versions.superseded_at, EXCLUDED.superseded_at)
""",
            (
                RESOURCE_TYPE_DOCUMENT,
                publication.resource_id,
                publication.resource_version_id,
                publication.owner_id,
                _json_value(list(publication.resource_department_ids)),
                str(_scope_int(publication.classification, 1)),
                _scope_text(publication.visibility) or "private",
                publication.resource_status_value,
                _scope_text(publication.content_hash) or None,
                _json_value(
                    {
                        **publication.scope_metadata(),
                        "index_version_id": version.index_version_id,
                        "index_id": version.index_id,
                    }
                ),
                "now" if publication.retirement else None,
            ),
        )

    def write_chunks(self, publication: DocumentIndexPublication, version: IndexVersion) -> int:
        rows = publication.chunk_rows()
        parameters = [
            (
                chunk.chunk_id,
                publication.owner_id,
                RESOURCE_TYPE_DOCUMENT,
                publication.resource_id,
                publication.resource_version_id,
                version.index_version_id,
                chunk.content,
                _json_value(chunk.metadata),
            )
            for chunk in rows
        ]
        if parameters:
            self._execute_many(_INSERT_CHUNK_SQL, parameters)
        return len(parameters)

    def retire_chunks(self, publication: DocumentIndexPublication) -> int:
        cursor = self._execute(
            "DELETE FROM chunks WHERE resource_type = %s AND resource_id = %s",
            (RESOURCE_TYPE_DOCUMENT, publication.resource_id),
        )
        return int(getattr(cursor, "rowcount", 0) or 0)

    def validate(self, publication: DocumentIndexPublication, version: IndexVersion) -> int:
        """Refuse to publish a count the database does not hold."""
        if publication.retirement:
            remaining = self._count(
                "SELECT COUNT(*) FROM chunks WHERE resource_type = %s AND resource_id = %s",
                (RESOURCE_TYPE_DOCUMENT, publication.resource_id),
            )
            if remaining:
                raise ValueError(f"{remaining} chunk rows are still stored for {publication.resource_id}")
            return remaining
        stored = self._count(
            "SELECT COUNT(*) FROM chunks WHERE index_version_id = %s",
            (version.index_version_id,),
        )
        if stored != version.chunk_count:
            raise ValueError(
                f"index version claims {version.chunk_count} chunks but {stored} were stored"
            )
        return stored

    def mark_published(
        self,
        publication: DocumentIndexPublication,
        version: IndexVersion,
        previous_index_version_id: str | None,
    ) -> None:
        if previous_index_version_id:
            self._execute(
                "UPDATE index_versions SET status = 'superseded', superseded_at = NOW() WHERE index_version_id = %s",
                (previous_index_version_id,),
            )
        # The version row keeps the ordinary lifecycle status: it is the published
        # version. What is retired is the index itself, which index_registry.status says,
        # and the row's metadata records the retirement explicitly.
        self._execute(
            """
UPDATE index_versions
SET status = %s, published_at = COALESCE(published_at, NOW()), superseded_at = NULL
WHERE index_version_id = %s
""",
            ("published", version.index_version_id),
        )
        self._execute(
            """
UPDATE index_registry
SET status = %s, current_version_id = %s, owner_id = COALESCE(owner_id, %s)
WHERE index_id = %s
""",
            (
                "retired" if publication.retirement else "active",
                version.index_version_id,
                publication.owner_id,
                publication.index_id,
            ),
        )

    def record_chunk_count(self, publication: DocumentIndexPublication) -> int:
        count = publication.chunk_count
        if publication.retirement:
            self._execute(
                "UPDATE document_versions SET chunk_count = 0 WHERE filename = %s",
                (publication.filename,),
            )
            self._execute(
                "UPDATE documents SET chunk_count = 0 WHERE filename = %s",
                (publication.filename,),
            )
            return count
        self._execute(
            "UPDATE document_versions SET chunk_count = %s WHERE filename = %s AND version = %s",
            (count, publication.filename, int(publication.version)),
        )
        self._execute(
            "UPDATE documents SET chunk_count = %s WHERE filename = %s",
            (count, publication.filename),
        )
        return count



class PostgresIndexStore:
    """Open the PostgreSQL mirror for one publication.

    ``available`` is the application's existing database health signal and is consulted per
    publication, so an offline development run never opens a connection.
    ``connection_factory`` exists for tests: it is the only way to exercise this SQL
    against something other than a live server.
    """

    def __init__(self, *, connection_factory=None, available=None, database_url: str | None = None):
        self._connection_factory = connection_factory
        self._available = available
        self._database_url = database_url

    def _connect(self):
        if self._connection_factory is not None:
            return self._connection_factory()
        import psycopg
        from psycopg.rows import dict_row

        url = self._database_url or os.getenv(
            "DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain"
        )
        return psycopg.connect(url, row_factory=dict_row, connect_timeout=2)

    @staticmethod
    def _read_schema(connection) -> set[tuple[str, str]]:
        tables = tuple(sorted(set(_MIRROR_TABLES) | set(_COUNTER_TABLES)))
        rows = connection.execute(_SCHEMA_SQL, (tables,)).fetchall()
        present: set[tuple[str, str]] = set()
        for row in rows:
            values = list(row.values()) if isinstance(row, dict) else list(row)
            if len(values) < 2:
                continue
            present.add((str(values[0]), str(values[1])))
        return present

    def open(self) -> IndexMirrorSession:
        """Begin one mirrored publication, or explain why the mirror is standing down.

        An unreachable or unmigrated database is a deployment state rather than a failed
        upload: the version still publishes to the local registry, and the caller reports
        the degradation instead of answering 500 for something the operator has to fix.
        """
        if self._available is not None and not self._available():
            return IndexMirrorSession(None, counters_enabled=False)
        try:
            connection = self._connect()
        except Exception as exc:
            reason = f"index mirror is unreachable ({type(exc).__name__})"
            logger.warning(f"[Index] {reason}; the version stays local to this process")
            return IndexMirrorSession(None, counters_enabled=False, degraded_reason=reason)
        try:
            present = self._read_schema(connection)
        except Exception as exc:
            reason = f"index mirror schema could not be read ({type(exc).__name__})"
            logger.warning(f"[Index] {reason}; the version stays local to this process")
            try:
                connection.close()
            except Exception:
                pass
            return IndexMirrorSession(None, counters_enabled=False, degraded_reason=reason)
        missing = [table for table in _MIRROR_TABLES if not _table_is_present(present, table)]
        if missing:
            reason = "index mirror tables are not migrated: " + ", ".join(missing)
            logger.warning(f"[Index] {reason}; run the migrations before trusting index bookkeeping")
            try:
                connection.close()
            except Exception:
                pass
            return IndexMirrorSession(None, counters_enabled=False, degraded_reason=reason)
        counters_enabled = all((table, _COUNTER_COLUMN) in present for table in _COUNTER_TABLES)
        return IndexMirrorSession(connection, counters_enabled=counters_enabled)


class IndexPublisher:
    """Drive one publication through create_version, validate and publish, or undo it."""

    def __init__(self, registry: IndexRegistry, store: PostgresIndexStore | None = None):
        self.registry = registry
        self.store = store

    def apply(self, publication: DocumentIndexPublication) -> PublicationOutcome | None:
        """Publish one document index state, or report that there is nothing to publish.

        Two states have no index version to describe: a version the vector store holds no
        chunks for, and a retirement of a document that never published (or already
        retired). Answering "published" for either would put a version in the registry
        that nothing backs, which is the half-published state this slice exists to stop,
        and it would make a second delete of one document retire it twice.
        """
        if publication.retirement:
            if not self._retirement_is_pending(publication.index_id):
                return None
        elif not publication.chunks:
            return None
        return self.publish(publication)

    def publish(self, publication: DocumentIndexPublication) -> PublicationOutcome:
        if not isinstance(publication, DocumentIndexPublication):
            raise TypeError("publication must be a DocumentIndexPublication")
        if publication.retirement and publication.chunks:
            raise ValueError("a retirement publication cannot carry chunks")

        index_id = publication.index_id
        previous_id = self._current_id(index_id)
        version = self._step(
            "create_version",
            lambda: self.registry.create_version(
                index_id=index_id,
                source_version_id=publication.resource_version_id,
                backend=INDEX_BACKEND,
                chunk_count=publication.chunk_count,
                checksum=publication_checksum(publication),
                retirement=publication.retirement,
            ),
        )
        warnings: list[str] = []
        mirrored = False
        session: IndexMirrorSession | None = None
        try:
            if self.store is not None:
                session = self._step("index_mirror", self.store.open)
                mirrored = session.enabled
                if not mirrored:
                    warnings.append(session.degraded_reason or "the index mirror is disabled")
                    logger.warning(
                        f"[Index] {session.degraded_reason or 'index mirror disabled'}: "
                        f"{publication.resource_version_id} published locally only"
                    )
            if mirrored and session is not None:
                self._step(
                    "resource_versions",
                    lambda: session.register_resource_version(publication, version),
                )
                self._step("index_registry", lambda: session.register_index(publication, version))
                self._step("index_versions", lambda: session.insert_version(publication, version))
                if publication.retirement:
                    self._step("chunks", lambda: session.retire_chunks(publication))
                else:
                    self._step("chunks", lambda: session.write_chunks(publication, version))
                self._step("validate", lambda: session.validate(publication, version))
                self._step("publish", lambda: session.mark_published(publication, version, previous_id))
                if session.counters_enabled:
                    self._step("chunk_count", lambda: session.record_chunk_count(publication))
                else:
                    warnings.append(
                        "chunk_count is not migrated; apply migrations/0007_document_chunk_count.sql"
                    )
            # The local pointer moves last but before the commit: a registry that cannot
            # validate or publish must not leave a committed database version that this
            # process does not consider current.
            self._step("validate", lambda: self.registry.validate(version.index_version_id))
            self._step("publish", lambda: self.registry.publish(version.index_version_id))
            if mirrored:
                self._step("index_mirror", session.commit)
        except IndexPublicationError as exc:
            self._abort(publication, version.index_version_id, previous_id, session, exc)
            raise
        if session is not None:
            session.close()

        return PublicationOutcome(
            index_id=index_id,
            index_version_id=version.index_version_id,
            source_version_id=version.source_version_id,
            chunk_count=version.chunk_count,
            checksum=version.checksum,
            status="retired" if publication.retirement else "published",
            mirrored=mirrored,
            retirement=publication.retirement,
            previous_index_version_id=previous_id,
            warnings=tuple(warnings),
        )

    def _current_id(self, index_id: str) -> str | None:
        try:
            return self.registry.current(index_id).index_version_id
        except KeyError:
            return None

    def _retirement_is_pending(self, index_id: str) -> bool:
        try:
            current = self.registry.current(index_id)
        except KeyError:
            return False
        return not current.retirement

    def _abort(
        self,
        publication: DocumentIndexPublication,
        index_version_id: str,
        previous_id: str | None,
        session: IndexMirrorSession | None,
        cause: IndexPublicationError,
    ) -> None:
        if session is not None:
            session.abort()
            session.close()
        try:
            if previous_id:
                self.registry.rollback(publication.index_id, previous_id)
            self.registry.discard(index_version_id)
        except Exception as exc:
            logger.error(
                f"[Index] rollback after a failed {cause.stage} step did not complete: {exc}"
            )

    @staticmethod
    def _step(stage: str, action):
        try:
            return action()
        except IndexPublicationError:
            raise
        except Exception as exc:
            raise IndexPublicationError(
                stage, f"index publication failed during {stage}", exc
            ) from exc


def _table_is_present(present: set[tuple[str, str]], table: str) -> bool:
    required = _MIRROR_COLUMNS.get(table, ())
    return all((table, column) in present for column in required)