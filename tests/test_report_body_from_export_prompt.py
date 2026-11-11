"""The report button must keep the answer the user actually saw."""
from types import SimpleNamespace

from pypdf import PdfReader

from app.agents import orchestrator
from app.agents.tools import _analysis_body_sections, _report_sections
from app.tools.export import generate_pdf_report
from app.trace.store import TraceStore


ANALYSIS = """按部门汇总，财务部合计 200 元。

| 部门 | 金额 |
| --- | --- |
| 财务部 | 200 |

单位未在原表中标注，不能直接视为人民币。"""


def _prompt() -> str:
    return "\n\n".join([
        "请将以下已完成的分析原文排版导出为 PDF 报告。仅使用提供的分析内容。",
        "分析问题：按部门汇总金额",
        "实际使用的数据文件：finance.csv",
        "分析原文开始：",
        ANALYSIS,
        "分析原文结束。",
    ])


class _Graph:
    def __init__(self):
        self.state = None
        self.config = None

    def get_state(self, config):
        return SimpleNamespace(values={})

    def stream(self, state, config, **_kwargs):
        self.state = state
        self.config = config
        yield {"messages": [], "worker_results": {}, "final_answer": "done"}


def test_export_prompt_carries_the_settled_answer():
    assert orchestrator.report_body_from_export_prompt(_prompt()) == ANALYSIS


def test_data_only_previous_turn_still_passes_the_answer_into_the_report(tmp_path):
    graph = _Graph()
    original = orchestrator.multi_agent_graph
    orchestrator.multi_agent_graph = graph
    try:
        list(orchestrator.run_with_stream(
            _prompt(),
            thread_id="report-body",
            user={
                "username": "alice",
                "department": "finance",
                "task_question": _prompt(),
                "data_filename": "finance.csv",
                "data_context": {"analysis_question": "按部门汇总金额", "query": "按部门汇总金额"},
            },
            trace_store=TraceStore(tmp_path / "traces.jsonl"),
        ))
    finally:
        orchestrator.multi_agent_graph = original

    assert graph.config["configurable"]["report_body"] == ANALYSIS
    assert graph.state["data_context"]["report_body"] == ANALYSIS
    # A data-only turn has no real task_context; report_body must not create one,
    # otherwise the dataset gate sees a bound task with no version.
    assert graph.state["task_context"] == {}


def test_the_rendered_pdf_contains_the_answer_paragraph():
    path = generate_pdf_report("费用分析报告", _analysis_body_sections(ANALYSIS))
    text = "".join(page.extract_text() for page in PdfReader(path).pages)

    assert "财务部合计 200 元" in text
    assert "单位未在原表中标注" in text


def test_a_report_without_original_body_keeps_the_recomputed_analysis():
    sections = _report_sections([], ANALYSIS, "")

    assert sections[0] == {"type": "heading", "content": "分析结论原文"}
    assert any("财务部合计 200 元" in str(section.get("content", "")) for section in sections)
    text = "".join(
        page.extract_text()
        for page in PdfReader(generate_pdf_report("费用分析报告", sections)).pages
    )
    assert "财务部合计 200 元" in text
