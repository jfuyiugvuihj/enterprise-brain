"""Immutable PostgreSQL migration metadata, validation, and execution helpers.

Importing this module only reads checked-in SQL files. Applying migrations remains an
explicit deployment responsibility and must occur under a PostgreSQL advisory lock.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    checksum: str
    sql: str


_MIGRATION_FILENAME = re.compile(r"(?P<version>\d{4})_(?P<name>[a-z][a-z0-9_]*)\.sql\Z")
_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_MANIFEST_FILENAME = "manifest.json"
_CREATE_LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(32) PRIMARY KEY,
    name TEXT NOT NULL,
    checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""
_SELECT_LEDGER_SQL = "SELECT version, checksum FROM schema_migrations ORDER BY version"
_INSERT_LEDGER_SQL = """
INSERT INTO schema_migrations (version, name, checksum)
VALUES (%s, %s, %s)
"""


def _load_manifest(migrations_dir: Path) -> dict[str, str]:
    manifest_path = migrations_dir / _MANIFEST_FILENAME
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"migration manifest does not exist: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"migration manifest is invalid JSON: {manifest_path}") from exc
    if not isinstance(raw, dict) or not raw:
        raise ValueError("migration manifest must be a non-empty object")

    manifest: dict[str, str] = {}
    for filename, checksum in raw.items():
        if not isinstance(filename, str) or not isinstance(checksum, str):
            raise ValueError("migration manifest entries must be string filename/checksum pairs")
        if _MIGRATION_FILENAME.fullmatch(filename) is None:
            raise ValueError(f"invalid migration filename in manifest: {filename}")
        if re.fullmatch(r"[0-9a-f]{64}", checksum) is None:
            raise ValueError(f"invalid migration checksum in manifest: {filename}")
        manifest[filename] = checksum
    return manifest


def discover_migrations(directory: str | Path | None = None) -> tuple[Migration, ...]:
    """Read immutable, manifest-verified SQL migrations without opening a connection."""
    migrations_dir = Path(directory) if directory is not None else _DEFAULT_MIGRATIONS_DIR
    if not migrations_dir.is_dir():
        raise ValueError(f"migration directory does not exist: {migrations_dir}")

    manifest = _load_manifest(migrations_dir)
    sql_files = sorted(migrations_dir.glob("*.sql"))
    actual_filenames = {path.name for path in sql_files}
    manifest_filenames = set(manifest)
    if actual_filenames != manifest_filenames:
        missing = sorted(manifest_filenames - actual_filenames)
        untracked = sorted(actual_filenames - manifest_filenames)
        details = []
        if missing:
            details.append(f"missing files: {', '.join(missing)}")
        if untracked:
            details.append(f"untracked files: {', '.join(untracked)}")
        raise ValueError(f"migration manifest mismatch ({'; '.join(details)})")

    migrations: list[Migration] = []
    seen_versions: set[str] = set()
    for path in sql_files:
        match = _MIGRATION_FILENAME.fullmatch(path.name)
        if match is None:
            raise ValueError(f"invalid migration filename: {path.name}")

        version = match.group("version")
        if version in seen_versions:
            raise ValueError(f"duplicate migration version: {version}")
        seen_versions.add(version)

        sql = path.read_text(encoding="utf-8")
        if not sql.strip():
            raise ValueError(f"migration SQL must not be empty: {path.name}")
        checksum = sha256(sql.encode("utf-8")).hexdigest()
        if checksum != manifest[path.name]:
            raise ValueError(f"migration manifest checksum mismatch: {path.name}")
        migrations.append(
            Migration(
                version=version,
                name=match.group("name"),
                checksum=checksum,
                sql=sql,
            )
        )
    return tuple(migrations)


MIGRATIONS = discover_migrations()


def migration_plan(
    applied_versions: Mapping[str, str] | None = None,
    *,
    migrations: tuple[Migration, ...] = MIGRATIONS,
) -> list[Migration]:
    """Return pending migrations and reject missing or drifted ledger checksums."""
    if applied_versions is None:
        checksums: dict[str, str] = {}
    elif not isinstance(applied_versions, Mapping):
        raise TypeError("applied migration checksums must be a mapping")
    else:
        checksums = dict(applied_versions)

    known_versions = {migration.version for migration in migrations}
    unknown_versions = sorted(set(checksums) - known_versions)
    if unknown_versions:
        joined = ", ".join(unknown_versions)
        raise ValueError(f"applied migration is missing from the catalog: {joined}")

    pending: list[Migration] = []
    for migration in migrations:
        if migration.version not in checksums:
            pending.append(migration)
            continue
        applied_checksum = checksums[migration.version]
        if not isinstance(applied_checksum, str) or applied_checksum != migration.checksum:
            raise ValueError(f"migration checksum mismatch: {migration.version}")
    return pending


def migration_lock_key(database_name: str) -> str:
    value = (database_name or "").strip()
    if not value:
        raise ValueError("database name is required for migration lock")
    return f"enterprise-brain:migrations:{value}"


def _ledger_checksums(rows: list[Any]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for row in rows:
        if isinstance(row, Mapping):
            version, checksum = row["version"], row["checksum"]
        else:
            version, checksum = row[0], row[1]
        checksums[str(version)] = str(checksum)
    return checksums


def apply_migrations(
    connection: Any,
    database_name: str,
    *,
    migrations: tuple[Migration, ...] = MIGRATIONS,
) -> list[Migration]:
    """Apply pending migrations in one explicit transaction and record checksums.

    The caller owns connection creation and error reporting. PostgreSQL's
    transaction-scoped advisory lock prevents concurrent deployment runners from
    applying the same migration set at once.
    """
    lock_key = migration_lock_key(database_name)
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_key,))
        connection.execute(_CREATE_LEDGER_SQL)
        result = connection.execute(_SELECT_LEDGER_SQL)
        pending = migration_plan(_ledger_checksums(result.fetchall()), migrations=migrations)
        for migration in pending:
            connection.execute(migration.sql)
            connection.execute(
                _INSERT_LEDGER_SQL,
                (migration.version, migration.name, migration.checksum),
            )
    return pending
