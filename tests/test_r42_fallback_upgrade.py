"""R42 判据②：判别器判成"快道/问答档"时，既有兜底仍能把它升回分析档/报告档。

这条是"规则优先"敢偏向快道的全部前提。被升档的通道一条都不新造，全是既有的：
- app/agents/orchestrator.py route_main 的关键词兜底（chart_kw / export_kw / doc_kw / data_kw）
- app/agents/nodes.py reflect_node 的"要图没图 / 要导出没下载链接 / 答案里有'无法'"
- app/agents/orchestrator.py route_reflect 的 redo → 回 supervisor

判别器在 route_main 里只允许**补一次读操作**（问答档的弃权轮补派 doc），
它在代码顺序上排在关键词兜底之后，且只在 workers 仍为空时生效——所以它永远
不可能盖住一条升档指令。摘掉这个先后关系（把补派挪到关键词之前，或去掉
`not workers` 条件），本文件对应用例必须变红（判据④的刀三）。
"""
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.nodes import (
    LANE_ANALYSIS,
    LANE_QA,
    LANE_REPORT,
    classify_intent,
    classify_route,
    reflect_node,
    route_reflect,
)
from app.agents.orchestrator import route_main

#: 判别器认为"问的是来源，不是要图"（评测集 chart-03，标注档位=问答）。
CHART_PROVENANCE = "图表数据来自哪里？"
#: 判别器眼里没有任何产物词，但 route_main 的 export_kw 有"下载"。
DOWNLOAD_SOURCE = "这份制度的原文在哪里下载？"
#: 兜底关键词一条都不命中，问答档补派 doc 的唯一适用面。
NO_SIGNAL_QUESTION = "CEO的持股比例是多少？"
#: 报告档的弃权轮：补派只给读操作，副作用一轮仍归 reflect。
REPORT_WITHOUT_FALLBACK_HIT = "周报里要写什么？"
#: 判别器故意不收裸"统计"（本语料里它是名词），升档交给 data_kw 兜底。
AGGREGATION_QUESTION = "统计一下三个区域的营收情况"
#: 问答档的题，检索回来一句"无法"⇒ reflect 必须重开这一轮。
MISS_LIGHT_JUDGEMENT = "这个标准去年是多少？"
MISS_LIGHT_FAILURE_ANSWER = "无法从知识库中找到去年的标准。"


def _abstained():
    """supervisor 既没派发也没给正文，即 route_main 的 abstained。"""
    return AIMessage(content="")


def _dispatched(*workers):
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "dispatch",
                "args": {"workers": list(workers)},
                "id": "supervisor-dispatch",
                "type": "tool_call",
            }
        ],
    )


def _routed(question, supervisor=None):
    state = {"messages": [HumanMessage(content=question), supervisor or _abstained()]}
    result = route_main(state)
    if result == "reflect":
        return "reflect"
    return [getattr(item, "node", None) for item in result if not isinstance(item, str)]


# ==================== 兜底升档：关键词通道仍然压过判别器 ====================


def test_the_chart_keyword_fallback_outvotes_the_question_lane():
    """判别器说问答档，chart_kw 说要图 ⇒ 这一轮画图为证：升档。"""
    assert classify_route(CHART_PROVENANCE).lane == LANE_QA

    assert _routed(CHART_PROVENANCE) == ["chart"]


def test_the_export_keyword_fallback_outvotes_the_question_lane():
    """"下载"不在判别器的产物词里，但在 export_kw 里 ⇒ 仍升到副作用一轮。"""
    assert classify_route(DOWNLOAD_SOURCE).lane == LANE_QA

    assert _routed(DOWNLOAD_SOURCE) == ["export"]


def test_the_data_keyword_fallback_outvotes_the_question_lane():
    """判别器故意不收裸"统计"，data_kw 收：这类题照样升到分析档。"""
    assert classify_route(AGGREGATION_QUESTION).lane == LANE_QA

    assert _routed(AGGREGATION_QUESTION) == ["data"]


def test_a_question_lane_fill_never_clobbers_a_real_dispatch():
    """问答档的补派只在"什么都没定"时生效，supervisor 已经派好的不动它。"""
    assert classify_route(NO_SIGNAL_QUESTION).lane == LANE_QA

    assert _routed(NO_SIGNAL_QUESTION, _dispatched("data")) == ["data"]


# ==================== 判别器自己：只补读操作 ====================


def test_the_fill_adds_a_read_on_a_dead_question_turn():
    """弃权 + 无计划 + 关键词全空：问答档补一次 doc 检索，替掉一整轮空转。"""
    assert _routed(NO_SIGNAL_QUESTION) == ["doc"]


def test_the_fill_refuses_to_invent_a_side_effect_for_the_report_lane():
    """报告档的弃权轮原样落回 reflect：副作用 worker 不由便宜规则代发。"""
    assert classify_route(REPORT_WITHOUT_FALLBACK_HIT).lane == LANE_REPORT

    assert _routed(REPORT_WITHOUT_FALLBACK_HIT) == "reflect"


def test_the_analysis_lane_dead_turn_is_left_exactly_as_today():
    """分析档的弃权轮一字未改：判别器不替它派 worker，仍然落回 reflect。

    这条同时是本单的边界声明——快道补派只覆盖问答档，另两条道的弃权轮今天没人兜，
    交了 R42 也没人兜，写在交付说明的"没做什么"里。
    """
    assert classify_route("各部门费用的环比变化").lane == LANE_ANALYSIS

    assert _routed("各部门费用的环比变化") == "reflect"


# ==================== 兜底升档：reflect 通道 ====================


def test_reflect_reopens_a_turn_the_question_lane_called_good_enough():
    """判成问答档、检索回一句"无法" ⇒ reflect 判 redo，route_reflect 送回 supervisor。"""
    assert classify_route(MISS_LIGHT_JUDGEMENT).lane == LANE_QA

    state = {
        "messages": [HumanMessage(content=MISS_LIGHT_JUDGEMENT), AIMessage(content=MISS_LIGHT_FAILURE_ANSWER)],
        "final_answer": MISS_LIGHT_FAILURE_ANSWER,
        "worker_results": {"doc": MISS_LIGHT_FAILURE_ANSWER},
    }
    update = reflect_node(state)

    assert update["redo"] is True, "快道判错的轮次没有被 reflect 拦下，升档通道已断"
    state.update(update)
    assert route_reflect(state) == "supervisor"


def test_reflect_still_escalates_a_missing_chart_on_a_question_lane_turn():
    """"要图没图"这条兜底与判别器无关：问答档的题照样重开。"""
    question = "把费用做成图表给我看一下"
    assert classify_route(question).lane in (LANE_QA, LANE_ANALYSIS)

    state = {
        "messages": [HumanMessage(content=question), AIMessage(content="费用合计 1.2 万元。")],
        "final_answer": "费用合计 1.2 万元。",
        "worker_results": {"doc": "费用合计 1.2 万元。"},
    }
    update = reflect_node(state)

    assert update["redo"] is True


# ==================== 判别器没有改写 intent 轴 ====================


def test_the_lane_is_a_separate_axis_from_intent():
    """chat/task 还是 classify_intent 说了算，快慢档只是另一条正交的轴。"""
    assert classify_intent({"messages": [HumanMessage(content="你好")]})["intent"] == "chat"
    assert classify_intent({"messages": [HumanMessage(content="住宿费标准是多少？")]})["intent"] == "task"

    assert classify_route("你好").lane == LANE_QA
    assert classify_route("住宿费标准是多少？").lane == LANE_QA
