import pandas as pd

from app.agents.tools import _report_data_facts, _verified_data_answer


def test_named_row_question_uses_its_value_in_final_answer():
    frame = pd.DataFrame({
        "项目": ["日常费用", "走查标记"],
        "数值": [100, 1025713],
    })

    facts = _report_data_facts("验收.csv", frame, "走查标记这一行的数值是多少？", version_id="v2")
    answer = _verified_data_answer([facts])

    assert "项目＝走查标记" in answer
    assert "数值：1,025,713.00" in answer
    assert "版本：v2" in answer
    assert "1,025,813.00" not in answer


def test_total_question_still_uses_aggregate():
    frame = pd.DataFrame({"项目": ["甲", "乙"], "数值": [100, 200]})

    facts = _report_data_facts("验收.csv", frame, "这张表的数值合计是多少？", version_id="v1")
    answer = _verified_data_answer([facts])

    assert "数值合计：300.00" in answer
    assert "named_rows" not in facts
