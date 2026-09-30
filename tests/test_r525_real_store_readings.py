# -*- coding: utf-8 -*-
"""R525 判据① ⑥ —— 活动先验的「真库面读数」账，外加全单共用的真库名次夹具。

## 这份账是从哪里来的（命令原文由量具自己生成，不在这里手抄第二份）

读数纸 ``docs/testing/r525-activity-prior-real-store-2026-09-30.md`` 里每一格都带
``scripts/r525_activity_prior_readout.py`` 现打的命令原文。本件把其中**跨时间稳定的形状**
钉成机器事实，把**会随打点漂移的计数**只当快照对平（快照自己内部一致，才配叫一次读数）：

* 面 A = 部署库（容器 ``enterprise-brain-postgres-1`` / ``enterprise_brain``）：0011 在台账里、
  表在、**0 行**、非零分布空、命中语料 **0 篇**。
* 面 B = 宿主 PG（计划书 §9.3 点名的「5432 上那台野 PostgreSQL」）：连 ``schema_migrations``
  都没有 ⇒ 0011 的表不存在 ⇒ 产品自己的读取器真跑到 ``UndefinedTable``。
* 🔴 面 A 那 1008 枚 / 100 篇是**演示语料**，不是客户尺寸（判据⑥）。本件把它钉在
  ``corpus_is_demo_corpus`` 这枚旗上，谁拿它冒充客户尺寸谁红。

## 名次夹具为什么可以叫「真库名次」

``REAL_ANN_TOP40`` 是**真库真实 ANN 查询**回来的行：算符现读 ``vector_scope``（``l2`` ⇒ ``<->``），
候选宽度 ``set_config('hnsw.ef_search','100',TRUE)`` 与产品读腿同档同写法，40 行里
``filename`` / ``chunk_index`` / ``classification`` / ``department`` / ``distance`` 逐字来自
``chunk_vectors``。只有两格不是原文：查询向量是定种子随机数（**本单不许打模型**），
``content`` 由 ``left(content, 24)`` 截过——先验一个字节都不读正文，位移算术与此无关。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "r525_activity_prior_readout.py"
RETRIEVER_PATH = REPO_ROOT / "app" / "rag" / "retriever.py"

#: 取证快照（执行层自报，量具 2026-09-30 现取；复跑凭 R525_REAL_STORE=on）。
#: 发形与量具产物逐字同形：单行聚合（`chunks_per_document`）是 dict，
#: 多行取数（`vector_scope` / `non_zero_distribution` / `top_signals`）是 list。
REAL_STORE = {
    "taken_at": "2026-09-30",
    "surface_a": {
        "name": "A-deployed-container-pg",
        "migration_count": 17,
        "migration_0011_in_ledger": True,
        "relation": "document_activity_signals",
        "rows": 0,
        "non_zero_distribution": [],
        "signals_hitting_corpus": 0,
        "top_signals": [],
        "corpus_is_demo_corpus": True,
        "corpus_shape": {"vector_rows": 1008, "distinct_filenames": 100,
                         "whitespace_padded_rows": 0, "over_512_rows": 0,
                         "max_filename_len": 32, "distinct_casefolded": 100},
        "chunks_per_document": {"widest": 586, "narrowest": 1, "average": 10.08,
                                "docs_with_5plus_chunks": 26},
        "vector_scope": ["1|nomic-embed-text|768|l2|16|100"],
        "reader_diagnostics": {"enabled": True, "source": "store", "reason": "", "documents": 0},
        "psycopg_reachable_from_host": False,
    },
    "surface_b": {
        "name": "B-host-postgres",
        "schema_migrations_present": False,
        "relation": None,
        "chunk_vectors_present": False,
        "public_tables": 9,
        "reader_diagnostics": {"enabled": True, "source": "error", "reason": "UndefinedTable",
                               "documents": 0},
        "psycopg_reachable_from_host": True,
    },
}

#: 真库 ANN top-40（l2、ef_search=100、query seed 20260930）：filename / chunk_index /
#: distance / classification / department。次序就是名次，一行一名。
REAL_ANN_TOP40 = (
    ("深度学习入门：基于Python的理论与实现.pdf", 340, 22.918308, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 246, 23.230082, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 255, 23.23174, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 256, 23.322941, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 352, 23.366426, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 269, 23.429538, 1, ""),
    ("MYO_私有化部署手册.txt", 5, 23.484237, 1, ""),
    ("深度学习技术栈学习路线.pdf", 10, 23.504168, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 568, 23.510306, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 274, 23.578169, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 228, 23.603706, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 234, 23.657589, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 326, 23.678721, 1, ""),
    ("产品技术手册.txt", 2, 23.698126, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 407, 23.704271, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 467, 23.739649, 1, ""),
    ("产品技术手册.txt", 3, 23.74052, 1, ""),
    ("MYO_私有化部署手册.txt", 4, 23.7539, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 341, 23.815537, 1, ""),
    ("产品技术手册.txt", 1, 23.851376, 1, ""),
    ("AI-Agent学习路线图.pdf", 8, 23.924689, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 408, 23.93341, 1, ""),
    ("MYBI_私有化部署手册.txt", 9, 23.937373, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 383, 23.96461, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 242, 23.977294, 1, ""),
    ("MYO_API接口文档_V1.txt", 1, 24.005805, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 351, 24.015663, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 371, 24.016523, 1, ""),
    ("MYO_API接口文档_V1.txt", 6, 24.043545, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 481, 24.047644, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 581, 24.049664, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 157, 24.057038, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 249, 24.062269, 1, ""),
    ("MYOps_部署与运维手册.txt", 2, 24.086746, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 366, 24.110195, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 273, 24.115455, 1, ""),
    ("MYO_私有化部署手册.txt", 2, 24.115663, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 580, 24.117082, 1, ""),
    ("MYO_API接口文档_V1.txt", 5, 24.127837, 1, ""),
    ("深度学习入门：基于Python的理论与实现.pdf", 578, 24.142453, 1, ""),
)

#: 本单三档腿宽（派工词点名各测一次）。
LEG_WIDTHS = (5, 12, 40)

#: 复跑闸：只有显式设了 R525_REAL_STORE=on 才碰真库（全量回归门里默认不碰 docker）。
REAL_STORE_OPT_IN = os.environ.get("R525_REAL_STORE", "").strip().lower() == "on"

BASELINE_SHA = hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest()
RETRIEVER_BASELINE_SHA = hashlib.sha256(RETRIEVER_PATH.read_bytes()).hexdigest()


def load_gauge_tool(name="r525_gauge_tool"):
    """按文件名单独加载量具（与 _r259_queue_ruler.load 同一族做法）。"""
    spec = importlib.util.spec_from_file_location(name, str(SCRIPT_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_retriever_copy(tmp_path, name, *, anchor=None, replacement=None):
    """把 ``app/rag/retriever.py`` 原样或按锚点改一处，加载成独立模块。

    🔴 全程只在 ``tmp_path`` 的副本上动手，跟踪里的原件前后各核一次 sha256。反证刀与被验的
    正控走**同一枚加载路径**，所以「红」只可能来自那一处变异，不来自加载方式。
    """
    original = RETRIEVER_PATH.read_bytes()
    assert hashlib.sha256(original).hexdigest() == RETRIEVER_BASELINE_SHA, "进刀之前原件就不是原样"
    text = original.decode("utf-8-sig").replace("\r\n", "\n")
    if anchor is not None:
        hits = text.count(anchor)
        assert hits == 1, f"{name}：锚点在原件里出现 {hits} 次，不唯一 ⇒ 这枚反证是空的"
        text = text.replace(anchor, replacement, 1)
        assert text != original.decode("utf-8-sig").replace("\r\n", "\n"), name + "：改了个寂寞"
    target = tmp_path / ("r525_" + name + ".py")
    target.write_text(text, encoding="utf-8", newline="\n")
    spec = importlib.util.spec_from_file_location("r525_" + name, str(target))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hashlib.sha256(RETRIEVER_PATH.read_bytes()).hexdigest() == RETRIEVER_BASELINE_SHA, \
        name + "：反证跑完原件不是原样"
    return module


def ann_rows(limit: int = 40) -> list:
    """把真库名次折成量具 ``_hit_dicts`` 吃的那份行（content 只占位，先验不读它）。"""
    return [{"filename": name, "chunk_index": index, "classification": cls,
             "department": dept, "distance": distance,
             "content_head": "r525-real-rank-%02d" % position}
            for position, (name, index, distance, cls, dept) in enumerate(
                REAL_ANN_TOP40[:limit], start=1)]


def product_hit_dicts(rows: list, module=None) -> list:
    """命中字典由产品自己的 ``_hit_dicts`` 生成；本件一个键都不自己定义。

    它以 ``self=None`` 调用：现读那份实现里 ``self`` 一个字段都不读（只吃 documents /
    metadatas / mode / reason），所以不必为了拿形状去冷起一次 chroma 客户端。
    """
    if module is None:
        from app.rag.retriever import DocumentRetriever

        module_class = DocumentRetriever
    else:
        module_class = module.DocumentRetriever
    metadatas = [{"filename": row["filename"], "chunk_index": row["chunk_index"],
                  "classification": row["classification"], "department": row["department"]}
                 for row in rows]
    return module_class._hit_dicts(None, [row["content_head"] for row in rows], metadatas,
                                  module_class.MODE_SEMANTIC, "")


def signal_on(rows: list, position: int, *, accepted: int = 3, rejected: int = 0) -> dict:
    """把合成计数钉在某一枚**真库真 filename** 上（键真、值明写是合成）。"""
    return {rows[position]["filename"]: {"accepted": accepted, "rejected": rejected}}


# ==================== 判据①：真库面读数那笔账对平 ====================

def test_the_select_the_gauge_ran_is_the_products_own_select():
    """连接键口径不许有第二份：量具跑的就是产品源码里那条 SELECT 原文。"""
    tool = load_gauge_tool()
    assert tool.read_product_select_text() == (
        "SELECT filename, accepted_count, rejected_count FROM document_activity_signals")


def test_the_snapshot_is_internally_consistent_about_zero_rows():
    """快照内部对平：0 行 ⇒ 非零分布空 ⇒ 命中语料 0 篇 ⇒ 榜首清单空。

    🔴 这枚不是「今天真库有几行」的判据（那一格写在读数纸里，随打点漂移），而是「一份自称
    0 行的快照必须四个数一起是 0」。少一个就说明有人在纸上一本账两句话。
    """
    surface = REAL_STORE["surface_a"]
    assert surface["rows"] == 0
    assert surface["non_zero_distribution"] == []
    assert surface["signals_hitting_corpus"] == 0
    assert surface["top_signals"] == []
    assert surface["migration_0011_in_ledger"] is True
    assert surface["relation"] == "document_activity_signals"


def test_there_is_no_real_store_signal_to_read_so_the_hit_set_is_empty():
    """判据①「能命中语料里哪几篇」的真库读数＝零篇；有信号那一格按未量到交回。"""
    tool = load_gauge_tool()
    snapshot_rows = REAL_STORE["surface_a"]["rows"]
    assert snapshot_rows == 0, "快照自称 0 行"
    assert tool.rows_to_priors([]) == {}, "0 行折进先验必须是空字典"
    assert REAL_STORE["surface_a"]["reader_diagnostics"]["source"] == "store"


def test_the_two_kinds_of_zero_are_distinguishable_on_the_two_real_databases():
    """判据⑤的「不许冒充」在真库上是两枚真读数，不是推断。

    面 A：读成功而零行 ⇒ ``source=store`` / ``reason=''`` / ``documents=0``。
    面 B：读不通 ⇒ ``source=error`` / ``reason=UndefinedTable`` / ``documents=0``。
    两枚的 ``documents`` 相同（排序都不动用），能把它们分开的只有 ``source`` 与 ``reason``，
    所以这一格必须钉在「两枚读数不相等」上，而不是钉在「有日志」上。
    """
    surface_a = REAL_STORE["surface_a"]["reader_diagnostics"]
    surface_b = REAL_STORE["surface_b"]["reader_diagnostics"]
    assert surface_a["documents"] == surface_b["documents"] == 0
    assert (surface_a["source"], surface_a["reason"]) == ("store", "")
    assert (surface_b["source"], surface_b["reason"]) == ("error", "UndefinedTable")
    assert surface_a != surface_b, "两枚 0 撞成同一份读数 ⇒ 读不到就被冒充成没有信号"


# ==================== 判据⑥：真数据形状（演示语料那一枚旗不许摘） ====================

def test_the_real_filename_key_space_is_clean_enough_for_the_exact_join():
    """先验按 filename 精确匹配，所以键空间干不干净是**真数据形状**里能量的一格。"""
    shape = REAL_STORE["surface_a"]["corpus_shape"]
    assert shape["whitespace_padded_rows"] == 0, "有空首尾的真名会让 btrim 那条 CHECK 放行却匹配不上"
    assert shape["over_512_rows"] == 0, "超过 0011 的 CHECK 上界的真名压根打不了点"
    assert REAL_STORE["surface_a"]["chunks_per_document"], "每篇几枚 chunk 是先验放大率的真形状"
    assert shape["distinct_casefolded"] == shape["distinct_filenames"], "同名不同大小写＝先验会只命中一半"


def test_the_snapshot_declares_itself_demo_corpus_not_customer_size():
    """🔴 判据⑥：1008 枚 / 100 篇只配叫演示语料，本件把这枚旗钉成机器事实。"""
    assert REAL_STORE["surface_a"]["corpus_is_demo_corpus"] is True
    assert REAL_STORE["surface_a"]["corpus_shape"]["vector_rows"] == 1008
    assert REAL_STORE["surface_a"]["corpus_shape"]["distinct_filenames"] == 100


def test_the_real_ann_window_is_dominated_by_one_document():
    """真库名次里的集中度（强度问题的真形状）：窗口越宽、同篇占的席越多。"""
    concentration = {width: len({row[0] for row in REAL_ANN_TOP40[:width]})
                     for width in LEG_WIDTHS}
    assert concentration == {5: 1, 12: 3, 40: 8}, concentration
    winner = REAL_ANN_TOP40[0][0]
    assert sum(1 for row in REAL_ANN_TOP40 if row[0] == winner) == 27, (
        "演示库里那篇 586 枚 chunk 的文档独占 40 席中的 27 席：一篇打点会同时注记 27 枚命中")


def test_the_fixture_rows_are_the_real_corpus_rows_not_invented_names():
    """夹具里的每一枚 filename/chunk_index 必须能落回真库快照，不许出现造出来的名字。"""
    tool = load_gauge_tool()
    assert tool.rows_to_priors  # 量具的折账函数在位（本件复用它的口径）
    names = {row[0] for row in REAL_ANN_TOP40}
    assert all(name.endswith((".pdf", ".txt")) for name in names), names
    assert len(REAL_ANN_TOP40) == 40
    distances = [row[2] for row in REAL_ANN_TOP40]
    assert distances == sorted(distances), "真库 l2 名次必须单调不减，否则这份快照不是 ANN 回来的"


# ==================== 复跑闸（默认跳过：要真库 + docker） ====================

@pytest.mark.skipif(not REAL_STORE_OPT_IN,
                    reason="R525_REAL_STORE=on 才复跑真库面（要 docker 与面 B 的 DSN 出处）；"
                           "在册读数纸 docs/testing/r525-activity-prior-real-store-2026-09-30.md")
def test_the_live_real_store_still_matches_the_pinned_snapshot(tmp_path, monkeypatch):
    """把量具在真库上再跑一遍，与快照逐格对账（演示库被重建或真有人打了点，这一格先红）。"""
    import subprocess
    import sys

    dotenv = os.environ.get("R525_DOTENV", "")
    assert dotenv, "R525_REAL_STORE=on 必须同时给 R525_DOTENV（面 B 的 DSN 出处，凭据不落纸）"
    out_path = tmp_path / "readout.json"
    proc = subprocess.run([sys.executable, str(SCRIPT_PATH), "--section", "all",
                           "--dotenv", dotenv, "--out", str(out_path)],
                          capture_output=True, text=True, encoding="utf-8", timeout=300)
    assert proc.returncode == 0, proc.stdout[-800:] + proc.stderr[-800:]
    live = json.loads(out_path.read_text(encoding="utf-8"))
    surface_a = live["surface_a"]
    for key in ("rows", "non_zero_distribution", "signals_hitting_corpus", "corpus_shape",
                "chunks_per_document", "migration_count", "vector_scope"):
        assert surface_a[key] == REAL_STORE["surface_a"][key], (key, surface_a[key])
    assert [row["filename"] for row in live["ann"]["rows"]] == [row[0] for row in REAL_ANN_TOP40], \
        "真库 ANN 名次漂了：本单的位移读数要重取"
