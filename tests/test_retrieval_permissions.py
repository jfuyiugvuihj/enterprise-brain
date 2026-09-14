from app.common.identity import Principal
from app.rag.filters import RetrievalScopeError, build_document_retrieval_filter


def test_document_retrieval_filter_limits_classification_and_department_before_query():
    principal = Principal(
        user_id="u-1",
        username="alice",
        permissions=["document.read"],
        department="finance",
        department_ids=["shared-services"],
        clearance=2,
    )

    where = build_document_retrieval_filter(principal)

    assert where == {
        "$and": [
            {"classification": {"$in": [1, 2]}},
            {"department": {"$in": ["finance", "shared-services"]}},
        ]
    }


def test_document_retrieval_filter_rejects_missing_principal_or_department_scope():
    try:
        build_document_retrieval_filter(None)
    except RetrievalScopeError as exc:
        assert exc.code == "authentication_required"
    else:
        raise AssertionError("anonymous retrieval must be rejected")

    principal = Principal(
        user_id="u-1",
        username="alice",
        permissions=["document.read"],
        clearance=2,
    )
    try:
        build_document_retrieval_filter(principal)
    except RetrievalScopeError as exc:
        assert exc.code == "authorization_unavailable"
    else:
        raise AssertionError("unscoped retrieval must be rejected")


def test_document_retrieval_filter_rejects_inactive_or_zero_clearance_principals():
    inactive = Principal(
        user_id="u-1",
        username="alice",
        permissions=["document.read"],
        department="finance",
        clearance=2,
        status="disabled",
    )
    zero_clearance = Principal(
        user_id="u-2",
        username="bob",
        permissions=["document.read"],
        department="finance",
        clearance=0,
    )

    for principal, expected_code in (
        (inactive, "permission_denied"),
        (zero_clearance, "authorization_unavailable"),
    ):
        try:
            build_document_retrieval_filter(principal)
        except RetrievalScopeError as exc:
            assert exc.code == expected_code
        else:
            raise AssertionError("invalid principal scope must be rejected")


def test_principal_aware_pipeline_scopes_semantic_and_bm25_recall():
    from app.rag.retrieval_pipeline import RetrievalPipeline

    class Semantic:
        def __init__(self):
            self.where = None

        def search(self, query, k, where):
            self.where = where
            return [
                {
                    "content": "finance policy",
                    "classification": 2,
                    "department": "finance",
                }
            ]

    class BM25:
        def __init__(self):
            self.pred = None

        def search(self, query, k, pred):
            self.pred = pred
            docs = [
                {
                    "content": "finance policy",
                    "classification": 2,
                    "department": "finance",
                },
                {
                    "content": "hr policy",
                    "classification": 1,
                    "department": "hr",
                },
                {
                    "content": "secret finance policy",
                    "classification": 3,
                    "department": "finance",
                },
            ]
            return [doc for doc in docs if pred(doc)]

    class Rewriter:
        @staticmethod
        def rewrite(query):
            return {"rewrites": [], "sub_questions": []}

    class Reranker:
        @staticmethod
        def rerank(query, docs, top_k):
            return docs[:top_k]

    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    pipeline.semantic = Semantic()
    pipeline.bm25 = BM25()
    pipeline.rewriter = Rewriter()
    pipeline.reranker = Reranker()
    principal = Principal(
        user_id="u-1",
        username="alice",
        permissions=["document.read"],
        department="finance",
        clearance=2,
    )

    docs, rewrites = pipeline.search_for_principal("policy", principal, top_k=5)

    assert pipeline.semantic.where == {
        "$and": [
            {"classification": {"$in": [1, 2]}},
            {"department": {"$in": ["finance"]}},
        ]
    }
    assert pipeline.bm25.pred is not None
    assert docs == [
        {
            "content": "finance policy",
            "classification": 2,
            "department": "finance",
        }
    ]
    assert rewrites == []


def test_principal_aware_pipeline_rejects_anonymous_before_recall():
    from app.rag.retrieval_pipeline import RetrievalPipeline

    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)

    try:
        pipeline.search_for_principal("policy", None)
    except RetrievalScopeError as exc:
        assert exc.code == "authentication_required"
    else:
        raise AssertionError("anonymous retrieval must be rejected before recall")
