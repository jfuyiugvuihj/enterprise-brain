from fastapi.testclient import TestClient

from app.common.auth import create_token
from app.main import app


def test_staff_cannot_manage_alert_rules(monkeypatch):
    from app.common import auth

    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "username": username,
            "role": "staff",
            "department": "finance",
        },
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/alerts/rules",
        headers={"Authorization": f"Bearer {create_token('alice')}"},
        json={"name": "Revenue drop", "metric": "revenue", "op": "lt", "threshold": 10},
    )

    assert response.status_code == 403


def test_manager_can_manage_alert_rules(monkeypatch):
    from app.api.v1 import alerts
    from app.common import auth

    alerts._MEM_RULES.clear()
    monkeypatch.setattr(alerts, "_database_available", lambda: False)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "username": username,
            "role": "manager",
            "department": "finance",
        },
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/alerts/rules",
        headers={"Authorization": f"Bearer {create_token('manager')}"},
        json={"name": "Revenue drop", "metric": "revenue", "op": "lt", "threshold": 10},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
