"""R158 · 把「索引里查无此物」与「检索根本没跑成」钉成两张脸。

工单 R158（跟进单 §80）：P3 逐题对比 135 题里 24 题 Chroma 交回 0 条、PG 同一查询给精确前 5；
而生产面上"没有来源"与"检索挂了"在调用方是同一个空列表，两种事实在界面上同一张脸。
本文件钉判据①（离线可跑的形状钉）、判据③（具名读数：哪个 collection、要几行、回几行、
谁答的、有没有走过降级腿），并钉死判据②(d) 那条底线——本单不许把异常改成空列表。

全程零模型、零 PG、零写仓库 chroma_db：
- 假 collection 顶掉 self.collection，应答形状逐字段抄 chromadb（每列一张"只有一行请求"的二维表）；
- 真 chroma 那一组只在 pytest 临时目录里建小库（R134 的改道只管仓库内路径，临时目录直通），
  查询向量由 numpy 固定播种生成，一次 embedding 模型都不调。
"""
import ast
import inspect
import json
import textwrap
from typing import get_args

import pytest

from app.agents.contracts import ErrorEnvelope
from app.rag import hot_index
from app.rag import retriever as rt

DIM = rt.EMBEDDING_DIM

#: 隐私钉用的两枚记号：查询原文与命中正文各一枚，读数里出现即为红。
QUERY_CANARY = "查看其他部门的工资明细-canary"
BODY_CANARY = "salary-body-canary-MUST-NOT-LEAK"

#: 本单新立的七枚稳定码（四枚结局 + 三枚答复方）。判据④要求它们与 R64 那张封闭终态
#: 码表互不相容，也不许盖掉 R21 已有的检索腿码。
NEW_CODES = frozenset({
    rt.RETRIEVAL_OUTCOME_ANSWERED,
    rt.RETRIEVAL_OUTCOME_ZERO_ROWS,
    rt.RETRIEVAL_OUTCOME_ROWS_DROPPED,
    rt.RETRIEVAL_OUTCOME_STORE_FAILED,
    rt.RETRIEVAL_SERVER_CHROMA,
    rt.RETRIEVAL_SERVER_HOT_INDEX,
    rt.RETRIEVAL_SERVER_KEYWORD_STORE,
})


# ==================================================== 假向量库：应答形状抄 chromadb
class _StubCollection:
    """只认 query()/get() 的假 collection：交回什么、抛什么全由用例摆好。

    刻意不引 chromadb：这几枚用例要钉的是"我们这一侧怎么记账"，后端给的回答是输入而非
    结论，用假件反而能把 ids/documents/metadatas 三列不齐的形状钉准（真库不会那么给）。
    """

    name = "r158_stub_collection"

    def __init__(self, columns=None, *, raises=None, flat=None):
        self.columns = columns if columns is not None else _columns([])
        self.raises = raises
        self.flat = flat if flat is not None else {"ids": [], "documents": [], "metadatas": []}
        self.query_calls = []
        self.get_calls = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return dict(self.columns)

    def get(self, where=None):
        self.get_calls.append(where)
        return dict(self.flat)


class _VectorEmbedder:
    """把"某一枚指定向量当查询"接进真读路径：不发 socket、不打模型。"""

    def __init__(self, vector=None):
        self.vector = list(vector) if vector is not None else [0.0] * DIM
        self.queries = []

    def embed_query(self, text):
        self.queries.append(text)
        return list(self.vector)


class _RaisingEmbedder:
    """embedding 挂掉的形状：带稳定原因码的 EmbeddingError，走降级腿。"""

    def __init__(self, reason):
        self.reason = reason
        self.vector = [0.0] * DIM

    def embed_query(self, text):
        raise rt.EmbeddingError("model down", reason=self.reason)


class _FakeHotIndex:
    """热集那一腿的假索引：rank() 交回调用方摆好的名次，populated 恒真（免回读）。"""

    def __init__(self, ranked):
        self.ranked = list(ranked)
        self.populated = True
        self.rank_calls = []

    def adopt_scope(self, scope_key):
        return None

    def warm_retry_blocked(self):
        return False

    def rank(self, query_vector, k, *, where=None, pred=None, scope_key=None,
             stores_vectors=True):
        self.rank_calls.append({"k": k, "where": where})
        return list(self.ranked)


def _metadata(filename, chunk_index):
    return {"filename": filename, "chunk_index": chunk_index,
            "classification": 1, "department": "finance"}


def _columns(names, *, bodies=None, metadatas="auto"):
    """chromadb 的二维应答：n_results=1 的请求，每列一行、行内是候选。

    metadatas="none" 交回空列，那是"库给了行、我们配不出命中"的靶子形状。
    """
    names = list(names)
    if bodies is None:
        bodies = [f"body of {name}" for name in names]
    columns = {
        "ids": [[f"cid-{name}-{position}" for position, name in enumerate(names)]],
        "documents": [list(bodies)],
        "distances": [[0.1 * (position + 1) for position in range(len(names))]],
    }
    if metadatas == "auto":
        columns["metadatas"] = [[_metadata(name, position)
                                 for position, name in enumerate(names)]]
    else:
        columns["metadatas"] = [[]]
    return columns


def _flat(names):
    """collection.get() 的形状：一维表，降级腿与热集回读都按它排。"""
    return {
        "ids": [f"cid-{name}" for name in names],
        "documents": [f"部门工资明细 {name}" for name in names],
        "metadatas": [_metadata(name, 0) for name in names],
    }


@pytest.fixture(scope="module")
def retriever():
    """一把真 DocumentRetriever，后端与 embedding 由各用例现换。

    全模块共用一枚：构造函数会冷起一个 chromadb 客户端（R134 已把它改道进沙箱），
    每枚用例各起一次会让本文件成为全量里的时间黑洞，而那不是本单要付的代价。
    """
    from app.rag.retriever import DocumentRetriever

    instance = DocumentRetriever(activity_prior=lambda: {})
    instance.embedding = _VectorEmbedder()
    return instance


@pytest.fixture(autouse=True)
def _clean_ledger_and_default_legs(monkeypatch):
    """每枚用例从空账本开始，并默认关掉热集。

    不关热集就无法钉"0 行是谁给的"：热集在外部向量库之前拦截，留它开着等于每次测的都是
    别的腿，判据③那三个数就混成一团。热集自己的用例各自把它按回去。
    """
    rt.reset_search_shape()
    monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: False)
    yield
    rt.reset_search_shape()


def _wire(instance, collection, embedder=None):
    instance.collection = collection
    instance.embedding = embedder or _VectorEmbedder()
    return instance


def _last():
    return rt.search_shape_diagnostics()["last"]


# ======================= 判据③ 具名读数：三种"看起来都是空"的形状各占一格
def test_a_leg_that_hands_back_no_rows_is_named_zero_rows(retriever):
    """向量库正常答复、就是没给行：记成 leg_returned_zero_rows，不是故障。"""
    store = _StubCollection(_columns([]))

    hits = _wire(retriever, store).search("工资明细", k=5)

    assert hits == []
    reading = _last()
    assert reading["outcome"] == rt.RETRIEVAL_OUTCOME_ZERO_ROWS
    assert reading["rows_returned"] == 0 and reading["hits_built"] == 0
    assert reading["answered_by"] == rt.RETRIEVAL_SERVER_CHROMA
    assert reading["leg"] == rt.RETRIEVAL_MODE_SEMANTIC
    assert reading["n_results_requested"] == 5
    assert reading["collection"] == store.name
    assert reading["store_error"] == "" and reading["degradation_reason"] == ""


def test_rows_the_store_gave_and_we_dropped_are_a_different_cell(retriever):
    """库给了 5 行、我们建成 0 条命中：这一格必须与「库里没邻居」分家。

    靶子形状抄的是真故障面：query() 交回的 metadatas 缺列（include 形状不对就会这样），
    _hit_dicts 的 zip 于是配不出任何一条。若读数只数 documents，这格会被记成上一格——
    那正是"我们丢了数据"永远冒充"索引里没有"的形态。
    """
    store = _StubCollection(_columns(["a.txt", "b.txt", "c.txt", "d.txt", "e.txt"],
                                     metadatas="none"))

    hits = _wire(retriever, store).search("工资明细", k=5)

    assert hits == []
    reading = _last()
    assert reading["outcome"] == rt.RETRIEVAL_OUTCOME_ROWS_DROPPED
    assert reading["rows_returned"] == 5 and reading["hits_built"] == 0
    assert reading["rows_lost"] == 5


def test_the_two_flavours_of_zero_do_not_share_a_reading(retriever):
    """判据③的正面表述：都是空列表，但读数分得开，且不是靠"差不多"分了再合。"""
    _wire(retriever, _StubCollection(_columns([]))).search("工资明细", k=5)
    no_neighbours = _last()
    _wire(retriever, _StubCollection(_columns(["a.txt", "b.txt"], metadatas="none"))).search(
        "工资明细", k=5)
    lost_rows = _last()

    assert {no_neighbours["outcome"], lost_rows["outcome"]} == {
        rt.RETRIEVAL_OUTCOME_ZERO_ROWS, rt.RETRIEVAL_OUTCOME_ROWS_DROPPED}
    assert no_neighbours["rows_returned"] == 0 and lost_rows["rows_returned"] > 0


def test_a_store_that_raises_is_named_and_still_reaches_the_caller(retriever):
    """判据②(d) 的正面：库抛异常 ⇒ 记下类名之后照旧上抛，本单不改成空列表。

    ValueError + 空 $in 的文案抄的是 chromadb 1.5.9 的真形状（实测 1007/1007 探针都落在
    这一格），它是"检索根本没跑成"最便宜的一枚标本。
    """
    boom = ValueError("Expected `where` `$in` operator to have non-empty list")
    store = _StubCollection(raises=boom)

    with pytest.raises(ValueError) as caught:
        _wire(retriever, store).search("工资明细", k=5)

    assert caught.value is boom, "异常必须原样上抛：包装一次就等于换了一种吞法"
    reading = _last()
    assert reading["outcome"] == rt.RETRIEVAL_OUTCOME_STORE_FAILED
    assert reading["store_error"] == "ValueError"
    assert reading["rows_returned"] == 0 and reading["hits_built"] == 0
    assert reading["answered_by"] == rt.RETRIEVAL_SERVER_CHROMA


def test_failure_and_no_neighbours_are_apart_even_though_both_return_an_empty_list(retriever):
    """两件事在调用方都是 []，在读数里是两枚码：这条钉的是"可分辨"本身。"""
    _wire(retriever, _StubCollection(_columns([]))).search("工资明细", k=5)
    empty_leg = _last()["outcome"]
    with pytest.raises(ValueError):
        _wire(retriever, _StubCollection(raises=ValueError("boom"))).search("工资明细", k=5)
    failed_store = _last()["outcome"]

    assert empty_leg == rt.RETRIEVAL_OUTCOME_ZERO_ROWS
    assert failed_store == rt.RETRIEVAL_OUTCOME_STORE_FAILED
    assert empty_leg != failed_store


def test_a_normal_answer_is_a_third_face_with_its_own_numbers(retriever):
    store = _StubCollection(_columns(["a.txt", "b.txt", "c.txt"]))

    hits = _wire(retriever, store).search("工资明细", k=3)

    assert [hit["source"] for hit in hits] == ["a.txt", "b.txt", "c.txt"]
    reading = _last()
    assert reading["outcome"] == rt.RETRIEVAL_OUTCOME_ANSWERED
    assert reading["rows_returned"] == 3 and reading["hits_built"] == 3
    assert reading["rows_lost"] == 0


def test_the_totals_answer_how_many_questions_wore_each_face(retriever):
    """三个数的来源：totals 记结局、answered_by 记谁答的，两者都是逐问累计。"""
    for _ in range(3):
        _wire(retriever, _StubCollection(_columns(["a.txt", "b.txt"]))).search("工资", k=2)
    for _ in range(2):
        _wire(retriever, _StubCollection(_columns([]))).search("工资", k=2)
    _wire(retriever, _StubCollection(_columns(["a.txt"], metadatas="none"))).search("工资", k=2)
    with pytest.raises(ValueError):
        _wire(retriever, _StubCollection(raises=ValueError("boom"))).search("工资", k=2)

    diagnostics = rt.search_shape_diagnostics()
    assert diagnostics["totals"] == {
        rt.RETRIEVAL_OUTCOME_ANSWERED: 3,
        rt.RETRIEVAL_OUTCOME_ZERO_ROWS: 2,
        rt.RETRIEVAL_OUTCOME_ROWS_DROPPED: 1,
        rt.RETRIEVAL_OUTCOME_STORE_FAILED: 1,
    }
    assert diagnostics["answered_by"] == {rt.RETRIEVAL_SERVER_CHROMA: 7}


def test_the_keyword_degradation_leg_says_who_answered_and_why(retriever):
    """降级腿答的必须记成 keyword_scan + 原因码，否则"退化了"这件事只有日志知道。"""
    store = _StubCollection(_columns([]), flat=_flat(["payroll.txt"]))

    hits = _wire(retriever, store, _RaisingEmbedder("model_unavailable")).search(
        "部门工资明细", k=3)

    assert hits, "降级腿应该真的捞回东西，否则这条用例什么都没钉"
    reading = _last()
    assert reading["answered_by"] == rt.RETRIEVAL_SERVER_KEYWORD_STORE
    assert reading["leg"] == rt.RETRIEVAL_MODE_KEYWORD
    assert reading["degradation_reason"] == "model_unavailable"
    assert reading["outcome"] == rt.RETRIEVAL_OUTCOME_ANSWERED
    assert retriever.last_search_mode == rt.RETRIEVAL_MODE_KEYWORD


def test_a_store_without_vectors_is_attributed_to_the_keyword_scan(retriever, monkeypatch):
    """chromadb 缺失那一支（离线后端）也是降级，不许混进"外部库给了 0 行"。"""
    monkeypatch.setattr(rt, "chromadb", None)
    store = _StubCollection(_columns([]), flat=_flat(["payroll.txt"]))

    hits = _wire(retriever, store).search("部门工资明细", k=3)

    assert hits
    reading = _last()
    assert reading["answered_by"] == rt.RETRIEVAL_SERVER_KEYWORD_STORE
    assert reading["leg"] == rt.RETRIEVAL_MODE_KEYWORD
    assert reading["degradation_reason"] == rt.RETRIEVAL_REASON_STORE_OFFLINE
    assert store.query_calls == [], "离线后端没有向量列，问它语义就是假账"


def test_the_hot_leg_is_attributed_to_hot_index_and_the_store_is_never_queried(
        retriever, monkeypatch):
    """热集交回 0 行时外部向量库压根没被问过。

    把这种 0 记成"HNSW 找不到邻居"就是假账，所以这里同时钉两件事：answered_by 是
    hot_index，以及假 collection 上一次 query() 都没被调用（用调用次数钉，不用推理）。
    """
    store = _StubCollection(_columns(["a.txt"]))
    _wire(retriever, store)
    monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: True)
    monkeypatch.setattr(hot_index, "get_hot_index", lambda: _FakeHotIndex([]))

    hits = retriever.search("工资明细", k=5)

    assert hits == []
    assert store.query_calls == []
    reading = _last()
    assert reading["answered_by"] == rt.RETRIEVAL_SERVER_HOT_INDEX
    assert reading["outcome"] == rt.RETRIEVAL_OUTCOME_ZERO_ROWS
    assert rt.search_shape_diagnostics()["answered_by"] == {rt.RETRIEVAL_SERVER_HOT_INDEX: 1}


def test_the_hot_leg_answering_rows_is_not_counted_as_a_chroma_answer(retriever, monkeypatch):
    store = _StubCollection(_columns(["never-asked.txt"]))
    _wire(retriever, store)
    ranked = [("cid-a", None, "body of hot.txt", _metadata("hot.txt", 0))]
    monkeypatch.setattr(hot_index, "hot_index_enabled", lambda: True)
    monkeypatch.setattr(hot_index, "get_hot_index", lambda: _FakeHotIndex(ranked))

    hits = retriever.search("工资明细", k=5)

    assert [hit["source"] for hit in hits] == ["hot.txt"]
    assert store.query_calls == []
    reading = _last()
    assert reading["answered_by"] == rt.RETRIEVAL_SERVER_HOT_INDEX
    assert reading["outcome"] == rt.RETRIEVAL_OUTCOME_ANSWERED



# ================== 判据②(d) 底线：本单不许新增任何"把异常吞成空列表"的路径
def test_search_has_no_handler_that_returns_an_empty_collection():
    """AST 钉：search() 里任何一个 except 分支都不许 return 空列表/空元组。

    写成读源码而不是"跑一遍看会不会吞"，是因为吞异常的路径只在真库抛异常那天才走到——
    那种日子恰恰是线上出事的日子。降级腿那条 except 是合法返回（它交回词法命中的列表），
    所以钉的是"交回空容器"，不是"交回东西"。
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(rt.DocumentRetriever.search)))

    offenders = []
    for handler in [node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)]:
        for inner in ast.walk(handler):
            if isinstance(inner, ast.Return) and isinstance(inner.value, (ast.List, ast.Tuple)):
                if not inner.value.elts:
                    offenders.append(inner.lineno)
    assert not offenders, f"search() 把异常吞成了空容器，行号 {offenders}"


def test_the_vector_store_handler_records_the_shape_and_then_re_raises():
    """上抛必须是**裸 raise**：原样、同一枚异常对象，且记账发生在抛之前。"""
    tree = ast.parse(textwrap.dedent(inspect.getsource(rt.DocumentRetriever.search)))
    handlers = [node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)]
    guarded = [
        handler for handler in handlers
        if any(isinstance(call, ast.Call)
               and getattr(call.func, "attr", "") == "_note_search_shape"
               and any(keyword.arg == "store_error" for keyword in call.keywords)
               for call in ast.walk(handler))
    ]
    assert len(guarded) == 1, "记下 store_error 的分支应当只有一处（向量库那一腿）"
    tail = guarded[0].body[-1]
    assert isinstance(tail, ast.Raise) and tail.exc is None, (
        "那一处必须以裸 raise 收尾：本单只加读数，不改异常语义")


def test_the_new_codes_stay_outside_the_closed_error_code_table():
    """判据④：R64 那 29 枚终态码是封闭枚举，本单的码不进那张表、也不借用表里的字面量。"""
    terminal = get_args(ErrorEnvelope.model_fields["code"].annotation)
    assert len(terminal) == 29, (
        f"终态码表枚数变了（现 {len(terminal)} 枚）：本单的钉子要按新表重读，别改断言")
    assert NEW_CODES.isdisjoint(set(terminal)), (
        f"撞进了终态码表：{sorted(NEW_CODES & set(terminal))}")


def test_the_new_codes_do_not_shadow_existing_retrieval_leg_or_reason_codes():
    """同一模块里的 R21 腿码/原因码也不许被盖名：两套码各自指一件事。"""
    legacy = {
        value for name, value in vars(rt).items()
        if name.startswith(("REASON_", "RETRIEVAL_MODE_", "RETRIEVAL_REASON_"))
        and isinstance(value, str) and not name.startswith("RETRIEVAL_OUTCOME_")
        and not name.startswith("RETRIEVAL_SERVER_")
    }
    assert legacy, "读不到既有检索码表，这条钉就成了空断言"
    assert NEW_CODES.isdisjoint(legacy), f"与既有码同名：{sorted(NEW_CODES & legacy)}"


def test_search_still_returns_a_plain_list_of_hit_dicts_with_the_documented_keys(retriever):
    """返回形状一个字不许动：新读数只长在模块级账本里，不塞进命中字典。"""
    hits = _wire(retriever, _StubCollection(_columns(["a.txt", "b.txt"]))).search("工资", k=2)

    assert isinstance(hits, list) and all(isinstance(hit, dict) for hit in hits)
    assert set(hits[0]) == {"content", "source", "chunk_index", "classification",
                            "department", "retrieval_mode", "retrieval_reason"}
    assert hits[0]["retrieval_mode"] == rt.RETRIEVAL_MODE_SEMANTIC
    assert hits[0]["retrieval_reason"] == ""
    assert retriever.last_search_mode == rt.RETRIEVAL_MODE_SEMANTIC
    assert retriever.last_search_reason == ""


def test_the_readout_carries_no_query_text_and_no_hit_content(retriever):
    """账本里只有数字与稳定码：查询原文与正文一律不许进来（R46 隐私口径的延续）。"""
    store = _StubCollection(_columns([QUERY_CANARY], bodies=[BODY_CANARY]))

    _wire(retriever, store).search(QUERY_CANARY, k=5)

    blob = json.dumps(rt.search_shape_diagnostics(), ensure_ascii=False)
    assert QUERY_CANARY not in blob, "查询原文泄进了形状读数"
    assert BODY_CANARY not in blob, "命中正文泄进了形状读数"
    assert set(_last()) == {"collection", "answered_by", "leg", "degradation_reason",
                            "n_results_requested", "rows_returned", "hits_built",
                            "rows_lost", "outcome", "store_error"}


def test_reading_the_ledger_issues_no_io(retriever):
    """读数必须能在故障现场反复读：它自己不许再问一次向量库，否则观测会改变被观测量。"""
    store = _StubCollection(_columns(["a.txt"]))
    _wire(retriever, store).search("工资", k=2)
    calls = len(store.query_calls)

    for _ in range(20):
        rt.search_shape_diagnostics()

    assert len(store.query_calls) == calls


def test_reset_search_shape_empties_the_ledger_for_the_next_measurement(retriever):
    """复位是"逐问计数"能对上算术的前提：不复位就会把上一题的账算进这一题。"""
    _wire(retriever, _StubCollection(_columns(["a.txt"]))).search("工资", k=2)
    assert rt.search_shape_diagnostics()["totals"]

    rt.reset_search_shape()

    diagnostics = rt.search_shape_diagnostics()
    assert diagnostics == {"last": None, "totals": {}, "answered_by": {}}
