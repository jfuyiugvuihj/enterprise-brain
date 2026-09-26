"""Dataset and DatasetVersion metadata, stored in the PostgreSQL lineage tables.

``datasets`` and ``dataset_versions`` (``migrations/0002_execution_data_lineage.sql``) are the
only source of truth for a registered dataset. Every read in this module goes back to those
two tables: the process keeps no authoritative copy, so a registration that survives a write
survives a restart, and one that did not land is simply not there.

Versioning is a row, not an overwrite. ``register`` addresses a dataset by a stable
``dataset_id`` and appends one ``dataset_versions`` row per registration (``version_number``
monotonic, each row carrying its own ``content_sha256``), then moves the dataset row's
``current_version_id`` -- the same shape ``document_versions`` gives the document side.

The JSON ledger this module used to own is now read-only input: it is imported once into the
tables by :meth:`DatasetRegistry.import_legacy_metadata` and never written again. Where no
PostgreSQL backend is configured, the registry still needs a table to sit on, so it gets
:class:`InMemoryDatasetTableStore`, which is explicitly **not durable** -- the factory says so
in the log instead of letting a deployment believe its datasets are persisted.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass, field, fields as dataclass_fields
from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterable, Mapping

from app.agents.contracts import Principal, ResourceScope
from app.common.logger import logger
# The ranking of the classification words belongs to policy. A second copy of it here is how the
# storage layer and the authorization layer start answering one resource two ways, so 0015's
# reader borrows the one ranking there is. It is the only private name this module imports
# because app/common/policy.py has no public spelling of it yet.
from app.common.policy import _classification_level
from app.storage.persistence import PersistenceWriteError

DATASET_TABLE = "datasets"
DATASET_VERSION_TABLE = "dataset_versions"
STATUS_ACTIVE = "active"
STATUS_SUPERSEDED = "superseded"
STATUS_DELETED = "deleted"
#: The ledger this module wrote until the tables became the source of truth. Read-only now.
LEGACY_METADATA_FILENAME = ".dataset-metadata.json"

_INSERT = "insert"
_UPDATE = "update"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_text() -> str:
    return _utc_now().isoformat()


def _timestamp_text(value: Any) -> str:
    """A TIMESTAMPTZ read as a datetime and a written ISO string must land in one shape.

    PostgreSQL hands back ``datetime`` objects, the JSON import hands back strings, and the
    in-memory store hands back whatever was written. Records are compared field by field
    across a restart, so every one of those paths has to produce the same text.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _date_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _mapping_value(value: Any) -> dict:
    """JSONB as a python mapping: driver, memory store and JSON import all agree."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence_value(value: Any) -> list:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _number_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class DatasetRecord:
    """One ``datasets`` row: a stable identity, its owner, its scope, and its live version.

    The field set *is* the column set -- ``tests/test_r249_dataset_column_alignment.py`` fails
    if either side gains a member the other does not have. ``storage_path`` and ``version_id``
    stay as properties because callers outside this module still speak those names.
    """

    dataset_id: str
    owner_id: str
    filename: str
    department_ids: list[str]
    classification: str
    visibility: str
    storage_key: str
    content_sha256: str
    status: str
    current_version_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def storage_path(self) -> str:
        """``storage_key`` under the name the API and agent layers already use."""
        return self.storage_key

    @property
    def version_id(self) -> str | None:
        """The version this dataset row currently points at."""
        return self.current_version_id

    @property
    def resource_scope(self) -> ResourceScope:
        return ResourceScope(
            resource_type="dataset",
            resource_id=self.dataset_id,
            owner_id=self.owner_id,
            department_ids=list(self.department_ids),
            classification=self.classification,
            visibility=self.visibility,
            version_id=self.current_version_id,
            status=self.status,
        )


@dataclass
class DatasetVersionRecord:
    """One ``dataset_versions`` row: the content of one registration, addressed forever.

    The two scope columns arrived with migration 0015, and with them the row stopped being
    content-only: ``department_ids`` and ``classification`` hold the scope **this**
    registration was made under, which is the only scope anyone can state about the bytes
    that row keeps. Before 0015 the parent ``datasets`` row was the only scope on the table,
    so lowering it moved the whole chain with it -- the hole R256 exists to close. A version
    is still never a *looser* resource than its dataset row: the reading takes the stricter
    of the two. See :meth:`DatasetRegistry.scope_for_version`.

    The two fields are last, in the order the ALTERs append them to the table, because
    ``tests/test_r249_dataset_table_columns.py`` pins that the INSERT column order is the
    composed DDL order.
    """

    dataset_version_id: str
    dataset_id: str
    owner_id: str
    version_number: int
    storage_key: str
    content_sha256: str
    schema_snapshot: dict = field(default_factory=dict)
    period_start: str | None = None
    period_end: str | None = None
    status: str = STATUS_ACTIVE
    created_at: str = ""
    published_at: str | None = None
    superseded_at: str | None = None
    metadata: dict = field(default_factory=dict)
    department_ids: list = field(default_factory=list)
    classification: str = ""


DATASET_COLUMNS = tuple(item.name for item in dataclass_fields(DatasetRecord))
DATASET_VERSION_COLUMNS = tuple(item.name for item in dataclass_fields(DatasetVersionRecord))

_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    DATASET_TABLE: DATASET_COLUMNS,
    DATASET_VERSION_TABLE: DATASET_VERSION_COLUMNS,
}
_PRIMARY_KEY = {DATASET_TABLE: "dataset_id", DATASET_VERSION_TABLE: "dataset_version_id"}
_ORDER_COLUMN = {DATASET_TABLE: "created_at", DATASET_VERSION_TABLE: "version_number"}
#: Column families that need an explicit cast in the statement, keyed by the DDL types.
_JSON_COLUMNS = frozenset({"department_ids", "metadata", "schema_snapshot"})
_TIMESTAMP_COLUMNS = frozenset({"created_at", "updated_at", "published_at", "superseded_at"})
_DATE_COLUMNS = frozenset({"period_start", "period_end"})

#: A change is ``(table, row, kind)``, and one ``apply()`` call is one transaction.
Change = tuple[str, Mapping[str, Any], str]


class DatasetRowConflict(ValueError):
    """A write broke a uniqueness rule of the tables (primary key, live filename, version number)."""


class UnknownDatasetTable(ValueError):
    """A caller asked this store to touch a table it does not own.

    The store speaks for exactly two tables. A third name is either a typo or a new write
    point nobody reviewed, and both answers should be a failure, not an empty list.
    """


def _columns_for(table: str) -> tuple[str, ...]:
    try:
        return _TABLE_COLUMNS[table]
    except KeyError:
        raise UnknownDatasetTable(f"unsupported dataset table: {table}") from None


def _primary_key_for(table: str) -> str:
    return _PRIMARY_KEY[table]


def _validate_row(table: str, row: Mapping[str, Any], *, change: str = _INSERT) -> tuple[str, ...]:
    """Reject a row that is not a row of this table *before* it reaches the database."""
    columns = _columns_for(table)
    unknown = sorted(key for key in row if key not in columns)
    if unknown:
        raise ValueError(
            f"{table} row carries columns the table does not have: {', '.join(unknown)}"
        )
    primary_key = _primary_key_for(table)
    if not str(row.get(primary_key) or ""):
        raise ValueError(f"{table} row requires {primary_key}")
    if change == _UPDATE:
        changed = [key for key in row if key != primary_key]
        if not changed:
            raise ValueError(f"{table} update carries no columns to set")
    if change == _INSERT:
        missing = [column for column in columns if column not in row]
        required = [
            column
            for column in missing
            if column in {"owner_id", "filename", "dataset_id", "version_number", "storage_key"}
        ]
        if required:
            raise ValueError(f"{table} insert requires columns: {', '.join(required)}")
    return columns


def _placeholder(column: str) -> str:
    if column in _JSON_COLUMNS:
        return "%s::jsonb"
    if column in _TIMESTAMP_COLUMNS:
        return "%s::timestamptz"
    if column in _DATE_COLUMNS:
        return "%s::date"
    return "%s"


def _write_statement(table: str, row: Mapping[str, Any], *, change: str) -> tuple[str, tuple]:
    """One row becomes one statement plus the parameters in exactly the order it asks for.

    The order is the whole point: an ``UPDATE`` puts the primary key last (it is in the WHERE,
    not the SET), while an ``INSERT`` lists it wherever the column order puts it. Building the
    SQL and the parameters here, from the same list, is what keeps those two from drifting
    apart into a statement that writes the wrong column.
    """
    columns = [column for column in _columns_for(table) if column in row]
    if change == _INSERT:
        holders = ", ".join(_placeholder(column) for column in columns)
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({holders})"
        return sql, tuple(_param(column, row.get(column)) for column in columns)
    primary_key = _primary_key_for(table)
    set_columns = [column for column in columns if column != primary_key]
    assignments = ", ".join(f"{column} = {_placeholder(column)}" for column in set_columns)
    sql = f"UPDATE {table} SET {assignments} WHERE {primary_key} = {_placeholder(primary_key)}"
    params = tuple(_param(column, row.get(column)) for column in set_columns)
    return sql, params + (_param(primary_key, row.get(primary_key)),)


def _param(column: str, value: Any) -> Any:
    if column in _JSON_COLUMNS:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, default=str)
    return value


def _decode_row(columns: tuple[str, ...], row: Any) -> dict[str, Any]:
    values = dict(row) if isinstance(row, Mapping) else dict(zip(columns, row))
    decoded = {column: values.get(column) for column in columns}
    for column in _JSON_COLUMNS:
        if column in decoded:
            decoded[column] = (
                _mapping_value(decoded[column])
                if column != "department_ids"
                else _sequence_value(decoded[column])
            )
    return decoded


class DatasetTableStore:
    """The two lineage tables, addressed by row.

    The registry never speaks SQL and never keeps a shadow copy: it selects rows and applies
    changes, and this class decides where those rows live. ``select`` returns column-ordered
    dicts so both backends answer with the same shape, and ``apply`` is the only write
    entry -- one call, one transaction, so a registration cannot land half of itself.
    """

    def select(
        self,
        table: str,
        *,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def apply(self, changes: Iterable[Change]) -> None:
        raise NotImplementedError


def _sort_key(value: Any) -> tuple[int, Any]:
    """Order mixed readings (datetime, ISO text, int, None) without comparing across types.

    A TIMESTAMPTZ column can come back as a datetime or as the ISO text that was written into
    it, and ``period_start`` is nullable. Sorting on ``(bucket, value)`` keeps the two kinds
    apart instead of raising ``TypeError`` halfway through a listing.
    """
    if value is None:
        return (0, "")
    if isinstance(value, (int, float)):
        return (1, float(value))
    if isinstance(value, datetime):
        return (2, value.isoformat())
    return (3, str(value))


class InMemoryDatasetTableStore(DatasetTableStore):
    """A non-durable stand-in for the two tables: the same columns, the same rules, no disk.

    This is what the registry sits on when ``PERSISTENCE_BACKEND`` is not ``postgres``. It
    enforces the same three uniqueness rules the DDL does -- the primary key of each table,
    ``datasets (filename) WHERE status = 'active'``, and ``dataset_versions (dataset_id,
    version_number)`` -- so code that passes here is not quietly relying on a database that
    is not in the room. It is *not* a source of truth: everything in it dies with the process.
    """

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, dict[str, Any]]] = {table: {} for table in _TABLE_COLUMNS}
        self._lock = RLock()

    def select(
        self,
        table: str,
        *,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        columns = _columns_for(table)
        order_column = order_by or _ORDER_COLUMN[table]
        if order_column not in columns:
            raise ValueError(f"{table} has no column {order_column} to order by")
        filters = dict(where or {})
        unknown = sorted(key for key in filters if key not in columns)
        if unknown:
            raise ValueError(f"{table} cannot filter on columns it does not have: {', '.join(unknown)}")
        with self._lock:
            rows = [
                dict(row)
                for row in self._rows[table].values()
                if all(_sort_key(row.get(key)) == _sort_key(value) for key, value in filters.items())
            ]
        return sorted(rows, key=lambda row: _sort_key(row.get(order_column)), reverse=descending)

    def apply(self, changes: Iterable[Change]) -> None:
        staged = [(table, dict(row), change) for table, row, change in changes]
        if not staged:
            return
        with self._lock:
            for table, row, change in staged:
                _validate_row(table, row, change=change)
            for table, row, change in staged:
                self._guard_uniqueness(table, row, change)
            for table, row, change in staged:
                primary_key = _primary_key_for(table)
                identity = str(row[primary_key])
                if change == _INSERT:
                    self._rows[table][identity] = row
                else:
                    current = self._rows[table].get(identity)
                    if current is None:
                        raise DatasetRowConflict(f"{table} row {identity} does not exist to update")
                    current.update(row)

    def _guard_uniqueness(self, table: str, row: Mapping[str, Any], change: str) -> None:
        primary_key = _primary_key_for(table)
        identity = str(row[primary_key])
        if change == _INSERT and identity in self._rows[table]:
            raise DatasetRowConflict(f"{table} primary key {identity} already exists")
        if table == DATASET_TABLE:
            filename = str(row.get("filename") or "")
            status = str(row.get("status") or "")
            if status == STATUS_ACTIVE and filename:
                for other in self._rows[table].values():
                    if (
                        str(other.get("filename")) == filename
                        and str(other.get("status")) == STATUS_ACTIVE
                        and str(other[primary_key]) != identity
                    ):
                        raise DatasetRowConflict(
                            f"datasets_active_filename_idx: an active dataset already uses {filename}"
                        )
        if table == DATASET_VERSION_TABLE:
            dataset_id = str(row.get("dataset_id") or "")
            number = _number_value(row.get("version_number"))
            for other in self._rows[table].values():
                if (
                    str(other.get("dataset_id")) == dataset_id
                    and _number_value(other.get("version_number")) == number
                    and str(other[primary_key]) != identity
                ):
                    raise DatasetRowConflict(
                        f"dataset_versions (dataset_id, version_number) already holds {dataset_id} v{number}"
                    )

    def clear(self) -> None:
        """Empty both tables. Test seam only: production never calls it."""
        with self._lock:
            for rows in self._rows.values():
                rows.clear()


#: ``pg_store._with_connect_timeout`` does the same thing for the vector leg; the storage leg
#: keeps its own copy rather than importing across into ``app/rag/**``.
DEFAULT_CONNECT_TIMEOUT_SECONDS = 2


def _with_connect_timeout(url: str, seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS) -> str:
    """Pin a connect timeout into the conninfo, leaving an operator's own number alone."""
    if "connect_timeout=" in url:
        return url
    return url + ("&" if "?" in url else "?") + f"connect_timeout={int(seconds)}"


class PostgresDatasetTableStore(DatasetTableStore):
    """The two lineage tables in PostgreSQL -- the production source of truth.

    Deterministic, single-statement SQL with explicit casts (``::jsonb`` / ``::timestamptz`` /
    ``::date``), one connection per call, one commit per ``apply``. Write failures surface as
    :class:`~app.storage.persistence.PersistenceWriteError` instead of silently falling back
    to another backend, which is the same rule ``app/storage/persistence.py`` already plays.

    ``connection_factory`` is the test seam and the shape every other PG reader in this repo
    uses (``app/rag/pg_store.py``, ``app/rag/indexing.py``); without it the connection comes
    from ``app.db.connection.open_connection``, the sanctioned place psycopg gets imported.
    Nothing here connects at construction time.
    """

    def __init__(
        self,
        *,
        connection_factory: Callable[[], Any] | None = None,
        database_url: str | None = None,
    ) -> None:
        self.connection_factory = connection_factory
        self.database_url = (database_url or "").strip()

    def resolve_database_url(self) -> str:
        return (self.database_url or os.getenv("DATABASE_URL", "")).strip()

    def _connect(self) -> Any:
        if self.connection_factory is not None:
            return self.connection_factory()
        from app.db.connection import open_connection, parse_database_settings

        url = self.resolve_database_url()
        if not url:
            raise ValueError("DATABASE_URL is required for PostgreSQL dataset persistence")
        return open_connection(parse_database_settings(_with_connect_timeout(url)))

    def select(
        self,
        table: str,
        *,
        where: Mapping[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        columns = _columns_for(table)
        order_column = order_by or _ORDER_COLUMN[table]
        if order_column not in columns:
            raise ValueError(f"{table} has no column {order_column} to order by")
        filters = dict(where or {})
        unknown = sorted(key for key in filters if key not in columns)
        if unknown:
            raise ValueError(f"{table} cannot filter on columns it does not have: {', '.join(unknown)}")
        sql = f"SELECT {', '.join(columns)} FROM {table}"
        params: list[Any] = []
        if filters:
            conditions = []
            for key, value in filters.items():
                params.append(_param(key, value))
                conditions.append(f"{key} = {_placeholder(key)}")
            sql = f"{sql} WHERE {' AND '.join(conditions)}"
        sql = f"{sql} ORDER BY {order_column} DESC" if descending else f"{sql} ORDER BY {order_column}"
        connection = None
        try:
            connection = self._connect()
            rows = connection.execute(sql, tuple(params)).fetchall()
            return [_decode_row(columns, row) for row in rows]
        except Exception as exc:
            raise PersistenceWriteError(f"{table} read failed: {exc}") from exc
        finally:
            self._close(connection)

    def apply(self, changes: Iterable[Change]) -> None:
        staged = [(table, dict(row), change) for table, row, change in changes]
        if not staged:
            return
        for table, row, change in staged:
            _validate_row(table, row, change=change)
        connection = None
        try:
            connection = self._connect()
            for table, row, change in staged:
                sql, params = _write_statement(table, row, change=change)
                connection.execute(sql, params)
            if hasattr(connection, "commit"):
                connection.commit()
        except Exception as exc:
            if connection is not None and hasattr(connection, "rollback"):
                try:
                    connection.rollback()
                except Exception:  # pragma: no cover - the original failure is the one to report
                    pass
            raise PersistenceWriteError(f"{DATASET_TABLE}/{DATASET_VERSION_TABLE} write failed: {exc}") from exc
        finally:
            self._close(connection)

    @staticmethod
    def _close(connection: Any) -> None:
        if connection is not None and hasattr(connection, "close"):
            connection.close()


_TRANSITION_WARNING_LOGGED = False


def build_dataset_table_store(
    *,
    backend: str | None = None,
    database_url: str | None = None,
    connection_factory: Callable[[], Any] | None = None,
) -> DatasetTableStore:
    """Pick the table backend from ``PERSISTENCE_BACKEND``, exactly like the persistence adapter.

    ``postgres`` gives the production answer: the two lineage tables. ``json``/``local`` -- the
    shipped default of the non-Docker path -- cannot own a table, so it gets the in-memory
    store and a warning that says the registration will not survive the process. One switch
    therefore moves datasets together with the rest of the metadata; nothing here falls back
    after a configured PostgreSQL fails, because a silent fallback would be a lost dataset.
    """
    global _TRANSITION_WARNING_LOGGED
    selected = (backend or os.getenv("PERSISTENCE_BACKEND", "json")).strip().lower()
    if selected in {"postgres", "postgresql"}:
        return PostgresDatasetTableStore(
            connection_factory=connection_factory,
            database_url=database_url,
        )
    if selected not in {"json", "local"}:
        raise ValueError(f"unsupported dataset persistence backend: {selected}")
    if not _TRANSITION_WARNING_LOGGED:
        _TRANSITION_WARNING_LOGGED = True
        logger.warning(
            "[Datasets] PERSISTENCE_BACKEND=%s：数据集登记只活在内存过渡表里，进程重启即失；"
            "生产请配 PERSISTENCE_BACKEND=postgres 落 datasets/dataset_versions 两张表",
            selected,
        )
    return InMemoryDatasetTableStore()


def _dataset_from_row(row: Mapping[str, Any]) -> DatasetRecord:
    return DatasetRecord(
        dataset_id=str(row.get("dataset_id") or ""),
        owner_id=str(row.get("owner_id") or ""),
        filename=str(row.get("filename") or ""),
        department_ids=_sequence_value(row.get("department_ids")),
        classification=str(row.get("classification") or ""),
        visibility=str(row.get("visibility") or ""),
        storage_key=str(row.get("storage_key") or ""),
        content_sha256=str(row.get("content_sha256") or ""),
        status=str(row.get("status") or ""),
        current_version_id=(
            str(row["current_version_id"]) if row.get("current_version_id") else None
        ),
        created_at=_timestamp_text(row.get("created_at")),
        updated_at=_timestamp_text(row.get("updated_at")),
        metadata=_mapping_value(row.get("metadata")),
    )


def _strictness(word: str) -> tuple[int, int]:
    """Order one classification word so the *stricter* answer sorts higher.

    A word ``app/common/policy.py`` cannot rank is not "lowest": it is refused outright,
    which is the strictest thing the table can say, so it sorts above every rankable word.
    Ranking it below would be exactly the widening 0015 exists to close.
    """
    level = _classification_level(word)
    if level is None:
        return (1, 0)
    return (0, level)


def _no_wider_scope(
    version: DatasetVersionRecord, dataset: DatasetRecord
) -> ResourceScope | None:
    """The strictest scope both rows support, or ``None`` when the version records no scope.

    One place, so the "never looser than the dataset row" rule cannot be re-decided
    differently by a second caller. ``_classification_level`` is imported from
    ``app/common/policy.py`` rather than restated here: the ranking of the words is
    policy's, and a second copy is how two answers start disagreeing about one resource.

    Three shapes are worth naming, because all three are denials rather than guesses:
    a version that recorded no classification answers ``None`` (policy reads
    ``resource_scope_missing``); a classification either row spells with a word policy
    cannot rank outranks every rankable word, so it travels back as written and policy
    refuses it by name (``resource_scope_invalid``) instead of being quietly replaced by
    the other row's word; and departments are intersected, which can answer the empty
    set -- also a ``resource_scope_missing``.
    """
    own = str(version.classification or "").strip()
    if not own:
        return None
    parent = str(dataset.classification or "").strip()
    strictest = own
    if parent and _strictness(parent) > _strictness(own):
        strictest = parent
    return dataset.resource_scope.model_copy(
        update={
            "version_id": version.dataset_version_id,
            "classification": strictest,
            "department_ids": sorted(
                {str(value) for value in version.department_ids if str(value)}
                & {str(value) for value in dataset.department_ids if str(value)}
            ),
        }
    )


def _version_from_row(row: Mapping[str, Any]) -> DatasetVersionRecord:
    return DatasetVersionRecord(
        dataset_version_id=str(row.get("dataset_version_id") or ""),
        dataset_id=str(row.get("dataset_id") or ""),
        owner_id=str(row.get("owner_id") or ""),
        version_number=_number_value(row.get("version_number")),
        storage_key=str(row.get("storage_key") or ""),
        content_sha256=str(row.get("content_sha256") or ""),
        schema_snapshot=_mapping_value(row.get("schema_snapshot")),
        period_start=_date_text(row.get("period_start")),
        period_end=_date_text(row.get("period_end")),
        status=str(row.get("status") or ""),
        created_at=_timestamp_text(row.get("created_at")),
        published_at=_timestamp_text(row.get("published_at")) or None,
        superseded_at=_timestamp_text(row.get("superseded_at")) or None,
        metadata=_mapping_value(row.get("metadata")),
        department_ids=_sequence_value(row.get("department_ids")),
        classification=str(row.get("classification") or ""),
    )


class DatasetRegistry:
    """Dataset metadata whose only source of truth is the ``datasets`` / ``dataset_versions`` tables.

    Every read goes back to the store, so a restart recovers the same rows the process wrote
    and nothing is remembered in a cache that could disagree with them. A second registration
    of the same logical file is a new ``dataset_versions`` row plus a moved
    ``current_version_id`` on the same ``datasets`` row -- stable identity, append-only history.

    ``root`` still bounds which bytes may be registered (a dataset row must point inside the
    storage root), and ``metadata_path`` now names the *read-only* legacy ledger.
    """

    def __init__(
        self,
        root: str | Path,
        metadata_path: str | Path | None = None,
        *,
        store: DatasetTableStore | None = None,
    ):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.metadata_path = Path(metadata_path or self.root / LEGACY_METADATA_FILENAME).resolve()
        self.store = store if store is not None else build_dataset_table_store()
        self._lock = RLock()
        self._legacy_import_done = False

    # ------------------------------------------------------------------ storage bounds

    def _contained_path(self, value: str | Path, *, must_exist: bool) -> Path:
        path = Path(value).resolve(strict=must_exist)
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("dataset storage path escapes registry root") from exc
        return path

    # --------------------------------------------------------------- legacy JSON ledger

    def _legacy_rows(self) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """Read the transitional JSON and return the ``(datasets, dataset_versions)`` rows for it.

        Read-only by construction: there is no write path to this file any more anywhere in
        this module (``tests/test_r249_dataset_column_alignment.py`` counts the sites and
        pins the number at zero). A row whose path escapes the storage root is skipped rather
        than dropping the whole ledger, which is what the old loader did.
        """
        if not self.metadata_path.is_file():
            return []
        try:
            payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning(f"[Datasets] 遗留台账 {self.metadata_path} 读取失败，跳过导入：{exc}")
            return []
        rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for raw in payload.get("datasets", []) if isinstance(payload, Mapping) else []:
            if not isinstance(raw, Mapping) or not raw.get("dataset_id"):
                continue
            try:
                path = self._contained_path(raw.get("storage_path") or "", must_exist=False)
            except ValueError:
                logger.warning(
                    f"[Datasets] 遗留台账条目 {raw.get('dataset_id')} 的路径越出存储根，跳过"
                )
                continue
            dataset_id = str(raw["dataset_id"])
            legacy_version_id = str(raw.get("version_id") or "") or f"{dataset_id}:v1"
            version_number = _number_value(legacy_version_id.rsplit(":v", 1)[-1]) or 1
            status = str(raw.get("status") or STATUS_ACTIVE) or STATUS_ACTIVE
            created_at = _timestamp_text(raw.get("created_at"))
            source = {"legacy_import": str(self.metadata_path)}
            rows.append(
                (
                    {
                        "dataset_id": dataset_id,
                        "owner_id": str(raw.get("owner_id") or ""),
                        "filename": str(raw.get("filename") or path.name),
                        "department_ids": _sequence_value(raw.get("department_ids")),
                        "classification": str(raw.get("classification") or ""),
                        "visibility": str(raw.get("visibility") or ""),
                        "storage_key": str(path),
                        "content_sha256": str(raw.get("content_sha256") or ""),
                        "status": status,
                        "current_version_id": legacy_version_id,
                        "created_at": created_at,
                        "updated_at": created_at,
                        "metadata": source,
                    },
                    {
                        "dataset_version_id": legacy_version_id,
                        "dataset_id": dataset_id,
                        "owner_id": str(raw.get("owner_id") or ""),
                        "version_number": version_number,
                        "storage_key": str(path),
                        "content_sha256": str(raw.get("content_sha256") or ""),
                        "status": STATUS_ACTIVE if status == STATUS_ACTIVE else STATUS_DELETED,
                        "created_at": created_at,
                        "published_at": created_at or None,
                        "metadata": source,
                        # Not a backfill: the ledger holds one row per dataset, and that row
                        # *is* the version named by ``version_id``, so the classification and
                        # departments written here are the ones it recorded for it.
                        "department_ids": _sequence_value(raw.get("department_ids")),
                        "classification": str(raw.get("classification") or ""),
                    },
                )
            )
        return rows

    def import_legacy_metadata(self) -> dict[str, int]:
        """Import the transitional JSON ledger into the tables, once and read-only.

        Rows already in the tables are skipped by primary key, so this is a no-op on the
        second run and safe to leave wired into startup. Returns the row counts it wrote.
        """
        with self._lock:
            counts = self._import_locked()
            self._legacy_import_done = True
        return counts

    def _import_locked(self) -> dict[str, int]:
        imported_datasets = 0
        imported_versions = 0
        changes: list[Change] = []
        for dataset_row, version_row in self._legacy_rows():
            present = self.store.select(
                DATASET_TABLE, where={"dataset_id": dataset_row["dataset_id"]}
            )
            if not present:
                changes.append((DATASET_TABLE, dataset_row, _INSERT))
                imported_datasets += 1
            present_version = self.store.select(
                DATASET_VERSION_TABLE,
                where={"dataset_version_id": version_row["dataset_version_id"]},
            )
            if not present_version:
                changes.append((DATASET_VERSION_TABLE, version_row, _INSERT))
                imported_versions += 1
        if changes:
            self.store.apply(changes)
        return {"datasets": imported_datasets, "dataset_versions": imported_versions}

    def _ensure_legacy_import(self) -> None:
        """Import once, lazily, at first use -- never at import time.

        Startup is where a connection would be opened by accident (R229 got bitten by exactly
        that on the auth leg), so the ledger is read the first time a caller actually touches
        the registry. If the store is unreachable the warning says the import is incomplete
        and the next call tries again; a dataset that never made it into the tables must not
        be reported as absent without a word about why.
        """
        if self._legacy_import_done:
            return
        if not self.metadata_path.is_file():
            self._legacy_import_done = True
            return
        try:
            counts = self._import_locked()
        except Exception as exc:
            logger.warning(
                f"[Datasets] 遗留台账导入未完成，下次访问重试：{type(exc).__name__}: {exc}"
            )
            return
        self._legacy_import_done = True
        if counts["datasets"] or counts["dataset_versions"]:
            logger.warning(
                f"[Datasets] 从只读遗留台账 {self.metadata_path} 导入 "
                f"{counts['datasets']} 条 datasets / {counts['dataset_versions']} 条 dataset_versions"
            )

    # ------------------------------------------------------------------------ register

    def register(
        self,
        storage_path: str | Path,
        *,
        principal: Principal,
        filename: str | None = None,
        classification: str = "internal",
        visibility: str = "private",
        schema_snapshot: Mapping[str, Any] | None = None,
        period_start: str | date | None = None,
        period_end: str | date | None = None,
    ) -> DatasetRecord:
        """Register the file as a new *version* of the dataset that owns its logical name.

        The first call creates the ``datasets`` row and ``version_number = 1``; every later
        call on the same active filename keeps the ``dataset_id``, appends a version row with
        its own ``content_sha256``, marks the version it replaces ``superseded``, and repoints
        ``current_version_id``. Nothing is overwritten -- the history an audit needs is the
        version rows, and the dataset row is only ever the "what is live now" pointer plus the
        scope the whole dataset is authorized by.

        The two tables are written in one ``apply`` call, so a registration either lands whole
        or does not exist; and the record handed back is read *back out of the store*, so a
        write the database refused to keep is never reported as a success.
        """
        if principal.status != "active" or not principal.user_id:
            raise PermissionError("active principal is required to register a dataset")
        path = self._contained_path(storage_path, must_exist=True)
        logical_filename = Path(filename or path.name).name
        if not logical_filename or logical_filename in {".", ".."}:
            raise ValueError("dataset filename is required")
        departments = sorted(
            {
                value
                for value in [principal.department, *principal.department_ids]
                if value
            }
        )
        if not departments:
            raise ValueError("dataset owner must have a department scope")
        content_sha256 = _hash_file(path)

        with self._lock:
            self._ensure_legacy_import()
            existing = self._active_row_by_filename(logical_filename)
            now = _utc_now_text()
            if existing is None:
                dataset_id = uuid.uuid4().hex
                created_at = now
                version_number = 1
                dataset_metadata: dict[str, Any] = {}
                previous_version_id: str | None = None
            else:
                previous = _dataset_from_row(existing)
                dataset_id = previous.dataset_id
                created_at = previous.created_at or now
                dataset_metadata = dict(previous.metadata)
                previous_version_id = previous.current_version_id
                version_number = self._next_version_number(dataset_id)
            version_id = f"{dataset_id}:v{version_number}"
            owner_id = str(principal.user_id)
            version = DatasetVersionRecord(
                dataset_version_id=version_id,
                dataset_id=dataset_id,
                owner_id=owner_id,
                version_number=version_number,
                storage_key=str(path),
                content_sha256=content_sha256,
                schema_snapshot=_mapping_value(schema_snapshot),
                period_start=_date_text(period_start),
                period_end=_date_text(period_end),
                status=STATUS_ACTIVE,
                created_at=now,
                published_at=now,
                superseded_at=None,
                metadata={"registered_by": owner_id, "previous_version_id": previous_version_id},
                # The scope this version is *registered under*, copied onto the version row
                # rather than left to the dataset row to remember: the dataset row is what a
                # later registration rewrites, and a version that only borrows it changes
                # classification after the fact.
                department_ids=list(departments),
                classification=classification,
            )
            record = DatasetRecord(
                dataset_id=dataset_id,
                owner_id=owner_id,
                filename=logical_filename,
                department_ids=departments,
                classification=classification,
                visibility=visibility,
                storage_key=str(path),
                content_sha256=content_sha256,
                status=STATUS_ACTIVE,
                current_version_id=version_id,
                created_at=created_at,
                updated_at=now,
                metadata=dataset_metadata,
            )
            changes: list[Change] = [
                # The dataset row goes first: dataset_versions.dataset_id references it.
                (DATASET_TABLE, asdict(record), _INSERT if existing is None else _UPDATE)
            ]
            if previous_version_id:
                changes.append(
                    (
                        DATASET_VERSION_TABLE,
                        {
                            "dataset_version_id": previous_version_id,
                            "status": STATUS_SUPERSEDED,
                            "superseded_at": now,
                        },
                        _UPDATE,
                    )
                )
            changes.append((DATASET_VERSION_TABLE, asdict(version), _INSERT))
            self.store.apply(changes)

        published = self.get(dataset_id)
        if published is None:
            raise PersistenceWriteError(
                f"datasets row {dataset_id} is not readable after register wrote it"
            )
        return published

    def _next_version_number(self, dataset_id: str) -> int:
        """One past the highest version row this dataset already holds.

        Read from the rows rather than a counter, so a process that restarts mid-chain cannot
        hand out a ``version_number`` the ``UNIQUE (dataset_id, version_number)`` rule already
        refuses.
        """
        rows = self.store.select(
            DATASET_VERSION_TABLE, where={"dataset_id": dataset_id}, descending=True
        )
        if not rows:
            return 1
        return _number_value(rows[0].get("version_number")) + 1

    # ----------------------------------------------------------------------------- reads

    def _active_row_by_filename(self, filename: str) -> dict | None:
        """The live ``datasets`` row for a logical filename, exactly as the table holds it.

        Unlike :meth:`get_active_by_filename` this does not ask whether the bytes are still on
        disk: registration is about the row, and re-registering a name whose file was removed
        must append a version to the dataset that owns the name instead of opening a second
        active row that ``datasets_active_filename_idx`` would refuse.
        """
        rows = self.store.select(
            DATASET_TABLE,
            where={"filename": filename, "status": STATUS_ACTIVE},
            order_by="created_at",
            descending=True,
        )
        return rows[0] if rows else None

    def get(self, dataset_id: str) -> DatasetRecord | None:
        """The dataset row, exactly as the table holds it."""
        with self._lock:
            self._ensure_legacy_import()
            rows = self.store.select(DATASET_TABLE, where={"dataset_id": dataset_id})
        return _dataset_from_row(rows[0]) if rows else None

    def list(self, *, include_retired: bool = False) -> list[DatasetRecord]:
        """Every dataset row, newest first; retired rows only when asked for."""
        with self._lock:
            self._ensure_legacy_import()
            rows = self.store.select(DATASET_TABLE, order_by="created_at", descending=True)
        records = [_dataset_from_row(row) for row in rows]
        if not include_retired:
            records = [record for record in records if record.status == STATUS_ACTIVE]
        return records

    def get_active_by_filename(self, filename: str) -> DatasetRecord | None:
        candidates = [
            record
            for record in self.list()
            if record.filename == filename and record.status == STATUS_ACTIVE
        ]
        if not candidates:
            return None
        record = max(candidates, key=lambda item: item.created_at)
        path = self._contained_path(record.storage_path, must_exist=False)
        return record if path.is_file() else None

    def active_records(self) -> list[DatasetRecord]:
        """Active datasets whose bytes are still where the row says they are, newest first."""
        records = []
        for record in self.list():
            if record.status != STATUS_ACTIVE:
                continue
            path = self._contained_path(record.storage_path, must_exist=False)
            if path.is_file():
                records.append(record)
        return sorted(records, key=lambda item: item.created_at, reverse=True)

    def versions(self, dataset_id: str, *, include_superseded: bool = True) -> list[DatasetVersionRecord]:
        """The version chain of one dataset, oldest first."""
        with self._lock:
            self._ensure_legacy_import()
            rows = self.store.select(
                DATASET_TABLE, where={"dataset_id": dataset_id}, order_by="created_at"
            )
            if not rows:
                return []
            version_rows = self.store.select(
                DATASET_VERSION_TABLE, where={"dataset_id": dataset_id}, order_by="version_number"
            )
        versions = [_version_from_row(row) for row in version_rows]
        if not include_superseded:
            versions = [
                version for version in versions if version.status not in {STATUS_SUPERSEDED, STATUS_DELETED}
            ]
        return sorted(versions, key=lambda item: item.version_number)

    def get_version(
        self,
        dataset_id: str,
        version_number: int | None = None,
        *,
        version_id: str | None = None,
    ) -> DatasetVersionRecord | None:
        """Address one version by number or by its ``dataset_id:vN`` id; default is the live one."""
        with self._lock:
            self._ensure_legacy_import()
            if version_id is None and version_number is None:
                dataset_rows = self.store.select(
                    DATASET_TABLE, where={"dataset_id": dataset_id}
                )
                if not dataset_rows:
                    return None
                version_id = _dataset_from_row(dataset_rows[0]).current_version_id
                if version_id is None:
                    return None
            if version_id is not None:
                rows = self.store.select(
                    DATASET_VERSION_TABLE, where={"dataset_version_id": version_id}
                )
                return _version_from_row(rows[0]) if rows else None
            rows = self.store.select(
                DATASET_VERSION_TABLE,
                where={"dataset_id": dataset_id, "version_number": version_number},
            )
        return _version_from_row(rows[0]) if rows else None

    def dataset_for_version(self, version_id: str) -> DatasetRecord | None:
        """The dataset a version row belongs to."""
        with self._lock:
            self._ensure_legacy_import()
            rows = self.store.select(
                DATASET_VERSION_TABLE, where={"dataset_version_id": version_id}
            )
        if not rows:
            return None
        return self.get(str(_version_from_row(rows[0]).dataset_id))

    def version_row(self, version_id: str) -> DatasetVersionRecord | None:
        """One version row by its id, or ``None`` when the table has no such row."""
        with self._lock:
            self._ensure_legacy_import()
            rows = self.store.select(
                DATASET_VERSION_TABLE, where={"dataset_version_id": version_id}
            )
        return _version_from_row(rows[0]) if rows else None

    def scope_for_version(
        self, version: DatasetVersionRecord | str
    ) -> ResourceScope | None:
        """Authorize a version by the scope recorded **on its own row**, never wider than its dataset.

        Migration 0015 gave ``dataset_versions`` a ``classification`` and a ``department_ids``,
        so a version no longer has to borrow the only scope in the database -- the one a later
        registration rewrites. The answer is the meet of the two rows rather than either one
        alone: the stricter classification and the intersection of the department sets. That
        keeps the property R249 stated (a version is never its own looser resource) while
        closing what it could not close: lowering the dataset row no longer loosens the
        versions stored before the lowering.

        A version row with no recorded classification answers ``None``. Rows written before
        0015 are exactly that, and 0015 refuses to invent a scope for them, so the honest
        statement is "not recorded" and policy reads ``None`` as ``resource_scope_missing`` --
        a denial, the same shape an unknown version already took. An unknown version, a
        missing dataset row and an unrecorded scope therefore all fail closed together, and
        none of them falls through to the live version.
        """
        version_id = version if isinstance(version, str) else version.dataset_version_id
        record = self.version_row(version_id)
        if record is None:
            return None
        dataset = self.get(record.dataset_id)
        if dataset is None:
            return None
        return _no_wider_scope(record, dataset)

    # --------------------------------------------------------------------------- retire

    def soft_delete(self, dataset_id: str) -> bool:
        """Retire the dataset row and its live version row, keeping both addressable.

        The row is kept with status ``deleted`` rather than erased: the tables are what an
        operator reconstructs an audit trail from, and ``get_active_by_filename`` already
        ignores retired rows, so the filename becomes reusable without the history
        disappearing with it. Version rows are retired too -- a ``deleted`` dataset must not
        leave an ``active`` version that could be read back as live content.
        """
        with self._lock:
            self._ensure_legacy_import()
            rows = self.store.select(DATASET_TABLE, where={"dataset_id": dataset_id})
            if not rows:
                return False
            record = _dataset_from_row(rows[0])
            if record.status != STATUS_ACTIVE:
                return False
            now = _utc_now_text()
            changes: list[Change] = [
                (
                    DATASET_TABLE,
                    {"dataset_id": dataset_id, "status": STATUS_DELETED, "updated_at": now},
                    _UPDATE,
                )
            ]
            if record.current_version_id:
                live = self.store.select(
                    DATASET_VERSION_TABLE,
                    where={"dataset_version_id": record.current_version_id},
                )
                if live and str(live[0].get("status")) == STATUS_ACTIVE:
                    changes.append(
                        (
                            DATASET_VERSION_TABLE,
                            {
                                "dataset_version_id": record.current_version_id,
                                "status": STATUS_DELETED,
                            },
                            _UPDATE,
                        )
                    )
            self.store.apply(changes)
            return True


_DATA_ROOT = Path(os.getenv("DATA_DIR", "./data"))
dataset_registry = DatasetRegistry(_DATA_ROOT)
