"""Selected catalog arithmetic must be the result the employee actually receives."""
from dataclasses import replace

import pandas as pd
import pytest

from app.semantics.execution import calculate_metric, execution_support
from app.semantics.registry import MetricDefinition
from test_alert_scan_scope import alert_pg


def definition(**changes):
    item = MetricDefinition(metric_id="expense.mean", metric_name="有效费用均值", definition="仅统计有效记录",
        definition_version="v1", formula="MEAN(金额（元）)", unit="元", period_type="month",
        timezone="Asia/Shanghai", time_granularity="月", match_terms=(), source="metric_definitions",
        warnings=(), definition_id="metric-test", owner_id="owner", source_scope=("费用.csv",),
        filters={"状态": "有效"}, verification_state="verified", verified_document="费用口径（合成）.md",
        verified_section="均值", verified_by="fixture-reviewer", verified_at="2026-10-28")
    return replace(item, **changes)


def binding(**changes):
    item = definition(**changes)
    return {**item.to_public(), "definition_id": item.definition_id}


def test_employee_answer_and_report_use_selected_mean_instead_of_generic_total():
    from app.agents.tools import _answer_query, _report_data_facts, _report_sections, _verified_data_answer, _calculation_scope
    frame = pd.DataFrame({"部门": ["甲", "甲", "乙"], "金额（元）": [10., 30., 999.], "状态": ["有效", "有效", "作废"]})
    frame, result = calculate_metric(frame, binding(), "按部门统计", dimension="部门")
    assert result["value"] == 20 and result["rows"] == 2
    answer = "\n".join(_answer_query(frame, "按部门统计", ["金额（元）"], ["部门"]))
    assert "有效费用均值：20.00" in answer and "MEAN(金额（元）)" in answer
    facts = [_report_data_facts("费用.csv", frame, "按部门统计", version_id="input-v1")]
    assert facts[0]["metric_result"] == result
    assert _calculation_scope(frame, '按部门统计')['units'] == [{'column': '有效费用均值', 'unit': '元'}]
    assert "有效费用均值：20.00" in _verified_data_answer(facts)
    assert "MEAN(金额（元）)" in str(_report_sections(facts, "", ""))
    assert _report_sections(facts, '', '')[0]['type'] == 'summary'
    assert "999" not in answer
    series = []
    _answer_query(frame, '按部门统计', ['金额（元）'], ['部门'], series_out=series)
    assert series[0]['kind'] == 'group' and series[0]['operation'] == 'MEAN'
    original = '### 制度依据\n\n必须提供原始凭证。\n\n### 核查限制\n\n缺少业务用途说明。'
    assert '必须提供原始凭证' in str(_report_sections(facts, '', original))


@pytest.mark.parametrize("formula,question", [("MEAN(金额（元）)", "金额合计"),
    ("SUM(金额（元）)", "计算中位数"), ("COUNT(*)", "计算同比")])
def test_incompatible_question_cannot_override_selected_formula(formula, question):
    with pytest.raises(ValueError, match="运算"):
        calculate_metric(pd.DataFrame({"金额（元）": [1.], "状态": ["有效"]}), binding(formula=formula), question)


def test_empty_mean_and_missing_values_do_not_become_zero():
    frame = pd.DataFrame({"金额（元）": [float("nan")], "状态": ["有效"]})
    _, result = calculate_metric(frame, binding(), "统计")
    assert result["value"] is None and result["missing"] == 1
    _, count = calculate_metric(frame, binding(formula="COUNT(*)", unit="条"), "统计")
    assert count["value"] == 1


def test_unsupported_unverified_and_unit_mismatch_are_not_executed():
    assert not execution_support(definition(formula="__import__('os')"))["supported"]
    assert not execution_support(definition(verification_state="unverified"))["supported"]
    assert not execution_support(definition(source_scope=()))["supported"]
    with pytest.raises(ValueError, match="单位"):
        calculate_metric(pd.DataFrame({"金额（元）": [1.], "状态": ["有效"]}), binding(unit="万元"), "统计")


@pytest.mark.parametrize('question', ['计算金额最大值', '计算利润合计', '计算金额占比'])
def test_other_operations_or_columns_cannot_be_answered_as_selected_total(question):
    frame = pd.DataFrame({'金额（元）': [10., 30.], '利润': [1., 3.], '状态': ['有效', '有效']})
    with pytest.raises(ValueError):
        calculate_metric(frame, binding(formula='SUM(金额（元）)'), question)


def test_new_full_metric_question_replaces_prior_goal_but_keeps_input_version():
    from app.agents.task_review import review_context
    old = review_context('按部门统计有效费用均值', '费用.csv', {}, {'version_id': 'v1', 'sha256': 'hash'})
    old['metric_binding'] = binding()
    new = review_context('按月份统计有效费用均值', '费用.csv', old, {'version_id': 'v2', 'sha256': 'changed'})
    assert new['analysis_question'] == '按月份统计有效费用均值'
    assert new['version_id'] == 'v1' and new['metric_binding'] == old['metric_binding']


def test_numeric_grouping_dimension_is_not_another_requested_metric():
    frame = pd.DataFrame({'年度': [2025, 2026, 2026], '金额（元）': [10., 20., 30.], '状态': ['有效'] * 3})
    _, result = calculate_metric(frame, binding(formula='COUNT(*)', unit='条'), '按年度统计记录数', dimension='年度')
    assert result['value'] == 3 and result['groups'] == [('2025', 1), ('2026', 2)]


def test_real_pg_metric_binding_records_execution_and_rejects_changed_definition(alert_pg, monkeypatch, tmp_path):
    from app.agents import tools
    from app.agents.contracts import Principal
    from app.agents.evidence import new_evidence_bag
    from app.semantics import registry as semantics
    from app.semantics.execution import bind_metric
    from app.storage import calculations, datasets
    from app.storage.calculations import CalculationStorage
    from app.storage.persistence import PostgresPersistenceAdapter

    owner = Principal.from_user({'id': 'metric-owner', 'username': 'metric-owner',
                                 'role': 'manager', 'department': 'finance'})
    store = datasets.PostgresDatasetTableStore(connection_factory=alert_pg)
    dataset_registry = datasets.DatasetRegistry(tmp_path, store=store)
    path = tmp_path / 'metric.csv'
    path.write_text('store,profit,state\nwest,10,active\neast,30,active\neast,999,void\n', encoding='utf-8')
    source = dataset_registry.register(path, principal=owner)
    monkeypatch.setattr(datasets, 'dataset_registry', dataset_registry)
    monkeypatch.setattr(calculations, 'dataset_registry', dataset_registry)
    calc = CalculationStorage(PostgresPersistenceAdapter(alert_pg))
    monkeypatch.setattr(calculations, 'calculation_storage', calc)
    monkeypatch.setattr(semantics, '_conn', alert_pg)
    monkeypatch.setattr(semantics, '_database_available', lambda: True)
    options = dict(metric_id='active.profit.mean', metric_name='有效利润均值', definition_version='v1',
        formula='MEAN(profit)', unit='元', period_type='month', source_scope=[source.dataset_id],
        filters={'state': 'active'}, owner_id=owner.user_id, verified_document='合成口径.md',
        verified_section='均值', verified_by='fixture-reviewer')
    registered = semantics.register_metric_definition(**options)
    assert registered['result'] == 'inserted'
    selected = bind_metric(registered['definition_id'], owner.user_id, source)
    with pytest.raises(ValueError, match='不可用'):
        bind_metric(registered['definition_id'], 'other-owner', source)
    with pytest.raises(ValueError, match='不适用'):
        bind_metric(registered['definition_id'], owner.user_id,
                    type('OtherSource', (), {'filename': 'other.csv', 'dataset_id': 'other'})())
    bag = new_evidence_bag()
    config = {'configurable': {'principal': owner, 'data_filename': source.filename,
        'thread_id': 'metric-execution:data', 'request_id': 'metric-execution',
        'data_question': '按store统计', 'evidence_bag': bag,
        'data_context': {'filename': source.filename, 'version_id': source.version_id,
                         'sha256': source.content_sha256, 'metric_binding': selected}}}
    answer = tools._analyze_data('按store统计', config)
    assert '有效利润均值：20.00' in answer, answer
    row = calc.list_for(owner, request_id='metric-execution')[0]
    assert row['metric_definition_id'] == selected['definition_id']
    assert row['formula'] == 'MEAN(profit)' and row['dataset_version_id'] == source.version_id
    assert row['parameters']['metric_binding'] == selected
    assert row['result']['metric_result']['value'] == 20
    assert row['result']['rows'] == 2
    assert bag['report_facts'][0]['metric_result']['value'] == 20
    assert calc.can_view(row, owner)
    assert not calc.can_view(row, Principal.from_user({'id': 'other', 'username': 'other',
        'role': 'manager', 'department': 'sales'}))
    revised = semantics.register_metric_definition(**{**options, 'formula': 'SUM(profit)'})
    assert revised['definition_id'] == selected['definition_id']  # same ID/version was edited
    config['configurable']['request_id'] = 'metric-changed'
    rejected = tools._analyze_data('按store统计', config)
    assert '口径已发生变化' in rejected, rejected
    assert not calc.list_for(owner, request_id='metric-changed')
    assert calc.get(row['calculation_run_id'])['parameters']['metric_binding'] == selected
