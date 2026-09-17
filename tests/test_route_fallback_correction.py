"""R27 前置：钉死 route_main 的关键词 / 计划兜底路径。

判据来源：docs/handoff/2026-09-15-backend-followup-requests.md §21 R27 判据②
——“先加测试钉住兜底仍能纠正错派”，之后才允许删 Supervisor 两发往返。

被钉死的实现（app/agents/orchestrator.py）：
- :283 abstained 判定、:285 计划分支入口
- :289-292 计划分支内按需追加 chart / export（elif ⇒ 一轮只追加一个副作用 worker）
- :293-308 else 分支的 chart_kw → export_kw → doc_kw → data_kw 关键词纠正
- :309-313 纯副作用派发时补齐计划里未完成的分析型 worker

:293-308 就是 R27 的禁改边界。变异验证：临时注释掉 :301-305 的 doc_kw 分支，
本文件前三个用例必须变红；`git checkout -- app/agents/orchestrator.py` 之后
必须重新变绿，且 `git diff -- app/agents/orchestrator.py` 为空。
"""
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.orchestrator import route_main

# 制度/报销类：命中 doc_kw，且刻意不命中 chart_kw / export_kw / data_kw。
POLICY_QUESTION = "差旅报销制度里住宿费标准是多少？超过标准要准备什么材料？"
# 图表类：命中 chart_kw（画/图/柱状图），同时带数据分析语义。
CHART_QUESTION = "把各季度营收画成柱状图"
# 导出类：只命中 export_kw。
EXPORT_QUESTION = "把这季度营收情况整理一下并导出报告"
# 一个兜底关键词都不命中，用来验证兜底不反噬正常路径。
NEUTRAL_QUESTION = "把这季度营收情况整理一下"
# 同时命中 chart_kw 与 export_kw。
CHART_AND_EXPORT_QUESTION = "把各季度营收画成折线图并导出报告"
# 文档引用陷阱：剥离《…》之后 export_kw 不该再命中。
DOC_REFERENCE_QUESTION = "《差旅报销制度.pdf》里住宿费标准是多少？"


def _dispatched(*workers):
    """supervisor 派发了这些 worker 时的那条 AI 消息。"""
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


def _abstained():
    """supervisor 既没派发也没给正文，即 route_main:283 的 abstained。"""
    return AIMessage(content="")


def _answered():
    """supervisor 直接给出最终回答：有正文、无派发。"""
    return AIMessage(content="结论已经整理好了，无需再派发子 Agent。")


def _route(question, supervisor, plan=(), worker_results=None):
    """走一遍 route_main，返回本轮最终派发的 worker 列表（顺序敏感）。"""
    state = {"messages": [HumanMessage(content=question), supervisor]}
    if plan:
        state["plan"] = [{"worker": w, "objective": f"step-{w}"} for w in plan]
    if worker_results is not None:
        state["worker_results"] = dict(worker_results)

    result = route_main(state)
    assert result != "reflect", "本轮没有派发任何 worker，兜底纠正链已失效"
    assert result[0] == "main_tools"
    return [getattr(item, "node", None) for item in result if not isinstance(item, str)]


def _reflect(question, supervisor, plan=(), worker_results=None):
    """同上，但断言本轮以 reflect 收敛。"""
    state = {"messages": [HumanMessage(content=question), supervisor]}
    if plan:
        state["plan"] = [{"worker": w, "objective": f"step-{w}"} for w in plan]
    if worker_results is not None:
        state["worker_results"] = dict(worker_results)
    assert route_main(state) == "reflect"


# ==================== 判据 1：doc_kw 纠正错派 ====================


def test_policy_question_moves_wrong_data_dispatch_back_to_doc():
    """supervisor 把制度问题错派给 data，兜底必须改派 doc。"""
    assert _route(POLICY_QUESTION, _dispatched("data")) == ["doc"]


def test_policy_question_still_corrected_when_plan_is_a_single_data_step():
    """单步 data 计划 + 未弃权时，关键词纠正仍然优先于计划。"""
    assert _route(
        POLICY_QUESTION, _dispatched("data"), plan=["data"]
    ) == ["doc"]


def test_document_reference_does_not_keep_a_wrong_export_dispatch():
    """《xxx.pdf》是被提问对象，剥离后 doc_kw 必须把 export 错派改回 doc。"""
    assert _route(DOC_REFERENCE_QUESTION, _dispatched("export")) == ["doc"]


# ==================== 判据 2：chart_kw 纠正为图表 ====================


def test_chart_intent_overrides_the_wrong_data_dispatch():
    """含图表意图的问题被错派给 data，兜底纠正为单独的 chart。"""
    assert _route(CHART_QUESTION, _dispatched("data")) == ["chart"]


def test_chart_fallback_keeps_planned_retrieval_step_ahead_of_it():
    """chart 兜底不能吞掉计划里未完成的检索步骤：先 doc，再 chart。"""
    assert _route(CHART_QUESTION, _dispatched("data"), plan=["doc"]) == ["doc"]
    assert _route(
        CHART_QUESTION, _abstained(), plan=["doc"], worker_results={"doc": "已取到营收数据"}
    ) == ["chart"]


# ==================== 判据 3：abstained + 计划分支 ====================


def test_abstained_supervisor_defers_to_a_multi_step_plan():
    """弃权 + 多路计划 ⇒ 按确定性计划派发，且中性问题不追加副作用 worker。"""
    assert _route(NEUTRAL_QUESTION, _abstained(), plan=["doc", "data"]) == ["doc", "data"]


def test_plan_branch_appends_export_once_upstreams_are_done():
    """计划分支追加的 export 先被分层挡住，前置完成后再单独放行。"""
    assert _route(EXPORT_QUESTION, _abstained(), plan=["doc", "data"]) == ["doc", "data"]
    assert _route(
        EXPORT_QUESTION,
        _abstained(),
        plan=["doc", "data"],
        worker_results={"doc": "制度要点", "data": "营收数据"},
    ) == ["export"]


def test_plan_branch_appends_chart_once_upstreams_are_done():
    """计划分支追加的 chart 同样分两轮放行。"""
    assert _route(CHART_QUESTION, _abstained(), plan=["doc", "data"]) == ["doc", "data"]
    assert _route(
        CHART_QUESTION,
        _abstained(),
        plan=["doc", "data"],
        worker_results={"doc": "制度要点", "data": "营收数据"},
    ) == ["chart"]


def test_abstained_supervisor_with_single_step_plan_still_dispatches_it():
    """弃权 + 单步计划也走计划分支；兜底一旦被删，这里会退化成 reflect。"""
    assert _route(NEUTRAL_QUESTION, _abstained(), plan=["data"]) == ["data"]


def test_chart_and_export_only_append_one_side_effect_per_round():
    """同一句话命中 chart_kw 与 export_kw 时，本轮只追加 chart（:291 的 elif）。"""
    assert _route(
        CHART_AND_EXPORT_QUESTION, _abstained(), plan=["doc", "data"]
    ) == ["doc", "data"]
    dispatched = _route(
        CHART_AND_EXPORT_QUESTION,
        _abstained(),
        plan=["doc", "data"],
        worker_results={"doc": "制度要点", "data": "营收数据"},
    )
    assert dispatched == ["chart"]
    assert "export" not in dispatched


# ==================== 判据 4：兜底不得反噬正常路径 ====================


def test_answered_turn_with_single_step_plan_terminates():
    """supervisor 已给出正文 ⇒ 未弃权，单步计划不得把这一轮重新派发出去。"""
    _reflect(NEUTRAL_QUESTION, _answered(), plan=["data"])


def test_single_step_plan_does_not_clobber_a_multi_worker_dispatch():
    """supervisor 正常派发多路时，单步计划与关键词都不得改写这轮决策。"""
    assert _route(
        NEUTRAL_QUESTION, _dispatched("doc", "data"), plan=["data"]
    ) == ["doc", "data"]


def test_keyword_fallback_leaves_a_clean_data_dispatch_alone():
    """纯数据问题被正确派给 data 时，兜底不插手。"""
    assert _route(
        "统计一下三个区域的营收情况", _dispatched("data")
    ) == ["data"]