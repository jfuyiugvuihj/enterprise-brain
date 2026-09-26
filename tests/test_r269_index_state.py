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
    """照抄重传路径写 8 代再从盘重开：记录平面仍是 1000 枚、向量一枚不缺，
    但自探针已经开始问不到自己；同一批向量的精确扫描一枚不漏。

    图平面里躺着 13 倍于在册元素的代际堆，候选预算（ef_search=100，
    app/rag/retriever.py:882 从来没设过）被同坐标的近重复墓碑吃光。
    缺口大小随并发写序浮动（实测落在 7..480 之间，且约 1/7 的运行一枚都不掉），所以本钉**不断缺口**：
    量级是报告 §2/§3 的观测值，不是门。门里只留确定性断言——机制膨胀、探针方法学、精确扫描零漏。
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
    assert collection.count() == 1000, "重传把记录数改了，本钉的前提就变了"
    assert _slot_census(tmp_path)["by_data"] == 13000, "十二代堆没攒出来，膨胀这条得另找因"
    page = collection.get(ids=ids, include=["embeddings"])
    stored = {str(a): [float(v) for v in row] for a, row in zip(page["ids"], page["embeddings"])}
    assert len(stored) == 1000, "向量本身一枚都不能少"
    matrix = np.asarray([stored[name] for name in ids], dtype="float64")
    ann_miss = brute_miss = 0
    widths = set()
    probe_sources = set()
    for index, name in enumerate(ids):
        got = [str(x) for x in collection.query(query_embeddings=[stored[name]],
                                                n_results=5)["ids"][0]]
        ann_miss += name not in got
        widths.add(len(got))
        probe_sources.add(id(stored[name]))
        dist = ((matrix - matrix[index]) ** 2).sum(axis=1)
        brute_miss += name not in [ids[i] for i in np.argsort(dist, kind="stable")[:5]]
    assert brute_miss == 0, ("精确扫描都有问不到的，探针就不对：%d" % brute_miss)
    # 判据②（总控落笔·09-26）：此处原来是 assert ann_miss >= 1，实测抖动率约 1/7
    # （主树首跑即红、其后单跑 6 次全绿；与本件 docstring 及报告 §9.2「6 遍只出 1 遍」同源）。
    # 全量门每班要跑十几轮，1/7 的浮动率等于每天制造若干次假红——门一旦被假红污染，
    # 「敢不敢并树」的心理成本会把整条流水线拖死。所以量级改为现取记录，不赌单次运行：
    print("R269 self-probe: ann_miss=%d/%d brute_miss=%d/%d (hnsw 配置从未传 => ef_search 恒 100)"
          % (ann_miss, len(ids), brute_miss, len(ids)))
    # 守卫一（探针方法学，确定性）：每一发都拿回 5 名，且查的就是入库后读回的那一枚向量；
    # 否则「ANN 会漏、精确扫描不漏」这组对照测的是两个东西，brute_miss == 0 会变成一个空洞的胜利。
    assert widths == {5}, sorted(widths)
    assert len(probe_sources) == len(ids)
    # 守卫二（机制，确定性）：图平面槽位是记录平面的 13 倍——这才是「候选预算被代际堆吃光」的
    # 可门证据。哪天 ef/hnsw 被正确设进 retriever.py:882，这一枚会先改口，不必靠某一次掉几枚报信。
    assert _slot_census(tmp_path)["by_data"] == collection.count() * 13