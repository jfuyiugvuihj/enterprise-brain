"""查询改写档位：fast 档一次检索必须 0 次大模型往返。

打桩替换的是 ``app.rag.retrieval_pipeline.model``（模块级 ``ModelHandler()``），
断言的是它的 chat 被调用了几次，而不是返回值长什么样。测试不连 Ollama、不建
Chroma 集合、不读写 chroma_db。
"""
import json

import pytest

from app.common.identity import Principal
from app.rag import retrieval_pipeline

TIER_ENV = retrieval_pipeline.TIER_ENV
QUERY = "员工出差住宿和餐费的报销标准是多少，超标之后找谁审批"
REWRITES = ["差旅报销标准", "住宿费的报销上限", "餐费报销规则"]
SUB_QUESTIONS = ["出差住宿标准是多少", "超标准报销如何审批"]


class _CountingModel:
    """记录每一次 chat 调用的桩模型：真实推理一次都不该发生。"""

    def __init__(self):
        self.calls = []

    def chat(self, messages=None, source=None, stream=True, **kwargs):
        self.calls.append({"messages": messages, "source": source, "stream": stream})
        return json.dumps(
            {"rewrites": list(REWRITES), "sub_questions": list(SUB_QUESTIONS)},
            ensure_ascii=False,
        )

    @property
    def roundtrips(self):
        return len(self.calls)


class _RecordingSemantic:
    """语义召回桩：签名对齐 SemanticSearcher.search，只记录跑过哪些 query。"""

    def __init__(self):
        self.queries = []
        self.wheres = []

    def search(self, query, k=10, where=None):
        self.queries.append(query)
        self.wheres.append(where)
        return []


class _RecordingBM25:
    """BM25 召回桩：签名对齐 BM25Searcher.search。"""

    def __init__(self):
        self.queries = []
        self.preds = []

    def search(self, query, k=10, pred=None):
        self.queries.append(query)
        self.preds.append(pred)
        return []


class _NoopReranker:
    """本地 Cross-Encoder 桩：档位只管改写，重排这一步不该被动到。"""

    def rerank(self, query, docs, top_k=5):
        return docs[:top_k]


def _pipeline():
    """绕开 ``__init__``（它会连 Chroma），但保留真·QueryRewriter。

    rewriter 必须用实现本身而不是桩：只有它真的跑起来，model 的调用计数才能
    证明"改写发生过"或"改写确实被跳过了"。
    """
    pipeline = retrieval_pipeline.RetrievalPipeline.__new__(retrieval_pipeline.RetrievalPipeline)
    pipeline.semantic = _RecordingSemantic()
    pipeline.bm25 = _RecordingBM25()
    pipeline.reranker = _NoopReranker()
    pipeline.rewriter = retrieval_pipeline.QueryRewriter()
    return pipeline


def _stub_model(monkeypatch):
    fake = _CountingModel()
    monkeypatch.setattr(retrieval_pipeline, "model", fake)
    return fake


def test_fast_tier_makes_zero_llm_roundtrips(monkeypatch):
    fake = _stub_model(monkeypatch)
    monkeypatch.setenv(TIER_ENV, "fast")

    docs, rewrites = _pipeline().search(QUERY)

    assert fake.roundtrips == 0
    assert rewrites == []
    assert docs == []


def test_fast_tier_still_runs_both_recall_paths_on_the_original_query(monkeypatch):
    fake = _stub_model(monkeypatch)
    monkeypatch.setenv(TIER_ENV, "fast")
    pipeline = _pipeline()

    pipeline.search(QUERY)

    assert pipeline.semantic.queries == [QUERY]
    assert pipeline.bm25.queries == [QUERY]


def test_default_tier_without_env_keeps_rewriting(monkeypatch):
    fake = _stub_model(monkeypatch)
    monkeypatch.delenv(TIER_ENV, raising=False)
    pipeline = _pipeline()

    docs, rewrites = pipeline.search(QUERY)

    assert fake.roundtrips >= 1
    assert rewrites == REWRITES
    assert pipeline.semantic.queries[0] == QUERY
    assert len(pipeline.semantic.queries) == 5


def test_fast_tier_via_explicit_argument_beats_unset_env(monkeypatch):
    fake = _stub_model(monkeypatch)
    monkeypatch.delenv(TIER_ENV, raising=False)

    _pipeline().search(QUERY, tier="fast")

    assert fake.roundtrips == 0


def test_explicit_full_tier_overrides_fast_env(monkeypatch):
    fake = _stub_model(monkeypatch)
    monkeypatch.setenv(TIER_ENV, "fast")

    _pipeline().search(QUERY, tier="full")

    assert fake.roundtrips >= 1


def test_misspelled_tier_still_rewrites(monkeypatch):
    """拼错开关不等于关掉改写：档位不认识时必须保持现状。"""
    fake = _stub_model(monkeypatch)
    monkeypatch.setenv(TIER_ENV, "fastt")

    _pipeline().search(QUERY)

    assert fake.roundtrips >= 1


def test_search_for_principal_inherits_tier_without_caller_changes(monkeypatch):
    """tools.py / debug.py 一个参数都没传，也只靠环境变量就能整条链路分档。"""
    fake = _stub_model(monkeypatch)
    monkeypatch.setenv(TIER_ENV, "fast")
    principal = Principal(
        user_id="u-1",
        username="alice",
        permissions=["document.read"],
        department="finance",
        clearance=2,
    )

    docs, rewrites = _pipeline().search_for_principal(QUERY, principal, top_k=5)

    assert fake.roundtrips == 0
    assert rewrites == []
    assert docs == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("fast", "fast"),
        ("  FAST\n", "fast"),
        ("off", "fast"),
        ("adaptive", "adaptive"),
        ("full", "full"),
        ("standard", "full"),
        ("", "full"),
        ("   ", "full"),
        ("fsat", "full"),
        ("fas", "full"),
        ("quict", "full"),
        ("false", "full"),
        ("0", "full"),
        ("改写关闭", "full"),
    ],
)
def test_tier_resolution_is_conservative(monkeypatch, raw, expected):
    monkeypatch.setenv(TIER_ENV, raw)

    assert retrieval_pipeline.resolve_rewrite_tier() == expected


class _Unreadable:
    def __str__(self):
        raise RuntimeError("这个配置值连字符串都读不出来")


def test_unreadable_or_wrong_type_tier_is_conservative(monkeypatch):
    monkeypatch.delenv(TIER_ENV, raising=False)

    assert retrieval_pipeline.resolve_rewrite_tier(_Unreadable()) == "full"
    assert retrieval_pipeline.resolve_rewrite_tier(123) == "full"
    assert retrieval_pipeline.should_rewrite_query(QUERY, _Unreadable()) is True


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("报销标准", False),
        ("住宿费？", False),
        ("住宿费？餐费？", True),
        ("", False),
        (QUERY, True),
    ],
)
def test_adaptive_rewrite_condition(query, expected):
    assert retrieval_pipeline._looks_multi_intent(query) is expected


def test_adaptive_tier_skips_rewrite_for_single_intent_queries(monkeypatch):
    fake = _stub_model(monkeypatch)
    monkeypatch.setenv(TIER_ENV, "adaptive")

    _pipeline().search("报销标准")

    assert fake.roundtrips == 0


def test_adaptive_tier_rewrites_multi_intent_queries(monkeypatch):
    fake = _stub_model(monkeypatch)
    monkeypatch.setenv(TIER_ENV, "adaptive")

    _pipeline().search(QUERY)

    assert fake.roundtrips >= 1
