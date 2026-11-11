"""R42 判据④的靶纸：每条规则都有代表题，摘掉任何一条必有一条红在这里。

断言的是 (lane, rule) 两个字段，不只 lane——两条规则可以给出同一条道
（制图词与算数词都给分析档），只断言 lane 的靶纸摘掉一条规则也不会红，
那正是判据④要防的假绿。

总控 09-18 新增 ⑤ 之后，规则的先后是：产物词 > 制图词 > **口径×取值动词** >
复合连接词 > 口径定义 > 算数词 > 默认快道。metric-12 这类"算…用哪个分母"
由 ⑤ 接管（要算的是它），metric-04 这类"按什么口径统计"仍归口径定义条。题面全部取自 tests/fixtures/business_evaluation_100.jsonl
的原文（只读，不改写），另加一条 R30 用例原题；少数跨文件借来的题面在用例名里注明。
"""
import pytest

from app.agents.nodes import LANE_ANALYSIS, LANE_QA, LANE_REPORT, classify_route

#: (题面, 期望道, 期望规则名, 用例名)
RULE_TABLE = [
    ("把分析导出成PDF", LANE_REPORT, "report_marker", "tool-01 导出词"),
    ("生成本月差旅费用分析周报", LANE_REPORT, "report_marker", "report-01 周报词"),
    ("刚才的下载链接打不开了", LANE_REPORT, "report_marker", "tool-03 下载链接"),
    ("项目月报里，项目部怎么判定里程碑已完成？", LANE_REPORT, "report_marker", "metric-18 月报里"),
    ("画各部门超标率对比图并标注统计口径", LANE_ANALYSIS, "artifact", "chart-04 制图词压过口径词"),
    ("生成部门费用柱状图", LANE_ANALYSIS, "artifact", "chart-01 柱状图"),
    ("查一下报销制度，并且看看门店利润", LANE_ANALYSIS, "compound", "r30 复合连接词"),
    ("销售部的活跃客户数按什么口径统计？", LANE_QA, "definitional", "metric-04 口径题"),
    ("人力资源部算人均产值用哪个分母？", LANE_ANALYSIS, "caliber_value", "metric-12 分母×取值动词"),
    ("住宿费按晚还是按天？", LANE_QA, "definitional", "metric-03 算法定义"),
    ("哪个部门花费最高？", LANE_ANALYSIS, "analysis_marker", "data-01 最值"),
    ("各月份报销金额的环比变化", LANE_ANALYSIS, "analysis_marker", "data-06 环比"),
    ("有没有费用异常？", LANE_ANALYSIS, "analysis_marker", "insight-01 异常"),
    ("按财务部口径算本月销售额是多少？", LANE_ANALYSIS, "caliber_value", "metric-06 ⑤形状规则"),
    ("财务部算人均产值用哪个分母？", LANE_ANALYSIS, "caliber_value", "metric-13 ⑤形状规则"),
    ("财务部把这笔报销费用算进哪个月？", LANE_QA, "definitional", "metric-10 归属问法不算⑤"),
    ("销售部的活跃客户数按什么口径统计？", LANE_QA, "definitional", "metric-04 口径条（被⑤上移后仍要在）"),
    ("住宿费标准是多少？", LANE_QA, "default", "doc-01 默认快道"),
    ("餐费和住宿费的票能开在一张上吗？", LANE_QA, "default", "doc-08 裸和不算复合"),
    ("城市间交通和市内交通执行同一标准吗？", LANE_QA, "default", "doc-18 裸和不算复合"),
    ("图表数据来自哪里？", LANE_QA, "default", "chart-03 问来源不是要图"),
    ("我昨晚住了650元，能报多少？", LANE_QA, "default", "chat-01 裸多少不算算数"),
    ("下个月会不会裁员？", LANE_QA, "default", "unsupported-04 无证据题"),
]


@pytest.mark.parametrize(
    "question, lane, rule",
    [(case[0], case[1], case[2]) for case in RULE_TABLE],
    ids=[case[3] for case in RULE_TABLE],
)
def test_each_rule_owns_its_own_lane_verdict(question, lane, rule):
    """每条规则各管一批题；摘掉它，这批题的道或规则名必有一个变。"""
    decision = classify_route(question)

    assert decision.lane == lane, f"{question} 判到 {decision.lane}/{decision.rule}，期望 {lane}"
    assert decision.rule == rule, f"{question} 由 {decision.rule} 定档，期望 {rule}"


@pytest.mark.parametrize("question", ["", "   ", None])
def test_an_empty_question_is_the_cheapest_lane(question):
    """空题面不得抛异常，也不得被推到重流程上。"""
    assert classify_route(question).lane == LANE_QA


def test_a_decision_always_names_its_rule_and_carries_a_real_tier():
    """判据①的另一半：输出必须是"选哪个档"，且档位在 R30 的枚举里。"""
    from app.agents.contracts import ModelTier
    from app.agents.nodes import LANE_TIERS

    for case in RULE_TABLE:
        decision = classify_route(case[0])
        assert isinstance(decision.tier, ModelTier)
        assert decision.tier is LANE_TIERS[decision.lane]
        assert decision.matched or decision.rule in ("default", "empty"), decision


def test_the_report_rule_wins_over_the_chart_rule():
    """产物词排在制图词之前：既画图又导出的一轮走报告档，不能被分析档吃掉。"""
    decision = classify_route("把各季度营收画成柱状图并导出报告")

    assert decision.lane == LANE_REPORT
    assert "报告" in decision.matched


def test_the_compound_rule_wins_over_a_definition_question():
    """复合连接词排在口径定义之前：两件独立的事该拆，哪怕每件都像查制度。"""
    decision = classify_route("住宿费的口径是什么，并且把差旅的口径也说明白")

    assert decision.lane == LANE_ANALYSIS
    assert decision.rule == "compound"
