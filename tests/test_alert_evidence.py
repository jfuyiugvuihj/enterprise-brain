import pandas as pd
import pytest
from app.common.identity import Principal


def test_alert_calculation_filters_hidden_rows_and_records_unknown_unit():
    from app.insights.alert_evidence import calculate_finding, explain_finding
    frame = pd.DataFrame({'部门': ['财务', '财务', '销售'], '金额': [120, 80, 999],
                          '发生日期': ['2026-10-01', '2026-10-02', '2026-10-02']})
    principal = Principal.from_user({'username': 'fin', 'role': 'manager', 'department': '财务'})
    evidence = calculate_finding(frame, {'id': 7, 'metric': '金额', 'op': 'gt', 'threshold': 150},
        filename='合成验收.csv', dataset_id='dataset-1', version_id='v1', sha256='hash', principal=principal)
    assert evidence['current'] == 200 and evidence['rows'] == 2
    assert evidence['unit'] == '单位未标注'
    assert evidence['contributions'] == [{'label': '财务', 'value': 200.0}]
    assert '999' not in str(evidence)
    assert '阈值提醒' in explain_finding(evidence)
    assert '不判断异常增长或确定原因' in explain_finding(evidence)


def test_version_update_preserves_original_evidence_and_recovery_is_not_manual_close():
    from app.insights.alert_evidence import observation_update
    first = {'version_id': 'v1', 'current': 200, 'breached': True}
    prior = {'evidence': first, 'observations': [first], 'status': 'closed', 'recovered_at': ''}
    update = observation_update(prior, {**first, 'version_id': 'v2', 'current': 100, 'breached': False}, 'now')
    assert update['status'] == 'closed' and update['recovered_at'] == 'now'
    assert [item['version_id'] for item in update['observations']] == ['v1', 'v2']
    assert update['evidence']['current'] == 100


def test_non_additive_alert_metric_is_refused():
    from app.insights.alert_evidence import calculate_finding
    with pytest.raises(ValueError, match='不可直接求和'):
        calculate_finding(pd.DataFrame({'毛利率': [.2, .3]}), {'id': 1, 'metric': '毛利率', 'threshold': .4},
            filename='test.csv', dataset_id='d', version_id='v', sha256='h', principal=None)
