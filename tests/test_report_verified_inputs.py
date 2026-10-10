from app.agents.tools import _verified_data_sections


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
