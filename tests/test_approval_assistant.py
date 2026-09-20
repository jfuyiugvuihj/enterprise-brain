from app.approval.assistant import build_precheck


def test_precheck_marks_over_standard_without_auto_approval():
    result = build_precheck(
        amount=650,
        standard=500,
        department="市场部",
        expense_type="住宿费",
        evidence=["差旅制度.pdf 第3页"],
    )

    assert result["risk_level"] == "high"
    assert result["excess_amount"] == 150
    assert result["approved"] is False
    assert result["recommendation"]


def test_precheck_marks_insufficient_evidence_as_unconfirmed():
    result = build_precheck(100, 500, "财务部", "住宿费", [])
    assert result["status"] == "无法确认"
    assert result["approved"] is False
