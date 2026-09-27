"""R382: is the top-k disagreement between the engines the index, or the two copies drifting?

r382_leg_compare.py found pgvector HNSW reproducing the exact top-5 on every query while the
legacy engine missed 27% of slots. That number means nothing until the two stores are shown
to hold the same vectors: the mirror was populated from a read-only copy of the legacy volume
through a text round trip, so a float32 difference would move near-ties and look exactly like
an approximation miss. This script separates the two by brute force: exact KNN computed on
each engine's OWN vectors, compared against that engine's ANN answer.

Then it times the hot-set leg in both states with a predicate it can actually satisfy, so the
"how much does switching save" number is not a scan-and-reject artefact.

Read-only throughout: SELECT on the sandbox, get/query on a copy of the legacy volume.
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

SANDBOX_DB = "eb_r59_sandbox"
K = 5

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
    return {"min": ordered[0], "median": ordered[len(ordered) // 2], "max": ordered[-1]}


def exact_topk(matrix, ids, vector, k):
    started = time.perf_counter()
    squared = ((matrix - np.asarray(vector, dtype=np.float32)) ** 2).sum(axis=1)
    order = np.argsort(squared, kind="stable")[:k]
    took = round((time.perf_counter() - started) * 1000, 3)
    return ([ids[index] for index in order], [float(squared[index]) for index in order], took)


def main() -> int:
    import psycopg

    from app.rag import pg_store
    from app.rag.retriever import DocumentRetriever, OllamaEmbeddings

    url = os.getenv("DATABASE_URL", "")
    with psycopg.connect(url) as conn:
        db = conn.execute("SELECT current_database()").fetchone()[0]
    if db != SANDBOX_DB:
        raise SystemExit(f"ABORT: attached to {db!r}")

    retriever = DocumentRetriever(chroma_dir=os.getenv("R382_CHROMA_DIR", "/work/chroma_db"))
    collection = retriever.collection

    legacy = collection.get(include=["embeddings", "metadatas"])
    legacy_ids = [str(item) for item in (legacy.get("ids") or [])]
    legacy_matrix = np.asarray(legacy.get("embeddings"), dtype=np.float32)

    with psycopg.connect(url) as conn:
        mirrored_ids = []
        mirrored_rows = []
        for vector_id, text in conn.execute(
                "SELECT vector_id, embedding::text FROM chunk_vectors ORDER BY vector_id"):
            mirrored_ids.append(str(vector_id))
            mirrored_rows.append(np.fromstring(text[1:-1], dtype=np.float32, sep=","))
    mirrored_matrix = np.stack(mirrored_rows)

    report = {
        "database": db,
        "corpus": {"legacy_rows": int(legacy_matrix.shape[0]),
                   "mirrored_rows": int(mirrored_matrix.shape[0]),
                   "dimension": [int(legacy_matrix.shape[1]), int(mirrored_matrix.shape[1])]},
    }

    legacy_position = {chunk: index for index, chunk in enumerate(legacy_ids)}
    mirrored_position = {chunk: index for index, chunk in enumerate(mirrored_ids)}
    deltas = []
    cosine = []
    for vector_id, index in legacy_position.items():
        mirror_index = mirrored_position.get(vector_id)
        if mirror_index is None:
            continue
        mirrored_vector = mirrored_matrix[mirror_index]
        legacy_vector = legacy_matrix[index]
        deltas.append(float(np.max(np.abs(mirrored_vector - legacy_vector))))
        denominator = float(np.linalg.norm(mirrored_vector) * np.linalg.norm(legacy_vector)) or 1.0
        cosine.append(float(np.dot(mirrored_vector, legacy_vector) / denominator))
    aligned = [chunk for chunk in mirrored_ids if chunk in legacy_position]
    report["vector_parity"] = {
        "ids_compared": len(deltas),
        "ids_only_legacy": len(set(legacy_ids) - set(mirrored_ids)),
        "ids_only_mirrored": len(set(mirrored_ids) - set(legacy_ids)),
        "max_abs_element_delta": max(deltas),
        "mean_abs_element_delta": float(np.mean(deltas)),
        "rows_bitwise_equal": sum(1 for delta in deltas if delta == 0.0),
        "rows_within_float32_eps": sum(1 for delta in deltas if delta <= 1e-6),
        "min_pairwise_cosine": min(cosine),
        "aligned_ids": len(aligned),
    }

    embedder = OllamaEmbeddings()
    per_query = []
    ann_latency = {"pg_hnsw": [], "legacy_hnsw": []}
    exact_latency = {"pg_brute": [], "legacy_brute": []}
    for index, query in enumerate(QUERIES, start=1):
        vector, took = timed(lambda: embedder.embed_query(query))
        array = np.asarray(vector, dtype=np.float32)
        pg_rows, pg_took = timed(lambda: pg_store.read_topk(
            query_vector=vector, k=K, where=None))
        pg_ann = [str(row["vector_id"]) for row in pg_rows]
        legacy_result, legacy_took = timed(lambda: collection.query(
            query_embeddings=[vector], n_results=K, include=["distances"]))
        legacy_ann = [str(item) for item in (legacy_result.get("ids") or [[]])[0]]
        pg_exact_ids, pg_exact_distances, pg_brute_ms = exact_topk(
            mirrored_matrix, mirrored_ids, array, K)
        legacy_exact_ids, legacy_exact_distances, legacy_brute_ms = exact_topk(
            legacy_matrix, legacy_ids, array, K)
        ann_latency["pg_hnsw"].append(pg_took)
        ann_latency["legacy_hnsw"].append(legacy_took)
        exact_latency["pg_brute"].append(pg_brute_ms)
        exact_latency["legacy_brute"].append(legacy_brute_ms)
        per_query.append({
            "n": index, "query": query, "embed_ms": took,
            "pg_ann": pg_ann, "pg_brute": pg_exact_ids,
            "legacy_ann": legacy_ann, "legacy_brute": legacy_exact_ids,
            "pg_ann_equals_own_brute": pg_ann == pg_exact_ids,
            "legacy_ann_equals_own_brute": legacy_ann == legacy_exact_ids,
            "pg_ann_set_vs_own_brute": len(set(pg_ann) & set(pg_exact_ids)),
            "legacy_ann_set_vs_own_brute": len(set(legacy_ann) & set(legacy_exact_ids)),
            "cross_engine_brute_identical": pg_exact_ids == legacy_exact_ids,
            "pg_brute_equals_legacy_brute_set": len(set(pg_exact_ids) & set(legacy_exact_ids)),
            "pg_ann_vs_legacy_ann": len(set(pg_ann) & set(legacy_ann)),
            "distances": {"pg_brute_squared_l2": [round(d, 6) for d in pg_exact_distances],
                          "legacy_ann_reported": [float(item) for item in
                                                  (legacy_result.get("distances") or [[]])[0]],
                          "pg_ann_reported": [round(float(row["distance"]), 6)
                                              for row in pg_rows]},
        })
    report["per_query"] = per_query
    report["recall"] = {
        "pg_hnsw_at_k_vs_own_brute": round(sum(row["pg_ann_set_vs_own_brute"]
                                               for row in per_query) / (len(per_query) * K), 4),
        "legacy_hnsw_at_k_vs_own_brute": round(sum(row["legacy_ann_set_vs_own_brute"]
                                                   for row in per_query) / (len(per_query) * K), 4),
        "pg_hnsw_exact_order_queries": sum(1 for row in per_query
                                           if row["pg_ann_equals_own_brute"]),
        "legacy_hnsw_exact_order_queries": sum(1 for row in per_query
                                               if row["legacy_ann_equals_own_brute"]),
        "brute_force_agreement_queries": sum(1 for row in per_query
                                             if row["cross_engine_brute_identical"]),
        "queries": len(per_query), "k": K,
    }
    report["ann_latency_ms"] = {arm: stats(samples) for arm, samples in ann_latency.items()}

    # ---- hot-set leg, both states, with a predicate the legacy corpus can satisfy ----
    from app.rag import hot_index, indexing
    from app.rag.retriever import DocumentRetriever as RetrieverClass

    hot = {}
    for backend in ("chroma", "pgvector"):
        os.environ["INDEX_BACKEND"] = backend
        os.environ["HOT_INDEX_ENABLED"] = "on"
        assert indexing.read_backend() == backend
        hot_index.reset_hot_index_diagnostics()
        instance = RetrieverClass(chroma_dir=os.getenv("R382_CHROMA_DIR", "/work/chroma_db"))
        query_texts = [row["query"] for row in per_query]
        probe_vector = embedder.embed_query(query_texts[0])
        warm, warm_ms = timed(lambda: instance._hot_hits(probe_vector, K, None, None))
        timings = []
        served = []
        for query in query_texts:
            vector = embedder.embed_query(query)
            result, took = timed(lambda: instance._hot_hits(vector, K, None, None))
            timings.append(took)
            served.append(None if result is None else len(result))
        hot[backend] = {
            "warm_call_ms": warm_ms, "warm_returned": None if warm is None else len(warm),
            "per_call_ms": timings, "served_hits": served,
            "median_ms": stats(timings)["median"], "max_ms": stats(timings)["max"],
            "diagnostics_after": hot_index.hot_index_diagnostics(),
        }
        os.environ.pop("HOT_INDEX_ENABLED", None)
    os.environ.pop("INDEX_BACKEND", None)
    report["hot_leg"] = hot

    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    out = os.getenv("R382_JSON_OUT", "/work/out/r382_parity.json")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    print(f"full document at {out} ({len(payload)} bytes)")
    print(json.dumps({key: report[key] for key in ("corpus", "vector_parity", "recall",
                                                   "ann_latency_ms", "hot_leg")},
                     ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())