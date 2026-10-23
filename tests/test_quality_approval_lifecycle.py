"""Local control-plane regressions; live PG/model/browser acceptance is separate."""
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END

from app.agents import orchestrator
from app.agents.state import AgentState
from app.api.v1 import chat


def approval_graph(tmp_path):
    # Real LangGraph scheduler + production router; only model/worker bodies are fixtures.
    builder = StateGraph(AgentState)
    builder.add_node("supervisor", lambda state: {"messages": [AIMessage(content="")]})
    builder.add_node("main_tools", lambda state: {})
    for name in ("data", "chart", "export"):
        def worker(state, name=name):
            if name != "data":
                (tmp_path / name).write_text("executed", encoding="utf-8")
            return {"worker_results": {name: f"{name} complete"}}
        builder.add_node(name, worker)
        builder.add_edge(name, "supervisor")
    builder.add_node("reflect", lambda state: {})
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", orchestrator.route_main)
    builder.add_edge("main_tools", "supervisor")
    builder.add_edge("reflect", END)
    graph = builder.compile(checkpointer=MemorySaver(), interrupt_before=["chart", "export"])
    sid = uuid4().hex
    graph.invoke({"messages": [HumanMessage(content="统计金额，生成柱状图并导出PDF报告")],
                  "plan": [{"worker": n} for n in ("data", "chart", "export")]},
                 {"configurable": {"thread_id": sid}})
    return graph, sid


def test_refusal_does_not_execute_next_unapproved_action(monkeypatch, tmp_path):
    graph, sid = approval_graph(tmp_path)
    monkeypatch.setattr(orchestrator, "multi_agent_graph", graph)
    assert orchestrator.check_interrupt(sid)["pending"] == ["chart"]
    list(orchestrator.run_interrupt_stream(sid, approved=False))
    assert not (tmp_path / "chart").exists()
    assert not (tmp_path / "export").exists(), "refusing chart must not execute unapproved export"
    assert orchestrator.check_interrupt(sid)["pending"] == ["export"]
    list(orchestrator.run_interrupt_stream(sid, approved=False))
    assert not (tmp_path / "export").exists()
    assert orchestrator.check_interrupt(sid) is None


def test_approval_executes_only_current_action(monkeypatch, tmp_path):
    graph, sid = approval_graph(tmp_path)
    monkeypatch.setattr(orchestrator, "multi_agent_graph", graph)
    list(orchestrator.run_interrupt_stream(sid, approved=True))
    assert (tmp_path / "chart").exists()
    assert not (tmp_path / "export").exists()
    assert orchestrator.check_interrupt(sid)["pending"] == ["export"]


def test_explicit_prohibition_removes_model_and_plan_side_effects():
    state = {"messages": [HumanMessage(content="统计金额，筛选后为空时不画图，不导出报告"),
                           AIMessage(content="", tool_calls=[{"name": "dispatch", "id": "fixture",
                                                               "args": {"workers": ["chart", "export"]}}])],
             "plan": [{"worker": n} for n in ("data", "chart", "export")]}
    sends = orchestrator.route_main(state)
    assert [send.node for send in sends if hasattr(send, "node")] == ["data"]
    state["worker_results"] = {"data": "0行，0元"}
    state["agent_results"] = {"data": {"evidence": [{"source_type": "dataset", "metadata": {"row_count": 0}}]}}
    assert orchestrator.route_main(state) == "reflect"
    state["agent_results"]["data"]["evidence"][0]["metadata"]["row_count"] = 2
    assert [send.node for send in orchestrator.route_main(state) if hasattr(send, "node")] == ["chart"]


def test_no_chart_request_still_exports_requested_pdf():
    state = {"messages": [HumanMessage(content="核查费用并导出PDF报告，不生成图表。"),
        AIMessage(content="", tool_calls=[{"name": "dispatch", "id": "test-no-chart",
            "args": {"workers": ["chart", "export"]}}])],
        "plan": [{"worker": name} for name in ("data", "chart", "export")],
        "worker_results": {"data": "已核验合计80"}}
    assert [send.node for send in orchestrator.route_main(state) if hasattr(send, 'node')] == ['export']


def test_resuming_keeps_one_primary_answer_in_history():
    sid = uuid4().hex
    chat._ensure_session(sid, user_id="synthetic-finance")
    chat._save_message(sid, "user", "统计并生成报告")
    chat._save_message(sid, "assistant", "合计200元")
    chat._save_approval_answer(sid, "合计200元\n\n已取消，未执行：生成图表")
    chat._save_approval_answer(sid, "合计200元\n\n已取消，未执行：生成图表\n\n已取消，未执行：导出报告")
    rows = chat._get_session_messages(sid)
    assert [row["role"] for row in rows] == ["user", "assistant"]
    assert rows[-1]["content"].count("合计200元") == 1
    assert "导出报告" in rows[-1]["content"]


def test_approval_history_keeps_actual_step_verdict():
    sid = uuid4().hex
    chat._ensure_session(sid, user_id='synthetic-finance')
    chat._save_message(sid, 'assistant', '等待确认', [{'tool': 'export', 'status': 'unknown'}])
    chat._save_approval_answer(sid, '执行失败，未生成报告', [{'tool': 'export', 'status': 'failed'}])
    assert chat._get_session_messages(sid)[-1]['steps'] == [{'tool': 'export', 'status': 'failed'}]


def test_display_interruption_does_not_swallow_following_explicit_refusal():
    sid = uuid4().hex
    assert chat.cancel_request(sid) is False
    generation = chat.register_request(sid, inherit_pending=False)
    try:
        assert not generation.is_set()
        assert not chat.is_request_cancelled(sid, epoch=generation.epoch)
    finally:
        chat.release_request(generation)


def test_worker_results_deduplicate_repeated_body():
    assert chat._select_final_answer(worker_results={"data": "合计200元", "chart": "合计200元",
                                                     "export": "合计200元\n\n报告已生成"}) == "合计200元\n\n报告已生成"


def test_numbered_calculations_keep_repeated_scope_within_one_worker():
    answer = "① 一月\n\n当前授权范围内纳入 **1 条记录**。\n\n② 三月\n\n当前授权范围内纳入 **1 条记录**。"
    assert chat._select_final_answer(worker_results={"data": answer}) == answer
