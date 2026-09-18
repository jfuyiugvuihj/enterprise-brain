"""R58: the PostgreSQL half of the Chroma / pgvector dual write.

================================================================== 口径 (钉死)
This module exists for one reason: to close the window in which a chunk's metadata is
visible in PostgreSQL while its vector lives only in Chroma, so authorization filtering
and semantic search can be answered by one engine. It is NOT a latency measure -- measured
retrieval is 0.242 s, 0.15% of an end-to-end request -- and it does not change which model
produces a vector, how wide that vector is, or how results are re-ranked
(docs/handoff/2026-09-17-pgvector-adoption-plan.md section 7 lists all three under
明确不做). Nothing here calls an embedding endpoint: it writes vectors somebody else made.

Chroma stays the read path until R59. pg_store writes, plus the two read-only probes in
vector_mirror(), which is what proves the target really is the database these vectors
belong to before a single one of them is sent to it.

================================================================== fail closed
The switch is VECTOR_DUAL_WRITE and its default is OFF. With it off this module imports no
psycopg, opens no connection and issues no SQL, so a private install without pgvector keeps
running exactly as it does today. With it on, a failure anywhere in the PostgreSQL leg
raises; no path reports success because Chroma took the write. The caller in
app/rag/retriever.py holds both legs in one try block and rolls PostgreSQL back when Chroma
fails, so the two engines either both hold a vector or neither does.

============================================================== no re-declaration
Dimension and model come from app/rag/indexing.py (EMBEDDING_MODEL_ENV,
EMBEDDING_DIMENSION_ENV, SCOPE_UNKNOWN, configured_embedding_scope); the error family and
the pre-write gate come from app/rag/retriever.py (VectorWriteRejectedError,
assert_writable_embeddings, the REASON_* codes). Both are imported, never copied: R22
closed with the explicit instruction that this file must not carry a second literal 768,
and R21 closed with exactly one exception family for vector writes.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from app.common.logger import logger
from app.db.connection import open_connection, parse_database_settings
from app.rag.indexing import (
    EMBEDDING_DIMENSION_ENV,
    EMBEDDING_MODEL_ENV,
    SCOPE_UNKNOWN,
    EmbeddingScope,
    configured_embedding_scope,
)
from app.rag.retriever import (
    REASON_DIMENSION_MISMATCH,
    REASON_VECTOR_COUNT_MISMATCH,
    REASON_VECTOR_MIRROR_SCOPE_MISMATCH,
    REASON_VECTOR_MIRROR_UNAVAILABLE,
    REASON_VECTOR_MIRROR_WRITE_FAILED,
    VectorWriteRejectedError,
    assert_writable_embeddings,
)

#: The only spelling that turns the PostgreSQL leg on. Anything else -- including a value
#: this module does not recognise -- leaves it off, because off is the state every ticket
#: before this one shipped and tested.
DUAL_WRITE_ENV = "VECTOR_DUAL_WRITE"
TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
FALSY_VALUES = frozenset({"0", "false", "no", "off"})

#: The same default every other PostgreSQL writer in this tree uses, so a deployment sets
#: DATABASE_URL once. It is a connection string, not an embedding口径.
DEFAULT_DATABASE_URL = "postgresql://postgres@localhost:5432/enterprise_brain"

#: The one vector_scope row this build understands, and the table it speaks about.
VECTOR_SCHEMA_VERSION = 1
DEFAULT_VECTOR_TABLE = "chunk_vectors"

_READ_SCOPE_SQL = (
    "SELECT embedding_model, dimension, distance_function "
    "FROM vector_scope WHERE schema_version = %s"
)
_READ_VECTOR_TYPE_SQL = (
    "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
    "WHERE attrelid = %s::regclass AND attname = 'embedding' AND attnum > 0 AND NOT attisdropped"
)
_CLAIM_SCOPE_SQL = (
    "UPDATE vector_scope SET embedding_model = %s, updated_at = NOW() "
    "WHERE schema_version = %s AND embedding_model = %s"
)
_UPSERT_VECTOR_SQL = (
    "INSERT INTO chunk_vectors "
    "(vector_id, filename, chunk_index, content, classification, department, content_sha256, "
    "index_version_id, embedding, embedding_model, embedding_dimension, distance_function) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s) "
    "ON CONFLICT (vector_id) DO UPDATE SET "
    "filename = EXCLUDED.filename, chunk_index = EXCLUDED.chunk_index, content = EXCLUDED.content, "
    "classification = EXCLUDED.classification, department = EXCLUDED.department, "
    "content_sha256 = EXCLUDED.content_sha256, index_version_id = EXCLUDED.index_version_id, "
    "embedding = EXCLUDED.embedding, embedding_model = EXCLUDED.embedding_model, "
    "embedding_dimension = EXCLUDED.embedding_dimension, "
    "distance_function = EXCLUDED.distance_function, updated_at = NOW()"
)
_DELETE_VECTOR_SQL = "DELETE FROM chunk_vectors WHERE vector_id = ANY(%s::text[])"
_COUNT_VECTORS_SQL = "SELECT count(*) FROM chunk_vectors"

#: Process-local observability, deliberately kept out of retriever._DIAGNOSTICS:
#: tests/test_r21_answer_side_degradation.py compares that dictionary key for key, so
#: adding mirror keys to it would be a change to R21's contract, not an addition to it.
_DIAGNOSTICS: dict = {
    "mirrored_writes": 0,
    "mirrored_deletes": 0,
    "rejected_writes": 0,
    "last_failure": None,
}


def vector_mirror_diagnostics() -> dict:
    """Mirror-side counters for /health/details and for tests. Reading it opens nothing."""
    last = _DIAGNOSTICS["last_failure"]
    return {
        "mirrored_writes": _DIAGNOSTICS["mirrored_writes"],
        "mirrored_deletes": _DIAGNOSTICS["mirrored_deletes"],
        "rejected_writes": _DIAGNOSTICS["rejected_writes"],
        "last_failure": dict(last) if last else None,
    }


def reset_vector_mirror_diagnostics() -> None:
    """Clear process state. Tests only; production code must not call it."""
    _DIAGNOSTICS["mirrored_writes"] = 0
    _DIAGNOSTICS["mirrored_deletes"] = 0
    _DIAGNOSTICS["rejected_writes"] = 0
    _DIAGNOSTICS["last_failure"] = None


def _record_failure(reason: str, detail: str) -> None:
    _DIAGNOSTICS["last_failure"] = {
        "reason": reason,
        "detail": str(detail)[:400],
        "at": time.time(),
    }


def _refusal(message: str, reason: str, model: str) -> "VectorWriteRejectedError":
    """One place that turns a mirror problem into R21's exception, with the counters."""
    _record_failure(reason, message)
    _DIAGNOSTICS["rejected_writes"] += 1
    return VectorWriteRejectedError(message, reason=reason, model=model or "")


def dual_write_enabled() -> bool:
    """Is the PostgreSQL leg on? Off unless an operator says so, in those words.

    An unrecognised value is a typo waiting to be deployed ("ture"), so it is reported and
    then treated as off: the state that keeps working is the state that was shipped.
    """
    raw = str(os.getenv(DUAL_WRITE_ENV, "") or "").strip().lower()
    if raw in TRUTHY_VALUES:
        return True
    if raw in FALSY_VALUES:
        return False
    if raw:
        logger.warning(
            f"[VectorMirror] {DUAL_WRITE_ENV}={raw!r} is not recognised; the PostgreSQL leg "
            f"stays off. Use one of {sorted(TRUTHY_VALUES)} to enable it."
        )
    return False


def resolve_database_url() -> str:
    return str(os.getenv("DATABASE_URL", "") or "").strip() or DEFAULT_DATABASE_URL


def _with_connect_timeout(url: str, seconds: int = 2) -> str:
    """Pin a connect timeout into the conninfo instead of reaching past the boundary.

    app/db/connection.open_connection() is the sanctioned place psycopg gets imported, and
    it forwards the URL as it stands, so the timeout travels as a libpq parameter. A URL
    that already carries one is left alone: the operator's number beats our default.
    """
    if "connect_timeout=" in url:
        return url
    return url + ("&" if "?" in url else "?") + f"connect_timeout={int(seconds)}"


def _row_value(row, key: str, position: int):
    """Read a probe column from either a dict_row or a plain tuple row.

    A fake connection in a test answers with tuples; the production path in
    app/rag/indexing.py answers with dicts. Neither spelling may be required.
    """
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[position]
    except (IndexError, TypeError, KeyError):
        return None


def _vector_literal(vector) -> str:
    """Text form of a vector: pgvector parses '[0.1,0.2]' into vector and psycopg has no
    adapter for the type. json's non-strict float spellings are what pgvector accepts.
    """
    return json.dumps([float(value) for value in vector])

@dataclass(frozen=True)
class VectorScope:
    """What migrations/0010_pgvector_chunks.sql recorded about this database."""

    embedding_model: str
    dimension: int
    distance_function: str

    @property
    def unclaimed(self) -> bool:
        """True when 0010 found nothing to label and left the profile to the first writer."""
        return self.embedding_model == SCOPE_UNKNOWN

    def as_dict(self) -> dict:
        return {
            "embedding_model": self.embedding_model,
            "dimension": self.dimension,
            "distance_function": self.distance_function,
        }


def scope_disagreements(configured: EmbeddingScope, scope: VectorScope) -> tuple[str, ...]:
    """Why the running profile is not the stored one, as stable codes.

    An unclaimed model is not a disagreement: 0010 recorded SCOPE_UNKNOWN because the
    database was empty, and the first write labels it. A dimension is never unknown, so a
    width difference always means two profiles would end up in one table -- R22's case.
    """
    codes: list[str] = []
    if scope.dimension != configured.dimension:
        codes.append("embedding_dimension_drift")
    if not scope.unclaimed and scope.embedding_model != configured.embedding_model:
        codes.append("embedding_model_drift")
    return tuple(codes)


class VectorMirror:
    """One PostgreSQL transaction holding the vector side of a write.

    Deliberately neither a pool nor long-lived: the caller opens it, uses it for one
    document, and closes it, so the transaction boundary matches the boundary of the Chroma
    batch loop it is paired with. psycopg3 begins a transaction at the first statement and
    holds it until commit(), which is what makes "both engines or neither" expressible.
    """

    def __init__(self, connection, *, scope: VectorScope, column_type: str, vector_table: str):
        self.connection = connection
        self.scope = scope
        self.column_type = column_type
        self.vector_table = vector_table
        self.written = 0
        self.deleted = 0
        self._claimed = not scope.unclaimed
        self._closed = False

    def _profile_model(self) -> str:
        return configured_embedding_scope().embedding_model or self.scope.embedding_model

    def _refuse(self, reason: str, message: str, model: str) -> VectorWriteRejectedError:
        return _refusal(message, reason, model)

    def _as_int(self, value, vector_id: str, field: str, model: str, *, allow_none: bool):
        """Column-typed reading of a metadata key. Garbage is refused, never coerced."""
        if value is None and allow_none:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise self._refuse(
                REASON_VECTOR_MIRROR_WRITE_FAILED,
                f"镜像拒写：{vector_id} 的 {field}={value!r} 不是整数",
                model,
            ) from None

    # -- gates ---------------------------------------------------------------
    def build_rows(self, ids, documents, metadatas, embeddings) -> list:
        """Everything must hold before the first statement of a batch is sent.

        assert_writable_embeddings is R21's gate and is not re-implemented here. This adds
        the one thing only the mirror can know -- the width this database was migrated for
        -- plus the metadata shape the columns need. A refusal means nothing was sent: this
        function opens no cursor and issues no SQL.
        """
        vector_list = list(embeddings)
        id_list = [str(item) for item in ids]
        document_list = list(documents)
        metadata_list = list(metadatas)
        model = self._profile_model()
        if len(vector_list) != len(id_list):
            raise self._refuse(
                REASON_VECTOR_COUNT_MISMATCH,
                f"镜像拒写：向量 {len(vector_list)} 条与 id {len(id_list)} 条不符",
                model,
            )
        assert_writable_embeddings(vector_list, len(document_list), cause="vector_mirror")
        if len(document_list) != len(id_list) or len(metadata_list) != len(id_list):
            raise self._refuse(
                REASON_VECTOR_COUNT_MISMATCH,
                "镜像拒写：id / document / metadata 条数不一致，无法逐条对齐",
                model,
            )
        rows: list = []
        for vector_id, document, metadata, vector in zip(
            id_list, document_list, metadata_list, vector_list
        ):
            if len(vector) != self.scope.dimension:
                raise self._refuse(
                    REASON_DIMENSION_MISMATCH,
                    f"镜像拒写：{vector_id} 长度 {len(vector)}，本库 vector_scope 声明 "
                    f"{self.scope.dimension}；R22 禁止两个维度的向量共存于一个库",
                    model,
                )
            values = dict(metadata or {})
            filename = str(values.get("filename") or "")
            if not filename:
                raise self._refuse(
                    REASON_VECTOR_MIRROR_WRITE_FAILED,
                    f"镜像拒写：{vector_id} 的元数据没有 filename，落库后无法按文档删除",
                    model,
                )
            classification = self._as_int(
                values.get("classification"), vector_id, "classification", model, allow_none=True
            )
            chunk_index = self._as_int(
                values.get("chunk_index"), vector_id, "chunk_index", model, allow_none=False
            )
            rows.append(
                (
                    vector_id,
                    filename,
                    chunk_index,
                    document,
                    classification,
                    str(values.get("department") or ""),
                    str(values.get("hash") or "") or None,
                    # index_version_id, NULL by design: the retriever does not know the
                    # index version, the publication that follows it does. Inventing one
                    # here is R22's silent desync, so the row says "not yet published" and
                    # scripts/compare_vector_recall.py counts those rows instead.
                    None,
                    _vector_literal(vector),
                    model,
                    self.scope.dimension,
                    self.scope.distance_function,
                )
            )
        return rows

    # -- writes ------------------------------------------------------------
    def add(self, *, ids, documents, metadatas, embeddings) -> int:
        """Mirror one batch of vectors; returns the number of rows sent.

        Vectors travel positionally, never inside metadata, so a caller cannot line a vector
        up with the wrong chunk by accident.
        """
        rows = self.build_rows(ids, documents, metadatas, embeddings)
        if not rows:
            return 0
        try:
            self._claim_scope()
            with self.connection.cursor() as cursor:
                cursor.executemany(_UPSERT_VECTOR_SQL, rows)
        except VectorWriteRejectedError:
            raise
        except Exception as exc:  # psycopg errors, missing table, aborted transaction
            raise self._refuse(
                REASON_VECTOR_MIRROR_WRITE_FAILED,
                f"镜像写入失败：{type(exc).__name__}: {exc}",
                self.scope.embedding_model,
            ) from exc
        self.written += len(rows)
        _DIAGNOSTICS["mirrored_writes"] += len(rows)
        return len(rows)

    def delete(self, ids) -> int:
        """Mirror a delete, inside the caller's transaction."""
        vector_ids = [str(item) for item in ids if str(item)]
        if not vector_ids:
            return 0
        try:
            self.connection.execute(_DELETE_VECTOR_SQL, (vector_ids,))
        except Exception as exc:
            raise self._refuse(
                REASON_VECTOR_MIRROR_WRITE_FAILED,
                f"镜像删除失败：{type(exc).__name__}: {exc}",
                self.scope.embedding_model,
            ) from exc
        self.deleted += len(vector_ids)
        _DIAGNOSTICS["mirrored_deletes"] += len(vector_ids)
        return len(vector_ids)

    def _claim_scope(self) -> None:
        """First writer labels an unclaimed profile; see 0010's SCOPE_UNKNOWN branch."""
        if self._claimed:
            return
        self.connection.execute(
            _CLAIM_SCOPE_SQL, (self._profile_model(), VECTOR_SCHEMA_VERSION, SCOPE_UNKNOWN)
        )
        self._claimed = True

    # -- transaction edge --------------------------------------------------
    def commit(self) -> None:
        """Make the mirrored rows visible. Called last, after Chroma accepted the write."""
        try:
            self.connection.commit()
        except Exception as exc:
            raise self._refuse(
                REASON_VECTOR_MIRROR_WRITE_FAILED,
                f"镜像提交失败：{type(exc).__name__}: {exc}",
                self.scope.embedding_model,
            ) from exc

    def rollback(self) -> None:
        """Undo the PostgreSQL half. A failure here is logged, not raised: the caller is
        already unwinding a failed write, and a second exception would bury the first.
        """
        try:
            self.connection.rollback()
        except Exception as exc:  # pragma: no cover - a dead connection cannot be helped
            logger.warning(
                f"[VectorMirror] rollback failed ({exc}); the transaction ends with the connection"
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.connection.close()
        except Exception as exc:  # pragma: no cover
            logger.warning(f"[VectorMirror] close failed ({exc})")

    def __enter__(self) -> "VectorMirror":
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is not None:
            self.rollback()
        self.close()
        return False

    def vector_count(self) -> int:
        """Rows currently mirrored. Read-only; used by tests and the comparison script."""
        row = self.connection.execute(_COUNT_VECTORS_SQL).fetchone()
        return int(_row_value(row, "count", 0) or 0)


def _connect(url: str, connection_factory):
    if connection_factory is not None:
        return connection_factory()
    settings = parse_database_settings(_with_connect_timeout(url))
    if not settings.is_postgresql:
        raise VectorWriteRejectedError(
            "向量镜像只接受 PostgreSQL 连接串",
            reason=REASON_VECTOR_MIRROR_UNAVAILABLE,
            model=configured_embedding_scope().embedding_model,
        )
    try:
        return open_connection(settings)
    except ImportError as exc:
        raise VectorWriteRejectedError(
            f"镜像已开启但 psycopg 不可用（{exc}）：安装 psycopg[binary]，或关掉 {DUAL_WRITE_ENV}",
            reason=REASON_VECTOR_MIRROR_UNAVAILABLE,
            model=configured_embedding_scope().embedding_model,
        ) from exc
    except Exception as exc:
        raise VectorWriteRejectedError(
            f"镜像已开启但连不上 {settings.host}:{settings.port}/{settings.database}"
            f"（{type(exc).__name__}: {exc}）",
            reason=REASON_VECTOR_MIRROR_UNAVAILABLE,
            model=configured_embedding_scope().embedding_model,
        ) from exc


def vector_mirror(*, connection_factory=None, url: str | None = None,
                  vector_table: str = DEFAULT_VECTOR_TABLE) -> "VectorMirror | None":
    """Open the mirror for one document write, or return None when the switch is off.

    Returning None is the entire behaviour of a disabled switch: the caller then issues no
    PostgreSQL statement at all, so an install without pgvector is untouched by this ticket.
    With the switch on, both probes have to agree before a vector is accepted -- 0010's
    vector_scope row and the real column type, checked against the running EMBEDDING_MODEL
    and EMBEDDING_DIMENSION. A database that is merely unreachable is also a refusal rather
    than a degraded write, because a silently missing mirror is exactly the half-state this
    ticket exists to remove; the reason code is what an upload operator reads.
    """
    if not dual_write_enabled():
        return None
    configured = configured_embedding_scope()
    connection = _connect(url or resolve_database_url(), connection_factory)
    try:
        scope_row = connection.execute(_READ_SCOPE_SQL, (VECTOR_SCHEMA_VERSION,)).fetchone()
        if scope_row is None:
            raise VectorWriteRejectedError(
                f"镜像已开启但 vector_scope 里没有第 {VECTOR_SCHEMA_VERSION} 行： "
                "先执行 migrations/0010_pgvector_chunks.sql",
                reason=REASON_VECTOR_MIRROR_UNAVAILABLE,
                model=configured.embedding_model,
            )
        scope = VectorScope(
            embedding_model=str(_row_value(scope_row, "embedding_model", 0) or ""),
            dimension=int(_row_value(scope_row, "dimension", 1) or 0),
            distance_function=str(_row_value(scope_row, "distance_function", 2) or ""),
        )
        type_row = connection.execute(_READ_VECTOR_TYPE_SQL, (vector_table,)).fetchone()
        column_type = str(_row_value(type_row, "format_type", 0) or "") if type_row is not None else ""
        if column_type != f"vector({scope.dimension})":
            # 0010 declared a width and the column does not carry it: an unmigrated
            # database, a hand-edited one, or a 0002 that was never retyped. Any of those
            # would take a vector pgvector cannot index, which is R22's failure mode.
            raise VectorWriteRejectedError(
                f"镜像拒开：{vector_table}.embedding 的实际类型是 "
                f"{column_type or '不存在'}，与 vector_scope 声明的 vector({scope.dimension}) 不符",
                reason=REASON_VECTOR_MIRROR_SCOPE_MISMATCH,
                model=configured.embedding_model,
            )
        disagreements = scope_disagreements(configured, scope)
        if disagreements:
            raise VectorWriteRejectedError(
                f"镜像拒开：本库口径 model={scope.embedding_model} "
                f"dimension={scope.dimension}，运行时 {EMBEDDING_MODEL_ENV}="
                f"{configured.embedding_model} {EMBEDDING_DIMENSION_ENV}="
                f"{configured.dimension}（{', '.join(disagreements)}）；"
                "R22 不允许一个库里同时存在两套向量",
                reason=REASON_VECTOR_MIRROR_SCOPE_MISMATCH,
                model=configured.embedding_model,
            )
        return VectorMirror(
            connection, scope=scope, column_type=column_type, vector_table=vector_table
        )
    except Exception as exc:
        # Whatever the probes said, the transaction never got a vector: close the
        # connection so an implicit BEGIN cannot linger behind a refused open.
        connection.close()
        if isinstance(exc, VectorWriteRejectedError):
            raise
        _record_failure(
            REASON_VECTOR_MIRROR_UNAVAILABLE, f"镜像探测失败：{type(exc).__name__}: {exc}"
        )
        raise VectorWriteRejectedError(
            f"镜像探测失败：{type(exc).__name__}: {exc}",
            reason=REASON_VECTOR_MIRROR_UNAVAILABLE,
            model=configured.embedding_model,
        ) from exc
