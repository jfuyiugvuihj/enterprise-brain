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
    # Authorised bodies must not survive in a browser cache either (P2-2).
    for response in (download, preview):
        assert response.headers["cache-control"] == "no-store", response.url
        assert response.headers["pragma"] == "no-cache", response.url
        assert response.headers["expires"] == "0", response.url


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


def test_dataset_file_and_preview_are_not_cacheable(monkeypatch, tmp_path):
    """P2-2 同款口径：数据集文件体与预览逐请求授权，因此一律不得进缓存。

    这里直接调用路由函数：Dataset 注册表与租户 DATA_DIR 的真实形态由其它切片负责，
    本例只锁定响应头与失败时的稳定 code。
    """
    import asyncio
    from types import SimpleNamespace

    import pandas
    from fastapi import HTTPException, Response

    from app.api.v1 import data

    stored = tmp_path / "sales.csv"
    stored.write_text("部门,销售额\n研发,3\n", encoding="utf-8")
    record = SimpleNamespace(
        dataset_id="ds-1",
        version_id="dv-1",
        filename="sales.csv",
        storage_path=str(stored),
        classification=1,
    )
    monkeypatch.setattr(data, "_authorized_dataset", lambda request, filename, action: record)
    monkeypatch.setattr(data, "load_excel", lambda path: pandas.read_csv(path))

    response = Response()
    body = asyncio.run(data.preview_data_file("sales.csv", request=None, response=response))

    assert body["dataset_id"] == "ds-1"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"

    file_response = asyncio.run(data.get_data_file("sales.csv", request=None, inline=False))

    assert file_response.headers["cache-control"] == "no-store"
    assert file_response.headers["pragma"] == "no-cache"


def test_dataset_preview_failure_reports_a_stable_code(monkeypatch):
    """P2-8：预览失败不得把异常文本回显给客户端。"""
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException, Response

    from app.api.v1 import data

    record = SimpleNamespace(dataset_id="ds-1", version_id="dv-1", filename="broken.xlsx", storage_path="broken.xlsx", classification=1)
    monkeypatch.setattr(data, "_authorized_dataset", lambda request, filename, action: record)

    def refuse(path):
        raise RuntimeError("third-party parser exploded at C:\\parsers\\stack")

    monkeypatch.setattr(data, "load_excel", refuse)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(data.preview_data_file("broken.xlsx", request=None, response=Response()))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "dataset_preview_failed"


def test_read_only_storage_answers_with_a_stable_code(monkeypatch):
    """只读保护触发时只能暴露 `storage_read_only`，环境变量名与路径留在日志里。"""
    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.api.v1 import intelligence
    from app.common.monitoring import ProductionReadOnlyProtection

    principal = SimpleNamespace(user_id="u1", department="finance", clearance=1, department_ids=[])
    captured = {}
    monkeypatch.setattr(intelligence, "_authorized", lambda request, action, name: principal)
    monkeypatch.setattr(
        intelligence,
        "record_audit",
        lambda *args, **kwargs: captured.setdefault("audit", args),
    )

    def refuse(*args, **kwargs):
        raise ProductionReadOnlyProtection(
            "knowledge_graph_read_only: KNOWLEDGE_GRAPH_STORE_PATH is required in production"
        )

    monkeypatch.setattr(intelligence._graph, "add_relation", refuse)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            intelligence.add_relation(
                intelligence.RelationRequest(
                    source_entity="制度", relation="规定", target="住宿费", source="制度.pdf"
                ),
                request=None,
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "storage_read_only"
    assert captured["audit"][1:5] == ("resource:upload", "denied", "knowledge_graph_relation", "storage_read_only")
