import pandas as pd
import pytest


def test_joint_review_keeps_document_versions_until_explicit_new_task():
    from app.agents.task_review import review_context
    first = review_context('2026-10-01至2026-10-10，仅统计已支付，核查制度', '费用.csv', {},
        {'version_id': 'data-v1'}, documents=[{'filename': '制度.pdf', 'version_id': '1'}])
    assert '仅依据以下文件' not in first['analysis_question']
    followup = review_context('解释这个数', '费用.csv', first, {'version_id': 'data-v1'},
        documents=[{'filename': '制度.pdf', 'version_id': '2'}])
    assert followup['requested_documents'] == first['requested_documents']
    first['policy_sources'] = [{'source_name': '制度.pdf', 'version_id': '1'}]
    cleared = review_context('解释这个数', '费用.csv', first, {'version_id': 'data-v1'}, documents=[])
    assert cleared['requested_documents'] == [] and 'policy_sources' not in cleared
    assert '仅统计已支付' in cleared['analysis_question']
    renewed = review_context('重新发起核查，2026-10-01至2026-10-10', '费用.csv', first,
        {'version_id': 'data-v2'}, documents=[{'filename': '制度.pdf', 'version_id': '2'}])
    assert renewed['requested_documents'][0]['version_id'] == '2'


def test_explicit_period_excludes_other_dates_before_totals():
    from app.tools.excel import filter_explicit_categories
    frame = pd.DataFrame({'发生日期': ['2026-10-01', '2026-10-02', '2026-10-03', '2026-10-05', '2026-10-06'],
                          '状态': ['已支付', '已支付', '已批准', '待审批', '已支付'],
                          '金额': [120, 80, 300, 200, 420]})
    result = filter_explicit_categories(frame, '2026-10-02至2026-10-05，仅统计已批准或已支付的金额')
    assert result['金额'].sum() == 380
    assert len(result) == 2
    assert '2026-10-02' in result.attrs['filter_note']
    assert result.attrs['filter_note'].count('状态仅包含已批准、已支付') == 1


def test_invalid_or_ambiguous_period_never_silently_sums_all_rows():
    from app.tools.excel import filter_explicit_categories
    frame = pd.DataFrame({'发生日期': ['2026-10-01', '无法识别'], '金额': [120, 80]})
    with pytest.raises(ValueError, match='日期'):
        filter_explicit_categories(frame, '2026-10-01至2026-10-05，按部门汇总金额')


def test_review_followup_keeps_input_version_and_original_filters():
    from app.agents.task_review import review_context
    first = review_context('2026-10-02至2026-10-05，仅统计已批准或已支付，按部门汇总金额并核查制度',
                           '费用.csv', {}, {'version_id': 'fees:v1', 'sha256': 'abc'})
    following = review_context('为什么是这个数？生成核查PDF', '费用.csv', first,
                               {'version_id': 'fees:v2', 'sha256': 'def'})
    assert following['version_id'] == 'fees:v1'
    assert following['analysis_question'] == first['analysis_question']


@pytest.mark.parametrize('change', ['只统计已支付', '仅计算已支付', '只保留已支付', '改读工作表「费用明细」'])
def test_partial_scope_change_preserves_other_conditions(change):
    from app.agents.task_review import review_context
    original = '2026-10-02至2026-10-05，仅统计已批准或已支付，按部门汇总金额并核查制度'
    prior = review_context(original, '费用.xlsx', {}, {'version_id': 'v1'})
    revised = review_context(change, '费用.xlsx', prior, {'version_id': 'v2'})
    assert '2026-10-02至2026-10-05' in revised['analysis_question']
    assert '按部门汇总金额' in revised['analysis_question']
    if '工作表' in change:
        assert '已批准或已支付' in revised['analysis_question']
    else:
        assert '已批准' not in revised['analysis_question']
    assert revised['version_id'] == 'v1'


def test_policy_identity_does_not_depend_on_file_title():
    from app.agents.task_review import policy_identity
    assert policy_identity([{'source_name': '报销办法.pdf', 'version_id': '2',
                             'index_version_id': 'idx2'}])[0]['source_name'] == '报销办法.pdf'


def test_deleted_policy_quote_is_withheld_from_history(monkeypatch):
    from app.api.v1 import chat
    from app.storage.calculations import calculation_storage
    from app.agents.contracts import Principal
    monkeypatch.setattr(chat, '_history_catalog_rows', lambda: [])
    monkeypatch.setattr(calculation_storage, 'session_access_denied', lambda *a: False)
    rows, withheld = chat._history_scope_face([{'role': 'assistant',
        'content': '依据：《报销办法.pdf》；制度原文：秘密条款。'}],
        Principal.from_user({'id': 'f', 'role': 'manager', 'department': 'finance'}), 's')
    assert withheld == 1 and '秘密条款' not in rows[0]['content']


def test_review_does_not_append_unfiltered_table_quotes_as_calculation_basis():
    from app.agents.nodes import _cited_caliber_fragments
    state = {'task_context': {'filename': '费用.csv'}, 'agent_results': {'doc': {'evidence': [{
        'source_name': '费用.csv', 'provenance_status': 'verified', 'permission_checked': True,
        'excerpt': '筛选外原文记录120'}]}}}
    assert _cited_caliber_fragments(state) == []


def test_policy_review_quotes_original_and_never_calls_approval_tiers_a_limit():
    from app.agents.task_review import policy_review_text
    documents = [{'source_name': '现行制度.pdf', 'version_id': 'doc:2', 'source_id': '现行制度.pdf#chunk=0',
                  'excerpt': '版本：V2；生效日：2026-10-01。\n费用发生日期自2026-10-01起采用本版。\n一、材料：费用明细、原始凭证、业务用途说明和相关批准记录。\n二、提交期限：费用发生后10个工作日内提交。\n三、金额不超过500元（含500元）：部门经理审批。\n六、批准只表示审批完成，不表示已经付款。'}]
    text = policy_review_text(documents, period='2026-10-02 至 2026-10-05', unit_known=False)
    assert '10个工作日' in text and 'doc:2' in text and '现行制度.pdf' in text
    assert '原始凭证' in text and '提交日期' in text and '单位' in text
    assert '全面合规' in text and '无法判断' in text
    assert '符合标准' not in text and '报销上限500' not in text
    assert '已核验：本次授权数据' not in text
    assert '0条' in policy_review_text(documents, period='2026-10-02至2026-10-05', verified_rows=0)


def test_explicit_status_change_replaces_prior_status_equals_phrase():
    from app.agents.task_review import review_context
    prior = review_context('2026-10-02至2026-10-05，状态为已批准，按部门汇总', '费用.csv', {}, {'version_id': 'v1'})
    revised = review_context('改为仅计算已支付记录', '费用.csv', prior, {'version_id': 'v2'})
    assert '状态为已批准' not in revised['analysis_question']
    assert '仅计算已支付记录' in revised['analysis_question']
    assert '2026-10-02至2026-10-05' in revised['analysis_question']


def test_policy_evidence_keeps_actual_hit_version():
    from app.agents.evidence import new_evidence_bag, record_document_hits
    bag = new_evidence_bag()
    record_document_hits(bag, query='制度', hits=[{'source': '制度.pdf', 'content': '条款',
                         'chunk_index': 3, 'version': 2, 'index_version_id': 'idx-2'}])
    assert bag['documents'][0]['version_id'] == '2'
    assert bag['documents'][0]['index_version_id'] == 'idx-2'


def test_report_distinguishes_requested_period_from_observed_dates():
    from app.agents.tools import _report_data_facts
    frame = pd.DataFrame({'发生日期': ['2026-10-03'], '金额': [300]})
    frame.attrs['requested_period'] = '2026-10-02 至 2026-10-05（发生日期）'
    facts = _report_data_facts('费用.csv', frame, '按部门汇总金额')
    assert facts['period'] == frame.attrs['requested_period']
    assert '2026-10-03' in facts['observed_period']


def test_calculated_answer_explains_total_with_filtered_detail():
    from app.agents.tools import _report_data_facts, _verified_data_answer
    facts = _report_data_facts('费用.csv', pd.DataFrame({'申请编号': ['SYN-002'],
        '发生日期': ['2026-10-02'], '部门': ['试用-财务'], '金额': [80], '状态': ['已支付']}), '按部门汇总金额')
    answer = _verified_data_answer([facts])
    assert 'SYN-002' in answer and '2026-10-02' in answer and '已支付' in answer
    assert '80.00' in answer and '1 / 1' in answer


def test_report_preserves_analysis_explanation_limits_and_detail_table():
    from app.agents.tools import _analysis_body_sections
    sections = _analysis_body_sections('### 计算事实\n\n合计200，来自120和80；单位未注明。\n\n'
        '| 编号 | 金额 |\n| --- | --- |\n| F1 | 120 |\n| F2 | 80 |\n\n'
        '### 尚待核实\n\n> 无提交日期，无法判断期限。')
    assert any(s.get('content') == '合计200，来自120和80；单位未注明。' for s in sections)
    assert any(s.get('content') == '无提交日期，无法判断期限。' for s in sections)
    assert next(s for s in sections if s['type'] == 'table')['rows'] == [['F1', '120'], ['F2', '80']]


def test_original_analysis_chart_becomes_report_slot_not_internal_url_text():
    from app.agents.tools import _analysis_body_sections
    sections = _analysis_body_sections('销量合计30。\n\n图表已生成: ![销量（件）](/api/v1/artifacts/abc123/content)')
    assert any(s['type'] == 'chart_slot' for s in sections)
    assert '/api/v1/artifacts/' not in str(sections)
    two = _analysis_body_sections('甲说明\n![甲](/api/v1/artifacts/chartA/content)\n乙说明\n![乙](/api/v1/artifacts/chartB/content)')
    assert [s['artifact_id'] for s in two if s['type']=='chart_slot'] == ['chartA', 'chartB']
    assert [s['type'] for s in two] == ['text','chart_slot','text','chart_slot']


def test_non_expense_report_does_not_sum_identifiers_or_ratios_or_invent_missing_budget():
    from app.agents.tools import _report_data_facts, _verified_report_sections
    frame = pd.DataFrame({'产品': ['甲', '乙'], '销量（件）': [10, 20], '毛利率': [.2, .3],
                          '订单编号': [1001, 1002], '预算销量': [12, 25]})
    facts = _report_data_facts('合成验收-销量.csv', frame, '按产品汇总销量（件）')
    assert [item['column'] for item in facts['metrics']] == ['销量（件）']
    text = str(_verified_report_sections([facts], ''))
    assert '费用汇总' not in text and '费用复核' not in text
    assert '当前材料未提供预算' not in text


def test_report_original_question_does_not_request_a_new_chart_or_analysis():
    from langchain_core.messages import AIMessage
    from app.agents.orchestrator import _initial_execution_state, route_main
    state = _initial_execution_state('请将以下已完成的分析原文排版导出为 PDF 报告。\n'
        '分析问题：不生成图表或报告。', thread_id='preserved-report',
        user={'data_filename': '费用.csv'}, request_id='report', trace_id='report', task_id='report')
    state['task_context'] = {'report_body': '已验证200，单位未标注。',
        'execution_question': '请将以下已完成的分析原文排版导出为 PDF 报告。分析问题：不生成图表或报告。'}
    state['messages'].append(AIMessage(content='', tool_calls=[
        {'name': 'dispatch', 'args': {'workers': ['doc', 'data', 'chart', 'export']}, 'id': 'report-call'}]))
    assert [step.node for step in route_main(state) if hasattr(step, 'node')] == ['export']


def test_retrieved_policy_keeps_index_identity_through_hit_projection():
    from app.rag.retriever import DocumentRetriever
    hits = DocumentRetriever._hit_dicts(None, ['制度正文'], [{'filename': '制度.pdf',
        'index_version_id': 'index-v2', 'content_sha256': 'source-hash'}], 'semantic')
    assert hits[0]['index_version_id'] == 'index-v2'
    assert hits[0]['content_sha256'] == 'source-hash'


def test_review_routing_keeps_original_action_constraints_after_rewrite():
    from langchain_core.messages import AIMessage
    from app.agents.orchestrator import _initial_execution_state, route_main
    from app.agents.task_review import review_context
    question = '改为仅计算已批准记录，其他条件沿用，导出核查PDF，不生成图表。'
    state = _initial_execution_state('计算已批准记录，生成图表和报告', thread_id='review-actions',
        user={'task_question': question, 'data_filename': '费用.csv'},
        request_id='req-actions', trace_id='trace-actions', task_id='task-actions')
    state['task_context'] = review_context(question, '费用.csv', {}, {'version_id': 'v1'})
    state['worker_results'] = {'doc': '制度依据', 'data': '0条记录'}
    state['messages'].append(AIMessage(content='', tool_calls=[
        {'name': 'dispatch', 'args': {'workers': ['chart', 'export']}, 'id': 'call-actions'}]))
    dispatched = route_main(state)
    assert [step.node for step in dispatched if hasattr(step, 'node')] == ['export']
