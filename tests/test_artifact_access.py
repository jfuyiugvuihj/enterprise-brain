from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _user(username: str, department: str = "finance") -> dict[str, str]:
    return {
        "id": username,
        "username": username,
        "role": "manager",
        "department": department,
    }


def _registry(monkeypatch, tmp_path):
    from app.storage import artifacts
    from app.storage.artifacts import ArtifactRegistry

    registry = ArtifactRegistry(
        root=tmp_path,
        metadata_path=tmp_path / "artifact-metadata.json",
    )
    monkeypatch.setattr(artifacts, "artifact_registry", registry)
    return registry


def test_artifact_content_and_download_are_limited_to_the_registered_scope(monkeypatch, tmp_path):
    from app.agents.contracts import Principal
    from app.common import auth
    from app.main import app

    registry = _registry(monkeypatch, tmp_path)
    artifact_file = tmp_path / "finance-chart.png"
    artifact_file.write_bytes(b"chart-content")
    owner = Principal.from_user(_user("finance-manager"))
    artifact = registry.register(
        artifact_file,
        artifact_type="chart",
        principal=owner,
    )
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: _user(username, "hr" if username == "hr-manager" else "finance"),
    )

    client = TestClient(app)

    assert client.get(
        f"/api/v1/artifacts/{artifact.artifact_id}/content",
        headers=_headers("finance-manager"),
    ).status_code == 200
    assert client.get(
        f"/api/v1/artifacts/{artifact.artifact_id}/download",
        headers=_headers("finance-manager"),
    ).status_code == 200
    assert client.get(
        f"/api/v1/artifacts/{artifact.artifact_id}/content",
        headers=_headers("hr-manager"),
    ).status_code == 403
    assert client.get(
        f"/api/v1/artifacts/{artifact.artifact_id}/download",
        headers=_headers("hr-manager"),
    ).status_code == 403


def test_artifact_rejects_expired_or_deleted_records(monkeypatch, tmp_path):
    from app.agents.contracts import Principal
    from app.common import auth
    from app.main import app

    registry = _registry(monkeypatch, tmp_path)
    artifact_file = tmp_path / "report.pdf"
    artifact_file.write_bytes(b"%PDF-1.4")
    owner = Principal.from_user(_user("finance-manager"))
    expired = registry.register(
        artifact_file,
        artifact_type="report",
        principal=owner,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    active = registry.register(
        artifact_file,
        artifact_type="report",
        principal=owner,
    )
    registry.soft_delete(active.artifact_id)
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username))

    client = TestClient(app)

    assert client.get(
        f"/api/v1/artifacts/{expired.artifact_id}/content",
        headers=_headers("finance-manager"),
    ).status_code == 404
    assert client.get(
        f"/api/v1/artifacts/{active.artifact_id}/download",
        headers=_headers("finance-manager"),
    ).status_code == 404


def test_chart_generation_returns_a_controlled_artifact_url(monkeypatch, tmp_path):
    from app.api.v1 import data
    from app.common import auth
    from app.main import app

    _registry(monkeypatch, tmp_path)
    generated = tmp_path / "generated-chart.png"
    generated.write_bytes(b"chart-content")
    monkeypatch.setattr(data, "bar_chart", lambda labels, values, title: str(generated))
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username))

    response = TestClient(app).post(
        "/api/v1/chart",
        headers=_headers("finance-manager"),
        json={"type": "bar", "labels": ["A"], "values": [1], "title": "Revenue"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["error"] is None
    assert body["path"].startswith("/api/v1/artifacts/")
    assert body["path"].endswith("/content")
    assert body["download_url"].endswith("/download")


def test_chart_generation_rejects_a_principal_without_analyze_permission(monkeypatch, tmp_path):
    from app.api.v1 import data
    from app.common import auth
    from app.main import app

    _registry(monkeypatch, tmp_path)
    generated = {"called": False}

    def fake_chart(*args, **kwargs):
        generated["called"] = True
        raise AssertionError("chart generation must not run without analyze permission")

    monkeypatch.setattr(data, "bar_chart", fake_chart)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": username,
            "username": username,
            "role": "auditor",
            "department": "finance",
        },
    )

    response = TestClient(app).post(
        "/api/v1/chart",
        headers=_headers("finance-auditor"),
        json={"type": "bar", "labels": ["A"], "values": [1], "title": "Revenue"},
    )

    assert response.status_code == 403
    assert not generated["called"]


def test_static_chart_and_export_paths_do_not_bypass_artifact_authorization(monkeypatch):
    import asyncio

    from app.main import StaticFilesWithoutGeneratedArtifacts

    static_files = StaticFilesWithoutGeneratedArtifacts(directory="static")

    assert asyncio.run(static_files.get_response("charts/known-chart.png", {})).status_code == 404
    assert asyncio.run(static_files.get_response("exports/known-report.pdf", {})).status_code == 404
