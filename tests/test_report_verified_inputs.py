from app.agents.tools import _verified_data_sections


def test_query_chart_uses_the_actual_group_medians_and_preserves_their_order():
    import pandas as pd
    from app.tools.excel import safe_query
    frame = pd.DataFrame({'部门': ['销售', '销售', '财务', '财务'], '金额（元）': [100, 900, -20, 40]})
    result = safe_query(frame, "df.groupby('部门')['金额（元）'].median().sort_values(ascending=False)")
    assert result['error'] is None
    assert result['chart_series']['labels'] == ['销售', '财务']
    assert result['chart_series']['values'] == [500, 10]


def test_query_chart_rejects_lost_labels_missing_values_and_truncated_tables():
    import pandas as pd
    from app.tools.excel import safe_query
    cases = [pd.DataFrame({'标签': ['A', 'A'], '值': [1, 2]}),
             pd.DataFrame({'标签': ['A', 'B'], '值': [1, float('nan')]}),
             pd.DataFrame({'标签': list(map(str, range(51))), '值': list(range(51))})]
    for frame in cases:
        assert safe_query(frame, 'df')['chart_series'] is None
    frame = pd.DataFrame({'值': [1, 2]}, index=['A', 'A'])
    assert safe_query(frame, "df['值']")['chart_series'] is None


def test_query_chart_accepts_two_column_results_without_filling_or_sorting():
    import pandas as pd
    from app.tools.excel import safe_query
    frame = pd.DataFrame({'状态': ['已支付', '已批准'], '中位数': [-7, 13]})
    series = safe_query(frame, 'df')['chart_series']
    assert series['labels'] == ['已支付', '已批准']
    assert series['values'] == [-7, 13]


def test_query_report_chart_cannot_use_another_questions_verified_result(monkeypatch):
    from app.agents.tools import _report_charts_from_queries
    drawn = []
    monkeypatch.setattr('app.tools.chart.bar_chart', lambda labels, values, **kw: drawn.append((values, kw['title'])) or 'chart.png')
    question = '2026-01按状态金额中位数'
    def row(query, values):
        return {'parameters': {'query': query}, 'result': {'query_chart':
            {'labels': ['A', 'B'], 'values': values, 'dimension': '状态'}}}
    records = [row(question, [10, 20]), row('2026-02按状态金额中位数', [900, 800])]
    assert _report_charts_from_queries(records, question) == ['chart.png']
    assert drawn[0][0] == [10, 20] and len(drawn) == 1
    assert '2026-01' in drawn[0][1]


def test_query_report_keeps_the_calculated_result_instead_of_the_input_sum():
    from app.agents.tools import _query_result_body
    body = _query_result_body({'dataset_version_id': 'finance:v2',
        'parameters': {'query': '金额中位数乘2'}, 'result': {'query_result': 700, 'rows': 6,
        'analysis_scope': {'period': '2026-01 至 2026-06', 'filter': '未指定分类筛选'}}})
    assert '700' in body and 'finance:v2' in body and '6' in body
    assert '输入' in body and '合计' not in body and '700元' not in body


def test_table_brief_never_invents_currency_or_completed_artifacts():
    import pandas as pd
    from app.agents import tools
    frame = pd.DataFrame({"部门": ["财务", "财务"], "金额": [120, 80]})
    facts = tools._report_data_facts("费用.csv", frame, "按部门汇总金额")
    text = tools._verified_data_answer([facts])
    assert "200.00" in text and "2 条" in text and "100.00" in text
    assert "单位未标注" in text and "元" not in text
    assert "已生成" not in text and "已导出" not in text


def test_average_question_leads_with_the_mean_instead_of_the_total():
    import pandas as pd
    from app.agents.tools import _report_data_facts, _verified_data_answer
    question = '2026-03金额（元）平均值是多少？'
    frame = pd.DataFrame({'月份': ['2026-03', '2026-03'], '金额（元）': [300, 900]})
    answer = _verified_data_answer([_report_data_facts('合成.csv', frame, question)],
        question=question, include_groups=False)
    assert answer.index('600.00') < answer.index('1,200.00')


def test_monthly_report_uses_month_range_and_verified_chart():
    import pandas as pd
    from pypdf import PdfReader
    from app.agents.tools import _report_data_facts, _report_sections, _report_chart_from_facts
    from app.tools.export import generate_pdf_report

    frame = pd.DataFrame({"月份": ["2026-01", "2026-01", "2026-02", "2026-02"],
                          "提交日期": ["2026-02-14", "2026-02-14", "2026-03-13", "2026-03-13"],
                          "部门": ["财务", "销售", "财务", "销售"],
                          "报销金额": [120, 80, 150, 100]})
    facts = _report_data_facts("报销明细.csv", frame, "请生成上半年经营分析报告")
    assert facts["period"] == "2026-01 至 2026-02（月份）"
    assert facts["metrics"][0]["groups"] == [("2026-01", 200.0), ("2026-02", 250.0)]
    sections = _report_sections([facts], "数据分析结果:\n月份(str)\n--- 数据样本(前15行) ---", "")
    assert "仅反映《报销明细.csv》" in str(sections)
    assert "数据样本" not in str(sections) and "没有可汇总的分组字段" not in str(sections)
    assert "2026-02指标值最高" in str(sections)
    assert "2026-01指标值最高" not in str(sections)
    chart = _report_chart_from_facts([facts])
    assert chart
    slot = next(i for i, section in enumerate(sections) if section["type"] == "chart_slot")
    sections[slot] = {"type": "chart", "path": chart, "caption": "按月份汇总报销金额；单位未标注"}
    reader = PdfReader(generate_pdf_report("经营分析报告", sections))
    assert any(page.images for page in reader.pages)


def test_report_appendix_does_not_leave_its_count_note_alone_on_a_page():
    import pandas as pd
    from pypdf import PdfReader
    from app.agents.tools import _report_data_facts, _report_sections, _report_chart_from_facts
    from app.tools.export import generate_pdf_report

    frame = pd.DataFrame({'月份': [f'2026-{i:02d}' for i in range(1, 7)],
                          '部门': ['财务部'] * 6, '报销金额': [1200, 1500, 1800, 1700, 2100, 2300]})
    facts = _report_data_facts('报销明细表.csv', frame, '合计报销金额', version_id='expenses:v1')
    facts['sha256'] = '3' * 64
    sections = _report_sections([facts], '', '')
    slot = next(i for i, section in enumerate(sections) if section['type'] == 'chart_slot')
    sections[slot] = {'type': 'chart', 'path': _report_chart_from_facts([facts]), 'caption': '当前授权范围内的月份金额，单位未标注'}
    pages = [page.extract_text() for page in PdfReader(generate_pdf_report('经营分析简报', sections)).pages]
    note_page = next(text for text in pages if '本附录展示' in text)
    assert '附录' in note_page and '原始明细' in note_page and '2026-01' in note_page


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
    assert '金额（元）（元）' not in str(_verified_report_sections([facts], '合计200'))


def test_short_recommendation_table_keeps_all_its_rows_with_its_heading():
    import pandas as pd
    from pypdf import PdfReader
    from app.agents.tools import _report_data_facts, _verified_report_sections
    from app.tools.export import generate_pdf_report
    frame = pd.DataFrame({'月份': [f'2026-{i:02d}' for i in range(1, 7)],
                          '部门': ['财务部'] * 6, '金额（元）': [300*i for i in range(1, 7)]})
    facts = _report_data_facts('qa-context-3e2eb3bca6.csv', frame, '金额合计', version_id='f8bd4b7fb41744d19da76754271468d1:v3')
    facts['sha256'] = '7' * 64
    pages = [page.extract_text() for page in PdfReader(generate_pdf_report('经营分析简报', _verified_report_sections([facts], ''))).pages]
    recommendations = next(text for text in pages if '下一步行动' in text)
    assert all(label in recommendations for label in ('指标复核', '单位口径', '预算与对比'))


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


def test_numeric_condition_filters_the_same_rows_used_in_answer_and_report():
    import pandas as pd
    import pytest
    from app.tools.excel import filter_explicit_categories
    from app.agents.tools import _report_data_facts, _verified_data_answer
    frame = pd.DataFrame({'月份': ['2026-01', '2026-02', '2026-03'],
                          '金额（元）': [100, 300, 500]})
    result = filter_explicit_categories(frame, '金额超过300的记录有几条')
    assert result['金额（元）'].tolist() == [500]
    assert '超过300' in result.attrs['filter_note']
    facts = _report_data_facts('finance.csv', result, '金额超过300的记录有几条')
    assert facts['rows'] == 1 and facts['metrics'][0]['sum'] == 500
    answer = _verified_data_answer([facts], question='金额超过300的记录有几条')
    assert '1 条记录' in answer and '合计' not in answer
    assert filter_explicit_categories(frame, '金额不低于300且金额小于500')['金额（元）'].tolist() == [300]
    assert filter_explicit_categories(frame, '金额（元）<=-1').empty
    for question in ('利润超过300的记录', '金额超过3万元的记录', '金额超过300或金额小于200的记录'):
        with pytest.raises(ValueError):
            filter_explicit_categories(frame, question)


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
def test_group_chart_for_a_mean_question_does_not_plot_group_sums():
    import pandas as pd
    from app.agents.tools import _report_data_facts, _report_chart_metric
    facts = _report_data_facts('费用.csv', pd.DataFrame({'状态': ['已支付', '已支付', '已批准'],
        '金额（元）': [100, 300, 900]}), '按状态平均金额（元）')
    metric, groups, operation = _report_chart_metric([facts], '按状态平均金额（元）')
    assert dict(groups) == {'已支付': 200, '已批准': 900} and operation == '平均值'
    assert metric['unit'] == '元'
