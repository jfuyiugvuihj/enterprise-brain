"""Create a PostgreSQL logical backup without exposing credentials in argv."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv


def _pg_dump_environment(database_url: str) -> tuple[dict[str, str], str]:
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
    return environment, unquote(parsed.path.lstrip("/"))


def backup_database(
    database_url: str,
    output: str | Path,
    *,
    pg_dump_path: str = "pg_dump",
) -> Path:
    """Write a custom-format backup after passing credentials only via env."""
    destination = Path(output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    environment, database_name = _pg_dump_environment(database_url)
    subprocess.run(
        [
            pg_dump_path,
            "--format=custom",
            "--file",
            str(destination),
            database_name,
        ],
        env=environment,
        check=True,
    )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError("pg_dump completed without creating a backup file")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an Enterprise Brain PostgreSQL backup.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--pg-dump", default="pg_dump")
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    database_url = (args.database_url or os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    try:
        output = backup_database(database_url, args.output, pg_dump_path=args.pg_dump)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"database backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"backup={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
