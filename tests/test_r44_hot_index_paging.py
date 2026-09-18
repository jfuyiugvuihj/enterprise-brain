"""R44 暖机回读的分页与失败退避 —— 大库（>32 766 chunk）上的回归钉子。

立案缘由（总控亲测，09-18 主树全量）：`documents/` 里 115 个 txt → 向量库 37 483 个
chunk，`collection.get(include=["metadatas"])` 整库一次读直接报
`too many SQL variables`（Chroma 把 id 逐个绑进 SQL，撞 SQLite 的 32 766 变量上限），
于是热集永远判"不能服务"；而暖机失败原先不留痕迹，每一次检索都重跑一遍注定失败的整库
回读 —— 两条 coverage 用例因此跑了 482 秒。干净树里只有 95 个 txt、chunk 数在预算与上限
之内，所以这两条在子树上全绿：这是一个**只在真实规模下才现形**的产品缺陷，不是测试噪声。

这里钉的是形状而不是体量：不要求测试机上真有一个 32 766 条的库（那要跑几十秒），只要求
"任何一次回读的条数都不超过 roster_page"，分页拼回来必须等于整库一次读的那一份，
以及"暖机失败之后不许每题重跑"。
"""

import hashlib

import pytest

from app.rag import hot_index as hi
from app.rag import retriever as retriever_module
from app.rag.retriever import DocumentRetriever

#: 故意取小，让 30 来条 chunk 就能走出好几页。
PAGE = 7
#: SQLite 的变量上限，钉住"默认分页值必须留在它下面"这个前提。
SQLITE_VARIABLE_CAP = 32_766


def _hash_vector(text: str, dim: int) -> list:
    vector = [0.0] * dim
    data = str(text).encode("utf-8")
    for position in range(0, len(data), 3):
        digest = int.from_bytes(hashlib.md5(data[position:position + 3]).digest()[:4], "big")
        vector[digest % dim] += 1.0 + (digest % 7) / 10.0
    return vector if any(vector) else [1.0] + [0.0] * (dim - 1)


class _GetRecorder:
    """记录 collection.get 的每一次入参，必要时让它失败。

    换掉的是实例属性（与 tests/test_r44_hot_index_coverage.py 同一手法），所以
    `DocumentRetriever` 里那三条真实读库路径一个字都没被绕过。
    """

    def __init__(self, collection):
        self.collection = collection
        self.calls = []
        self.failing = False
        self._real_get = collection.get

        def recorded(*args, **kwargs):
            self.calls.append(dict(kwargs))
            if self.failing:
                raise RuntimeError("injected: too many SQL variables")
            return self._real_get(*args, **kwargs)

        collection.get = recorded

    @property
    def count(self) -> int:
        return len(self.calls)

    def bounded(self) -> bool:
        """每一次 get 都必须带页大小：要么 limit 不超页，要么 ids 不超页。"""
        for call in self.calls:
            limit = call.get("limit")
            ids = call.get("ids")
            if limit is not None and limit <= PAGE:
                continue
            if ids is not None and len(ids) <= PAGE:
                continue
            return False
        return True


def _corpus(retriever: DocumentRetriever, docs: int = 4, paragraphs: int = 12) -> None:
    for doc in range(docs):
        body = "\n\n".join(
            f"文档{doc}第{part}段 预算与回读口径的说明 {(doc * 100 + part):04d} "
            + ("内容" * 90)
            for part in range(paragraphs)
        )
        retriever.add_document(f"paging_doc_{doc}.txt", body, classification=1, department="")


class _Store:
    def __init__(self, tmp_path, monkeypatch, *, page: int = PAGE, clock=None,
                 warm_retry_seconds: float = hi.DEFAULT_WARM_RETRY_SECONDS):
        monkeypatch.setattr(retriever_module.OllamaEmbeddings, "_call_api",
                            lambda _self, text: _hash_vector(
                                str(text), retriever_module.EMBEDDING_DIM))
        kwargs = {"max_chunks": 10_000, "roster_ttl_seconds": 3600.0,
                  "roster_page": page, "warm_retry_seconds": warm_retry_seconds}
        if clock is not None:
            kwargs["clock"] = clock
        self.index = hi.HotSetIndex(**kwargs)
        monkeypatch.setattr(hi, "_HOT_INDEX", self.index)
        hi.reset_hot_index_diagnostics()
        self.monkeypatch = monkeypatch
        self.retriever = DocumentRetriever(chroma_dir=str(tmp_path / "chroma"))
        self.recorder = _GetRecorder(self.retriever.collection)
        _corpus(self.retriever)

    def search(self, question: str, *, hot: bool = True) -> list:
        if hot:
            self.monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")
        else:
            self.monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)
        self.recorder.calls.clear()
        return self.retriever.search(question, k=5)

    @staticmethod
    def keys(hits: list) -> list:
        return [(hit["source"], hit["chunk_index"]) for hit in hits]


def _total_chunks(store: _Store) -> int:
    return int(store.retriever.collection.count())


def test_warm_pages_the_roster_and_never_issues_an_unbounded_get(tmp_path, monkeypatch):
    """判据（本次立案）：任何一次回读的条数都不超过 roster_page。

    整库一次 get 就是那条 37 483 chunk 上必炸的语句，这里直接钉住它不出现。
    """
    store = _Store(tmp_path, monkeypatch)
    total = _total_chunks(store)
    assert total > PAGE * 2, f"语料太小，测不出分页：{total} 条"

    store.search("预算与回读口径", hot=False)          # 先取外部库基线
    baseline = store.keys(store.search("预算与回读口径", hot=False))
    hits = store.keys(store.search("预算与回读口径"))   # 这一趟要暖机

    assert store.recorder.calls, "暖机一次 get 都没发，说明没走真读库路径"
    assert store.recorder.bounded(), f"出现了不受页大小约束的读库: {store.recorder.calls}"
    pages = [call for call in store.recorder.calls if call.get("limit") is not None]
    assert len(pages) > 1, f"花名册没有分页读，只读到 {len(pages)} 次"
    assert store.index.resident_chunks == total, (store.index.resident_chunks, total)
    assert hits == baseline


def test_paged_roster_reads_every_chunk_exactly_once(tmp_path, monkeypatch):
    """分页拼回来必须与整库一次读逐条等价：不重、不漏、元数据不错位。"""
    store = _Store(tmp_path, monkeypatch)
    ids, metadatas = store.retriever._read_hot_roster(store.index)
    one_shot = store.retriever.collection.get(include=["metadatas"]) or {}
    want_ids = [str(item) for item in (one_shot.get("ids") or [])]
    want_meta = {str(chunk_id): (one_shot.get("metadatas") or [])[position]
                 for position, chunk_id in enumerate(want_ids)}

    assert len(ids) == len(set(ids)) == _total_chunks(store), (len(ids), len(set(ids)))
    assert set(ids) == set(want_ids)
    assert len(metadatas) == len(ids)
    for chunk_id, metadata in zip(ids, metadatas):
        assert (metadata or {}) == (want_meta.get(chunk_id) or {}), chunk_id


def test_pages_of_seven_and_pages_of_ten_thousand_serve_the_same_hits(tmp_path, monkeypatch):
    """页大小不得影响结果：小页与大页给同一批命中、同一顺序。"""
    small = _Store(tmp_path, monkeypatch, page=PAGE)
    question = "预算与回读口径的说明"
    small.search(question, hot=False)
    small_hits = small.keys(small.search(question))

    large_index = hi.HotSetIndex(max_chunks=10_000, roster_ttl_seconds=3600.0,
                                 roster_page=10_000)
    monkeypatch.setattr(hi, "_HOT_INDEX", large_index)
    hi.reset_hot_index_diagnostics()
    large = DocumentRetriever(chroma_dir=str(small.retriever.chroma_dir))
    monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")
    large_hits = large_index and small.keys(large.search(question, k=5))

    assert small_hits and large_hits == small_hits, (small_hits, large_hits)


def test_a_failed_warm_is_not_retried_on_every_query(tmp_path, monkeypatch):
    """暖机失败必须退避：否则每次检索都重跑一遍注定失败的整库回读（实测 482 秒的来源）。"""
    store = _Store(tmp_path, monkeypatch)
    store.search("预算与回读口径", hot=False)
    baseline = store.keys(store.search("预算与回读口径", hot=False))

    store.recorder.failing = True
    first = store.keys(store.search("预算与回读口径"))
    failed_once = store.recorder.count
    assert failed_once >= 1, "注入失败之后一次都没尝试暖机"
    assert store.index.warm_retry_blocked()

    for turn in range(4):
        later = store.keys(store.search("预算与回读口径"))
        assert store.recorder.count == 0, (
            f"冷却期内第 {turn + 1} 题又重跑了整库回读 {store.recorder.count} 次")
        assert later == baseline, "退避期间结果必须与不开热集逐条一致"
    assert first == baseline
    assert hi.hot_index_diagnostics()["last_bypass_reason"] == hi.REASON_COLD


def test_cooldown_expiry_retries_the_warm_and_then_serves(tmp_path, monkeypatch):
    """冷却只是止损，不是永久放弃：库能读了必须重新暖起来并开始服务。"""
    now = [0.0]
    store = _Store(tmp_path, monkeypatch, clock=lambda: now[0], warm_retry_seconds=60.0)
    store.recorder.failing = True
    store.search("预算与回读口径")
    assert store.index.warm_retry_blocked()

    store.recorder.failing = False
    store.search("预算与回读口径")                       # 冷却期内：不再尝试
    assert store.recorder.count == 0

    now[0] = 61.0
    hits = store.keys(store.search("预算与回读口径"))     # 冷却到期：再试一次
    assert store.recorder.count > 0
    assert store.index.resident_chunks == _total_chunks(store)
    assert hits


def test_invalidation_clears_the_cooldown_so_a_changed_corpus_retries(tmp_path, monkeypatch):
    """库里的内容变了（写路径/口径变更/整体作废）⇒ 必须允许立刻再暖一次，不许被冷却挡住。"""
    store = _Store(tmp_path, monkeypatch)
    store.recorder.failing = True
    store.search("预算与回读口径")
    assert store.index.warm_retry_blocked()

    store.index.reset(reason="corpus changed")
    assert not store.index.warm_retry_blocked(), "整体作废之后冷却没清，下次检索仍不敢读库"
    store.recorder.failing = False
    store.recorder.calls.clear()
    hits = store.keys(store.search("预算与回读口径"))
    assert store.recorder.count > 0 and hits


def test_roster_page_defaults_below_the_sqlite_cap_and_env_is_fail_safe(monkeypatch):
    """默认页大小必须留在 SQLite 变量上限之下；未知/0/负数一律回落到默认值。"""
    assert 0 < hi.DEFAULT_ROSTER_PAGE < SQLITE_VARIABLE_CAP, hi.DEFAULT_ROSTER_PAGE
    monkeypatch.delenv(hi.HOT_INDEX_ROSTER_PAGE_ENV, raising=False)
    assert hi.HotSetIndex().roster_page == hi.DEFAULT_ROSTER_PAGE
    monkeypatch.setenv(hi.HOT_INDEX_ROSTER_PAGE_ENV, "3")
    assert hi.HotSetIndex().roster_page == 3
    for junk in ("0", "-5", "abc", ""):
        monkeypatch.setenv(hi.HOT_INDEX_ROSTER_PAGE_ENV, junk)
        assert hi.HotSetIndex().roster_page == hi.DEFAULT_ROSTER_PAGE, junk
    monkeypatch.delenv(hi.HOT_INDEX_WARM_RETRY_SECONDS_ENV, raising=False)
    assert hi.HotSetIndex()._warm_retry_seconds == hi.DEFAULT_WARM_RETRY_SECONDS
    monkeypatch.setenv(hi.HOT_INDEX_WARM_RETRY_SECONDS_ENV, "not-a-number")
    assert hi.HotSetIndex()._warm_retry_seconds == hi.DEFAULT_WARM_RETRY_SECONDS
