from app.common.identity import Principal
from app.rag.filters import RetrievalScopeError, build_document_retrieval_filter


def test_exclusive_document_request_excludes_other_sources_without_widening_permissions():
    from app.rag.filters import resolve_document_retrieval_scope
    from app.rag.retrieval_pipeline import document_query_predicate

    principal = Principal(user_id="finance", username="finance", department="finance", clearance=2)
    scope = resolve_document_retrieval_scope(principal)
    allowed = {"source": "现行制度.pdf", "department": "finance", "classification": 1}
    predicate = document_query_predicate("只依据文件【现行制度.pdf】回答：600元谁审批？", scope)
    assert predicate(allowed)
    assert not predicate({**allowed, "source": "费用.csv"})
    assert not predicate({**allowed, "department": "sales"})
    assert not predicate({**allowed, "classification": 3})
    assert not document_query_predicate("只查【不存在.pdf】", scope)(allowed)
    assert document_query_predicate("仅依据【现行制度.pdf】【旧制度.pdf】比较版本", scope)(allowed)
    assert document_query_predicate("查询公司的报销制度", scope)({**allowed, "source": "费用.csv"})


def test_selected_document_scope_does_not_expand_when_question_mentions_another_file():
    from app.rag.retrieval_pipeline import requested_document_names
    assert requested_document_names('仅依据以下文件《A.pdf》《B.txt》回答：\n与《C.pdf》相比有哪些已知限制？') == frozenset({'A.pdf', 'B.txt'})


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
