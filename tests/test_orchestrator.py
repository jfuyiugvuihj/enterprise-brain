"""Multi-Agent Orchestrator 集成测试"""
import pytest
import importlib.util
from pathlib import Path

_gate_spec = importlib.util.spec_from_file_location(
    "_live_model", Path(__file__).resolve().parent / "_live_model.py"
)
_live_model = importlib.util.module_from_spec(_gate_spec)
_gate_spec.loader.exec_module(_live_model)
live_model_required = _live_model.live_model_required



class TestGraphImport:
    def test_import_module(self):
        """Graph 能正常导入和编译"""
        from app.agents.orchestrator import multi_agent_graph
        assert multi_agent_graph is not None

    def test_graph_nodes(self):
        """所有节点已注册"""
        from app.agents.orchestrator import multi_agent_graph
        # graph 有 nodes 属性
        assert hasattr(multi_agent_graph, 'get_graph')
        info = multi_agent_graph.get_graph()
        nodes = list(info.nodes.keys())
        for n in ["classify_intent", "supervisor", "main_tools", "reflect", "synthesize",
                  "doc", "data", "chart", "export", "approval"]:
            assert n in nodes, f"缺少节点: {n}"


class TestState:
    def test_merge_dicts(self):
        """worker_results reducer 正确合并并行写入"""
        from app.agents.orchestrator import _merge_dicts
        a = {"doc": "result1"}
        b = {"data": "result2"}
        merged = _merge_dicts(a, b)
        assert merged == {"doc": "result1", "data": "result2"}

    def test_merge_overwrites(self):
        """同一 key 后者覆盖前者"""
        from app.agents.orchestrator import _merge_dicts
        a = {"doc": "old"}
        b = {"doc": "new"}
        merged = _merge_dicts(a, b)
        assert merged == {"doc": "new"}

    def test_merge_reset_marker_clears_previous_turn_results(self):
        """新一轮执行可以清空上一轮 worker 结果"""
        from app.agents.orchestrator import _merge_dicts

        assert _merge_dicts(
            {"doc": "上一轮答案"},
            {"__reset__": {}},
        ) == {}

    def test_route_main_falls_back_to_doc_for_approval_question_without_tool_call(self):
        """监督模型未调用工具时，审批制度问题仍必须进入文档 Agent"""
        from app.agents.orchestrator import route_main
        from langchain_core.messages import AIMessage, HumanMessage

        result = route_main(
            {
                "messages": [
                    HumanMessage(
                        content="单笔报销金额达到5000元和20000元时，分别需要谁审批？"
                    ),
                    AIMessage(content="我来根据公司的规定回答这个问题。"),
                ]
            }
        )

        assert isinstance(result, list)
        assert any(getattr(item, "node", None) == "doc" for item in result)

    def test_route_main_corrects_data_dispatch_for_policy_question(self):
        """文档制度问题即使被模型误派给 data，也必须纠正到 doc Agent。"""
        from app.agents.orchestrator import route_main
        from langchain_core.messages import AIMessage, HumanMessage

        tool_call = {
            "name": "dispatch",
            "args": {"workers": ["data"]},
            "id": "wrong-data-for-policy",
            "type": "tool_call",
        }
        result = route_main(
            {
                "messages": [
                    HumanMessage(content="超出住宿费标准的部分由谁承担？"),
                    AIMessage(content="", tool_calls=[tool_call]),
                ]
            }
        )

        assert isinstance(result, list)
        assert any(getattr(item, "node", None) == "doc" for item in result)
        assert not any(getattr(item, "node", None) == "data" for item in result)

    def test_route_main_stops_after_worker_result_exists(self):
        """本轮已有 worker 结果时，监督节点不能因关键词再次无限重派"""
        from app.agents.orchestrator import route_main
        from langchain_core.messages import AIMessage, HumanMessage

        result = route_main(
            {
                "messages": [
                    HumanMessage(
                        content="单笔报销金额达到5000元和20000元时，分别需要谁审批？"
                    ),
                    AIMessage(content="我已根据文档整理了审批流程。"),
                ],
                "worker_results": {
                    "doc": "5000元由财务总监审批，20000元由总经理审批。"
                },
            }
        )

        assert result == "reflect"

    def test_route_main_stops_when_model_repeats_completed_dispatch(self):
        """模型重复派发已完成的同一 Agent 时，必须停止循环"""
        from app.agents.orchestrator import dispatch, route_main
        from langchain_core.messages import AIMessage, HumanMessage

        tool_call = {
            "name": "dispatch",
            "args": {"workers": ["doc"]},
            "id": "repeat-doc",
            "type": "tool_call",
        }
        result = route_main(
            {
                "messages": [
                    HumanMessage(content="单笔报销金额达到5000元时，需要谁审批？"),
                    AIMessage(content="", tool_calls=[tool_call]),
                ],
                "worker_results": {"doc": "5000元由财务总监审批。"},
            }
        )

        assert result == "reflect"


class TestDispatchTool:
    def test_dispatch_returns_string(self):
        from app.agents.orchestrator import dispatch
        r = dispatch.invoke({"workers": ["doc"]})
        assert isinstance(r, str)
        assert "子Agent" in r

    def test_dispatch_valid_workers(self):
        from app.agents.orchestrator import dispatch
        r = dispatch.invoke({"workers": ["doc", "data", "chart", "export", "approval"]})
        assert "5" in r


class TestInterruptCheck:
    def test_no_interrupt_on_new_thread(self):
        """新会话不应有中断"""
        from app.agents.orchestrator import check_interrupt
        result = check_interrupt("no_such_thread_99999")
        assert result is None


@live_model_required
class TestEndToEnd:
    def test_load_memory_without_identity_does_not_use_shared_default_user(self, monkeypatch):
        from app.agents import nodes
        from langchain_core.messages import HumanMessage

        monkeypatch.setattr(
            nodes,
            "recall",
            lambda *_args, **_kwargs: pytest.fail("anonymous request must not recall shared memory"),
        )
        monkeypatch.setattr(
            nodes,
            "get_profile",
            lambda *_args, **_kwargs: pytest.fail("anonymous request must not load a profile"),
        )

        result = nodes.load_memory({"messages": [HumanMessage(content="private request")]})

        assert result["memory"] == {
            "long": [],
            "work": [],
            "profile": {},
            "profile_context": "",
        }
        assert result["memory_error"] == "authorization_required"

    def test_synthesize_without_identity_does_not_persist_shared_default_memory(self, monkeypatch):
        from app.agents import nodes
        from langchain_core.messages import HumanMessage

        calls = []
        monkeypatch.setattr(nodes, "remember", lambda *args: calls.append(args))

        result = nodes.synthesize(
            {
                "intent": "task",
                "messages": [HumanMessage(content="private request")],
                "worker_results": {"doc": "private response"},
            }
        )

        assert result["final_answer"] == "private response"
        assert calls == []

    def test_ask_final_answer_prefers_worker_result(self):
        from app.api.v1.chat import _select_final_answer

        answer = _select_final_answer(
            final_answer="如有疑问，请咨询财务部。",
            worker_results={
                "doc": "根据差旅费报销细则，一线城市住宿费标准为500元/晚。"
            },
            candidates=["我将查询公司内部政策和制度。"],
        )

        assert "500元/晚" in answer
        assert "如有疑问" not in answer

    def test_synthesize_prefers_worker_result_over_generic_ai_message(self):
        from app.agents.nodes import synthesize
        from langchain_core.messages import AIMessage, HumanMessage

        result = synthesize(
            {
                "intent": "task",
                "messages": [
                    HumanMessage(content="一线城市住宿费报销标准是多少？"),
                    AIMessage(content="如有疑问，请咨询财务部。"),
                ],
                "worker_results": {
                    "doc": "根据差旅费报销细则，一线城市住宿费标准为500元/晚。",
                },
            }
        )

        assert "500元/晚" in result["final_answer"]
        assert "如有疑问" not in result["final_answer"]

    def test_simple_question_gets_answer(self):
        """简单问题得到回答"""
        from app.agents.orchestrator import run_orchestrator
        result = run_orchestrator("你好，简单介绍一下自己", thread_id="test_e2e_simple_v2")
        assert isinstance(result, str)
        assert len(result) > 5

    def test_doc_question_gets_answer(self):
        """文档问题得到搜索回答"""
        from app.agents.orchestrator import run_orchestrator
        import uuid
        tid = f"test_doc_{uuid.uuid4().hex[:8]}"
        try:
            result = run_orchestrator("公司报销流程是什么", thread_id=tid)
        except ValueError as e:
            if "Chroma" in str(e) or "tenant" in str(e):
                pytest.skip(f"ChromaDB 连接不可用: {e}")
            raise
        assert isinstance(result, str)
        assert len(result) > 20
        has_content = any(kw in result for kw in ["报销", "公司", "流程", "根据"])
        assert has_content, f"回答不包含预期内容: {result[:100]}"

    def test_data_question_gets_answer(self):
        """数据分析问题得到回答"""
        from app.agents.orchestrator import run_orchestrator
        import uuid
        tid = f"test_data_{uuid.uuid4().hex[:8]}"
        result = run_orchestrator("哪个门店利润最高", thread_id=tid)
        assert isinstance(result, str)
        assert len(result) > 20
