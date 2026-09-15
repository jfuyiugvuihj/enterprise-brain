import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.common.logger import logger

_tz = timezone(timedelta(hours=8))
_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")
DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", "./documents")
_initialized = False
_db_available: bool | None = None
_PRODUCTION_ENVIRONMENTS = {"production", "prod"}

# The catalog has two persistence paths and both of them must carry ownership: the
# PostgreSQL document_versions table (mirrored by the documents table) and, for any
# deployment where PostgreSQL is offline, a JSON sidecar kept next to the stored
# files. The sidecar is addressed through the directory of the file it describes
# rather than through DOCUMENTS_DIR, so a caller that stores a version outside the
# documents root can never write into that root by accident.
LOCAL_CATALOG_FILENAME = ".document-versions.json"
PARSE_STATUSES = ("pending", "parsing", "ready", "failed")
OWNERSHIP_OWNED = "owned"
OWNERSHIP_LEGACY = "legacy"
_SELECT_COLUMNS = (
    "filename, version, classification, department, storage_path, created_at, "
    "owner_id, size_bytes, parse_status"
)


def next_document_version(rows: list[dict], filename: str) -> int:
    versions = [int(row.get("version", 0)) for row in rows if row.get("filename") == filename]
    return max(versions, default=0) + 1


def build_storage_name(filename: str, version: int) -> str:
    stem, ext = os.path.splitext(filename)
    return f"{stem}__v{version}{ext}"


def _public_storage_path(value) -> str:
    """Express a stored file for API responses without echoing a server path.

    Catalog rows are also consumed inside the process (preview, download and
    delete resolve the physical file), so the value must stay resolvable: an
    absolute path is rewritten relative to the working directory the service
    runs from, and only the bare file name is kept when no relative form can be
    expressed at all (for example across Windows drives). The absolute path
    remains in the catalog table and in the server log, never in a response.
    """
    if value is None or value == "":
        return ""
    raw = str(value)
    if not os.path.isabs(raw):
        return raw.replace(os.sep, "/")
    try:
        relative = os.path.relpath(raw, os.getcwd())
    except ValueError:
        logger.warning(f"[Docs] storage path leaves the working directory tree: {raw}")
        return os.path.basename(raw).replace(os.sep, "/")
    return relative.replace(os.sep, "/")


def _is_unowned(value) -> bool:
    """A row without a usable owner is legacy, never public."""
    return value is None or str(value).strip() == ""


def _resolve_owner_id(principal=None, owner_id=None) -> str | None:
    """Read an owner identity from a Principal, a user mapping or an explicit value.

    Callers that have no authenticated subject record an unowned row on purpose: the
    policy treats an unowned document as legacy and keeps it away from ordinary
    staff until somebody resolves its ownership.
    """
    if owner_id not in (None, ""):
        return str(owner_id).strip() or None
    if principal is None:
        return None
    if isinstance(principal, dict):
        value = principal.get("id") or principal.get("user_id") or principal.get("username")
    else:
        value = getattr(principal, "user_id", None)
    if value is None:
        return None
    return str(value).strip() or None


def _normalise_parse_status(value) -> str:
    status = str(value or "pending").strip().lower()
    if status in PARSE_STATUSES:
        return status
    logger.warning(f"[Docs] unknown parse status {value!r} recorded as pending")
    return "pending"


def _resolved_size(storage_path, size_bytes) -> int | None:
    """Prefer the recorded size and fall back to the file actually on disk."""
    if size_bytes is not None:
        try:
            return max(int(size_bytes), 0)
        except (TypeError, ValueError):
            pass
    if storage_path in (None, ""):
        return None
    try:
        return int(os.path.getsize(str(storage_path)))
    except (OSError, TypeError, ValueError):
        return None


def _sidecar_key(filename: str, version: int) -> str:
    return f"{filename}|v{int(version)}"


def _sidecar_path(storage_path) -> Path | None:
    raw = str(storage_path or "").strip()
    if not raw:
        return None
    return Path(raw).parent / LOCAL_CATALOG_FILENAME


def _read_sidecar(path: Path) -> dict:
    """Load locally recorded version metadata; an absent file is not an error."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning(f"[Docs] catalog sidecar is unreadable: {exc}")
        return {}
    records = payload.get("documents") if isinstance(payload, dict) else None
    if not isinstance(records, dict):
        return {}
    return {str(key): dict(value) for key, value in records.items() if isinstance(value, dict)}


def _write_sidecar(path: Path, records: dict) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    payload = json.dumps({"documents": records}, ensure_ascii=False, indent=2, sort_keys=True)
    temp.write_text(payload, encoding="utf-8")
    os.replace(temp, path)


_SIDECAR_FIELDS = (
    "filename",
    "version",
    "classification",
    "department",
    "owner_id",
    "size_bytes",
    "parse_status",
    "created_at",
)


def _record_local_version(metadata: dict) -> None:
    """Mirror one version row into the JSON sidecar that sits beside the file."""
    path = _sidecar_path(metadata.get("storage_path"))
    if path is None:
        return
    try:
        records = _read_sidecar(path)
        records[_sidecar_key(str(metadata["filename"]), int(metadata["version"]))] = {
            key: metadata.get(key) for key in _SIDECAR_FIELDS
        } | {"recorded_path": str(metadata.get("storage_path") or "")}
        _write_sidecar(path, records)
    except OSError as exc:
        logger.warning(f"[Docs] catalog sidecar write failed: {exc}")
    except Exception as exc:
        logger.warning(f"[Docs] catalog sidecar write skipped: {exc}")


def _drop_local_versions(filename: str, storage_paths=()) -> None:
    """Remove every local record of a logical document after a delete."""
    paths = {Path(DOCUMENTS_DIR) / LOCAL_CATALOG_FILENAME}
    for storage_path in storage_paths:
        sidecar = _sidecar_path(storage_path)
        if sidecar is not None:
            paths.add(sidecar)
    for path in sorted(paths):
        records = _read_sidecar(path)
        kept = {key: value for key, value in records.items() if value.get("filename") != filename}
        if len(kept) == len(records):
            # Nothing here belongs to the document: leave the file untouched.
            continue
        try:
            if kept:
                _write_sidecar(path, kept)
            else:
                path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(f"[Docs] catalog sidecar prune failed: {exc}")


def public_document_row(row: dict) -> dict:
    """Shape one stored row for an API response.

    R4 asks the catalog to carry the stored size, the parse state and the owner, and
    the ownership marker tells a client whether a row predates document ownership and
    is therefore only visible to the management level.
    """
    public = dict(row)
    if "storage_path" in public:
        public["storage_path"] = _public_storage_path(public["storage_path"])
    storage_path = row.get("storage_path")
    public["owner_id"] = None if _is_unowned(row.get("owner_id")) else str(row.get("owner_id"))
    public["size_bytes"] = _resolved_size(storage_path, row.get("size_bytes"))
    public["parse_status"] = _normalise_parse_status(row.get("parse_status"))
    public["ownership"] = OWNERSHIP_LEGACY if public["owner_id"] is None else OWNERSHIP_OWNED
    return public


def _public_rows(rows: list[dict]) -> list[dict]:
    """Return catalog rows with every server-side storage path de-identified."""
    return [public_document_row(row) for row in rows]


def _database_available() -> bool:
    """Reuse the application's database health state to avoid repeated slow retries."""
    auth_module = sys.modules.get("app.common.auth")
    if auth_module is not None:
        return bool(getattr(auth_module, "_db_ready", False))
    return _db_available is not False


def _conn():
    global _db_available
    import psycopg
    from psycopg.rows import dict_row

    try:
        conn = psycopg.connect(_PG_URL, row_factory=dict_row, connect_timeout=1)
    except Exception:
        _db_available = False
        raise
    _db_available = True
    return conn


def _is_production_environment() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


def _path_is_readable(value) -> bool:
    """Report whether a recorded storage path still points at a real file."""
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        return Path(raw).is_file()
    except OSError:
        return False


def _local_row(filename: str, version: int, storage_path, stored: dict) -> dict:
    """Build one offline catalog row, preferring what the sidecar recorded."""
    return {
        "filename": filename,
        "version": int(version),
        "classification": stored.get("classification", 1),
        "department": stored.get("department") or "",
        "owner_id": stored.get("owner_id"),
        "size_bytes": stored.get("size_bytes"),
        "parse_status": stored.get("parse_status"),
        "storage_path": _public_storage_path(storage_path),
        "created_at": stored.get("created_at")
        or _file_mtime(storage_path),
    }


def _file_mtime(storage_path) -> str:
    try:
        return datetime.fromtimestamp(os.path.getmtime(str(storage_path)), _tz).isoformat()
    except OSError:
        return datetime.now(_tz).isoformat()


def _local_version_rows(filename: str | None = None) -> list[dict]:
    rows = []
    pattern = re.compile(r"^(?P<stem>.+)__v(?P<version>\d+)(?P<ext>\.[^.]+)$")
    directory = Path(DOCUMENTS_DIR)
    if not directory.is_dir():
        return rows
    recorded = _read_sidecar(directory / LOCAL_CATALOG_FILENAME)

    for path in directory.iterdir():
        if not path.is_file() or path.name == LOCAL_CATALOG_FILENAME:
            continue
        match = pattern.match(path.name)
        if not match:
            continue
        original_name = f"{match.group('stem')}{match.group('ext')}"
        if filename and original_name != filename:
            continue
        version = int(match.group("version"))
        stored = recorded.get(_sidecar_key(original_name, version)) or {}
        rows.append(
            _local_row(
                filename=original_name,
                version=version,
                storage_path=path,
                stored=stored,
            )
        )

    # A stored version is addressed by resource id, so the legacy ``name__vN`` scan
    # never sees it. The sidecar rows are the only way an offline catalog can list
    # them, and dropping them would also drop their ownership.
    listed = {(row["filename"], row["version"]) for row in rows}
    for stored in recorded.values():
        name = str(stored.get("filename") or "")
        try:
            version = int(stored.get("version"))
        except (TypeError, ValueError):
            continue
        if not name or (name, version) in listed:
            continue
        if filename and name != filename:
            continue
        recorded_path = stored.get("recorded_path")
        if not _path_is_readable(recorded_path):
            continue
        path = Path(str(recorded_path))
        rows.append(_local_row(filename=name, version=version, storage_path=path, stored=stored))
        listed.add((name, version))
    return rows


def _ensure():
    global _initialized
    if _initialized:
        return
    with _conn() as conn:
        if _is_production_environment():
            row = conn.execute("SELECT to_regclass('public.document_versions') AS table_name").fetchone()
            if not row or row["table_name"] is None:
                raise RuntimeError("document_versions table is required in production; run migrations first")
            _initialized = True
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS document_versions (
                id SERIAL PRIMARY KEY,
                filename TEXT NOT NULL,
                version INT NOT NULL,
                classification INT NOT NULL DEFAULT 1,
                department TEXT,
                storage_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                owner_id TEXT,
                size_bytes BIGINT,
                parse_status TEXT NOT NULL DEFAULT 'pending',
                UNIQUE(filename, version)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_versions_name ON document_versions(filename)")
        conn.commit()
    _initialized = True


def peek_next_document_version(filename: str) -> int:
    if not _database_available():
        return next_document_version(_local_version_rows(filename), filename)
    try:
        _ensure()
        with _conn() as conn:
            rows = conn.execute(
                "SELECT filename, version FROM document_versions WHERE filename = %s ORDER BY version",
                (filename,),
            ).fetchall()
        return next_document_version([dict(row) for row in rows], filename)
    except Exception as exc:
        logger.warning(f"[Docs] version lookup fallback: {exc}")
        return next_document_version(_local_version_rows(filename), filename)


def _version_metadata(
    filename: str,
    classification: int,
    department: str,
    storage_path: str,
    version: int | None,
    principal,
    owner_id: str | None,
    size_bytes: int | None,
    parse_status: str,
) -> dict:
    """Build the one shape both persistence paths share."""
    version = version or peek_next_document_version(filename)
    owner = _resolve_owner_id(principal, owner_id)
    return {
        "filename": filename,
        "version": version,
        "classification": int(classification),
        "department": department or "",
        "storage_path": storage_path,
        "created_at": datetime.now(_tz).isoformat(),
        "owner_id": owner,
        "size_bytes": _resolved_size(storage_path, size_bytes),
        "parse_status": _normalise_parse_status(parse_status),
    }


def record_local_document_version(
    filename: str,
    classification: int,
    department: str,
    storage_path: str,
    version: int | None = None,
    *,
    principal=None,
    owner_id: str | None = None,
    size_bytes: int | None = None,
    parse_status: str = "pending",
) -> dict:
    """Record one version through the local JSON path only.

    This is the write an offline deployment still gets: a stored file with no owner in
    either path would become a legacy row that ordinary staff can never list, which is
    exactly how a document ends up undeletable.
    """
    metadata = _version_metadata(
        filename,
        classification,
        department,
        storage_path,
        version,
        principal,
        owner_id,
        size_bytes,
        parse_status,
    )
    _record_local_version(metadata)
    return metadata


def record_document_version(
    filename: str,
    classification: int,
    department: str,
    storage_path: str,
    version: int | None = None,
    *,
    principal=None,
    owner_id: str | None = None,
    size_bytes: int | None = None,
    parse_status: str = "pending",
) -> dict:
    """Register one stored version on both persistence paths, owner included.

    ``owner_id`` wins over ``principal``, which may be a Principal or a user mapping.
    The sidecar is written before the table: it is the only durable owner record when
    PostgreSQL is offline, and a version that exists on disk without ownership
    metadata would otherwise stay unattributable forever.
    """
    metadata = _version_metadata(
        filename,
        classification,
        department,
        storage_path,
        version,
        principal,
        owner_id,
        size_bytes,
        parse_status,
    )

    _record_local_version(metadata)

    if not _database_available():
        return metadata
    try:
        _ensure()
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO document_versions
                (filename, version, classification, department, storage_path, created_at,
                 owner_id, size_bytes, parse_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (filename, version) DO UPDATE SET
                    classification = EXCLUDED.classification,
                    department = EXCLUDED.department,
                    storage_path = EXCLUDED.storage_path,
                    owner_id = COALESCE(document_versions.owner_id, EXCLUDED.owner_id),
                    size_bytes = COALESCE(EXCLUDED.size_bytes, document_versions.size_bytes),
                    parse_status = EXCLUDED.parse_status
                """,
                (
                    metadata["filename"],
                    metadata["version"],
                    metadata["classification"],
                    metadata["department"] or None,
                    metadata["storage_path"],
                    metadata["created_at"],
                    metadata["owner_id"],
                    metadata["size_bytes"],
                    metadata["parse_status"],
                ),
            )
            conn.commit()
    except Exception as exc:
        logger.warning(f"[Docs] version record fallback: {exc}")
    return metadata


def current_documents() -> list[dict]:
    if not _database_available():
        rows = _local_version_rows()
    else:
        try:
            _ensure()
            with _conn() as conn:
                rows = [
                    dict(row)
                    for row in conn.execute(
                        f"""
                        SELECT {_SELECT_COLUMNS}
                        FROM document_versions
                        ORDER BY filename, version DESC
                        """
                    ).fetchall()
                ]
        except Exception as exc:
            logger.warning(f"[Docs] current listing fallback: {exc}")
            rows = _local_version_rows()

    latest = {}
    for row in rows:
        latest.setdefault(row["filename"], row)
    ordered = sorted(latest.values(), key=lambda item: item["created_at"], reverse=True)
    return _public_rows(ordered)


def list_document_versions(filename: str) -> list[dict]:
    if not _database_available():
        return _public_rows(
            sorted(_local_version_rows(filename), key=lambda item: item["version"], reverse=True)
        )
    try:
        _ensure()
        with _conn() as conn:
            rows = conn.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM document_versions
                WHERE filename = %s
                ORDER BY version DESC
                """,
                (filename,),
            ).fetchall()
        return _public_rows([dict(row) for row in rows])
    except Exception as exc:
        logger.warning(f"[Docs] history fallback: {exc}")
        return _public_rows(
            sorted(_local_version_rows(filename), key=lambda item: item["version"], reverse=True)
        )


def _logical_documents_table_exists(conn) -> bool:
    """Ask whether the lazy logical table is there, without ever poisoning the transaction.

    ``to_regclass`` is the only safe probe: a ``DELETE`` against a missing table would abort
    the surrounding transaction and take the version rows down with it. Any surprise in the
    cursor answer (a shape this function does not recognise, a driver that refuses the
    statement) is reported as "absent", which costs a skipped row and not the whole delete.

    Known unknown: the shapes read here - a ``dict_row`` mapping, a NULL, and a probe that
    raises - are the three the tests reproduce against a fake connection. Real psycopg3
    returns a plain ``dict`` for ``row_factory=dict_row``, which is what the first branch
    expects, but no test in this repository has been run against a live database, so the
    probe has not been observed on one. Verification belongs to the next backend-image
    acceptance run.
    """
    try:
        row = conn.execute("SELECT to_regclass('public.documents') AS documents_table").fetchone()
        if row is None:
            return False
        if isinstance(row, dict):
            return bool(row.get("documents_table"))
        try:
            return bool(dict(row).get("documents_table"))
        except (TypeError, ValueError):
            return bool(row[0])
    except Exception as exc:
        logger.warning(f"[Docs] logical table probe failed: {exc}")
        return False


def delete_document_versions(filename: str, storage_paths=()) -> None:
    """Remove every catalog row of a logical document from both persistence paths.

    The ``documents`` row goes in the same transaction as its versions. The upload path
    UPSERTS it (``_upsert_document`` in app/api/v1/chat.py) and nothing else in the
    repository ever removed it, which is how a deployment ends up with logical rows that
    point at files no longer on disk while ``document_versions`` reads clean. Cleaning it
    here - rather than in one more caller - is why this function is the one the delete
    route already trusts.
    """
    _drop_local_versions(filename, storage_paths)
    if not _database_available():
        return
    try:
        _ensure()
        with _conn() as conn:
            conn.execute(
                "DELETE FROM document_versions WHERE filename = %s",
                (filename,),
            )
            if _logical_documents_table_exists(conn):
                conn.execute(
                    "DELETE FROM documents WHERE filename = %s",
                    (filename,),
                )
            conn.commit()
    except Exception as exc:
        logger.warning(f"[Docs] version deletion fallback: {exc}")