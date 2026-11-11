# -*- coding: utf-8 -*-
"""R157：U1 那枚前置必须「量得出来」，也必须在量不拢时照旧拒。

为什么有这一单：`scripts/compare_vector_recall.py` 的 U1 判据只看 collection 的 metadata，
而真实安装里它一直是 None —— 写入侧建集合时不写 hnsw:space，Chroma 用自己的默认值。
于是那条 `space != scope` 在**任何一台装过这套的客户机上恒成立**：09-22 双写窗第一次真跑到
P3 就撞死在退出码 2（`[前置不满足] collection 距离=未记录`），P3 逐题对比从没跑过。

修法不是放宽判据，是换一种判据：同一批向量在 l2 / cosine / inner_product 下排序不同，
拿 collection 自己返回的顺序对一遍就知道它用哪个距离（只读，不写一字节）。
两把真形状钉是被这台机器教出来的，不是想出来的：
  · chromadb 的 get()["embeddings"] 是 numpy.ndarray，不是 list（`rows or []` 当场抛）；
  · collection.query 排的是**整库**，只拿采样那几十枚比序，谁都对不上（第一次误判由此而来），
    所以返回集合里落在采样之外的命中必须按 id 取回向量再比。
量不拢——样本不足、维度不齐、问回的名不够、探针不在自己的序里、候选并列、谁的序都对不上——
一律空串，仍走原来的退出码 2。宁可不跑，不猜。

判据（每枚点名，缺一不收）：
  ⓪ 样本集自证：三种候选算符对同一探针给出三份互不相同、内部无并列的序；
  ① 记了 metadata 就用记录值，且一次都不问 query；
  ② 没记时按实测序认出 l2 / cosine / inner_product（三枚各自独立，两枚探针都要对）；
  ③ 候选并列 ⇒ 拒，不许挑一个；④ 谁的序都对不上 / 两枚探针不一致 ⇒ 拒，不许取多数；
  ⑤ 样本不足 / 维度不齐 / query 空手 / 名不够 / 探针不在返回里 / 向量补不回来 ⇒ 都拒且不崩；
  ⑥ 真形状：embeddings 是 ndarray、ids 是 numpy.str_、返回集合超出采样时要按 id 补向量；
  ⑦ main()：测不拢 ⇒ 退出码 2 且不产出结论文件；量出来 ⇒ 那个算符真的进了 PG 那条 SQL；
  ⑧ 同源钉：写入侧确实还不记 hnsw:space，候选表恰好等于 PG 能声明的那三种。
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "compare_vector_recall.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("compare_vector_recall_r157", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()

#: 14 枚二维向量，故意不归一化：模长两两不同 ⇒ 三种算符对同一探针给出三份不同的序，
#: 且内部无并列（⓪ 现场算一遍钉死）。数字是搜出来的，不是随手写的。
VECTORS = [
    [3.0, 4.0], [6.3, 1.9], [1.3, 1.1], [-1.3, 3.4], [6.7, -0.4], [1.2, 5.6],
    [3.7, -1.6], [2.2, 2.1], [-2.3, -0.1], [7.2, 4.1], [1.2, -2.1], [5.7, 6.4],
    [-1.3, 5.4], [3.8, 1.4],
]
IDS = ["v%02d" % index for index in range(len(VECTORS))]
PROBE_INDICES = [0, len(VECTORS) // 2]

#: 同模长（=5）的 12 枚：三种算符同序，这就是"并列不许挑一个"那种形状。
#: (-4.8, 1.4) / (4.8, -1.4) 用来破 (±4, ∓3) 的点积并列。
UNIT = [
    [3.0, 4.0], [4.0, 3.0], [5.0, 0.0], [0.0, 5.0], [-3.0, 4.0], [-4.8, 1.4],
    [-5.0, 0.0], [-4.0, -3.0], [-3.0, -4.0], [0.0, -5.0], [3.0, -4.0], [4.8, -1.4],
]
UNIT_IDS = ["u%02d" % index for index in range(len(UNIT))]

#: 20 枚：前 14 枚与上面同源，后 6 枚只在"整库比采样大"那一枚判据里出场。
WIDE = VECTORS + [[9.1, 2.4], [-6.2, 8.3], [8.8, -5.1], [2.9, 9.4], [-8.6, -2.7], [10.2, 3.1]]
WIDE_IDS = IDS + ["x%d" % index for index in range(6)]


def _key(metric, vector, probe):
    """测试自己的实现，刻意与脚本不同形：l2 走 math.dist，cosine 走 math.acos（对 cos 单调），
    inner_product 走点积取负。写成两份，才谈得上互相校验。"""
    dot = sum(a * b for a, b in zip(probe, vector))
    if metric == "l2":
        return math.dist(probe, vector)
    if metric == "cosine":
        cosine = dot / (math.hypot(*probe) * math.hypot(*vector))
        return math.acos(max(-1.0, min(1.0, cosine)))
    return -dot


def _order(metric, vectors, probe_index):
    probe = vectors[probe_index]
    scored = sorted(((round(_key(metric, vector, probe), 9), index)
                     for index, vector in enumerate(vectors)))
    return [index for _, index in scored]


def _permutation(metric, vectors=VECTORS, ids=IDS, probe_index=0):
    return [ids[index] for index in _order(metric, vectors, probe_index)]


class FakeCollection:
    """回答四件事：metadata、按 limit 采样、按 ids 补向量、按探针返回一个**给定**的序。"""

    def __init__(self, *, metadata=None, vectors=None, ids=None, order_for=None,
                 ragged=False, empty_query=False, short_query=0, withhold=()):
        self.metadata = metadata
        self.vectors = [list(vector) for vector in (VECTORS if vectors is None else vectors)]
        self.ids = list(IDS if ids is None else ids)
        self.order_for = dict(order_for or {})
        self.ragged = ragged
        self.empty_query = empty_query
        self.short_query = short_query
        self.withhold = set(withhold)
        self.calls = []

    def _vector(self, name):
        return self.vectors[self.ids.index(name)]

    def get(self, include=None, limit=None, ids=None):
        if ids is not None:
            self.calls.append(("get-ids", len(ids)))
            picked = [name for name in ids if name not in self.withhold]
            return {"ids": picked, "embeddings": [self._vector(name) for name in picked]}
        self.calls.append(("get", limit))
        picked = self.ids[:limit] if limit else list(self.ids)
        rows = [self._vector(name) for name in picked]
        if self.ragged:
            rows = [row[:1] for row in rows]
            rows[3] = []
        return {"ids": picked, "embeddings": rows}

    def query(self, query_embeddings=None, n_results=None):
        self.calls.append(("query", len(query_embeddings or []), n_results))
        if self.empty_query:
            return {"ids": [[]]}
        probe = [float(value) for value in (query_embeddings or [[]])[0]]
        slot = self.ids[self.vectors.index(probe)] if probe in self.vectors else "*"
        order = self.order_for.get(slot) or self.order_for.get("*")
        assert order is not None, "测试没给这一枚探针的预期序：%s" % slot
        take = n_results - self.short_query if self.short_query else n_results
        return {"ids": [[str(name) for name in list(order)[:max(0, take)]]]}


def _orders_for(metric, vectors=VECTORS, ids=IDS, probe_indices=None):
    return {ids[index]: _permutation(metric, vectors, ids, index)
            for index in (PROBE_INDICES if probe_indices is None else probe_indices)}


# ----------------------------------------------------------------------- ⓪ 自证
def test_the_sample_set_discriminates_all_three():
    for index in PROBE_INDICES:
        probe = VECTORS[index]
        seen = {}
        for metric in SCRIPT._U1_CANDIDATES:
            keys = [round(_key(metric, vector, probe), 9) for vector in VECTORS]
            assert len(set(keys)) == len(keys), (index, metric, "样本里有并列，换向量")
            assert min(abs(a - b) for i, a in enumerate(keys) for b in keys[i + 1:]) > 1e-3
            seen[metric] = [IDS[position] for position in sorted(
                range(len(keys)), key=lambda position: keys[position])]
        assert seen["l2"] != seen["cosine"] and seen["l2"] != seen["inner_product"] \
            and seen["cosine"] != seen["inner_product"], index


# --------------------------------------------------------------------------- ①
def test_recorded_metadata_is_used_without_asking_the_collection():
    for space, canonical in (("l2", "l2"), ("cosine", "cosine"), ("ip", "inner_product")):
        collection = FakeCollection(metadata={"hnsw:space": space})
        name, evidence = SCRIPT.resolve_chroma_distance(collection)
        assert name == canonical, (space, name)
        assert evidence["source"] == "metadata"
        assert evidence["sampled"] == 0 and evidence["probes"] == 0
        assert evidence["matched"] == [canonical]
    collection = FakeCollection(metadata={"hnsw:space": "l2"})
    SCRIPT.resolve_chroma_distance(collection)
    assert [call[0] for call in collection.calls] == [], collection.calls


# --------------------------------------------------------------------------- ②
@pytest.mark.parametrize("metric", ["l2", "cosine", "inner_product"])
def test_unrecorded_space_is_measured_from_the_returned_order(metric):
    collection = FakeCollection(metadata=None, order_for=_orders_for(metric))
    name, evidence = SCRIPT.resolve_chroma_distance(collection)
    assert name == metric, (metric, name, evidence)
    assert evidence["source"] == "measured"
    assert evidence["matched"] == [metric]
    assert evidence["sampled"] == len(IDS)
    assert evidence["probes"] == SCRIPT.U1_PROBES
    assert evidence["returned"] == SCRIPT.U1_MIN_RESULTS
    assert evidence["reason"] == ""


def test_a_single_probe_is_enough_and_the_sample_floor_is_honoured():
    collection = FakeCollection(metadata=None, order_for={IDS[0]: _permutation("l2")})
    name, evidence = SCRIPT.resolve_chroma_distance(collection, probes=1)
    assert name == "l2", evidence
    assert evidence["probes"] == 1
    assert SCRIPT.U1_MIN_SAMPLES <= len(IDS) <= SCRIPT.U1_SAMPLE_LIMIT


# --------------------------------------------------------------------------- ③
def test_candidates_that_agree_are_refused_not_guessed():
    unit_probes = [0, len(UNIT) // 2]
    orders = {UNIT_IDS[index]: _permutation("l2", UNIT, UNIT_IDS, index)
              for index in unit_probes}
    collection = FakeCollection(metadata=None, vectors=UNIT, ids=UNIT_IDS, order_for=orders)
    name, evidence = SCRIPT.resolve_chroma_distance(collection)
    assert name == "", evidence
    assert "并列" in evidence["reason"]
    assert set(evidence["matched"]) >= {"l2", "cosine"}


# --------------------------------------------------------------------------- ④
def _nobody_order():
    """探针留在第 0 名（否则先撞"探针不在自己返回里"那一步），只打乱后面的名次。"""
    full = _permutation("l2")
    scrambled = [full[0]] + list(reversed(full[1:]))
    for metric in SCRIPT._U1_CANDIDATES:
        assert scrambled != _permutation(metric), (metric, "这份乱序其实属于某个候选")
    return scrambled


def test_an_order_belonging_to_no_candidate_is_refused():
    collection = FakeCollection(metadata=None, order_for={"*": _nobody_order()})
    name, evidence = SCRIPT.resolve_chroma_distance(collection)
    assert name == ""
    assert "不属于任何候选算子" in evidence["reason"]
    assert evidence["matched"] == []


def test_the_two_probes_have_to_agree():
    orders = {IDS[PROBE_INDICES[0]]: _permutation("l2", probe_index=PROBE_INDICES[0]),
              IDS[PROBE_INDICES[1]]: _permutation("cosine", probe_index=PROBE_INDICES[1])}
    name, evidence = SCRIPT.resolve_chroma_distance(FakeCollection(order_for=orders))
    assert name == ""
    assert "不属于任何候选算子" in evidence["reason"]


# --------------------------------------------------------------------------- ⑤
def test_empty_query_result_is_refused_not_crashed():
    name, evidence = SCRIPT.resolve_chroma_distance(
        FakeCollection(empty_query=True, order_for={"*": _permutation("l2")}))
    assert name == ""
    assert "探针只问回 0 名" in evidence["reason"]


def test_too_few_returned_ranks_is_refused():
    collection = FakeCollection(order_for={"*": _permutation("l2")}, short_query=3)
    name, evidence = SCRIPT.resolve_chroma_distance(collection)
    assert name == ""
    assert "少于" in evidence["reason"] and "排序比不出差别" in evidence["reason"]


def test_a_probe_that_is_not_in_its_own_result_is_refused():
    # 自己离自己最近，本该排第一；不在返回里就不是这三种算符算的序，不许拿第 0 名顶替。
    order = _permutation("l2")
    rotated = order[1:] + order[:1]
    name, evidence = SCRIPT.resolve_chroma_distance(
        FakeCollection(order_for={"*": rotated}))
    assert name == ""
    assert "探针没出现在自己返回的前" in evidence["reason"]


def test_too_few_samples_is_refused_before_any_query():
    floor = SCRIPT.U1_MIN_SAMPLES
    keep_ids, keep_vectors = IDS[:floor - 1], VECTORS[:floor - 1]
    collection = FakeCollection(vectors=keep_vectors, ids=keep_ids,
                                order_for={"*": list(keep_ids)})
    name, evidence = SCRIPT.resolve_chroma_distance(collection)
    assert name == "" and "样本只有" in evidence["reason"]
    assert [call[0] for call in collection.calls] == ["get"], "样本不够就不该去问序"


def test_ragged_widths_is_refused_with_a_reason():
    name, evidence = SCRIPT.resolve_chroma_distance(
        FakeCollection(ragged=True, order_for={"*": _permutation("l2")}))
    assert name == "" and "维度不齐" in evidence["reason"]


@pytest.mark.parametrize("shape", ["empty-dict", "none", "missing-keys"])
def test_an_empty_response_is_refused_not_crashed(shape):
    class EmptyCollection(FakeCollection):
        def get(self, include=None, limit=None, ids=None):
            self.calls.append(("get", limit))
            if shape == "none":
                return None
            if shape == "missing-keys":
                return {}
            return {"ids": [], "embeddings": []}

    name, evidence = SCRIPT.resolve_chroma_distance(EmptyCollection())
    assert name == "" and "样本只有 0 枚" in evidence["reason"], (shape, evidence)


# --------------------------------------------------------------------------- ⑥
def test_chromadb_hands_back_numpy_arrays_not_lists():
    """第一次真跑就是死在这里：get()["embeddings"] 是 numpy.ndarray，`rows or []` 当场抛
    "truth value of an array with more than one element is ambiguous"。假 collection 全用
    list 写的话一枚都拦不住，所以这一枚把真形状钉进来。"""
    numpy = pytest.importorskip("numpy")
    orders = [_permutation("l2", probe_index=index) for index in PROBE_INDICES]
    queue = list(orders)

    class NumpyCollection(FakeCollection):
        def get(self, include=None, limit=None, ids=None):
            payload = super().get(include=include, limit=limit, ids=ids)
            if payload and payload.get("embeddings") is not None:
                payload["embeddings"] = numpy.asarray(payload["embeddings"], dtype=numpy.float64)
            return payload

        def query(self, query_embeddings=None, n_results=None):
            self.calls.append(("query", len(query_embeddings or []), n_results))
            order = queue.pop(0)
            assert n_results == SCRIPT.U1_MIN_RESULTS, n_results
            return {"ids": [[numpy.str_(name) for name in order[:n_results]]]}

    collection = NumpyCollection()
    name, evidence = SCRIPT.resolve_chroma_distance(collection)
    assert name == "l2", evidence
    assert evidence["matched"] == ["l2"] and evidence["probes"] == SCRIPT.U1_PROBES
    assert queue == [], "两枚探针都该被问到"


def test_the_returned_set_is_bigger_than_the_sample_and_gets_hydrated():
    """真库形状：采样只有 12 枚，而 collection.query 排的是整库 20 枚。

    只拿采样集去比序，谁都对不上——09-22 第一次真跑正是这样把 l2 误判成
    "不属于任何候选算子"。所以落在采样之外的命中必须按 id 把向量取回来再比。
    """
    # 采样被压到 12 枚，脚本的探针位就成了 [0, 12 // 2]，测试得按同一把尺给序。
    orders = _orders_for("l2", WIDE, WIDE_IDS, probe_indices=[0, 6])
    collection = FakeCollection(vectors=WIDE, ids=WIDE_IDS, order_for=orders)
    name, evidence = SCRIPT.resolve_chroma_distance(collection, sample_limit=12)
    assert name == "l2", evidence
    hydration = [call for call in collection.calls if call[0] == "get-ids"]
    assert hydration, "没补向量就是在拿采样集冒充整库：%s" % collection.calls
    assert evidence["returned"] == SCRIPT.U1_MIN_RESULTS


def test_a_returned_hit_whose_vector_cannot_be_fetched_is_refused():
    orders = _orders_for("l2", WIDE, WIDE_IDS, probe_indices=[0, 6])
    sample = set(WIDE_IDS[:12])
    returned = orders[IDS[0]][:SCRIPT.U1_MIN_RESULTS]
    missing = [name for name in returned if name not in sample][:1]
    assert missing, "构造失败：返回集合该有采样之外的命中"
    collection = FakeCollection(vectors=WIDE, ids=WIDE_IDS, order_for=orders,
                                withhold=missing)
    name, evidence = SCRIPT.resolve_chroma_distance(collection, sample_limit=12)
    assert name == "" and "取不到向量" in evidence["reason"], evidence


# --------------------------------------------------------------------------- ⑦
class FakeConnection:
    def execute(self, sql, params=None):
        class Result:
            def fetchone(inner):
                return None

            def fetchall(inner):
                return []

        return Result()

    def close(self):
        pass


DRIFT_CLEAN = {"pg_vectors": len(IDS), "chroma_vectors": len(IDS), "only_in_pg": [],
               "only_in_chroma": [], "wrong_width": [], "all_zero_rows": 0,
               "index_version_id_null": 0, "chunks_rows": len(IDS),
               "chunks_with_backfilled_embedding": 0}


def _scope(distance="l2"):
    return {"embedding_model": "nomic-embed-text", "dimension": 2,
            "distance_function": distance, "column_type": "vector(2)"}


def test_main_refuses_and_writes_nothing_when_u1_cannot_be_measured(tmp_path, capsys, monkeypatch):
    out = tmp_path / "r157.json"
    monkeypatch.setattr(SCRIPT, "connect_read_only", lambda url: FakeConnection())
    monkeypatch.setattr(SCRIPT, "read_scope", lambda connection, table: _scope())
    monkeypatch.setattr(SCRIPT, "open_chroma", lambda directory, name: FakeCollection(
        order_for={"*": _nobody_order()}))
    code = SCRIPT.main(["--out", str(out)])
    printed = capsys.readouterr().out
    assert code == 2, printed
    assert "U1 判读" in printed and "前置不满足" in printed
    assert not out.exists(), "测不拢时不许产出结论文件"


def test_main_sends_the_measured_operator_to_pg(tmp_path, capsys, monkeypatch):
    import app.rag.retriever as retriever_module

    seen = {}
    full = _permutation("cosine")
    orders = _orders_for("cosine")
    orders["*"] = full

    def fake_recall(connection, **kwargs):
        seen.update(kwargs)
        return list(orders["*"][:kwargs["k"]])

    class QuestionCollection(FakeCollection):
        def query(self, query_embeddings=None, n_results=None):
            probe = [float(value) for value in (query_embeddings or [[]])[0]]
            if probe in self.vectors:
                return super().query(query_embeddings=query_embeddings, n_results=n_results)
            self.calls.append(("question", n_results))
            return {"ids": [list(full[:n_results])]}

    class StubEmbeddings:
        def embed_query(self, question):
            return [0.25, -0.5]

    collection = QuestionCollection(order_for=orders)
    monkeypatch.setattr(SCRIPT, "connect_read_only", lambda url: FakeConnection())
    monkeypatch.setattr(SCRIPT, "read_scope", lambda connection, table: _scope("cosine"))
    monkeypatch.setattr(SCRIPT, "open_chroma", lambda directory, name: collection)
    monkeypatch.setattr(SCRIPT, "pg_recall", fake_recall)
    monkeypatch.setattr(SCRIPT, "corpus_drift", lambda *a, **kw: dict(DRIFT_CLEAN))
    monkeypatch.setattr(SCRIPT, "load_questions",
                        lambda paths: [("fixture.jsonl", "q1", "报销额度是多少")])
    monkeypatch.setattr(retriever_module, "OllamaEmbeddings", StubEmbeddings)
    out = tmp_path / "r157.json"
    code = SCRIPT.main(["--out", str(out), "--k", "3"])
    printed = capsys.readouterr().out
    assert code == 0, printed + repr(seen)
    assert seen["operator"] == "<=>", seen
    assert "U1：collection 距离=cosine（来源=measured" in printed, printed
    payload = out.read_text(encoding="utf-8")
    assert '"source": "measured"' in payload and '"probes": 2' in payload


# --------------------------------------------------------------------------- ⑧
def test_the_write_side_still_does_not_record_hnsw_space():
    """哪天写入侧补上了 hnsw:space（那是好事，U1 从此不用量），本枚会红——红的时候请一起改
    docs/handoff/2026-09-17-pgvector-adoption-plan.md §8.5 与本文件顶部散文，别只删本枚。"""
    source = (ROOT / "app" / "rag" / "retriever.py").read_text(encoding="utf-8")
    assert "hnsw:space" not in source, (
        "写入侧开始记录距离了：metadata 分支会变成主路径，§8.5 与脚本注释要一起改")


def test_the_candidate_table_covers_everything_pg_can_declare():
    assert set(SCRIPT._U1_CANDIDATES) == set(SCRIPT.DISTANCE_OPERATORS)
    for stored in ("l2", "cosine", "ip"):
        assert SCRIPT.canonical_distance(stored) in SCRIPT._U1_CANDIDATES
    migration = (ROOT / "migrations" / "0010_pgvector_chunks.sql").read_text(encoding="utf-8")
    assert "distance_function IN ('l2', 'cosine', 'ip')" in migration, "0010 的允许集改口了，同步候选表"


def test_an_empty_candidate_table_refuses_instead_of_picking_one(monkeypatch):
    monkeypatch.setattr(SCRIPT, "_U1_CANDIDATES", ())
    name, evidence = SCRIPT.resolve_chroma_distance(
        FakeCollection(order_for={"*": _permutation("l2")}))
    assert name == ""
    assert "不属于任何候选算子" in evidence["reason"]
