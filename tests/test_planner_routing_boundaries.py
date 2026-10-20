from app.agents.planner import build_task_plan
from langchain_core.messages import AIMessage, HumanMessage


def _workers(question):
    return [task["worker"] for task in build_task_plan(question)]


def test_policy_question_about_expense_standard_routes_only_to_documents():
    assert _workers("住宿费用通常按什么标准报销？超过标准需要准备哪些材料？") == ["doc"]


def test_approval_flow_summary_does_not_precheck_a_nonexistent_expense():
    assert _workers("请依据差旅制度汇总报销审批环节，演示编号193416") == ["doc"]
    assert "approval" in _workers("请预审申请金额500元的报销，并说明审批流程")


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
