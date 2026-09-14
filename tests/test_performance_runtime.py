import asyncio
import json


def test_performance_stats_calculates_p95_and_error_rate():
    from app.common.performance import PerformanceStats

    stats = PerformanceStats()
    for value in [100, 120, 180, 240, 500]:
        stats.observe(value)
    stats.observe(300, error=True)

    report = stats.report()

    assert report["count"] == 6
    assert report["p95_ms"] == 500
    assert report["error_rate"] == 1 / 6


def test_request_budget_reports_timeout():
    from app.common.performance import RequestBudget

    budget = RequestBudget(timeout_seconds=0.01)
    assert budget.expired() is False
    asyncio.run(asyncio.sleep(0.02))
    assert budget.expired() is True


def _bind_session(chat_module, monkeypatch, tmp_path, session_id: str, username: str):
    """Register the fixture session for the caller the way POST /ask would."""
    from app.common import auth
    from app.common.identity import Principal
    from app.storage import sessions as sessions_module

    user = auth.get_user(username)
    assert user, f"the test subject {username} must resolve to a user"
    registry = sessions_module.SessionRegistry(tmp_path / "session-registry.json")
    registry.bind(session_id, Principal.from_user(user))
    monkeypatch.setattr(chat_module, "session_registry", registry)
    return registry

def test_sse_helpers_emit_heartbeat_and_cancel_route(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.common.auth import create_token
    from app.main import app
    from app.api.v1 import chat

    _bind_session(chat, monkeypatch, tmp_path, "perf-session", "admin")
    chat.register_request("perf-session")
    response = TestClient(app).post(
        "/api/v1/ask/perf-session/cancel",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
    )

    assert response.status_code == 200
    assert response.json()["cancelled"] is True
    assert chat.is_request_cancelled("perf-session") is True

    event = chat.sse_event("heartbeat", {"type": "heartbeat"})
    assert event.startswith("event: heartbeat\n")
    assert json.loads(event.split("data: ", 1)[1].split("\n", 1)[0])["type"] == "heartbeat"


def test_ask_stream_emits_hard_timeout(monkeypatch):
    import time

    from fastapi.testclient import TestClient
    from app.common.auth import create_token
    from app.main import app

    def slow_stream(*args, **kwargs):
        time.sleep(0.05)
        yield {"messages": []}

    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", slow_stream)
    monkeypatch.setenv("CHAT_REQUEST_TIMEOUT", "0.01")

    response = TestClient(app).post(
        "/api/v1/ask",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
        json={"message": "慢请求测试", "session_id": "hard-timeout-test"},
    )

    assert response.status_code == 200
    assert "请求超过系统处理时限" in response.text
