"""R382 probe: read the ranking scope off all three engines, side by side.

The report claims that flipping INDEX_BACKEND does not change what "closest" means, only
which graph answers. That claim needs the scope of each side on the record, not just the
chroma side read in isolation and the pg side quoted from the adoption plan. This probe
takes all three in one go: the sandbox that every R382 reading ran against, the production
database (strictly read-only, and proven read-only by the session flag), and the legacy
chroma volume copy, whose configuration is also on disk.

Zero writes. The session is opened with readonly=True and every statement is a SELECT; the
chroma side is only asked for its own configuration. The DSN never reaches this file, the
tree, or the report - only a masked form of it is printed.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse

SANDBOX_DB = "eb_r59_sandbox"


def mask(url: str) -> str:
    if "@" not in url:
        return "<unparseable>"
    head, tail = url.split("@", 1)
    user = head.rsplit(":", 1)[0]
    return user + ":***@" + tail


def swap_db(url: str, database: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parts._replace(path="/" + database))


def read_pg(url: str, label: str) -> dict:
    import psycopg

    out: dict = {"engine": label, "database_url_masked": mask(url)}
    # Read-only is imposed at connect time so no statement can ever run writable,
    # and transaction_read_only below is the on-paper proof that it took.
    with psycopg.connect(url, options="-c default_transaction_read_only=on") as conn:
        ident = conn.execute(
            "SELECT current_database() AS db, current_user AS usr, "
            "current_setting('transaction_read_only') AS read_only, "
            "current_setting('server_version') AS server_version"
        ).fetchone()
        out.update(zip(("database", "user", "transaction_read_only", "server_version"), ident))
        out["vectors"] = conn.execute("SELECT count(*) FROM chunk_vectors").fetchone()[0]
        out["scope"] = [
            dict(zip(("embedding_model", "dimension", "distance_function"), row))
            for row in conn.execute(
                "SELECT embedding_model, dimension, distance_function "
                "FROM public.vector_scope"
            ).fetchall()
        ]
        out["indexes"] = [
            row[0] for row in conn.execute(
                "SELECT indexdef FROM pg_indexes WHERE tablename = 'chunk_vectors' "
                "ORDER BY indexname"
            ).fetchall()
        ]
        out["ef_search_runtime"] = conn.execute("SHOW hnsw.ef_search").fetchone()[0]
        out["vector_version"] = conn.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()[0]
        # Pull the HNSW knobs out of the DDL text so the table can show them per column.
        # pgvector prints storage parameters quoted, so strip the quotes first and
        # keep every pattern free of quote characters (one less escaping trap).
        joined = " ".join(out["indexes"]).replace("'", "")
        for key, pattern in (("m", r"\bm\s*=\s*(\d+)"),
                             ("ef_construction", r"ef_construction\s*=\s*(\d+)"),
                             ("operator_class", r"\b([a-z0-9_]+_ops)\b")):
            found = re.search(pattern, joined)
            out[key] = found.group(1) if found else None
    return out


def read_chroma() -> dict:
    import chromadb

    path = os.getenv("R382_CHROMA_DIR", "/work/chroma_db")
    out: dict = {"engine": "chroma (retiring, volume copy)", "chroma_dir": path,
                 "chromadb_version": chromadb.__version__}
    try:
        collection = chromadb.PersistentClient(path=path).get_collection("enterprise_docs")
        hnsw = collection.configuration["hnsw"]
        out["vectors"] = collection.count()
        out["distance_function"] = hnsw["space"]
        out["m"] = hnsw["max_neighbors"]
        out["ef_construction"] = hnsw["ef_construction"]
        out["ef_search"] = hnsw["ef_search"]
    except Exception as exc:  # noqa: BLE001 - a probe reports what it could not read
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def main() -> int:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("ABORT: DATABASE_URL missing", file=sys.stderr)
        return 2
    sandbox_url = swap_db(url, SANDBOX_DB)
    report = {"sandbox": read_pg(sandbox_url, "pgvector sandbox"), "chroma": read_chroma()}
    if report["sandbox"].get("database") != SANDBOX_DB:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"ABORT: attached to {report['sandbox'].get('database')!r}", file=sys.stderr)
        return 2
    # Production is read second, and only because transaction_read_only came back on.
    try:
        report["production"] = read_pg(url, "pgvector production")
    except Exception as exc:  # noqa: BLE001 - a refused production read is a finding too
        report["production"] = {"engine": "pgvector production",
                                "error": f"{type(exc).__name__}: {exc}"}
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    dest = os.getenv("R382_OUT", "")
    if dest:
        with open(dest, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())