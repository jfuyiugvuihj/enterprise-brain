"""R382: attribute the top-k disagreement between the two engines to a distance metric.

vector_scope declares one embedding profile for the mirror: nomic-embed-text / 768 / l2.
The legacy collection was created without an explicit space, so whichever default the
shipped engine applies is what today's answers are actually ranked by. If the two differ,
then flipping INDEX_BACKEND changes ranking semantics for every answer, and the diff set is
a metric decision rather than an index defect. This script settles it by brute force: exact
KNN under three operators, compared against what the legacy engine returns.

Read-only: SELECT with ORDER BY, no writes, no DDL, no index changes.
"""
from __future__ import annotations

import json
import os
import statistics

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

OPERATORS = {"l2": "<->", "cosine": "<=>", "inner_product": "<#>"}


def exact_knn(connection, vector_literal, operator):
    sql = (f"SELECT vector_id, embedding {operator} %s::vector AS distance "
           "FROM chunk_vectors ORDER BY embedding " + operator + " %s::vector LIMIT %s")
    return [(row[0], float(row[1])) for row in connection.execute(
        sql, (vector_literal, vector_literal, K)).fetchall()]


def main() -> int:
    import psycopg

    from app.rag import pg_store
    from app.rag.retriever import DocumentRetriever, OllamaEmbeddings

    url = os.getenv("DATABASE_URL", "")
    with psycopg.connect(url) as conn:
        db = conn.execute("SELECT current_database()").fetchone()[0]
    if db != SANDBOX_DB:
        raise SystemExit(f"ABORT: attached to {db!r}")

    embedder = OllamaEmbeddings()
    retriever = DocumentRetriever(chroma_dir=os.getenv("R382_CHROMA_DIR", "/work/chroma_db"))
    collection = retriever.collection

    report = {"database": db, "queries": len(QUERIES), "k": K, "rows": [],
              "agreement": {}}
    with psycopg.connect(url) as conn:
        conn.execute("SET enable_indexscan = off")
        conn.execute("SET enable_indexonlyscan = off")
        norms = conn.execute(
            "SELECT min(vector_norm(embedding)) AS lo, max(vector_norm(embedding)) AS hi, "
            "avg(vector_norm(embedding)) AS avg, stddev(vector_norm(embedding)) AS sd "
            "FROM chunk_vectors").fetchone()
        report["stored_vector_norms"] = {
            "min": float(norms[0]), "max": float(norms[1]),
            "mean": float(norms[2]), "stdev": float(norms[3]),
            "unit_norm_count": conn.execute(
                "SELECT count(*) FROM chunk_vectors "
                "WHERE abs(vector_norm(embedding) - 1.0) < 1e-6").fetchone()[0],
            "reading": "nomic-embed-text vectors are NOT unit-norm, so cosine and L2 order "
                       "the same library differently; that is arithmetic, not a defect",
        }
        query_norms = []
        for index, query in enumerate(QUERIES, start=1):
            vector = embedder.embed_query(query)
            literal = pg_store._vector_literal(vector)
            query_norms.append(float(conn.execute(
                "SELECT vector_norm(%s::vector)", (literal,)).fetchone()[0]))
            chroma_result = collection.query(query_embeddings=[vector], n_results=K,
                                            include=["distances"])
            chroma_ids = [str(item) for item in (chroma_result.get("ids") or [[]])[0]]
            chroma_distances = [float(item) for item in
                                (chroma_result.get("distances") or [[]])[0]]
            arms = {name: exact_knn(conn, literal, operator)
                    for name, operator in OPERATORS.items()}
            row = {"n": index, "query": query, "chroma_ids": chroma_ids,
                   "chroma_distances": [round(d, 6) for d in chroma_distances],
                   "exact": {name: [{"id": item[0], "distance": round(item[1], 6)}
                                    for item in value] for name, value in arms.items()},
                   "matches": {name: len(set(chroma_ids) & {item[0] for item in value})
                               for name, value in arms.items()},
                   "identical_order": {name: chroma_ids == [item[0] for item in value]
                                       for name, value in arms.items()}}
            report["rows"].append(row)
        report["query_vector_norms"] = {"min": min(query_norms), "max": max(query_norms),
                                        "mean": statistics.fmean(query_norms)}
    report["agreement"] = {
        name: {"set_overlap_total": sum(row["matches"][name] for row in report["rows"]),
               "max_possible": len(QUERIES) * K,
               "order_identical_queries": sum(1 for row in report["rows"]
                                              if row["identical_order"][name])}
        for name in OPERATORS}
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    out = os.getenv("R382_JSON_OUT", "/work/out/r382_metric.json")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    print(f"full document at {out} ({len(payload)} bytes)")
    print(json.dumps({"agreement": report["agreement"],
                      "stored_vector_norms": report["stored_vector_norms"],
                      "query_vector_norms": report["query_vector_norms"]},
                     ensure_ascii=False, indent=2))
    print(json.dumps(report["rows"][0], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())