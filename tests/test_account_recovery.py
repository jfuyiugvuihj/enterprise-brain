"""Account recovery through real PostgreSQL and the protected HTTP entry."""
import pytest
from fastapi.testclient import TestClient
from test_alert_scan_scope import alert_pg


@pytest.fixture
def accounts(alert_pg, monkeypatch):
    from app.common import auth
    from app.main import app

    with alert_pg() as conn:
        conn.execute('TRUNCATE users CASCADE')
    monkeypatch.setattr(auth, '_get_conn', alert_pg)
    monkeypatch.setattr(auth, '_db_ready', True)
    for name, role in [('recovery-admin', 'admin'), ('employee', 'staff'), ('other', 'staff')]:
        assert auth.create_user(name, 'before123', role=role, department='finance')[0]
    client = TestClient(app)
    def login(name, password='before123'):
        response = client.post('/api/v1/login', json={'username': name, 'password': password})
        assert response.status_code == 200, response.text
        return response.json()
    return client, login


def bearer(login):
    return {'Authorization': 'Bearer ' + login['token']}


def test_waiting_account_write_does_not_freeze_other_http_requests(accounts, alert_pg):
    import asyncio
    import threading
    import httpx
    from app.main import app
    _, login = accounts
    admin = login('recovery-admin')
    release = threading.Event()
    blocked = alert_pg()
    blocked.execute("SELECT id FROM users WHERE username='employee' FOR UPDATE")
    def unlock():
        release.wait(1.5)
        blocked.rollback()
        blocked.close()
        release.set()
    holder = threading.Thread(target=unlock)
    holder.start()
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            writing = asyncio.create_task(client.post('/api/v1/users/reset-password', headers=bearer(admin),
                json={'username': 'employee', 'new_password': 'temporary123'}))
            await asyncio.sleep(.05)
            try:
                health = await client.get('/api/v1/health')
                assert health.status_code == 200
                assert not release.is_set(), 'An account DB wait froze the unrelated health request'
            finally:
                release.set()
                result = await writing
                assert result.status_code == 200, result.text
    try:
        asyncio.run(check())
    finally:
        release.set()
        holder.join(5)


def test_admin_can_remove_an_unreadable_derived_file_without_granting_read_access(accounts, alert_pg, monkeypatch, tmp_path):
    from app.common.auth import get_user
    from app.agents.contracts import Principal
    from app.storage import artifacts
    from app.storage.persistence import PostgresPersistenceAdapter
    store = artifacts.ArtifactRegistry(root=tmp_path, persistence=PostgresPersistenceAdapter(alert_pg))
    monkeypatch.setattr(artifacts, 'artifact_registry', store)
    owner = Principal.from_user(get_user('employee'))
    source = tmp_path / 'source.txt'
    source.write_text('Synthetic source', encoding='utf-8')
    original = store.register(source, artifact_type='report', principal=owner)
    output = tmp_path / 'derived.txt'
    output.write_text('Synthetic derived file', encoding='utf-8')
    report = store.register(output, artifact_type='report', principal=owner, source_artifact_ids=[original.artifact_id])
    store.soft_delete(original.artifact_id)
    client, login = accounts
    admin, peer = bearer(login('recovery-admin')), bearer(login('other'))
    url = '/api/v1/artifacts/' + report.artifact_id
    assert client.get(url + '/content', headers=admin).status_code == 403
    assert client.get(url + '/download', headers=admin).status_code == 403
    assert client.delete(url, headers=peer).status_code == 403 and output.exists()
    result = client.delete(url, headers=admin)
    assert result.status_code == 200, result.text
    assert not output.exists() and store.get(report.artifact_id).status == 'deleted'


def test_admin_reset_revokes_sessions_and_requires_employee_to_choose_password(accounts):
    client, login = accounts
    admin, employee, other = login('recovery-admin'), login('employee'), login('other')
    body = {'username': 'employee', 'new_password': 'temporary123'}
    assert client.post('/api/v1/users/reset-password', headers=bearer(other), json=body).status_code == 403
    result = client.post('/api/v1/users/reset-password', headers=bearer(admin), json=body)
    assert result.status_code == 200, result.text
    assert client.get('/api/v1/profile', headers=bearer(employee)).status_code == 401
    assert client.post('/api/v1/login', json={'username': 'employee', 'password': 'before123'}).status_code == 401
    temporary = login('employee', 'temporary123')
    assert temporary['must_change_password'] is True
    assert client.get('/api/v1/profile', headers=bearer(temporary)).status_code == 403
    failed = client.put('/api/v1/users/password', headers=bearer(temporary), json={
        'username': 'employee', 'old_password': 'wrong', 'new_password': 'chosen123'})
    assert failed.status_code == 400
    assert client.get('/api/v1/account', headers=bearer(temporary)).json()['must_change_password'] is True
    changed = client.put('/api/v1/users/password', headers=bearer(temporary), json={
        'username': 'employee', 'old_password': 'temporary123', 'new_password': 'chosen123'})
    assert changed.status_code == 200, changed.text
    assert client.get('/api/v1/account', headers=bearer(temporary)).status_code == 401
    assert login('employee', 'chosen123')['must_change_password'] is False
    assert client.get('/api/v1/account', headers=bearer(other)).status_code == 200


def test_password_change_cannot_reuse_temporary_password_or_change_another_account(accounts):
    client, login = accounts
    admin = login('recovery-admin')
    assert client.post('/api/v1/users/reset-password', headers=bearer(admin), json={
        'username': 'employee', 'new_password': 'temporary123'}).status_code == 200
    temporary = login('employee', 'temporary123')
    for target, new in [('other', 'chosen123'), ('employee', 'temporary123')]:
        response = client.put('/api/v1/users/password', headers=bearer(temporary), json={
            'username': target, 'old_password': 'temporary123', 'new_password': new})
        assert response.status_code in (400, 403), response.text


def test_reset_invalidates_queued_and_running_tool_identity(accounts):
    from app.agents.contracts import Principal
    from app.agents.tools import _tool_principal
    from app.common import auth
    from deploy.queue_worker import resolve_consumption_principal
    client, login = accounts
    previous = Principal.from_user(auth.get_user('employee'))
    payload = {'username': previous.username, 'principal': previous.model_dump()}
    assert client.post('/api/v1/users/reset-password', headers=bearer(login('recovery-admin')), json={
        'username': 'employee', 'new_password': 'temporary123'}).status_code == 200
    projection, _, refusal = resolve_consumption_principal(payload)
    assert refusal and not projection
    with pytest.raises(PermissionError):
        _tool_principal({'configurable': {'principal': previous}})


def test_disable_restore_revokes_old_login_without_deleting_account(accounts):
    from app.common import auth
    from app.agents.contracts import Principal
    from deploy.queue_worker import resolve_consumption_principal
    client, login = accounts
    admin, employee, other = login('recovery-admin'), login('employee'), login('other')
    snapshot = Principal.from_user(auth.get_user('employee')).model_dump()
    body = {'username': 'employee', 'status': 'disabled'}
    assert client.put('/api/v1/users/status', headers=bearer(other), json=body).status_code == 403
    assert client.put('/api/v1/users/status', headers=bearer(admin), json=body).status_code == 200
    assert client.get('/api/v1/account', headers=bearer(employee)).status_code == 401
    assert client.post('/api/v1/login', json={'username': 'employee', 'password': 'before123'}).status_code == 403
    assert resolve_consumption_principal({'username': 'employee', 'principal': snapshot})[2]
    assert client.put('/api/v1/users/status', headers=bearer(admin), json={**body, 'status': 'active'}).status_code == 200
    assert login('employee')['must_change_password'] is False
    assert client.get('/api/v1/account', headers=bearer(employee)).status_code == 401
    assert resolve_consumption_principal({'username': 'employee', 'principal': snapshot})[2]
    roster = client.get('/api/v1/users', headers=bearer(admin)).json()['users']
    assert next(row for row in roster if row['username'] == 'employee')['status'] == 'active'


def test_last_active_administrator_cannot_be_disabled_deleted_or_demoted(accounts):
    from app.common import auth
    client, login = accounts
    admin = login('recovery-admin')
    users = client.get('/api/v1/users', headers=bearer(admin)).json()['users']
    own_id = next(row['id'] for row in users if row['username'] == 'recovery-admin')
    actions = [
        ('put', '/api/v1/users/status', {'username': 'recovery-admin', 'status': 'disabled'}),
        ('put', '/api/v1/users/role', {'username': 'recovery-admin', 'role': 'staff'}),
        ('delete', '/api/v1/users/' + str(own_id), None),
    ]
    for method, path, data in actions:
        response = client.request(method, path, headers=bearer(admin), **({'json': data} if data else {}))
        assert response.status_code == 409, response.text
    assert client.get('/api/v1/account', headers=bearer(admin)).status_code == 200
    assert auth.upsert_sso_user('recovery-admin', role='staff', department='finance')[0] is False
    assert auth.get_user('recovery-admin')['role'] == 'admin'


def test_concurrent_disables_leave_one_active_administrator(accounts):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.common import auth
    assert auth.create_user('second-admin', 'before123', role='admin', department='finance')[0]
    barrier = Barrier(2)
    def disable(name):
        barrier.wait(timeout=10)
        try:
            auth.update_account_status(name, 'disabled')
            return 'disabled'
        except auth.LastAdministratorError:
            return 'protected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(disable, ['recovery-admin', 'second-admin'])) == ['disabled', 'protected']
    assert sum(row['role'] == 'admin' and row['status'] == 'active' for row in auth.list_users()) == 1
