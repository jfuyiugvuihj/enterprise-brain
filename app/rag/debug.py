"""Retrieval debug reports for authorized, versioned inspection."""

from time import perf_counter
from typing import Any

from app.common.identity import Principal
from app.rag.filters import resolve_document_retrieval_scope
from app.rag.retrieval_pipeline import RetrievalPipeline
from app.trace.store import TraceStore


def _debug_result(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": document.get("source", ""),
        "chunk_index": document.get("chunk_index"),
        "classification": document.get("classification"),
        "department": document.get("department", ""),
        "score": document.get("_score"),
        "excerpt": str(document.get("content", ""))[:240],
        "permission_checked": True,
    }


def run_retrieval_debug(
    query: str,
    principal: Principal | None,
    *,
    pipeline: RetrievalPipeline,
    trace_store: TraceStore | None,
    trace_id: str,
    request_id: str,
    index_version_id: str = "",
    strategy_version: str = "",
    top_k: int = 5,
) -> dict[str, Any]:
    """Run an authorized retrieval and return a bounded, replayable debug report."""
    scope = resolve_document_retrieval_scope(principal)
    permission_filter = scope.filters
    started = perf_counter()
    documents, rewrites = pipeline.search_for_principal(
        query,
        principal,
        top_k=top_k,
    )
    duration_ms = round((perf_counter() - started) * 1000, 2)
    results = [_debug_result(document) for document in documents]
    report = {
        "index_version_id": index_version_id,
        "strategy_version": strategy_version,
        "permission_filter": permission_filter,
        # A report that shows the filter but not the rule that widened it is how an
        # administrator override disappears from a review of somebody's question.
        "scope_reason": scope.reason_code,
        "rewrites": rewrites,
        "stages": [
            {
                "name": "permission_filter",
                "candidate_count": len(results),
            },
            {
                "name": "reranked",
                "candidate_count": len(results),
            },
        ],
        "results": results,
        "duration_ms": duration_ms,
    }
    if trace_store is not None:
        trace_store.record_event(
            trace_id=trace_id,
            request_id=request_id,
            event_type="retrieval.completed",
            status="completed",
            payload={
                "index_version_id": index_version_id,
                "strategy_version": strategy_version,
                "permission_filter": permission_filter,
                "scope_reason": scope.reason_code,
                "candidate_count": len(results),
                "duration_ms": duration_ms,
                "sources": [result["source"] for result in results],
            },
        )
    return report
