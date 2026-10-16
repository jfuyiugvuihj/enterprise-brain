from decimal import Decimal
from app.approval.assistant import extract_standard, build_precheck


def test_approval_tiers_are_not_reimbursement_limits():
    assert extract_standard(['金额不超过500元：部门经理审批。金额超过500元且不超过2000元：财务审批。']) is None


def test_conflicting_limits_require_context_instead_of_taking_minimum():
    assert extract_standard(['甲城市住宿上限500元。乙城市住宿上限800元。']) is None
    assert extract_standard(['住宿上限500元。']) == Decimal('500')


def test_amount_comparison_does_not_claim_full_compliance():
    result = build_precheck(100, 500, '财务', '住宿', ['制度原文'])
    assert result['status'] == '金额未超过所给标准'
    assert '不代表全面合规' in result['recommendation']
