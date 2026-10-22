import pandas as pd
import pytest

from app.tools.excel import filter_explicit_categories


@pytest.mark.parametrize("query", ["只计算这份数据的总行数", "仅统计总行数", "只计算该表的记录数"])
def test_count_operation_keeps_all_rows(query):
    frame = pd.DataFrame({"部门": ["财务部", "销售部"], "金额": [80, 120]})
    result = filter_explicit_categories(frame, query)
    pd.testing.assert_frame_equal(result, frame)


def test_unknown_category_is_not_treated_as_count_operation():
    frame = pd.DataFrame({"部门": ["财务部", "销售部"], "金额": [80, 120]})
    with pytest.raises(ValueError, match="未知"):
        filter_explicit_categories(frame, "仅统计未知部门")


def test_explicit_category_still_filters_rows():
    frame = pd.DataFrame({"部门": ["财务部", "销售部"], "金额": [80, 120]})
    result = filter_explicit_categories(frame, "只统计部门为财务部的记录")
    assert result["部门"].tolist() == ["财务部"]
