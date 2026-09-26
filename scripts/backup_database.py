"""Create a PostgreSQL logical backup without exposing credentials in argv."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

#: A custom-format archive lists one entry per object. These two patterns read the relation
#: definition ("TABLE") and the rows ("TABLE DATA") out of that listing, because an archive
#: can name a table and still carry none of its contents.
_TABLE_ENTRY = re.compile(r"^[^;]+;\s+\d+\s+\d+\s+TABLE\s+public\s+(?P<name>\S+)\s+\S+$")
_TABLE_DATA_ENTRY = re.compile(r"^[^;]+;\s+\d+\s+\d+\s+TABLE\s+DATA\s+public\s+(?P<name>\S+)\s+\S+$")


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


def tables_in_backup(entries: list[str], *, data: bool = False) -> set[str]:
    """Return the public table names an archive of contents actually carries.

    ``data=True`` asks for the entries that hold rows instead of the relation definition.
    """
    pattern = _TABLE_DATA_ENTRY if data else _TABLE_ENTRY
    return {
        match.group("name")
        for match in (pattern.search(line) for line in entries)
        if match
    }


def missing_landing_tables(entries: list[str], required: tuple[str, ...] | set[str]) -> set[str]:
    """Return the required tables the archive lost -- its definition or its rows.

    A whole-database ``pg_dump`` covers every table *by construction*, which is reasoning
    and not a drill: it does not stop a filtered dump, a partial failure, or a table that
    only exists in the source from leaving a landing point out of the file an operator
    believes is a backup. Naming the landing points is what turns "it should be in there"
    into "it was checked to be in there".
    """
    definitions = tables_in_backup(entries)
    rows = tables_in_backup(entries, data=True)
    return {name for name in required if name not in definitions or name not in rows}


def backup_database(
    database_url: str,
    output: str | Path,
    *,
    pg_dump_path: str = "pg_dump",
    required_tables: tuple[str, ...] | set[str] = (),
    pg_restore_path: str = "pg_restore",
) -> Path:
    """Write a custom-format backup after passing credentials only via env.

    ``required_tables`` names the landing points the operator refuses to lose. For this
    project that is ``chunks`` -- the table authorization and retrieval read, together with
    its ``embedding`` column -- and ``chunk_vectors``, the table the PGVector dual write
    maintains, which is the half of the vector library a schema-only listing would report as
    "backed up" while holding no vector at all. When the argument is given, the archive
    pg_dump just wrote is listed and every named table must appear with both its definition
    and its rows, or the backup fails loudly instead of succeeding as a file that cannot be
    restored.
    """
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
    if required_tables:
        # Imported at call time so a backup run never needs the restore path to import.
        from scripts.restore_database import list_backup

        absent = missing_landing_tables(
            list_backup(destination, pg_restore_path=pg_restore_path), required_tables
        )
        if absent:
            raise RuntimeError(
                str(destination)
                + " does not carry "
                + ", ".join(sorted(absent))
                + "; a whole-database dump is not evidence that these tables survived it"
            )
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an Enterprise Brain PostgreSQL backup.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--pg-dump", default="pg_dump")
    parser.add_argument(
        "--require-table",
        action="append",
        default=[],
        dest="required_tables",
        help="refuse an archive that does not carry this table with its rows; repeat per table",
    )
    parser.add_argument(
        "--pg-restore",
        default="pg_restore",
        dest="pg_restore_path",
        help="pg_restore used to read the archive table of contents for --require-table",
    )
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    database_url = (args.database_url or os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2
    try:
        output = backup_database(
            database_url,
            args.output,
            pg_dump_path=args.pg_dump,
            required_tables=tuple(args.required_tables),
            pg_restore_path=args.pg_restore_path,
        )
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"database backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"backup={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
