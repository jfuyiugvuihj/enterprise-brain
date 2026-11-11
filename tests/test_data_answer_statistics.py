import pandas as pd

from app.agents.tools import _answer_query


def _frame():
    return pd.DataFrame({"小组": ["华东", "华东", "华南"], "金额": [1100, 2300, 4000]})


def _summary_lines(query):
    lines = _answer_query(_frame(), query, ["金额"], ["小组"])
    return [line for block in lines for line in block.splitlines()]


def test_a_total_is_reported_instead_of_n_a():
    summary = _summary_lines("统计一下")

    assert any(line.startswith("  合计: 金额: 7400.0") for line in summary), summary
    assert not any("N/A" in line for line in summary), summary


def test_the_other_describe_fields_still_come_from_describe():
    summary = _summary_lines("汇总")

    assert any("均值: 金额: 2466.7" in line for line in summary), summary
    assert any("最小: 金额: 1100.0" in line for line in summary), summary
    assert any("最大: 金额: 4000.0" in line for line in summary), summary
