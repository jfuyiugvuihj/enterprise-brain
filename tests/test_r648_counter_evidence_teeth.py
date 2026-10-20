# -*- coding: utf-8 -*-
"""R648 的反证刀 —— 四把，每一把先在**同一套影子机械**上跑正控确认它会咬。

🔴 全程只在 ``tmp_path`` 的副本上动手（同族纪律：#96 / #107 / #113 都是拿盘面当判据炸的）：
影子模块的 ``REPO`` 指回真仓，仓内原件每枚前后各核一次 sha256；锚点是唯一文本，不含行位。

* **K1 读后写**：把打点语句换成「客户端先 SELECT、再 UPDATE 回去」。同一套并发判据必须红，
  并点名丢了哪一列、哪一枚、谁被谁覆盖。这一把的刀口长在真 PG 上（丢更新只能真并发才量得到），
  所以它有两半：``R648_REAL_PG=on`` 时当场重打一遍；默认态复算的是 2026-10-04 那次真腿留下的
  读数（``read_then_write`` 那一格），判据函数与真腿走的是同一枚。
* **K2 界换成腿宽**：把 ``rank_hits_by_activity`` 里「交换轮数 = 界」改成「= 候选条数」。
  在册那枚 40 席真库窗口 + 真库读回的先验必须当场量出大于一名 ⇒ 次序腿红。
  🔴 界由量具里钉死的 ``R153_BOOKED_MAX_SHIFT_RANKS`` 出题，不读被改的那枚常量。
* **K3 闸门摸成恒开**：把 ``gate_declared`` 改成「设不设都放行」⇒ 绊线必响（常驻件不许偷偷连库）。
* **K4 两列折成净值**：把 ``fold_rows_to_priors`` 改成 ``accepted = a - b`` 的单列净值 ⇒
  混排腿那一格（库里明明 12/12）读出来是 0/0，「0/0 与 5/5 是两件事」当场失真。
"""
from __future__ import annotations

import pytest

from pathlib import Path

from _r648_gauge_harness import (GAUGE_BASELINE_SHA, GAUGE_PATH, REAL_PG_OPT_IN, REPO,
                                 RETRIEVER_BASELINE_SHA, RETRIEVER_PATH, load_gauge,
                                 load_retriever_copy, sha_of)
from test_r648_real_order_bound import BOOKED_MOVES_AT_40, ann_rows
from test_r648_real_order_bound import BOOKED_PRIORS as ORDER_BOOKED_PRIORS
from test_r648_real_pg_concurrency import BOOKED as BOOKED_CONC

#: 混排腿在册那行的原文（折账刀就打在它上面）。
BOOKED_MIXED_ROWS = [("r648_mixed_columns.md", "12", "12")]


def concurrency_verdict(leg) -> list:
    """并发腿那三件事的判据：逐列相加不许丢、行数不许多不许少、会话不许报错。"""
    reds = []
    if leg.get("lost_updates"):
        for item in leg["lost_updates"]:
            reds.append("丢更新 " + str(item["column"]) + "：该 " + str(item["expected"])
                        + " 实 " + str(item["observed"]) + "（缺 " + str(item["missing"]) + "）")
    if "row_count" in leg and int(leg["row_count"]) != 1:
        reds.append("行数不是一行不多一行不少：" + str(leg["row_count"]))
    if any(int(code) != 0 for code in leg.get("session_rc", [0])):
        reds.append("有会话报错：" + str(leg.get("session_rc")))
    if expected := leg.get("expected"):
        observed = leg.get("observed") or {}
        if observed != expected:
            reds.append("逐列对不平：" + str(expected) + " vs " + str(observed))
    return reds


def order_verdict(readings, width) -> list:
    """次序腿的判据：位移夹在钉死的那根界里，且不许是空炮。"""
    reds = []
    for key in (str(width), width):
        cell = readings.get(key)
        if cell is not None:
            readings = cell
            break
    if int(readings["bound_booked"]) != 1:
        reds.append("界本身被改了：" + str(readings["bound_booked"]))
    if int(readings["max_abs_places_moved"]) > int(readings["bound_booked"]):
        reds.append("宽度 " + str(width) + " 上位移 " + str(readings["max_abs_places_moved"])
                    + " 名，超出钉死的 " + str(readings["bound_booked"]) + " 名界")
    if not readings["carriers_shifted"]:
        reds.append("一枚都没挪 ⇒ 这格是空炮")
    if readings["no_signal_returns_same_object"] is not True:
        reds.append("无信号没交回同一个对象 ⇒ 判据② 破了")
    return reds


def columns_verdict(leg, folded) -> list:
    """混排腿的判据：两列分开记，净值 0 的那行必须两列都非零。"""
    reds = []
    observed = leg["observed"]
    if folded.get(leg["filename"]) != {"accepted": observed["accepted_count"],
                                       "rejected": observed["rejected_count"]}:
        reds.append("读回来的两列与库里的两列不等：" + str(folded.get(leg["filename"])))
    if leg["net_value"] == 0 and not leg["both_columns_nonzero"]:
        reds.append("净值 0 却被折成两列皆零 ⇒ 0/0 与 12/12 又被混成一件事")
    return reds


# ==================== K1 ====================

def test_k1_read_then_write_goes_red_under_the_same_judgement(tmp_path):
    """同一枚判据：打在产品 UPSERT 上必须空，打在「先 SELECT 再 UPDATE」上必须红并点名。"""
    green = concurrency_verdict(BOOKED_CONC["concurrency"])
    assert green == [], green
    reds = concurrency_verdict(BOOKED_CONC["read_then_write"])
    assert reds, "读后写形状没被抓出来 ⇒ 那枚「零丢更新」是假的"
    victim = BOOKED_CONC["read_then_write"]["victims_named"][0]
    assert "accepted_count" in reds[0], reds
    assert victim["victim_session"] == "S_A" and victim["overwritten_by_session"] == "S_B"
    assert BOOKED_CONC["read_then_write"]["both_sessions_read_the_same_base"] is True
    if not REAL_PG_OPT_IN:
        return
    gauge = load_gauge(tmp_path, "k1_live")
    baseline = gauge.leg_baseline(gauge.SANDBOX_DB)
    control = gauge.leg_read_then_write_control()
    assert concurrency_verdict(control), control
    assert control["victims_named"][0]["victim_session"] == "S_A", control
    assert concurrency_verdict(gauge.leg_concurrency()) == []
    clean = gauge.leg_cleanup(baseline)
    assert clean["rows_returned_to_original"] is True, clean
    assert clean["r648_rows_after"] == baseline["r648_rows"], clean


# ==================== K2 ====================

#: 把界的分母换成腿宽：交换轮数 = 候选条数 ⇒ 名次空间里的夹缝没了。
K2_ANCHOR = "    for _ in range(int(ACTIVITY_PRIOR_MAX_SHIFT_RANKS)):\n"
K2_REPLACE = "    for _ in range(len(carriers)):\n"


def test_k2_bound_replaced_by_leg_width_reddens_the_order_leg(tmp_path):
    assert sha_of(RETRIEVER_PATH) == RETRIEVER_BASELINE_SHA
    gauge = load_gauge(tmp_path, "k2")
    hits = gauge.product_hit_dicts(ann_rows())
    #: 正控：同一套加载机械、不加任何刀，界成立。
    pristine = load_retriever_copy(tmp_path, "k2_control")
    control = gauge.displacement_report(hits, ORDER_BOOKED_PRIORS, widths=(5, 12, 40),
                                        module=pristine)
    for width in (5, 12, 40):
        assert order_verdict(control, width) == [], width
    assert [(m["source"], m["previous_rank"], m["new_rank"], m["places_moved"])
            for m in control["40"]["moves"]] == [tuple(row[:4]) for row in BOOKED_MOVES_AT_40]
    #: 刀下：轮数换成腿宽 ⇒ 真库窗口上必须量出超过一名。
    widened = load_retriever_copy(tmp_path, "k2_widened", anchor=K2_ANCHOR,
                                  replacement=K2_REPLACE)
    cut = gauge.displacement_report(hits, ORDER_BOOKED_PRIORS, widths=(5, 12, 40),
                                    module=widened)
    reds = order_verdict(cut, 40)
    assert reds, "把界换成分母之后次序腿还绿 ⇒ 这枚界是空的"
    assert cut["40"]["max_abs_places_moved"] > 1, cut["40"]
    assert cut["40"]["bound_constant_in_module"] == 1, "常量本身不该被这枚刀动到"
# ==================== K3 ====================

#: 把闸门摸成「设不设都连库」。
K3_ANCHOR = "    return raw in OPT_IN_ON_VALUES\n"
K3_REPLACE = "    return True\n"


def test_k3_always_open_gate_makes_the_resident_tool_connect(tmp_path):
    from _r648_gauge_harness import Tripwire

    pristine = load_gauge(tmp_path, "k3_control")
    wire = Tripwire(pristine).install()
    assert pristine.run_report(env={})["legs"].values() is not None
    assert wire.fired == 0, wire.calls

    opened = load_gauge(tmp_path, "k3_gate_open", edits=[(K3_ANCHOR, K3_REPLACE)])
    assert opened.gate_declared(env={}) is True
    wire = Tripwire(opened).install()
    report = opened.run_report(env={}, legs=("identity",))
    assert wire.fired >= 1, "闸门被摸成恒开却一枚子进程都没发 ⇒ 绊线是空的"
    assert report["legs"]["identity"]["status"] != "unmeasured"
    assert opened.REASON_GATE_OFF == pristine.REASON_GATE_OFF


# ==================== K4 ====================

#: 把两列折成一枚净值（净值一列的方案从一开始就把区别抹掉）。
K4_ANCHOR = "        return activity_priors(row_reader=lambda: list(rows))\n"
K4_REPLACE = ("        return activity_priors(row_reader=lambda: [\n"
              "            (name, str(max(int(accepted) - int(rejected), 0)), \"0\")\n"
              "            for name, accepted, rejected in rows])\n")


def test_k4_folding_the_two_columns_into_a_net_loses_the_distinction(tmp_path):
    control = load_gauge(tmp_path, "k4_control")
    leg = BOOKED_CONC["mixed_columns"]
    folded = control.fold_rows_to_priors(BOOKED_MIXED_ROWS)
    assert folded[leg["filename"]] == {"accepted": 12, "rejected": 12}
    assert columns_verdict(leg, folded) == []

    net = load_gauge(tmp_path, "k4_net_fold", edits=[(K4_ANCHOR, K4_REPLACE)])
    folded = net.fold_rows_to_priors(BOOKED_MIXED_ROWS)
    assert folded[leg["filename"]] == {"accepted": 0, "rejected": 0}, folded
    assert columns_verdict(leg, folded), "折成净值之后混排腿还绿 ⇒ 那格只有纸上说"


# ==================== 总清点 ====================

def test_the_teeth_leave_the_repo_untouched(tmp_path):
    """四把刀跑完之后：两份原件仍是原样，影子只落在 ``tmp_path``（仓内一枚都不许有）。"""
    load_gauge(tmp_path, "tally")
    load_retriever_copy(tmp_path, "tally_retriever")
    assert sha_of(RETRIEVER_PATH) == RETRIEVER_BASELINE_SHA
    assert sha_of(GAUGE_PATH) == GAUGE_BASELINE_SHA
    shadows = sorted(item.name for item in Path(tmp_path).glob("r648_*.py"))
    assert shadows, "影子端一枚文件都没落 ⇒ 这几把刀没真跑"
    assert not list(REPO.glob("r648_*.py")), "影子落进仓内了"