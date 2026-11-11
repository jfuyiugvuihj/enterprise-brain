import pandas as pd

from app.agents.tools import _answer_query, _requested_group_series


def test_department_chart_uses_group_total_instead_of_date_preview():
    df = pd.DataFrame({"部门": ["财务", "财务"], "发生日期": ["2026-10-01", "2026-10-02"], "金额": [120, 80]})
    series = []
    _answer_query(df, "按部门汇总金额与合计，生成柱状图", ["金额"], ["部门", "发生日期"], series_out=series)
    result = _requested_group_series({"chart_series": series}, "按部门汇总金额与合计，生成柱状图")
    assert result["labels"] == ["财务"]
    assert result["values"] == [200]


def test_unspecified_dimension_does_not_override_model_selection():
    assert _requested_group_series({"chart_series": []}, "请画图") == {}
