import pandas as pd
import pytest

from app.tools.excel import filter_explicit_categories
from app.agents.task_review import independent_period_questions


def test_joint_question_keeps_one_department_and_date_range():
    frame = pd.DataFrame(
        {
            "发生日期": ["2026-01-10", "2026-03-02", "2026-07-01", "2026-04-09"],
            "部门": ["财务部", "财务部", "财务部", "销售部"],
            "报销金额": [100, 200, 400, 500],
        }
    )
    question = (
        "仅统计财务部发生日期 2026-01-01至2026-06-30 的报销金额合计与记录数，"
        "并核对所选制度对凭证、审批记录和付款证明的要求"
    )

    filtered = filter_explicit_categories(frame, question)

    assert len(filtered) == 2
    assert filtered["报销金额"].sum() == 300
    assert "部门仅包含财务部" in filtered.attrs["filter_note"]


@pytest.mark.parametrize("question", [
    "请回答：①仅财务部 2026-01-01 至 2026-06-30 的记录数？②金额合计？",
    "财务部 2026-01 的报销金额合计与记录数是多少？",
])
def test_short_department_scope_and_month_do_not_include_sales(question):
    frame = pd.DataFrame({"发生日期": ["2026-01-10", "2026-03-02", "2026-04-09"],
                          "部门": ["财务部", "财务部", "销售部"], "报销金额": [100, 200, 500]})
    filtered = filter_explicit_categories(frame, question)
    assert filtered["部门"].eq("财务部").all()
    assert "部门仅包含财务部" in filtered.attrs["filter_note"]
    if "2026-01 的" in question:
        assert filtered["报销金额"].tolist() == [100]


def test_distinct_months_and_range_must_not_be_combined_into_one_answer():
    frame = pd.DataFrame({"发生日期": ["2026-01-10", "2026-03-02"],
                          "部门": ["财务部", "财务部"], "报销金额": [100, 200]})
    with pytest.raises(ValueError, match="多段统计期间"):
        filter_explicit_categories(frame, "①财务部 2026-01 合计；②财务部 2026-03 合计；"
                                          "③2026-01-01 至 2026-06-30 总合计")


def test_numbered_independent_periods_keep_each_question():
    question = ("分别回答：①财务部 2026-01 报销金额合计；"
                "②财务部 2026-03 报销金额合计；"
                "③财务部 2026-01-01 至 2026-06-30 报销金额总合计。")
    items = independent_period_questions(question)
    assert len(items) == 3
    assert [label for label, _ in items] == ["①", "②", "③"]
    assert "2026-01 报销" in items[0][1]
    assert "2026-03 报销" in items[1][1]
    assert "2026-01-01 至 2026-06-30" in items[2][1]


def test_arabic_numbered_questions_keep_shared_department_scope():
    question = ("仅财务部，请分别回答：1. 2026-01 报销金额合计；"
                "2. 2026-03 报销金额合计；"
                "3. 2026-01-01 至 2026-06-30 报销金额总合计。")
    items = independent_period_questions(question)
    assert [label for label, _ in items] == ["1.", "2.", "3."]
    frame = pd.DataFrame({"发生日期": ["2026-01-10", "2026-03-02", "2026-04-09"],
                          "部门": ["财务部", "财务部", "销售部"], "报销金额": [100, 200, 500]})
    prefix = question.split(items[0][0], 1)[0]
    totals = [filter_explicit_categories(frame, prefix + item)["报销金额"].sum()
              for _, item in items]
    assert totals == [100, 200, 300]
