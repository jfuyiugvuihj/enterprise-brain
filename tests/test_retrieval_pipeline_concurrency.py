from concurrent.futures import ThreadPoolExecutor
import sys


def test_unavailable_pg_is_not_an_empty_knowledge_base():
    import pytest
    from app.rag.retrieval_pipeline import RetrievalPipeline
    from app.rag.retriever import OllamaEmbeddings

    # conftest 指向不可连接的 PostgreSQL；实际连接失败，不能冒充零召回。
    pipeline = RetrievalPipeline()
    pipeline.semantic.retriever.embedding = OllamaEmbeddings(base_url="http://127.0.0.1:1")
    with pytest.raises(RuntimeError, match="retrieval_unavailable"):
        pipeline.search("报销材料", tier="fast")


def test_bm25_search_serializes_first_index_build(monkeypatch):
    from app.rag.retrieval_pipeline import BM25Searcher

    monkeypatch.setattr("app.rag.pg_store.switched_corpus", lambda: {
        "documents": ["报销流程需要提交申请", "差旅费标准按城市执行"],
        "metadatas": [{"filename": "policy.txt"}, {"filename": "travel.txt"}],
    })

    searcher = BM25Searcher()
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(searcher.search, ["报销流程"] * 5))

    assert len(results) == 5
    assert all(isinstance(result, list) for result in results)
    assert len(searcher.corpus) == len(searcher.documents) == 2


def test_bm25_search_falls_back_when_jieba_is_unavailable(monkeypatch):
    """jieba 不可用时关键词检索仍要给出结果。

    语料刻意造到五篇：rank_bm25 的 idf = log(N-df+0.5) - log(df+0.5)，两篇文档
    且每个词只命中其一时 idf 恒为 0，整份得分一起归零，那样测的就不是回退分词
    而是 idf 公式本身。
    """
    from app.rag.retrieval_pipeline import BM25Searcher, _tokenize_text

    docs = [
        ("报销流程需要提交申请单并附发票", "policy.txt"),
        ("差旅费标准按城市分级执行", "travel.txt"),
        ("月度经营分析会在每月初召开", "meeting.txt"),
        ("客户回访记录需要填写到系统", "crm.txt"),
        ("固定资产盘点每年进行一次", "assets.txt"),
    ]

    monkeypatch.setattr("app.rag.pg_store.switched_corpus", lambda: {
        "documents": [content for content, _ in docs],
        "metadatas": [{"filename": name} for _, name in docs],
    })
    # None 占位让 import jieba 抛 ImportError 而不是 ModuleNotFoundError，
    # 回退分支必须两种导入失败都挡住。
    monkeypatch.setitem(sys.modules, "jieba", None)

    assert _tokenize_text("报销流程") == ["报", "销", "流", "程"]

    results = BM25Searcher().search("报销流程")

    assert results
    assert results[0]["source"] == "policy.txt"
