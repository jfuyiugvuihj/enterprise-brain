from pathlib import Path

from fastapi.testclient import TestClient


class _FakeConnection:
    def __init__(self):
        self.executed = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def commit(self):
        self.committed = True


def test_delete_document_versions_removes_all_rows_for_filename(monkeypatch):
    from app.documents import catalog

    connection = _FakeConnection()
    monkeypatch.setattr(catalog, "_database_available", lambda: True)
    monkeypatch.setattr(catalog, "_ensure", lambda: None)
    monkeypatch.setattr(catalog, "_conn", lambda: connection)

    catalog.delete_document_versions("policy.txt")

    assert connection.committed is True
    assert len(connection.executed) == 1
    sql, params = connection.executed[0]
    assert "delete from document_versions" in sql.lower()
    assert "where filename = %s" in sql.lower()
    assert params == ("policy.txt",)


def test_delete_document_endpoint_removes_file_and_catalog_entry(monkeypatch, tmp_path):
    from app.agents import tools
    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.main import app

    filename = "policy.txt"
    stored_file = tmp_path / "policy__v1.txt"
    stored_file.write_text("policy", encoding="utf-8")
    deleted_catalog_entries = []

    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "list_document_versions", lambda name: [
        {
            "filename": name,
            "storage_path": str(stored_file),
            "classification": 1,
            "department": "finance",
            "owner_id": "document-owner",
        }
    ])
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
    monkeypatch.setattr(
        chat,
        "delete_document_versions",
        lambda name: deleted_catalog_entries.append(name),
    )
    monkeypatch.setattr(chat.retriever, "delete_document", lambda name: None)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)

    client = TestClient(app)
    response = client.delete(
        f"/api/v1/documents/{filename}",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert deleted_catalog_entries == [filename]
    assert not stored_file.exists()
