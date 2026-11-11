"""R79 判据④：HOT_INDEX_* 被设成不现实的值时，行为仍必须正确；暖机失败仍不许每题重跑。

R44b 修的是真机上量出来的一条坑：`documents/` 115 个 txt → 37 483 chunk，整库一次 get 撞
SQLite 的 32 766 变量上限直接报错，而暖机失败原先不留痕迹，每次检索都重跑一遍注定失败的整库
回读，两条 coverage 用例跑了 482 秒。分页 + 冷却修完之后是 6.8 秒。

R44 的 tests/test_r44_hot_index_paging.py 已经用构造参数钉过冷却的形状。本文件补的是它没覆盖
的那一半：**全部走环境变量、走真实解析分支**，因为线上运维只会改环境变量，不会传 kwargs；
并且把"不现实的值"（max_chunks=1、roster_page=1）钉成结果仍逐条一致，而不是钉成"能跑就行"。

真机规模的分页耗时 / 总暖机耗时 / 峰值 RSS 是脚本实测数字，写在交付回执④里，不落进用例
（一条要跑几分钟的用例不会被任何人勤快地跑，那是自欺）。
"""

import hashlib

import pytest

from app.rag import hot_index as hi
from app.rag import retriever as retriever_module
from app.rag.retriever import DocumentRetriever

CORPUS = (
    #: 五篇文档五个部门：一条常驻、四条冷表时，"只看常驻那一家的部门"这个过滤条件必然
    #: 把冷表整体挡在外面 —— 不依赖向量库返回的行序，测试才不会看运气。
    ("policy_a.txt", "住宿费标准是每晚500元，超出部分需要总监审批。", "travel"),
    ("policy_b.txt", "差旅费报销细则：市内交通凭票实报实销。", "expense"),
    ("hr_handbook.txt", "考勤与假期管理办法：年假按工龄计算。", "hr"),
    ("fin_budget.txt", "年度预算方案：营销费用占比下调两个点。", "finance"),
    ("ops_safety.txt", "安全生产管理制度：动火作业需要提前报备。", "ops"),
)
QUESTIONS = ("住宿费标准是多少", "出差交通怎么报销", "年假有几天",
             "预算怎么安排", "动火作业要报备吗", "完全不相关的量子隧穿问题")


def _hash_vector(text: str, dim: int) -> list:
    vector = [0.0] * dim
    data = str(text).encode("utf-8")
    for position in range(0, len(data), 3):
        digest = int.from_bytes(hashlib.md5(data[position:position + 3]).digest()[:4], "big")
        vector[digest % dim] += 1.0 + (digest % 7) / 10.0
    return vector if any(vector) else [1.0] + [0.0] * (dim - 1)


def _keys(hits):
    return [(hit["source"], hit["chunk_index"]) for hit in hits]


class _Store:
    """只按环境变量装配的热集 + 真临时向量库，外加读库次数计数器。"""

    def __init__(self, tmp_path, monkeypatch, *, clock=None):
        monkeypatch.setattr(retriever_module.OllamaEmbeddings, "_call_api",
                            lambda _self, text: _hash_vector(
                                str(text), retriever_module.EMBEDDING_DIM))
        kwargs = {"clock": clock} if clock is not None else {}
        self.index = hi.HotSetIndex(**kwargs)         # 一个容量参数都不传：全走环境变量
        monkeypatch.setattr(hi, "_HOT_INDEX", self.index)
        monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")
        hi.reset_hot_index_diagnostics()
        self.monkeypatch = monkeypatch
        self.retriever = DocumentRetriever(chroma_dir=str(tmp_path / "chroma"))
        self.reads = 0
        self.queries = 0
        #: reads / queries 每次 search 归零，方便按题记账；reads_total 只增不减，
        #: 冷却量的是"从头到尾一共打了几次库"，必须用累计值。
        self.reads_total = 0
        collection = self.retriever.collection
        real_get, real_query = collection.get, collection.query
        store = self

        def get(*args, **kwargs_):
            store.reads += 1
            store.reads_total += 1
            #: 先计数再抛：计数器量的是"有没有去打库"，注入失败也必须被记上，
            #: 否则"一次都没尝试暖机"和"尝试了但失败"就分不开。
            if getattr(get, "failing", False):
                raise RuntimeError("injected: too many SQL variables")
            return real_get(*args, **kwargs_)

        def query(*args, **kwargs_):
            store.queries += 1
            return real_query(*args, **kwargs_)

        get.failing = False
        collection.get, collection.query = get, query
        for filename, content, department in CORPUS:
            ok, message = self.retriever.add_document(
                filename, content, classification=1, department=department)
            assert ok, message
        self.total_chunks = len(self.retriever.collection.get(include=["metadatas"])["ids"])

    def reset_counts(self):
        self.reads = self.queries = 0
        return self

    def search(self, question, *, hot=True, k=3, where=None):
        if hot:
            self.monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")
        else:
            self.monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)
        self.reset_counts()
        return self.retriever.search(question, k=k, where=where)


@pytest.fixture
def env(monkeypatch):
    for name in (hi.HOT_INDEX_ENV, hi.HOT_INDEX_MAX_CHUNKS_ENV,
                 hi.HOT_INDEX_MAX_AGE_SECONDS_ENV, hi.HOT_INDEX_ROSTER_PAGE_ENV,
                 hi.HOT_INDEX_WARM_RETRY_SECONDS_ENV):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# ==================== 不现实的预算：max_chunks=1 ====================

def test_a_one_chunk_budget_from_the_environment_answers_exactly_as_if_there_were_no_hot_index(
        env, tmp_path):
    """HOT_INDEX_MAX_CHUNKS=1：装不下语料就必须整体让路，结果与关闭态逐条同序同 id。"""
    env.setenv("HOT_INDEX_MAX_CHUNKS", "1")
    store = _Store(tmp_path, monkeypatch=env)
    assert store.index.max_chunks == 1
    differences = []
    for question in QUESTIONS:
        baseline = store.search(question, hot=False)
        assert baseline, question                       # 这批题必须真能召回东西，否则比对是空的
        hot = store.search(question, hot=True)
        if _keys(hot) != _keys(baseline):
            differences.append((question, _keys(baseline), _keys(hot)))
    assert differences == []
    assert store.index.resident_chunks == 1
    assert store.index.cold_chunks == store.total_chunks - 1
    assert hi.hot_index_diagnostics()["last_bypass_reason"] == hi.REASON_INCOMPLETE
    assert hi.hot_index_diagnostics()["hits"] == 0
    #: 退路本身也要有代价上限：每题恰好一次 query，一次都不许多读库。
    assert store.queries == 1 and store.reads == 0, (store.queries, store.reads)


def test_a_one_chunk_budget_still_serves_when_the_filter_excludes_every_cold_row(env, tmp_path):
    """同一批常驻条目在窄过滤下仍然敢服务：1 条预算不是"永远不用"，是"覆盖不了才不用"。"""
    env.setenv("HOT_INDEX_MAX_CHUNKS", "1")
    store = _Store(tmp_path, monkeypatch=env)
    question = "住宿费标准是多少"
    #: 先让它在 where=None 的最坏情况下暖机并让路，再把过滤条件收窄到常驻那一家。
    store.search(question, hot=True)
    assert store.index.resident_chunks == 1 and store.index.cold_chunks >= 1
    assert hi.hot_index_diagnostics()["last_bypass_reason"] == hi.REASON_INCOMPLETE
    resident = next(iter(store.index._entries.values()))
    where = {"department": resident.metadata["department"]}
    baseline = _keys(store.search(question, hot=False, where=where))
    before = hi.hot_index_diagnostics()["hits"]
    hot = _keys(store.search(question, hot=True, where=where))
    assert hi.hot_index_diagnostics()["hits"] == before + 1, "窄过滤下必须由热集服务"
    assert store.queries == 0 and store.reads == 0, (store.queries, store.reads)
    assert hot == baseline and hot, (hot, baseline)


# ==================== 不现实的页大小：roster_page=1 ====================

def test_a_one_row_page_still_reads_the_whole_roster(env, tmp_path):
    """HOT_INDEX_ROSTER_PAGE=1：一页一条也必须把花名册读全，读出来的东西与整库一次读等价。"""
    env.setenv("HOT_INDEX_ROSTER_PAGE", "1")
    store = _Store(tmp_path, monkeypatch=env)
    assert store.index.roster_page == 1
    baseline = _keys(store.search("住宿费标准是多少", hot=False))
    hits = _keys(store.search("住宿费标准是多少", hot=True))
    assert store.index.resident_chunks == store.total_chunks
    assert store.reads >= store.total_chunks, "分页没读满整库，说明提前止步了"
    assert hits == baseline
    assert hi.hot_index_diagnostics()["last_bypass_reason"] == ""


# ==================== 暖机失败的退避：全部走环境变量 ====================

def test_a_failed_warm_does_not_rerun_the_store_read_on_every_query(env, tmp_path):
    """冷却必须生效：否则每次检索都重跑一遍注定失败的整库回读（482 秒那条坑）。"""
    store = _Store(tmp_path, monkeypatch=env)
    baseline = {}
    for question in QUESTIONS:
        baseline[question] = _keys(store.search(question, hot=False))

    store.retriever.collection.get.failing = True
    first = _keys(store.search(QUESTIONS[0]))
    assert store.reads_total >= 1, "注入失败之后一次都没尝试暖机"
    assert store.index.warm_retry_blocked()
    blocked_reads = store.reads_total

    for _ in range(len(QUESTIONS) - 1):
        for question in QUESTIONS:
            later = _keys(store.search(question))
            assert store.reads_total == blocked_reads, (
                f"冷却期内又重跑了 {store.reads_total - blocked_reads} 次整库回读")
            assert later == baseline[question], question
    assert first == baseline[QUESTIONS[0]]
    ledger = hi.hot_index_diagnostics()
    assert ledger["last_bypass_reason"] == hi.REASON_COLD
    assert ledger["hits"] == 0 and ledger["misses"] >= len(QUESTIONS)


def test_the_retry_window_comes_from_the_environment_and_lets_the_next_attempt_through(env,
                                                                                       tmp_path):
    """HOT_INDEX_WARM_RETRY_SECONDS=2：两秒之后必须再试一次，不能一冷却就永久躺平。"""
    env.setenv("HOT_INDEX_WARM_RETRY_SECONDS", "2")
    clock = [0.0]
    store = _Store(tmp_path, monkeypatch=env, clock=lambda: clock[0])
    assert store.index.state()["warm_retry_seconds"] == 2.0
    store.retriever.collection.get.failing = True
    store.search("住宿费标准是多少")
    assert store.index.warm_retry_blocked()

    clock[0] = 1.9
    store.reset_counts()
    store.search("住宿费标准是多少")
    assert store.reads == 0, "冷却没到点就重试，退避等于没做"

    store.retriever.collection.get.failing = False
    clock[0] = 2.1
    store.reset_counts()
    hits = _keys(store.search("住宿费标准是多少"))
    assert store.reads > 0, "到点了没再试，冷却变成了永久放弃"
    assert store.index.resident_chunks == store.total_chunks
    assert hits and hi.hot_index_diagnostics()["last_bypass_reason"] == ""


def test_the_default_retry_window_is_sixty_seconds_on_both_sides_of_the_dot(env):
    """R44b 那三枚常量的出厂值也一并钉住：60 秒退避 / 1 000 行分页 / 开关默认关。"""
    assert hi.HotSetIndex().state()["warm_retry_seconds"] == 60.0
    assert hi.HotSetIndex().state()["roster_page"] == 1_000
    assert hi.hot_index_config()["enabled"] is False
    clock = [0.0]
    index = hi.HotSetIndex(clock=lambda: clock[0])
    index.note_warm_failure()
    clock[0] = 59.999
    assert index.warm_retry_blocked() is True
    clock[0] = 60.001
    assert index.warm_retry_blocked() is False
    env.setattr(hi, "DEFAULT_WARM_RETRY_SECONDS", 7.0)
    retry_index = hi.HotSetIndex(clock=lambda: clock[0])
    retry_index.note_warm_failure()
    clock[0] = 130.0
    assert retry_index.warm_retry_blocked() is False, "改常量不跟着动，说明冷却窗是抄的"
