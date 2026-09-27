"""R382 probe: pin down what the container actually sees before any reading is taken.

Zero writes. Every statement here is a SELECT or a read-only collection call, and the
script refuses to continue if the database it is attached to is not the R59 sandbox.
"""
from __future__ import annotations

import json
import os
import sys
import time

SANDBOX_DB = "eb_r59_sandbox"


def mask(url: str) -> str:
    if "@" not in url:
        return url
    head, tail = url.split("@", 1)
    if ":" not in head:
        return "*@" + tail
    user = head.rsplit(":", 1)[0]
    return user + ":***@" + tail


def main() -> int:
    report: dict = {"python": sys.executable, "argv_cwd": os.getcwd()}
    url = os.getenv("DATABASE_URL", "")
    report["database_url_masked"] = mask(url)

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(url, row_factory=dict_row) as conn:
        ident = conn.execute(
            "SELECT current_database() AS db, current_user AS usr, "
            "inet_server_addr()::text AS server, "
            "current_setting('server_version') AS server_version"
        ).fetchone()
        report["identity"] = ident
        if str(ident["db"]) != SANDBOX_DB:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            print(f"ABORT: attached to {ident['db']!r}, not {SANDBOX_DB!r}", file=sys.stderr)
            return 2
        report["vectors"] = conn.execute(
            "SELECT count(*) AS n FROM chunk_vectors"
        ).fetchone()["n"]
        report["scope"] = conn.execute(
            "SELECT embedding_model, dimension, distance_function "
            "FROM public.vector_scope LIMIT 3"
        ).fetchall()
        report["ids_pg"] = [
            row["vector_id"] for row in conn.execute(
                "SELECT vector_id FROM chunk_vectors ORDER BY vector_id LIMIT 5"
            ).fetchall()
        ]
        report["pg_key_sample"] = [
            f"{row['filename']}#{row['chunk_index']}" for row in conn.execute(
                "SELECT filename, chunk_index FROM chunk_vectors "
                "ORDER BY vector_id LIMIT 5"
            ).fetchall()
        ]
        report["index_meta"] = conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE tablename = 'chunk_vectors'"
        ).fetchall()

    import chromadb
    from chromadb.config import Settings

    chroma_dir = os.getenv("R382_CHROMA_DIR", "/app/chroma_db")
    report["chroma_dir"] = chroma_dir
    client = chromadb.PersistentClient(
        path=chroma_dir, settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_or_create_collection("enterprise_docs")
    report["chromadb_version"] = getattr(chromadb, "__version__", "unknown")
    report["chroma_count"] = collection.count()
    got = collection.get(include=["metadatas"])
    chroma_ids = list(got.get("ids") or [])
    report["chroma_ids"] = chroma_ids[:5]
    metas = list(got.get("metadatas") or [])
    report["chroma_key_sample"] = [
        f"{m.get('filename')}#{m.get('chunk_index')}" for m in metas[:5]
    ]
    with psycopg.connect(url) as conn:
        pg_keys = {
            f"{a}#{b}" for a, b in conn.execute(
                "SELECT filename, chunk_index FROM chunk_vectors"
            ).fetchall()
        }
    chroma_keys = {
        f"{m.get('filename')}#{m.get('chunk_index')}" for m in metas
    }
    report["keys_pg"] = len(pg_keys)
    report["keys_chroma"] = len(chroma_keys)
    report["keys_shared"] = len(pg_keys & chroma_keys)
    report["keys_pg_only"] = len(pg_keys - chroma_keys)
    report["keys_chroma_only"] = len(chroma_keys - pg_keys)
    with psycopg.connect(url) as conn:
        pg_ids = {r[0] for r in conn.execute("SELECT vector_id FROM chunk_vectors").fetchall()}
    report["ids_shared"] = len(pg_ids & set(chroma_ids))

    from app.rag import indexing
    from app.rag.retriever import OllamaEmbeddings

    report["read_backend_default"] = indexing.read_backend()
    os.environ["INDEX_BACKEND"] = "pgvector"
    report["read_backend_after_in_process_env"] = indexing.read_backend()
    del os.environ["INDEX_BACKEND"]
    report["read_backend_after_unset"] = indexing.read_backend()

    embedder = OllamaEmbeddings()
    report["embed_api_url"] = embedder.api_url
    started = time.perf_counter()
    try:
        vector = embedder.embed_query("R382 probe: quarterly revenue growth")
    except Exception as exc:  # noqa: BLE001 - the probe reports, it does not rescue
        report["embedding_error"] = f"{type(exc).__name__}: {exc}"
        report["embedding_reason"] = getattr(exc, "reason", "")
        report["embedding_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 3
    report["embedding_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    report["embedding_dim"] = len(vector)
    report["embedding_nonzero"] = sum(1 for value in vector if value) 
    report["embedding_head"] = [round(float(value), 6) for value in vector[:4]]
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())