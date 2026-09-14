"""Alert sweep scope (P1-3) and per-sweep idempotency (E1-11).

The sweep used to read ``<repo>/data`` through a hardcoded ``../../../data``
join, so a tenant's own DATA_DIR was never evaluated while leftover files in
the repository folder were analyzed as if they belonged to whoever pressed
"check now". These tests keep both halves fixed, offline.
"""
import shutil
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


class _FakeAlertConnection:
    def __init__(self, rules: list[dict]):
        self.rules = rules
        self.executed: list[tuple] = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    def fetchall(self):
        return [dict(rule) for rule in self.rules]

    def commit(self):
        self.commits += 1


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

    tenant, legacy = scan_dirs
    _write_business_csv(tenant, "east.csv", 42.0)
    # The value the audit saw coming out of the repository folder.
    _write_business_csv(legacy, "qa_ascii_leftover.csv", 560.0)
    (legacy / "not_business.txt").write_text("ignore me", encoding="utf-8")
    monkeypatch.setattr(data, "DATA_DIR", str(tenant))
    _offline_rules(monkeypatch, [_rule()])

    summary: dict = {}
    triggered = alerts.evaluate_all(scan_summary=summary)

    assert summary["data_dir_configured"] is True
    assert summary["evaluated_files"] == ["east.csv"]
    assert [item["message"] for item in triggered] == ["profit-floor: profit=42.0 (gt 1.0)"]
    assert not any("560.0" in item["message"] for item in triggered)
    # DATA_DIR is what decides the scope, in both directions.
    monkeypatch.setattr(data, "DATA_DIR", str(legacy))
    relocated = alerts.evaluate_all()

    assert [item["message"] for item in relocated] == ["profit-floor: profit=560.0 (gt 1.0)"]


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
    assert [item["message"] for item in triggered] == ["profit-floor: profit=42.0 (gt 1.0)"]

    hr_summary: dict = {}
    hr_triggered = alerts.evaluate_all(principal=hr, scan_summary=hr_summary)

    assert hr_summary["evaluated_files"] == ["hr-book.csv"]
    assert [item["message"] for item in hr_triggered] == ["profit-floor: profit=7.5 (gt 1.0)"]


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


def test_one_sweep_inserts_a_rule_only_once(scan_dirs, monkeypatch):
    from app.api.v1 import alerts, data

    tenant, _ = scan_dirs
    # Two datasets that produce the identical finding, as in the audit evidence.
    _write_business_csv(tenant, "east.csv", 42.0)
    _write_business_csv(tenant, "west.csv", 42.0)
    monkeypatch.setattr(data, "DATA_DIR", str(tenant))
    connection = _FakeAlertConnection([_rule()])
    monkeypatch.setattr(alerts, "_database_available", lambda: True)
    monkeypatch.setattr(alerts, "_ensure", lambda: None)
    monkeypatch.setattr(alerts, "_conn", lambda: connection)
    analyzed: list = []

    def analysis(rule, value):
        analyzed.append((rule["id"], value))
        return "offline analysis"

    monkeypatch.setattr(alerts, "_ai_analysis", analysis)

    triggered = alerts.evaluate_all()

    inserts = [params for sql, params in connection.executed if "INSERT INTO alerts" in sql]
    assert len(inserts) == 1
    assert inserts[0][0] == 1
    assert inserts[0][1] == "profit-floor: profit=42.0 (gt 1.0)"
    assert len(triggered) == 1
    assert analyzed == [(1, 42.0)], "the duplicate must not even reach the model"
    assert connection.commits == 1


def test_one_sweep_appends_a_memory_alert_only_once(scan_dirs, monkeypatch):
    from app.api.v1 import alerts, data

    tenant, _ = scan_dirs
    _write_business_csv(tenant, "east.csv", 42.0)
    _write_business_csv(tenant, "west.csv", 42.0)
    monkeypatch.setattr(data, "DATA_DIR", str(tenant))
    recorded = _offline_rules(monkeypatch, [_rule()])
    notifications: list = []
    monkeypatch.setattr(
        alerts,
        "send_im_notification",
        lambda title, body, source="system", severity="info": notifications.append(body) or True,
    )

    triggered = alerts.evaluate_all()

    assert len(triggered) == 1
    assert [alert["message"] for alert in recorded] == ["profit-floor: profit=42.0 (gt 1.0)"]
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