"""Reanalysis must keep a checked metric instead of silently changing arithmetic."""
import pytest
import uuid
from fastapi.testclient import TestClient

from test_alert_scan_scope import alert_pg, _headers


@pytest.fixture
def reuse_case(alert_pg, monkeypatch, tmp_path):
    from app.agents.contracts import Principal
    from app.api.v1 import calculations as api, data
    from app.common import auth
    from app.main import app
    from app.semantics import registry as semantics
    from app.semantics.execution import bind_metric
    from app.storage import calculations, datasets
    from app.storage.calculations import CalculationStorage
    from app.storage.persistence import PostgresPersistenceAdapter

    tag = uuid.uuid4().hex[:8]
    user = {'username': 'reuse-' + tag, 'role': 'manager', 'department': 'finance'}
    owner = Principal.from_user(user)
    monkeypatch.setattr(auth, 'get_user', lambda name: {**user, 'username': name,
        'department': 'hr' if name == 'outsider' else 'finance'})
    store = datasets.DatasetRegistry(tmp_path, store=datasets.PostgresDatasetTableStore(connection_factory=alert_pg))
    for module in (datasets, calculations, data):
        monkeypatch.setattr(module, 'dataset_registry', store)
    calc = CalculationStorage(PostgresPersistenceAdapter(alert_pg))
    for module in (calculations, api):
        monkeypatch.setattr(module, 'calculation_storage', calc)
    monkeypatch.setattr(semantics, '_conn', alert_pg)
    monkeypatch.setattr(semantics, '_database_available', lambda: True)
    path = tmp_path / f'reuse-{tag}.csv'
    path.write_text('store,profit,state\nwest,10,active\neast,30,active\neast,999,void\n', encoding='utf-8')
    first = store.register(path, principal=owner)
    options = dict(metric_id='reuse.profit.mean', metric_name='有效利润均值', definition_version='v1',
        formula='MEAN(profit)', unit='元', period_type='month', source_scope=[first.dataset_id],
        filters={'state': 'active'}, owner_id=owner.user_id, verified_document='合成口径.md',
        verified_section='均值', verified_by='fixture-reviewer')
    definition = semantics.register_metric_definition(**options)
    binding = bind_metric(definition['definition_id'], owner.user_id, first)
    run = calc.start_run(owner.user_id, first.version_id, 'reuse-original',
        {'filename': first.filename, 'query': '按store统计有效利润均值', 'metric_binding': binding,
         'scope': {'classification': first.classification, 'department_ids': first.department_ids}},
        formula=binding['formula'], metric_definition_id=binding['definition_id'])
    run = calc.complete_run(run['calculation_run_id'], {'columns': ['store', 'profit', 'state']})
    path = store.new_version_path(first.filename)
    path.write_text('store,profit,state\nwest,100,active\neast,300,active\neast,999,void\n', encoding='utf-8')
    latest = store.register(path, filename=first.filename, principal=owner)
    return dict(client=TestClient(app, raise_server_exceptions=False), owner=owner, store=store,
        calc=calc, first=first, latest=latest, run=run, options=options, semantics=semantics,
        url=f"/api/v1/calculations/{run['calculation_run_id']}/reuse")


def test_prepares_latest_version_with_original_metric_without_starting_calculation(reuse_case):
    c = reuse_case
    response = c['client'].get(c['url'], headers=_headers(c['owner'].user_id))
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft['version_id'] == c['latest'].version_id != c['first'].version_id
    assert draft['reuse']['metric_binding'] == c['run']['parameters']['metric_binding']
    assert len(draft['reuse']['metric_binding_sha256']) == 64
    assert draft['reuse']['calculation_run_id'] == c['run']['calculation_run_id']
    assert c['calc'].get(c['run']['calculation_run_id']) == c['run']
    assert len(c['calc'].list_for(c['owner'])) == 1
    assert response.headers['cache-control'] == 'no-store'


def test_other_account_and_changed_definition_cannot_reuse_old_metric(reuse_case):
    c = reuse_case
    denied = c['client'].get(c['url'], headers=_headers('outsider'))
    assert denied.status_code == 403 and 'MEAN' not in denied.text
    c['semantics'].register_metric_definition(**{**c['options'], 'formula': 'SUM(profit)'})
    changed = c['client'].get(c['url'], headers=_headers(c['owner'].user_id))
    assert changed.status_code == 409 and '口径' in changed.text


def test_plain_calculation_remains_plain_when_reused(reuse_case):
    c = reuse_case
    original = c['run']
    parameters = {key: value for key, value in original['parameters'].items() if key != 'metric_binding'}
    run = c['calc'].start_run(c['owner'].user_id, c['first'].version_id, 'plain-reuse', parameters)
    c['calc'].complete_run(run['calculation_run_id'], original['result'])
    response = c['client'].get(f"/api/v1/calculations/{run['calculation_run_id']}/reuse",
                               headers=_headers(c['owner'].user_id))
    assert response.status_code == 200, response.text
    assert response.json()['reuse']['metric_binding'] is None
    assert response.json()['reuse']['metric_binding_sha256'] is None


def test_definition_changed_after_draft_is_refused_before_a_task_starts(reuse_case):
    c = reuse_case
    draft = c['client'].get(c['url'], headers=_headers(c['owner'].user_id)).json()
    c['semantics'].register_metric_definition(**{**c['options'], 'formula': 'SUM(profit)'})
    response = c['client'].post('/api/v1/ask', headers=_headers(c['owner'].user_id), json={
        'message': '按store统计有效利润均值', 'data_filename': c['latest'].filename,
        'expected_data_version_id': draft['version_id'],
        'metric_definition_id': draft['reuse']['metric_binding']['definition_id'],
        'expected_metric_binding_sha256': draft['reuse']['metric_binding_sha256']})
    assert response.status_code == 409 and '口径' in response.text
    assert len(c['calc'].list_for(c['owner'])) == 1
