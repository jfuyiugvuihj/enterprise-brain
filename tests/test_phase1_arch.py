"""阶段 1（LangGraph + 记忆）架构测试"""
import uuid
import pytest
from langchain_core.messages import HumanMessage, AIMessage


class TestState:
    def test_state_fields(self):
        from app.agents.state import AgentState
        # TypedDict 的字段应包含关键键
        keys = AgentState.__annotations__
        for f in ["messages", "intent", "user_id", "memory", "plan",
                  "worker_results", "reflect_count", "redo", "final_answer"]:
            assert f in keys, f"AgentState 缺少字段: {f}"

    def test_merge_dicts(self):
        from app.agents.state import _merge_dicts
        assert _merge_dicts({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
        assert _merge_dicts({"a": 1}, {"a": 2}) == {"a": 2}


class TestClassifyIntent:
    def test_smalltalk_is_chat(self):
        from app.agents.nodes import classify_intent
        st = {"messages": [HumanMessage(content="你好")]}
        assert classify_intent(st)["intent"] == "chat"

    def test_task_question(self):
        from app.agents.nodes import classify_intent
        st = {"messages": [HumanMessage(content="哪个门店利润最高")]}
        assert classify_intent(st)["intent"] == "task"


class TestReflect:
    def test_empty_answer_redo(self):
        from app.agents.nodes import reflect_node
        st = {"messages": [HumanMessage(content="画个图")], "reflect_count": 0}
        out = reflect_node(st)
        assert out["redo"] is True

    def test_chart_without_image_redo(self):
        from app.agents.nodes import reflect_node
        st = {"messages": [HumanMessage(content="画柱状图"),
                           AIMessage(content="好的，这是分析结果但没有图")],
              "reflect_count": 0}
        assert reflect_node(st)["redo"] is True

    def test_good_answer_pass(self):
        from app.agents.nodes import reflect_node
        st = {"messages": [HumanMessage(content="哪个门店利润最高"),
                           AIMessage(content="建国路利润最高，为30。")],
              "reflect_count": 0}
        out = reflect_node(st)
        assert out["redo"] is False

    def test_route_reflect(self):
        from app.agents.nodes import route_reflect
        assert route_reflect({"redo": True, "reflect_count": 1}) == "supervisor"
        assert route_reflect({"redo": False, "reflect_count": 1}) == "synthesize"
        # 超重派上限不再回
        assert route_reflect({"redo": True, "reflect_count": 2}) == "synthesize"


class TestSummarizer:
    def test_short_not_compressed(self):
        from app.memory.summarizer import compress_messages
        msgs = [HumanMessage(content=f"q{i}") for i in range(5)]
        out = compress_messages(msgs, model=None)  # 不超阈值不应调 model
        assert out == msgs


class TestLongTermMemory:
    def test_remember_recall_roundtrip(self):
        from app.memory import long_term
        try:
            long_term._ensure()
        except Exception:
            pytest.skip("Postgres 未运行，跳过长期记忆测试")
        uid = f"t_{uuid.uuid4().hex[:6]}"
        try:
            assert long_term.remember(uid, "我喜欢用柱状图看营收") is True
            hits = long_term.recall(uid, "柱状图", k=3)
            assert isinstance(hits, list)
            assert any("柱状图" in h for h in hits), f"应召回刚记的, 实际 {hits}"
        finally:
            try:
                conn = long_term._conn()
                conn.execute("DELETE FROM memories WHERE user_id = %s", (uid,))
                conn.commit()
                conn.close()
            except Exception:
                pass


class TestGraphStructure:
    def test_new_nodes_registered(self):
        from app.agents.orchestrator import multi_agent_graph
        nodes = list(multi_agent_graph.get_graph().nodes.keys())
        for n in ["classify_intent", "respond", "load_memory", "plan",
                  "supervisor", "reflect", "synthesize",
                  "doc", "data", "chart", "export"]:
            assert n in nodes, f"缺少节点: {n}"

    def test_queue_graph_no_interrupt_nodes_same(self):
        from app.agents.orchestrator import queue_graph
        nodes = list(queue_graph.get_graph().nodes.keys())
        assert "supervisor" in nodes and "reflect" in nodes

    def test_dispatch_still_works(self):
        from app.agents.orchestrator import dispatch
        r = dispatch.invoke({"workers": ["doc", "data"]})
        assert "2" in r or "子Agent" in r
