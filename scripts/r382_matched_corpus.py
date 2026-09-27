"""R382: end-to-end A/B on a corpus where both engines carry the SAME scope metadata.

The first pass (r382_readpath_measure.py) could not produce a fair overlap ratio: the
sandbox mirror carries synthetic department/classification labels while the legacy volume
carries production values (''/1) on all 1008 chunks, so any department predicate returns
rows on one side and nothing on the other. That is a metadata asymmetry, not an engine
difference, and it hides exactly the number the owner asked for.

Fix: stamp the mirror's synthetic labels onto the legacy corpus, then compare both legs end
to end under identical queries, identical principals, identical k. The stamp happens with
collection.update(), which touches metadata only -- upsert() would re-write the vectors and
rebuild the HNSW graph, which would silently invalidate the recall reading taken earlier.
The script verifies afterwards, row by row, that the labels match the mirror and that not
one vector moved.

It writes only to the operator's temp copy of the volume, never to the production one and
never to the database.
"""
from __future__ import annotations

import json
import os

import numpy as np
import psycopg

SANDBOX_DB = "eb_r59_sandbox"
TOP_K = 5

QUERIES = [
    "2026年第一季度营收和利润情况怎么样",
    "员工年假和调休是怎么规定的",
    "私有化部署对环境配置有什么要求",
    "告警规则如何配置通知渠道",
    "等保三级对日志审计的要求",
    "供应商评估表的使用流程",
    "数据源接入支持哪些数据库",
    "五一放假安排通知",
    "AI 大模型在企业落地的应用场景",
    "仓库管理标准操作规程的出入库要求",
    "网络安全法对数据分类分级的要求",
    "Pulsar 迁移相比 RabbitMQ 的优势",
]

PRINCIPALS = [
    ("sales-c1", "sales", 1),
    ("engineering-c2", "engineering", 2),
    ("finance-c3", "finance", 3),
    ("hr-c4", "hr", 4),
    ("hr-c1-impossible", "hr", 1),
]


def make_principal(department: str, clearance: int):
    from app.common.identity import Principal

    return Principal(
        user_id=f"r382-{department}-c{clearance}", username=f"r382-{department}",
        roles=["user"], permissions=[], department=department, department_ids=[],
        clearance=clearance, status="active",
    )


def pg_label_map(url: str) -> dict:
    with psycopg.connect(url) as conn:
        return {str(vector_id): (department, int(classification)) for vector_id, department,
                classification in conn.execute(
                    "SELECT vector_id, department, classification FROM chunk_vectors")}


def stamp_labels(collection, labels: dict) -> dict:
    """Metadata-only stamp, then prove the vectors and ids are exactly what they were."""
    import chromadb  # noqa: F401  (kept so an import failure is visible at this line)

    before = collection.get(include=["metadatas", "embeddings"])
    before_ids = [str(item) for item in before["ids"]]
    before_vectors = {chunk: np.asarray(vector, dtype=np.float32)
                      for chunk, vector in zip(before_ids, before["embeddings"])}
    batch = 200
    for start in range(0, len(before_ids), batch):
        chunk_ids = before_ids[start:start + batch]
        collection.update(ids=chunk_ids,
                          metadatas=[{"department": labels[item][0],
                                      "classification": labels[item][1],
                                      "filename": item.rsplit("_", 1)[0],
                                      "chunk_index": int(item.rsplit("_", 1)[1])}
                                     for item in chunk_ids])
    after = collection.get(include=["metadatas", "embeddings"])
    after_ids = [str(item) for item in after["ids"]]
    label_mismatches = [chunk for chunk, meta in zip(after_ids, after["metadatas"])
                        if (str((meta or {}).get("department") or ""),
                            int((meta or {}).get("classification") or -1))
                        != tuple(labels[chunk])]
    moved = []
    for chunk, vector in zip(after_ids, after["embeddings"]):
        original = before_vectors.get(chunk)
        if original is None or not np.array_equal(original, np.asarray(vector, np.float32)):
            moved.append(chunk)
    return {"rows_before": len(before_ids), "rows_after": len(after_ids),
            "ids_added_or_lost": len(set(before_ids) ^ set(after_ids)),
            "label_mismatches_after_stamp": len(label_mismatches),
            "vector_rows_changed_by_stamp": len(moved),
            "count_after": collection.count(),
            "reading": "update() moves metadata only; a non-zero vector count here would "
                       "mean the recall reading above no longer describes this corpus"}


def run_leg(backend: str, principals) -> dict:
    from app.rag import indexing
    from app.rag.retrieval_pipeline import RetrievalPipeline

    os.environ["INDEX_BACKEND"] = backend
    assert indexing.read_backend() == backend
    pipeline = RetrievalPipeline()
    pipeline.bm25.build_index()
    leg = {}
    for name, department, clearance in principals:
        principal = make_principal(department, clearance)
        rows = []
        for query in QUERIES:
            import time

            started = time.perf_counter()
            hits, _ = pipeline.search_for_principal(query, principal, top_k=TOP_K,
                                                    tier="fast")
            rows.append({
                "query": query,
                "seconds": round(time.perf_counter() - started, 4),
                "ids": [f"{h.get('source')}_{h.get('chunk_index')}" for h in hits],
                "labels": [[str(h.get("department")), h.get("classification")] for h in hits],
            })
        leg[name] = rows
    return leg


def compare(pg_rows, chroma_rows) -> list:
    table = []
    for pg_row, chroma_row in zip(pg_rows, chroma_rows):
        pg_ids = pg_row["ids"]
        chroma_ids = chroma_row["ids"]
        shared = [item for item in pg_ids if item in set(chroma_ids)]
        table.append({
            "query": pg_row["query"], "pg_ids": pg_ids, "chroma_ids": chroma_ids,
            "pg_labels": pg_row["labels"], "chroma_labels": chroma_row["labels"],
            "shared": len(shared),
            "overlap_ratio": round(len(shared) / max(1, len(set(pg_ids) | set(chroma_ids))), 4),
            "pg_only": [item for item in pg_ids if item not in set(chroma_ids)],
            "chroma_only": [item for item in chroma_ids if item not in set(pg_ids)],
            "position_match": sum(1 for a, b in zip(pg_ids, chroma_ids) if a == b),
            "seconds_pg": pg_row["seconds"], "seconds_chroma": chroma_row["seconds"],
        })
    return table


def violating(labels, department, clearance) -> list:
    return [label for label in labels
            if (label[1] is None or int(label[1]) > clearance
                or str(label[0]) != department)]


def scoped_store(collection, principals, vectors, top_k) -> dict:
    """Both engines under the caller's real predicate, with the score each one reports.

    This is the leg-level reading behind the end-to-end table: it names the chunk and the
    distance, so a difference can be pointed at instead of only counted.
    """
    from app.rag import pg_store
    from app.rag.filters import resolve_document_retrieval_scope

    result = {}
    for name, department, clearance in principals:
        scope = resolve_document_retrieval_scope(make_principal(department, clearance))
        rows = []
        for query in QUERIES:
            vector = vectors[query]
            pg_rows = [{"id": str(row["vector_id"]),
                        "distance": round(float(row["distance"]), 6),
                        "department": row.get("department") or "",
                        "classification": row.get("classification")}
                       for row in pg_store.read_topk(query_vector=vector, k=top_k,
                                                     where=scope.filters)]
            kwargs = {"query_embeddings": [vector], "n_results": top_k,
                      "include": ["metadatas", "distances"]}
            if scope.filters:
                kwargs["where"] = scope.filters
            found = collection.query(**kwargs)
            chroma_rows = [{"id": str(chunk_id), "distance": round(float(distance), 6),
                            "department": (meta or {}).get("department") or "",
                            "classification": (meta or {}).get("classification")}
                           for chunk_id, distance, meta in
                           zip((found.get("ids") or [[]])[0],
                               (found.get("distances") or [[]])[0],
                               (found.get("metadatas") or [[]])[0])]
            pg_ids = [row["id"] for row in pg_rows]
            chroma_ids = [row["id"] for row in chroma_rows]
            shared = [item for item in pg_ids if item in set(chroma_ids)]
            scores = {}
            for row in pg_rows:
                scores[row["id"]] = {"pg_distance": row["distance"]}
            for row in chroma_rows:
                scores.setdefault(row["id"], {})["chroma_distance"] = row["distance"]
            rows.append({
                "query": query, "pg": pg_rows, "chroma": chroma_rows,
                "shared": len(shared),
                "overlap_ratio": round(len(shared)
                                       / max(1, len(set(pg_ids) | set(chroma_ids))), 4),
                "pg_only": [{"id": item, **scores[item]} for item in pg_ids
                            if item not in set(chroma_ids)],
                "chroma_only": [{"id": item, **scores[item]} for item in chroma_ids
                                if item not in set(pg_ids)],
                "position_match": sum(1 for a, b in zip(pg_ids, chroma_ids) if a == b),
                "pg_out_of_scope": [row for row in pg_rows
                                    if row["classification"] not in scope.classification_levels
                                    or (scope.departments is not None
                                        and row["department"] not in scope.departments)],
                "chroma_out_of_scope": [row for row in chroma_rows
                                        if row["classification"] not in scope.classification_levels
                                        or (scope.departments is not None
                                            and row["department"] not in scope.departments)],
            })
        result[name] = {"filters": scope.filters, "rows": rows}
    return result


def main() -> int:
    url = os.getenv("DATABASE_URL", "")
    with psycopg.connect(url) as conn:
        db = conn.execute("SELECT current_database()").fetchone()[0]
    if db != SANDBOX_DB:
        raise SystemExit(f"ABORT: attached to {db!r}")

    from app.rag.retriever import DocumentRetriever

    labels = pg_label_map(url)
    retriever = DocumentRetriever(chroma_dir=os.getenv("R382_CHROMA_DIR", "./chroma_db"))
    stamp = stamp_labels(retriever.collection, labels)

    from app.rag.retriever import OllamaEmbeddings

    embedder = OllamaEmbeddings()
    vectors = {query: embedder.embed_query(query) for query in QUERIES}
    scoped = scoped_store(retriever.collection, PRINCIPALS, vectors, TOP_K)

    pg_leg = run_leg("pgvector", PRINCIPALS)
    chroma_leg = run_leg("chroma", PRINCIPALS)
    os.environ.pop("INDEX_BACKEND", None)

    report = {"database": db, "corpus_stamp": stamp, "top_k": TOP_K,
              "queries": len(QUERIES), "tables": {}, "permission": {}, "scoped_store": scoped}
    for name, department, clearance in PRINCIPALS:
        table = compare(pg_leg[name], chroma_leg[name])
        report["tables"][name] = table
        report["permission"][name] = {
            "department": department, "clearance": clearance,
            "pg_violations": sum(len(violating(row["pg_labels"], department, clearance))
                                 for row in table),
            "chroma_violations": sum(len(violating(row["chroma_labels"], department, clearance))
                                     for row in table),
            "pg_hits": sum(len(row["pg_ids"]) for row in table),
            "chroma_hits": sum(len(row["chroma_ids"]) for row in table),
            "pg_empty_queries": sum(1 for row in table if not row["pg_ids"]),
            "chroma_empty_queries": sum(1 for row in table if not row["chroma_ids"]),
            "mean_overlap": round(sum(row["overlap_ratio"] for row in table) / len(table), 4),
        }
    cells = len(PRINCIPALS) * len(QUERIES)
    report["summary"] = {
        "cells": cells,
        "mean_overlap_all": round(sum(row["overlap_ratio"]
                                      for table in report["tables"].values() for row in table)
                                  / cells, 4),
        "full_agreement_cells": sum(1 for table in report["tables"].values() for row in table
                                    if row["shared"] == TOP_K),
        "pg_violations_total": sum(item["pg_violations"]
                                   for item in report["permission"].values()),
        "chroma_violations_total": sum(item["chroma_violations"]
                                       for item in report["permission"].values()),
    }
    scoped_rows = [row for item in scoped.values() for row in item["rows"]]
    report["summary"]["scoped_cells"] = len(scoped_rows)
    report["summary"]["scoped_mean_overlap"] = round(
        sum(row["overlap_ratio"] for row in scoped_rows) / len(scoped_rows), 4)
    report["summary"]["scoped_full_agreement_cells"] = sum(
        1 for row in scoped_rows if row["shared"] == TOP_K)
    report["summary"]["scoped_pg_out_of_scope_rows"] = sum(
        len(row["pg_out_of_scope"]) for row in scoped_rows)
    report["summary"]["scoped_chroma_out_of_scope_rows"] = sum(
        len(row["chroma_out_of_scope"]) for row in scoped_rows)
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    out = os.getenv("R382_MATCHED_OUT", "./out/r382_matched.json")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    print(f"full document at {out} ({len(payload)} bytes)")
    print(json.dumps({"corpus_stamp": stamp, "permission": report["permission"],
                      "summary": report["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())