"""Apply checked-in PostgreSQL migrations explicitly during deployment."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.db.connection import open_connection, parse_database_settings
from app.db.migrations import apply_migrations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply Enterprise Brain migrations.")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)

    url = (args.database_url or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        print("DATABASE_URL is required", file=sys.stderr)
        return 2

    settings = parse_database_settings(url)
    try:
        connection = open_connection(settings)
    except Exception as exc:
        print(f"database connection failed: {exc}", file=sys.stderr)
        return 1
    try:
        try:
            applied = apply_migrations(connection, settings.database)
        except Exception as exc:
            print(f"migration failed and transaction was rolled back: {exc}", file=sys.stderr)
            return 1
    finally:
        connection.close()

    print(f"applied={len(applied)} database={settings.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
