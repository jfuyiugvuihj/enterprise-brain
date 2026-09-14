from pathlib import Path

from fastapi.testclient import TestClient


def test_doc_panel_uses_catalog_endpoint():
    source = Path("frontend/src/components/DocPanel.vue").read_text(encoding="utf-8")

    assert "/documents/catalog" in source
    assert 'axios.get(`${API}/documents`' not in source


def test_document_catalog_route_returns_metadata(monkeypatch):
    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.main import app

    monkeypatch.setattr(
        chat,
        "current_documents",
        lambda: [
            {
                "filename": "policy.txt",
                "version": 1,
                "classification": 1,
                "department": "finance",
                "owner_id": "document-owner",
                "created_at": "2026-09-08T00:00:00+08:00",
            }
        ],
    )
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": username,
            "username": username,
            "role": "admin",
            "department": "finance",
        },
    )

    client = TestClient(app)
    token = create_token("admin")
    response = client.get("/api/v1/documents/catalog", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["documents"][0]["filename"] == "policy.txt"
