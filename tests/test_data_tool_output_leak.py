"""The data tool feeds the answer that a caller sees when no model is available."""

from app.agents.tools import _analyze_data


def _config():
    return {"configurable": {"user_id": "7", "username": "tester", "role": "manager", "department": "finance"}}


def test_data_tool_output_carries_data_only(tmp_path, monkeypatch):
    from app.agents import tools

    frame_file = tmp_path / "sales.csv"
    frame_file.write_text("小组,金额\n华东,1100\n华南,900\n", encoding="utf-8")
    monkeypatch.setattr(
        tools, "_authorized_dataset_files", lambda config: ([("sales.csv", str(frame_file))], None)
    )

    answer = _analyze_data("按小组汇总金额", _config())

    assert "数据分析结果:" in answer
    assert "华东" in answer, answer
    for scaffolding in ("用户查询:", "图表生成时直接使用", "上述数据样本"):
        assert scaffolding not in answer, f"internal instruction leaked into the answer: {scaffolding}"
