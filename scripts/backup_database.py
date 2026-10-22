"""Create a PostgreSQL logical backup without exposing credentials in argv.

R596 closes the half of "we have a backup" that ``pg_dump`` cannot answer. Database-level and
role-in-database settings live in ``pg_db_role_setting``, which appears nowhere in a
custom-format archive's table of contents, so a whole-database dump can be perfectly green
while the restored database answers ``current_setting('app.embedding_dimension')`` with
MISSING -- the width migration 0010 and the read path both depend on. A backup therefore does
not finish when the dump exists: it finishes when the dump *and* its paired
``<archive stem>.globals.json`` / ``<archive stem>.globals.sql`` exist next to it, carrying the
settings that were read off the source database and a statement file the restore side can
re-apply before it reconciles anything. The artifact shape is R587's shape (see
``scripts/restore_database.py``), not a second format invented here.
"""
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


def _globals_book():
    """成对产物那一本账住在恢复侧（``scripts/restore_database.py``，R587 的口径）。

    包内导入优先；``python scripts/backup_database.py`` 直跑时只有 ``scripts/`` 在 sys.path
    上，那就退回同目录导入——操作者那条路必须走得通，不能只在 pytest 里绿。
    """
    try:
        from scripts import restore_database as book
    except ImportError:
        here = str(Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        import restore_database as book
    return book


def pair_globals_with_backup(database_url: str, archive: str | Path, *,
                             psql_path: str = "psql") -> dict:
    """判据①备份侧那一半：与归档同目录、同前缀落下 ``.globals.json`` 与 ``.globals.sql``。

    少了这一步，"整库备份成功"就还是那句推理而不是演练：dump 里一枚库级 setting 都没有，
    恢复出来的库 ``app.embedding_dimension`` / ``app.embedding_model`` 全是 MISSING，而备份
    日志与向量行数都好看。成对产物带归档 sha256，两侧不成对时恢复侧当场拒收。
    """
    return _globals_book().write_globals_pair(database_url, archive, psql_path=psql_path)

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
    parser.add_argument(
        "--psql",
        default="psql",
        dest="psql_path",
        help="psql used to read the database-level settings pg_dump cannot carry; the "
             "production image installs postgresql-client-17 for it (R596, re-pinned by R608)",
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
    book = _globals_book()
    try:
        pair = pair_globals_with_backup(database_url, output, psql_path=args.psql_path)
    except book.RefuseError as exc:
        print(f"database backup refused: {exc}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"database backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"globals={pair['json']}")
    print(f"globals_sql={pair['sql']}")
    print(f"globals_pair={pair['json_sha256'][:12]}/{pair['sql_sha256'][:12]} "
          f"archive={pair['archive_sha256'][:12]}")
    print(f"globals_applied={pair['applied']} globals_deferred={pair['deferred']}")
    print(f"globals_profile={pair['profile']}")
    print(f"globals_session={pair['session_profile']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
