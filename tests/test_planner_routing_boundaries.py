from app.agents.planner import build_task_plan
from langchain_core.messages import AIMessage, HumanMessage


def _workers(question):
    return [task["worker"] for task in build_task_plan(question)]


def test_policy_question_about_expense_standard_routes_only_to_documents():
    assert _workers("住宿费用通常按什么标准报销？超过标准需要准备哪些材料？") == ["doc"]


def test_approval_flow_summary_does_not_precheck_a_nonexistent_expense():
    assert _workers("请依据差旅制度汇总报销审批环节，演示编号193416") == ["doc"]
    assert "approval" in _workers("请预审申请金额500元的报销，并说明审批流程")


def test_general_policy_and_compliance_questions_do_not_start_expense_precheck():
    for question in (
        "报销审批规定是什么？请给出制度原文",
        "比较新版与旧版制度的审批要求有什么不同",
        "这份记录是否符合制度规则？请列出已核验和缺失材料",
        "统计已批准记录的金额合计是多少？",
        "帮我自查报销制度对凭证有哪些要求？",
    ):
        assert "approval" not in _workers(question), question


def test_explicit_expense_precheck_still_uses_existing_worker():
    assert "approval" in _workers("帮我预审600元住宿费是否超标")


def test_model_cannot_turn_an_approval_rule_question_into_expense_precheck():
    from langgraph.types import Send
    from app.agents.orchestrator import route_main

    question = "报销审批规定是什么？请给出制度原文"
    result = route_main({
        "messages": [HumanMessage(content=question), AIMessage(content="", tool_calls=[{
            "name": "dispatch", "args": {"workers": ["approval"]}, "id": "approval-rule",
        }])],
        "plan": [{"worker": "doc"}, {"worker": "approval"}],
    })
    assert [item.node for item in result if isinstance(item, Send)] == ["doc"]


def test_status_aggregation_is_not_an_approval_request():
    assert _workers("仅统计状态为「已批准」或「已支付」的记录，排除「待审批」和「已驳回」，按部门汇总金额并给出合计") == ["data"]


def test_comparative_expense_question_routes_only_to_data():
    assert _workers("哪个部门住宿费最高、哪个最低，差距是多少？") == ["data"]


def test_route_main_keeps_accommodation_comparison_on_data_worker():
    from app.agents.orchestrator import route_main

    result = route_main(
        {
            "messages": [
                HumanMessage(content="如果只看住宿费这一列，最高的记录和平均值相差多少？"),
                AIMessage(content=""),
            ],
            "plan": build_task_plan("如果只看住宿费这一列，最高的记录和平均值相差多少？"),
        }
    )

    nodes = {getattr(item, "node", None) for item in result if hasattr(item, "node")}
    assert "data" in nodes
    assert "doc" not in nodes
