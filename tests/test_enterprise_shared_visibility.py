"""Level-1 enterprise sharing reaches every department; levels 2/3 do not."""
import pytest

from app.agents.contracts import Principal
from app.common.policy import authorization_decision
from app.documents import catalog
from app.rag.filters import build_document_retrieval_filter, resolve_document_retrieval_scope
from app.rag.pg_store import sql_scope_filter


class _Result:
    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _VisibilityConnection:
    """In-memory stand-in for the four tables the visibility transaction touches."""

    def __init__(self, chunk_vectors, chunks_by_version):
        self.vectors = [dict(row) for row in chunk_vectors]
        self.chunks_by_version = chunks_by_version
        self.executed = []
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        lowered = sql.lower()
        if "to_regclass" in lowered:
            table = str(params[0]).split(".")[-1]
            return _Result(row={"table_name": table})
        if "from chunks" in lowered:
            resource_version_id = params[1]
            rows = [
                {"vector_id": vector_id}
                for vector_id in self.chunks_by_version.get(resource_version_id, [])
            ]
            return _Result(rows=rows)
        if "update chunk_vectors" in lowered:
            if "vector_id = any" in lowered:
                selected = set(params[1])
                changed = 0
                for row in self.vectors:
                    if row["vector_id"] in selected:
                        row["visibility"] = params[0]
                        changed += 1
                return _Result(rowcount=changed)
            changed = 0
            for row in self.vectors:
                row["visibility"] = params[0]
                changed += 1
            return _Result(rowcount=changed)
        return _Result(rowcount=1)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _principal(username="alice", department="sales", role="staff") -> Principal:
    return Principal.from_user(
        {"id": username, "username": username, "role": role, "department": department}
    )


def _document(classification=1, department="finance", visibility="enterprise_shared"):
    return {
        "resource_type": "document",
        "resource_id": "doc-1",
        "owner_id": "someone-else",
        "department": department,
        "classification": classification,
        "visibility": visibility,
        "status": "active",
    }


def test_level_one_enterprise_share_is_visible_across_departments():
    decision = authorization_decision(_principal(), _document())

    assert decision.allowed is True
    assert decision.reason_code == "enterprise_shared"


def test_enterprise_sharing_never_publishes_level_two():
    decision = authorization_decision(
        _principal(), _document(classification=2, visibility="enterprise_shared")
    )

    assert decision.allowed is False
    assert decision.reason_code == "clearance_insufficient"


def test_enterprise_sharing_requires_an_assigned_department():
    decision = authorization_decision(
        _principal(department=""), _document()
    )

    assert decision.allowed is False
    assert decision.reason_code == "authorization_unavailable"


def test_retrieval_scope_allows_level_one_enterprise_hits_only():
    scope = resolve_document_retrieval_scope(_principal())

    assert scope.allows({
        "classification": 1, "department": "finance", "visibility": "enterprise_shared"
    }) is True
    assert scope.allows({
        "classification": 1, "department": "finance", "visibility": "private"
    }) is False
    assert scope.allows({
        "classification": 2, "department": "finance", "visibility": "enterprise_shared"
    }) is False
    assert scope.allows({
        "classification": 1, "department": "", "visibility": "enterprise_shared"
    }) is False


def test_the_pg_filter_translates_the_enterprise_or_branch():
    where = build_document_retrieval_filter(_principal(department="finance"))
    clause, params = sql_scope_filter(where)

    assert " OR " in clause
    assert "visibility = ANY" in clause
    assert ["finance"] in params
    assert [1] in params
    assert ["enterprise_shared"] in params


def test_the_catalog_publishes_and_unpublishes_a_level_one_document(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    path = tmp_path / "policy.md"
    path.write_text("policy body", encoding="utf-8")
    principal = _principal(department="finance")
    catalog.record_local_document_version(
        "policy.md", 1, "finance", str(path), 1,
        principal=principal, owner_id="alice", parse_status="ready",
    )

    published = catalog.set_document_visibility("policy.md", "enterprise_shared")
    assert published["visibility"] == "enterprise_shared"
    assert catalog.current_documents()[0]["visibility"] == "enterprise_shared"

    unpublished = catalog.set_document_visibility("policy.md", "private")
    assert unpublished["visibility"] == "private"
    assert catalog.current_documents()[0]["visibility"] == "private"


def test_the_catalog_refuses_enterprise_sharing_of_level_two(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    path = tmp_path / "restricted.md"
    path.write_text("restricted body", encoding="utf-8")
    catalog.record_local_document_version(
        "restricted.md", 2, "finance", str(path), 1,
        principal=_principal(department="finance"), owner_id="alice", parse_status="ready",
    )

    with pytest.raises(catalog.DocumentVisibilityError) as refused:
        catalog.set_document_visibility("restricted.md", "enterprise_shared")

    assert refused.value.code == "enterprise_shared_requires_level_1"


def test_publishing_the_latest_version_leaves_earlier_versions_private(monkeypatch):
    """Visibility follows the version being published, not the filename.

    Publishing v2 must not retroactively publish v1: an earlier revision may carry content
    that was never reviewed for enterprise-wide release.
    """
    connection = _VisibilityConnection(
        chunk_vectors=[
            {"vector_id": "policy.txt|v1#0", "visibility": "private"},
            {"vector_id": "policy.txt|v2#0", "visibility": "private"},
        ],
        chunks_by_version={"policy.txt|v2": ["policy.txt|v2#0"]},
    )
    monkeypatch.setattr(catalog, "_database_available", lambda: True)
    monkeypatch.setattr(catalog, "_require_ready_store", lambda *args, **kwargs: None)
    monkeypatch.setattr(catalog, "_conn", lambda: connection)
    monkeypatch.setattr(
        catalog,
        "latest_document_version",
        lambda filename: {"version": 2, "classification": 1, "department": "finance"},
    )

    published = catalog.set_document_visibility("policy.txt", "enterprise_shared")

    assert published == {"filename": "policy.txt", "version": 2, "visibility": "enterprise_shared"}
    assert connection.committed is True
    by_id = {row["vector_id"]: row["visibility"] for row in connection.vectors}
    assert by_id["policy.txt|v1#0"] == "private"
    assert by_id["policy.txt|v2#0"] == "enterprise_shared"


def test_publishing_an_unindexed_document_is_refused(monkeypatch):
    connection = _VisibilityConnection(
        chunk_vectors=[],
        chunks_by_version={},
    )
    monkeypatch.setattr(catalog, "_database_available", lambda: True)
    monkeypatch.setattr(catalog, "_require_ready_store", lambda *args, **kwargs: None)
    monkeypatch.setattr(catalog, "_conn", lambda: connection)
    monkeypatch.setattr(
        catalog,
        "latest_document_version",
        lambda filename: {"version": 1, "classification": 1, "department": "finance"},
    )

    with pytest.raises(catalog.DocumentVisibilityError) as refused:
        catalog.set_document_visibility("policy.txt", "enterprise_shared")

    assert refused.value.code == "document_not_indexed"
    assert connection.rolled_back is True


def test_the_semantic_leg_keeps_the_visibility_label(monkeypatch):
    """The vector read returns ``visibility``; the hit dictionary must not drop it."""
    from app.rag import indexing, pg_store
    from app.rag.retriever import DocumentRetriever

    monkeypatch.setattr(indexing, "pgvector_reads_enabled", lambda: True)
    monkeypatch.setattr(pg_store, "note_read_answered", lambda count: None)
    monkeypatch.setattr(
        pg_store,
        "read_topk",
        lambda **kwargs: [
            {
                "content": "星河采购单笔上限 8888 元",
                "filename": "policy.md",
                "chunk_index": 0,
                "classification": 1,
                "department": "财务部",
                "visibility": "enterprise_shared",
                "index_version_id": "index-v1",
                "content_sha256": "sha",
            }
        ],
    )
    retriever = object.__new__(DocumentRetriever)
    retriever.collection = None

    hits = retriever._pgvector_hits([0.0, 0.0, 0.0], 5, {}, query="星河采购上限")

    assert hits[0]["visibility"] == "enterprise_shared"


def test_the_bm25_leg_keeps_the_visibility_label(monkeypatch):
    import numpy as np

    from app.rag import retrieval_pipeline
    from app.rag import pg_store

    metadata = {
        "filename": "policy.md",
        "chunk_index": 0,
        "classification": 1,
        "department": "财务部",
        "visibility": "enterprise_shared",
    }

    class _Scorer:
        def __init__(self, corpus):
            pass

        def get_scores(self, tokens):
            return np.array([1.0])

    monkeypatch.setattr(
        pg_store,
        "switched_corpus",
        lambda: {"documents": ["星河采购单笔上限 8888 元"], "metadatas": [dict(metadata)]},
    )
    monkeypatch.setattr(retrieval_pipeline, "BM25Okapi", _Scorer)

    searcher = retrieval_pipeline.BM25Searcher()
    searcher.build_index()

    assert searcher.documents[0]["visibility"] == "enterprise_shared"


def test_revoking_enterprise_sharing_refreshes_the_live_keyword_index(monkeypatch):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.agents import tools
    from app.api.v1 import chat
    from app.rag import pg_store, retrieval_pipeline

    visibility = {"value": "enterprise_shared"}
    monkeypatch.setattr(
        pg_store,
        "switched_corpus",
        lambda: {
            "documents": ["星河采购单笔上限 8888 元"],
            "metadatas": [{
                "filename": "policy.md", "chunk_index": 0, "classification": 1,
                "department": "finance", "visibility": visibility["value"],
            }],
        },
    )
    monkeypatch.setattr(retrieval_pipeline, "BM25Okapi", lambda corpus: object())
    searcher = retrieval_pipeline.BM25Searcher()
    searcher.build_index()
    monkeypatch.setattr(tools, "_search_pipeline", SimpleNamespace(bm25=searcher))
    monkeypatch.setattr(
        chat, "latest_document_version",
        lambda filename: {"filename": filename, "version": 1, "visibility": visibility["value"]},
    )

    def set_visibility(filename, requested):
        visibility["value"] = requested
        return {"filename": filename, "version": 1, "visibility": requested}

    monkeypatch.setattr(chat, "set_document_visibility", set_visibility)
    probe = FastAPI()
    probe.include_router(chat.router, prefix="/api/v1")

    @probe.middleware("http")
    async def attach_principal(request, call_next):
        request.state.principal = _principal("root", "", role="admin")
        return await call_next(request)

    sales_scope = resolve_document_retrieval_scope(_principal("sales", "sales"))
    assert sales_scope.allows(searcher.documents[0])

    response = TestClient(probe).put(
        "/api/v1/documents/policy.md/visibility", json={"visibility": "private"}
    )

    assert response.status_code == 200, response.text
    assert searcher.documents[0]["visibility"] == "private"
    assert not sales_scope.allows(searcher.documents[0])


def test_document_evidence_carries_the_visibility_label():
    from app.agents.evidence import record_document_hits

    bag = {"documents": []}
    record_document_hits(
        bag,
        query="星河采购上限",
        hits=[
            {
                "source": "policy.md",
                "chunk_index": 0,
                "content": "星河采购单笔上限 8888 元",
                "classification": 1,
                "department": "财务部",
                "visibility": "enterprise_shared",
            }
        ],
    )

    assert bag["documents"][0]["metadata"]["visibility"] == "enterprise_shared"


def test_the_source_event_keeps_an_enterprise_shared_document_visible():
    from app.api.v1 import chat

    row = chat._document_source_row(
        "doc",
        {
            "source_type": "document",
            "source_name": "policy.md",
            "source_id": "policy.md#chunk=0",
            "locator": {"chunk_index": 0},
            "metadata": {
                "classification": 1,
                "department": "财务部",
                "visibility": "enterprise_shared",
            },
        },
    )
    scope = resolve_document_retrieval_scope(_principal(department="sales"))

    assert scope.allows(row) is True
