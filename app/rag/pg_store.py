"""R58: the PostgreSQL half of the Chroma / pgvector dual write.

================================================================== 口径 (钉死)
This module exists for one reason: to close the window in which a chunk's metadata is
visible in PostgreSQL while its vector lives only in Chroma, so authorization filtering
and semantic search can be answered by one engine. It is NOT a latency measure -- measured
retrieval is 0.242 s, 0.15% of an end-to-end request -- and it does not change which model
produces a vector, how wide that vector is, or how results are re-ranked
(docs/handoff/2026-09-17-pgvector-adoption-plan.md section 7 lists all three under
明确不做). Nothing here calls an embedding endpoint: it writes vectors somebody else made.

Chroma is still the read path: R59b added the pgvector read leg at the bottom of this
file, but its switch -- indexing.INDEX_BACKEND -- still ships on "chroma", so which engine
answers a search does not change until somebody flips that on purpose. Everything the read
leg needs is already here: it reuses vector_mirror(), so the 0010 scope row and the real
column type are the same two probes that gate writes, never a second口径 check.

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

#: Columns in the order VectorMirror.build_rows lays one out for _UPSERT_VECTOR_SQL. Only
#: read to name the offending column in an R130 refusal; a mismatch with the SQL above is
#: caught by tests/test_r130_text_unencodable_is_named_refusal.py, not by PostgreSQL.
_UPSERT_COLUMNS = (
    "vector_id",
    "filename",
    "chunk_index",
    "content",
    "classification",
    "department",
    "content_sha256",
    "index_version_id",
    "embedding",
    "embedding_model",
    "embedding_dimension",
    "distance_function",
)

#: R130 判据②: PostgreSQL refuses U+0000 in any text column, psycopg refuses the whole
#: executemany batch over it, and the failure that reaches an operator is a bare class
#: name. The mirror therefore refuses by name before it opens a cursor.
#: app/rag/loader.py drops this same character on the way out of every parser; the
#: literal lives here too because a storage layer that imports the parsing layer would
#: drag pypdf into every process that only wants to read vector_mirror_diagnostics().
REASON_VECTOR_MIRROR_TEXT_UNENCODABLE = "vector_mirror_text_unencodable"
NUL_CHARACTER = "\x00"

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
        -- plus the metadata shape the columns need, and the one thing the column types
        cannot survive: a NUL character (R130). A refusal means nothing was sent: this
        function opens no cursor and issues no SQL, and it never cleans a value on its way
        in -- dropping the character is the loader's job, naming the refusal is this
        layer's, and a mirror that silently rewrote text would leave Chroma and
        PostgreSQL holding two different documents.
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
        try:
            # R21's gate, called and not re-implemented. Its refusal is recorded on the
            # mirror side too, so a mirrored batch rejected by the shared gate still shows
            # up in vector_mirror_diagnostics(), not only in retriever's counters.
            assert_writable_embeddings(vector_list, len(document_list), cause="vector_mirror")
        except VectorWriteRejectedError as exc:
            _record_failure(exc.reason, str(exc))
            raise
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
            row = (
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
                # R76 is that publication: IndexMirrorSession.tag_vector_index_version
                # stamps the id in the same transaction that marks the version published.
                # A re-upsert here still belongs to no version, which is the correct
                # answer -- a freshly written vector is newer than anything published.
                None,
                _vector_literal(vector),
                model,
                self.scope.dimension,
                self.scope.distance_function,
            )
            # R130 判据②: text a PostgreSQL column cannot hold is refused here, by
            # name, with the document that carries it -- which is the information
            # psycopg's DataError throws away and executemany is too late to add.
            for column, value in zip(_UPSERT_COLUMNS, row):
                if isinstance(value, str) and NUL_CHARACTER in value:
                    raise self._refuse(
                        REASON_VECTOR_MIRROR_TEXT_UNENCODABLE,
                        f"镜像拒写：filename={filename} chunk_index={chunk_index} "
                        f"(vector_id={vector_id}) 的列 {column} 含 "
                        f"{value.count(NUL_CHARACTER)} 枚 \\x00（首枚偏移 "
                        f"{value.index(NUL_CHARACTER)}），PostgreSQL text 列收不下这个"
                        "字符；整批零写入，镜像层不代为清洗（清洗属 loader 净化层）",
                        model,
                    )
            rows.append(row)
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


# ================================================================== reads (R59b)
#
# The read half of the mirror this file already writes: one SQL top-k over chunk_vectors,
# with the caller's scope filter pushed into the WHERE clause.
#
# Fail-closed where it matters more than availability: an authorisation filter
# :func:`sql_scope_filter` does not recognise must never become "no WHERE clause". Every
# refusal below raises, and the caller in app/rag/retriever.py answers by falling back to
# the legacy Chroma leg -- which enforces the same filter natively -- so a refusal costs a
# slower answer, never a wider one.

#: SQL operator per 0010's CHECK spelling of distance_function. The index 0010 builds is
#: ``vector_l2_ops``, so l2 has to travel as <-> or the query will not use it. An unmapped
#: spelling is a refusal, not a guess: R120's lesson is that a guessed operator still
#: returns a number, and a number from the wrong arithmetic looks exactly like a result.
DISTANCE_OPERATORS = {"l2": "<->", "cosine": "<=>", "ip": "<#>"}

#: What a read has to hand back to rebuild ``retriever._hit_dicts``' shape. Deliberately
#: not SELECT *: that dict is R44's contract, and a column that stops existing has to fail
#: here by name rather than turn into a silently missing metadata key.
_READ_COLUMNS = ("vector_id", "content", "filename", "chunk_index", "classification",
                 "department")

#: R59 block 1 criterion (1): once reads are switched, the *lexical* leg's corpus comes from
#: here too, so the whole read path stops asking the retiring engine. No embedding column:
#: BM25 scores text, and shipping 768 floats per row to build a token index is a different
#: bill for the same answer. ORDER BY vector_id keeps two runs byte-comparable. The column
#: list is _READ_COLUMNS verbatim -- the same six the top-k read hands back -- so a corpus
#: and a search can never disagree about which metadata exists. It sits down there with
#: that list, not up here with the write statements, because it copies the list.
_READ_CORPUS_SQL = ("SELECT " + ", ".join(_READ_COLUMNS)
                    + " FROM " + DEFAULT_VECTOR_TABLE + " ORDER BY vector_id")

#: The only scope columns the retrieval gate speaks, and the SQL type each needs.
_SCOPE_COLUMNS = {"classification": "integer", "department": "text"}

# ===================================================== HNSW candidate width (R386)
#:
#: pgvector answers an HNSW search from a candidate list whose width it reads from a GUC,
#: and the server ships that GUC narrower than the width the retiring engine answers with.
#: The evidence is in this tree, twice: migrations/0010_pgvector_chunks.sql:40-46 records
#: the measured legacy configuration (its ef_search), and app/rag/loader.py:247 quotes the
#: same number while explaining why near-duplicates starve a search. Nothing in app/** ever
#: set the GUC: `rg -n ef_search app/ migrations/` returns only those two comments. So
#: flipping INDEX_BACKEND alone would have narrowed every semantic read by itself, and this
#: block is what makes that flip width-preserving by code rather than by luck or by a note.
#:
#: One source, one reader -- the R380 rule, a defence written in two places is a defence
#: that drifts. :data:`HNSW_EF_SEARCH_DEFAULT` is the only spelling of the number in this
#: file, :func:`_apply_hnsw_ef_search` is the only place it becomes SQL, and
#: :func:`search_vectors` is its only caller. Anything else that wants the number -- a test,
#: a script, a doc -- asks :func:`configured_hnsw_ef_search`; the guard test goes one step
#: further and derives the retiring engine's width from 0010's own comment instead of
#: retyping it, so a second copy of the digits is a red test, not a style complaint.
ENV_HNSW_EF_SEARCH = "PGVECTOR_EF_SEARCH"

#: The knob's absent spelling, i.e. what an install that never heard of this ticket gets:
#: the width the retiring engine is measured to answer with. "Unset" and "set like the old
#: engine" are therefore the same statement, which is the whole point of the ticket.
HNSW_EF_SEARCH_DEFAULT = 100

#: pgvector's own spelling of the GUC, and the one statement that carries it.
#:
#: A bare ``SET`` would leave the value on the *session*: a connection that outlives this
#: read -- a pool, a reused handle, a script that keeps asking -- would answer the next
#: caller at a width nobody asked for. ``set_config(name, value, is_local)`` with
#: ``is_local`` = TRUE is ``SET LOCAL`` in function form: PostgreSQL documents a local
#: setting as rolled back at the end of the current transaction, and the read leg never
#: commits (:func:`read_topk` closes the connection over an implicit BEGIN, which is what
#: makes the locality load-bearing rather than decorative). The function form is not a
#: preference either: ``SET`` takes no bind parameter, so a bare SET would have to paste
#: the number into the statement text -- the second copy of the digits this section forbids.
#: The GUC's own bounds are PostgreSQL's to enforce; see :func:`configured_hnsw_ef_search`.
HNSW_EF_SEARCH_GUC = "hnsw.ef_search"
_APPLY_HNSW_EF_SEARCH_SQL = "SELECT set_config(%s, %s, TRUE)"

#: Read-leg stable codes. They live here -- like REASON_VECTOR_MIRROR_TEXT_UNENCODABLE
#: above -- precisely so they stay out of retriever's R21 degradation-code set, which a
#: test compares key for key.
REASON_VECTOR_READ_FILTER_UNTRANSLATABLE = "vector_read_filter_untranslatable"
REASON_VECTOR_READ_WITHOUT_DUAL_WRITE = "vector_read_without_dual_write"
REASON_VECTOR_READ_OPERATOR_UNKNOWN = "vector_read_operator_unknown"
REASON_VECTOR_READ_TABLE_UNRECOGNISED = "vector_read_table_unrecognised"
REASON_VECTOR_READ_FAILED = "vector_read_failed"


class VectorReadRejectedError(RuntimeError):
    """The pgvector read leg refuses to answer. ``reason`` says which guard fired."""

    def __init__(self, message: str, *, reason: str = REASON_VECTOR_READ_FAILED):
        super().__init__(message)
        self.reason = reason


class ScopeFilterUntranslatable(VectorReadRejectedError):
    """Raised instead of issuing a vector query with a missing or partial WHERE clause."""

    def __init__(self, message: str):
        super().__init__(message, reason=REASON_VECTOR_READ_FILTER_UNTRANSLATABLE)


def _scope_clause(column: str, values, sql_type: str):
    """One ``column = ANY(%s::type[])`` predicate, with no coercion of the values.

    The bind list is wrapped -- ``([kept],)`` -- because this predicate owns exactly one
    ``%s``: returning the inner list bare makes :func:`sql_scope_filter`'s ``$and`` branch
    ``extend`` the individual levels into the parameter tuple, so a two-key filter ships
    five values against four placeholders. The 2026-09-24 first pass of
    tests/test_r59b_pg_read_switch.py caught that off a fake connection that has since
    been made to count placeholders, because a fake that ignores arity is a fake that
    approves broken SQL.
    """
    if not isinstance(values, (list, tuple, set, frozenset)):
        raise ScopeFilterUntranslatable(
            f"{column} 的谓词不是集合：{type(values).__name__}")
    kept: list = []
    for value in values:
        if sql_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ScopeFilterUntranslatable(
                    f"{column} 收了非整数密级 {value!r}：密级这一维不做字符串→整数猜测")
            kept.append(int(value))
        elif not isinstance(value, str):
            raise ScopeFilterUntranslatable(
                f"{column} 收了非字符串部门名 {value!r}")
        elif not value.strip():
            # R59 block 1 criterion (2c), the permission half: the writer normalises a
            # missing department to "" (build_rows, str(values.get("department") or "")),
            # while the retiring engine's metadata simply has no such key. Those two agree
            # for every value app/rag/filters.py can actually build -- it drops falsy
            # departments before assembling $in -- and disagree on exactly one spelling: an
            # $in that contains the empty string, which SQL answers "yes" to and a missing
            # key answers "no" to. Refusing is the only honest move: guessing either side
            # would make the pushed-down filter wider than the one it replaces.
            raise ScopeFilterUntranslatable(
                f"{column} 的 $in 里有空串：两侧对『没有部门』的表示法不同，"
                "这一档不做猜测，宁可拒答")
        else:
            kept.append(value)
    return f"{column} = ANY(%s::{sql_type}[])", [kept]


def sql_scope_filter(where):
    """Translate the retrieval scope's Chroma-shaped ``where`` into a SQL predicate.

    What is accepted is what app/rag/filters.py actually builds -- a bare
    ``{"classification": {"$in": [...]}}``, a bare ``{"department": {"$in": [...]}}``, and
    ``{"$and": [that, that]}`` -- plus "no filter at all" (``None`` / ``{}``), the shape
    the hot set and scripts/compare_vector_recall.py use. Everything else raises
    ScopeFilterUntranslatable: an ``$or``, a second top-level key, a bare equality, any
    operator other than ``$in``, a value that is not a collection of the right type.

    Returns ``(clause, params)``, and ``clause`` is "" only when there is genuinely no
    predicate to add. A row whose classification is NULL drops out of ``= ANY`` exactly as
    a row missing the key drops out of Chroma's ``$in``, so the two engines do not differ
    in who is allowed to see what.
    """
    if where is None:
        return "", []
    if not isinstance(where, dict):
        raise ScopeFilterUntranslatable(f"where 不是字典：{type(where).__name__}")
    if not where:
        return "", []
    if len(where) != 1:
        raise ScopeFilterUntranslatable(
            f"一份 where 只允许一个顶层键，拿到 {sorted(where)}")
    key, value = next(iter(where.items()))
    if key == "$and":
        if not isinstance(value, (list, tuple)) or not value:
            raise ScopeFilterUntranslatable("$and 需要非空列表")
        clauses: list = []
        params: list = []
        for item in value:
            clause, part = sql_scope_filter(item)
            if clause:
                clauses.append(clause)
                params.extend(part)
        if not clauses:
            return "", []
        return "(" + " AND ".join(clauses) + ")", params
    if key not in _SCOPE_COLUMNS:
        raise ScopeFilterUntranslatable(
            f"不认识的作用域列 {key!r}：检索闸门只发 classification / department 两维")
    if not isinstance(value, dict) or set(value) != {"$in"}:
        raise ScopeFilterUntranslatable(
            f"{key} 只接受 $in 这一种算符，拿到 {sorted(value) if isinstance(value, dict) else type(value).__name__}")
    return _scope_clause(key, value["$in"], _SCOPE_COLUMNS[key])


def _read_row_dict(row):
    names = _READ_COLUMNS + ("distance",)
    if isinstance(row, dict):
        return {name: row.get(name) for name in names}
    return dict(zip(names, row))


def configured_hnsw_ef_search(environ=None) -> int:
    """The HNSW candidate width a PG read asks for: the operator's knob, else the pinned one.

    Resolved at call time, never frozen at import -- the same reason ``read_backend()``
    resolves ``INDEX_BACKEND`` when it is asked rather than once at load: a deployment that
    says something after the module was imported has to be heard, and a test that moves the
    knob must not have to reload a product module to be believed.

    An unusable value falls back to :data:`HNSW_EF_SEARCH_DEFAULT` with a warning, which is
    how ``indexing._configured_dimension`` already treats an unusable width. The fallback is
    not a guess: that default *is* the width the retiring engine answers with, so a typo in
    the knob costs a setting that did not take effect, never an answer narrower than the
    engine it is replacing. No upper bound lives here on purpose -- the GUC bounds are
    PostgreSQL's to enforce, and a value the server refuses raises inside this transaction,
    where app/rag/retriever.py already turns any read-leg exception into a named bypass.
    The bound it enforces is the server's own and is worth measuring rather than assuming:
    0.8.6 in the R59 sandbox answers `set_config('hnsw.ef_search', '0', TRUE)` with
    "0 is outside the valid range for parameter hnsw.ef_search (1 .. 1000)".
    """
    source = os.environ if environ is None else environ
    raw = str(source.get(ENV_HNSW_EF_SEARCH, "") or "").strip()
    if not raw:
        return HNSW_EF_SEARCH_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            f"[Index] {ENV_HNSW_EF_SEARCH}={raw!r} 不是整数，HNSW 候选宽度按本构建的默认值走")
        return HNSW_EF_SEARCH_DEFAULT
    if value < 1:
        logger.warning(
            f"[Index] {ENV_HNSW_EF_SEARCH}={value} 不可用（这一档只收正整数），"
            "HNSW 候选宽度按本构建的默认值走")
        return HNSW_EF_SEARCH_DEFAULT
    return value


def _apply_hnsw_ef_search(connection) -> int:
    """Set the candidate width for the rest of *this* transaction and report what was set.

    One call site, :func:`search_vectors`, on the connection that is about to run the
    ranking SQL: a width set on another connection, or set after the scan started, buys
    nothing. Setting it locally is what keeps a reused or pooled connection from carrying
    one request's width into the next one, so the value's lifetime is the read's lifetime.
    """
    value = configured_hnsw_ef_search()
    connection.execute(_APPLY_HNSW_EF_SEARCH_SQL, (HNSW_EF_SEARCH_GUC, str(value)))
    return value


def search_vectors(*, connection, vector_table: str, distance_function: str,
                   query_vector, k: int, where=None) -> list:
    """Top-k over chunk_vectors with the caller's scope filter inside the SQL.

    The query vector travels as pgvector's text form (:func:`_vector_literal`), because
    psycopg has no adapter for the type -- the same route the writer takes, so a read can
    never be measuring an encoding that was not stored.

    The ranking statement is also preceded, on this same connection and inside this same
    transaction, by :func:`_apply_hnsw_ef_search`. That ordering is the ticket: the same SQL
    with a different candidate width is a different question, and the response does not say
    which question was asked. It runs after every validation below, so a refusal still
    reaches the server as zero statements.
    """
    if vector_table != DEFAULT_VECTOR_TABLE:
        raise VectorReadRejectedError(
            f"读腿只认 {DEFAULT_VECTOR_TABLE}，拿到 {vector_table!r}",
            reason=REASON_VECTOR_READ_TABLE_UNRECOGNISED)
    operator = DISTANCE_OPERATORS.get(str(distance_function or "").strip().lower())
    if operator is None:
        raise VectorReadRejectedError(
            f"vector_scope.distance_function={distance_function!r} 没有对应的 SQL 算符："
            "猜一个算符换来的排序，和正确答案长得一模一样",
            reason=REASON_VECTOR_READ_OPERATOR_UNKNOWN)
    clause, params = sql_scope_filter(where)
    literal = _vector_literal(query_vector)
    limit = int(k) if int(k) > 0 else 0
    sql = ("SELECT " + ", ".join(_READ_COLUMNS) + ", embedding " + operator
           + " %s::vector AS distance FROM " + vector_table
           + (" WHERE " + clause if clause else "")
           + " ORDER BY embedding " + operator + " %s::vector LIMIT %s")
    _apply_hnsw_ef_search(connection)
    rows = connection.execute(sql, (literal, *params, literal, limit)).fetchall()
    return [_read_row_dict(row) for row in rows]


def read_topk(*, query_vector, k: int, where=None, connection_factory=None,
              url: str | None = None, vector_table: str = DEFAULT_VECTOR_TABLE) -> list:
    """One semantic top-k over the mirror, under the same two probes that gate writes.

    ``connection_factory`` is the test seam :func:`vector_mirror` already exposes; with it
    unset this opens a fresh connection per call, which is what the write side does too.
    """
    mirror = vector_mirror(connection_factory=connection_factory, url=url,
                           vector_table=vector_table)
    if mirror is None:
        raise VectorReadRejectedError(
            f"{DUAL_WRITE_ENV} 关着：chunk_vectors 里没有人在写的向量，把读切过去只会问出一库空。"
            "切读的前置是双写先开满一轮重建，不是把这枚写开关当读开关用",
            reason=REASON_VECTOR_READ_WITHOUT_DUAL_WRITE)
    try:
        return search_vectors(connection=mirror.connection,
                              vector_table=mirror.vector_table,
                              distance_function=mirror.scope.distance_function,
                              query_vector=query_vector, k=k, where=where)
    finally:
        # Reads never commit: whatever transaction the probes opened ends with the
        # connection, so this path cannot leave a row behind even if handed one that writes.
        mirror.close()


_READ_DIAGNOSTICS: dict = {"attempts": 0, "answered": 0, "rows": 0, "bypasses": {},
                           "last_bypass": None}


def read_corpus(*, connection_factory=None, url: str | None = None,
                vector_table: str = DEFAULT_VECTOR_TABLE) -> list:
    """Every mirrored row's text and metadata, under the same two probes that gate writes.

    This is what the lexical leg of a switched deployment reads its corpus from, so that
    "reads are on PostgreSQL" means the whole read path -- not only the ANN leg. It is a
    full scan by design (BM25 needs the library), it selects no embedding, and it refuses
    exactly where :func:`read_topk` refuses: no dual write, no mirror; an unknown table, no
    rows. It never commits, and an empty mirror answers with an empty list rather than
    pretending the legacy store has a copy.
    """
    if vector_table != DEFAULT_VECTOR_TABLE:
        raise VectorReadRejectedError(
            f"语料腿只认 {DEFAULT_VECTOR_TABLE}，拿到 {vector_table!r}",
            reason=REASON_VECTOR_READ_TABLE_UNRECOGNISED)
    mirror = vector_mirror(connection_factory=connection_factory, url=url,
                           vector_table=vector_table)
    if mirror is None:
        raise VectorReadRejectedError(
            f"{DUAL_WRITE_ENV} 关着：chunk_vectors 里没有人在写的内容，切读态的语料腿无库可读",
            reason=REASON_VECTOR_READ_WITHOUT_DUAL_WRITE)
    try:
        rows = mirror.connection.execute(_READ_CORPUS_SQL).fetchall()
    finally:
        mirror.close()
    return [dict(zip(_READ_COLUMNS, row)) for row in rows]


#: Corpus-leg counters, kept apart from the top-k ones on purpose. "How many searches did
#: the mirror answer" and "where did this process get its lexical corpus" are two questions
#: that get answered by two different incidents, and one number covering both cannot tell a
#: degraded answer apart from a rebuilt index.
_CORPUS_DIAGNOSTICS: dict = {"reads": 0, "rows": 0, "source": "", "reason": ""}

CORPUS_SOURCE_PGVECTOR = "pgvector"
CORPUS_SOURCE_LEGACY = "legacy_chroma"
CORPUS_SOURCE_NOT_SWITCHED = "not_switched"


def _note_corpus(source: str, rows: int | None, reason: str = "") -> None:
    _CORPUS_DIAGNOSTICS["reads"] += 1
    _CORPUS_DIAGNOSTICS["source"] = source
    _CORPUS_DIAGNOSTICS["reason"] = str(reason)[:200]
    _CORPUS_DIAGNOSTICS["rows"] = (int(_CORPUS_DIAGNOSTICS["rows"]) + int(rows)
                                   if rows is not None else int(_CORPUS_DIAGNOSTICS["rows"]))


def vector_corpus_diagnostics() -> dict:
    """The last corpus build's source and row count. Issues no SQL of its own."""
    return dict(_CORPUS_DIAGNOSTICS)


def reset_vector_corpus_diagnostics() -> None:
    _CORPUS_DIAGNOSTICS.update({"reads": 0, "rows": 0, "source": "", "reason": ""})


def switched_corpus():
    """The corpus a switched deployment should use, or ``None`` to mean "ask the legacy one".

    Three answers, three different sentences said out loud in the diagnostics: nobody
    switched (``not_switched``), switched but the mirror will not open (a refusal reason --
    and the caller then falls back, which is the same availability-first trade R59b made for
    the top-k leg, and equally visible), and switched and answered (``pgvector``). Returning
    ``None`` never means "the library is empty": that would let a connection failure look
    like a corpus wipe, which is the exact shape R158 named for answers.
    """
    from app.rag import indexing as indexing_module

    if not indexing_module.pgvector_reads_enabled():
        _note_corpus(CORPUS_SOURCE_NOT_SWITCHED, None)
        return None
    try:
        rows = read_corpus()
    except Exception as exc:  # noqa: BLE001 - 一次拒答只该让语料建得慢一点，不该放宽
        reason = str(getattr(exc, "reason", "") or REASON_VECTOR_READ_FAILED)
        _note_corpus(CORPUS_SOURCE_LEGACY, None, f"{type(exc).__name__}: {exc}")
        note_read_bypass(reason, f"corpus: {type(exc).__name__}: {exc}")
        logger.warning(f"PGVector 语料腿拒答，本次语料仍取遗留向量库（{reason}）：{exc}")
        return None
    payload = {
        "documents": [row.get("content") or "" for row in rows],
        "metadatas": [{
            "filename": row.get("filename") or "unknown",
            "chunk_index": row.get("chunk_index"),
            # Kept as NULL, not filled with 1: R57's fail-closed is one rule for both legs,
            # and a corpus builder that invented a clearance would feed the very
            # classification value app/rag/filters.py cannot tell apart from a real one.
            "classification": row.get("classification"),
            "department": row.get("department") or "",
        } for row in rows],
    }
    _note_corpus(CORPUS_SOURCE_PGVECTOR, len(rows))
    return payload


def note_read_bypass(reason: str, detail: str = "") -> None:
    """Count a read leg that did not answer, under the stable code that says why."""
    _READ_DIAGNOSTICS["attempts"] += 1
    bypasses = _READ_DIAGNOSTICS["bypasses"]
    bypasses[reason] = int(bypasses.get(reason, 0)) + 1
    _READ_DIAGNOSTICS["last_bypass"] = {"reason": reason, "detail": str(detail)[:200]}


def note_read_answered(rows: int) -> None:
    _READ_DIAGNOSTICS["attempts"] += 1
    _READ_DIAGNOSTICS["answered"] += 1
    _READ_DIAGNOSTICS["rows"] += int(rows)
    _READ_DIAGNOSTICS["last_bypass"] = None


def vector_read_diagnostics() -> dict:
    """Read-side counters. Reading this dictionary opens no connection and issues no SQL."""
    return {
        "attempts": int(_READ_DIAGNOSTICS["attempts"]),
        "answered": int(_READ_DIAGNOSTICS["answered"]),
        "rows": int(_READ_DIAGNOSTICS["rows"]),
        "bypasses": dict(_READ_DIAGNOSTICS["bypasses"]),
        "last_bypass": (dict(_READ_DIAGNOSTICS["last_bypass"])
                        if _READ_DIAGNOSTICS["last_bypass"] else None),
    }


def reset_vector_read_diagnostics() -> None:
    _READ_DIAGNOSTICS["attempts"] = 0
    _READ_DIAGNOSTICS["answered"] = 0
    _READ_DIAGNOSTICS["rows"] = 0
    _READ_DIAGNOSTICS["bypasses"] = {}
    _READ_DIAGNOSTICS["last_bypass"] = None


# ============================================================================
# R60 判据③：停写之后，「这份文档的行住在哪一库」必须由 PG 自己回答
# ----------------------------------------------------------------------------
# 遗留腿不再接新行之后，chunk_vectors 里会出现 Chroma 根本没有的行。删除与按文档读回如果
# 还只问遗留腿，那些行就永远删不掉 ——「已删文档继续被检索」是这一格点名的形状，它只能在
# 问句那一层修，不在删除那一层。两条语句都留在存储层：retriever 不抄第二份 SQL，正如 R575
# 的恢复演练不复制 pg_store 的排名语句。
#
# 两条都不问 ANN、都不选 embedding 列：按文档名找行是目录动作，不是检索动作。
# VECTOR_DUAL_WRITE 关着时它们与 read_topk 同口径拒答 —— 那时 PG 里没有人在写的向量，
# 交回「没有行」就是说谎，宁可拒答。
# ============================================================================

#: content_sha256 这一列装的就是 metadata 里的 ``hash``（凭据：VectorMirror.build_rows 那一行
#: ``str(values.get("hash") or "") or None``）。列名与键名在这里刻意不同名，本单不改列名
#: （改名要动 migrations 与在册对账件，越出 R60 写域）；读出来摊回 ``hash`` 这个键，两条腿
#: 对同一个消费方（app/api/v1/chat.py 的 _document_publication）说同一个词。
_SELECT_DOCUMENT_ROWS_SQL = (
    "SELECT vector_id, content, chunk_index, classification, department, content_sha256 "
    "FROM chunk_vectors WHERE filename = %s ORDER BY chunk_index, vector_id"
)
_SELECT_DOCUMENT_NAMES_SQL = (
    "SELECT DISTINCT filename FROM chunk_vectors WHERE filename <> '' ORDER BY filename"
)
#: 与 _SELECT_DOCUMENT_ROWS_SQL 的列序逐位对齐；第六位的键名用遗留腿的写法，不用列名。
_DOCUMENT_ROW_COLUMNS = ("vector_id", "content", "chunk_index", "classification",
                         "department", "hash")


def _document_leg_connection(*, connection_factory=None, url=None,
                             vector_table=DEFAULT_VECTOR_TABLE):
    """Open the PostgreSQL leg for a document read, refusing with the codes reads use.

    Reuses :func:`vector_mirror` rather than opening a connection of its own: the mirror is
    the only place that knows how to reach this database, what to do when psycopg is missing,
    and which stable code to name when the switch says off.
    """
    if vector_table != DEFAULT_VECTOR_TABLE:
        raise VectorReadRejectedError(
            f"按文档读行只认 {DEFAULT_VECTOR_TABLE}，拿到 {vector_table!r}",
            reason=REASON_VECTOR_READ_TABLE_UNRECOGNISED)
    mirror = vector_mirror(connection_factory=connection_factory, url=url,
                           vector_table=vector_table)
    if mirror is None:
        raise VectorReadRejectedError(
            f"{DUAL_WRITE_ENV} 关着：chunk_vectors 里没有人在写的向量，按文档读行问不出真相",
            reason=REASON_VECTOR_READ_WITHOUT_DUAL_WRITE)
    return mirror


def document_vector_rows(*, filename: str, connection_factory=None, url=None,
                         vector_table: str = DEFAULT_VECTOR_TABLE) -> list[dict]:
    """The rows PostgreSQL holds for one document, in chunk order.

    Read-back, not a re-split and not a search: it answers "which vector ids does this
    filename own", which is exactly what a delete has to know before it may claim the
    document is gone. ``classification`` comes back as NULL when the row carries none --
    the same fail-closed rule R57 set for :func:`switched_corpus` and
    ``retriever._hit_dicts``: a storage layer that invents a clearance is the last forged
    row in this tree.
    """
    mirror = _document_leg_connection(connection_factory=connection_factory, url=url,
                                      vector_table=vector_table)
    try:
        rows = mirror.connection.execute(_SELECT_DOCUMENT_ROWS_SQL,
                                         (str(filename),)).fetchall()
    finally:
        mirror.close()
    return [
        {column: _row_value(row, column, position)
         for position, column in enumerate(_DOCUMENT_ROW_COLUMNS)}
        for row in rows
    ]


def indexed_document_names(*, connection_factory=None, url=None,
                           vector_table: str = DEFAULT_VECTOR_TABLE) -> list[str]:
    """Every document name PostgreSQL holds vector rows for, sorted.

    The empty string is dropped rather than counted: build_rows already refuses a row with
    no filename, so one appearing here would be another ticket's bug, and naming "" as a
    document would report a file nobody uploaded.
    """
    mirror = _document_leg_connection(connection_factory=connection_factory, url=url,
                                      vector_table=vector_table)
    try:
        rows = mirror.connection.execute(_SELECT_DOCUMENT_NAMES_SQL).fetchall()
    finally:
        mirror.close()
    names = [str(_row_value(row, "filename", 0) or "") for row in rows]
    return sorted({name for name in names if name})
