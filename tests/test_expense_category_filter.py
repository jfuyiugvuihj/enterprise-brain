import pandas as pd
import pytest

from app.tools.excel import filter_explicit_categories


@pytest.fixture
def expenses():
    return pd.DataFrame({
        "部门": ["财务", "销售", "研发", "人事", "销售", "研发"],
        "状态": ["已批准", "已支付", "已批准", "已支付", "待审批", "已驳回"],
        "金额": [200, 480, 420, 210, 200, 200],
    })


@pytest.mark.parametrize("question", [
    "仅统计已批准或已支付，排除待审批和已驳回，按部门汇总金额与合计",
    "只汇总状态为已批准或已支付。",
    "仅统计“已批准”或“已支付”",
    "排除待审批和已驳回",
])
def test_explicit_status_filter_has_same_total_with_or_without_quotes(expenses, question):
    actual = filter_explicit_categories(expenses, question)
    assert actual["金额"].sum() == 1310
    assert set(actual["状态"]) == {"已批准", "已支付"}


def test_unknown_status_does_not_silently_widen_to_all_rows(expenses):
    with pytest.raises(ValueError):
        filter_explicit_categories(expenses, "仅统计状态为已批准或不存在")


def test_ambiguous_column_requires_name(expenses):
    expenses["复核状态"] = expenses["状态"]
    with pytest.raises(ValueError):
        filter_explicit_categories(expenses, "仅统计已批准或已支付")


def test_no_category_instruction_preserves_amounts(expenses):
    assert filter_explicit_categories(expenses, "按部门汇总金额")["金额"].sum() == 1710


def test_valid_status_absent_from_own_rows_is_still_a_valid_filter(expenses):
    own = expenses.loc[expenses["部门"] == "财务"]
    actual = filter_explicit_categories(own, "仅统计已批准或已支付，排除待审批和已驳回", category_frame=expenses)
    assert actual["金额"].sum() == 200 and len(actual) == 1


def test_unknown_unquoted_category_is_not_ignored(expenses):
    with pytest.raises(ValueError):
        filter_explicit_categories(expenses, "仅统计已撤销")
