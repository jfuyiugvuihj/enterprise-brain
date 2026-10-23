from app.agents.tools import _verified_data_sections


def test_table_brief_never_invents_currency_or_completed_artifacts():
    import pandas as pd
    from app.agents import tools
    frame = pd.DataFrame({"部门": ["财务", "财务"], "金额": [120, 80]})
    facts = tools._report_data_facts("费用.csv", frame, "按部门汇总金额")
    text = tools._verified_data_answer([facts])
    assert "200.00" in text and "2 条" in text and "100.00" in text
    assert "单位未标注" in text and "元" not in text
    assert "已生成" not in text and "已导出" not in text


def test_monthly_report_uses_month_range_and_verified_chart():
    import pandas as pd
    from pypdf import PdfReader
    from app.agents.tools import _report_data_facts, _report_sections, _report_chart_from_facts
    from app.tools.export import generate_pdf_report

    frame = pd.DataFrame({"月份": ["2026-01", "2026-01", "2026-02", "2026-02"],
                          "部门": ["财务", "销售", "财务", "销售"],
                          "报销金额": [120, 80, 150, 100]})
    facts = _report_data_facts("报销明细.csv", frame, "请生成上半年经营分析报告")
    assert facts["period"] == "2026-01 至 2026-02（月份）"
    assert facts["metrics"][0]["groups"] == [("2026-01", 200.0), ("2026-02", 250.0)]
    sections = _report_sections([facts], "数据分析结果:\n月份(str)\n--- 数据样本(前15行) ---", "")
    assert "数据样本" not in str(sections) and "没有可汇总的分组字段" not in str(sections)
    assert "2026-02指标值最高" in str(sections)
    assert "2026-01指标值最高" not in str(sections)
    chart = _report_chart_from_facts([facts])
    assert chart
    slot = next(i for i, section in enumerate(sections) if section["type"] == "chart_slot")
    sections[slot] = {"type": "chart", "path": chart, "caption": "按月份汇总报销金额；单位未标注"}
    reader = PdfReader(generate_pdf_report("经营分析报告", sections))
    assert any(page.images for page in reader.pages)


def test_verified_report_has_analysis_body_instead_of_only_statistics():
    from app.agents import tools
    analysis = "合计: 金额=1310\n按部门分组汇总:\n销售: 金额=480"
    if not hasattr(tools, "_verified_report_sections"):
        sections = _verified_data_sections("费用.csv", analysis)
    else:
        import pandas as pd
        facts = tools._report_data_facts("费用.csv", pd.DataFrame({"部门": ["销售"], "金额": [480]}), "按部门汇总金额")
        sections = tools._verified_report_sections([facts], analysis)
    text = "\n".join(item.get("content", "") for item in sections)
    assert "分析结论" in text and "建议与限制" in text


def test_report_includes_business_findings_from_real_filtered_rows():
    import pandas as pd
    from app.agents.tools import _report_data_facts, _verified_report_sections

    frame = pd.DataFrame({"部门": ["财务", "财务", "销售", "销售", "研发", "人事", "人事"],
        "金额": [120, 80, 300, 180, 420, 150, 60],
        "发生日期": pd.date_range("2026-10-01", periods=7)})
    facts = _report_data_facts("费用.csv", frame, "按部门汇总金额", version_id="expenses:v1")
    sections = _verified_report_sections([facts], "实际筛选：已批准或已支付；合计: 金额=1310")
    text = "\n".join(item.get("content", "") for item in sections)
    assert "分析结论" in text and "建议与限制" in text
    assert "1,310" in text and "187.14" in text
    assert "销售" in text and "36.64%" in text
    assert "expenses:v1" in text and "2026-10-01" in text and "2026-10-07" in text
    assert "单位未标注" in text and "890" not in text


def test_report_finance_scope_and_explicit_unit_are_not_invented():
    import pandas as pd
    from app.agents.tools import _report_data_facts, _verified_report_sections

    frame = pd.DataFrame({"部门": ["财务", "财务"], "金额（元）": [120, 80]})
    frame.attrs.update(sheet_name="本月费用", filter_note="状态仅包含已支付")
    facts = _report_data_facts("费用.xlsx", frame, "按部门汇总金额", version_id="expenses:v2")
    text = "\n".join(item.get("content", "") for item in _verified_report_sections([facts], "合计200"))
    assert "200" in text and "100" in text and "元" in text and "本月费用" in text
    assert "销售" not in text and "1,310" not in text


def test_report_empty_and_negative_rows_do_not_claim_positive_shares():
    import pandas as pd
    from app.agents.tools import _report_data_facts, _verified_report_sections

    for values in ([], [-10, 0]):
        frame = pd.DataFrame({"部门": ["财务"] * len(values), "金额": pd.Series(values, dtype=float)})
        facts = _report_data_facts("费用.csv", frame, "按部门汇总金额")
        text = "\n".join(item.get("content", "") for item in _verified_report_sections([facts], ""))
        assert "nan" not in text.lower() and "100.00%" not in text
        if not values:
            assert "0 行" in text and "0.00" in text


def test_equivalent_filter_wording_keeps_report_input_total():
    import pandas as pd
    from app.tools.excel import filter_explicit_categories
    frame = pd.DataFrame({"状态": ["已支付", "已批准", "待审批", "已驳回"], "金额": [200, 1110, 310, 90]})
    question = "请按部门合计已经批准或已经支付的金额，并列出总计；待审批、已驳回不计入。"
    result = filter_explicit_categories(frame, question)
    assert result["金额"].sum() == 1310
    assert set(result["状态"]) == {"已支付", "已批准"}


def test_report_contains_verified_source_and_amounts_instead_of_model_prose():
    analysis = "实际筛选：状态仅包含已批准、已支付；筛选后 4 行。\n按部门分组汇总:\n财务: 金额=200\n销售: 金额=480\n研发: 金额=420\n人事: 金额=210\n合计: 金额=1310"
    sections = _verified_data_sections("费用明细.csv", analysis)
    text = "\n".join(section.get("content", "") for section in sections)
    assert "费用明细.csv" in text and "1310" in text
    assert all(value in text for value in ("200", "480", "420", "210", "已批准", "已支付"))


def test_report_preserves_finance_scope():
    sections = _verified_data_sections("费用明细.csv", "财务: 金额=200\n合计: 金额=200")
    text = "\n".join(section.get("content", "") for section in sections)
    assert "200" in text and "1310" not in text and "销售" not in text


def test_report_keeps_business_totals_without_tool_internals():
    analysis = '数据分析结果:\n📁 费用.csv: 实际筛选：状态仅包含已支付\n📁 费用.csv: 2行 × 2列 — 列: 金额(int64),部门(str)\n合计: 金额=200\n--- 数据样本(前15行) ---\n[{"金额":120}]'
    text = "\n".join(section.get("content", "") for section in _verified_data_sections("费用.csv", analysis))
    assert "200" in text and "实际筛选" in text
    assert "int64" not in text and "数据样本" not in text and '[{"' not in text
