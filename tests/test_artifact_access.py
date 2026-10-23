from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient


def test_historical_policy_report_requires_both_original_and_current_scope(monkeypatch, tmp_path):
    from app.agents.contracts import Principal
    from app.documents import catalog
    from app.rag import indexing
    from app.storage.artifacts import ArtifactRegistry, artifact_sources_allowed
    from types import SimpleNamespace
    principal = Principal.from_user(_user('finance-manager'))
    registry = ArtifactRegistry(root=tmp_path)
    path = tmp_path / 'historical.pdf'
    path.write_bytes(b'old report')
    report = registry.register(path, artifact_type='report', principal=principal,
        source_documents=[{'source_name': '报销办法.pdf', 'version_id': '1', 'index_version_id': 'old-index'}])
    assert report.metadata.get('source_documents')
    current = {'filename': '报销办法.pdf', 'version': 2, 'department': 'finance', 'classification': 1}
    old = dict(current, version=1)
    monkeypatch.setattr(catalog, 'current_documents', lambda: [current])
    monkeypatch.setattr(catalog, 'list_document_versions', lambda name: [current, old])
    monkeypatch.setattr(indexing, 'read_index_metadata', lambda *a: ([SimpleNamespace(
        index_version_id='old-index', index_id=indexing.document_index_id('报销办法.pdf'), status='superseded')], {}))
    assert artifact_sources_allowed(report, principal)
    current['department'] = 'sales'
    assert not artifact_sources_allowed(report, principal)
    current['department'] = 'finance'
    old['department'] = 'sales'
    assert not artifact_sources_allowed(report, principal)


def test_chart_embedding_rechecks_current_artifact_permission(monkeypatch, tmp_path):
    from app.agents.contracts import Principal
    from app.agents.tools import _round_chart_paths
    from app.documents import catalog
    registry = _registry(monkeypatch, tmp_path)
    path = tmp_path / 'old.png'
    path.write_bytes(b'old chart')
    owner = Principal.from_user(_user('finance-manager'))
    registry.register(path, artifact_type='chart', principal=owner, session_id='task:chart',
        source_documents=[{'source_name': '制度.pdf', 'version_id': '1', 'index_version_id': 'idx'}])
    monkeypatch.setattr(catalog, 'current_documents', lambda: [{
        'filename': '制度.pdf', 'version': 1, 'department': 'finance', 'classification': 1}])
    changed = Principal.from_user(_user('finance-manager', 'sales'))
    assert _round_chart_paths({'configurable': {'thread_id': 'task:export'}}, changed) == []


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


def test_short_lived_attachment_rechecks_current_permissions(monkeypatch, tmp_path):
    from app.agents.contracts import Principal
    from app.api.v1 import artifacts as artifact_api
    from app.common import auth
    from app.common.cache import _MemoryRedis
    from app.main import app

    registry = _registry(monkeypatch, tmp_path)
    path = tmp_path / "report.pdf"
    path.write_bytes(b"%PDF-1.4\nreview")
    artifact = registry.register(path, artifact_type="report", principal=Principal.from_user(_user("owner")))
    users = {"owner": _user("owner"), "viewer": _user("viewer")}
    monkeypatch.setattr(auth, "get_user", lambda username: users.get(username))
    store = _MemoryRedis()
    monkeypatch.setattr(artifact_api, "_ticket_store", lambda: store)
    client = TestClient(app)

    issued = client.post(f"/api/v1/artifacts/{artifact.artifact_id}/download-link", headers=_headers("viewer"))
    assert issued.status_code == 200
    ticket = issued.json()["url"].rsplit("/", 1)[1]
    headers = {"X-Download-Ticket": ticket}
    downloaded = client.get("/api/v1/artifacts/attachment", headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == path.read_bytes()
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert downloaded.headers["cache-control"] == "no-store"

    users["viewer"]["department"] = "hr"
    assert client.get("/api/v1/artifacts/attachment", headers=headers).status_code == 403
    store.delete(artifact_api._ticket_key(ticket))
    assert client.get("/api/v1/artifacts/attachment", headers=headers).status_code == 404
    assert client.get("/api/v1/artifacts/attachment").status_code == 404


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
