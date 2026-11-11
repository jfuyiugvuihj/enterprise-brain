# -*- coding: utf-8 -*-
"""R520 判据⑤ —— 反证刀：每一枚都必须咬在「本单新钉」上，而且有一枚要证明在册那枚看不见。

## 口径

🔴 全程只在临时根副本上动手：把量具读进内存、按锚点改一处、写到 tmp_path，再加载那一份副本
跑同一场判断；跟踪里的原件一个字节都不动（每把刀前后各核一次 sha256，最后一枚用例总清点）。
每把刀都带一枚**影子端正控** —— 同一场判断在未变异的真树上必须先是那个读数，不然「红」
只是它本来就红，量不出任何东西。

派工词点名要的两把都在：K1 摘读取腿（os.getenv 那一行整枚换成空串）、K4/K5 改宽值比较
（== 换成子串 in / 换成真值判断）。另附 K2/K3（两枚 .strip() 各自摘掉）、K6/K7（lane 字面
漂走／两档撞同一枚字面）—— 强度只升，方向是加刀不是换刀。

## K1 顺手量出来的一格事实（写在这里，免得下一班误读在册覆盖）

在册那枚 tests/test_r222_queue_terminal_stopwatch.py 里的
test_r226_lane_declaration_still_travels_only_the_declared_tier 走的是
monkeypatch.setattr(模块, "DECLARE_LANE_TIER", ...)：它绕开了环境读取腿。所以 K1 变异之后
**它照旧绿**（本件 test_k1 把这一步当场量出来，不是推断）。这正是本单要补的缺口 ——
派工词「EVAL_DECLARE_LANE_TIER 在 tests 里零命中」为真，但「常量层面零钉」为假：
常量有一枚属性钉，环境读取腿才是今天这单补的那一块。
"""
from __future__ import annotations

import contextlib
import hashlib

from test_r520_declare_lane_env_leg import (  # noqa: T401  共用同一套离线假出口与题册
    REPORT_LANE,
    REPORT_TIER,
    SCRIPT_PATH,
    fixture_rows,
    lane_via_attribute,
    lanes_sent,
    ruler,
)
from test_r520_report_lane_contract import (  # noqa: T401  接缝判据只用那一枚函数，不另写宽口径
    lane_word_violations,
    product_lane_literals,
)

#: 本件一进来就抄下的原件指纹：每把刀跑完都要回到它上面。
BASELINE_SHA = hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest()

#: 锚点全部现取唯一（不唯一的刀等于没动东西，mutant() 当场红）。
KNIVES = {
    "K1_env_read_leg_gone": {
        "anchor": 'DECLARE_LANE_TIER = os.getenv("EVAL_DECLARE_LANE_TIER", "").strip()',
        "replace": 'DECLARE_LANE_TIER = ""',
        "victim": "判据①②③ 的全部环境用例（本件另证：在册那枚属性钉对此全盲）",
    },
    "K2_env_value_not_stripped": {
        "anchor": 'DECLARE_LANE_TIER = os.getenv("EVAL_DECLARE_LANE_TIER", "").strip()',
        "replace": 'DECLARE_LANE_TIER = os.getenv("EVAL_DECLARE_LANE_TIER", "")',
        "victim": "test_the_env_value_is_stripped_before_it_is_compared",
    },
    "K3_row_tier_not_stripped": {
        "anchor": 'tier = str(row.get("tier", "")).strip()',
        "replace": 'tier = str(row.get("tier", ""))',
        "victim": "test_the_row_tier_is_stripped_before_it_is_compared",
    },
    "K4_substring_counts_as_match": {
        "anchor": 'lane = LANE_BY_TIER.get(tier, "") if DECLARE_LANE_TIER and tier == DECLARE_LANE_TIER else ""',
        "replace": 'lane = LANE_BY_TIER.get(tier, "") if DECLARE_LANE_TIER and tier in DECLARE_LANE_TIER else ""',
        "victim": "test_a_declared_value_that_only_contains_a_tier_name_is_not_a_match",
    },
    "K5_truthiness_counts_as_match": {
        "anchor": 'lane = LANE_BY_TIER.get(tier, "") if DECLARE_LANE_TIER and tier == DECLARE_LANE_TIER else ""',
        "replace": 'lane = LANE_BY_TIER.get(tier, "") if DECLARE_LANE_TIER and tier else ""',
        "victim": "test_declaring_a_tier_sends_lanes_for_exactly_that_tier_across_the_corpus",
    },
    "K6_report_lane_word_drifts": {
        "anchor": '"报告": "report"',
        "replace": '"报告": "reports"',
        "victim": "test_the_report_tier_sends_the_very_string_the_queue_gate_reads 与接缝钉",
    },
    "K7_analysis_lane_word_collides": {
        "anchor": '"分析": "analysis"',
        "replace": '"分析": "report"',
        "victim": "lane_word_violations 那一枚「两档共用同一 lane」的接缝判据",
    },
}


def report_rows():
    return [row for row in fixture_rows() if row.get("tier") == REPORT_TIER]


def lanes_on(source, tmp_path, env, rows, tag):
    """在指定那一份采集器源码上跑一题册，交回 {题号: 发出去的 lane（None = 没发）}。"""
    with ruler(tmp_path, env=env, source_path=source, tag=tag) as module:
        return lanes_sent(module, rows)


def violations_on(source, tmp_path, tag):
    """在指定那一份源码上跑接缝判据：交回违规清单（空 = 合格）。用的还是 contract 件那一段代码。"""
    with ruler(tmp_path, env=REPORT_TIER, source_path=source, tag=tag) as module:
        return lane_word_violations(dict(module.LANE_BY_TIER), product_lane_literals())


@contextlib.contextmanager
def mutant(tmp_path, name):
    """把量具按锚点改出一枚副本，交回副本路径；原件前后各核一次指纹。"""
    original = SCRIPT_PATH.read_bytes()
    assert hashlib.sha256(original).hexdigest() == BASELINE_SHA, "进刀之前原件就不是原样了"
    text = original.decode("utf-8").replace("\r\n", "\n")
    anchor = KNIVES[name]["anchor"]
    hits = text.count(anchor)
    assert hits == 1, name + "：锚点在原件里出现 " + str(hits) + " 次，不唯一 ⇒ 这枚反证是空的"
    mutated = text.replace(anchor, KNIVES[name]["replace"], 1)
    assert mutated != text, name + "：改了个寂寞"
    target = tmp_path / ("r520_" + name + ".py")
    target.write_text(mutated, encoding="utf-8", newline="\n")
    assert SCRIPT_PATH.read_bytes() == original, name + "：跟踪里的原件被动了"
    yield target
    assert hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest() == BASELINE_SHA, \
        name + "：反证跑完原件不是原样"


# ==================== K1 摘掉环境读取腿 ====================

def test_k1_dropping_the_env_read_leg_goes_red_here(tmp_path):
    """反证一：把 :220 那一行换成空串（＝环境这一路彻底不存在）。

    正控（真树）：设「报告」⇒ 报告档 20 题全发 report。
    刀下：同一枚环境设进去 ⇒ 一题都不发。本单每一条判据都从环境起跳，所以这里必红。
    """
    rows = report_rows()
    want = {str(row["id"]): REPORT_LANE for row in rows}
    assert lanes_on(SCRIPT_PATH, tmp_path, REPORT_TIER, rows, "k1-control") == want, \
        "影子端正控就不成立 ⇒ 下面那声红不算牙"
    with mutant(tmp_path, "K1_env_read_leg_gone") as copy:
        got = lanes_on(copy, tmp_path, REPORT_TIER, rows, "k1")
    assert got != want, "摘掉读取腿还照发 lane ⇒ 本件的钉是空的"
    assert set(got.values()) == {None}, repr(got)


def test_k1_is_invisible_to_the_registered_attribute_pin(tmp_path):
    """K1 的归因：在册那枚 r226 属性钉对同一枚变异全盲 —— 它设的字段还在，它就照旧绿。

    这一枚不是判据，是「本单补的不是重复钉」的证据：读法与 test_r222 一字不差（直接
    setattr 常量），只是把源码换成 K1 那一版。
    """
    with mutant(tmp_path, "K1_env_read_leg_gone") as copy:
        with ruler(tmp_path, env="", source_path=copy, tag="k1-attr") as module:
            assert module.DECLARE_LANE_TIER == "", "环境设了空串，读取腿已被摘净"
            assert lane_via_attribute(module, REPORT_TIER) == REPORT_LANE, \
                "在册那条 setattr 路在 K1 下也红了 ⇒ 它其实读过环境，本单的缺口说法要改"


# ==================== K2 / K3 两枚 .strip() ====================

def test_k2_dropping_the_strip_on_the_env_value_goes_red_here(tmp_path):
    """反证二：读取腿上那枚 .strip() 摘掉 ⇒ 「.env 里多一个尾空格」从此等于没开相 2。"""
    rows = report_rows()
    want = {str(row["id"]): REPORT_LANE for row in rows}
    assert lanes_on(SCRIPT_PATH, tmp_path, "  报告  ", rows, "k2-control") == want, \
        "影子端正控不成立（带空格的声明本该认）"
    with mutant(tmp_path, "K2_env_value_not_stripped") as copy:
        got = lanes_on(copy, tmp_path, "  报告  ", rows, "k2")
    assert got != want, "不 strip 也认得出来 ⇒ 那枚 .strip() 是永真装饰，本件不该为它留钉子"
    assert set(got.values()) == {None}, repr(got)


def test_k3_dropping_the_strip_on_the_row_tier_goes_red_here(tmp_path):
    """反证三：题面档位那枚 .strip() 摘掉 ⇒ 夹具或派生表多一个空格就整档漏发。"""
    rows = [{"id": "sp-01", "question": "Q1", "tier": " 报告"},
            {"id": "sp-02", "question": "Q2", "tier": "报告 "}]
    want = {"sp-01": REPORT_LANE, "sp-02": REPORT_LANE}
    assert lanes_on(SCRIPT_PATH, tmp_path, REPORT_TIER, rows, "k3-control") == want
    with mutant(tmp_path, "K3_row_tier_not_stripped") as copy:
        got = lanes_on(copy, tmp_path, REPORT_TIER, rows, "k3")
    assert got != want, "题面空格也照样认 ⇒ 这一枚 strip 没被量到过"
    assert set(got.values()) == {None}, repr(got)


# ==================== K4 / K5 值比较改宽 ====================

def test_k4_widening_the_compare_to_a_substring_goes_red_here(tmp_path):
    """反证四（派工词点名那把·其一）：== 换成 in ⇒ 「分析报告」这种声明会把报告档整批发出去。"""
    rows = report_rows()
    want = {str(row["id"]): None for row in rows}
    assert lanes_on(SCRIPT_PATH, tmp_path, "分析报告", rows, "k4-control") == want, \
        "影子端正控不成立：子串从来不算同一个档位名"
    with mutant(tmp_path, "K4_substring_counts_as_match") as copy:
        got = lanes_on(copy, tmp_path, "分析报告", rows, "k4")
    assert got != want, "子串也算配上 ⇒ 值比较改宽没人拦"
    assert set(got.values()) == {REPORT_LANE}, repr(sorted({str(v) for v in got.values()}))


def test_k5_widening_the_compare_to_truthiness_goes_red_here(tmp_path):
    """反证五（派工词点名那把·其二）：整枚比较换成「有档位就发」⇒ 三档一起入队。"""
    rows = fixture_rows()
    base = lanes_on(SCRIPT_PATH, tmp_path, REPORT_TIER, rows, "k5-control")
    assert {rid for rid, lane in base.items() if lane} == {str(row["id"]) for row in report_rows()}, \
        "影子端正控不成立"
    with mutant(tmp_path, "K5_truthiness_counts_as_match") as copy:
        got = lanes_on(copy, tmp_path, REPORT_TIER, rows, "k5")
    assert got != base, "值比较被摘掉还是这个读数 ⇒ 本件的判据③ 是空的"
    widened = {rid for rid, lane in got.items() if lane}
    assert len(widened) > len({str(row["id"]) for row in report_rows()}), repr(sorted(widened))
    assert any(lane != REPORT_LANE for lane in got.values() if lane), \
        "只有报告档多发了 ⇒ 这枚刀没摘到值比较上"


# ==================== K6 / K7 lane 字面漂移 ====================

def test_k6_a_drifted_report_lane_word_goes_red_here(tmp_path):
    """反证六：报告档改发 reports ⇒ 服务端按闭集当场 400，队列闸也永远不认它。

    这一枚要的就是接缝：光看「有没有发 lane」（判据②）是绿得过去的，字面漂了才发现得晚。
    """
    rows = report_rows()[:3]
    want = {str(row["id"]): REPORT_LANE for row in rows}
    assert lanes_on(SCRIPT_PATH, tmp_path, REPORT_TIER, rows, "k6-control") == want
    assert violations_on(SCRIPT_PATH, tmp_path, "k6-control") == []
    with mutant(tmp_path, "K6_report_lane_word_drifts") as copy:
        got = lanes_on(copy, tmp_path, REPORT_TIER, rows, "k6")
        problems = violations_on(copy, tmp_path, "k6")
    assert got != want, "字面漂了读数还一样 ⇒ 本件读的不是载荷"
    assert set(got.values()) == {"reports"}, repr(got)
    assert problems, "接缝判据放过了 reports ⇒ 那是它没牙"
    assert any("闭集" in line for line in problems), repr(problems)
    assert any("队列闸" in line for line in problems), repr(problems)


def test_k7_two_tiers_sharing_one_lane_word_goes_red_here(tmp_path):
    """反证七：分析档也发 report ⇒ 声明档位与入队判定不再一一对应。

    归因要写清：这一枚**发没发**那一层看不出来（发 lane 的名册一字未动，所以
    tests/test_r520_declare_lane_env_leg.py 那几条照旧绿）—— 咬得住它的只有接缝上
    「两档共用同一枚字面」这一条。本件当场把这两面都量出来。
    """
    rows = fixture_rows()
    base = lanes_on(SCRIPT_PATH, tmp_path, REPORT_TIER, rows, "k7-control")
    assert violations_on(SCRIPT_PATH, tmp_path, "k7-control") == []
    with mutant(tmp_path, "K7_analysis_lane_word_collides") as copy:
        got = lanes_on(copy, tmp_path, REPORT_TIER, rows, "k7")
        problems = violations_on(copy, tmp_path, "k7")
    assert problems, "两档撞同一枚 lane 还没人拦 ⇒ 接缝判据是装饰"
    assert any("同一枚 lane" in line for line in problems), repr(problems)
    assert {rid for rid, lane in got.items() if lane} == {rid for rid, lane in base.items() if lane}, \
        "这一枚刀连发没发都改了 ⇒ 它摘的不是分析档的字面，锚点搭错了"


# ==================== 原件指纹总清点 ====================

def test_the_tracked_ruler_is_byte_identical_after_every_overlay_proof():
    """七把刀全走临时根：跟踪里的原件必须与进件那一刻逐字节同一，且每枚锚点还都在原地。"""
    data = SCRIPT_PATH.read_bytes()
    assert hashlib.sha256(data).hexdigest() == BASELINE_SHA
    text = data.decode("utf-8")
    for name, knife in KNIVES.items():
        assert text.count(knife["anchor"]) == 1, name + "：原件里的锚点不唯一或已漂走"
    assert 'DECLARE_LANE_TIER = os.getenv("EVAL_DECLARE_LANE_TIER", "").strip()' in text
    assert '"报告": "report", "分析": "analysis", "问答": "qa"' in text
