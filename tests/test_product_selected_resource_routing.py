from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Send

from app.agents.orchestrator import route_main


def _routed(question, *, data_filename="", document_filenames=(), workers=("doc", "data")):
    state = {
        "messages": [
            HumanMessage(content=question),
            AIMessage(content="", tool_calls=[{"name": "dispatch", "args": {"workers": list(workers)}, "id": "chosen"}]),
        ],
        "data_filename": data_filename,
        "worker_results": {},
    }
    result = route_main(state, {"configurable": {"document_filenames": list(document_filenames)}})
    return [item.node for item in result if isinstance(item, Send)]


def test_selected_table_plain_total_does_not_read_unrelated_documents():
    workers = _routed(
        "发生日期 2026-01-01至2026-06-30；仅统计财务部报销金额合计是多少？",
        data_filename="selected.csv",
    )
    assert workers == ["data"]


def test_two_selected_policies_compare_without_a_data_table():
    workers = _routed(
        "比较《new.md》和《old.md》对凭证材料的要求，请分别引用原文。",
        document_filenames=("new.md", "old.md"),
    )
    assert workers == ["doc"]
