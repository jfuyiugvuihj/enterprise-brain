"""Multi-Agent Orchestrator 集成测试"""
import pytest


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
                  "doc", "data", "chart", "export"]:
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


class TestDispatchTool:
    def test_dispatch_returns_string(self):
        from app.agents.orchestrator import dispatch
        r = dispatch.invoke({"workers": ["doc"]})
        assert isinstance(r, str)
        assert "子Agent" in r

    def test_dispatch_valid_workers(self):
        from app.agents.orchestrator import dispatch
        r = dispatch.invoke({"workers": ["doc", "data", "chart", "export"]})
        assert "4" in r


class TestInterruptCheck:
    def test_no_interrupt_on_new_thread(self):
        """新会话不应有中断"""
        from app.agents.orchestrator import check_interrupt
        result = check_interrupt("no_such_thread_99999")
        assert result is None


class TestEndToEnd:
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
