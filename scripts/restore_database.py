"""Restore or inspect a PostgreSQL logical backup without exposing credentials in argv.

The companion of ``scripts/backup_database.py``. A restore drill must run against an
explicitly named target database so an operator can verify a backup in isolation before
promoting it.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv


def _pg_environment(database_url: str) -> tuple[dict[str, str], str]:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use a PostgreSQL scheme")
    if not parsed.hostname or not parsed.path or parsed.path == "/":
        raise ValueError("DATABASE_URL must include host and database name")

    environment = os.environ.copy()
    environment["PGHOST"] = parsed.hostname
    environment["PGPORT"] = str(parsed.port or 5432)
    if parsed.username:
        environment["PGUSER"] = unquote(parsed.username)
    if parsed.password is not None:
        environment["PGPASSWORD"] = unquote(parsed.password)
    environment.pop("DATABASE_URL", None)
    return environment, unquote(parsed.path.lstrip("/"))


def _run(command: list[str], environment: dict[str, str], *, capture: bool = False) -> subprocess.CompletedProcess:
    """Execute a PostgreSQL client tool with redaction-safe error reporting."""
    try:
        return subprocess.run(
            command,
            env=environment,
            check=True,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"{command[0]} failed: {detail[-500:]}") from exc


def list_backup(archive: str | Path, *, pg_restore_path: str = "pg_restore") -> list[str]:
    """Return the archive table of contents so a backup can be verified before use."""
    source = Path(archive).resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError("backup archive is missing or empty")
    environment = os.environ.copy()
    result = _run([pg_restore_path, "--list", str(source)], environment, capture=True)
    return [line for line in (result.stdout or "").splitlines() if line.strip() and not line.startswith(";")]


def restore_database(
    archive: str | Path,
    database_url: str,
    *,
    pg_restore_path: str = "pg_restore",
) -> str:
    """Restore into the database named by ``database_url`` and return that name."""
    environment, database_name = _pg_environment(database_url)
    source = Path(archive).resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError("backup archive is missing or empty")
    _run(
        [
            pg_restore_path,
            "--dbname",
            database_name,
            "--no-owner",
            "--exit-on-error",
            str(source),
        ],
        environment,
    )
    return database_name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore an Enterprise Brain PostgreSQL backup.")
    parser.add_argument("archive")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--pg-restore", default="pg_restore")
    parser.add_argument("--list", action="store_true", dest="list_only")
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    try:
        if args.list_only:
            entries = list_backup(args.archive, pg_restore_path=args.pg_restore)
            print(f"entries={len(entries)}")
            return 0
        database_url = (args.database_url or os.getenv("DATABASE_URL") or "").strip()
        if not database_url:
            print("DATABASE_URL is required", file=sys.stderr)
            return 2
        database_name = restore_database(args.archive, database_url, pg_restore_path=args.pg_restore)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"database restore failed: {exc}", file=sys.stderr)
        return 1
    print(f"restored={database_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())