"""R382: the legacy engine handed back an empty neighbour list for some real queries.

Two independent container runs (r382_leg_compare.py, r382_vector_parity.py) agreed
query-for-query: three of twelve real questions got ZERO rows from the retiring engine,
while that same engine's own brute force over the same vectors returned five and pgvector
answered five every time. This codebase already names that shape -- R158 counts "the store
found no neighbours" apart from "nothing matched" -- so it is worth characterising instead of
folding into one recall percentage.

Read-only. The vectors come from the live embedding model; nothing is written anywhere.
"""
from __future__ import annotations

import json
import os

import numpy as np

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


def main() -> int:
    from app.rag.retriever import DocumentRetriever, OllamaEmbeddings

    retriever = DocumentRetriever(chroma_dir=os.getenv("R382_CHROMA_DIR", "/work/chroma_db"))
    collection = retriever.collection
    embedder = OllamaEmbeddings()
    rows = []
    for index, query in enumerate(QUERIES, start=1):
        vector = embedder.embed_query(query)
        array = np.asarray(vector, dtype=np.float32)
        row = {"n": index, "query": query, "vector_finite": bool(np.isfinite(array).all()),
               "norm": round(float(np.linalg.norm(array)), 4), "by_k": {}, "repeat": [],
               "perturbed": {}}
        for k in (1, 3, 5, 10, 50):
            found = collection.query(query_embeddings=[vector], n_results=k,
                                    include=["distances"])
            ids = (found.get("ids") or [[]])[0]
            distances = (found.get("distances") or [[]])[0]
            row["by_k"][str(k)] = {"returned": len(ids),
                                   "first_distance": round(float(distances[0]), 4)
                                   if len(distances) else None}
        for _ in range(3):
            found = collection.query(query_embeddings=[vector], n_results=5)
            row["repeat"].append(len((found.get("ids") or [[]])[0]))
        for scale in (0.999, 1.001, 1.01):
            nudged = (array * scale).astype(np.float32).tolist()
            found = collection.query(query_embeddings=[nudged], n_results=5)
            row["perturbed"][str(scale)] = len((found.get("ids") or [[]])[0])
        rows.append(row)
    report = {"chroma_dir": os.getenv("R382_CHROMA_DIR", "/work/chroma_db"),
              "count": collection.count(), "metadata": collection.metadata,
              "empty_leg_queries": [row["query"] for row in rows
                                    if row["by_k"]["5"]["returned"] == 0],
              "rows": rows}
    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    out = os.getenv("R382_JSON_OUT", "/work/out/r382_empty_legs.json")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    print(json.dumps({"count": report["count"], "metadata": report["metadata"],
                      "empty_leg_queries": report["empty_leg_queries"]},
                     ensure_ascii=False, indent=2))
    for row in rows:
        print(row["n"], row["query"][:24], "by_k",
              {k: value["returned"] for k, value in row["by_k"].items()},
              "first", {k: value["first_distance"] for k, value in row["by_k"].items()},
              "repeat", row["repeat"], "perturbed", row["perturbed"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())