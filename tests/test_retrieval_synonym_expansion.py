"""R47 术语/同义词接进改写：纯规则扩展必须真的改到召回，且不新增模型往返。

打桩边界（每处都写清楚，免得被读成"测试自己造了个改进"）：

- 关键词腿用**真** ``BM25Searcher.search`` + **真** ``rank_bm25.BM25Okapi`` + 真分词，语料由
  本文件给定。所以"扩展前召不到、扩展后召得到"是检索自己算出来的，不是桩喂回来的。
- 语义腿是 ``_LiteralSemantic`` 替身：它不模拟向量，只按"query 是否原样出现在正文里"回货。
  它存在的意义是证明扩展 query 同样喂到了第二条腿、``where`` 也一起带了下去。
- 大模型用计数桩替掉 ``retrieval_pipeline.model``：本文件只认它的调用次数。
- 指标目录用真 ``app.semantics.registry``，但把 ``_database_available`` 钉成 False，让它走
  出厂的 code fallback 词表：用例不许依赖测试机上有没有 PostgreSQL。
两条腿的召回是并发提交的，完成顺序不固定，所以本文件一律按集合断言，不咬调用次序。
全程不建 PersistentClient、不打 Ollama、不连库、不写盘。
"""
import json

import pytest

from app.agents.contracts import Principal
from app.rag import retrieval_pipeline
from app.rag.retrieval_pipeline import (
    BM25Searcher,
    MAX_RECALL_QUERIES,
    RetrievalPipeline,
    SYNONYM_EXPANSION_MAX_QUERIES,
)
from app.semantics import registry as registry_module

TIER_ENV = retrieval_pipeline.TIER_ENV

# 只有别名、没有标准名的口语问题：词表里"差旅费/差旅费用"是标准名，"出差"是别名。
ALIAS_QUERY = "出差花了多少钱"
# 命中标准名的写法，用来断言"同形的词不会被再问一遍"。
STANDARD_QUERY = "本月差旅费用合计多少"
# 命不中任何指标定义的问题：扩展必须像没存在过一样。
NEUTRAL_QUERY = "制度第几条写着需要审批"
# 给打桩词表用的短问题（必须短于扩展的字面长度门槛）。
GENERIC_QUERY = "本月预算数是多少"

# 语料：只有 D1 含标准名"差旅费用"，含别名"出差"的是 D2。
D1 = {
    "id": "expense-summary",
    "document": "市场部 2025 年 3 月差旅费用合计 12.4 万元。",
    "metadata": {
        "filename": "expense-summary.xlsx",
        "chunk_index": 0,
        "classification": 1,
        "department": "marketing",
    },
}
D2 = {
    "id": "travel-note",
    "document": "员工出差需要在系统里登记行程。",
    "metadata": {
        "filename": "travel-note.txt",
        "chunk_index": 0,
        "classification": 1,
        "department": "marketing",
    },
}
D3 = {
    "id": "canteen",
    "document": "员工餐费按实际就餐次数结算。",
    "metadata": {
        "filename": "canteen.txt",
        "chunk_index": 0,
        "classification": 1,
        "department": "marketing",
    },
}
D_SECRET = {
    "id": "board-secret",
    "document": "董事会专用：差旅费用明细与预算说明。",
    "metadata": {
        "filename": "board-secret.txt",
        "chunk_index": 0,
        "classification": 4,
        "department": "board",
    },
}
ROWS = [D1, D2, D3, D_SECRET]
OPEN_ROWS = [D1, D2, D3]


# ==================== 测试替身 ====================

class _CountingModel:
    """记录每一次 chat 调用的桩模型：真实推理一次都不该发生。"""

    def __init__(self, payload=None):
        self.calls = []
        self.payload = payload or {
            "rewrites": ["差旅报销标准", "费用合计口径", "支出统计口径"],
            "sub_questions": ["差旅费用是多少", "超标如何审批"],
        }

    def chat(self, messages=None, source=None, stream=True, **kwargs):
        self.calls.append({"messages": messages, "source": source, "stream": stream})
        return json.dumps(self.payload, ensure_ascii=False)

    @property
    def roundtrips(self):
        return len(self.calls)


def _matches_where(metadata, where):
    """假库对 ``where`` 的求值：只认 department / classification 的 $in/$eq。"""
    if not where:
        return True
    for key, condition in where.items():
        if key == "$and":
            if not all(_matches_where(metadata, clause) for clause in condition):
                return False
            continue
        value = metadata.get(key)
        if isinstance(condition, dict):
            if "$in" in condition and value not in condition["$in"]:
                return False
            if "$eq" in condition and value != condition["$eq"]:
                return False
        elif value != condition:
            return False
    return True


def _hit(row):
    metadata = row["metadata"]
    return {
        "content": row["document"],
        "source": metadata["filename"],
        "chunk_index": metadata["chunk_index"],
        "classification": metadata["classification"],
        "department": metadata["department"],
    }


class _LiteralSemantic:
    """语义腿替身：按"query 原样出现在正文里"回货，并把 where 下推。

    它不是第二套权限判定：能不能看仍然只由 search() 传下来的 where/pred 决定，这里只复刻
    真库"先按 where 裁候选再回货"的形状。``pushdown=False`` 时故意无视 where，用来验"扩展
    query 召回来的越权条目照样被 pred 拦下"。
    """

    def __init__(self, rows, pushdown=True):
        self.rows = rows
        self.pushdown = pushdown
        self.calls = []
        self.returned = []

    def search(self, query, k=10, where=None):
        self.calls.append({"query": query, "k": k, "where": where})
        hits = []
        for row in self.rows:
            if not query or query not in row["document"]:
                continue
            if self.pushdown and not _matches_where(row["metadata"], where):
                continue
            hits.append(_hit(row))
        self.returned.append(hits[:k])
        return hits[:k]


class _RecordingBM25:
    """关键词腿的旁听装具：真检索照跑，只额外记录 query 与 pred。"""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def search(self, query, k=10, pred=None):
        self.calls.append({"query": query, "k": k, "pred": pred})
        return self.inner.search(query, k=k, pred=pred)


class _CapturingReranker:
    """记录进重排的候选集合：越权条目有没有混进融合，在这儿看。"""

    def __init__(self):
        self.inputs = []

    def rerank(self, query, docs, top_k=5):
        self.inputs.append(list(docs))
        return docs[:top_k]


def _keyword_leg(rows):
    """真 BM25Searcher：索引由本文件给定，绕开 Chroma。"""
    from rank_bm25 import BM25Okapi

    searcher = BM25Searcher()
    searcher.corpus = [retrieval_pipeline._tokenize_text(row["document"]) for row in rows]
    searcher.documents = [_hit(row) for row in rows]
    searcher.bm25 = BM25Okapi(searcher.corpus)
    return searcher


def _pipeline(rows=ROWS, *, pushdown=True):
    """绕开 ``__init__``（它会连 Chroma），保住真 BM25 与真 QueryRewriter。"""
    pipeline = RetrievalPipeline.__new__(RetrievalPipeline)
    pipeline.semantic = _LiteralSemantic(rows, pushdown=pushdown)
    pipeline.bm25 = _RecordingBM25(_keyword_leg(rows))
    pipeline.reranker = _CapturingReranker()
    pipeline.rewriter = retrieval_pipeline.QueryRewriter()
    return pipeline


def _stub_model(monkeypatch, payload=None):
    fake = _CountingModel(payload)
    monkeypatch.setattr(retrieval_pipeline, "model", fake)
    return fake


def _disable_expansion(monkeypatch):
    """反证开关：把扩展摘掉，检索退回"只有原题与模型改写"的形状。"""
    monkeypatch.setattr(retrieval_pipeline, "expand_query_synonyms", lambda *args, **kwargs: [])


def _stub_catalog(monkeypatch, terms):
    """把命中出口换成给定词表，用来单独量扩展自己的筛选与上限。"""
    catalog = _StubCatalog(terms)
    monkeypatch.setattr(
        retrieval_pipeline,
        "_matched_definition",
        lambda query, owner_id=None: catalog,
    )
    return catalog


def _semantic_queries(pipeline):
    return [call["query"] for call in pipeline.semantic.calls]


def _keyword_queries(pipeline):
    return [call["query"] for call in pipeline.bm25.calls]


def _contents(docs):
    return [doc["content"] for doc in docs]


def _rank_of(docs, row):
    try:
        return _contents(docs).index(row["document"])
    except ValueError:
        return None


class _StubCatalog:
    """替掉 registry 命中出口的最小定义：只带扩展会读的那两个字段。"""

    def __init__(self, terms, metric_id="test.stub"):
        self.metric_id = metric_id
        self.match_terms = tuple(terms)


@pytest.fixture(autouse=True)
def _catalog_offline(monkeypatch):
    """词表固定走 code fallback：不依赖测试机上有没有 PG，也不为读目录开连接。"""
    monkeypatch.setattr(registry_module, "_database_available", lambda: False)


@pytest.fixture(autouse=True)
def _fast_by_default(monkeypatch):
    """本文件默认在 fast 档跑：规则扩展的价值场景就是 0 模型往返这一档。"""
    monkeypatch.setenv(TIER_ENV, "fast")


# ==================== 判据①：同义词题的命中确实变好（前后对比） ====================

def test_alias_question_reaches_the_standard_wording_only_after_expansion(monkeypatch):
    real_expansion = retrieval_pipeline.expand_query_synonyms
    _disable_expansion(monkeypatch)
    before_pipeline = _pipeline(OPEN_ROWS)
    before, _ = before_pipeline.search(ALIAS_QUERY, top_k=3)

    monkeypatch.setattr(retrieval_pipeline, "expand_query_synonyms", real_expansion)
    after_pipeline = _pipeline(OPEN_ROWS)
    after, _ = after_pipeline.search(ALIAS_QUERY, top_k=3)

    # 摘掉扩展：正文只写标准名的那份文档，两条腿都召不到。
    assert _rank_of(before, D1) is None, "基线本就不该命中，否则这条对比证明不了任何事"
    assert set(_semantic_queries(before_pipeline)) == {ALIAS_QUERY}
    # 接上扩展：同一份文档进了结果，而且名次不输给写别名的那份。
    assert _rank_of(after, D1) is not None
    assert _rank_of(after, D1) < _rank_of(after, D2)
    # 原题的命中不许被挤掉。
    assert _rank_of(before, D2) is not None
    assert _rank_of(after, D2) is not None
    assert set(_semantic_queries(after_pipeline)) > set(_semantic_queries(before_pipeline))


def test_expansion_feeds_both_recall_paths():
    pipeline = _pipeline(OPEN_ROWS)

    pipeline.search(ALIAS_QUERY, top_k=3)

    assert set(_keyword_queries(pipeline)) == set(_semantic_queries(pipeline)), "两条腿吃到同一批 query"
    assert ALIAS_QUERY in _keyword_queries(pipeline), "原问题不许被丢掉"
    assert "差旅费用" in _keyword_queries(pipeline)
    assert "差旅费" in _keyword_queries(pipeline)


def test_expansion_drops_wording_the_question_already_uses():
    assert retrieval_pipeline.expand_query_synonyms(STANDARD_QUERY) == ["出差"]
    for term in retrieval_pipeline.expand_query_synonyms(ALIAS_QUERY):
        assert term.lower() not in ALIAS_QUERY.lower()


def test_no_match_question_is_byte_identical(monkeypatch):
    assert retrieval_pipeline._matched_definition(NEUTRAL_QUERY) is None

    pipeline = _pipeline()
    with_expansion = pipeline.search(NEUTRAL_QUERY, top_k=3)

    _disable_expansion(monkeypatch)
    without = _pipeline().search(NEUTRAL_QUERY, top_k=3)

    assert with_expansion == without
    assert _semantic_queries(pipeline) == [NEUTRAL_QUERY]
    assert _keyword_queries(pipeline) == [NEUTRAL_QUERY]


# ==================== 判据②：fast 档 0 次模型往返，且扩展照样生效 ====================

def test_fast_tier_expands_with_zero_llm_roundtrips(monkeypatch):
    fake = _stub_model(monkeypatch)
    pipeline = _pipeline(OPEN_ROWS)

    docs, rewrites = pipeline.search(ALIAS_QUERY, top_k=3)

    assert fake.roundtrips == 0, "扩展必须是规则，不许借道大模型"
    assert rewrites == []
    assert len(set(_semantic_queries(pipeline))) > 1, "fast 档也必须吃到扩展"
    assert _rank_of(docs, D1) is not None


def test_adaptive_tier_single_intent_still_expands_without_the_model(monkeypatch):
    fake = _stub_model(monkeypatch)
    monkeypatch.setenv(TIER_ENV, "adaptive")
    pipeline = _pipeline(OPEN_ROWS)

    pipeline.search(ALIAS_QUERY, top_k=3)

    assert fake.roundtrips == 0
    assert "差旅费" in set(_semantic_queries(pipeline))


def test_expansion_never_steals_a_slot_from_a_paid_rewrite(monkeypatch):
    """full 档模型改写占满槽位时，扩展一个字都不加：不给已付费的宽化再掺进去。"""
    fake = _stub_model(monkeypatch)
    monkeypatch.delenv(TIER_ENV, raising=False)
    payload = {
        "rewrites": ["差旅报销标准", "费用合计口径", "支出统计口径"],
        "sub_questions": ["差旅费用是多少", "超标如何审批"],
    }
    monkeypatch.setattr(fake, "payload", payload)
    pipeline = _pipeline(OPEN_ROWS)

    docs, rewrites = pipeline.search(ALIAS_QUERY, top_k=3)

    assert fake.roundtrips == 1
    assert rewrites == payload["rewrites"]
    queries = set(_semantic_queries(pipeline))
    assert queries == {ALIAS_QUERY, *payload["rewrites"], payload["sub_questions"][0]}
    assert len(_semantic_queries(pipeline)) == MAX_RECALL_QUERIES
    assert "差旅费用" not in queries and "差旅费" not in queries, "词表词不许挤掉模型改写"


# ==================== 判据③：条数上限、去重、不读白读的目录 ====================

@pytest.mark.parametrize(
    "terms",
    [
        tuple(f"甲类指标{i}" for i in range(6)),
        tuple(f"budget_scope_{i}" for i in range(12)),
    ],
)
def test_expansion_is_capped(monkeypatch, terms):
    _stub_catalog(monkeypatch, terms)

    expanded = retrieval_pipeline.expand_query_synonyms(GENERIC_QUERY)

    assert len(expanded) == SYNONYM_EXPANSION_MAX_QUERIES
    assert len(set(expanded)) == len(expanded), "同一词形不许重复占槽位"
    assert set(expanded) <= set(terms)


def test_expansion_only_fills_the_remaining_slots(monkeypatch):
    _stub_catalog(monkeypatch, tuple(f"甲类指标{i}" for i in range(6)))

    two_left = retrieval_pipeline.expand_query_synonyms(GENERIC_QUERY, [GENERIC_QUERY, "改写1", "改写2"])
    one_left = retrieval_pipeline.expand_query_synonyms(GENERIC_QUERY, [GENERIC_QUERY, "改写1", "改写2", "改写3"])
    exactly_full = retrieval_pipeline.expand_query_synonyms(
        GENERIC_QUERY, [GENERIC_QUERY] + [f"改写{i}" for i in range(MAX_RECALL_QUERIES - 1)]
    )
    over_full = retrieval_pipeline.expand_query_synonyms(
        GENERIC_QUERY, [GENERIC_QUERY] + [f"改写{i}" for i in range(MAX_RECALL_QUERIES)]
    )

    assert len(two_left) == 2
    assert len(one_left) == 1
    assert exactly_full == []
    assert over_full == []


def test_expansion_reads_no_catalog_when_it_cannot_take_effect(monkeypatch):
    """槽位已满时连词表都不读：不为注定被上限挡掉的扩展付一次目录往返。"""
    calls = []

    def _spy(question, owner_id=None):
        calls.append((question, owner_id))
        return _StubCatalog(("某个别名",))

    monkeypatch.setattr(registry_module, "match_definition", _spy)

    retrieval_pipeline.expand_query_synonyms(
        ALIAS_QUERY, [ALIAS_QUERY] + [f"q{index}" for index in range(MAX_RECALL_QUERIES)]
    )

    assert calls == []


def test_expansion_does_not_mutate_the_callers_query_list():
    base = [ALIAS_QUERY, "改写一"]

    expanded = retrieval_pipeline.expand_query_synonyms(ALIAS_QUERY, base)

    assert base == [ALIAS_QUERY, "改写一"]
    assert expanded == ["差旅费用", "差旅费"]


def test_single_character_terms_do_not_get_a_query_of_their_own(monkeypatch):
    _stub_catalog(monkeypatch, ("钱", "预算明细口径"))

    assert retrieval_pipeline.expand_query_synonyms(GENERIC_QUERY) == ["预算明细口径"]


def test_a_question_rich_enough_on_its_own_face_is_not_expanded(monkeypatch):
    """字面长度门槛：长问题字面已带够检索词，宽化是模型改写的活（见 pipeline 注释）。"""
    _stub_catalog(monkeypatch, ("甲类指标", "乙类指标"))
    long_question = "过去一年各部门的预算执行率与上年同期相比变化情况如何"

    assert len(long_question) >= retrieval_pipeline.SYNONYM_EXPANSION_MAX_QUERY_CHARS
    assert retrieval_pipeline.expand_query_synonyms(long_question) == []

    monkeypatch.setattr(retrieval_pipeline, "SYNONYM_EXPANSION_MAX_QUERY_CHARS", 0)

    assert retrieval_pipeline.expand_query_synonyms(long_question) == ["甲类指标", "乙类指标"]


# ==================== 判据④（权限腿）：扩展不许绕过预过滤 ====================

def _staff():
    return Principal(
        user_id="u-r47",
        username="r47-staff",
        permissions=["document.read"],
        department="marketing",
        clearance=1,
    )


def test_expanded_queries_carry_the_same_scope_predicate():
    pipeline = _pipeline()
    scope = retrieval_pipeline.resolve_document_retrieval_scope(_staff())

    pipeline.search_for_principal(ALIAS_QUERY, _staff(), top_k=3)

    queries = set(_semantic_queries(pipeline))
    assert len(queries) > 1, "这条用例只在确实发生扩展时才有意义"
    assert [call["where"] for call in pipeline.semantic.calls] == [scope.filters] * len(pipeline.semantic.calls)
    # pred 是同一个谓词对象不许由"两个 scope 实例相等"来证明：方法比较用的是身份，这里直接
    # 看它到底是哪个函数、绑在哪一份 scope 上——判定必须仍然只有 filters 那一处事实源。
    predicates = {call["pred"] for call in pipeline.bm25.calls}
    assert len(predicates) == 1, "扩展出来的每条 query 必须共用同一个谓词，不许各算各的"
    predicate = predicates.pop()
    assert predicate.__func__ is type(scope).allows
    assert predicate.__self__ == scope
    assert {call["k"] for call in pipeline.semantic.calls} == {8}
    assert len(pipeline.semantic.calls) == len(queries)


def test_a_forbidden_hit_from_an_expanded_query_is_still_dropped():
    """扩展 query 命中的越权 chunk 进不了结果：语义腿故意无视 where，挡它的是 pred。"""
    pipeline = _pipeline(pushdown=False)
    assert ALIAS_QUERY not in D_SECRET["document"], "越权那份必须只靠扩展词才召得到"
    assert "差旅费用" in D_SECRET["document"]

    docs, _ = pipeline.search_for_principal(ALIAS_QUERY, _staff(), top_k=5)

    # 先证明扩展确实把它捞回来了：没有这一步，"被拦下"这件事根本无从谈起。
    raw = [hit for batch in pipeline.semantic.returned for hit in batch]
    assert D_SECRET["document"] in _contents(raw), "扩展腿确实召回到越权条目"
    fused = pipeline.reranker.inputs[0]
    assert D_SECRET["document"] not in _contents(fused), "越权条目连融合都不该进"
    assert D_SECRET["document"] not in _contents(docs)


def test_permitted_documents_still_survive_the_expansion():
    pipeline = _pipeline()

    docs, _ = pipeline.search_for_principal(ALIAS_QUERY, _staff(), top_k=5)

    assert D1["document"] in _contents(docs)
    assert D2["document"] in _contents(docs)


# ==================== 判据⑤：owner / 作用域 ====================

def test_owner_id_follows_the_principal(monkeypatch):
    seen = []

    def _record(question, owner_id=None):
        seen.append((question, owner_id))
        return None

    monkeypatch.setattr(registry_module, "match_definition", _record)
    pipeline = _pipeline()

    pipeline.search_for_principal(ALIAS_QUERY, _staff(), top_k=3)
    pipeline.search(ALIAS_QUERY, top_k=3)

    assert seen == [(ALIAS_QUERY, "u-r47"), (ALIAS_QUERY, None)]


def test_another_owners_vocabulary_cannot_leak_in(monkeypatch):
    """假目录按 owner 分片：不给别人的行，别人的词就进不了检索 query。"""

    def _scoped(question, owner_id=None):
        if owner_id == "owner-a":
            return _StubCatalog(("董事会专用口径", "另一个租户的词", "跨租户别名"), "tenant.a")
        return None

    monkeypatch.setattr(registry_module, "match_definition", _scoped)
    principal = Principal(
        user_id="owner-b",
        username="r47-b",
        permissions=["document.read"],
        department="marketing",
        clearance=1,
    )
    pipeline = _pipeline()

    pipeline.search_for_principal(ALIAS_QUERY, principal, top_k=3)

    assert _semantic_queries(pipeline) == [ALIAS_QUERY]
    assert _keyword_queries(pipeline) == [ALIAS_QUERY]


def test_no_principal_means_the_shared_catalog_only(monkeypatch):
    """``search`` 不带 owner_id 时只读共享目录：扩展照样生效，但不碰任何租户私有行。"""
    asked_for = []

    def _system_only(question, owner_id=None):
        asked_for.append(owner_id)
        return _StubCatalog(("差旅费用", "差旅费"), "expense.travel.total") if owner_id is None else None

    monkeypatch.setattr(registry_module, "match_definition", _system_only)
    pipeline = _pipeline(OPEN_ROWS)

    docs, _ = pipeline.search(ALIAS_QUERY, top_k=3)

    assert asked_for == [None]
    assert "差旅费" in set(_semantic_queries(pipeline))
    assert _rank_of(docs, D1) is not None


# ==================== 词表来源：必须用带 match_terms 的那个出口 ====================

def test_expansion_reads_the_definition_outlet_that_carries_terms(monkeypatch):
    """``match_metric_context`` 的出口没有 match_terms，选错出口扩展会静默失效。"""
    context = registry_module.match_metric_context(ALIAS_QUERY)

    assert "match_terms" not in context.model_dump()
    assert "match_terms" not in registry_module.match_metric_definition(ALIAS_QUERY)["definition"]
    assert "出差" in registry_module.match_definition(ALIAS_QUERY).match_terms

    def _broken(question, owner_id=None):
        raise RuntimeError("目录读不动")

    monkeypatch.setattr(registry_module, "match_definition", _broken)

    assert retrieval_pipeline._matched_definition(ALIAS_QUERY) is None
    assert retrieval_pipeline.expand_query_synonyms(ALIAS_QUERY) == []


def test_the_shipped_catalog_drives_the_alias_case_without_any_stub():
    """端到端一口：出厂词表自带 出差→差旅费，扩展必须自己认出来。"""
    definition = registry_module.match_definition(ALIAS_QUERY)

    assert definition.metric_id == "expense.travel.total"
    assert definition.owner_id == registry_module.SYSTEM_OWNER_ID
    assert retrieval_pipeline.expand_query_synonyms(ALIAS_QUERY) == ["差旅费用", "差旅费"]
