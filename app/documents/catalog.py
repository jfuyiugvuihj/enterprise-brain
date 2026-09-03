import os
from datetime import datetime, timedelta, timezone

from app.common.logger import logger

_tz = timezone(timedelta(hours=8))
_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")
_initialized = False


def next_document_version(rows: list[dict], filename: str) -> int:
    versions = [int(row.get("version", 0)) for row in rows if row.get("filename") == filename]
    return max(versions, default=0) + 1


def build_storage_name(filename: str, version: int) -> str:
    stem, ext = os.path.splitext(filename)
    return f"{stem}__v{version}{ext}"


def _conn():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _ensure():
    global _initialized
    if _initialized:
        return
    with _conn() as conn:
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
        return 1


def record_document_version(
    filename: str,
    classification: int,
    department: str,
    storage_path: str,
    version: int | None = None,
) -> dict:
    _ensure()
    version = version or peek_next_document_version(filename)
    now = datetime.now(_tz).isoformat()
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
    return {
        "filename": filename,
        "version": version,
        "classification": int(classification),
        "department": department or "",
        "storage_path": storage_path,
        "created_at": now,
    }


def current_documents() -> list[dict]:
    try:
        _ensure()
        with _conn() as conn:
            rows = conn.execute(
                """
                SELECT filename, version, classification, department, storage_path, created_at
                FROM document_versions
                ORDER BY filename, version DESC
                """
            ).fetchall()
    except Exception as exc:
        logger.warning(f"[Docs] current listing failed: {exc}")
        return []

    latest = {}
    for row in rows:
        item = dict(row)
        latest.setdefault(item["filename"], item)
    return sorted(latest.values(), key=lambda item: item["created_at"], reverse=True)


def list_document_versions(filename: str) -> list[dict]:
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
        logger.warning(f"[Docs] history failed: {exc}")
        return []
