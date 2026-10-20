# -*- coding: utf-8 -*-
"""R269 判据①②⑤：现网 Chroma「138 枚自探针取不到自己 / 21 题空 top-k」的机理钉。

一枚用例都不碰工作树的 chroma_db/：库一律开在 pytest 的 tmp_path 上，
模块级 autouse 夹具在整件跑完后再按 sha256 复比工作树索引清单（判据⑤ 的红线钉）。

本文件只钉今天实测得到的七件事：

  ① 段字节里只有一处可信——槽数。data_level0.bin/(132+4*dim+8) == length.bin/4
     == header.bin 第 6 枚 u32，三套独立口径必须相等，它们才是"图平面里有几枚元素"。
  ② sqlite 的 embeddings 表根本没有向量列 ⇒ 「get 读得到」与「query 问不到」不矛盾，
     向量的唯一副本就在图平面上。
  ③ app/rag/retriever.py:1357-1374 的重传路径（同 id 先 delete 再 add）让 count() 持平，
     而槽数每轮净增 N 枚、一枚都不回收 ⇒ 现网 39923 槽 / 1008 在册就是这么来的。
  ④ 只删不补也一样：删掉 40% 的记录，图平面一枚槽都不缩。
  ⑤ 零删除、纯 add 出来的稠密近重复语料，在 ef_search=100 下就有自探针问不到自己，
     而同样本 numpy 精确扫描一枚不漏 ⇒ 症状 A 属于读路径的近似性，不是持久状态损坏。
  ⑥ 把候选预算翻到语料量级，缺口变小 ⇒ 能把"读路径参数"和"状态损坏"切开。
  ⑦ 反证：95% 整档墓碑也不会把无过滤 query 打成空表 ⇒ "墓碑多"本身不是症状 B 的因。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

chromadb = pytest.importorskip("chromadb")
from chromadb.api.client import Client
from chromadb.config import Settings

COLLECTION = "enterprise_docs"          # 生产在用的那枚名字（app/rag/retriever.py:882）
DIM = 64
ELEM = 132 + 4 * DIM + 8                # size_data_per_element：邻接区 + 向量 + label
SETTINGS = Settings(anonymized_telemetry=False)
DOC = "深度学习入门：基于Python的理论与实现.pdf"   # 现网 126/586 枚不可达的那枚文档
WORKTREE_DB = Path(__file__).resolve().parents[1] / "chroma_db"


def _vectors(count, seed=20260926):
    rng = np.random.default_rng(seed)
    return (rng.random((count, DIM), dtype="float64") * 2.0 - 1.0).tolist()


def _ids(count):
    return ["%s_%d" % (DOC, index) for index in range(count)]


def _release() -> None:
    """放掉 chroma 的进程内单例，否则 Windows 下段文件还是开着。"""
    import gc

    gc.collect()
    Client.clear_system_cache()


def _open(path, hnsw=None):
    meta = {"hnsw:space": "l2"}
    meta.update({"hnsw:" + key: value for key, value in (hnsw or {}).items()})
    client = chromadb.PersistentClient(path=str(path), settings=SETTINGS)
    return client, client.get_or_create_collection(name=COLLECTION, metadata=meta)


def _add(collection, ids, vectors, step=500):
    for start in range(0, len(ids), step):
        collection.add(ids=ids[start:start + step], embeddings=vectors[start:start + step])


def _segment_dir(root):
    for entry in sorted(os.listdir(str(root))):
        candidate = Path(root) / entry
        if candidate.is_dir() and (candidate / "data_level0.bin").exists():
            return candidate
    raise AssertionError("临时库里找不到 HNSW 段目录：%s" % sorted(os.listdir(str(root))))


def _slot_census(root):
    """三套独立口径同时数一遍图平面的元素数。它们不等就说明解码不成立。"""
    import struct

    seg = _segment_dir(root)
    data = (seg / "data_level0.bin").stat().st_size
    length = (seg / "length.bin").stat().st_size
    header = (seg / "header.bin").read_bytes()
    assert data % ELEM == 0, "解码不成立：%d 不能被 %d 整除" % (data, ELEM)
    assert length % 4 == 0
    u32 = struct.unpack("<" + "I" * (len(header) // 4), header)
    return {"by_data": data // ELEM, "by_length": length // 4, "by_header": u32[5], "header": u32}


def _clusters(n_docs, per_doc, scale, seed):
    rng = np.random.default_rng(seed)
    centres = rng.normal(size=(n_docs, DIM))
    centres /= np.linalg.norm(centres, axis=1, keepdims=True)
    centres *= 6.0
    ids, vectors = [], []
    for doc in range(n_docs):
        for chunk in range(per_doc):
            ids.append("doc%02d_%d" % (doc, chunk))
            vectors.append(list(centres[doc] + rng.normal(scale=scale, size=DIM)))
    return ids, vectors


# ---------------------------------------------------------- 判据⑤ 红线：不许碰工作树索引
def _db_manifest():
    if not WORKTREE_DB.is_dir():
        return {}
    out = {}
    for base, _dirs, files in os.walk(str(WORKTREE_DB)):
        for name in files:
            full = Path(base) / name
            out[str(full.relative_to(WORKTREE_DB))] = hashlib.sha256(full.read_bytes()).hexdigest()
    return out


@pytest.fixture(autouse=True, scope="module")
def worktree_index_untouched():
    """整件跑完复比 sha256：本文件对工作树 chroma_db/ 一个字节都不许动。"""
    before = _db_manifest()
    yield
    assert _db_manifest() == before, "工作树 chroma_db/ 被本文件的用例改动了"


# ------------------------------------------------------------------ ① 只信槽数这一处
def test_the_slot_count_is_agreed_by_three_independent_planes(tmp_path):
    _release()
    client, collection = _open(tmp_path)
    _add(collection, _ids(1000), _vectors(1000))
    _release()
    client, collection = _open(tmp_path)          # 从盘重开，量的是持久态
    census = _slot_census(tmp_path)
    assert census["by_data"] == census["by_length"] == census["by_header"] == 1000, census
    assert collection.count() == 1000


def test_the_record_plane_has_no_vector_column_at_all(tmp_path):
    """向量只在图平面一份：sqlite 的 embeddings 表里没有 embedding/vector 列。"""
    _release()
    client, collection = _open(tmp_path)
    _add(collection, _ids(1000), _vectors(1000))
    _release()
    import sqlite3

    con = sqlite3.connect(str(Path(tmp_path) / "chroma.sqlite3"))
    try:
        columns = [row[1] for row in con.execute("PRAGMA table_info(embeddings)")]
        assert "embedding" not in columns and "vector" not in columns, columns
        assert {"id", "embedding_id", "seq_id"} <= set(columns), columns
        # 唯一带 vector 的是 WAL（embeddings_queue），它是写序流水而不是可读副本
        wal_columns = [row[1] for row in con.execute("PRAGMA table_info(embeddings_queue)")]
        assert "vector" in wal_columns, wal_columns
    finally:
        con.close()


# ------------------------------------------------------ ③ 重传只涨槽不回收（现网膨胀来源）
def test_reupload_keeps_count_flat_while_slots_grow_by_exactly_n(tmp_path):
    _release()
    ids, vectors = _ids(1000), _vectors(1000)
    client, collection = _open(tmp_path)
    _add(collection, ids, vectors)
    _release()
    client, collection = _open(tmp_path)
    assert _slot_census(tmp_path)["by_data"] == 1000
    for _round in range(2):
        # 逐条照抄 app/rag/retriever.py:1357-1374：同 id 先 delete 再 add
        collection.delete(ids=ids)
        _add(collection, ids, [row if index < 500 else [value + 0.01 for value in row]
                               for index, row in enumerate(vectors)])
        _release()
        client, collection = _open(tmp_path)
    assert collection.count() == 1000, "记录平面被重传改动了，本钉的前提就变了"
    assert _slot_census(tmp_path)["by_data"] == 3000, "每轮重传净增 N 枚元素，一枚都不回收"


def test_deleting_records_never_shrinks_the_graph_plane(tmp_path):
    """删档路径只打标记：删掉 40% 记录之后，图平面一枚槽都不缩。

    现网 39923 槽 / 1008 在册 = 39.6 倍，就是这么一路只增不减攒出来的。
    （把最后一枚也删空时长库会把段截回初始容量，所以本钉只断言"部分删除不回收"。）
    """
    _release()
    ids = _ids(1000)
    client, collection = _open(tmp_path)
    _add(collection, ids, _vectors(1000))
    _release()
    client, collection = _open(tmp_path)
    assert _slot_census(tmp_path)["by_data"] == 1000
    collection.delete(ids=ids[:400])
    _release()
    client, collection = _open(tmp_path)
    assert collection.count() == 600
    assert _slot_census(tmp_path)["by_data"] == 1000, "删 400 枚就回收槽 ⇒ 现网的膨胀另有其因"


# ------------------------------------- ⑤ 症状 A 的最小机理：稠密近重复 + 默认 ef，零删除
def test_a_clean_index_with_near_duplicate_chunks_already_loses_self_probes(tmp_path):
    """一枚都不删、纯 add 出来的健康索引：ef_search=100 就够让在册向量问不到自己。

    同时 numpy 在同一批向量上扫精确 top-5 一枚不漏 ⇒ 缺口在"问法"（近似检索的
    候选预算），不在"库坏了"。这就是现网 138/1008 那一档的形状。
    """
    _release()
    ids, vectors = _clusters(60, 200, scale=0.05, seed=3)
    client, collection = _open(tmp_path, hnsw={"search_ef": 100})
    _add(collection, ids, vectors)
    probes = [(name, vec) for index, (name, vec) in enumerate(zip(ids, vectors))
              if index % 50 == 7]
    matrix = np.asarray(vectors, dtype="float64")

    def exact(vec):
        dist = ((matrix - np.asarray(vec)) ** 2).sum(axis=1)
        return [ids[index] for index in np.argsort(dist, kind="stable")[:5]]

    ann_miss = brute_miss = 0
    for name, vec in probes:
        got = [str(x) for x in collection.query(query_embeddings=[vec], n_results=5)["ids"][0]]
        ann_miss += name not in got
        brute_miss += name not in exact(vec)
    assert collection.count() == len(ids), "记录平面一枚不缺，才有资格说这是读路径的事"
    assert brute_miss == 0, ("精确扫描都有问不到的，说明探针或数据不对：%d" % brute_miss)
    assert ann_miss >= 1, ("健康库里 ef=100 也能人人问到自己 ⇒ 症状 A 的归因要重写：%d/%d" % (
        ann_miss, len(probes)))


def test_raising_the_candidate_budget_pulls_the_gap_back_without_touching_the_data(tmp_path):
    """同一批数据、同一套写序，只把 ef_search 抬到语料规模量级：缺口不得变大。

    这条把「读路径参数」和「持久状态损坏」切开：真损坏不会因为换个问法就好转。
    """
    _release()
    ids, vectors = _clusters(60, 200, scale=0.05, seed=3)
    probes = [(name, vec) for index, (name, vec) in enumerate(zip(ids, vectors))
              if index % 50 == 7]
    gaps = {}
    for ef in (100, 8000):
        path = Path(tmp_path) / ("ef%d" % ef)
        _release()
        client, collection = _open(path, hnsw={"search_ef": ef})
        _add(collection, ids, vectors)
        miss = 0
        for name, vec in probes:
            got = [str(x) for x in collection.query(query_embeddings=[vec], n_results=5)["ids"][0]]
            miss += name not in got
        gaps[ef] = miss
    assert gaps[100] >= 1, gaps
    assert gaps[8000] <= gaps[100], ("候选预算翻 80 倍缺口反而变大 ⇒ 不是截断，得改判：%s" % gaps)


# --------------------------------------------------------------- ⑦ 反证：墓碑本身不是因
def test_ninety_five_percent_tombstones_still_answer_every_query(tmp_path):
    """整档删到只剩 5%，无过滤 query 仍然每问必答、每答满 5 行。

    所以"现网 97.5% 的槽是墓碑"这一条本身不构成症状，谁也不许拿它当结论。
    """
    _release()
    ids, vectors = _clusters(40, 250, scale=0.05, seed=21)
    client, collection = _open(tmp_path)
    _add(collection, ids, vectors)
    dead = {name for name in ids if int(name.split("_")[0][3:]) >= 2}
    dead_ids = sorted(dead)
    for start in range(0, len(dead_ids), 500):
        collection.delete(ids=dead_ids[start:start + 500])
    live = {name for name in ids if name not in dead}
    _release()
    client, collection = _open(tmp_path)
    assert collection.count() == len(live)
    assert _slot_census(tmp_path)["by_data"] == len(ids)          # 墓碑一枚不回收
    empty = short = 0
    for name, vec in [(a, b) for a, b in zip(ids, vectors) if a in live]:
        got = [str(x) for x in collection.query(query_embeddings=[vec], n_results=5)["ids"][0]]
        empty += not got
        short += bool(got) and len(got) < 5
    assert empty == 0 and short == 0, ("纯墓碑就能打出空表 ⇒ 症状 B 不必另找因：%s" % (
        (empty, short),))


# ------------------------------- 症状 A 的量级来源：同 id 重传的代际堆（现网 40 代）
def test_generational_reupload_degrades_self_recall_on_an_uncorrupted_index(tmp_path):
    """同 id 重传 12 代再从盘重开：门内只断**确定性**那半——膨胀机制在、向量一枚不缺、
    精确扫描不漏、两条腿同向量同 k 同口径。自探针缺口**只记录不断言**。

    为什么不赌缺口：图平面的落盘形状随并发写序浮动，1,000 枚探针实测 0..480 枚
    （执行侧 6 次 1 次出状态，总控侧 7 次 1 次红），把它写成硬断言就是给全量门装一枚
    假红发生器。机制是确定的（§2 的 ef 扫与精确对照已坐实），量级不是。
    缺口现取现记，落在 tmp_path/r269_generational_self_recall.json，随 -rA 一起回显。
    """
    _release()
    ids, vectors = _ids(1000), _vectors(1000)
    client, collection = _open(tmp_path)
    _add(collection, ids, vectors)
    for _round in range(12):
        collection.delete(ids=ids)
        _add(collection, ids, [[value + 0.01 for value in row] for row in vectors])
    _release()
    client, collection = _open(tmp_path)
    # ---- 门内断言：全部与写序无关
    assert collection.count() == 1000, "重传把记录数改了，本钉的前提就变了"
    assert _slot_census(tmp_path)["by_data"] == 13000, "十二代堆没攒出来，膨胀这条得另找因"
    page = collection.get(ids=ids, include=["embeddings"])
    stored = {str(a): [float(v) for v in row] for a, row in zip(page["ids"], page["embeddings"])}
    assert len(stored) == 1000, "向量本身一枚都不能少"
    assert collection.configuration.get("hnsw", {}).get("space") == "l2", (
        "库不是 l2 口径，下面的精确扫描与它不同尺，对照不成立")
    matrix = np.asarray([stored[name] for name in ids], dtype="float64")
    n_results = 5
    ann_miss = ann_empty = brute_miss = self_rank_first = same_vector = 0
    for index, name in enumerate(ids):
        probe = stored[name]
        # 结构守卫①：两条腿吃的是同一枚向量（不是各算一遍）
        same_vector += int(np.array_equal(np.asarray(probe, dtype="float64"), matrix[index]))
        got = [str(x) for x in collection.query(query_embeddings=[probe],
                                                n_results=n_results)["ids"][0]]
        dist = ((matrix - matrix[index]) ** 2).sum(axis=1)
        exact_top = [ids[i] for i in np.argsort(dist, kind="stable")[:n_results]]
        # 结构守卫②：同一个 k，且平方欧氏下探针到自己的距离恒为 0 ⇒ 必排第 1
        self_rank_first += int(exact_top[0] == name and len(exact_top) == n_results)
        ann_miss += name not in got
        ann_empty += not got
        brute_miss += name not in exact_top
    assert same_vector == len(ids), "有探针的向量与矩阵行不一致，对照的量具坏了"
    assert self_rank_first == len(ids), (
        "有探针在自己面前排不到第 1 ⇒ k 或距离口径不同尺，对照不成立：%d/%d" % (
            self_rank_first, len(ids)))
    assert brute_miss == 0, ("精确扫描都有问不到的，探针就不对：%d" % brute_miss)
    # ---- 只记录，不断言：随写序浮动的那一半
    evidence = {"probes": len(ids), "generations": 13, "slots": 13000,
                "n_results": n_results, "space": "l2",
                "ann_miss": ann_miss, "ann_empty": ann_empty,
                "brute_miss": brute_miss, "miss_rate": round(ann_miss / float(len(ids)), 4)}
    Path(tmp_path, "r269_generational_self_recall.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print("R269 代际堆自探针缺口（只记录）：" + json.dumps(evidence, ensure_ascii=False))
