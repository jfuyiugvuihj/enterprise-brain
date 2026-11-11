from pathlib import Path

import pytest

from app.agents.contracts import Principal
from app.rag.spreadsheets import load_spreadsheet
from app.rag.row_scope import project_spreadsheet_hit


def principal(role="manager"):
    return Principal(user_id="test", username="test", roles=[role], department="财务", clearance=2)


@pytest.fixture
def sheet(tmp_path):
    path = tmp_path / "费用.csv"
    path.write_text("部门,金额,classification\n财务,200,1\n销售,480,1\n研发,420,1\n财务,888,3\n,999,1\n", encoding="utf8")
    return load_spreadsheet(path)


def test_manager_prompt_and_source_content_exclude_foreign_and_secret_rows(sheet):
    hit = {"source": "费用.csv", "content": sheet.text, "classification": 1, "department": "财务"}
    result = project_spreadsheet_hit(hit, sheet, principal())
    assert result and "200" in result["content"]
    assert all(value not in result["content"] for value in ("销售", "研发", "480", "420", "888", "999"))
    assert "销售" in hit["content"]  # source candidates must not be mutated


def test_admin_retains_full_scope(sheet):
    hit = {"source": "费用.csv", "content": sheet.text}
    assert project_spreadsheet_hit(hit, sheet, principal("admin")) == hit


def test_stale_or_unrecognizable_fragment_is_not_emitted(sheet):
    hit = {"source": "费用.csv", "content": "销售 480 旧文件里还有不能解析的内容"}
    assert project_spreadsheet_hit(hit, sheet, principal()) is None


def test_foreign_only_fragment_is_not_emitted(sheet):
    hit = {"source": "费用.csv", "content": "| 销售 | 480 | 1 |"}
    result = project_spreadsheet_hit(hit, sheet, principal())
    assert result is None


@pytest.mark.parametrize("department,row,amount", [("销售", 1, "480"), ("研发", 2, "420")])
def test_own_fragment_keeps_original_row_position_after_authorization(sheet, department, row, amount):
    caller = Principal(user_id="test", username="test", roles=["manager"], department=department, clearance=2)
    hit = {"source": "费用.csv", "content": sheet.blocks[0].row_lines[row]}
    result = project_spreadsheet_hit(hit, sheet, caller)
    assert result and amount in result["content"]
    assert all(value not in result["content"] for value in ("200", "888", "999"))
