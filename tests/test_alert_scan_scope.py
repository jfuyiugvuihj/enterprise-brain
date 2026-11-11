"""Alert sweep scope (P1-3) and per-sweep idempotency (E1-11).

The sweep used to read ``<repo>/data`` through a hardcoded ``../../../data``
join, so a tenant's own DATA_DIR was never evaluated while leftover files in
the repository folder were analyzed as if they belonged to whoever pressed
"check now". These checks use disposable PostgreSQL and never call a model.
"""
import shutil
import os
import json
import secrets
import subprocess
import time
from uuid import uuid4
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _rule(rule_id=1, name="profit-floor", metric="profit", op="gt", threshold=1.0):
    return {
        "id": rule_id,
        "name": name,
        "metric": metric,
        "op": op,
        "threshold": threshold,
        "enabled": True,
    }


def _write_business_csv(directory: Path, name: str, profit: float) -> Path:
    path = directory / name
    path.write_text(f"store,profit\nwest,{profit:.2f}\n", encoding="utf-8")
    return path


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _offline_rules(monkeypatch, rules: list[dict]) -> list[dict]:
    """Force the no-Postgres path and keep the real in-memory fallback clean."""
    from app.api.v1 import alerts

    recorded: list[dict] = []
    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(alerts, "_MEM_RULES", rules)
    monkeypatch.setattr(alerts, "_MEM_ALERTS", recorded)
    monkeypatch.setattr(alerts, "_ai_analysis", lambda rule, value: "offline analysis")
    return recorded


@pytest.fixture(scope="module")
def alert_pg():
    """Use the cached deployment image, random loopback port, and no mounted volumes."""
    import psycopg
    from psycopg.rows import dict_row
    from app.db.migrations import apply_migrations

    image = "pgvector/pgvector:pg16"
    if not shutil.which("docker"):
        pytest.skip("alert scope integration requires Docker")
    available = subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=15)
    if available.returncode:
        pytest.skip("alert scope integration requires the cached PGVector deployment image")
    name, password = "eb-test-alert-" + uuid4().hex[:12], secrets.token_urlsafe(24)
    created = subprocess.run(
        ["docker", "run", "--detach", "--rm", "--pull=never", "--name", name,
         "--publish", "127.0.0.1::5432", "--env", "POSTGRES_PASSWORD", image,
         "-c", "shared_buffers=16MB", "-c", "max_connections=20"],
        env={**os.environ, "POSTGRES_PASSWORD": password}, capture_output=True, text=True, timeout=30)
    assert created.returncode == 0, created.stderr
    try:
        port_result = subprocess.run(["docker", "inspect", name], capture_output=True, text=True, timeout=10)
        assert port_result.returncode == 0, port_result.stderr
        port = json.loads(port_result.stdout)[0]["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"]

        def connect():
            return psycopg.connect(host="127.0.0.1", port=int(port), user="postgres",
                password=password, dbname="postgres", connect_timeout=1, row_factory=dict_row)

        deadline = time.monotonic() + 30
        while True:
            try:
                with connect() as connection, pytest.MonkeyPatch.context() as environment:
                    environment.setenv("EMBEDDING_MODEL", "isolated-alert-test")
                    environment.setenv("EMBEDDING_DIMENSION", "8")
                    apply_migrations(connection, "postgres")
                break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.2)
        yield connect
    finally:
        subprocess.run(["docker", "rm", "--force", name], capture_output=True, timeout=20, check=True)


@pytest.fixture(autouse=True)
def calculation_postgres(alert_pg, monkeypatch):
    from app.storage import calculations, datasets
    from app.storage.calculations import CalculationStorage
    from app.storage.datasets import PostgresDatasetTableStore
    from app.storage.persistence import PostgresPersistenceAdapter

    with alert_pg() as connection:
        connection.execute("TRUNCATE datasets, alerts, alert_rules CASCADE")
    monkeypatch.setattr(datasets, "build_dataset_table_store",
        lambda: PostgresDatasetTableStore(connection_factory=alert_pg))
    monkeypatch.setattr(calculations, "calculation_storage",
        CalculationStorage(PostgresPersistenceAdapter(alert_pg)))


@pytest.fixture
def scan_dirs(request):
    """A tenant DATA_DIR plus a stand-in for the repository folder, under tmp/."""
    root = Path.cwd() / "tmp" / f"x1_{request.node.name}"
    shutil.rmtree(root, ignore_errors=True)
    tenant = root / "tenant_data"
    legacy = root / "legacy_repo_data"
    tenant.mkdir(parents=True)
    legacy.mkdir(parents=True)
    try:
        yield tenant, legacy
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_sweep_evaluates_the_tenant_data_dir_and_not_the_other_folder(scan_dirs, monkeypatch):
    from app.api.v1 import alerts, data
    from app.agents.contracts import Principal
    from app.storage import datasets as dataset_storage
    from app.storage.datasets import DatasetRegistry

    tenant, legacy = scan_dirs
    east = _write_business_csv(tenant, "east.csv", 42.0)
    # The value the audit saw coming out of the repository folder.
    leftover = _write_business_csv(legacy, "qa_ascii_leftover.csv", 560.0)
    (legacy / "not_business.txt").write_text("ignore me", encoding="utf-8")
    owner = Principal.from_user(
        {"id": "u_scan_owner", "username": "scan_owner", "role": "manager", "department": "finance"}
    )
    tenant_registry = DatasetRegistry(root=tenant, metadata_path=tenant / ".dataset-metadata.json")
    first = tenant_registry.register(east, principal=owner, filename="east.csv")
    monkeypatch.setattr(dataset_storage, "dataset_registry", tenant_registry)
    monkeypatch.setattr(data, "DATA_DIR", str(tenant))
    _offline_rules(monkeypatch, [_rule()])

    summary: dict = {}
    triggered = alerts.evaluate_all(principal=owner, scan_summary=summary)

    assert summary["data_dir_configured"] is True
    assert summary["evaluated_files"] == ["east.csv"]
    assert [item["message"] for item in triggered] == ["profit-floor: profit=42 (gt 1)"]
    assert triggered[0]["evidence"]["current"] == 42.0
    assert not any("560.0" in item["message"] for item in triggered)
    # DATA_DIR is what decides the scope, in both directions.
    tenant_registry.soft_delete(first.dataset_id)
    legacy_registry = DatasetRegistry(root=legacy, metadata_path=legacy / ".dataset-metadata.json")
    legacy_registry.register(leftover, principal=owner, filename="qa_ascii_leftover.csv")
    monkeypatch.setattr(dataset_storage, "dataset_registry", legacy_registry)
    monkeypatch.setattr(data, "DATA_DIR", str(legacy))
    relocated = alerts.evaluate_all(principal=owner)

    assert [item["message"] for item in relocated] == ["profit-floor: profit=560 (gt 1)"]
    assert relocated[0]["evidence"]["current"] == 560.0


def test_registry_path_mismatch_is_not_empty_success_or_recovery(scan_dirs, monkeypatch):
    from app.api.v1 import alerts, data
    from app.agents.contracts import Principal
    from app.storage import datasets
    from app.storage.datasets import DatasetRegistry

    tenant, legacy = scan_dirs
    owner = Principal.from_user({"id": "owner", "username": "owner", "role": "manager", "department": "finance"})
    original = DatasetRegistry(root=tenant)
    original.register(_write_business_csv(tenant, "east.csv", 42), principal=owner)
    monkeypatch.setattr(datasets, "dataset_registry", DatasetRegistry(root=legacy))
    monkeypatch.setattr(data, "DATA_DIR", str(legacy))
    recorded = _offline_rules(monkeypatch, [_rule()])
    summary = {}
    assert alerts.evaluate_all(principal=owner, scan_summary=summary) == []
    assert summary["reason"] == "dataset_registry_unavailable"
    assert summary["evaluation_failures"] and summary["recovered"] == 0
    assert not recorded


def test_departmentless_admin_can_reopen_own_calculation(scan_dirs, monkeypatch):
    from app.agents.contracts import Principal
    from app.agents.tools import _start_calculation
    from app.storage import calculations, datasets

    tenant, _ = scan_dirs
    owner = Principal.from_user({'username': 'owner', 'role': 'manager', 'department': 'finance'})
    registry = datasets.DatasetRegistry(root=tenant)
    registry.register(_write_business_csv(tenant, 'finance.csv', 42), principal=owner)
    monkeypatch.setattr(datasets, 'dataset_registry', registry)
    monkeypatch.setattr(calculations, 'dataset_registry', registry)
    admin = Principal.from_user({'username': 'admin', 'role': 'admin', 'department': ''})
    config = {'configurable': {'principal': admin, 'thread_id': 'admin-scope:data', 'request_id': 'scope-request'}}
    run_id = _start_calculation(config, 'finance.csv', 'profit合计', operation='analyze_data')
    record = calculations.calculation_storage.complete_run(run_id, {'rows': 1})
    assert record['parameters']['department'] == ''
    assert record['parameters']['scope']['department_ids'] == ['finance']
    assert calculations.calculation_storage.can_view(record, admin)
    assert not calculations.calculation_storage.session_access_denied(admin, 'admin-scope')
    other = Principal.from_user({'username': 'other', 'role': 'manager', 'department': 'finance'})
    assert not calculations.calculation_storage.can_view(record, other)


def test_report_keeps_actionable_reason_when_its_data_version_changed(scan_dirs, monkeypatch):
    from app.agents.contracts import Principal
    from app.agents.tools import _export_report
    from app.storage import datasets
    tenant, _ = scan_dirs
    owner = Principal.from_user({'username': 'report-owner', 'role': 'manager', 'department': 'finance'})
    registry = datasets.DatasetRegistry(root=tenant)
    first = registry.register(_write_business_csv(tenant, 'finance.csv', 42), principal=owner)
    replacement = registry.new_version_path('finance.csv')
    replacement.write_text('store,profit\nwest,84\n', encoding='utf-8')
    registry.register(replacement, principal=owner, filename='finance.csv')
    monkeypatch.setattr(datasets, 'dataset_registry', registry)
    config = {'configurable': {'principal': owner, 'data_filename': 'finance.csv',
              'data_question': 'profit合计', 'data_context': {'version_id': first.version_id, 'sha256': first.content_sha256}}}
    result = _export_report('经营分析简报', '[]', config)
    assert '输入数据版本已变化' in result and '重新发起' in result
    assert '报告已生成' not in result


def test_query_scope_describes_input_not_the_derived_result(scan_dirs, monkeypatch):
    from app.agents.contracts import Principal
    from app.agents import tools
    from app.storage import calculations, datasets
    tenant, _ = scan_dirs
    path = tenant / 'finance.csv'
    path.write_text('department,月份,金额（元）\nfinance,2026-01,100\nfinance,2026-02,300\nhr,2026-03,900\n', encoding='utf-8')
    owner = Principal.from_user({'username': 'query-owner', 'role': 'manager', 'department': 'finance'})
    registry = datasets.DatasetRegistry(root=tenant)
    dataset = registry.register(path, principal=owner)
    monkeypatch.setattr(datasets, 'dataset_registry', registry)
    monkeypatch.setattr(calculations, 'dataset_registry', registry)
    # Only replace the model's generated expression, not authorization, execution,
    # or calculation persistence. The result is a count, not a currency amount.
    monkeypatch.setattr(tools, '_llm_pandas_code', lambda df, query: "df[df['金额（元）'] > 200].shape[0]")
    config = {'configurable': {'principal': owner, 'data_filename': 'finance.csv',
        'thread_id': 'query-scope:data', 'request_id': 'query-input-scope', 'data_question': '查看当前数据'}}
    answer = tools._query_data('金额超过200的记录有几条', config)
    row = calculations.calculation_storage.list_for(owner, request_id='query-input-scope')[0]
    assert row['dataset_version_id'] == dataset.version_id and '查询结果' in answer
    result = row['result']
    assert result['query_result'] == 1 and result['rows'] == 2
    scope = result['analysis_scope']
    assert scope['kind'] == 'query_input' and scope['rows'] == 2
    assert '2026-01' in scope['period'] and '2026-03' not in scope['period']
    assert scope['units'] == [{'column': '金额（元）', 'unit': '元'}]


def test_explicit_update_preserves_resource_scope_and_checks_the_seen_version(scan_dirs):
    from app.agents.contracts import Principal
    from app.storage.datasets import DatasetRegistry, DatasetRowConflict
    tenant, _ = scan_dirs
    owner = Principal.from_user({'username': 'data-owner', 'role': 'manager', 'department': 'finance'})
    admin = Principal.from_user({'username': 'admin-updater', 'role': 'admin', 'department': ''})
    registry = DatasetRegistry(root=tenant)
    first = registry.register(_write_business_csv(tenant, 'finance.csv', 42), principal=owner, classification='2')
    path = registry.new_version_path('finance.csv')
    path.write_text('store,profit\nwest,84\n', encoding='utf-8')
    updated = registry.register(path, filename='finance.csv', principal=admin,
                                expected_version_id=first.version_id)
    assert updated.owner_id == first.owner_id and updated.department_ids == first.department_ids
    assert updated.classification == first.classification and updated.visibility == first.visibility
    version = registry.get_version(first.dataset_id, version_id=updated.version_id)
    assert version.owner_id == first.owner_id and version.metadata['registered_by'] == admin.user_id
    other_process = DatasetRegistry(root=tenant)
    with pytest.raises(DatasetRowConflict):
        other_process.register(path, filename='finance.csv', principal=admin,
                               expected_version_id=first.version_id)
    duplicate = other_process.register(path, filename='finance.csv', principal=admin,
                                       expected_version_id=updated.version_id)
    assert duplicate.version_id == updated.version_id
    assert len(registry.versions(first.dataset_id)) == 2


def test_simultaneous_updates_do_not_overwrite_a_newer_version(scan_dirs, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.agents.contracts import Principal
    from app.storage.datasets import DatasetRegistry, DatasetRowConflict
    tenant, _ = scan_dirs
    owner = Principal.from_user({'username': 'version-owner', 'role': 'manager', 'department': 'finance'})
    registry = DatasetRegistry(root=tenant)
    first = registry.register(_write_business_csv(tenant, 'finance.csv', 42), principal=owner)
    gate = Barrier(2)
    registries = [DatasetRegistry(root=tenant), DatasetRegistry(root=tenant)]
    for item in registries:
        original = item._next_version_number
        def simultaneous(dataset_id, original=original):
            number = original(dataset_id)
            gate.wait(timeout=10)
            return number
        monkeypatch.setattr(item, '_next_version_number', simultaneous)
    def update(index):
        target = registry.new_version_path('finance.csv')
        target.write_text(f'store,profit\nwest,{84 + index}\n', encoding='utf-8')
        try:
            return registries[index].register(target, principal=owner, filename='finance.csv',
                expected_version_id=first.version_id).version_id
        except DatasetRowConflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update, (0, 1)))
    assert results.count('conflict') == 1
    assert len(registry.versions(first.dataset_id)) == 2
    assert registry.get(first.dataset_id).version_id in results


def test_data_and_knowledge_publication_share_the_callers_transaction(scan_dirs, alert_pg):
    from app.agents.contracts import Principal
    from app.storage.datasets import DatasetRegistry, PostgresDatasetTableStore
    from app.documents.catalog import record_document_version
    tenant, _ = scan_dirs
    owner = Principal.from_user({'username': 'atomic-owner', 'role': 'manager', 'department': 'finance'})
    registry = DatasetRegistry(root=tenant)
    first = registry.register(_write_business_csv(tenant, 'atomic.csv', 42), principal=owner)
    path = registry.new_version_path('atomic.csv')
    path.write_text('store,profit\nwest,84\n', encoding='utf-8')
    with alert_pg() as connection:
        transactional = DatasetRegistry(root=tenant, store=PostgresDatasetTableStore(connection=connection))
        updated = transactional.register(path, principal=owner, filename='atomic.csv', expected_version_id=first.version_id)
        record_document_version('atomic.csv', 1, 'finance', str(path), owner_id=owner.user_id,
                                parse_status='ready', connection=connection)
        assert transactional.get(first.dataset_id).version_id == updated.version_id
        assert registry.get(first.dataset_id).version_id == first.version_id
        connection.rollback()
    assert registry.get(first.dataset_id).version_id == first.version_id
    with alert_pg() as connection:
        assert connection.execute("SELECT COUNT(*) AS n FROM document_versions WHERE filename='atomic.csv'").fetchone()['n'] == 0
    assert len(registry.versions(first.dataset_id)) == 1


def test_reused_draft_refuses_changed_data_before_starting_a_task(scan_dirs, monkeypatch):
    from app.agents.contracts import Principal
    from app.common import auth
    from app.storage import datasets
    from app.api.v1 import data
    from app.main import app
    tenant, _ = scan_dirs
    user = {'username': 'draft-owner', 'role': 'manager', 'department': 'finance'}
    registry = datasets.DatasetRegistry(root=tenant)
    first = registry.register(_write_business_csv(tenant, 'finance.csv', 42), principal=Principal.from_user(user))
    path = registry.new_version_path('finance.csv')
    path.write_text('store,profit\nwest,84\n', encoding='utf-8')
    registry.register(path, principal=Principal.from_user(user), filename='finance.csv')
    monkeypatch.setattr(data, 'dataset_registry', registry)
    monkeypatch.setattr(datasets, 'dataset_registry', registry)
    monkeypatch.setattr(auth, 'get_user', lambda name: {**user, 'username': name,
        'department': 'hr' if name == 'outsider' else 'finance'})
    payload = {'message': 'profit合计', 'data_filename': 'finance.csv', 'expected_data_version_id': first.version_id}
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post('/api/v1/ask', headers=_headers(user['username']), json=payload)
    assert response.status_code == 409 and response.json()['detail'] == 'dataset_version_changed'
    denied = client.post('/api/v1/ask', headers=_headers('outsider'), json=payload)
    assert denied.status_code == 403


def test_sweep_never_resolves_to_the_repository_data_folder(scan_dirs, monkeypatch):
    from app.api.v1 import alerts, data

    tenant, _ = scan_dirs
    monkeypatch.setattr(data, "DATA_DIR", str(tenant))

    resolved = alerts._tenant_data_root()

    assert resolved == tenant.resolve()
    assert resolved != (Path.cwd() / "data").resolve()
    source = Path("app/api/v1/alerts.py").read_text(encoding="utf-8")
    assert '"..", "..", "..", "data"' not in source


def test_sweep_only_evaluates_datasets_the_principal_may_analyze(scan_dirs, monkeypatch):
    from app.agents.contracts import Principal
    from app.api.v1 import alerts, data
    from app.storage import datasets as dataset_storage
    from app.storage.datasets import DatasetRegistry

    tenant, legacy = scan_dirs
    own_file = _write_business_csv(tenant, "finance-book.csv", 42.0)
    foreign_file = _write_business_csv(tenant, "hr-book.csv", 7.5)
    _write_business_csv(legacy, "repo-leftover.csv", 560.0)
    registry = DatasetRegistry(root=tenant, metadata_path=tenant / ".dataset-metadata.json")
    monkeypatch.setattr(dataset_storage, "dataset_registry", registry)
    monkeypatch.setattr(data, "DATA_DIR", str(tenant))
    _offline_rules(monkeypatch, [_rule()])
    finance = Principal.from_user(
        {"id": "u_finance", "username": "u_finance", "role": "manager", "department": "finance"}
    )
    hr = Principal.from_user(
        {"id": "u_hr", "username": "u_hr", "role": "manager", "department": "hr"}
    )
    registry.register(own_file, principal=finance, filename="finance-book.csv")
    registry.register(foreign_file, principal=hr, filename="hr-book.csv")

    summary: dict = {}
    triggered = alerts.evaluate_all(principal=finance, scan_summary=summary)

    assert summary["scoped_to_principal"] is True
    assert summary["evaluated_files"] == ["finance-book.csv"]
    assert [item["message"] for item in triggered] == ["profit-floor: profit=42 (gt 1)"]
    assert triggered[0]["evidence"]["current"] == 42.0

    hr_summary: dict = {}
    hr_triggered = alerts.evaluate_all(principal=hr, scan_summary=hr_summary)

    assert hr_summary["evaluated_files"] == ["hr-book.csv"]
    assert [item["message"] for item in hr_triggered] == ["profit-floor: profit=7.5 (gt 1)"]
    assert hr_triggered[0]["evidence"]["current"] == 7.5


def test_missing_tenant_data_dir_reports_no_data_without_falling_back(tmp_path, monkeypatch):
    from app.api.v1 import alerts, data

    missing = tmp_path / "tenant-data"
    assert not missing.exists()
    monkeypatch.setattr(data, "DATA_DIR", str(missing))
    recorded = _offline_rules(monkeypatch, [_rule()])

    summary: dict = {}
    triggered = alerts.evaluate_all(scan_summary=summary)

    assert triggered == []
    assert recorded == []
    assert summary == {
        "data_dir_configured": False,
        "scoped_to_principal": False,
        "evaluated_files": [],
        "reason": "tenant_data_dir_unavailable",
        "evaluation_failures": [], "ongoing": 0, "recovered": 0,
    }
    assert alerts._tenant_data_root() is None


def test_empty_data_dir_reports_no_data_files(scan_dirs, monkeypatch):
    from app.api.v1 import alerts, data

    tenant, _ = scan_dirs
    monkeypatch.setattr(data, "DATA_DIR", str(tenant))
    _offline_rules(monkeypatch, [_rule()])

    summary: dict = {}

    assert alerts.evaluate_all(scan_summary=summary) == []
    assert summary["data_dir_configured"] is True
    assert summary["reason"] == "no_data_files"
    assert summary["evaluated_files"] == []


def test_repeated_sweep_keeps_distinct_dataset_findings_without_duplicate_notifications(scan_dirs, monkeypatch, alert_pg):
    from app.api.v1 import alerts, data
    from app.agents.contracts import Principal
    from app.storage import datasets
    from app.storage.datasets import DatasetRegistry

    tenant, _ = scan_dirs
    owner = Principal.from_user({"id": "scope_owner", "username": "scope_owner",
        "role": "manager", "department": "finance"})
    registry = DatasetRegistry(root=tenant)
    for filename in ("east.csv", "west.csv"):
        registry.register(_write_business_csv(tenant, filename, 42), principal=owner)
    monkeypatch.setattr(datasets, "dataset_registry", registry)
    monkeypatch.setattr(data, "DATA_DIR", str(tenant))
    monkeypatch.setattr(alerts, "_database_available", lambda: True)
    monkeypatch.setattr(alerts, "_conn", alert_pg)
    monkeypatch.setattr(alerts, "_initialized", False)
    notifications = []
    monkeypatch.setattr(alerts, "send_im_notification", lambda *args, **kwargs: notifications.append(args))
    with alert_pg() as connection:
        connection.execute("INSERT INTO alert_rules (name,metric,op,threshold) VALUES ('profit-floor','profit','gt',1)")

    assert len(alerts.evaluate_all(principal=owner)) == 2
    summary = {}
    assert alerts.evaluate_all(principal=owner, scan_summary=summary) == []
    assert summary["ongoing"] == 2 and summary["evaluation_failures"] == []
    with alert_pg() as connection:
        rows = connection.execute("SELECT finding_key,evidence FROM alerts").fetchall()
        assert len(rows) == 2 and len({row["finding_key"] for row in rows}) == 2
        assert {row["evidence"]["filename"] for row in rows} == {"east.csv", "west.csv"}
        assert all(row["evidence"]["calculation_run_id"] for row in rows)
        assert connection.execute("SELECT COUNT(*) AS n FROM calculation_runs WHERE status='completed'").fetchone()["n"] == 4
    assert len(notifications) == 2


def test_one_sweep_appends_a_memory_alert_only_once(scan_dirs, monkeypatch):
    from app.api.v1 import alerts, data
    from app.agents.contracts import Principal
    from app.storage import datasets
    from app.storage.datasets import DatasetRegistry

    tenant, _ = scan_dirs
    owner = Principal.from_user({"id": "memory_owner", "username": "memory_owner",
        "role": "manager", "department": "finance"})
    registry = DatasetRegistry(root=tenant)
    registry.register(_write_business_csv(tenant, "east.csv", 42.0), principal=owner)
    monkeypatch.setattr(datasets, "dataset_registry", registry)
    monkeypatch.setattr(data, "DATA_DIR", str(tenant))
    recorded = _offline_rules(monkeypatch, [_rule()])
    notifications: list = []
    monkeypatch.setattr(
        alerts,
        "send_im_notification",
        lambda title, body, source="system", severity="info": notifications.append(body) or True,
    )

    triggered = alerts.evaluate_all(principal=owner)
    assert alerts.evaluate_all(principal=owner) == []

    assert len(triggered) == 1
    assert [alert["message"] for alert in recorded] == ["profit-floor: profit=42 (gt 1)"]
    assert recorded[0]["evidence"]["current"] == 42.0
    assert len(notifications) == 1, "a deduplicated finding must not notify twice"


def test_check_route_reports_the_scope_it_evaluated(scan_dirs, monkeypatch):
    from app.api.v1 import alerts, data
    from app.common import auth
    from app.main import app

    tenant, _ = scan_dirs
    monkeypatch.setattr(data, "DATA_DIR", str(tenant))
    _offline_rules(monkeypatch, [])
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": username,
            "username": username,
            "role": "manager",
            "department": "finance",
        },
    )

    response = TestClient(app).post("/api/v1/alerts/check", headers=_headers("finance-manager"))

    assert response.status_code == 200
    body = response.json()
    assert body["triggered"] == []
    assert body["scan_scope"]["data_dir_configured"] is True
    assert body["scan_scope"]["scoped_to_principal"] is True
    assert body["scan_scope"]["evaluated_files"] == []
    assert body["scan_scope"]["reason"] == "no_permitted_datasets"


@pytest.fixture
def versioned_alerts(scan_dirs, monkeypatch, alert_pg):
    from app.agents.contracts import Principal
    from app.api.v1 import alerts, data
    from app.common import auth
    from app.storage import datasets, calculations
    tenant, _ = scan_dirs
    user = {'id': 'version-owner', 'username': 'version-owner', 'role': 'manager', 'department': 'finance'}
    owner = Principal.from_user(user)
    registry = datasets.DatasetRegistry(root=tenant)
    first = registry.register(_write_business_csv(tenant, 'finance.csv', 42), principal=owner)
    monkeypatch.setattr(datasets, 'dataset_registry', registry)
    monkeypatch.setattr(calculations, 'dataset_registry', registry)
    monkeypatch.setattr(data, 'DATA_DIR', str(tenant))
    monkeypatch.setattr(alerts, '_database_available', lambda: True)
    monkeypatch.setattr(alerts, '_conn', alert_pg)
    monkeypatch.setattr(alerts, '_initialized', False)
    monkeypatch.setattr(auth, 'get_user', lambda name: user if name == user['username'] else None)
    monkeypatch.setattr(alerts, 'send_im_notification', lambda *args, **kwargs: None)
    return owner, registry, first


def _version_rule(owner, **options):
    import asyncio
    from starlette.requests import Request
    from app.api.v1.alerts import create_rule, RuleCreate
    request = Request({'type': 'http'})
    request.state.principal = owner
    return asyncio.run(create_rule(RuleCreate(name='version-check', metric='profit', op='gt', threshold=1,
        data_filename='finance.csv', **options), request))['id']


def test_fixed_and_following_alerts_keep_distinct_versions_after_update(versioned_alerts, alert_pg):
    from app.api.v1 import alerts
    owner, registry, first = versioned_alerts
    fixed_id = _version_rule(owner, version_policy='fixed')
    follow_id = _version_rule(owner, version_policy='follow_latest')
    initial = alerts.evaluate_all(principal=owner)
    assert len(initial) == 2
    replacement = registry.new_version_path('finance.csv')
    replacement.write_text('store,profit\nwest,84\n', encoding='utf-8')
    second = registry.register(replacement, filename='finance.csv', principal=owner)
    summary = {}
    assert alerts.evaluate_all(principal=owner, scan_summary=summary) == []
    with alert_pg() as connection:
        rows = {row['rule_id']: row for row in connection.execute('SELECT * FROM alerts').fetchall()}
    assert rows[fixed_id]['evidence']['version_id'] == first.version_id
    assert rows[fixed_id]['evidence']['current'] == 42
    assert rows[follow_id]['evidence']['version_id'] == second.version_id
    assert rows[follow_id]['evidence']['current'] == 84
    assert len(rows[fixed_id]['observations']) == 1 and len(rows[follow_id]['observations']) == 2
    Path(first.storage_path).unlink()
    unavailable = {}
    assert alerts.evaluate_all(principal=owner, scan_summary=unavailable) == []
    assert any('固定版本' in item['reason'] for item in unavailable['evaluation_failures'])
    assert unavailable['recovered'] == 0
    Path(second.storage_path).unlink()
    unavailable = {}
    assert alerts.evaluate_all(principal=owner, scan_summary=unavailable) == []
    assert any('固定版本' in item['reason'] for item in unavailable['evaluation_failures'])
    assert unavailable['recovered'] == 0


def test_selected_new_rule_defaults_to_fixed_and_invalid_policy_is_rejected(versioned_alerts, alert_pg):
    from fastapi import HTTPException
    owner, _, first = versioned_alerts
    ident = _version_rule(owner)
    with alert_pg() as connection:
        options = connection.execute('SELECT options FROM alert_rules WHERE id=%s', (ident,)).fetchone()['options']
    assert options['version_policy'] == 'fixed' and options['version_id'] == first.version_id
    with pytest.raises(HTTPException) as error:
        _version_rule(owner, version_policy='unknown')
    assert error.value.status_code == 400


def test_fixed_alert_analysis_reads_and_records_original_version(versioned_alerts):
    from app.agents import tools
    from app.agents.evidence import new_evidence_bag
    from app.storage import calculations
    owner, registry, first = versioned_alerts
    replacement = registry.new_version_path('finance.csv')
    replacement.write_text('store,profit\nwest,84\n', encoding='utf-8')
    registry.register(replacement, filename='finance.csv', principal=owner)
    bag = new_evidence_bag()
    config = {'configurable': {'principal': owner, 'data_filename': 'finance.csv',
        'thread_id': 'fixed-alert:data', 'request_id': 'fixed-alert-analysis', 'evidence_bag': bag,
        'data_context': {'filename': 'finance.csv', 'version_policy': 'fixed',
            'version_id': first.version_id, 'sha256': first.content_sha256}}}
    result = tools._analyze_data('profit合计', config)
    assert '42' in result and bag['datasets'][0]['version_id'] == first.version_id
    row = calculations.calculation_storage.list_for(owner, request_id='fixed-alert-analysis')[0]
    assert row['dataset_version_id'] == first.version_id and row['status'] == 'completed'


def test_scheduled_rule_refuses_an_owner_who_lost_alert_permission(versioned_alerts, monkeypatch):
    from app.api.v1 import alerts
    from app.common import auth
    owner, _, _ = versioned_alerts
    ident = _version_rule(owner)
    monkeypatch.setattr(auth, 'get_user', lambda name: {'id': owner.user_id, 'username': owner.username,
        'role': 'staff', 'department': 'finance'})
    summary = {}
    assert alerts.evaluate_all(scan_summary=summary, rule_ids=[ident]) == []
    assert any('权限' in item['reason'] for item in summary['evaluation_failures'])


def test_scheduled_scan_uses_registered_immutable_uploads_not_loose_root_files(versioned_alerts):
    import asyncio
    from starlette.requests import Request
    from app.api.v1 import alerts
    owner, registry, first = versioned_alerts
    registry.soft_delete(first.dataset_id)
    path = registry.new_version_path('monthly.csv')
    path.write_text('store,profit\nwest,42\n', encoding='utf-8')
    registry.register(path, filename='monthly.csv', principal=owner)
    (registry.root / 'unregistered.csv').write_text('profit\n9999\n', encoding='utf-8')
    request = Request({'type': 'http'})
    request.state.principal = owner
    ident = asyncio.run(alerts.create_rule(alerts.RuleCreate(name='scheduled-upload',
        metric='profit', op='gt', threshold=1, data_filename='monthly.csv'), request))['id']
    summary = {}
    rows = alerts.evaluate_all(rule_ids=[ident], scan_summary=summary)
    assert len(rows) == 1 and rows[0]['evidence']['current'] == 42
    assert summary['evaluated_files'] == ['monthly.csv']
    assert summary['evaluation_failures'] == []


def test_alert_trend_uses_calculated_series_without_model_business_claims(versioned_alerts, alert_pg, monkeypatch):
    from langchain_core.messages import HumanMessage
    from app.agents.orchestrator import _make_worker_wrapper
    from app.storage import artifacts
    from app.storage.persistence import PostgresPersistenceAdapter
    from app.tools import chart
    from PIL import Image
    owner, registry, _ = versioned_alerts
    path = registry.new_version_path('finance.csv')
    path.write_text('store,profit\neast,20\nwest,22\n', encoding='utf-8')
    record = registry.register(path, filename='finance.csv', principal=owner)
    output = registry.root / 'generated'
    output.mkdir()
    monkeypatch.setattr(chart, 'STATIC_DIR', str(output))
    store = artifacts.ArtifactRegistry(root=output, persistence=PostgresPersistenceAdapter(alert_pg))
    monkeypatch.setattr(artifacts, 'artifact_registry', store)
    class NoModel:
        def invoke(self, *args, **kwargs):
            raise AssertionError('A verified alert trend must not invent business claims')
    state = {'messages': [HumanMessage(content='按store汇总profit，生成趋势图。')],
        'data_filename': 'finance.csv', 'worker_results': {}, 'data_context': {
            'alert_id': 24, 'query': '按store汇总profit与记录数', 'filename': 'finance.csv',
            'version_policy': 'fixed', 'version_id': record.version_id, 'sha256': record.content_sha256}}
    result = _make_worker_wrapper(NoModel(), 'chart')(state, {'configurable': {
        'principal': owner, 'thread_id': 'alert-trend', 'request_id': 'alert-trend'}})
    assert result['agent_results']['chart']['status'] == 'success'
    assert '图表已生成' in result['worker_results']['chart']
    generated = store.list_active(owner_id=owner.user_id)
    assert len(generated) == 1 and generated[0].source_version_id == record.version_id
    with Image.open(generated[0].storage_path) as image:
        image.verify()


def test_fresh_scheduler_resolves_database_without_a_prior_login_import(alert_pg):
    import os
    import subprocess
    import sys
    from psycopg.conninfo import make_conninfo
    with alert_pg() as connection:
        info = connection.info
        dsn = make_conninfo(host=info.host, port=info.port, user=info.user,
            password=info.password, dbname=info.dbname)
    result = subprocess.run([sys.executable, '-c',
        'from app.api.v1.alerts import _database_available; print(_database_available())'],
        capture_output=True, text=True, env={**os.environ, 'DATABASE_URL': dsn,
            'APP_ENV': 'production', 'DEMO_ADMIN_PASSWORD': 'Isolated-test-only-42'})
    assert result.returncode == 0, 'Isolated scheduler database probe failed'
    assert result.stdout.strip().splitlines()[-1] == 'True'


@pytest.mark.parametrize('mixed', [False, True])
def test_unnumbered_worker_keeps_each_period_out_of_the_other_calculation(versioned_alerts, mixed):
    from langchain_core.messages import HumanMessage
    from app.agents.orchestrator import _make_worker_wrapper
    from app.storage.calculations import calculation_storage
    owner, registry, _ = versioned_alerts
    path = registry.new_version_path('finance.csv')
    path.write_text('月份,profit\n2026-01,100\n2026-02,200\n', encoding='utf-8')
    record = registry.register(path, filename='finance.csv', principal=owner)
    question = '2026-01的profit合计是多少？2026-02的profit合计是多少？不要生成图表或报告。'
    if mixed:
        question = '①制度要求多久提交凭证？②2026-01的profit合计是多少？③2026-02的profit合计是多少？④为什么金额增加？不要生成图表或报告。'
    class NoModel:
        def invoke(self, *args, **kwargs):
            raise AssertionError('Clear independent statistics must use actual calculations')
    state = {'messages': [HumanMessage(content=question)], 'worker_results': {},
        'data_filename': 'finance.csv', 'data_context': {'query': question,
            'version_id': record.version_id, 'sha256': record.content_sha256}}
    result = _make_worker_wrapper(NoModel(), 'data')(state, {'configurable': {
        'principal': owner, 'thread_id': 'unnumbered', 'request_id': 'unnumbered'}})
    assert result['agent_results']['data']['status'] == 'success'
    rows = calculation_storage.list_for(owner, request_id='unnumbered')
    assert len(rows) == 2 and all(r['status'] == 'completed' for r in rows)
    assert sorted(r['result']['numeric_statistics'][0]['sum'] for r in rows) == [100, 200]
    assert all(r['result']['rows'] == 1 for r in rows)
    if mixed:
        assert all('制度' not in r['parameters']['query'] and '原因' not in r['parameters']['query'] for r in rows)
        assert '不能单凭金额确认业务原因' in result['worker_results']['data']


@pytest.mark.parametrize('missing_metric', [False, True, 'missing_chart', 'preserved_body', 'joint_review', 'ambiguous_count', 'separate', 'separate_fail', 'query', 'separate_query', 'missing_query', 'failed_query'])
def test_combined_period_report_revalidates_each_scope_without_a_full_table_substitute(
        versioned_alerts, alert_pg, monkeypatch, tmp_path, missing_metric):
    from pypdf import PdfReader
    from app.agents.tools import export_report
    from app.agents.evidence import new_evidence_bag
    from app.storage import artifacts
    from app.storage.persistence import PostgresPersistenceAdapter
    from app.storage.calculations import calculation_storage
    from app.tools import export
    from app.storage import datasets, calculations
    from app.api.v1 import data
    owner, _, _ = versioned_alerts
    inputs = tmp_path / 'combined-inputs'
    inputs.mkdir()
    registry = datasets.DatasetRegistry(root=inputs,
        store=datasets.PostgresDatasetTableStore(connection_factory=alert_pg))
    monkeypatch.setattr(datasets, 'dataset_registry', registry)
    monkeypatch.setattr(calculations, 'dataset_registry', registry)
    monkeypatch.setattr(data, 'DATA_DIR', str(inputs))
    path = registry.new_version_path('finance.csv')
    path.write_text('月份,金额（元）\n2026-01,100\n2026-01,300\n2026-02,200\n2026-02,600\n2026-03,300\n2026-03,900\n', encoding='utf-8')
    record = registry.register(path, filename='finance.csv', principal=owner)
    output = tmp_path / 'combined-reports'
    output.mkdir()
    monkeypatch.setattr(export, 'EXPORT_DIR', str(output))
    store = artifacts.ArtifactRegistry(root=output, persistence=PostgresPersistenceAdapter(alert_pg))
    monkeypatch.setattr(artifacts, 'artifact_registry', store)
    last = '预算金额合计' if missing_metric is True else '金额（元）平均值'
    question = f'①2026-01金额（元）合计是多少？②2026-02金额（元）合计是多少？③2026-03{last}是多少？不要生成图表，请把以上三项结果合并成一份PDF报告。'
    if missing_metric == 'missing_chart':
        question = question.replace('不要生成图表，', '').replace('一份PDF', '一份带图PDF')
    if missing_metric == 'ambiguous_count':
        question = question.replace('请把以上三项结果合并成一份PDF报告', '请生成PDF报告')
    if missing_metric in ('separate', 'separate_fail', 'separate_query'):
        question = question.replace('请把以上三项结果合并成一份PDF报告', '请分别生成三份PDF报告')
    if missing_metric == 'separate_fail':
        generate = export.generate_pdf_report
        calls = []
        def failed_second(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise OSError('Synthetic second PDF write failure')
            return generate(*args, **kwargs)
        monkeypatch.setattr(export, 'generate_pdf_report', failed_second)
    run_id = 'combined-report-' + str(missing_metric)
    conf = {'principal': owner, 'thread_id': run_id,
            'request_id': run_id, 'data_filename': 'finance.csv', 'data_question': question,
            'data_context': {'query': question, 'version_id': record.version_id, 'sha256': record.content_sha256},
            'evidence_bag': new_evidence_bag()}
    query_case = missing_metric in ('query', 'separate_query', 'missing_query', 'failed_query')
    if query_case:
        from app.agents.tools import _start_calculation, _finish_calculation
        from app.agents.task_review import question_items
        question = question.replace('2026-02金额（元）合计是多少', '2026-02金额（元）中位数乘3是多少')
        conf['data_question'] = question
        conf['data_context']['query'] = question
        if missing_metric != 'missing_query':
            item = question_items(question)[1][1]
            query_conf = {'configurable': {**conf, 'data_question': item}}
            calculation_id = _start_calculation(query_conf, 'finance.csv', item, operation='query_data')
            _finish_calculation(calculation_id, {'rows': 2, 'query_result': 1200.0,
                'expression': "df['金额（元）'].median() * 3",
                'analysis_scope': {'period': '2026-02', 'filter': '未指定分类筛选'}})
            from langchain_core.messages import HumanMessage
            from app.agents import tools
            from app.agents.orchestrator import _make_worker_wrapper
            attempts = []
            def generated(frame, query):
                attempts.append(query)
                if len(attempts) == 1 or missing_metric == 'failed_query':
                    return "df[df['月份'] == '2026-02' & df['金额（元）'] > 0]['金额（元）'].median() * 3"
                return "df['金额（元）'].median() * 3"
            monkeypatch.setattr(tools, '_llm_pandas_code', generated)
            class NoModel:
                def invoke(self, *args, **kwargs):
                    raise AssertionError('Independent questions must use actual data tools')
            response = _make_worker_wrapper(NoModel(), 'data')({'messages': [HumanMessage(content=question)],
                'data_filename': 'finance.csv', 'data_context': conf['data_context'],
                'worker_results': {}}, {'configurable': conf})
            if missing_metric == 'failed_query':
                assert response['agent_results']['data']['status'] in ('partial', 'failed')
                assert '未能计算' in response['worker_results']['data']
                assert '400.00' in response['worker_results']['data'] and '600.00' in response['worker_results']['data']
                assert not store.list_active(owner_id=owner.user_id)
                return
            assert '1200' in response['worker_results']['data'] and '查询结果' in response['worker_results']['data']
            assert len(attempts) == 2 and '执行错误' in attempts[1]
    if missing_metric == 'preserved_body':
        import pandas as pd
        from app.agents.tools import _report_data_facts, _verified_data_answer
        from app.tools.excel import filter_explicit_categories
        frame = pd.read_csv(path)
        parts = []
        for marker, month in zip('①②③', ['2026-01', '2026-02', '2026-03']):
            item = month + ('金额（元）平均值是多少？' if month == '2026-03' else '金额（元）合计是多少？')
            facts = _report_data_facts('finance.csv', filter_explicit_categories(frame, item), item, version_id=record.version_id)
            parts.append(f'{marker} {item}\n\n'+_verified_data_answer([facts], question=item))
        conf['report_body'] = '\n\n'.join(parts) + '\n\n保留限制：不能据此判断增长原因。'
    if missing_metric == 'joint_review':
        conf['task_context'] = {'analysis_question': question, 'version_id': record.version_id}
    result = export_report.invoke({'report_title': '合成验收多问题', 'sections_json': '[]'}, config={'configurable': conf})
    generated = store.list_active(owner_id=owner.user_id)
    if missing_metric == 'missing_query':
        assert not generated and '查询计算' in result
        return
    if missing_metric == 'separate_fail':
        assert not generated and '已撤下本轮部分文件' in result
        return
    if missing_metric == 'missing_chart':
        assert not generated and '图表尚未成功生成' in result
        return
    if missing_metric == 'joint_review':
        assert not generated and '制度适用范围' in result
        return
    if missing_metric == 'ambiguous_count':
        assert not generated and '报告形式尚未明确' in result
        return
    if missing_metric is True:
        assert not generated and '③' in result and '预算' in result
        return
    if missing_metric in ('separate', 'separate_query'):
        assert len(generated) == 3, result
        rows = calculation_storage.list_for(owner, request_id=run_id)
        for report in generated:
            pages = PdfReader(report.storage_path).pages
            assert len(pages) == 1, 'A short per-question result should not get a separate cover'
            text = '\n'.join(p.extract_text() for p in pages)
            month = next(m for m in ('2026-01', '2026-02', '2026-03') if m in text)
            assert all(m not in text for m in ('2026-01', '2026-02', '2026-03') if m != month)
            assert {'2026-01': '400.00', '2026-02': '1200.0' if query_case else '800.00', '2026-03': '600.00'}[month] in text
            linked = [r for r in rows if r['calculation_run_id'] in report.metadata['calculation_run_ids']]
            assert linked and all(month in r['result']['analysis_scope']['period'] for r in linked)
            assert report.metadata['report_part_key']
            assert 'SHA-256' in text
            assert text.count('SHA-256') == 1, 'One input version should have one digest in a per-question report'
            if missing_metric == 'separate_query' and month == '2026-02':
                assert '中位数乘3' in text and '查询结果' in text and '800.0' not in text
                assert any(r['parameters']['operation'] == 'query_data' for r in linked)
        repeated = export_report.invoke({'report_title': '合成验收多问题', 'sections_json': '[]'}, config={'configurable': conf})
        assert {r.artifact_id for r in store.list_active(owner_id=owner.user_id)} == {r.artifact_id for r in generated}, repeated
        return
    assert len(generated) == 1, result
    pages = PdfReader(generated[0].storage_path).pages
    assert len(pages) <= 2 and ('①' if missing_metric == 'preserved_body' else '第1项') in pages[0].extract_text()
    if missing_metric is False:
        assert '第3项' not in pages[0].extract_text() and '第3项' in pages[-1].extract_text()
    text = '\n'.join(page.extract_text() for page in pages)
    assert all(value in text for value in ['2026-01', '2026-02', '2026-03', '400.00', '1200.0' if query_case else '800.00', '600.00'])
    assert record.version_id in ''.join(text.split())
    assert '2,400.00' not in text
    if missing_metric == 'preserved_body':
        assert '保留限制：不能据此判断增长原因' in text
        assert '③' not in pages[0].extract_text() and '③' in pages[-1].extract_text()
    rows = calculation_storage.list_for(owner, request_id=run_id)
    if missing_metric == 'query':
        assert '中位数乘3' in text and '查询结果' in text and '800.0' not in text
        assert any(r['parameters']['operation'] == 'query_data' and r['result'].get('query_result') == 1200
                   for r in rows if r['calculation_run_id'] in generated[0].metadata['calculation_run_ids'])
    else:
        assert len(rows) == 3 and all(r['status'] == 'completed' and r['result']['rows'] == 2 for r in rows)
        assert len(generated[0].metadata['calculation_run_ids']) == 3
