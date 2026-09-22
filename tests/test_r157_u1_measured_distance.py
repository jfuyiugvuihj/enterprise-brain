# -*- coding: utf-8 -*-
"""R157：U1 那枚前置必须「量得出来」，也必须在量不拢时照旧拒。

为什么有这一单：`scripts/compare_vector_recall.py` 的 U1 判据只看 collection 的 metadata，
而真实安装里它一直是 None —— 写入侧建集合时不写 hnsw:space，Chroma 用自己的默认值。
于是那条 `space != scope` 在**任何一台装过这套的客户机上恒成立**：09-22 双写窗第一次跑到
这里就撞死在退出码 2（`[前置不满足] collection 距离=未记录`），P3 逐题对比从没跑过。

修法不是放宽判据，是换一种判据：同一批向量在 l2 / cosine / inner_product 下排序不同，
所以拿 collection 自己返回的顺序对一遍就知道它用哪个距离（只读，不写一字节）。
量不拢——样本不足、维度不齐、候选并列、谁的序都对不上——仍然返回空串走退出码 2。

判据（每枚都点名，缺一不收）：
  ⓪ 样本集自己先自证：三枚候选算符给出三份互不相同的序，且内部无并列（否则下面全是自欺）；
  ① 记了 metadata 就用记录值，且一次都不问 collection.query；
  ② 没记时能按实测排序认出 l2 / cosine / inner_product（三枚各自独立，两枚探针都要对）；
  ③ 序同时属于多个候选（向量同模长时三者同序）⇒ 空串 + 具名「并列」，不许挑一个；
  ④ 谁的序都对不上 / 两枚探针各属一个候选 ⇒ 空串，不许"取多数"、不许"最接近的那个"；
  ⑤ 样本不足 / 维度不齐 / query 空手 ⇒ 都是空串，不许崩，且样本不足时压根不去问序；
  ⑥ main()：测不拢 ⇒ return 2 且不产出结论文件；量出来 ⇒ 那个算符真的进了 PG 那条 SQL；
  ⑦ 同源钉：写入侧确实还不记 hnsw:space，候选表恰好等于 PG 能声明的那三种。
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

#: 14 枚二维向量，故意不归一化：模长两两不同，于是 l2 / cosine / inner_product 三份排序
#: 两两不同、内部无并列（⓪ 现场算一遍钉死）。数字是搜出来的，不是随手写的。
VECTORS = [
    [3.0, 4.0], [6.3, 1.9], [1.3, 1.1], [-1.3, 3.4], [6.7, -0.4], [1.2, 5.6],
    [3.7, -1.6], [2.2, 2.1], [-2.3, -0.1], [7.2, 4.1], [1.2, -2.1], [5.7, 6.4],
    [-1.3, 5.4], [3.8, 1.4],
]
IDS = ["v%02d" % index for index in range(len(VECTORS))]
PROBE_INDICES = [0, len(VECTORS) // 2]

#: 12 枚**同模长**（=5）的向量：同模长时三种算符对同一个探针给出同一份排序，
#: 这正是"并列不许挑一个"那种形状。(-4.8, 1.4) 与 (4.8, -1.4) 用来破 (±4, ∓3) 的点积并列。
UNIT = [
    [3.0, 4.0], [4.0, 3.0], [5.0, 0.0], [0.0, 5.0], [-3.0, 4.0], [-4.8, 1.4],
    [-5.0, 0.0], [-4.0, -3.0], [-3.0, -4.0], [0.0, -5.0], [3.0, -4.0], [4.8, -1.4],
]
UNIT_IDS = ["u%02d" % index for index in range(len(UNIT))]


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
    return [vectors_name for _, vectors_name in
            [(None, index) for _, index in scored]]


def _permutation(metric, probe_index=0):
    return [IDS[index] for index in _order(metric, VECTORS, probe_index)]


class FakeCollection:
    """只回答三件事：metadata、按 limit 取样本、按探针返回一个**给定**的序。"""

    def __init__(self, *, metadata=None, vectors=None, ids=None, order_for=None,
                 ragged=False, empty_query=False):
        self.metadata = metadata
        self.vectors = [list(vector) for vector in (VECTORS if vectors is None else vectors)]
        self.ids = list(IDS if ids is None else ids)
        self.order_for = dict(order_for or {})
        self.ragged = ragged
        self.empty_query = empty_query
        self.calls = []

    def get(self, include=None, limit=None):
        self.calls.append(("get", limit))
        picked = self.ids[:limit] if limit else list(self.ids)
        rows = [self.vectors[self.ids.index(name)] for name in picked]
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
        return {"ids": [list(order)[:n_results]]}


def _measured_orders(metric, ids=IDS, vectors=VECTORS):
    orders = {}
    for index in PROBE_INDICES:
        order = [ids[position] for position in _order(metric, vectors, index)]
        orders[ids[index]] = order
    return orders


# ----------------------------------------------------------------------- ⓪ 自证
def test_the_sample_set_discriminates_all_three():
    by_metric = {}
    for index in PROBE_INDICES:
        for metric in SCRIPT._U1_CANDIDATES:
            keys = [round(_key(metric, vector, VECTORS[index]), 9) for vector in VECTORS]
            assert len(set(keys)) == len(keys), (index, metric, "样本里有并列，换向量")
            assert min(abs(a - b) for i, a in enumerate(keys) for b in keys[i + 1:]) > 1e-3
            by_metric[(index, metric)] = keys
    for index in PROBE_INDICES:
        probe = VECTORS[index]
        l2 = [ids for _, ids in sorted(zip(by_metric[(index, "l2")], IDS))][:8]
        cos = [ids for _, ids in sorted(zip(by_metric[(index, "cosine")], IDS))][:8]
        ip = [ids for _, ids in sorted(zip(by_metric[(index, "inner_product")], IDS))][:8]
        assert l2 != cos and l2 != ip and cos != ip, (index, l2[:4], cos[:4], ip[:4])


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
    collection = FakeCollection(metadata=None, order_for=_measured_orders(metric))
    name, evidence = SCRIPT.resolve_chroma_distance(collection)
    assert name == metric, (metric, name, evidence)
    assert evidence["source"] == "measured"
    assert evidence["matched"] == [metric]
    assert evidence["sampled"] == len(IDS)
    assert evidence["probes"] == SCRIPT.U1_PROBES
    assert evidence["reason"] == ""
    assert [call[0] for call in collection.calls] == ["get"] + ["query"] * SCRIPT.U1_PROBES


def test_a_single_probe_is_enough_and_the_sample_floor_is_honoured():
    collection = FakeCollection(metadata=None, order_for={IDS[0]: _permutation("l2")})
    name, evidence = SCRIPT.resolve_chroma_distance(collection, probes=1)
    assert name == "l2", evidence
    assert evidence["probes"] == 1
    assert SCRIPT.U1_MIN_SAMPLES <= len(IDS) <= SCRIPT.U1_SAMPLE_LIMIT


# --------------------------------------------------------------------------- ③
def test_candidates_that_agree_are_refused_not_guessed():
    orders = {UNIT_IDS[0]: _permutation_all("l2", 0), UNIT_IDS[len(UNIT) // 2]:
              _permutation_all("l2", len(UNIT) // 2)}
    collection = FakeCollection(metadata=None, vectors=UNIT, ids=UNIT_IDS, order_for=orders)
    name, evidence = SCRIPT.resolve_chroma_distance(collection)
    assert name == "", evidence
    assert "并列" in evidence["reason"]
    assert set(evidence["matched"]) >= {"l2", "cosine"}


def _permutation_all(metric, probe_index):
    return [UNIT_IDS[index] for index in _order(metric, UNIT, probe_index)]


# --------------------------------------------------------------------------- ④
def test_an_order_belonging_to_no_candidate_is_refused():
    collection = FakeCollection(metadata=None, order_for={"*": list(reversed(_permutation("l2")))})
    name, evidence = SCRIPT.resolve_chroma_distance(collection)
    assert name == ""
    assert "不属于任何候选算子" in evidence["reason"]
    assert evidence["matched"] == []


def test_the_two_probes_have_to_agree():
    # 第一枚像 l2、第二枚像 cosine：这不是"取多数"，这是测不出来。
    orders = {IDS[PROBE_INDICES[0]]: _permutation("l2", PROBE_INDICES[0]),
              IDS[PROBE_INDICES[1]]: _permutation("cosine", PROBE_INDICES[1])}
    name, evidence = SCRIPT.resolve_chroma_distance(FakeCollection(order_for=orders))
    assert name == ""
    assert "不属于任何候选算子" in evidence["reason"]


def test_empty_query_result_is_refused_not_crashed():
    name, evidence = SCRIPT.resolve_chroma_distance(
        FakeCollection(empty_query=True, order_for={"*": _permutation("l2")}))
    assert name == ""
    assert "没返回任何东西" in evidence["reason"]


# --------------------------------------------------------------------------- ⑤
def test_too_few_samples_is_refused_before_any_query():
    floor = SCRIPT.U1_MIN_SAMPLES
    keep_ids = IDS[:floor - 1]
    keep_vectors = VECTORS[:floor - 1]
    collection = FakeCollection(vectors=keep_vectors, ids=keep_ids,
                                order_for={"*": list(keep_ids)})
    name, evidence = SCRIPT.resolve_chroma_distance(collection)
    assert name == ""
    assert "样本只有" in evidence["reason"]
    assert [call[0] for call in collection.calls] == ["get"], "样本不够就不该去问序"


def test_ragged_widths_is_refused_with_a_reason():
    name, evidence = SCRIPT.resolve_chroma_distance(
        FakeCollection(ragged=True, order_for={"*": _permutation("l2")}))
    assert name == ""
    assert "维度不齐" in evidence["reason"]


# --------------------------------------------------------------------------- ⑥
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
        order_for={"*": list(reversed(_permutation("l2")))}))
    code = SCRIPT.main(["--out", str(out)])
    printed = capsys.readouterr().out
    assert code == 2, printed
    assert "U1 判读" in printed and "前置不满足" in printed
    assert not out.exists(), "测不拢时不许产出结论文件"


def test_main_sends_the_measured_operator_to_pg(tmp_path, capsys, monkeypatch):
    import app.rag.retriever as retriever_module

    seen = {}
    orders = _measured_orders("cosine")
    orders["*"] = _permutation("cosine")

    def fake_recall(connection, **kwargs):
        seen.update(kwargs)
        return list(orders["*"][:kwargs["k"]])

    class QuestionCollection(FakeCollection):
        def query(self, query_embeddings=None, n_results=None):
            probe = [float(value) for value in (query_embeddings or [[]])[0]]
            if probe in self.vectors:
                return super().query(query_embeddings, n_results)
            self.calls.append(("question", n_results))
            return {"ids": [list(self.order_for["*"])[:n_results]]}

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


# --------------------------------------------------------------------------- ⑦
def test_the_write_side_still_does_not_record_hnsw_space():
    """同源钉：①② 的分工（记了就用、没记就量）成立的前提，是写入侧确实不记。

    哪天 retriever 建集合时补上了 hnsw:space（那是好事，U1 从此不用量），本枚会红——
    红的时候请一起改 docs/handoff/2026-09-17-pgvector-adoption-plan.md §8.5 与本文件顶部散文，
    别只把本枚删掉。
    """
    source = (ROOT / "app" / "rag" / "retriever.py").read_text(encoding="utf-8")
    assert "hnsw:space" not in source, (
        "写入侧开始记录距离了：metadata 分支会变成主路径，§8.5 与脚本注释要一起改")


def test_the_candidate_table_covers_everything_pg_can_declare():
    # 0010 的 CHECK 只收 l2|cosine|ip；候选表少一个，实测就会"谁的序都对不上"→ 假拒。
    assert set(SCRIPT._U1_CANDIDATES) == set(SCRIPT.DISTANCE_OPERATORS)
    for stored in ("l2", "cosine", "ip"):
        assert SCRIPT.canonical_distance(stored) in SCRIPT._U1_CANDIDATES
    migration = (ROOT / "migrations" / "0010_pgvector_chunks.sql").read_text(encoding="utf-8")
    assert "distance_function IN ('l2', 'cosine', 'ip')" in migration, "0010 的允许集改口了，同步候选表"


def test_an_empty_candidate_table_refuses_instead_of_picking_one(monkeypatch):
    # 反证形状：把候选表清空 = 什么都测不出来，绝不能退化成"随便挑一个"。
    monkeypatch.setattr(SCRIPT, "_U1_CANDIDATES", ())
    name, evidence = SCRIPT.resolve_chroma_distance(
        FakeCollection(order_for={"*": _permutation("l2")}))
    assert name == ""
    assert "不属于任何候选算子" in evidence["reason"]
