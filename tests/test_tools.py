"""Tools 测试"""
import pytest
from app.agents.tools import search_docs, analyze_data, generate_chart, export_report
from app.agents.orchestrator import dispatch


class TestSearchDocs:
    def test_formats_string_scores_without_crashing(self, monkeypatch):
        class FakePipeline:
            def search_for_principal(self, query, principal, top_k):
                return ([{"source": "policy.txt", "_score": "0.75", "content": "住宿费标准为500元"}], [])

        monkeypatch.setattr("app.agents.tools._get_pipeline", lambda: FakePipeline())
        result = search_docs.invoke("住宿费标准", config={"configurable": {"username": "test-user", "role": "staff", "department": ""}})
        assert "0.75" in result
        assert "住宿费标准为500元" in result

    def test_returns_string(self):
        result = search_docs.invoke("公司报销流程")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_returns_results_or_not_found(self):
        result = search_docs.invoke("公司报销流程")
        # 要么找到结果，要么返回未找到提示
        assert "来源:" in result or "未找到" in result

    def test_empty_query(self):
        result = search_docs.invoke("")
        assert isinstance(result, str)


class TestAnalyzeData:
    def test_returns_string(self):
        result = analyze_data.invoke("哪个门店利润最高")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_data_or_no_files(self):
        result = analyze_data.invoke("排名")
        # 要么有数据，要么提示无文件
        assert any(kw in result for kw in ["数据分析", "暂无数据", "利润", "门店"])


class TestDispatch:
    def test_dispatch_tool(self):
        result = dispatch.invoke({"workers": ["doc", "data"]})
        assert "2" in result or "子Agent" in result

    def test_single_worker(self):
        result = dispatch.invoke({"workers": ["doc"]})
        assert isinstance(result, str)

    def test_all_workers(self):
        result = dispatch.invoke({"workers": ["doc", "data", "chart", "export"]})
        assert isinstance(result, str)


class TestChartExport:
    def test_generate_chart(self):
        result = generate_chart.invoke({
            "chart_type": "bar",
            "labels": ["A", "B", "C"],
            "values": [10, 20, 30],
            "title": "测试图表",
        })
        assert isinstance(result, str)
        assert "authorization_required" in result

    def test_export_report(self):
        result = export_report.invoke({
            "report_title": "测试报告",
            "sections_json": '[{"type":"heading","content":"测试标题"},{"type":"text","content":"测试内容"}]',
        })
        assert isinstance(result, str)
        assert "authorization_required" in result
