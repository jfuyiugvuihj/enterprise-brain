"""R44 判据③④⑥（单元层）：热集的服务判定、pre-filter 次序、口径隔离、观测计数。

这一份不碰 chromadb：HotSetIndex 的服务判定与截断次序是自足的逻辑，用假行就能钉死。
与真实向量库的一致性比对在 tests/test_r44_hot_index_chroma.py。
"""

import pytest

from app.rag import hot_index as hi

SCOPE_A = ("chroma", "model-a", 4, "v1")
SCOPE_B = ("chroma", "model-b", 4, "v1")
QUERY = [0.0, 0.0, 0.0, 0.0]


def _row(chunk_id, document="text", classification=1, department="sales", vector=None,
         cold=False):
    metadata = {
        "filename": chunk_id.rsplit("_", 1)[0],
        "chunk_index": 0,
        "classification": classification,
        "department": department,
    }
    if vector is None:
        vector = [1.0, 0.0, 0.0, 0.0]
    if cold:
        # 库里存在这一行、但这一条读不出向量（_JsonCollection 态/回读失败）：只能进冷表
        vector = None
    return (chunk_id, document, metadata, vector)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv(hi.HOT_INDEX_ENV, "1")
    hi.reset_hot_index_diagnostics()
    yield
    hi.reset_hot_index_diagnostics()


@pytest.fixture
def off(monkeypatch):
    monkeypatch.delenv(hi.HOT_INDEX_ENV, raising=False)
    hi.reset_hot_index_diagnostics()
    yield
    hi.reset_hot_index_diagnostics()


def _index(**kwargs):
    kwargs.setdefault("max_chunks", 100)
    kwargs.setdefault("roster_ttl_seconds", 3600.0)
    return hi.HotSetIndex(**kwargs)


def test_switch_treats_everything_unknown_as_off(monkeypatch):
    """开关口径抄 R58：未设置、空、拼错都算关，只有 1/true/yes/on 算开。"""
    for raw in ("", "ture", "0", "false", "maybe"):
        monkeypatch.setenv(hi.HOT_INDEX_ENV, raw)
        assert hi.hot_index_enabled() is False
    for raw in ("1", "true", "YES", "on"):
        monkeypatch.setenv(hi.HOT_INDEX_ENV, raw)
        assert hi.hot_index_enabled() is True


def test_disabled_index_serves_nothing(off):
    index = _index()
    index.populate([_row("a_0")], scope_key=SCOPE_A)
    assert index.rank(QUERY, 3, scope_key=SCOPE_A) is None
    assert index.bypass_reason(scope_key=SCOPE_A, query_vector=QUERY) == hi.REASON_DISABLED


def test_cold_rows_block_serving_until_the_roster_is_covered(on):
    """库里还有一条读不出向量的行 ⇒ 热集不许给结果（判据②的恒等前提）。"""
    index = _index()
    index.populate([_row("a_0"), _row("b_0", cold=True)], scope_key=SCOPE_A)
    assert index.resident_chunks == 1 and index.cold_chunks == 1
    assert index.rank(QUERY, 3, scope_key=SCOPE_A) is None
    assert index.bypass_reason(scope_key=SCOPE_A, query_vector=QUERY) == hi.REASON_INCOMPLETE


def test_cold_rows_outside_the_filter_do_not_block(on):
    """冷条目在本次 where 下召不回来 ⇒ 热集给的结果与向量库必然同序同 id。"""
    index = _index()
    index.populate([_row("a_0", department="sales"),
                    _row("b_0", department="hr", cold=True)], scope_key=SCOPE_A)
    hits = index.rank(QUERY, 3, where={"department": "sales"}, scope_key=SCOPE_A)
    assert [item[1] for item in hits] == ["a_0"]


def test_prefilter_runs_before_truncation(on):
    """R45 的召回饥饿形状：全局第一是被禁文档时，受限用户仍要拿到合法那份，而不是空。"""
    index = _index()
    rows = [_row("forbid_0", department="hr", vector=[0.0, 0.0, 0.0, 0.0]),
            _row("allow_0", department="sales", vector=[5.0, 0.0, 0.0, 0.0])]
    index.populate(rows, scope_key=SCOPE_A)
    pred = lambda item: item["department"] == "sales"  # noqa: E731
    hits = index.rank(QUERY, 1, pred=pred, scope_key=SCOPE_A)
    assert [item[1] for item in hits] == ["allow_0"], hits


def test_forbidden_document_is_never_returned(on):
    index = _index()
    index.populate([_row("a_0", department="sales"),
                    _row("b_0", department="hr")], scope_key=SCOPE_A)
    pred = lambda item: item["department"] == "sales"  # noqa: E731
    hits = index.rank(QUERY, 10, pred=pred, scope_key=SCOPE_A)
    assert [item[1] for item in hits] == ["a_0"], hits


def test_missing_classification_fails_closed(on):
    """元数据缺密级键时按 None 交给谓词，不补 1 级（R57 口径）。"""
    seen = []
    index = _index()
    row = _row("a_0")
    row[2].pop("classification")
    index.populate([row], scope_key=SCOPE_A)

    def pred(item):
        seen.append(item["classification"])
        return item["classification"] is not None

    assert index.rank(QUERY, 3, pred=pred, scope_key=SCOPE_A) == []
    assert seen == [None]


def test_scope_switch_invalidates_every_entry(on):
    """R22 的缓存版：换模型 = 旧条目一条都不留，也不跨版本复用。"""
    index = _index()
    index.populate([_row("a_0")], scope_key=SCOPE_A)
    assert index.scope_key == SCOPE_A
    assert index.adopt_scope(SCOPE_B) == "reset"
    assert index.resident_chunks == 0 and index.scope_key == SCOPE_B
    assert index.bypass_reason(scope_key=SCOPE_B, query_vector=QUERY) == hi.REASON_COLD


def test_entries_self_report_their_scope(on):
    index = _index()
    index.populate([_row("a_0")], scope_key=SCOPE_A)
    assert index._entries["a_0"].scope_key == SCOPE_A


def test_stale_scope_key_cannot_query_a_live_index(on):
    index = _index()
    index.populate([_row("a_0")], scope_key=SCOPE_A)
    assert index.rank(QUERY, 3, scope_key=SCOPE_B) is None
    assert index.bypass_reason(scope_key=SCOPE_B, query_vector=QUERY) == hi.REASON_SCOPE_MISMATCH


def test_note_delete_drops_resident_and_cold_rows(on):
    index = _index()
    index.populate([_row("a_0"), _row("b_0", cold=True)], scope_key=SCOPE_A)
    assert index.note_delete(["b_0"], scope_key=SCOPE_A) == 0  # 走的是冷表
    assert index.cold_chunks == 0
    assert index.note_delete(["a_0"], scope_key=SCOPE_A) == 1
    assert index.resident_chunks == 0


def test_budget_exhaustion_sends_new_rows_to_the_cold_table(on):
    index = _index(max_chunks=1)
    stats = index.populate([_row("a_0"), _row("b_0")], scope_key=SCOPE_A)
    assert stats == {"resident": 1, "cold": 1}
    assert index.rank(QUERY, 3, scope_key=SCOPE_A) is None


def test_eviction_drops_the_least_recently_queried_document(on):
    """淘汰按"整篇文档最久没被查过"，而且刚写入的那篇最热：不许随机、也不许先挤新文档。"""
    clock = {"now": 100.0}
    index = _index(max_chunks=2)
    index._clock = lambda: clock["now"]
    index.populate([_row("a_0"), _row("b_0")], scope_key=SCOPE_A)
    clock["now"] = 150.0
    assert [item[1] for item in index.rank(QUERY, 1, scope_key=SCOPE_A)] == ["a_0"]
    clock["now"] = 200.0
    index.note_write(ids=["c_0"], documents=["新上传的文档"], metadatas=[_row("c_0")[2]],
                     embeddings=[[1.0, 0.0, 0.0, 0.0]], scope_key=SCOPE_A)
    assert index.resident_chunks == 2
    assert sorted(index._entries) == ["a_0", "c_0"], sorted(index._entries)
    assert list(index._cold) == ["b_0"], index._cold
    assert index.cold_chunks == 1


def test_expired_roster_bypasses(on):
    clock = {"now": 1000.0}
    index = _index(roster_ttl_seconds=30.0)
    index._clock = lambda: clock["now"]
    index.populate([_row("a_0")], scope_key=SCOPE_A)
    assert index.rank(QUERY, 3, scope_key=SCOPE_A) is not None
    clock["now"] += 31.0
    assert index.rank(QUERY, 3, scope_key=SCOPE_A) is None
    assert index.bypass_reason(scope_key=SCOPE_A, query_vector=QUERY) == hi.REASON_STALE_ROSTER


def test_store_without_vectors_bypasses(on):
    index = _index()
    index.populate([_row("a_0")], scope_key=SCOPE_A)
    assert index.rank(QUERY, 3, scope_key=SCOPE_A, stores_vectors=False) is None
    assert (index.bypass_reason(scope_key=SCOPE_A, stores_vectors=False,
                               query_vector=QUERY) == hi.REASON_NO_VECTORS)


def test_diagnostics_count_without_changing_results(on):
    index = _index()
    index.populate([_row("a_0")], scope_key=SCOPE_A)
    before = hi.hot_index_diagnostics()
    assert index.rank(QUERY, 3, scope_key=SCOPE_A) is not None
    assert index.rank(QUERY, 3, scope_key=SCOPE_B) is None
    after = hi.hot_index_diagnostics()
    assert after["hits"] - before["hits"] == 1
    assert after["misses"] - before["misses"] == 1
    assert after["resident_chunks"] == 1
    assert after["last_bypass_reason"] == hi.REASON_SCOPE_MISMATCH
    assert set(after) == {"hits", "misses", "invalidations", "resident_chunks",
                          "last_bypass_reason"}


def test_current_scope_key_comes_from_the_r22_gate():
    """口径源只有一个：app/rag/indexing.configured_embedding_scope()。"""
    from app.rag import indexing

    scope = hi.current_scope_key(index_version_id="v9")
    declared = indexing.configured_embedding_scope()
    assert scope == (indexing.INDEX_BACKEND, declared.embedding_model,
                     declared.dimension, "v9")
