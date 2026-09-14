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


def next_document_version(rows: list[dict], filename: str) -> int:
    versions = [int(row.get("version", 0)) for row in rows if row.get("filename") == filename]
    return max(versions, default=0) + 1


def build_storage_name(filename: str, version: int) -> str:
    stem, ext = os.path.splitext(filename)
    return f"{stem}__v{version}{ext}"


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


def _local_version_rows(filename: str | None = None) -> list[dict]:
    rows = []
    pattern = re.compile(r"^(?P<stem>.+)__v(?P<version>\d+)(?P<ext>\.[^.]+)$")
    directory = Path(DOCUMENTS_DIR)
    if not directory.is_dir():
        return rows

    for path in directory.iterdir():
        if not path.is_file():
            continue
        match = pattern.match(path.name)
        if not match:
            continue
        original_name = f"{match.group('stem')}{match.group('ext')}"
        if filename and original_name != filename:
            continue
        rows.append(
            {
                "filename": original_name,
                "version": int(match.group("version")),
                "classification": 1,
                "department": "",
                "storage_path": str(path),
                "created_at": datetime.fromtimestamp(path.stat().st_mtime, _tz).isoformat(),
            }
        )
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


def record_document_version(
    filename: str,
    classification: int,
    department: str,
    storage_path: str,
    version: int | None = None,
) -> dict:
    version = version or peek_next_document_version(filename)
    now = datetime.now(_tz).isoformat()
    metadata = {
        "filename": filename,
        "version": version,
        "classification": int(classification),
        "department": department or "",
        "storage_path": storage_path,
        "created_at": now,
    }
    if not _database_available():
        return metadata
    try:
        _ensure()
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO document_versions
                (filename, version, classification, department, storage_path, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (filename, version, int(classification), department or None, storage_path, now),
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
                        """
                        SELECT filename, version, classification, department, storage_path, created_at
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
    return sorted(latest.values(), key=lambda item: item["created_at"], reverse=True)


def list_document_versions(filename: str) -> list[dict]:
    if not _database_available():
        return sorted(_local_version_rows(filename), key=lambda item: item["version"], reverse=True)
    try:
        _ensure()
        with _conn() as conn:
            rows = conn.execute(
                """
                SELECT filename, version, classification, department, storage_path, created_at
                FROM document_versions
                WHERE filename = %s
                ORDER BY version DESC
                """,
                (filename,),
            ).fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        logger.warning(f"[Docs] history fallback: {exc}")
        return sorted(_local_version_rows(filename), key=lambda item: item["version"], reverse=True)


def delete_document_versions(filename: str) -> None:
    if not _database_available():
        return
    try:
        _ensure()
        with _conn() as conn:
            conn.execute(
                "DELETE FROM document_versions WHERE filename = %s",
                (filename,),
            )
            conn.commit()
    except Exception as exc:
        logger.warning(f"[Docs] version deletion fallback: {exc}")
