"""Real PDF rendering regressions; only the output directory is isolated."""
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from app.tools import export


@pytest.fixture
def report_output(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "EXPORT_DIR", str(tmp_path))
    return tmp_path


def chart_file(directory, size=(800, 450)):
    path = directory / "bar_a76f345231.png"
    Image.new("RGB", size, "#8dbce6").save(path)
    return str(path)


def image_draws(reader):
    return sum(page.get_contents().get_data().count(b" Do") for page in reader.pages)


def test_short_report_has_no_disclaimer_only_ending_page(report_output):
    path = export.generate_pdf_report("部门费用报告", [
        {"type": "heading", "content": "核验结果"},
        {"type": "text", "content": "试用-财务：2条已支付记录，合计200.00元。"},
    ])
    pages = [page.extract_text() for page in PdfReader(path).pages]
    assert "报告结束" not in "".join(pages)
    assert "200.00元" in pages[-1]
    assert len(pages) <= 2


def test_management_template_starts_with_metrics_and_renders_numeric_table(report_output):
    path = export.generate_pdf_report("费用管理简报", [
        {"type": "summary", "period": "2026-10-01 至 2026-10-09", "cards": [
            {"label": "纳入费用合计", "value": "1,310.00", "hint": "单位未标注"},
            {"label": "纳入记录", "value": "7", "hint": "已批准或已支付"}]},
        {"type": "heading", "content": "01 管理摘要"},
        {"type": "callout", "content": "销售与研发合计900.00，占68.70%。"},
        {"type": "table", "headers": ["部门", "金额", "占比"], "rows": [
            ["试用-销售", "480.00", "36.64%"], ["试用-研发", "420.00", "32.06%"]]},
    ])
    pages = [page.extract_text() for page in PdfReader(path).pages]
    assert len(pages) == 1
    assert all(value in pages[0] for value in ("1,310.00", "01 管理摘要", "部门", "36.64%", "68.70%"))


def test_chart_section_and_legacy_path_embed_once_with_business_caption(report_output):
    chart = chart_file(report_output)
    caption = "按部门汇总已批准或已支付费用（元），财务200.00元。"
    path = export.generate_pdf_report("费用报告", [
        {"type": "chart", "path": chart, "caption": caption},
    ], [chart, str(Path(chart).parent / "." / Path(chart).name)])
    reader = PdfReader(path)
    assert image_draws(reader) == 1
    text = "".join(page.extract_text() for page in reader.pages)
    assert caption in text
    assert Path(chart).name not in text


def test_expense_brief_keeps_chart_with_summary_and_details_in_two_pages(report_output):
    import pandas as pd
    from app.agents.tools import _report_data_facts, _verified_report_sections
    frame = pd.DataFrame({"申请编号": [f"SYN-{i:03}" for i in range(1, 8)],
        "发生日期": pd.date_range("2026-10-01", periods=7).strftime("%Y-%m-%d"),
        "部门": ["财务", "财务", "销售", "销售", "研发", "人事", "人事"],
        "费用类别": ["办公"] * 7, "金额": [120, 80, 300, 180, 420, 150, 60],
        "状态": ["已支付"] * 7, "资料类型": ["合成"] * 7})
    facts = _report_data_facts("合成验收-费用明细.csv", frame, "按部门汇总金额",
        version_id="9fb5fa21aa334363b9e20b87901b5fa8:v1", sha256="8" * 64)
    sections = _verified_report_sections([facts], "")
    slot = next(i for i, s in enumerate(sections) if s.get("type") == "chart_slot")
    sections[slot] = {"type": "chart", "path": chart_file(report_output, (1200, 825)),
        "caption": "图1：部门费用构成；单位未标注；来源详见编制口径。"}
    reader = PdfReader(export.generate_pdf_report("费用分析简报", sections))
    assert len(reader.pages) == 2
    assert b" Do" in reader.pages[0].get_contents().get_data()
    assert "管理摘要" in reader.pages[0].extract_text()
    assert "SYN-007" in reader.pages[1].extract_text()


def test_expense_brief_without_chart_uses_first_page_for_details(report_output):
    import pandas as pd
    from app.agents.tools import _report_data_facts, _verified_report_sections
    frame = pd.DataFrame({"申请编号": ["SYN-001"], "发生日期": ["2026-10-01"],
        "部门": ["财务"], "费用类别": ["办公"], "金额": [80],
        "状态": ["已支付"], "资料类型": ["合成"]})
    facts = _report_data_facts("合成验收-费用明细.csv", frame, "按部门汇总金额",
        version_id="v1", sha256="8" * 64)
    reader = PdfReader(export.generate_pdf_report("费用分析简报", _verified_report_sections([facts], "")))
    assert "03 费用汇总明细" in reader.pages[0].extract_text()
    assert "本图" not in ''.join(page.extract_text() for page in reader.pages)


def test_legacy_chart_caption_never_exposes_random_filename(report_output):
    chart = chart_file(report_output)
    path = export.generate_pdf_report("部门费用分析", [], [chart])
    text = "".join(page.extract_text() for page in PdfReader(path).pages)
    assert "部门费用分析" in text
    assert "图1" in text
    assert Path(chart).name not in text


def test_long_title_heading_and_paragraph_remain_inside_page(report_output):
    title = "各业务部门已批准与已支付费用核验" * 5
    heading = "范围与数据来源说明" * 10
    body = "本报告仅分析授权数据；待审批与已驳回不计入。" * 120 + "正文终点。"
    path = export.generate_pdf_report(title, [
        {"type": "heading", "content": heading},
        {"type": "text", "content": body},
        {"type": "text", "content": "后一段应从左边距正常排版。"},
    ])
    reader = PdfReader(path)
    text = "".join(page.extract_text() for page in reader.pages)
    assert "正文终点。" in text and "后一段应从左边距正常排版。" in text
    for page in reader.pages:
        width = float(page.mediabox.width)
        def check_text(fragment, cm, tm, font, size):
            if fragment.strip():
                assert 20 <= tm[4] <= width - 20, (fragment, tm[4])
        page.extract_text(visitor_text=check_text)


def test_heading_moves_with_first_body_line(report_output):
    pdf = export.PDFReport("分页检查")
    pdf.add_page()
    pdf.set_y(pdf.page_break_trigger - 15)
    pdf.heading("需要保留在正文旁的标题", 2)
    pdf.paragraph("这里是标题对应的实际说明。")
    path = str(report_output / "heading.pdf")
    pdf.output(path)
    pages = [page.extract_text() for page in PdfReader(path).pages]
    assert any("需要保留在正文旁的标题" in p and "实际说明" in p for p in pages)


def test_tall_chart_keeps_caption_on_same_page(report_output):
    chart = chart_file(report_output, size=(400, 1200))
    caption = "长图说明：这是实际图表的授权数据范围。" * 4
    path = export.generate_pdf_report("图表报告", [
        {"type": "chart", "path": chart, "caption": caption},
    ])
    reader = PdfReader(path)
    chart_pages = [p for p in reader.pages if b" Do" in p.get_contents().get_data()]
    assert len(chart_pages) == 1
    assert caption in chart_pages[0].extract_text().replace("\n", "")


def test_review_brief_does_not_strand_limitations_on_nearly_empty_third_page(report_output):
    import pandas as pd
    from app.agents.task_review import policy_review_text
    from app.agents.tools import _report_data_facts, _verified_report_sections, _policy_review_sections
    frame = pd.DataFrame({"申请编号": ["SYN-002", "SYN-003", "SYN-004"],
        "发生日期": ["2026-10-02", "2026-10-03", "2026-10-04"],
        "部门": ["试用-财务", "试用-销售", "试用-销售"], "费用类别": ["办公", "差旅", "差旅"],
        "金额": [80, 300, 180], "状态": ["已支付", "已批准", "已批准"], "资料类型": ["合成"] * 3})
    frame.attrs.update(requested_period="2026-10-02 至 2026-10-05（发生日期）",
        filter_note="实际筛选：2026-10-02    至 2026-10-05（发生日期）；状态仅包含已批准、已支付；筛选前10行，筛选后3行。")
    policy = {"source_name": "合成验收-费用制度-现行20261001.pdf", "version_id": "1", "excerpt":
        "版本：V2；生效日：2026-10-01。\n"
        "一、材料：费用明细、原始凭证、业务用途说明和相关批准记录。\n"
        "二、提交期限：费用发生后10个工作日内提交。\n"
        "三、金额不超过500元（含500元）：部门经理审批。\n"
        "四、金额超过500元且不超过2000元（含2000元）：财务负责人审批。\n"
        "五、金额超过2000元：总经理审批。\n"
        "六、批准只表示审批完成，不表示已经付款。\n"
        "七、现行版住宿上限按合成城市住宿标准表；必须提供城市和天数。\n"
        "八、本制度未规定出租车补贴金额和外币换算规则，不得编造。\n"
        "九、2026-09-01版为历史版；不可把旧版期限与本版审批门槛拼接。"}
    facts = _report_data_facts("合成验收-费用明细.csv", frame, "按部门汇总金额",
        version_id="9fb5fa21aa334363b9e20b87901b5fa8:v1", sha256="8" * 64)
    sections = _verified_report_sections([facts], "") + _policy_review_sections(
        policy_review_text([policy], period="2026-10-02 至 2026-10-05"), facts["filename"])
    pages = [p.extract_text() for p in PdfReader(export.generate_pdf_report("费用核查简报", sections)).pages]
    assert len(pages) == 2
    assert all(s in ''.join(pages) for s in ("560.00", "SYN-004", "金额单位未注明", "风险建议", "真人业务验收"))
    assert "2026-10-02    至" not in ''.join(pages)


def test_empty_brief_explains_absent_groups_and_does_not_invent_review_target(report_output):
    import pandas as pd
    from app.agents.tools import _report_data_facts, _verified_report_sections
    facts = _report_data_facts('费用.csv', pd.DataFrame({'部门': pd.Series(dtype=str),
        '金额': pd.Series(dtype=float)}), '按部门汇总金额')
    reader = PdfReader(export.generate_pdf_report('费用核查简报', _verified_report_sections([facts], '')))
    text = ''.join(p.extract_text() for p in reader.pages)
    assert '没有可列示的分组明细' in text and '确认0条' in text
    assert '核对金额较高分组' not in text and '以授权范围内的分组表格为依据' not in text
