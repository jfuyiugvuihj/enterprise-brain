"""Response hygiene for protected content.

P2-2: authenticated Artifact bodies must never be reusable from an HTTP cache.
P2-8: document catalog rows must never echo a server-side absolute path.
"""
import os
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]|^\\\\[^\\/]+[\\/]|^/")
DRIVE_OR_ROOT = re.compile(r"[A-Za-z]:[\\/]|\\\\")


def _user(username: str, department: str = "finance", role: str = "manager") -> dict[str, str]:
    return {"id": username, "username": username, "role": role, "department": department}


def _headers(username: str, origin: str | None = None) -> dict[str, str]:
    from app.common.auth import create_token

    headers = {"Authorization": f"Bearer {create_token(username)}"}
    if origin:
        # A cross-origin request is the shape the audit replayed the cache on.
        headers["Origin"] = origin
    return headers


@pytest.fixture
def workdir_dir(request):
    """A documents directory inside the working tree, as in a real deployment.

    ``tmp/`` is git-ignored and the directory is removed afterwards, so the
    test never leaves files behind for the other agents sharing this tree.
    """
    root = Path.cwd() / "tmp" / f"x1_{request.node.name}"
    shutil.rmtree(root, ignore_errors=True)
    (root / "documents").mkdir(parents=True)
    try:
        yield root / "documents"
    finally:
        shutil.rmtree(root, ignore_errors=True)


class _FakeCatalogConnection:
    """Stand in for PostgreSQL so the real catalog read path runs offline."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    def fetchall(self):
        return [dict(row) for row in self.rows]

    def commit(self):
        return None


def _assert_no_server_path(storage_path: str) -> None:
    assert storage_path, "the catalog row must still name the stored resource"
    assert not os.path.isabs(storage_path), f"absolute path leaked: {storage_path}"
    assert not Path(storage_path).is_absolute(), storage_path
    assert not ABSOLUTE_PATH.match(storage_path), f"absolute path leaked: {storage_path}"
    assert not DRIVE_OR_ROOT.search(storage_path), storage_path


# ------------------------------------------------------------------ P2-2 artifacts
def test_artifact_content_and_download_are_not_cacheable(monkeypatch, tmp_path):
    from app.agents.contracts import Principal
    from app.common import auth
    from app.main import app
    from app.storage import artifacts
    from app.storage.artifacts import ArtifactRegistry

    registry = ArtifactRegistry(root=tmp_path, metadata_path=tmp_path / "artifact-metadata.json")
    monkeypatch.setattr(artifacts, "artifact_registry", registry)
    png = tmp_path / "revenue.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n chart bytes")
    artifact = registry.register(
        png,
        artifact_type="chart",
        principal=Principal.from_user(_user("finance-manager")),
    )
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username))
    client = TestClient(app)

    for route in ("content", "download"):
        response = client.get(
            f"/api/v1/artifacts/{artifact.artifact_id}/{route}",
            headers=_headers("finance-manager", origin="http://localhost:5173"),
        )

        assert response.status_code == 200, route
        assert response.content == b"\x89PNG\r\n\x1a\n chart bytes"
        assert response.headers["cache-control"] == "no-store"
        assert "public" not in response.headers["cache-control"]
        assert "max-age" not in response.headers["cache-control"]
        # Pragma/Expires must not contradict no-store on HTTP/1.0 hops.
        assert response.headers["pragma"] == "no-cache"
        assert response.headers["expires"] == "0"
        assert "no-store" not in response.headers.get("vary", "").lower()


def test_anonymous_and_cross_department_artifact_requests_stay_denied(monkeypatch, tmp_path):
    """no-store is what stops the owner's cached 200 from replaying to them."""
    from app.agents.contracts import Principal
    from app.common import auth
    from app.main import app
    from app.storage import artifacts
    from app.storage.artifacts import ArtifactRegistry

    registry = ArtifactRegistry(root=tmp_path, metadata_path=tmp_path / "artifact-metadata.json")
    monkeypatch.setattr(artifacts, "artifact_registry", registry)
    png = tmp_path / "revenue.png"
    png.write_bytes(b"chart bytes")
    artifact = registry.register(
        png,
        artifact_type="chart",
        principal=Principal.from_user(_user("finance-manager")),
    )
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: _user(username, "hr" if username == "hr-manager" else "finance"),
    )
    client = TestClient(app)

    owner = client.get(
        f"/api/v1/artifacts/{artifact.artifact_id}/download",
        headers=_headers("finance-manager"),
    )
    anonymous = client.get(f"/api/v1/artifacts/{artifact.artifact_id}/download")
    cross_department = client.get(
        f"/api/v1/artifacts/{artifact.artifact_id}/download",
        headers=_headers("hr-manager"),
    )

    assert owner.status_code == 200
    assert owner.headers["cache-control"] == "no-store"
    assert anonymous.status_code == 401
    assert cross_department.status_code == 403


# ------------------------------------------------------------- P2-8 document catalog
def test_document_catalog_and_file_route_never_echo_absolute_paths(monkeypatch, workdir_dir):
    from app.api.v1 import chat
    from app.common import auth
    from app.documents import catalog
    from app.main import app

    stored = workdir_dir / "e89d2c08-6d74-4e7a-baa5-1f2a7c8b9d0e.txt"
    stored.write_text("policy body", encoding="utf-8")
    absolute = str(stored.resolve())
    rows = [
        {
            "filename": "policy.txt",
            "version": 3,
            "classification": 2,
            "department": "finance",
            "storage_path": absolute,
            "created_at": "2026-09-14T09:00:00+08:00",
        }
    ]
    connection = _FakeCatalogConnection(rows)
    monkeypatch.setattr(catalog, "_database_available", lambda: True)
    monkeypatch.setattr(catalog, "_ensure", lambda: None)
    monkeypatch.setattr(catalog, "_conn", lambda: connection)
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(workdir_dir))
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username))

    client = TestClient(app)
    headers = _headers("finance-manager")

    catalog_response = client.get("/api/v1/documents/catalog", headers=headers)
    versions_response = client.get("/api/v1/documents/policy.txt/versions", headers=headers)

    assert catalog_response.status_code == 200
    assert versions_response.status_code == 200
    listed_documents = catalog_response.json()["documents"]
    listed_versions = versions_response.json()["versions"]
    assert [row["filename"] for row in listed_documents] == ["policy.txt"]
    assert [row["version"] for row in listed_versions] == [3]

    for row in [*listed_documents, *listed_versions]:
        _assert_no_server_path(row["storage_path"])
        # The rewritten value must stay resolvable for the in-process consumers
        # (download, preview, delete) that read it straight off the catalog row.
        assert os.path.exists(row["storage_path"]), row["storage_path"]

    for response in (catalog_response, versions_response):
        assert absolute not in response.text
        assert str(workdir_dir.resolve()) not in response.text

    download = client.get("/api/v1/documents/policy.txt/file", headers=headers)
    preview = client.get("/api/v1/documents/policy.txt/preview", headers=headers)

    assert download.status_code == 200
    assert download.text == "policy body"
    assert preview.status_code == 200


def test_local_catalog_rows_also_hide_the_documents_root(monkeypatch, workdir_dir):
    from app.documents import catalog

    (workdir_dir / "legacy__v1.txt").write_text("legacy body", encoding="utf-8")
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(workdir_dir))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    monkeypatch.setattr(
        catalog,
        "_conn",
        lambda: (_ for _ in ()).throw(AssertionError("offline mode must not connect")),
    )

    rows = catalog.current_documents()
    versions = catalog.list_document_versions("legacy.txt")

    assert [row["filename"] for row in rows] == ["legacy.txt"]
    assert [row["version"] for row in versions] == [1]
    for row in [*rows, *versions]:
        _assert_no_server_path(row["storage_path"])
        assert str(workdir_dir.resolve()) not in row["storage_path"]
        assert os.path.exists(row["storage_path"])


def test_public_storage_path_never_returns_an_absolute_path(monkeypatch):
    from app.documents import catalog

    inside = os.path.join(os.getcwd(), "documents", "resource-0001.txt")

    assert os.path.isabs(inside)
    assert catalog._public_storage_path(inside) == "documents/resource-0001.txt"
    assert catalog._public_storage_path("documents/resource-0001.txt") == (
        "documents/resource-0001.txt"
    )
    once = catalog._public_storage_path(inside)
    assert catalog._public_storage_path(once) == once, "rewriting must be idempotent"
    assert catalog._public_storage_path(None) == ""
    assert catalog._public_storage_path("") == ""

    def no_relative_form(*args, **kwargs):
        raise ValueError("path is on a different drive")

    monkeypatch.setattr(catalog.os.path, "relpath", no_relative_form)
    escaped = catalog._public_storage_path(inside)

    assert escaped == "resource-0001.txt"
    _assert_no_server_path(escaped)


def test_public_rows_rewrite_only_existing_storage_paths():
    from app.documents import catalog

    absolute = os.path.join(os.getcwd(), "documents", "b.txt")
    rows = [{"filename": "a.txt"}, {"filename": "b.txt", "storage_path": absolute}]

    public = catalog._public_rows(rows)

    assert "storage_path" not in public[0]
    assert public[1]["storage_path"] == "documents/b.txt"
    assert rows[1]["storage_path"] == absolute, "the caller's row must not be mutated"