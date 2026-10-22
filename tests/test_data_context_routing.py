from app.api.v1.chat import _should_use_data_context


def test_policy_question_does_not_force_selected_data_file():
    assert not _should_use_data_context(
        "住宿费用通常按什么标准报销？超过标准需要准备哪些材料？",
        "expenses.csv",
    )


def test_data_comparison_uses_selected_data_file():
    assert _should_use_data_context(
        "哪个部门住宿费最高、哪个最低，差距是多少？",
        "expenses.csv",
    )


def test_data_followup_uses_selected_data_file():
    assert _should_use_data_context(
        "如果只看住宿费这一列，最高的记录和平均值相差多少？",
        "expenses.csv",
    )
