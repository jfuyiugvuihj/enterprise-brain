from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Send
from app.agents.orchestrator import route_main


def test_policy_comparison_does_not_create_an_expense_precheck_after_document_answer():
    state = {
        'messages': [HumanMessage(content='仅依据以下文件《新版.pdf》《旧版.pdf》回答：\n比较600元审批要求'),
                     AIMessage(content='', tool_calls=[{'name': 'dispatch', 'args': {'workers': ['approval']}, 'id': 'comparison'}])],
        'worker_results': {'doc': '新版财务负责人审批；旧版部门经理审批'},
        'plan': [{'worker': 'doc'}, {'worker': 'approval'}],
    }
    result = route_main(state, {'configurable': {'declared_lane': 'qa'}})
    assert result == 'reflect'


def test_actual_expense_precheck_remains_available_in_question_mode():
    state = {
        'messages': [HumanMessage(content='帮我预审600元住宿费是否超标'),
                     AIMessage(content='', tool_calls=[{'name': 'dispatch', 'args': {'workers': ['approval']}, 'id': 'expense'}])],
        'worker_results': {'doc': '住宿费标准'},
        'plan': [{'worker': 'doc'}, {'worker': 'approval'}],
    }
    result = route_main(state, {'configurable': {'declared_lane': 'qa'}})
    assert [node.node for node in result if isinstance(node, Send)] == ['approval']
