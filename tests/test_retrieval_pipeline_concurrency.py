from concurrent.futures import ThreadPoolExecutor
import sys


def test_bm25_search_serializes_first_index_build(monkeypatch):
    from app.rag.retrieval_pipeline import BM25Searcher

    class FakeCollection:
        def get(self):
            return {
                "documents": ["报销流程需要提交申请", "差旅费标准按城市执行"],
                "metadatas": [
                    {"filename": "policy.txt"},
                    {"filename": "travel.txt"},
                ],
            }

    class FakeRetriever:
        def __init__(self):
            self.collection = FakeCollection()

    monkeypatch.setattr(
        "app.rag.retriever.DocumentRetriever",
        FakeRetriever,
    )

    searcher = BM25Searcher()
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(searcher.search, ["报销流程"] * 5))

    assert len(results) == 5
    assert all(isinstance(result, list) for result in results)
    assert len(searcher.corpus) == len(searcher.documents) == 2


def test_bm25_search_falls_back_when_jieba_is_unavailable(monkeypatch):
    from app.rag.retrieval_pipeline import BM25Searcher

    class FakeCollection:
        def get(self):
            return {
                "documents": ["报销流程需要提交申请", "差旅费标准按城市执行"],
                "metadatas": [
                    {"filename": "policy.txt"},
                    {"filename": "travel.txt"},
                ],
            }

    class FakeRetriever:
        def __init__(self):
            self.collection = FakeCollection()

    monkeypatch.setattr("app.rag.retriever.DocumentRetriever", FakeRetriever)
    monkeypatch.setitem(sys.modules, "jieba", None)

    results = BM25Searcher().search("报销流程")

    assert results
    assert results[0]["source"] == "policy.txt"