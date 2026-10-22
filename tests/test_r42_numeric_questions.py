"""R42 判据⑤（总控 09-18 裁定新增，硬门）：快道不得接任何"要求算出一个数"的题。

裁定形状：一句题里同时出现〔口径/归属词〕与〔取值动词〕⇒ 判分析档。
锚题是 metric-06「按财务部口径算本月销售额是多少？」——它要的是算出来的数，
不是定义；而 metric-01/02/11 那类"报销金额是否包含税/算进哪个月"是口径 lookup，
快道（检索 + CHAT 档）答得对。③ 的占比门已降级为报告值，正确性由这条顶上去。

**本文件对总控给的靶集判据提了一条实测反证**（见
test_report_the_answer_digit_criterion_is_not_executable）：
"用 answer/must_contain 里含数字结果作判据"在这份 fixture 上不可执行——
metric-06 的 must_contain 是「销售额不含税」，一个数字都没有，按它导出就漏掉锚题；
反过来含数字答案的 9 条（doc-01「500元/晚」、chat-11「800元」…）全是
"制度里写着一个数"的 lookup，按它导出会把快道正当题踢出快道。
⇒ 靶集改由**题面形状 + 评测集 category** 导出，"答案含数字"降级为
    一条不得误伤的反向门（test_a_number_written_in_the_policy_...）。

反假绿：词表在本文件里独立成文，不 import 实现的常量。实现侧缩小闭集 ⇒
test_the_marker_closed_sets_match_the_ticket 当场红，靶集不会跟着悄悄缩水。
"""
import json
from pathlib import Path

import pytest

from app.agents.nodes import LANE_QA, classify_route

FIXTURE = Path(__file__).parent / "fixtures" / "business_evaluation_100.jsonl"

#: 取值动词闭集：总控点名的十个词一个不少，另加三个同族硬算数词。
VALUE_VERBS = (
    "是多少", "算", "合计", "占比", "环比", "同比", "趋势", "排名", "总额", "平均",
    "汇总", "除以", "变化",
)

#: 口径/归属词闭集。刻意不含"哪个月"——metric-10/11「把这笔报销费用算进哪个月」
#: 是总控点名的 lookup 正当快道题。
CALIBER_WORDS = ("口径", "分母", "时点", "归口")

#: 形状规则在 105 条题面上应当挡住的确切集合（判据④的靶：摘掉规则 ⇒ 这条红）。
SHAPE_RULE_VICTIMS = {"metric-06", "metric-07", "metric-08", "metric-09", "metric-12", "metric-13"}

#: ⑤ 承认的缺口：形状规则与 category 判据都覆盖不到、目前也真没人兜的题。
#: 只许缩不许涨——新增一条就必须先补规则（判据④之外的第二道闸）。
KNOWN_GAPS = {"data-11", "insight-05"}

#: 总控"答案含数字"判据会误伤的题：数字写在制度里，查出来即可，不需要算。
POLICY_CONSTANT_QUESTIONS = (
    "doc-01", "doc-09", "doc-12", "doc-16", "chat-01", "chat-03", "chat-06", "chat-11", "approval-03",
)


def _rows():
    lines = FIXTURE.read_text(encoding="utf-8-sig").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _hits(text, words):
    return tuple(word for word in words if word in text)


def _shape_hit(question):
    """⑤ 的形状判据：〔口径/归属词〕∧〔取值动词〕。"""
    caliber = _hits(question, CALIBER_WORDS)
    verbs = _hits(question, VALUE_VERBS)
    return caliber, verbs


def _numeric_targets():
    """从评测集导出"答案需要一个算出来的数"的条目：形状 ∪ 计算类 category。

    第三路用 category 而不是题面词，是为了覆盖 data-*/insight-* 那批
    "词面上像问句、答案却要求跑一遍数据"的题；chart-03 靠 `tier != 问答` 排除，
    它问的是数据文件与字段，不是要图。
    """
    targets = {}
    for row in _rows():
        question = row["question"]
        caliber, verbs = _shape_hit(question)
        reasons = []
        if caliber and verbs:
            reasons.append(f"形状：{caliber}×{verbs}")
        if row["category"] == "Excel计算":
            reasons.append("category=Excel计算")
        if row["category"] in ("主动洞察", "图表生成") and row["tier"] != "问答":
            reasons.append(f"category={row['category']}")
        if reasons:
            targets[row["id"]] = (row, reasons)
    return targets


def _scored_targets():
    """靶集去掉登记在案的缺口；缺口集合本身另有用例钉住不得扩大。"""
    return {key: value for key, value in _numeric_targets().items() if key not in KNOWN_GAPS}


TARGET_IDS = sorted(_scored_targets())


@pytest.mark.parametrize("row_id", TARGET_IDS, ids=TARGET_IDS)
def test_a_question_that_wants_a_number_is_never_answered_on_the_fast_lane(row_id):
    """⑤ 主体：每一条"要算出数"的题都必须落在慢道（分析档或报告档）。"""
    row, reasons = _scored_targets()[row_id]
    decision = classify_route(row["question"])

    assert decision.lane != LANE_QA, (
        f"{row_id}（{'; '.join(reasons)}）被判到快道 {decision.rule}，"
        f"而它的答案需要一个算出来的数：{row['question']}"
    )


def test_metric_06_is_named_by_the_shape_rule_itself():
    """总控点名的锚题：不只是"不在快道"，而且必须是 ⑤ 这条规则把它挡住的。"""
    row = next(item for item in _rows() if item["id"] == "metric-06")
    decision = classify_route(row["question"])

    assert row["must_contain"] == ["销售额不含税"], "锚题的评测口径已变，本用例的取证前提失效"
    assert decision.lane == "analysis"
    assert decision.rule == "caliber_value"
    assert "口径" in decision.matched and "算" in decision.matched


def test_the_shape_rule_blocks_exactly_the_named_six_questions():
    """判据④的靶：摘掉 ⑤ 的形状规则，这条第一个红，且红名单指名到题。"""
    blocked = {
        row["id"]
        for row in _rows()
        if classify_route(row["question"]).rule == "caliber_value"
    }

    assert blocked == SHAPE_RULE_VICTIMS, (
        f"形状规则的战果已变：多出来 {sorted(blocked - SHAPE_RULE_VICTIMS)}，"
        f"丢了 {sorted(SHAPE_RULE_VICTIMS - blocked)}"
    )


def test_the_marker_closed_sets_match_the_ticket():
    """反假绿：实现侧的词表必须与本文件独立成文的词表一致，缩小即红。"""
    from app.agents import nodes

    assert set(nodes._CALIBER_MARKERS) == set(CALIBER_WORDS), (
        f"实现侧归属词已漂移：{nodes._CALIBER_MARKERS} vs {CALIBER_WORDS}"
    )
    assert set(nodes._VALUE_VERB_MARKERS) == set(VALUE_VERBS), (
        f"实现侧取值动词已漂移：{nodes._VALUE_VERB_MARKERS} vs {VALUE_VERBS}"
    )
    #: 总控点名的十个词必须一个不少。
    for verb in ("是多少", "算", "合计", "占比", "环比", "同比", "趋势", "排名", "总额", "平均"):
        assert verb in VALUE_VERBS


def test_a_number_written_in_the_policy_stays_on_the_fast_lane():
    """反向门：数字写在制度里的 lookup 不得被 ⑤ 挤到慢道。

    这条就是总控"answer 含数字"判据若照抄会踢掉的那 9 条。放宽任何一侧词表
    （比如把"哪个月"或裸"多少"收进来），这里立刻红。
    """
    rows = {row["id"]: row for row in _rows()}
    for row_id in POLICY_CONSTANT_QUESTIONS:
        row = rows[row_id]
        decision = classify_route(row["question"])
        assert decision.lane == LANE_QA, (
            f"{row_id} 是制度常量查询（答案 {row['must_contain']}），却被判到 {decision.lane}/{decision.rule}"
        )


def test_the_known_gaps_do_not_grow():
    """⑤ 现在遮不到的题只许是登记这两条；多一条就得先补规则再来改这份名单。"""
    gaps = {
        row_id
        for row_id in _numeric_targets()
        if classify_route(_row_by_id(row_id)["question"]).lane == LANE_QA
    }

    assert gaps == KNOWN_GAPS, f"快道上的算数题缺口已变：{sorted(gaps)}"


def _row_by_id(row_id):
    for row in _rows():
        if row["id"] == row_id:
            return row
    raise KeyError(row_id)


def test_report_the_answer_digit_criterion_is_not_executable():
    """取证并打印：按"answer/must_contain 含数字"导出的靶集与真靶集交集为 0。

    这条不判红（判据归总控），只把证据打在输出里，供台账引用：
    锚题 metric-06 的答案里一个数字都没有，而含数字答案的 9 条全是快道正当题。
    """
    import re

    digits = re.compile(r"[0-9]")
    labelled_numeric = [
        row["id"]
        for row in _rows()
        if digits.search(str(row.get("answer") or "") + " ".join(str(x) for x in (row.get("must_contain") or [])))
    ]
    overlap = sorted(set(labelled_numeric) & set(_numeric_targets()))
    print(
        "[R42-⑤取证] 按答案含数字导出={n}条 {ids} | 与形状/category 靶集交集={ov} | "
        "锚题 metric-06 是否被该判据命中={hit}".format(
            n=len(labelled_numeric),
            ids=labelled_numeric,
            ov=overlap,
            hit="metric-06" in labelled_numeric,
        )
    )

    assert labelled_numeric, "评测集答案全无数字，则该判据更无从谈起，请重看取证前提"
