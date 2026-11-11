# -*- coding: utf-8 -*-
"""R525 判据⑦ —— 反证刀：六把，每一把先在影子端跑正控确认它会咬。

## 口径

🔴 全程只在 ``tmp_path`` 的副本上动手：把 ``app/rag/retriever.py`` 读进内存、按锚点改一处、
写成副本、按副本单独加载成模块，再在**同一枚加载路径**上跑正控与刀下两遍同一场判断。
跟踪里的原件每把刀前后各核一次 sha256（最后一枚用例总清点）。

## 本件顺手量出来的一格事实（写在这里，免得下一班误读在册覆盖）

在册那条读腿覆盖 ``test_r46_activity_signals.py::test_every_leg_of_search_routes_through_the_prior``
判的是「``search()`` 源码里 ``self._apply_activity_prior(`` 出现不少于 4 次」。今天实际出现 **5 次**
（降级 / 热集 / PGVector / Chroma 语义 / 关键词兜底），所以摘掉任何一支都还剩 4 次——**那枚在册
覆盖对「PGVector 那一支被摘」全盲**（``test_k1_is_invisible_to_the_registered_count_pin`` 当场量
出来，不是推断）。K2 更彻底：接线还在、读取方被短路成空先验，计数一个字都没变，那枚覆盖同样
全盲。这正是 R525 判据④要补的那一格。
"""
from __future__ import annotations

import hashlib
import os

import pytest

from test_r525_real_store_readings import (
    BASELINE_SHA,
    LEG_WIDTHS,
    RETRIEVER_BASELINE_SHA,
    RETRIEVER_PATH,
    ann_rows,
    load_retriever_copy,
    product_hit_dicts,
    signal_on,
)
from test_r525_displacement_on_real_ranks import REAL_WINDOWS, single_carrier_index

#: 六把刀的锚点全部现取唯一（不唯一的刀等于没动东西，``load_retriever_copy`` 当场红）。
KNIVES = {
    "K1_pg_exit_stripped": {
        "anchor": "                return self._apply_activity_prior(pg_hits)",
        "replace": "                return pg_hits",
        "victim": "判据④（R525 的 PGVector 腿三档用例）；在册那枚计数覆盖对它全盲",
    },
    "K2_prior_loader_blinded": {
        "anchor": "            priors = self._activity_prior_loader() or {}",
        "replace": "            priors = {}",
        "victim": "判据①②④（先验压根不再被读）；接线次数一个字没变 ⇒ 计数覆盖也全盲",
    },
    "K3_no_signal_early_return_gone": {
        "anchor": "    if not any(strengths):\n        return hits",
        "replace": "    if not any(strengths) and False:\n        return hits",
        "victim": "判据③（无信号必须交回同一个对象）",
    },
    "K4_bound_widened_to_three_places": {
        "anchor": "\nACTIVITY_PRIOR_MAX_SHIFT_RANKS = 1",
        "replace": "\nACTIVITY_PRIOR_MAX_SHIFT_RANKS = 3",
        "victim": "判据②（5 / 12 / 40 三档的「买到一名」与界）",
    },
    "K5_places_moved_forged_to_zero": {
        "anchor": '            carrier["activity_prior"]["places_moved"] = index + 1 - new_rank',
        "replace": '            carrier["activity_prior"]["places_moved"] = 0',
        "victim": "判据②（名次与 places_moved 的账目自洽）",
    },
    "K6_read_failure_disguised_as_no_signal": {
        "anchor": '                "reason": type(exc).__name__,',
        "replace": '                "reason": "",',
        "victim": "判据⑤（读不到不许冒充成「没有信号所以本该如此」而不留痕）",
    },
}


def knife(name):
    spec = KNIVES[name]
    return spec["anchor"], spec["replace"]


class StubEmbedding:
    """常量向量：本件不验向量算术，只验名次接线。"""

    def embed_query(self, text):
        return [0.5] * 768


class StubCollection:
    """遗留引擎的假出口：被问到就记账（判据④要知道这一跑到底问没问它）。"""

    name = "r525-teeth"

    def __init__(self):
        self.asks = []

    def query(self, **kwargs):
        self.asks.append(kwargs.get("n_results"))
        return {"ids": [[]], "documents": [[]], "metadatas": [[]]}


def pg_leg_reading(module, tmp_rows, priors):
    """在（可能是变异的）那一枚 retriever 模块上，把 ``search()`` 逼到 PGVector 那一支。

    顶替的只有两格：embedding（本单不许打模型）与 ``pg_store.read_topk``（宿主够不到部署库
    端口）——交回的行是真库 ANN 的那 40 行。接线、命中字典、先验、形状账全是被验的那份码。
    """
    from app.rag import indexing, pg_store
    from app.rag import retriever as real_rt

    instance = module.DocumentRetriever.__new__(module.DocumentRetriever)
    instance.chroma_dir = ""
    instance.collection = StubCollection()
    instance.embedding = StubEmbedding()
    instance._activity_prior_loader = lambda: dict(priors)
    instance._last_search_mode = real_rt.RETRIEVAL_MODE_SEMANTIC
    instance._last_search_reason = ""

    rows = [dict(row) for row in tmp_rows]

    def replayed_read_topk(**kwargs):
        return [dict(row) for row in rows[: int(kwargs["k"])]]

    original = pg_store.read_topk
    pg_store.read_topk = replayed_read_topk
    original_backend = os.environ.get("INDEX_BACKEND")
    os.environ["INDEX_BACKEND"] = "pgvector"
    module.reset_search_shape()
    try:
        hits = instance.search("季度营收", k=len(rows))
        reading = {
            "order": [hit["source"] for hit in hits],
            "indexes": [hit["chunk_index"] for hit in hits],
            "moves": [int((hit.get("activity_prior") or {}).get("places_moved", 0))
                      for hit in hits],
            "chroma_asks": list(instance.collection.asks),
            "backend_during_search": indexing.read_backend(),
            "answered_by": (module.search_shape_diagnostics()["last"] or {}).get("answered_by"),
        }
    finally:
        pg_store.read_topk = original
        module.reset_search_shape()
        if original_backend is None:
            os.environ.pop("INDEX_BACKEND", None)
        else:
            os.environ["INDEX_BACKEND"] = original_backend
    return reading


def rank_reading(module, rows, priors):
    """同一份真库名次在（可能是变异的）那一枚模块上过一遍排序，交回位移账。"""
    hits = product_hit_dicts(rows, module=module)
    ranked = module.rank_hits_by_activity(hits, priors, enabled=True)
    moves = [int((hit.get("activity_prior") or {}).get("places_moved", 0)) for hit in ranked]
    return {"same_object": ranked is hits, "moves": moves,
            "worst": max((abs(move) for move in moves), default=0),
            "annotated": sum(1 for hit in ranked if "activity_prior" in hit),
            "order": [hit["source"] for hit in ranked],
            "notes": [((hit.get("activity_prior") or {}).get("previous_rank"),
                       (hit.get("activity_prior") or {}).get("new_rank"),
                       (hit.get("activity_prior") or {}).get("places_moved", 0))
                      for hit in ranked]}


def reason_reading(module):
    """读不通时观测面落下来的那枚 reason（判据⑤的「留痕」）。"""
    import psycopg.errors

    module.reset_activity_priors()

    def raiser():
        raise psycopg.errors.UndefinedTable('关系 "document_activity_signals" 不存在')

    module.activity_priors(row_reader=raiser)
    diagnostics = dict(module.activity_prior_diagnostics())
    module.reset_activity_priors()
    return {"source": diagnostics["source"], "reason": diagnostics["reason"],
            "documents": diagnostics["documents"]}


# ==================== K1 摘掉 PGVector 那一支的接线 ====================

def test_k1_stripping_the_pg_exit_blinds_the_registered_count_pin(tmp_path, monkeypatch):
    """正控（未变异的副本）：PG 腿交回的名次里有一枚上位。刀下：次序与真库名次逐字相同。

    顺手量在册覆盖的盲区：把 ``test_r46…routes_through_the_prior`` 那枚函数指向变异副本，
    它照旧通过——它数的是接线次数，而次数从 5 掉到 4 仍在它的下界之上。
    """
    rows = REAL_WINDOWS[40]
    index = single_carrier_index(rows)
    priors = signal_on(rows, index)

    pristine = load_retriever_copy(tmp_path, "k1-control")
    control = pg_leg_reading(pristine, rows, priors)
    assert control["backend_during_search"] == "pgvector", control
    assert control["answered_by"] == "pgvector", control
    assert control["chroma_asks"] == [], "影子端正控就去问了遗留引擎 ⇒ 下面那声红不算牙"
    assert 1 in control["moves"], "影子端正控就没有上位 ⇒ 下面那声红不算牙"

    anchor, replacement = knife("K1_pg_exit_stripped")
    mutant = load_retriever_copy(tmp_path, "k1", anchor=anchor, replacement=replacement)
    cut = pg_leg_reading(mutant, rows, priors)
    assert cut["answered_by"] == "pgvector", "刀下连腿都换了 ⇒ 这声红不是 K1 造成的"
    assert cut["moves"] == [0] * len(rows), cut
    assert cut["order"] == [row["filename"] for row in rows], cut

    import test_r46_activity_signals as r46

    monkeypatch.setattr(r46, "rt", mutant)
    r46.test_every_leg_of_search_routes_through_the_prior()  # 不抛 = 这枚在册覆盖全盲


# ==================== K2 短路先验读取方 ====================

def test_k2_blinding_the_loader_takes_the_pg_leg_and_the_gauge_down_together(tmp_path):
    """正控两条腿都动得；刀下：PG 腿不动、真库名次也不动，而接线次数一个字没变。"""
    rows = REAL_WINDOWS[40]
    index = single_carrier_index(rows)
    priors = signal_on(rows, index)

    pristine = load_retriever_copy(tmp_path, "k2-control")
    control_leg = pg_leg_reading(pristine, rows, priors)
    assert control_leg["answered_by"] == "pgvector" and 1 in control_leg["moves"]
    assert rank_reading(pristine, rows, priors)["worst"] == 1

    anchor, replacement = knife("K2_prior_loader_blinded")
    mutant = load_retriever_copy(tmp_path, "k2", anchor=anchor, replacement=replacement)
    cut = pg_leg_reading(mutant, rows, priors)
    assert cut["answered_by"] == "pgvector", cut
    assert cut["moves"] == [0] * len(rows), cut

    import inspect

    from app.rag import retriever as rt

    assert (inspect.getsource(mutant.DocumentRetriever.search)
            .count("self._apply_activity_prior(")
            == inspect.getsource(rt.DocumentRetriever.search).count("self._apply_activity_prior(")), (
        "K2 改了行为却没改接线次数 ⇒ 数次数的覆盖结构上看不见它")


# ==================== K3 摘掉「无信号原样交回」 ====================

def test_k3_removing_the_no_signal_early_return_breaks_the_identity_promise(tmp_path):
    """正控：空先验交回同一个对象。刀下：内容相同但换了对象 ⇒ 判据③当场红。"""
    rows = ann_rows(40)

    pristine = load_retriever_copy(tmp_path, "k3-control")
    control = rank_reading(pristine, rows, {})
    assert control["same_object"] is True
    assert control["annotated"] == 0

    anchor, replacement = knife("K3_no_signal_early_return_gone")
    mutant = load_retriever_copy(tmp_path, "k3", anchor=anchor, replacement=replacement)
    cut = rank_reading(mutant, rows, {})
    assert cut["same_object"] is False, "摘掉早退还交回同一对象 ⇒ K3 是死牙"
    assert cut["annotated"] == len(rows), cut


# ==================== K4 把界放宽到三名 ====================

def test_k4_widening_the_bound_moves_the_real_ranks_past_one_place(tmp_path):
    """正控：真库 top-40 上一枚净采纳至多挪一名。刀下：挪到三名 ⇒ 判据②那两枚钉都红。"""
    rows = ann_rows(40)
    index = single_carrier_index(rows)
    priors = signal_on(rows, index)

    pristine = load_retriever_copy(tmp_path, "k4-control")
    assert rank_reading(pristine, rows, priors)["worst"] == 1

    anchor, replacement = knife("K4_bound_widened_to_three_places")
    mutant = load_retriever_copy(tmp_path, "k4", anchor=anchor, replacement=replacement)
    cut = rank_reading(mutant, rows, priors)
    assert cut["worst"] > 1, "放宽界之后位移还是 1 名 ⇒ K4 咬不到东西"
    assert mutant.ACTIVITY_PRIOR_MAX_SHIFT_RANKS == 3


# ==================== K5 把 places_moved 伪造成 0 ====================

def test_k5_forging_places_moved_breaks_the_rank_bookkeeping(tmp_path):
    """正控：``places_moved == previous_rank - new_rank``。刀下：次序照变，账上却一律记 0。

    K5 不动排序，只伪造那枚读数——所以「红」必须落在账目上（``…_previous_rank_minus_new_rank``
    那枚钉），而不是落在次序上。这一格正是派工词说的「不许断言『读到了计数』」：名次账一旦
    被伪造成 0，只看「有没有注记」的写法全绿，只看 ``places_moved`` 的写法当场红。
    """
    rows = ann_rows(40)
    index = single_carrier_index(rows)
    priors = signal_on(rows, index)

    pristine = load_retriever_copy(tmp_path, "k5-control")
    control = rank_reading(pristine, rows, priors)
    assert control["moves"][index - 1] == 1, control
    assert all(new is not None and moved == previous - new
               for previous, new, moved in control["notes"] if new is not None), control

    anchor, replacement = knife("K5_places_moved_forged_to_zero")
    mutant = load_retriever_copy(tmp_path, "k5", anchor=anchor, replacement=replacement)
    cut = rank_reading(mutant, rows, priors)
    assert cut["order"] == control["order"], "K5 应当只伪造账目、不动次序"
    assert cut["moves"] == [0] * len(rows), cut
    lied = [row for row in cut["notes"] if row[0] != row[1]]
    assert lied and all(row[2] == 0 for row in lied), (
        "名次真的变了而 ``places_moved`` 还跟着变 ⇒ 这枚牙咬不到账目：" + str(lied))


# ==================== K6 把读失败抹成「没有信号」 ====================

def test_k6_swallowing_the_reason_makes_a_failed_read_look_like_no_signal(tmp_path):
    """正控：``source=error`` / ``reason=UndefinedTable``。刀下：两枚零撞成同一份读数。"""
    pristine = load_retriever_copy(tmp_path, "k6-control")
    control = reason_reading(pristine)
    assert control == {"source": "error", "reason": "UndefinedTable", "documents": 0}, control

    anchor, replacement = knife("K6_read_failure_disguised_as_no_signal")
    mutant = load_retriever_copy(tmp_path, "k6", anchor=anchor, replacement=replacement)
    cut = reason_reading(mutant)
    assert cut["source"] == "error"
    assert cut["reason"] == "", cut
    assert cut != control, "刀下与正控一模一样 ⇒ 这枚反证是空的"


# ==================== 收尾：原件指纹与刀的数量 ====================

@pytest.mark.parametrize("name", sorted(KNIVES))
def test_every_knife_is_declared_with_one_unique_anchor(name):
    """每把刀都要有唯一锚点与点名的 victim（死牙的特征是锚点根本不出现）。"""
    spec = KNIVES[name]
    text = RETRIEVER_PATH.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    assert text.count(spec["anchor"]) == 1, name + "：锚点不唯一或压根不存在"
    assert spec["victim"]


def test_the_original_source_is_untouched_after_every_knife():
    """🔴 原件指纹：六把刀全在副本上动手，``app/rag/retriever.py`` 一个字节都没变。"""
    assert hashlib.sha256(RETRIEVER_PATH.read_bytes()).hexdigest() == RETRIEVER_BASELINE_SHA
    assert hashlib.sha256(
        (RETRIEVER_PATH.parent.parent.parent / "scripts"
         / "r525_activity_prior_readout.py").read_bytes()).hexdigest() == BASELINE_SHA
    assert len(KNIVES) >= 2, "派工词要求至少两把反证刀"


def test_the_teeth_run_under_the_shipped_leg_widths():
    """本件的靶子必须落在 5 / 12 / 40 这三档真库名次切片上（与判据②同一份夹具）。"""
    assert LEG_WIDTHS == (5, 12, 40)
    assert set(REAL_WINDOWS) == set(LEG_WIDTHS)
