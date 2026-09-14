import asyncio
from pathlib import Path

from fastapi import Request
from starlette.responses import Response


def test_jwt_secret_rotation_updates_env_file(tmp_path):
    from app.common.secret_rotation import rotate_jwt_secret

    env_file = tmp_path / ".env"
    env_file.write_text("JWT_SECRET_KEY=old\nAPP_NAME=brain\n", encoding="utf-8")

    new_secret = rotate_jwt_secret(env_file)

    content = env_file.read_text(encoding="utf-8")
    assert new_secret in content
    assert "JWT_SECRET_KEY=old" not in content
    assert "APP_NAME=brain" in content


def test_health_snapshot_reports_disk_and_request_metrics(monkeypatch):
    from app.common.monitoring import build_health_snapshot

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    snapshot = build_health_snapshot({"count": 2, "p95_ms": 120})

    assert snapshot["status"] == "ok"
    assert snapshot["performance"]["p95_ms"] == 120
    assert snapshot["disk"]["free_bytes"] >= 0
    assert snapshot["model"]["base_url"].startswith("http://")
    assert set(snapshot["dependencies"]) == {"ollama", "postgres", "redis"}


def test_health_dependency_probes_fail_closed_without_configuration(monkeypatch):
    from app.common.monitoring import build_health_snapshot

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr("app.common.monitoring._probe_ollama", lambda: {"status": "unavailable"})

    snapshot = build_health_snapshot()

    assert snapshot["dependencies"]["postgres"]["status"] == "not_configured"
    assert snapshot["dependencies"]["redis"]["status"] == "not_configured"
    assert snapshot["dependencies"]["ollama"]["status"] == "unavailable"


def test_detailed_health_requires_authentication():
    from fastapi.testclient import TestClient

    from app.common.auth import create_token
    from app.main import app

    client = TestClient(app)
    assert client.get("/api/v1/health/details").status_code == 401
    response = client.get(
        "/api/v1/health/details",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
    )
    assert response.status_code == 200
    assert "performance" in response.json()


def test_auth_middleware_injects_a_principal_and_rejects_unknown_token_subject(monkeypatch):
    from app.common import auth
    from app.common.auth import create_token
    from app.main import AuthMiddleware, app

    def request_for(username: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/health/details",
                "headers": [(b"authorization", f"Bearer {create_token(username)}".encode())],
            }
        )

    observed = {}

    async def accept(request):
        observed["principal"] = request.state.principal
        return Response(status_code=204)

    response = asyncio.run(AuthMiddleware(app).dispatch(request_for("admin"), accept))

    assert response.status_code == 204
    assert observed["principal"].username == "admin"
    assert observed["principal"].user_id

    monkeypatch.setattr(auth, "get_user", lambda username: None)
    rejected = asyncio.run(AuthMiddleware(app).dispatch(request_for("unknown"), accept))
    assert rejected.status_code == 401


def test_static_files_require_authentication():
    from fastapi.testclient import TestClient

    from app.common.auth import create_token
    from app.main import app

    client = TestClient(app)

    assert client.get("/static/not-present.txt").status_code == 401
    assert client.get(
        "/static/not-present.txt",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
    ).status_code == 404


def test_auth_middleware_does_not_bypass_unknown_open_platform_paths():
    from app.main import AuthMiddleware, app

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/open/not-registered",
            "headers": [],
        }
    )

    async def accept(request):
        return Response(status_code=204)

    response = asyncio.run(AuthMiddleware(app).dispatch(request, accept))

    assert response.status_code == 401


def test_audit_sanitizer_redacts_nested_secrets():
    from app.common.tracing import sanitize_trace_event

    cleaned = sanitize_trace_event(
        {"request": {"token": "secret", "message": "safe"}, "items": [{"password": "x"}]}
    )

    assert cleaned["request"]["token"] == "[REDACTED]"
    assert cleaned["request"]["message"] == "safe"
    assert cleaned["items"][0]["password"] == "[REDACTED]"
