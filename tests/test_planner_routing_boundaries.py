from app.agents.planner import build_task_plan
from langchain_core.messages import AIMessage, HumanMessage


def _workers(question):
    return [task["worker"] for task in build_task_plan(question)]


def test_policy_question_about_expense_standard_routes_only_to_documents():
    assert _workers("住宿费用通常按什么标准报销？超过标准需要准备哪些材料？") == ["doc"]


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
