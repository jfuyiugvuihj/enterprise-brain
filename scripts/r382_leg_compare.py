"""R382: apples-to-apples engine comparison under real query vectors, no scope predicate.

The scoped A/B in r382_readpath_measure.py cannot be a fair comparison: the sandbox PG
mirror carries synthetic department/classification labels while the legacy copy carries the
production values (''/1) for all 1008 chunks. This script removes the predicate so the two
ANN engines are measured on identical input, and adds the exact-kNN arm so an HNSW miss
cannot be mistaken for an engine disagreement.

Read-only: SELECT and collection.query only, against the sandbox database and a copy of the
legacy volume. The switch is moved in-process via os.environ; nothing is persisted.
"""
from __future__ import annotations

import json
import os
import sys
import time

SANDBOX_DB = "eb_r59_sandbox"
K = 5
REPEATS = 3

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


def timed(function):
    started = time.perf_counter()
    value = function()
    return value, round((time.perf_counter() - started) * 1000, 3)


def stats(samples):
    ordered = sorted(samples)
    return {"min": ordered[0], "median": ordered[len(ordered) // 2], "max": ordered[-1],
            "mean": round(sum(ordered) / len(ordered), 3)}


def diff_report(pg_ids, chroma_ids, by_id):
    shared = [chunk for chunk in pg_ids if chunk in set(chroma_ids)]
    return {
        "overlap_ratio": round(len(shared) / max(1, len(set(pg_ids) | set(chroma_ids))), 4),
        "shared": len(shared),
        "pg_only": [{"id": c, **by_id.get(c, {}).get("pg", {})} for c in pg_ids
                    if c not in set(chroma_ids)],
        "chroma_only": [{"id": c, **by_id.get(c, {}).get("chroma", {})} for c in chroma_ids
                        if c not in set(pg_ids)],
        "exact_position_match": sum(1 for a, b in zip(pg_ids, chroma_ids) if a == b),
    }


def main() -> int:
    url = os.getenv("DATABASE_URL", "")
    out_path = os.getenv("R382_JSON_OUT", "/work/out/r382_compare.json")

    import psycopg

    from app.rag import indexing, pg_store
    from app.rag.retriever import DocumentRetriever, EmbeddingError, OllamaEmbeddings

    with psycopg.connect(url) as conn:
        db = conn.execute("SELECT current_database()").fetchone()[0]
        total = conn.execute("SELECT count(*) FROM chunk_vectors").fetchone()[0]
    if db != SANDBOX_DB:
        print(f"ABORT: attached to {db!r}", file=sys.stderr)
        return 2

    embedder = OllamaEmbeddings()
    vectors = {}
    stability = {}
    for query in QUERIES:
        try:
            first = embedder.embed_query(query)
            second = embedder.embed_query(query)
        except EmbeddingError as exc:
            print(json.dumps({"blocked": {"reason": exc.reason, "detail": str(exc)[:300]}}))
            print(f"BLOCKED: embedding unreachable ({exc.reason})", file=sys.stderr)
            return 3
        vectors[query] = first
        stability[query] = {
            "identical_on_repeat": list(map(round, first, [6])) == list(map(round, second, [6]))
            if isinstance(first[0], float) else first == second,
            "max_abs_delta": round(max(abs(float(a) - float(b))
                                       for a, b in zip(first, second)), 9),
        }

    retriever = DocumentRetriever(chroma_dir=os.getenv("R382_CHROMA_DIR", "/work/chroma_db"))
    collection = retriever.collection

    rows = []
    latency = {"pg_hnsw": [], "pg_exact": [], "chroma": []}
    for index, query in enumerate(QUERIES, start=1):
        vector = vectors[query]
        best = {}
        for arm, function in (
            ("pg_hnsw", lambda: pg_store.read_topk(query_vector=vector, k=K, where=None)),
            ("chroma", lambda: collection.query(query_embeddings=[vector], n_results=K,
                                                include=["metadatas", "distances"])),
        ):
            for _ in range(REPEATS):
                result, elapsed = timed(function)
                latency[arm].append(elapsed)
            best[arm] = result

        with psycopg.connect(url) as conn:
            with conn.transaction():
                conn.execute("SET LOCAL enable_indexscan = off")
                conn.execute("SET LOCAL enable_indexonlyscan = off")
                exact_rows, elapsed = timed(lambda: conn.execute(
                    "SELECT vector_id, embedding <-> %s::vector AS distance "
                    "FROM chunk_vectors ORDER BY embedding <-> %s::vector LIMIT %s",
                    (pg_store._vector_literal(vector), pg_store._vector_literal(vector), K),
                ).fetchall())
            latency["pg_exact"].append(elapsed)

        pg_items = [{"id": str(row["vector_id"]), "distance": round(float(row["distance"]), 6),
                     "department": row.get("department") or "",
                     "classification": row.get("classification")} for row in best["pg_hnsw"]]
        chroma_result = best["chroma"]
        chroma_items = [{"id": str(chunk_id),
                         "distance": round(float(distance), 6)}
                        for chunk_id, distance in zip((chroma_result.get("ids") or [[]])[0],
                                                      (chroma_result.get("distances") or [[]])[0])]
        exact_items = [{"id": str(row[0]), "distance": round(float(row[1]), 6)}
                       for row in exact_rows]

        by_id = {}
        for item in pg_items:
            by_id.setdefault(item["id"], {})["pg"] = {"pg_distance": item["distance"]}
        for item in chroma_items:
            by_id.setdefault(item["id"], {})["chroma"] = {"chroma_distance": item["distance"]}

        pg_ids = [item["id"] for item in pg_items]
        chroma_ids = [item["id"] for item in chroma_items]
        exact_ids = [item["id"] for item in exact_items]
        rows.append({
            "n": index, "query": query,
            "pg_hnsw": pg_items, "chroma": chroma_items, "pg_exact": exact_items,
            "pg_vs_chroma": diff_report(pg_ids, chroma_ids, by_id),
            "pg_hnsw_vs_exact": diff_report(pg_ids, exact_ids, by_id),
            "chroma_vs_exact": diff_report(chroma_ids, exact_ids, by_id),
        })

    report = {
        "env": {
            "database": db, "chunk_vectors": total, "python": sys.executable,
            "k": K, "repeats": REPEATS, "queries": len(QUERIES),
            "read_backend_shipped_default": indexing.read_backend(),
            "vector_dual_write": os.getenv("VECTOR_DUAL_WRITE"),
            "note": "store-level arms bypass the switch on purpose: both engines are asked "
                    "with the identical vector so the difference is the engine, not the query",
        },
        "embedding_stability": stability,
        "rows": rows,
        "latency_ms": {arm: stats(samples) for arm, samples in latency.items()},
        "aggregate": {
            "queries": len(rows),
            "pg_vs_chroma_full_topk_agreement": sum(
                1 for row in rows if row["pg_vs_chroma"]["shared"] == K),
            "pg_vs_chroma_mean_overlap": round(
                sum(row["pg_vs_chroma"]["overlap_ratio"] for row in rows) / len(rows), 4),
            "pg_hnsw_equals_exact_all": all(
                row["pg_hnsw_vs_exact"]["shared"] == K for row in rows),
            "chroma_equals_exact_all": all(
                row["chroma_vs_exact"]["shared"] == K for row in rows),
            "pg_hnsw_recall_at_k": round(sum(
                row["pg_hnsw_vs_exact"]["shared"] for row in rows)
                / (len(rows) * K), 4),
            "chroma_recall_at_k": round(sum(
                row["chroma_vs_exact"]["shared"] for row in rows)
                / (len(rows) * K), 4),
            "distance_units": "pg arms are squared-free L2 (vector_l2_ops); chroma reports "
                              "L2 as well but its own scaling, so only the ORDER is "
                              "comparable across engines, never the raw number",
        },
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    print(f"full document at {out_path} ({len(payload)} bytes)")
    print(json.dumps({"aggregate": report["aggregate"], "latency_ms": report["latency_ms"],
                      "env": report["env"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())