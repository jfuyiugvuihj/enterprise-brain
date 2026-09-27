"""R382 cell 1: in-process end-to-end read-path measurement, pgvector leg vs chroma leg.

Read-only by construction: it attaches to the R59 sandbox database, refuses to run
against anything else, and opens the legacy engine from a *copy* of the Chroma volume.
The switch is moved with os.environ inside this process only -- no .env file, no
default value, no deployment is touched.

Output: one JSON document with per-query rows, per-principal permission evidence,
latency samples, and the diagnostics counters that say which engine answered.
"""
from __future__ import annotations

import json
import os
import sys
import time

SANDBOX_DB = "eb_r59_sandbox"
TOP_K = 5

#: Realistic questions over the corpus the sandbox actually holds (production business
#: documents, synthetic department/classification labels). They must be answerable from
#: this library and must not all land in one cell.
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

#: (name, department, clearance). The sandbox labels are sales=1 / engineering=2 /
#: finance=3 / hr=4, 252 chunks each, so "hr + clearance 1" is satisfiable by nothing:
#: it is the probe that tells us the classification predicate binds on its own and the
#: result is not merely the department filter doing all the work.
PRINCIPALS = [
    ("sales-c1", "sales", 1),
    ("engineering-c2", "engineering", 2),
    ("finance-c3", "finance", 3),
    ("hr-c4", "hr", 4),
    ("sales-c2", "sales", 2),
    ("hr-c1-impossible", "hr", 1),
]


def mask(url: str) -> str:
    if "@" not in url:
        return "<unset>"
    head, tail = url.split("@", 1)
    return (head.rsplit(":", 1)[0] + ":***@" + tail) if ":" in head else "*@" + tail


def make_principal(department: str, clearance: int):
    from app.common.identity import Principal

    return Principal(
        user_id=f"r382-{department}-c{clearance}", username=f"r382-{department}",
        roles=["user"], permissions=[], department=department, department_ids=[],
        clearance=clearance, status="active",
    )


def database_identity(url: str) -> dict:
    from app.db.connection import open_connection, parse_database_settings

    with open_connection(parse_database_settings(url)) as conn:
        row = conn.execute("SELECT current_database() AS db, current_user AS usr").fetchone()
        count = conn.execute("SELECT count(*) FROM chunk_vectors").fetchone()[0]
    return {"db": row[0], "usr": row[1], "vectors": count}


def leg_rows_pg(query_vector, k, where):
    """Store-level pgvector top-k: id + distance, straight from the read leg."""
    from app.rag import pg_store

    rows = pg_store.read_topk(query_vector=query_vector, k=k, where=where)
    return [{
        "id": str(row["vector_id"]),
        "distance": round(float(row["distance"]), 6),
        "department": row.get("department") or "",
        "classification": row.get("classification"),
        "server": "pgvector",
    } for row in rows]


def leg_rows_chroma(collection, query_vector, k, where):
    """Store-level legacy top-k, same shape, for attribution only."""
    kwargs = {"query_embeddings": [query_vector], "n_results": k,
              "include": ["metadatas", "distances"]}
    if where:
        kwargs["where"] = where
    result = collection.query(**kwargs)
    ids = (result.get("ids") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    return [{
        "id": str(chunk_id),
        "distance": round(float(distance), 6),
        "department": (meta or {}).get("department") or "",
        "classification": (meta or {}).get("classification"),
        "server": "chroma",
    } for chunk_id, distance, meta in zip(ids, distances, metas)]


def brief(rows):
    return [{"id": row["id"], "distance": row["distance"]} for row in rows]


def overlap(left, right):
    left_ids = [row["id"] for row in left]
    right_ids = [row["id"] for row in right]
    shared = [chunk_id for chunk_id in left_ids if chunk_id in set(right_ids)]
    return {
        "pg_only": [c for c in left_ids if c not in set(right_ids)],
        "chroma_only": [c for c in right_ids if c not in set(left_ids)],
        "shared": len(shared),
        "overlap_ratio": round(len(shared) / max(1, len(set(left_ids) | set(right_ids))), 4),
        "exact_position_match": sum(1 for a, b in zip(left_ids, right_ids) if a == b),
    }


def permission_check(rows, principal, scope) -> dict:
    """Every returned row must sit inside the caller's scope, on both axes."""
    violations = []
    for row in rows:
        level = row.get("classification")
        department = str(row.get("department") or "")
        if level not in scope.classification_levels:
            violations.append({**row, "why": "classification_out_of_levels"})
        elif scope.departments is not None and department not in scope.departments:
            violations.append({**row, "why": "department_out_of_scope"})
    return {
        "principal": principal,
        "levels": sorted(scope.classification_levels),
        "departments": (sorted(scope.departments) if scope.departments is not None else None),
        "returned": len(rows),
        "violations": violations,
    }


def hot_index_snapshot() -> dict:
    from app.rag import hot_index

    return {"diagnostics": hot_index.hot_index_diagnostics(),
            "enabled": hot_index.hot_index_enabled(),
            "env": os.getenv("HOT_INDEX_ENABLED", "<unset>")}


def run_leg(backend: str, vectors: dict, chroma_collection, report: dict) -> None:
    from app.rag import indexing, pg_store, retriever as retriever_module
    from app.rag.filters import resolve_document_retrieval_scope
    from app.rag.retrieval_pipeline import RetrievalPipeline

    os.environ["INDEX_BACKEND"] = backend
    assert indexing.read_backend() == backend, "the in-process switch did not take"

    pg_store.reset_vector_read_diagnostics()
    pg_store.reset_vector_corpus_diagnostics()
    retriever_module.reset_search_shape()
    started_build = time.perf_counter()
    pipeline = RetrievalPipeline()
    pipeline.bm25.build_index()
    build_seconds = round(time.perf_counter() - started_build, 3)
    corpus = pg_store.vector_corpus_diagnostics()

    leg = {"backend": backend, "pipeline_build_seconds": build_seconds,
           "corpus_diagnostics": corpus, "end_to_end": [], "permission": []}

    for index, query in enumerate(QUERIES, start=1):
        started = time.perf_counter()
        hits, rewrites = pipeline.search_for_principal(query, make_principal("sales", 4),
                                                       top_k=TOP_K, tier="fast")
        elapsed = round(time.perf_counter() - started, 4)
        shape = retriever_module.search_shape_diagnostics()
        leg["end_to_end"].append({
            "n": index, "query": query, "principal": "sales-c4",
            "seconds": elapsed, "hits": len(hits), "rewrites": len(rewrites or []),
            "ids": [f"{h.get('source')}_{h.get('chunk_index')}" for h in hits],
            "scores": [h.get("_score") for h in hits],
            "answered_by": (shape.get("last") or {}).get("answered_by"),
            "legs_seen": shape.get("answered_by"),
        })

    for name, department, clearance in PRINCIPALS:
        principal = make_principal(department, clearance)
        scope = resolve_document_retrieval_scope(principal)
        rows_pg = []
        rows_chroma = []
        seconds = []
        end_to_end = []
        for query in QUERIES:
            started = time.perf_counter()
            hits, _ = pipeline.search_for_principal(query, principal, top_k=TOP_K,
                                                    tier="fast")
            seconds.append(round(time.perf_counter() - started, 4))
            end_to_end.append({
                "query": query,
                "ids": [f"{h.get('source')}_{h.get('chunk_index')}" for h in hits],
                "scores": [h.get("_score") for h in hits],
                "labels": [(h.get("department"), h.get("classification")) for h in hits],
            })
            rows_pg.extend(leg_rows_pg(vectors[query], TOP_K, scope.filters))
            rows_chroma.extend(leg_rows_chroma(chroma_collection, vectors[query],
                                               TOP_K, scope.filters))
        leg["permission"].append({
            "name": name, "department": department, "clearance": clearance,
            "filters": scope.filters, "reason_code": scope.reason_code,
            "pg_store_level": permission_check(rows_pg, name, scope),
            "chroma_store_level": permission_check(rows_chroma, name, scope),
            "pg_pairwise": [{"query": q, "pg": brief(a), "chroma": brief(b),
                             "diff": overlap(a, b)}
                            for q, a, b in zip(QUERIES,
                                               [rows_pg[i * TOP_K:(i + 1) * TOP_K]
                                                for i in range(len(QUERIES))],
                                               [rows_chroma[i * TOP_K:(i + 1) * TOP_K]
                                                for i in range(len(QUERIES))])],
            "end_to_end_seconds_max": max(seconds),
            "end_to_end_seconds_median": sorted(seconds)[len(seconds) // 2],
            "end_to_end": end_to_end,
        })

    leg["read_diagnostics"] = pg_store.vector_read_diagnostics()
    leg["hot_index"] = hot_index_snapshot()
    report["legs"][backend] = leg


def measure_hot_handoff(vectors: dict, report: dict) -> None:
    """Cell 2 (opportunistic): latency of the hot-set leg before and after the switch."""
    from app.rag import hot_index, indexing
    from app.rag.retriever import DocumentRetriever

    samples = {}
    for backend in ("chroma", "pgvector"):
        os.environ["INDEX_BACKEND"] = backend
        os.environ["HOT_INDEX_ENABLED"] = "on"
        assert indexing.read_backend() == backend
        hot_index.reset_hot_index_diagnostics()
        instance = DocumentRetriever(chroma_dir=os.getenv("R382_CHROMA_DIR", "/work/chroma_db"))
        where = {"department": {"$in": ["sales", "engineering", "finance", "hr"]}}
        timings = []
        served = []
        for query in QUERIES:
            started = time.perf_counter()
            hits = instance._hot_hits(vectors[query], TOP_K, where, None)
            timings.append(round((time.perf_counter() - started) * 1000, 3))
            served.append(None if hits is None else len(hits))
        samples[backend] = {
            "total_ms": round(sum(timings), 3), "per_query_ms": timings,
            "max_ms": max(timings), "median_ms": sorted(timings)[len(timings) // 2],
            "hits_served": served,
            "diagnostics_after": hot_index.hot_index_diagnostics(),
            "snapshot": hot_index_snapshot(),
        }
        os.environ.pop("HOT_INDEX_ENABLED", None)
    report["hot_handoff"] = samples


def main() -> int:
    url = os.getenv("DATABASE_URL", "")
    report = {"pairwise": [], "legs": {}, "env": {
        "python": sys.executable, "cwd": os.getcwd(),
        "database_url": mask(url), "chroma_dir": os.getenv("R382_CHROMA_DIR"),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL"),
        "vector_dual_write": os.getenv("VECTOR_DUAL_WRITE"),
        "index_backend_env_at_entry": os.getenv("INDEX_BACKEND", "<unset>"),
        "host_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }}

    identity = database_identity(url)
    report["database_identity"] = identity
    if identity["db"] != SANDBOX_DB:
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        print(f"ABORT: attached to {identity['db']!r}", file=sys.stderr)
        return 2

    from app.rag import indexing
    from app.rag.retriever import DocumentRetriever, EmbeddingError, OllamaEmbeddings

    report["env"]["read_backend_shipped_default"] = indexing.read_backend()
    instance = DocumentRetriever(chroma_dir=os.getenv("R382_CHROMA_DIR", "/work/chroma_db"))
    report["env"]["chromadb_present"] = instance.stores_vectors

    embedder = OllamaEmbeddings()
    vectors = {}
    embed_seconds = []
    for query in QUERIES:
        started = time.perf_counter()
        try:
            vectors[query] = embedder.embed_query(query)
        except EmbeddingError as exc:
            report["embedding_block"] = {"query": query, "reason": exc.reason,
                                         "detail": str(exc)[:300]}
            print(json.dumps(report, ensure_ascii=False, indent=2))
            print(f"BLOCKED: embedding unreachable ({exc.reason})", file=sys.stderr)
            return 3
        embed_seconds.append(round(time.perf_counter() - started, 4))
    report["embedding"] = {
        "model": embedder.model, "api_url": embedder.api_url,
        "count": len(vectors),
        "dimension": sorted({len(v) for v in vectors.values()}),
        "seconds_each": embed_seconds, "seconds_total": round(sum(embed_seconds), 3),
        "all_nonzero": all(any(abs(float(x)) > 0 for x in v) for v in vectors.values()),
    }
    report["env"]["read_backend_after_embedding"] = indexing.read_backend()

    for backend in ("pgvector", "chroma"):
        run_leg(backend, vectors, instance.collection, report)

    measure_hot_handoff(vectors, report)
    report["env"]["read_backend_at_exit"] = indexing.read_backend()
    os.environ.pop("INDEX_BACKEND", None)
    report["env"]["read_backend_after_unsetting"] = indexing.read_backend()

    payload = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    out = os.getenv("R382_JSON_OUT", "/work/out/r382_legs.json")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    print(f"full document at {out} ({len(payload)} bytes)")
    print(json.dumps({"embedding": report["embedding"], "env": report["env"],
                      "legs": {k: {kk: vv for kk, vv in v.items()
                                   if kk in ("corpus_diagnostics", "read_diagnostics",
                                             "pipeline_build_seconds", "hot_index")}
                               for k, v in report["legs"].items()}},
                     ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())