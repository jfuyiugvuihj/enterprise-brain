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
def test_denied_authorization_chain_is_replayable_after_a_restart(tmp_path, monkeypatch):
    """The S1 403 chain must survive a restart, which is the point of P1-5."""
    import json

    import pytest

    from app.common.audit import AUDIT_COLLECTION, get_audit_events, reset_audit_storage
    from app.common.authorization import authorize
    from app.common.identity import Principal
    from app.common.permissions import ACTION_DELETE

    journal = tmp_path / "persistence.json"
    monkeypatch.setenv("PERSISTENCE_BACKEND", "json")
    monkeypatch.setenv("PERSISTENCE_FALLBACK_PATH", str(journal))
    monkeypatch.delenv("AUDIT_PERSISTENCE", raising=False)
    reset_audit_storage()
    try:
        staff = Principal.from_user(
            {"id": 9, "username": "probe-staff", "role": "staff", "department": "finance"}
        )
        staff.request_id = "req-403-chain"

        with pytest.raises(PermissionError):
            authorize(staff, ACTION_DELETE)

        assert get_audit_events()[-1]["outcome"] == "denied"

        # A restart starts with an empty process list; the journal must not be empty.
        reset_audit_storage()
        replayed = get_audit_events()

        assert [event["outcome"] for event in replayed] == ["denied"]
        assert replayed[0]["reason"] == "permission_denied"
        assert replayed[0]["action"] == ACTION_DELETE
        assert replayed[0]["request_id"] == "req-403-chain"
        assert replayed[0]["policy_version"] == "resource-policy-v2"
        assert replayed[0]["persisted"] is True
        stored = json.loads(journal.read_text(encoding="utf-8"))
        assert list(stored[AUDIT_COLLECTION])[0] == replayed[0]["event_id"]
    finally:
        reset_audit_storage()


def test_audit_storage_status_reports_durability_without_faking_it(tmp_path, monkeypatch):
    from app.common.audit import audit_storage_status, record_audit, reset_audit_storage
    from app.common.identity import Principal

    monkeypatch.setenv("PERSISTENCE_BACKEND", "json")
    monkeypatch.setenv("PERSISTENCE_FALLBACK_PATH", str(tmp_path / "persistence.json"))
    monkeypatch.delenv("AUDIT_PERSISTENCE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_audit_storage()
    try:
        principal = Principal.from_user({"id": 3, "username": "ops", "role": "admin"})
        record_audit(principal, "resource:view", "allowed", "doc-1", "permission_granted")

        status = audit_storage_status()

        assert status["mode"] == "json"
        assert status["durable"] is True
        assert status["degraded"] is False
        assert status["health"] == "ok"
        assert status["last_error"] == ""
        assert status["view_complete"] is True
        assert status["write_failures"] == 0
        assert status["collection"] == "audit_events"
        assert status["migration"] == "0005_audit_events"
        assert status["in_memory_events"] == 1

        monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
        reset_audit_storage()
        degraded = audit_storage_status()

        assert degraded["durable"] is False
        assert degraded["degraded"] is True
        assert degraded["health"] == "backend_unavailable"
        assert degraded["mode"] == "memory_only"
        assert "DATABASE_URL" in degraded["degraded_reason"]
    finally:
        reset_audit_storage()


def test_audit_events_migration_is_manifest_verified():
    import hashlib
    import json

    from app.db.migrations import MIGRATIONS, migration_plan

    directory = Path(__file__).resolve().parents[1] / "migrations"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    migration = next(item for item in MIGRATIONS if item.name == "audit_events")
    filename = f"{migration.version}_{migration.name}.sql"

    assert manifest[filename] == migration.checksum
    assert (
        hashlib.sha256((directory / filename).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        == manifest[filename]
    )
    assert "CREATE TABLE IF NOT EXISTS audit_events" in migration.sql

    pending = [item.version for item in migration_plan({})]

    assert "0005" in pending
    assert pending == sorted(pending)
