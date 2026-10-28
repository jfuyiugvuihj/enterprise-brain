import pandas as pd
import pytest


def test_policy_review_uses_each_questions_period_instead_of_the_combined_span():
    from app.agents.task_review import policy_question_reviews
    docs = [dict(source_name=f'{month}月制度.txt', version_id=str(month), index_version_id=f'idx{month}',
        excerpt=f'制度；生效日：2026-0{month}-01；适用日期：2026-0{month}-01至2026-0{month}-{end}。\n一、提交期限：{days}个工作日。')
        for month, end, days in [(1, 31, 5), (2, 28, 10)]]
    reviews = policy_question_reviews(docs, '①2026-01金额合计并核查制度？②2026-02金额合计并核查制度？')
    assert len(reviews) == 2
    assert reviews[0]['policy_sources'][0]['source_name'] == '1月制度.txt'
    assert reviews[1]['policy_sources'][0]['source_name'] == '2月制度.txt'
    assert '5个工作日' in reviews[0]['body'] and '10个工作日' not in reviews[0]['body']
    assert '10个工作日' in reviews[1]['body'] and '1月制度.txt' not in reviews[1]['body']


def test_unnumbered_statistics_accept_one_explicit_combined_report_without_dropping_a_question():
    from app.agents.task_review import independent_period_questions
    question = '2026-01金额合计是多少？2026-02金额合计是多少？'
    assert len(independent_period_questions(question + '不要生成图表，请把以上两项结果合并成一份PDF报告。')) == 2
    assert independent_period_questions(question + '为什么会增长？生成一份PDF报告。') == []
    assert len(independent_period_questions(question + '分别生成两份PDF报告。')) == 2
    assert len(independent_period_questions('2026-01金额合计是多少？2026-01金额平均值是多少？')) == 2
    from app.agents.task_review import report_delivery
    assert report_delivery('分别说明两项统计结果，生成一份PDF报告') == 'combined'


def test_multi_report_clarifies_before_dispatching_an_export():
    from app.agents.orchestrator import _initial_execution_state, main_agent_node, route_main
    q = '①2026-01金额合计是多少？②2026-02金额合计是多少？生成PDF报告。'
    state = _initial_execution_state(q, thread_id='clarify', user={},
        request_id='clarify', trace_id='clarify', task_id='clarify')
    update = main_agent_node(state)
    state['messages'] += update.pop('messages')
    state.update(update)
    assert '一份' in state['final_answer'] and '分别' in state['final_answer']
    assert route_main(state) == 'synthesize'
    assert not state['messages'][-1].tool_calls
    state['messages'][0].content = '请分析数据文件《合成验收.csv》。用户问题：' + q
    assert route_main(state) == 'synthesize'
    state['messages'][0].content = q.replace('生成PDF报告', '分别生成三份PDF报告')
    assert '份数' in main_agent_node(state)['final_answer']


def test_named_question_followup_changes_only_that_question_and_keeps_version():
    from app.agents.task_review import review_context, independent_period_questions
    q = '①2026-01金额合计是多少？②2026-02金额合计是多少？③2026-03金额平均值是多少？'
    prior = review_context(q, '费用.csv', {}, {'version_id': 'v1', 'sha256': 'original'})
    revised = review_context('把第二题改为2026-04的金额平均值是多少，其他不变，不生成图或报告。',
        '费用.csv', prior, {'version_id': 'v2', 'sha256': 'new'})
    items = independent_period_questions(revised['analysis_question'])
    assert items[0] == independent_period_questions(q)[0]
    assert '2026-04' in items[1][1] and '平均值' in items[1][1]
    assert items[2] == independent_period_questions(q)[2]
    assert revised['version_id'] == 'v1' and revised['sha256'] == 'original'
    unclear = review_context('把第五题改为2026-04的金额合计', '费用.csv', prior, {})
    assert 'clarification' in unclear and unclear['analysis_question'] == q


def test_mixed_questions_keep_policy_and_calculation_tasks_separate():
    from app.agents.task_review import scoped_question_items
    q = '①制度要求几天内提交凭证？②2026-01金额合计是多少？③为什么金额增加？不要生成图或报告。'
    items = scoped_question_items(q)
    assert [(x[0], x[2]) for x in items] == [('①', 'doc'), ('②', 'data'), ('③', 'explanation')]
    assert '制度' not in items[1][1] and '2026-01' not in items[0][1]
    from langchain_core.messages import AIMessage
    from app.agents.orchestrator import _initial_execution_state, route_main
    state = _initial_execution_state(q, thread_id='mixed', user={'data_filename': '费用.csv'},
        request_id='mixed', trace_id='mixed', task_id='mixed')
    state['messages'].append(AIMessage(content='', tool_calls=[
        {'name': 'dispatch', 'args': {'workers': ['data']}, 'id': 'mixed-dispatch'}]))
    assert {s.node for s in route_main(state) if hasattr(s, 'node')} == {'data', 'doc'}


@pytest.mark.parametrize('change, expected', [
    ('只把第二题的期间改为2026-04，其他不变', ('2026-04', '已支付', '中位数乘2')),
    ('把第二题改为2026-04金额中位数乘2，仅统计已批准，其他不变，不生成图或报告',
     ('2026-04', '已批准', '中位数乘2')),
    ('把第二题的状态改为仅统计已批准，其他不变', ('2026-02', '已批准', '中位数乘2')),
])
def test_targeted_followup_preserves_complete_complex_conditions(change, expected):
    from app.agents.task_review import review_context, question_items
    q = '①制度要求几天内提交凭证？②2026-02金额中位数乘2，仅统计已支付？③2026-03金额合计是多少？'
    prior = review_context(q, '费用.csv', {}, {'version_id': 'v1', 'sha256': 'original'})
    changed = review_context(change, '费用.csv', prior, {'version_id': 'v2', 'sha256': 'new'})
    before, after = question_items(q), question_items(changed['analysis_question'])
    assert 'clarification' not in changed
    assert before[0] == after[0] and before[2] == after[2]
    assert all(value in after[1][1] for value in expected)
    if '已批准' in expected:
        assert '已支付' not in after[1][1]
    assert changed['version_id'] == 'v1' and changed['sha256'] == 'original'


def test_rewriting_one_statistic_does_not_remove_its_department_or_threshold():
    from app.agents.task_review import review_context, question_items
    original = '①2026-01金额合计？②2026-02金额中位数乘2，部门为研发，金额超过100，仅统计已支付？'
    prior = review_context(original, '费用.csv', {}, {'version_id': 'v1'})
    revised = review_context('第二题改为2026-04金额平均值，其他条件不变', '费用.csv', prior, {})
    assert 'clarification' not in revised
    second = question_items(revised['analysis_question'])[1][1]
    assert all(part in second for part in ('2026-04', '平均值', '部门为研发', '金额超过100', '已支付'))


def test_explicit_mindmap_structure_without_lookup_does_not_run_a_speculative_analysis():
    from langchain_core.messages import AIMessage
    from app.agents.orchestrator import _initial_execution_state, route_main
    question = ('生成思维导图：中心“企业工作”，分支“经营分析”和“成果交付”。'
                '仅按这些内容生成图片，不需要查询资料或生成PDF。')
    state = _initial_execution_state(question, thread_id='mindmap-only', user={},
        request_id='mindmap-only', trace_id='mindmap-only', task_id='mindmap-only')
    state['plan'] = [{'worker': 'data'}, {'worker': 'chart'}]
    state['messages'].append(AIMessage(content='', tool_calls=[
        {'name': 'dispatch', 'args': {'workers': ['data', 'chart']}, 'id': 'mindmap-call'}]))
    assert [x.node for x in route_main(state) if hasattr(x, 'node')] == ['chart']
    state['worker_results'] = {'chart': '已生成真实图片'}
    assert route_main(state) == 'reflect'
    state['worker_results'] = {}
    state['data_filename'] = '已选经营表.csv'
    assert [x.node for x in route_main(state) if hasattr(x, 'node')] == ['data']


def test_alert_metadata_is_not_a_filter_or_a_policy_review_request():
    from app.agents.task_review import alert_task_question, is_review_question
    question = ('按月份汇总金额（元）与记录数，说明需核对资料，生成PDF报告。'
        '\n\n提醒编号：24；状态：还没人处理'
        '\n\n已有分析：主要构成2026-06 600；2026-05 500。'
        '\n\n触发规则：月度提醒；条件：大于 1000')
    intent = alert_task_question(question, {'alert_id': 24})
    assert intent == question.split('\n\n提醒编号：')[0]
    assert not is_review_question(intent)
    assert alert_task_question(question, {}) == question
    explicit = '仅统计金额（元）大于300的记录，核查制度并导出PDF。'
    assert alert_task_question(explicit + '\n\n提醒编号：24', {'alert_id': 24}) == explicit
    assert is_review_question(explicit)


def test_alert_report_does_not_retrieve_current_tables_as_historical_evidence():
    from langchain_core.messages import AIMessage
    from app.agents.orchestrator import _initial_execution_state, route_main
    question = ('按月份汇总金额（元）与记录数，说明需核对资料，生成月度趋势图和PDF报告。'
        '\n\n提醒编号：24\n\n已有分析：未提供业务原因证据，请核对业务材料。\n\n触发规则：月度提醒；条件：大于 1000')
    state = _initial_execution_state(question, thread_id='alert-report',
        user={'data_filename': '费用.csv', 'data_context': {'alert_id': 24, 'version_id': 'v1'}},
        request_id='alert-report', trace_id='alert-report', task_id='alert-report')
    state['plan'] = [{'worker': 'doc'}, {'worker': 'data'}, {'worker': 'chart'}]
    state['messages'].append(AIMessage(content='', tool_calls=[
        {'name': 'dispatch', 'args': {'workers': ['doc']}, 'id': 'alert-call'}]))
    assert [x.node for x in route_main(state) if hasattr(x, 'node')] == ['data']
    state['worker_results'] = {'data': '合计2100'}
    assert [x.node for x in route_main(state) if hasattr(x, 'node')] == ['chart']
    state['worker_results']['chart'] = '真实图表'
    assert [x.node for x in route_main(state) if hasattr(x, 'node')] == ['export']


def test_refusing_a_report_does_not_turn_a_query_into_a_full_table_summary():
    from app.agents.task_review import table_summary_intent
    assert not table_summary_intent('按金额降序取前2条数据，不生成图表，不生成报告。')
    assert not table_summary_intent('统计金额的中位数，不生成报告。')
    assert table_summary_intent('金额超过300的记录数，不生成图或报告。')
    assert table_summary_intent('按部门合计金额，生成PDF报告。')


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


def test_selected_file_total_is_an_operation_not_an_unknown_category():
    from app.tools.excel import filter_explicit_categories
    import pytest
    frame = pd.DataFrame({'部门': ['财务部', '财务部'], '金额（元）': [100, 200]})
    for question in ('仅计算所选文件的金额合计，导出PDF', '仅统计当前选中的数据的金额合计'):
        assert filter_explicit_categories(frame, question)['金额（元）'].sum() == 300
    with pytest.raises(ValueError):
        filter_explicit_categories(frame, '仅统计部门为不存在的部门')


def test_invalid_or_ambiguous_period_never_silently_sums_all_rows():
    from app.tools.excel import filter_explicit_categories
    frame = pd.DataFrame({'发生日期': ['2026-10-01', '无法识别'], '金额': [120, 80]})
    with pytest.raises(ValueError, match='日期'):
        filter_explicit_categories(frame, '2026-10-01至2026-10-05，按部门汇总金额')


def test_month_column_keeps_independent_question_totals():
    from app.agents.task_review import independent_period_questions
    from app.tools.excel import filter_explicit_categories
    frame = pd.DataFrame({'月份': ['2026-01', '2026-01', '2026-02', '2026-03'],
                          '报销金额': [1200, 800, 2450, 2900]})
    question = '不要生成图或报告：①2026-01报销金额合计多少？②2026-02报销金额合计多少？③2026-03报销金额合计多少？'
    totals = [filter_explicit_categories(frame, item)['报销金额'].sum()
              for _, item in independent_period_questions(question)]
    assert totals == [2000, 2450, 2900]
    with pytest.raises(ValueError, match='月度|精度'):
        filter_explicit_categories(frame, '2026-01-15至2026-02-10报销金额合计')


def test_question_marks_separate_explicit_period_statistics_without_numbering():
    from app.agents.task_review import independent_period_questions
    from app.tools.excel import filter_explicit_categories
    question = '2026-01的金额（元）合计是多少？2026-02的金额（元）合计是多少？不要生成图表或报告。'
    items = independent_period_questions(question)
    assert len(items) == 2
    frame = pd.DataFrame({'月份': ['2026-01', '2026-02'], '金额（元）': [100, 200]})
    assert [filter_explicit_categories(frame, item)['金额（元）'].sum() for _, item in items] == [100, 200]
    for ambiguous in ['2026-01和2026-02金额合计是多少？', '2026-01多少？2026-02多少？',
            '①2026-01金额合计多少？2026-02金额合计多少？',
            '仅统计已支付，2026-01金额合计多少？2026-02金额合计多少？',
            '2026-01金额合计多少？为什么？2026-02金额合计多少？']:
        assert independent_period_questions(ambiguous) == []


def test_numeric_months_are_calendar_months_and_mixed_precision_is_rejected():
    from app.tools.excel import filter_explicit_categories
    numeric = pd.DataFrame({'月份': [202601, 202602], '金额': [100, 200]})
    selected = filter_explicit_categories(numeric, '2026-01金额合计')
    assert selected['金额'].sum() == 100
    from app.agents.tools import _report_data_facts
    facts = _report_data_facts('月份.csv', selected, '汇总统计')
    assert facts['observed_period'].startswith('2026-01')
    assert [metric['column'] for metric in facts['metrics']] == ['金额']
    mixed = pd.DataFrame({'月份': ['2026-01', '2026-02-15'], '金额': [100, 200]})
    with pytest.raises(ValueError, match='月度|精度'):
        filter_explicit_categories(mixed, '2026-01-15至2026-02-20金额合计')


def test_missing_requested_metric_never_becomes_another_metric():
    from app.agents.tools import _report_data_facts
    frame = pd.DataFrame({'月份': ['2026-05'], '部门': ['财务'], '报销金额': [3350]})
    with pytest.raises(ValueError, match='预算金额'):
        _report_data_facts('报销.csv', frame, '2026-05预算金额合计多少？')
    assert _report_data_facts('报销.csv', frame, '按部门合计报销金额')['metrics'][0]['sum'] == 3350
    business = pd.DataFrame({'收入': [100], '利润': [30]})
    assert len(_report_data_facts('经营.csv', business, '收入和利润合计')['metrics']) == 2
    with pytest.raises(ValueError, match='预算'):
        _report_data_facts('经营.csv', business, '收入和预算合计')


def test_calculation_scope_preserves_actual_period_unit_and_row_count():
    from app.agents.tools import _calculation_scope
    from app.tools.excel import filter_explicit_categories
    frame = pd.DataFrame({'月份': ['2026-01', '2026-02'], '收入（万元）': [20, 30]})
    selected = filter_explicit_categories(frame, '2026-01收入合计')
    scope = _calculation_scope(selected, '2026-01收入合计')
    assert scope['period'] == '2026-01（月份）'
    assert scope['period_kind'] == 'requested'
    assert scope['rows'] == 1 and scope['units'] == [{'column': '收入（万元）', 'unit': '万元'}]
    assert scope['filter'] == selected.attrs['filter_note']
    unrestricted = _calculation_scope(frame, '收入合计')
    assert unrestricted['period_kind'] == 'observed'
    assert unrestricted['period'].startswith('未限定期间；数据覆盖2026-01')
    annotated = pd.DataFrame({'年月': ['2026-01', '2026-02'], '收入（不含税）': [20, 30]})
    scope = _calculation_scope(annotated, '收入合计')
    assert scope['period'].startswith('未限定期间；数据覆盖2026-01')
    assert scope['units'][0]['unit'] == '单位未标注'


def test_current_graph_request_identity_is_not_guessed_for_unmatched_history():
    from app.api.v1.chat import _attach_current_request
    from app.agents.contracts import Principal
    principal = Principal.from_user({'username': 'scope-user', 'role': 'manager', 'department': 'finance'})
    messages = [{'role': 'assistant', 'content': '已完成2000'}]
    saved = {'principal': principal, 'request_id': 'req-known', 'final_answer': '已完成2000'}
    assert _attach_current_request(messages, saved, principal)[-1]['request_id'] == 'req-known'
    assert 'request_id' not in _attach_current_request(messages, {**saved, 'final_answer': '另一个结果'}, principal)[-1]
    assert 'request_id' not in _attach_current_request(messages, {**saved, 'principal': {'user_id': 'other'}}, principal)[-1]


def test_pending_report_restores_the_verified_calculation_request_only():
    from app.api.v1.chat import _attach_current_request
    from app.agents.contracts import Principal
    principal = Principal.from_user({'username': 'scope-user', 'role': 'manager', 'department': 'finance'})
    messages = [{'role': 'assistant', 'content': '合计2000'}]
    saved = {'principal': principal, 'request_id': 'req-pending', 'final_answer': '',
             'agent_results': {'data': {'request_id': 'req-pending', 'answer': '合计2000'}}}
    assert _attach_current_request(messages, saved, principal, pending_request_id='req-pending')[-1]['request_id'] == 'req-pending'
    assert 'request_id' not in _attach_current_request(messages, saved, principal, pending_request_id='req-other')[-1]
    assert 'request_id' not in _attach_current_request([{'role': 'assistant', 'content': '旧结果'}], saved, principal, pending_request_id='req-pending')[-1]


def test_unrelated_empty_condition_does_not_cancel_absolute_output_refusal():
    from langchain_core.messages import AIMessage
    from app.agents.orchestrator import _initial_execution_state, route_main
    state = _initial_execution_state('分析经营变化，不要生成图或报告；如果费用为空请说明无数据。',
        thread_id='conditional', user={'data_filename': '费用.csv'},
        request_id='conditional', trace_id='conditional', task_id='conditional')
    state['worker_results'] = {'data': '已分析'}
    state['agent_results'] = {'data': {'evidence': [{'source_type': 'dataset', 'metadata': {'row_count': 5}}]}}
    state['messages'].append(AIMessage(content='', tool_calls=[
        {'name': 'dispatch', 'args': {'workers': ['data', 'chart', 'export']}, 'id': 'conditional-call'}]))
    assert route_main(state) == 'reflect'


@pytest.mark.parametrize('prohibition', ['不要生成图或报告', '不生成图表或报告', '无需生成图表和PDF'])
def test_negated_outputs_do_not_route_to_report_or_dispatch_exports(prohibition):
    from langchain_core.messages import AIMessage
    from app.agents.nodes import classify_route
    from app.agents.orchestrator import _initial_execution_state, route_main
    question = f'请计算2026-01报销金额合计，{prohibition}。'
    assert classify_route(question).lane == 'analysis'
    state = _initial_execution_state(question, thread_id='negative-output',
        user={'data_filename': '费用.csv'}, request_id='negative', trace_id='negative', task_id='negative')
    state['messages'].append(AIMessage(content='', tool_calls=[
        {'name': 'dispatch', 'args': {'workers': ['data', 'chart', 'export']}, 'id': 'negative-call'}]))
    assert [step.node for step in route_main(state) if hasattr(step, 'node')] == ['data']
    # A default/selected report lane must not re-add an explicitly refused action.
    config = {'configurable': {'declared_lane': 'report'}}
    assert [step.node for step in route_main(state, config) if hasattr(step, 'node')] == ['data']


def test_finished_calculation_is_not_retried_for_refused_outputs():
    from langchain_core.messages import HumanMessage
    from app.agents.nodes import reflect_node
    result = reflect_node({'messages': [HumanMessage(content='合计多少？不要生成图或报告。')],
                           'final_answer': '合计为2000，单位未标注。'})
    assert result['redo'] is False


def test_chart_refusal_keeps_requested_pdf_export():
    from langchain_core.messages import AIMessage
    from app.agents.orchestrator import _initial_execution_state, route_main
    state = _initial_execution_state('报销金额合计，导出PDF，不生成图表。', thread_id='pdf-only',
        user={'data_filename': '费用.csv'}, request_id='pdf', trace_id='pdf', task_id='pdf')
    state['messages'].append(AIMessage(content='', tool_calls=[
        {'name': 'dispatch', 'args': {'workers': ['data', 'chart', 'export']}, 'id': 'pdf-call'}]))
    dispatched = [step.node for step in route_main(state) if hasattr(step, 'node')]
    assert 'chart' not in dispatched and 'export' in dispatched


def test_requested_pdf_brief_is_still_exported_after_calculation():
    from langchain_core.messages import AIMessage
    from app.agents.orchestrator import _initial_execution_state, route_main
    state = _initial_execution_state('2026-01报销金额合计，生成一份PDF简报，不要生成图表。',
        thread_id='brief', user={'data_filename': '费用.csv'},
        request_id='brief', trace_id='brief', task_id='brief')
    state['worker_results'] = {'data': '已完成金额计算'}
    state['messages'].append(AIMessage(content='', tool_calls=[
        {'name': 'dispatch', 'args': {'workers': ['export']}, 'id': 'brief-call'}]))
    assert [step.node for step in route_main(state) if hasattr(step, 'node')] == ['export']


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
