"""Versioned index publication with atomic local metadata and rollback.

The local JSON metadata file is the authority for what this process believes is
published. ``PostgresIndexStore`` mirrors one publication into ``index_registry``,
``index_versions`` and ``chunks`` inside a single database transaction, so a publication
that fails halfway leaves neither a published version nor a stranded chunk row behind.
Chroma stays the only retrieval path: this module records chunks, it never embeds them,
and every row it writes leaves ``chunks.embedding`` NULL.

R22 binds every index version to the embedding profile that produced it: ``embedding_model``
plus ``dimension``. Those two values are part of the version, they gate validate, publish,
current, rollback and discard, and a record written before they existed keeps an *unknown*
scope instead of inheriting whatever model happens to be configured now. Changing either
axis therefore cannot reuse a version: it takes a new one, and the only thing that creates
one at scale is the manual rebuild command (``scripts/rebuild_index.py``).

R50 adds the other half of that question. ``plan_index_refresh`` answers "which documents
actually need new vectors" out of the records this registry already holds, so a rebuild no
longer has to mean "re-embed the whole library": an unchanged document costs no embedding
call at all, and a run that stopped halfway resumes from the versions it published. It is
still a reader -- it neither embeds nor writes, and it is the digest a version already
carries that decides, never a guess about which model produced what.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
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
#: The two backend spellings this build knows. R59b: ``INDEX_BACKEND`` below is no longer
#: only a label written into the version ledger -- it is the switch that decides which
#: engine a semantic search asks. One constant, so the ledger and the read path cannot be
#: set apart from each other by accident.
INDEX_BACKENDS = frozenset({"chroma", "pgvector"})
INDEX_BACKEND_DEFAULT = "chroma"
PGVECTOR_BACKEND = "pgvector"
INDEX_BACKEND = INDEX_BACKEND_DEFAULT
INDEX_METADATA_ENV = "INDEX_METADATA_PATH"
DEFAULT_INDEX_METADATA_PATH = "./data/index-versions.json"

# The embedding profile a version is bound to. EMBED_MODEL is a module-level constant in
# app/rag/retriever.py:23, so an operator changes it in code; reading it here -- lazily, and
# never at import time -- is what makes a model swap visible to the registry instead of
# silently leaving the old vectors behind. The DEFAULT_* pair below applies only when
# nothing declares a value at all: it describes the shipped model, it is not a guess about
# some already-stored record.
EMBEDDING_MODEL_ENV = "EMBEDDING_MODEL"
EMBEDDING_DIMENSION_ENV = "EMBEDDING_DIMENSION"
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_EMBEDDING_DIMENSION = 768
SCOPE_UNKNOWN = "unknown"

# Stable codes. ``embedding_model_drift`` is the one docs/handoff section 18 criterion 2
# asks /health/details to report; the others say *why* a version is unusable.
CODE_SCOPE_UNKNOWN = "embedding_scope_unknown"
CODE_SCOPE_MISMATCH = "embedding_scope_mismatch"
CODE_MODEL_DRIFT = "embedding_model_drift"
CODE_DIMENSION_DRIFT = "embedding_dimension_drift"

# What the mirror needs to be able to write at all. An unmigrated database is a
# deployment state, not a failed upload: a document that already reached Chroma must not
# be reported as unparsable because index bookkeeping tables are missing, so the mirror
# degrades with a warning and the publication stays local.
#: The tables that decide whether index bookkeeping exists at all. Each of them is created
#: by a migration that predates pgvector, so a database missing one has not been migrated
#: for any index bookkeeping -- and a partial mirror is worse than an absent one that says
#: so out loud and publishes locally.
_MIRROR_REQUIRED_TABLES = ("index_registry", "index_versions", "chunks", "resource_versions")

#: The vector mirror's own table. app/rag/pg_store.py:71 is the writer and names the same
#: literal; the two are pinned together by a test rather than by an import, because
#: pg_store.py:41 imports this module and importing it back would be a cycle.
#: chunk_vectors joins the probe list -- the publication has to see it to bind a version
#: into it (R76) -- but deliberately not _MIRROR_REQUIRED_TABLES: migrations/0010 is
#: optional while VECTOR_DUAL_WRITE is off, and gating the whole index mirror on it would
#: take bookkeeping away from every deployment that has not adopted pgvector. The binding
#: step degrades on its own instead, exactly the way the chunk_count counter already does.
VECTOR_MIRROR_TABLE = "chunk_vectors"

_MIRROR_TABLES = _MIRROR_REQUIRED_TABLES + (VECTOR_MIRROR_TABLE,)
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
    VECTOR_MIRROR_TABLE: (
        # The columns the publication binding reads and writes, and nothing more. The table
        # also holds content/embedding/distance_function, but those belong to the dual
        # write: naming them here would make index bookkeeping refuse to bind vectors over a
        # column this ticket never touches.
        "vector_id",
        "index_version_id",
        "embedding_model",
        "embedding_dimension",
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

#: R76. The read is a GROUP BY rather than a count because the answer has to name the
#: profile the stored vectors were produced under, not only how many of them there are.
#: Both columns are NOT NULL (migrations/0010_pgvector_chunks.sql:144-145), so an empty
#: model or a zero width in a group is itself the evidence of an unlabelled generation.
_VECTOR_SCOPE_PROBE_SQL = f"""
SELECT embedding_model, embedding_dimension, COUNT(*) AS row_count
FROM {VECTOR_MIRROR_TABLE}
WHERE vector_id = ANY(%s::text[])
GROUP BY embedding_model, embedding_dimension
"""

#: The scope predicate is not decoration. It is what stops a generation that was not the one
#: probed from being stamped by this version: a row whose profile moved between the read and
#: the write stops matching, and the step refuses the mismatch instead of hiding it.
_TAG_VECTOR_VERSION_SQL = f"""
UPDATE {VECTOR_MIRROR_TABLE}
SET index_version_id = %s, updated_at = NOW()
WHERE vector_id = ANY(%s::text[]) AND embedding_model = %s AND embedding_dimension = %s
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


def _dimension_value(value) -> int:
    """Coerce one explicitly supplied dimension, or refuse.

    A caller that names a dimension has to mean it: this is the value the whole
    cross-dimension gate compares against, so a typo must not degrade into "unknown" and
    then into a permissive match.
    """
    try:
        dimension = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"embedding dimension must be a positive integer, got {value!r}") from None
    if dimension <= 0:
        raise ValueError(f"embedding dimension must be a positive integer, got {dimension}")
    return dimension


@dataclass(frozen=True)
class EmbeddingScope:
    """What produced a set of vectors: which model, and how wide its output is.

    Either half may be ``None``, which means *unknown* -- not "assume the current one".
    Only a fully known scope is publishable or queryable; an unknown scope fails closed.
    """

    embedding_model: str | None = None
    dimension: int | None = None

    @classmethod
    def unknown(cls) -> "EmbeddingScope":
        return cls()

    @property
    def known(self) -> bool:
        return bool(self.embedding_model) and isinstance(self.dimension, int) and self.dimension > 0

    @property
    def key(self) -> tuple:
        return (self.embedding_model, self.dimension)

    def disagreement(self, configured: "EmbeddingScope") -> tuple[str, ...]:
        """Which axes disagree with ``configured``, as stable codes.

        A missing axis reports ``embedding_scope_unknown`` rather than a drift code: a
        record that never named its model is not evidence the model changed, it is evidence
        nobody was keeping score. The refusal is the same either way; the reason is not.
        """
        codes: list[str] = []
        if self.embedding_model != configured.embedding_model:
            codes.append(CODE_MODEL_DRIFT if self.embedding_model else CODE_SCOPE_UNKNOWN)
        if self.dimension != configured.dimension:
            codes.append(CODE_DIMENSION_DRIFT if self.dimension else CODE_SCOPE_UNKNOWN)
        return tuple(dict.fromkeys(codes))

    def as_dict(self) -> dict:
        return {
            "embedding_model": self.embedding_model or SCOPE_UNKNOWN,
            "dimension": self.dimension if self.dimension else SCOPE_UNKNOWN,
        }

    def __str__(self) -> str:
        model = self.embedding_model or SCOPE_UNKNOWN
        dimension = self.dimension if self.dimension else SCOPE_UNKNOWN
        return f"{model}/{dimension}"


def _shipped_embedding_model() -> str:
    """The model this build embeds with, read from the module that actually calls it.

    Imported lazily and guarded: app/rag/retriever pulls in chromadb and langchain, and an
    index registry must still open when those are missing. If the retriever cannot be read
    the shipped constant answers, never "unknown".
    """
    try:
        from app.rag.retriever import EMBED_MODEL

        value = str(EMBED_MODEL or "").strip()
        if value:
            return value
    except Exception as exc:  # pragma: no cover - depends on optional third-party imports
        logger.warning(f"[Index] the embedding model could not be read from the retriever: {exc}")
    return DEFAULT_EMBEDDING_MODEL


def _configured_dimension() -> int:
    raw = str(os.getenv(EMBEDDING_DIMENSION_ENV, "") or "").strip()
    if not raw:
        return DEFAULT_EMBEDDING_DIMENSION
    try:
        return _dimension_value(raw)
    except ValueError as exc:
        logger.warning(f"[Index] {EMBEDDING_DIMENSION_ENV} is unusable ({exc}); using {DEFAULT_EMBEDDING_DIMENSION}")
        return DEFAULT_EMBEDDING_DIMENSION


def configured_embedding_scope() -> EmbeddingScope:
    """The profile new vectors are produced under: env override, else this build's model."""
    model = str(os.getenv(EMBEDDING_MODEL_ENV, "") or "").strip() or _shipped_embedding_model()
    return EmbeddingScope(model, _configured_dimension())


class IndexScopeError(ValueError):
    """A version may not be used under the embedding profile that is in effect now.

    ``code`` is stable and safe to surface: it is what /health/details reports and what a
    caller matches on, so the message can stay human-readable.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        index_id: str = "",
        index_version_id: str = "",
        version_scope: EmbeddingScope | None = None,
        configured_scope: EmbeddingScope | None = None,
        codes: tuple[str, ...] = (),
    ):
        super().__init__(message)
        self.code = code
        self.codes = tuple(codes) or (code,)
        self.index_id = index_id
        self.index_version_id = index_version_id
        self.version_scope = version_scope or EmbeddingScope.unknown()
        self.configured_scope = configured_scope or EmbeddingScope.unknown()

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "codes": list(self.codes),
            "index_id": self.index_id,
            "index_version_id": self.index_version_id,
            "version_scope": self.version_scope.as_dict(),
            "configured_scope": self.configured_scope.as_dict(),
        }


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
    # Part of the version, not a label on it. A record written before R22 has neither key
    # and stays unknown; appending them last keeps every existing positional use working.
    embedding_model: str | None = None
    dimension: int | None = None

    @property
    def scope(self) -> EmbeddingScope:
        return EmbeddingScope(self.embedding_model, self.dimension)

    def matches_scope(self, scope: EmbeddingScope) -> bool:
        return self.scope == scope


# The on-disk shape of one version record. A field list derived from the dataclass itself
# means the loader cannot fall behind the record: adding a field here needs no second edit.
_INDEX_VERSION_FIELDS = frozenset(f.name for f in fields(IndexVersion))
_INDEX_VERSION_REQUIRED = (
    "index_version_id",
    "index_id",
    "source_version_id",
    "backend",
    "chunk_count",
    "checksum",
    "status",
    "created_at",
)


class IndexRegistry:
    def __init__(self, metadata_path: str | Path, *, scope: EmbeddingScope | None = None):
        self.metadata_path = Path(metadata_path).resolve()
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._versions: dict[str, IndexVersion] = {}
        self._current: dict[str, str] = {}
        # None means "ask the environment every time", which is the point: a process that
        # picks up a new model has to notice on the next publication, not on the next
        # restart. A fixed scope exists for tests and for the rebuild command, which names
        # the profile it is about to write under rather than trusting the ambient value.
        self._fixed_scope = scope
        self._load()

    @property
    def scope(self) -> EmbeddingScope:
        """The embedding profile this process publishes under right now."""
        if self._fixed_scope is not None:
            return self._fixed_scope
        return configured_embedding_scope()

    def _reference_scope(
        self, embedding_model: str | None, dimension: int | None
    ) -> EmbeddingScope:
        """Resolve caller-supplied axes against the configured profile.

        Naming only one axis keeps the other from the configuration, so a query that says
        "768" still cannot match a version some other model built at 768.
        """
        base = self.scope
        model = base.embedding_model
        if embedding_model is not None:
            model = str(embedding_model).strip() or None
        dimension_value = base.dimension if dimension is None else _dimension_value(dimension)
        return EmbeddingScope(model, dimension_value)

    def _require_scope(self, version: IndexVersion, reference: EmbeddingScope, *, action: str) -> None:
        """Refuse to let one index serve two embedding profiles at once."""
        scope = version.scope
        if scope == reference:
            return
        codes = scope.disagreement(reference)
        code = CODE_SCOPE_UNKNOWN if CODE_SCOPE_UNKNOWN in codes else CODE_SCOPE_MISMATCH
        raise IndexScopeError(
            code,
            f"cannot {action} {version.index_version_id}: it was embedded as {scope}, "
            f"but this index is {reference}",
            index_id=version.index_id,
            index_version_id=version.index_version_id,
            version_scope=scope,
            configured_scope=reference,
            codes=codes,
        )

    def _load(self) -> None:
        if not self.metadata_path.exists():
            return
        payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        self._versions = {
            raw["index_version_id"]: self._version_from_record(raw)
            for raw in payload.get("versions", [])
        }
        self._current = {
            str(key): str(value)
            for key, value in (payload.get("current") or {}).items()
        }

    @staticmethod
    def _version_from_record(raw: dict) -> IndexVersion:
        """Read one persisted record without inventing a profile for it.

        A record written before R22 carries no ``embedding_model``/``dimension`` key. Those
        stay ``None`` -- reported as unknown and refused by every scope gate -- rather than
        taking the currently configured model, which would bless old vectors as though this
        build's model had produced them. Keys this build does not know are dropped instead
        of crashing the load, so a file written by a newer build still opens; a key this
        build *needs* still fails loudly rather than yielding a half-record version.
        """
        known = {key: value for key, value in raw.items() if key in _INDEX_VERSION_FIELDS}
        missing = [name for name in _INDEX_VERSION_REQUIRED if name not in known]
        if missing:
            raise ValueError(
                "index version record is missing required field(s): " + ", ".join(sorted(missing))
            )
        version = IndexVersion(**known)
        # Empty strings and zero are as unknown as an absent key: they say nothing about
        # which model produced a vector, and treating them as a profile would be a guess.
        if not version.embedding_model:
            version.embedding_model = None
        if not version.dimension:
            version.dimension = None
        return version

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
        embedding_model: str | None = None,
        dimension: int | None = None,
    ) -> IndexVersion:
        if not index_id.strip() or not source_version_id.strip():
            raise ValueError("index_id and source_version_id are required")
        if backend not in INDEX_BACKENDS:
            raise ValueError("unsupported index backend")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError("index checksum must be a SHA-256 hex digest")
        if retirement and int(chunk_count) != 0:
            raise ValueError("a retirement index version carries zero chunks")
        # A version that does not name its profile records the one this process embeds with.
        # It can never record "unknown": unknown arrives only from a legacy file, and that
        # asymmetry is what makes an unknown current version conspicuous.
        scope = self._reference_scope(embedding_model, dimension)
        if not scope.known:
            raise ValueError(
                "an index version must record an embedding model and a positive dimension"
            )
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
            embedding_model=scope.embedding_model,
            dimension=scope.dimension,
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
            # The profile check runs last but before the status moves: a version built for
            # another model or width is not "validated", and a validated-but-mismatched
            # version is one publish() call away from serving wrong vectors.
            self._require_scope(version, self.scope, action="validate")
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

    def current(
        self,
        index_id: str,
        *,
        embedding_model: str | None = None,
        dimension: int | None = None,
        enforce_scope: bool = False,
    ) -> IndexVersion:
        """The version an index points at now.

        Unscoped, it answers the bookkeeping question ("what is current") for callers that
        only trace a publication, including a legacy current whose profile is unknown --
        chat.py and the publisher read it that way, and refusing there would turn a
        reporting call into an outage. Pass a profile, or ``enforce_scope``, and it becomes
        the retrieval question instead: "may a query embedded this way be answered from
        what is current", with a stable refusal when it may not.
        """
        with self._lock:
            version_id = self._current.get(index_id)
            if not version_id:
                raise KeyError(index_id)
            version = self._versions[version_id]
            if enforce_scope or embedding_model is not None or dimension is not None:
                self._require_scope(
                    version,
                    self._reference_scope(embedding_model, dimension),
                    action="read",
                )
            return version

    def rollback(
        self,
        index_id: str,
        index_version_id: str,
        *,
        embedding_model: str | None = None,
        dimension: int | None = None,
        enforce_scope: bool = True,
    ) -> IndexVersion:
        with self._lock:
            version = self._versions[index_version_id]
            if version.index_id != index_id:
                raise ValueError("index version belongs to another index")
            if version.status not in {"published", "superseded"}:
                raise ValueError("only a published index version can be restored")
            # Rolling back is a profile switch as much as a version switch: restoring a
            # 384-wide version while this process embeds queries at 768 would answer new
            # queries with old vectors, which is the failure this whole gate exists to stop.
            # The publisher's abort path passes enforce_scope=False because it undoes a
            # publication that never completed and returns the pointer that was already
            # live; see IndexPublisher._abort.
            if enforce_scope:
                self._require_scope(
                    version,
                    self._reference_scope(embedding_model, dimension),
                    action="roll back to",
                )
            current_id = self._current.get(index_id)
            if current_id and current_id in self._versions:
                self._versions[current_id].status = "superseded"
            version.status = "published"
            version.published_at = datetime.now(timezone.utc).isoformat()
            self._current[index_id] = version.index_version_id
            self._save()
            return version

    def discard(
        self,
        index_version_id: str,
        *,
        embedding_model: str | None = None,
        dimension: int | None = None,
        enforce_scope: bool = True,
    ) -> None:
        """Forget a version that never reached the published state.

        A failed publication restores the pointer to the last version that really was
        published; when there was none, the dangling version and its pointer both go, so
        the registry can never report a current version that does not exist.

        ``enforce_scope`` is on by default so a rebuild under a new profile cannot erase the
        other profile's rollback target. Forgetting a version is the one operation here that
        pointing somewhere else cannot undo.
        """
        with self._lock:
            version = self._versions.get(index_version_id)
            if version is None:
                return
            if enforce_scope:
                # Checked before the pop, not after: a refusal has to leave this registry
                # exactly as it was, current pointer included.
                self._require_scope(
                    version,
                    self._reference_scope(embedding_model, dimension),
                    action="discard",
                )
            del self._versions[index_version_id]
            if self._current.get(version.index_id) == index_version_id:
                del self._current[version.index_id]
            self._save()

    def queryable_version_ids(
        self,
        *,
        index_id: str | None = None,
        embedding_model: str | None = None,
        dimension: int | None = None,
    ) -> frozenset[str]:
        """The versions this profile may serve a search from, and nothing else.

        Only versions that really reached the published state count, and only those whose
        model *and* width both agree. An unknown profile is never queryable, which is why a
        legacy record cannot leak into a new-profile result set.
        """
        reference = self._reference_scope(embedding_model, dimension)
        with self._lock:
            return frozenset(
                version.index_version_id
                for version in self._versions.values()
                if version.status in {"published", "superseded"}
                and version.scope == reference
                and (index_id is None or version.index_id == index_id)
            )

    def queryable_version(
        self,
        index_id: str,
        *,
        embedding_model: str | None = None,
        dimension: int | None = None,
    ) -> IndexVersion:
        """The version a query under this profile may hit, or a stable refusal."""
        return self.current(
            index_id,
            embedding_model=embedding_model,
            dimension=dimension,
            enforce_scope=True,
        )

    def index_ids(self) -> tuple[str, ...]:
        """Every index this registry has a current version for."""
        with self._lock:
            return tuple(sorted(self._current))

    def history(self, index_id: str) -> tuple[IndexVersion, ...]:
        """Every version of one index, oldest first, whatever its status.

        Superseded versions stay listed on purpose: a rebuild is only auditable -- and only
        reversible -- while the previous version is still there to be named.
        """
        with self._lock:
            return tuple(
                sorted(
                    (
                        version
                        for version in self._versions.values()
                        if version.index_id == index_id
                    ),
                    key=lambda version: version.created_at,
                )
            )

    def embedding_drift(
        self, *, index_id: str | None = None, include_history: bool = False
    ) -> "EmbeddingDrift":
        """Does what is published disagree with the embedding profile in effect now?

        With no ``index_id`` this surveys the current version of every index, which is what
        a health check needs; ``include_history`` widens it to superseded versions that may
        still hold vectors.
        """
        reference = self.scope
        with self._lock:
            if index_id is not None:
                candidates = [self._current.get(index_id)]
            else:
                candidates = list(self._current.values())
            versions = [
                self._versions[version_id]
                for version_id in candidates
                if version_id and version_id in self._versions
            ]
            if include_history:
                seen = {version.index_version_id for version in versions}
                versions.extend(
                    version
                    for version in self._versions.values()
                    if version.status == "superseded" and version.index_version_id not in seen
                )
        return EmbeddingDrift.from_versions(versions, configured=reference)


class IndexPublicationError(RuntimeError):
    """One publication step failed, so nothing about this version may be called done."""

    def __init__(self, stage: str, message: str, cause: BaseException | None = None):
        super().__init__(message)
        self.stage = stage
        self.cause_name = type(cause).__name__ if cause is not None else ""
        if cause is not None:
            self.__cause__ = cause


@dataclass(frozen=True)
class EmbeddingDrift:
    """How far the published index has come apart from the configured embedder.

    A pure report: nothing here mutates a registry, so a health probe can call it as often
    as it likes. ``codes`` is the set a caller puts in ``problems``; ``affected`` names the
    versions so an operator can see how wide a rebuild is before running one.
    """

    drifted: bool = False
    codes: tuple[str, ...] = ()
    configured: EmbeddingScope = EmbeddingScope.unknown()
    affected_index_version_ids: tuple[str, ...] = ()
    unknown_index_version_ids: tuple[str, ...] = ()
    checked: int = 0

    @classmethod
    def from_versions(
        cls, versions, *, configured: EmbeddingScope
    ) -> "EmbeddingDrift":
        codes: list[str] = []
        affected: list[str] = []
        unknown: list[str] = []
        for version in versions:
            disagreement = version.scope.disagreement(configured)
            if not disagreement:
                continue
            affected.append(version.index_version_id)
            codes.extend(disagreement)
            if CODE_SCOPE_UNKNOWN in disagreement:
                unknown.append(version.index_version_id)
        return cls(
            drifted=bool(affected),
            codes=tuple(dict.fromkeys(codes)),
            configured=configured,
            affected_index_version_ids=tuple(affected),
            unknown_index_version_ids=tuple(unknown),
            checked=len(versions),
        )

    def as_dict(self) -> dict:
        return {
            "drifted": self.drifted,
            "codes": list(self.codes),
            "configured": self.configured.as_dict(),
            "affected_index_version_ids": list(self.affected_index_version_ids),
            "unknown_index_version_ids": list(self.unknown_index_version_ids),
            "checked": self.checked,
        }


def retain_queryable(
    registry: IndexRegistry,
    records,
    *,
    index_id: str | None = None,
    embedding_model: str | None = None,
    dimension: int | None = None,
    version_key: str = "index_version_id",
) -> list:
    """Keep only the records that belong to the asked-for embedding profile.

    A hit whose version is unknown, or belongs to another profile, is not "close enough":
    it is a vector some other model computed, so it leaves the result set. That is what
    makes "one knowledge base, two dimensions, no cross-dimension hits" true while a rebuild
    is still in flight, when both generations of vectors are physically present. Records
    that carry no version at all fail closed too -- an unattributable hit cannot be shown to
    be the right width.
    """
    allowed = registry.queryable_version_ids(
        index_id=index_id, embedding_model=embedding_model, dimension=dimension
    )
    kept: list = []
    for record in records or ():
        if isinstance(record, dict):
            version_id = str(record.get(version_key) or "")
        else:
            version_id = str(getattr(record, version_key, "") or "")
        if version_id and version_id in allowed:
            kept.append(record)
    return kept


def read_index_metadata(metadata_path: str | Path | None = None) -> tuple[list[IndexVersion], dict]:
    """Parse the registry file without opening a registry.

    ``IndexRegistry.__init__`` creates its parent directory, which is right for a publisher
    and wrong for a health probe: a check that reports on the filesystem must not add to it,
    and must not be able to write. This reads the same records through the same legacy-safe
    loader and returns them.
    """
    path = Path(metadata_path or default_metadata_path()).expanduser().resolve()
    if not path.exists():
        return [], {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    versions = [IndexRegistry._version_from_record(raw) for raw in payload.get("versions", [])]
    current = {
        str(key): str(value)
        for key, value in (payload.get("current") or {}).items()
    }
    return versions, current


def embedding_drift_from_metadata(
    metadata_path: str | Path | None = None, *, scope: EmbeddingScope | None = None
) -> EmbeddingDrift:
    """The drift answer for a process that has no registry of its own."""
    versions, current = read_index_metadata(metadata_path)
    by_id = {version.index_version_id: version for version in versions}
    referenced = [by_id[version_id] for version_id in current.values() if version_id in by_id]
    return EmbeddingDrift.from_versions(
        referenced, configured=scope if scope is not None else configured_embedding_scope()
    )


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
class VectorTagging:
    """What one publication did to ``chunk_vectors.index_version_id``.

    Three numbers because they answer three different questions. ``carried`` is how many
    vector ids the publication named; ``existing`` is how many rows the vector mirror
    actually holds for them; ``tagged`` is how many this publication bound to its own index
    version. ``carried - existing`` is the mirror not having caught up, which is a state to
    report, and a ``tagged`` above zero with rows present is the whole point of the step: a
    caller that wants to know whether the chain reached the table reads this, not a log line.
    """

    carried: int = 0
    existing: int = 0
    tagged: int = 0
    scope: EmbeddingScope = EmbeddingScope.unknown()

    @property
    def missing(self) -> int:
        """Ids this publication named that the vector mirror holds no row for."""
        return max(self.carried - self.existing, 0)

    def as_dict(self) -> dict:
        return {
            "carried": self.carried,
            "existing": self.existing,
            "tagged": self.tagged,
            "missing": self.missing,
            "scope": self.scope.as_dict(),
        }


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
    embedding_model: str | None = None
    dimension: int | None = None
    vector_rows_tagged: int = 0
    vector_rows_missing: int = 0

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
            # Which embedder produced the vectors this version describes. A caller that
            # cannot see this cannot tell a fresh publication from a stale one.
            "embedding_model": self.embedding_model or SCOPE_UNKNOWN,
            "dimension": self.dimension if self.dimension else SCOPE_UNKNOWN,
            # R76: how much of the vector mirror this publication bound to its own index
            # version, and how much of it it could not name. Tagged 0 and missing 0 is an
            # install that holds no vector rows, not a failure; the warnings say which.
            "vector_rows_tagged": self.vector_rows_tagged,
            "vector_rows_missing": self.vector_rows_missing,
        }


class IndexMirrorSession:
    """One publication's worth of mirror writes, held in one database transaction.

    The session owns the connection. That is the whole reason it exists: a store is shared
    by every thread in the process, and two concurrent uploads that each kept their
    statements on the store would commit and roll back through each other's transaction.
    """

    def __init__(
        self,
        connection,
        *,
        counters_enabled: bool,
        vectors_enabled: bool = False,
        degraded_reason: str = "",
    ):
        self._connection = connection
        self.enabled = connection is not None
        self.counters_enabled = counters_enabled
        # Whether chunk_vectors is there to be bound into. Defaults to off so a session
        # built without a schema probe -- an older caller, or a unit test holding one
        # statement -- never guesses that the table exists, the same way counters_enabled
        # has to be told rather than inferred.
        self.vectors_enabled = vectors_enabled
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
        # psycopg3 keeps executemany on the cursor. The connection object has execute() but
        # no executemany(), so calling it there raises AttributeError the moment a real
        # server answers -- and a fake connection that mirrors this file instead of the
        # driver hides it. The chunk insert is the whole point of the slice, so it has to
        # go through the object that actually owns the method.
        with self._connection.cursor() as cursor:
            cursor.executemany(sql, parameters)

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
        # The scope rides in the version row's metadata rather than a new column: the
        # migration that gives chunks.embedding a real vector(<dim>) belongs to R58, and a
        # mirror must not start requiring a column no checked-in migration creates.
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
                _json_value(
                    {
                        **publication.scope_metadata(),
                        "embedding_model": version.scope.embedding_model or SCOPE_UNKNOWN,
                        "dimension": version.scope.dimension or SCOPE_UNKNOWN,
                    }
                ),
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

    def tag_vector_index_version(
        self, publication: DocumentIndexPublication, version: IndexVersion
    ) -> VectorTagging:
        """Bind this publication's vector rows to its index version, or refuse.

        ``chunk_vectors.index_version_id`` is the column that answers "which published
        version do these vectors belong to", and until now nothing wrote it: the dual write
        leaves it NULL on purpose, because the retriever that performs it has never heard of
        index versions. The publication that follows it has, so this is the step that closes
        that open end.

        Two rules, both fail-closed:

        * The stored rows speak for their own profile. Every row about to be stamped carries
          the model and width that actually produced its vector. If that is not the scope of
          the version being published, the mirror is a different generation from the index,
          and stamping it would make the half state *readable as a finished one* -- a search
          could then filter on ``index_version_id`` and trust vectors some other embedder
          computed. Refused with R22's own drift codes, so the publication aborts inside
          the one transaction and neither the registry nor the mirror moves.
        * A row that is simply not there is not a disagreement. VECTOR_DUAL_WRITE is off by
          default and chunk_vectors is empty in exactly that state, which is the documented
          deployment posture rather than corruption. Those ids are counted and reported as a
          warning; the publication still proceeds, because refusing here would take index
          bookkeeping away from every install that has not adopted pgvector.

        Crash safety (the all-or-nothing the mirror already promises): this runs in the same
        transaction as the chunk rows, before ``mark_published`` and before the commit. A
        process that dies between here and the commit leaves these rows at NULL -- "not yet
        published", the same shape a dual-written row has before any publication reached it
        -- never stamped with a version id that never became current. There is no partial
        visible state to reconcile, and a retry re-runs the same two statements.
        """
        vector_ids = list(dict.fromkeys(str(item) for item in publication.vector_ids if str(item)))
        if not vector_ids:
            return VectorTagging()
        publishing_scope = version.scope
        groups: list[tuple[EmbeddingScope, int]] = []
        for row in self._execute(_VECTOR_SCOPE_PROBE_SQL, (vector_ids,)).fetchall():
            values = list(row.values()) if isinstance(row, dict) else list(row)
            if len(values) < 3:
                continue
            try:
                dimension = int(values[1] or 0)
            except (TypeError, ValueError):
                dimension = 0
            try:
                count = int(values[2] or 0)
            except (TypeError, ValueError):
                count = 0
            groups.append((EmbeddingScope(str(values[0] or ""), dimension), count))
        existing = sum(count for _scope, count in groups)
        codes: list[str] = []
        for stored_scope, _count in groups:
            for code in stored_scope.disagreement(publishing_scope):
                if code not in codes:
                    codes.append(code)
        if codes:
            stored_scope, _count = groups[0]
            raise IndexScopeError(
                codes[0],
                f"{VECTOR_MIRROR_TABLE} holds {existing} vector rows for {publication.filename} "
                f"produced under {stored_scope}, which is not the profile this publication "
                f"is publishing ({publishing_scope}): binding them would leave the index on "
                "one embedder and the vector mirror on another",
                index_id=publication.index_id,
                index_version_id=version.index_version_id,
                version_scope=stored_scope,
                configured_scope=publishing_scope,
                codes=tuple(codes),
            )
        if not existing:
            # Nothing to bind, so no statement is spent: with the dual write off this is the
            # ordinary path. The probe above is the read that proves the chain reached the
            # table, and carried/missing is what the caller gets back for it.
            return VectorTagging(
                carried=len(vector_ids), existing=0, tagged=0, scope=publishing_scope
            )
        stored_scope = groups[0][0]
        cursor = self._execute(
            _TAG_VECTOR_VERSION_SQL,
            (
                version.index_version_id,
                vector_ids,
                stored_scope.embedding_model,
                stored_scope.dimension,
            ),
        )
        tagged = int(getattr(cursor, "rowcount", 0) or 0)
        if tagged != existing:
            raise ValueError(
                f"{VECTOR_MIRROR_TABLE} bound {tagged} of {existing} vector rows for "
                f"{publication.filename}; the stored profile moved during this publication, "
                "so nothing is claimed to be published that was not bound"
            )
        return VectorTagging(
            carried=len(vector_ids), existing=existing, tagged=tagged, scope=stored_scope
        )

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
        # A list, never a tuple: psycopg3 adapts a Python tuple to a row constructor, and
        # ``table_name = ANY(ROW(...))`` fails with InvalidTextRepresentation on a real
        # server. A fake connection that only looks at the SQL text cannot see the
        # difference, so the mirror would degrade on every real deployment while every
        # test stayed green.
        tables = sorted(set(_MIRROR_TABLES) | set(_COUNTER_TABLES))
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
        # The required four only: chunk_vectors degrades on its own, see VECTOR_MIRROR_TABLE.
        missing = [
            table for table in _MIRROR_REQUIRED_TABLES if not _table_is_present(present, table)
        ]
        if missing:
            reason = "index mirror tables are not migrated: " + ", ".join(missing)
            logger.warning(f"[Index] {reason}; run the migrations before trusting index bookkeeping")
            try:
                connection.close()
            except Exception:
                pass
            return IndexMirrorSession(None, counters_enabled=False, degraded_reason=reason)
        counters_enabled = all((table, _COUNTER_COLUMN) in present for table in _COUNTER_TABLES)
        return IndexMirrorSession(
            connection,
            counters_enabled=counters_enabled,
            vectors_enabled=_table_is_present(present, VECTOR_MIRROR_TABLE),
        )


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
        # Resolved once and handed down, so create_version, validate and publish cannot
        # disagree with each other about which profile this publication belongs to if the
        # environment happens to move while the steps run.
        scope = self.registry.scope
        version = self._step(
            "create_version",
            lambda: self.registry.create_version(
                index_id=index_id,
                source_version_id=publication.resource_version_id,
                backend=INDEX_BACKEND,
                chunk_count=publication.chunk_count,
                checksum=publication_checksum(publication),
                retirement=publication.retirement,
                embedding_model=scope.embedding_model,
                dimension=scope.dimension,
            ),
        )
        warnings: list[str] = []
        mirrored = False
        vector_tagging = VectorTagging()
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
                # Bound the vectors before the version is called published, and in the same
                # transaction: a current version must never be readable as owning vector rows
                # that are not tagged to it.
                named_vectors = any(str(item) for item in publication.vector_ids)
                if session.vectors_enabled:
                    vector_tagging = self._step(
                        "vector_index_version",
                        lambda: session.tag_vector_index_version(publication, version),
                    )
                    if vector_tagging.missing:
                        warnings.append(
                            f"{vector_tagging.missing} of {vector_tagging.carried} vector ids "
                            f"for {publication.resource_version_id} have no row in "
                            f"{VECTOR_MIRROR_TABLE}; the index published without a complete "
                            "vector mirror to bind"
                        )
                elif named_vectors:
                    warnings.append(
                        f"{VECTOR_MIRROR_TABLE} is not migrated; apply "
                        "migrations/0010_pgvector_chunks.sql to bind index_version_id "
                        "into the vector mirror"
                    )
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
            embedding_model=version.embedding_model,
            dimension=version.dimension,
            vector_rows_tagged=vector_tagging.tagged,
            vector_rows_missing=vector_tagging.missing,
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
        # One guard per undo step. Both calls deliberately pass enforce_scope=False: this
        # path puts back the version that was already live a moment ago and forgets the one
        # this process just built, so it is not a profile switch. Chaining them the way this
        # file used to meant a refused rollback skipped the discard, which left the aborted
        # version in a registry that a caller had already been told had failed.
        if previous_id:
            try:
                self.registry.rollback(publication.index_id, previous_id, enforce_scope=False)
            except Exception as exc:
                logger.error(
                    f"[Index] rollback after a failed {cause.stage} step did not complete: {exc}"
                )
        try:
            self.registry.discard(index_version_id, enforce_scope=False)
        except Exception as exc:
            logger.error(
                f"[Index] discarding the aborted version did not complete: {exc}"
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


# ---------------------------------------------------------------------------
# R50: incremental planning -- who actually needs re-embedding, decided for free
# ---------------------------------------------------------------------------
#
# The rebuild command predates this section and answered exactly one question: "re-embed
# everything under the profile configured now". That is the right answer for an embedder
# swap and the wrong answer for a document edit. With N documents stored, changing one of
# them used to cost N re-embedments, because nothing in the system could tell "this version
# already holds these chunk texts" apart from "these vectors were computed by some other
# model".
#
# The answer turns out to need no new table and no new state: `index_versions.checksum`
# is already a SHA-256 over the resource-version key plus the chunk texts, in stored order.
# So read the source, run it through the *same* splitter the write path uses, hash the
# result, and compare it with the digest of the version that is current for that document.
# What this costs is file IO and CPU; it costs no embedding calls, because a function that
# never receives an embedder cannot make one.
#
# The same comparison is what makes an interrupted rebuild resumable. A run that stops --
# the off-peak window closed, an operator interrupted it, the process died -- leaves behind
# the versions it published, and the next run plans from them. There is no journal to clear
# and no partial state to recognise, because the checkpoint is the publication record the
# registry already keeps. That is also why a resumed run and a single uninterrupted run
# converge on the same chunk texts: both are driven by the same digest comparison, and the
# digest of a published version does not move once it is written.
#
# Scope still comes from R22 and only from R22: the profile is `registry.scope`, which is
# `configured_embedding_scope()` unless a caller named one, and a current version whose model or
# width disagrees is *not* comparable to a fresh digest -- those vectors have to go whether
# or not the text ever moved.

PLAN_REASON_MATCHES = "index_matches_source"
PLAN_REASON_NEVER_PUBLISHED = "never_published"
PLAN_REASON_VERSION_MOVED = "catalog_version_moved"
PLAN_REASON_CONTENT_MOVED = "content_changed"
PLAN_REASON_INDEX_RETIRED = "index_retired"
PLAN_REASON_SOURCE_MISSING = "source_missing"
PLAN_REASON_PARSE_FAILED = "parse_failed"
PLAN_REASON_EMPTY_SOURCE = "source_empty"
PLAN_REASON_FORCED = "forced"

#: Reasons that leave a document unplanned: it needs work this build cannot even describe,
#: because its source cannot be read. Counting them apart from "up to date" is the point --
#: a plan that reports "nothing to do" while three files are unreadable is a lie.
PLAN_UNPLANNABLE_REASONS = frozenset(
    {PLAN_REASON_SOURCE_MISSING, PLAN_REASON_PARSE_FAILED, PLAN_REASON_EMPTY_SOURCE}
)


@dataclass(frozen=True)
class IndexPlanEntry:
    """What one catalog row needs done to its index, and what that will cost.

    `embedded_texts` is the number of embedding calls this document will cause -- zero when
    `rebuild` is False. It is a prediction of cost, not a claim that the work is already right:
    the caller still re-reads the source and re-verifies the store before publishing.
    """

    filename: str
    version: int
    index_id: str
    source_version_id: str
    rebuild: bool
    reason: str
    chunk_count: int = 0
    embedded_texts: int = 0
    checksum: str = ""
    current_index_version_id: str = ""
    current_checksum: str = ""
    current_scope: str = SCOPE_UNKNOWN
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "filename": self.filename,
            "version": self.version,
            "index_id": self.index_id,
            "source_version_id": self.source_version_id,
            "rebuild": self.rebuild,
            "reason": self.reason,
            "chunk_count": self.chunk_count,
            "embedded_texts": self.embedded_texts,
            "checksum": self.checksum,
            "current_index_version_id": self.current_index_version_id,
            "current_checksum": self.current_checksum,
            "current_scope": self.current_scope,
            "error": self.error,
        }


@dataclass(frozen=True)
class IndexPlan:
    """The whole answer of one planning pass, plus the profile it was taken under."""

    scope: EmbeddingScope
    entries: tuple[IndexPlanEntry, ...] = ()

    @property
    def documents(self) -> int:
        return len(self.entries)

    @property
    def rebuild_entries(self) -> tuple[IndexPlanEntry, ...]:
        return tuple(entry for entry in self.entries if entry.rebuild)

    @property
    def rebuild_documents(self) -> int:
        return len(self.rebuild_entries)

    @property
    def unchanged_documents(self) -> int:
        return sum(
            1 for entry in self.entries if not entry.rebuild and entry.reason == PLAN_REASON_MATCHES
        )

    @property
    def unplanned_documents(self) -> int:
        return sum(
            1
            for entry in self.entries
            if not entry.rebuild and entry.reason in PLAN_UNPLANNABLE_REASONS
        )

    @property
    def embedded_texts(self) -> int:
        """Embedding calls this plan predicts. Zero is the incremental result."""
        return sum(entry.embedded_texts for entry in self.entries)

    def by_filename(self) -> dict[str, IndexPlanEntry]:
        return {entry.filename: entry for entry in self.entries}

    def filenames_to_rebuild(self) -> tuple[str, ...]:
        return tuple(entry.filename for entry in self.rebuild_entries)

    def as_dict(self) -> dict:
        return {
            "scope": str(self.scope),
            "embedding_model": self.scope.embedding_model or SCOPE_UNKNOWN,
            "dimension": self.scope.dimension if self.scope.dimension else SCOPE_UNKNOWN,
            "documents": self.documents,
            "documents_to_rebuild": self.rebuild_documents,
            "documents_unchanged": self.unchanged_documents,
            "documents_unreadable": self.unplanned_documents,
            "embedded_texts": self.embedded_texts,
            "entries": [entry.as_dict() for entry in self.entries],
        }


def plan_index_refresh(
    rows,
    *,
    registry: IndexRegistry,
    load_text,
    chunk_texts,
    resolve_path=None,
    documents_dir: str = "",
    scope: EmbeddingScope | None = None,
    force: bool = False,
) -> IndexPlan:
    """Decide which documents need new vectors, without asking an embedder anything.

    `chunk_texts` has to be the chunker the write path uses -- pass the live retriever's splitter,
    not a lookalike. Two splitters that disagree produce two digests for one file, and the
    disagreement shows up as a library that never converges: every run finds "content
    changed" again. Everything else is injected for the same reason the publisher is: this
    is used by the rebuild command and by tests against the very same registry file.

    The comparison is deliberately conservative. A document is left alone only when the
    current version exists, is not a retirement, names this exact profile, describes this
    exact catalog version, and its stored digest equals the digest of the chunks read from
    the source right now. Every other combination schedules work -- including a legacy
    version that never recorded a profile, because an unattributable digest is not evidence
    of a match.
    """
    if not callable(load_text):
        raise TypeError("plan_index_refresh needs a load_text callable")
    if not callable(chunk_texts):
        raise TypeError("plan_index_refresh needs a chunk_texts callable")

    profile = scope if scope is not None else registry.scope
    if not profile.known:
        raise ValueError(
            "an index plan must name a usable embedding profile; the configured one is unknown"
        )

    entries: list[IndexPlanEntry] = []
    for row in rows or ():
        if not isinstance(row, dict):
            raise TypeError("plan_index_refresh rows must be catalog mappings")
        filename = str(row.get("filename") or "").strip()
        if not filename:
            continue
        version = _scope_int(row.get("version"), 1)
        candidate = DocumentIndexPublication(filename=filename, version=version)
        try:
            current = registry.current(candidate.index_id)
        except KeyError:
            current = None

        entry = {
            "filename": filename,
            "version": version,
            "index_id": candidate.index_id,
            "source_version_id": candidate.resource_version_id,
            "current_index_version_id": current.index_version_id if current else "",
            "current_checksum": current.checksum if current else "",
            "current_scope": str(current.scope) if current else SCOPE_UNKNOWN,
        }
        if callable(resolve_path):
            path = str(resolve_path(row, documents_dir) or "")
        else:
            path = str(row.get("storage_path") or "").strip()
        if not path:
            entries.append(IndexPlanEntry(**entry, rebuild=False, reason=PLAN_REASON_SOURCE_MISSING))
            continue
        try:
            content = load_text(path)
        except Exception as exc:  # an unreadable source is reported, not quietly retried
            entries.append(
                IndexPlanEntry(
                    **entry,
                    rebuild=False,
                    reason=PLAN_REASON_PARSE_FAILED,
                    error=type(exc).__name__,
                )
            )
            continue
        if not str(content or "").strip():
            entries.append(IndexPlanEntry(**entry, rebuild=False, reason=PLAN_REASON_EMPTY_SOURCE))
            continue

        chunks = tuple(str(text) for text in chunk_texts(content))
        checksum = publication_checksum(replace(candidate, chunks=chunks))
        if not chunks:
            entries.append(
                IndexPlanEntry(
                    **entry,
                    rebuild=False,
                    reason=PLAN_REASON_EMPTY_SOURCE,
                    checksum=checksum,
                )
            )
            continue

        if force:
            rebuild, reason = True, PLAN_REASON_FORCED
        elif current is None:
            rebuild, reason = True, PLAN_REASON_NEVER_PUBLISHED
        elif current.retirement:
            rebuild, reason = True, PLAN_REASON_INDEX_RETIRED
        elif current.scope != profile:
            disagreement = current.scope.disagreement(profile)
            reason = CODE_SCOPE_UNKNOWN if CODE_SCOPE_UNKNOWN in disagreement else CODE_SCOPE_MISMATCH
            rebuild = True
        elif current.source_version_id != candidate.resource_version_id:
            rebuild, reason = True, PLAN_REASON_VERSION_MOVED
        elif current.checksum == checksum:
            rebuild, reason = False, PLAN_REASON_MATCHES
        else:
            rebuild, reason = True, PLAN_REASON_CONTENT_MOVED

        entries.append(
            IndexPlanEntry(
                **entry,
                rebuild=rebuild,
                reason=reason,
                chunk_count=len(chunks),
                embedded_texts=len(chunks) if rebuild else 0,
                checksum=checksum,
            )
        )

    return IndexPlan(scope=profile, entries=tuple(entries))


def _table_is_present(present: set[tuple[str, str]], table: str) -> bool:
    required = _MIRROR_COLUMNS.get(table, ())
    return all((table, column) in present for column in required)


# ------------------------------------------------------------------ read-path switch


def read_backend() -> str:
    """Which engine answers a semantic search: ``"chroma"`` or ``"pgvector"``.

    This reads ``INDEX_BACKEND`` at call time, not at import time, for the same reason
    :func:`configured_embedding_scope` does: a process that has already imported this
    module must see the value the deployment actually settled on, and a test that sets
    the constant has to move the read path too -- otherwise the two would disagree about
    which engine is live, which is exactly the half-switched state R59b exists to avoid.

    An unrecognised value keeps reads on the shipped engine and says so in the log, the
    way :func:`app.rag.pg_store.dual_write_enabled` treats a typo in VECTOR_DUAL_WRITE.
    Silently trying the other engine is the worse failure: "pgvector" misspelled as
    "pg_vetcor" would otherwise read an empty Chroma nobody writes to.
    """
    value = str(INDEX_BACKEND or "").strip().lower()
    if value in INDEX_BACKENDS:
        return value
    if value:
        logger.warning(
            f"[Indexing] INDEX_BACKEND={value!r} is not one of "
            f"{sorted(INDEX_BACKENDS)}; reads stay on {INDEX_BACKEND_DEFAULT}."
        )
    return INDEX_BACKEND_DEFAULT


def pgvector_reads_enabled() -> bool:
    """True when the semantic read leg should ask PostgreSQL instead of Chroma.

    Default off: ``INDEX_BACKEND`` still ships as ``"chroma"``, and flipping it is the
    adoption plan's call, not this function's.
    """
    return read_backend() == PGVECTOR_BACKEND
