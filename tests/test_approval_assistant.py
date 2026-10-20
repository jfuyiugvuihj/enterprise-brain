from app.approval.assistant import build_precheck, parse_expense_request, extract_standard


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


def test_expense_amount_needs_currency_or_an_amount_label():
    assert parse_expense_request("汇总报销审批环节，演示编号193416，制度版本2026")['amount'] is None
    assert parse_expense_request("住宿费500元，单据编号193416")['amount'] == 500
    assert parse_expense_request("申请金额500，单据编号193416")['amount'] == 500
    assert parse_expense_request("制度标准300元，申请金额500")['amount'] == 500
    assert parse_expense_request("申请金额500，制度标准300元")['amount'] == 500


def test_policy_standard_requires_a_monetary_unit():
    assert extract_standard(["评估标准1：模型准确率", "住宿每晚上限500元"]) == 500
    assert extract_standard(["最高1万元"]) == 10000
