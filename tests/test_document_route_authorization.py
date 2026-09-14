from fastapi.testclient import TestClient


def _token_headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _user(username: str, department: str) -> dict[str, str]:
    return {
        "id": username,
        "username": username,
        "role": "manager",
        "department": department,
    }


def test_document_download_and_preview_deny_cross_department_principal(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    stored_file = tmp_path / "document.txt"
    stored_file.write_text("restricted", encoding="utf-8")
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, "hr"))
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name: [
            {
                "filename": name,
                "storage_path": str(stored_file),
                "classification": 2,
                "department": "finance",
                "owner_id": "finance-owner",
            }
        ],
    )

    client = TestClient(app)
    headers = _token_headers("hr-manager")

    assert client.get("/api/v1/documents/plan.txt/file", headers=headers).status_code == 403
    assert client.get("/api/v1/documents/plan.txt/preview", headers=headers).status_code == 403


def test_document_download_denies_metadata_without_resource_scope(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    stored_file = tmp_path / "legacy.txt"
    stored_file.write_text("legacy", encoding="utf-8")
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, "finance"))
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name: [{"filename": name, "storage_path": str(stored_file)}],
    )

    response = TestClient(app).get(
        "/api/v1/documents/legacy.txt/file",
        headers=_token_headers("finance-manager"),
    )

    assert response.status_code == 403


def test_document_download_and_preview_allow_matching_resource_scope(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    stored_file = tmp_path / "finance.txt"
    stored_file.write_text("finance", encoding="utf-8")
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, "finance"))
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name: [
            {
                "filename": name,
                "storage_path": str(stored_file),
                "classification": 2,
                "department": "finance",
                "owner_id": "finance-owner",
            }
        ],
    )

    client = TestClient(app)
    headers = _token_headers("finance-manager")

    assert client.get("/api/v1/documents/finance.txt/file", headers=headers).status_code == 200
    assert client.get("/api/v1/documents/finance.txt/preview", headers=headers).status_code == 200


def test_document_catalog_hides_resources_outside_principal_scope(monkeypatch):
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, "hr"))
    monkeypatch.setattr(
        chat,
        "current_documents",
        lambda: [
            {
                "filename": "finance.txt",
                "classification": 2,
                "department": "finance",
                "owner_id": "finance-owner",
            },
            {
                "filename": "hr.txt",
                "classification": 2,
                "department": "hr",
                "owner_id": "hr-owner",
            },
        ],
    )

    response = TestClient(app).get(
        "/api/v1/documents/catalog",
        headers=_token_headers("hr-manager"),
    )

    assert response.status_code == 200
    assert response.json()["documents"] == [
        {
            "filename": "hr.txt",
            "classification": 2,
            "department": "hr",
            "owner_id": "hr-owner",
        }
    ]


def test_document_version_history_denies_cross_department_principal(monkeypatch):
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, "hr"))
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name: [
            {
                "filename": name,
                "version": 1,
                "classification": 2,
                "department": "finance",
                "owner_id": "finance-owner",
            }
        ],
    )

    response = TestClient(app).get(
        "/api/v1/documents/finance.txt/versions",
        headers=_token_headers("hr-manager"),
    )

    assert response.status_code == 403
