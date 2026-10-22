"""R382 probe: what distance function does the retiring engine actually rank by?

vector_scope declares one embedding profile for the mirror: nomic-embed-text / 768 / l2 /
m16 / efc100. The legacy collection was created without an explicit space, so whatever
default the shipped engine applies is what today's answers are ranked by. If the two
differ, flipping INDEX_BACKEND changes ranking semantics for every answer, and the diff set
is a metric decision rather than an index defect. This probe reads the answer off the
collection itself, so the "both sides rank by L2" claim in the report does not rest on the
rank-comparison inference alone.

Read-only: the SQLite file is opened mode=ro and only SELECTed; the engine is only asked for
its own view of the collection. Nothing is created, migrated, or cleaned up. Only
configuration-bearing tables are scanned, so no customer document text is copied anywhere.
"""
from __future__ import annotations

import json
import os
import sqlite3

CHROMA = os.getenv("R382_CHROMA_DIR", "/work/chroma_db")
DEST = os.getenv("R382_OUT", "")
TOKENS = ("space", "hnsw", "cosine", "l2", "inner_product", "distance", "neighbor",
          "ef_construction", "ef_search", "m16", "vector_index")
CONFIG_TABLES = {"collections", "collection_metadata", "segment_metadata", "segments",
                 "segment_indexes", "segment_index_params", "embeddings_queue_config",
                 "maintenance_log", "collection_config"}

report: dict = {"chroma_dir": CHROMA, "engine_version": None}

import chromadb

report["engine_version"] = chromadb.__version__
client = chromadb.PersistentClient(path=CHROMA)
collection = client.get_collection("enterprise_docs")
report["count"] = collection.count()

for name in ("configuration", "get_index_params"):
    attribute = getattr(collection, name, None)
    if attribute is None:
        continue
    try:
        value = attribute() if callable(attribute) else attribute
        report[name] = value.model_dump() if hasattr(value, "model_dump") else value
    except Exception as exc:  # noqa: BLE001 - a probe reports what it could not read
        report[name] = f"<unavailable {type(exc).__name__}: {exc}>"

connection = sqlite3.connect(f"file:{CHROMA}/chroma.sqlite3?mode=ro", uri=True)
present = {row[0] for row in connection.execute(
    "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
report["config_tables_present"] = sorted(CONFIG_TABLES & present)
report["config_tables_absent"] = sorted(set(CONFIG_TABLES) - present)

hits = []
for table in report["config_tables_present"]:
    columns = [row[1] for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall()]
    for column in columns:
        try:
            rows = connection.execute(
                f"SELECT rowid, {column} FROM {table} LIMIT 400").fetchall()
        except sqlite3.Error:
            continue
        for row_id, value in rows:
            text = str(value)
            if any(token in text.lower() for token in TOKENS):
                hits.append({"table": table, "column": column, "rowid": row_id,
                             "value": text[:1200]})
report["config_bearing_values"] = hits
payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
if DEST:
    with open(DEST, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload + "\n")
print(payload)