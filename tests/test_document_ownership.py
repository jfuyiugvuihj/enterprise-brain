"""Document ownership: the owner column, the two write paths and the policy rules.

Ownership is the single fact that decides whether a document can be opened or removed
at all, so it is asserted from four angles: the catalog writes it on both persistence
paths, the policy reads it for every action, the API answers with it, and the schema
migration that added it stays offline-verifiable.
"""
import json
from pathlib import Path

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from app.agents.contracts import Principal
from app.common.permissions import (
    ACTION_ANALYZE,
    ACTION_AUDIT,
    ACTION_DELETE,
    ACTION_DOWNLOAD,
    ACTION_VIEW,
)
from app.common.policy import authorization_decision


def _principal(username: str, department: str = "finance", role: str = "staff", **extra) -> Principal:
    user = {"id": username, "username": username, "role": role, "department": department}
    user.update(extra)
    return Principal.from_user(user)


def _document(**overrides) -> dict:
    resource = {
        "resource_type": "document",
        "resource_id": "doc-1",
        "owner_id": "alice",
        "department": "finance",
        "classification": 1,
        "visibility": "private",
        "status": "active",
    }
    resource.update(overrides)
    return resource


class _RecordingConnection:
    def __init__(self):
        self.executed = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def commit(self):
        self.committed = True


# ------------------------------------------------------------------ persistence
def test_record_document_version_writes_the_owner_to_both_paths(tmp_path, monkeypatch):
    from app.documents import catalog

    stored = tmp_path / "resource-0001.txt"
    stored.write_text("policy body", encoding="utf-8")
    connection = _RecordingConnection()
    monkeypatch.setattr(catalog, "_database_available", lambda: True)
    monkeypatch.setattr(catalog, "_ensure", lambda: None)
    monkeypatch.setattr(catalog, "_conn", lambda: connection)

    metadata = catalog.record_document_version(
        "policy.txt",
        classification=2,
        department="finance",
        storage_path=str(stored),
        version=1,
        principal=_principal("alice", "finance"),
        parse_status="ready",
    )

    sql, params = connection.executed[0]
    assert "owner_id" in sql
    assert "size_bytes" in sql
    assert "parse_status" in sql
    assert "alice" in params
    assert "ready" in params
    assert connection.committed is True
    assert metadata["owner_id"] == "alice"
    assert metadata["size_bytes"] == len(b"policy body")

    records = catalog._read_sidecar(tmp_path / catalog.LOCAL_CATALOG_FILENAME)
    assert records["policy.txt|v1"]["owner_id"] == "alice"
    assert records["policy.txt|v1"]["parse_status"] == "ready"
    assert records["policy.txt|v1"]["size_bytes"] == len(b"policy body")


def test_local_record_keeps_the_owner_when_postgres_is_offline(tmp_path, monkeypatch):
    from app.documents import catalog

    stored = tmp_path / "resource-0002.txt"
    stored.write_text("offline body", encoding="utf-8")
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        catalog,
        "_conn",
        lambda: (_ for _ in ()).throw(AssertionError("offline mode must not connect")),
    )
    monkeypatch.setattr(catalog, "_database_available", lambda: False)

    catalog.record_local_document_version(
        "offline.txt",
        classification=1,
        department="hr",
        storage_path=str(stored),
        version=1,
        principal=_principal("bob", "hr", role="manager"),
        parse_status="ready",
    )

    rows = catalog.current_documents()
    assert [row["filename"] for row in rows] == ["offline.txt"]
    assert rows[0]["owner_id"] == "bob"
    assert rows[0]["ownership"] == "owned"
    assert rows[0]["parse_status"] == "ready"
    assert rows[0]["size_bytes"] == len(b"offline body")


def test_catalog_rows_are_shaped_for_the_api_and_hide_the_absolute_path(tmp_path, monkeypatch):
    from app.documents import catalog

    stored = tmp_path / "resource-0003.txt"
    stored.write_text("legacy body", encoding="utf-8")
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    catalog.record_local_document_version(
        "legacy.txt",
        classification=1,
        department="",
        storage_path=str(stored),
        version=1,
        parse_status="failed",
    )

    row = catalog.current_documents()[0]

    assert row["owner_id"] is None
    assert row["ownership"] == "legacy"
    assert row["parse_status"] == "failed"
    assert Path(row["storage_path"]).is_absolute() is False
    assert str(tmp_path) not in json.dumps(row, default=str)


def test_unknown_parse_status_degrades_to_pending(catalog_row=None):
    from app.documents import catalog

    assert catalog._normalise_parse_status("READY") == "ready"
    assert catalog._normalise_parse_status(None) == "pending"
    assert catalog._normalise_parse_status("exploded") == "pending"


def test_chunk_count_is_left_to_the_index_publication_slice():
    """S1 owns ownership and parse state; chunk accounting belongs to S4."""
    from app.db.migrations import MIGRATIONS

    migration = next(item for item in MIGRATIONS if item.version == "0006")

    assert "ADD COLUMN IF NOT EXISTS chunk_count" not in migration.sql
    assert "chunk_count" in migration.sql, "the comment must say who owns the column"
    for statement in (
        "ALTER TABLE IF EXISTS documents",
        "ALTER TABLE IF EXISTS document_versions",
    ):
        assert statement in migration.sql
    assert migration.sql.count("ADD COLUMN IF NOT EXISTS owner_id TEXT") == 2
    assert migration.sql.count("ADD COLUMN IF NOT EXISTS size_bytes BIGINT") == 2
    assert migration.sql.count("ADD COLUMN IF NOT EXISTS parse_status") == 2
    assert "'pending', 'parsing', 'ready', 'failed'" in migration.sql
    assert "CREATE INDEX IF NOT EXISTS documents_owner_idx" in migration.sql
    assert "CREATE INDEX IF NOT EXISTS document_versions_owner_idx" in migration.sql
    assert migration.sql.count("CREATE INDEX IF NOT EXISTS") == 4


# ----------------------------------------------------------------------- policy
@pytest.mark.parametrize(
    "action",
    [ACTION_VIEW, ACTION_DOWNLOAD, ACTION_DELETE],
)
def test_owner_is_authorized_for_every_ownership_action(action):
    alice = _principal("alice", "hr", role="staff")

    decision = authorization_decision(alice, _document(owner_id="alice", department="finance"), action)

    assert decision.allowed is True
    assert decision.reason_code == "owner_match"


def test_ownership_does_not_confer_a_functional_or_administrative_action():
    owner_in_scope = _principal("alice", "finance", role="staff")
    owner_elsewhere = _principal("alice", "hr", role="staff")

    # Analyzing content is a role capability. The owner who happens to sit in the
    # right department is allowed by the department rule, not by ownership.
    assert authorization_decision(
        owner_in_scope, _document(owner_id="alice"), ACTION_ANALYZE
    ).reason_code == "department_scope_match"
    assert authorization_decision(
        owner_elsewhere, _document(owner_id="alice"), ACTION_ANALYZE
    ).reason_code == "department_scope_denied"
    # Owning a document never makes the caller an auditor or an administrator.
    assert authorization_decision(
        owner_in_scope, _document(owner_id="alice"), ACTION_AUDIT
    ).reason_code == "permission_denied"


def test_administrator_decision_uses_its_own_reason_code_and_skips_departments():
    root = _principal("root", "", role="admin")

    decision = authorization_decision(root, _document(owner_id="someone-else", classification=2), ACTION_DELETE)

    assert decision.allowed is True
    assert decision.reason_code == "administrator_scope"
    assert decision.reason_code != "department_scope_match"
    assert "administrator_scope" in decision.matched_rules


def test_administrator_still_needs_the_clearance():
    root = _principal("root", "", role="admin")

    decision = authorization_decision(root, _document(owner_id=None, classification=4), ACTION_DELETE)

    assert decision.allowed is False
    assert decision.reason_code == "clearance_insufficient"


def test_cross_department_control_is_a_lack_of_authority_not_a_scope_answer():
    lead = _principal("ops-lead", "operations", role="manager", permissions=["resource:view", "resource:delete"])

    denied = authorization_decision(lead, _document(owner_id="someone-else", department="finance"), ACTION_DELETE)
    read = authorization_decision(lead, _document(owner_id="someone-else", department="finance"), ACTION_VIEW)

    assert denied.allowed is False
    assert denied.reason_code == "permission_denied"
    assert denied.reason_code != "department_scope_denied"
    assert "department_scope_mismatch" in denied.matched_rules
    # Reading stays a scope question, which is the only place the code survives.
    assert read.reason_code == "department_scope_denied"


@pytest.mark.parametrize(
    ("role", "expected_allowed"),
    [("staff", False), ("manager", True), ("admin", True)],
)
def test_unowned_documents_are_visible_only_to_the_management_level(role, expected_allowed):
    principal = _principal(f"{role}-user", "finance", role=role)

    decision = authorization_decision(principal, _document(owner_id=None), ACTION_VIEW)

    assert decision.allowed is expected_allowed
    if not expected_allowed:
        assert decision.reason_code == "permission_denied"
        assert decision.matched_rules == ["legacy_ownership"]


def test_legacy_rule_is_limited_to_documents():
    """Datasets and artifacts keep their existing behaviour for an empty owner."""
    staff = _principal("alice", "finance", role="staff")

    document = authorization_decision(staff, _document(owner_id=None), ACTION_VIEW)
    dataset = authorization_decision(
        staff,
        {"resource_type": "dataset", "owner_id": "", "department": "finance", "classification": 1},
        ACTION_VIEW,
    )

    assert document.allowed is False
    assert dataset.allowed is True


# ------------------------------------------------------------ upload lifecycle
def _upload_client(monkeypatch, tmp_path, principal):
    from app.api.v1 import chat
    from app.agents import tools
    from app.documents import catalog
    from fastapi import FastAPI

    class FakeRetriever:
        def __init__(self):
            self.indexed = {}

        def add_document(self, filename, content, classification, department):
            self.indexed[filename] = content
            return True, "indexed 2 chunks"

        def delete_document(self, filename):
            self.indexed.pop(filename, None)

    retriever = FakeRetriever()
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "retriever", retriever)
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False, raising=False)
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)

    probe = FastAPI()
    probe.include_router(chat.router, prefix="/api/v1")

    @probe.middleware("http")
    async def _attach_principal(request, call_next):
        request.state.principal = principal
        request.state.username = principal.username
        return await call_next(request)

    return TestClient(probe), retriever


def test_successful_upload_records_ready_and_the_uploader(monkeypatch, tmp_path):
    from app.documents import catalog

    client, _retriever = _upload_client(monkeypatch, tmp_path, _principal("alice", "finance"))
    body = "# inventory\n\nturnover 32 days\n"

    response = client.post(
        "/api/v1/upload",
        files={"file": ("inventory.md", body.encode("utf-8"), "text/markdown")},
        data={"classification": "1", "department": "finance"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["parse_status"] == "ready"
    assert payload["owner_id"] == "alice"
    assert payload["size_bytes"] == len(body.encode("utf-8"))

    rows = catalog.current_documents()
    assert [(row["filename"], row["parse_status"], row["owner_id"]) for row in rows] == [
        ("inventory.md", "ready", "alice")
    ]
    assert rows[0]["ownership"] == "owned"


def test_failed_upload_keeps_a_failed_row_that_can_still_be_retired(monkeypatch, tmp_path):
    from app.agents import tools
    from app.api.v1 import chat
    from app.common import auth
    from app.documents import catalog

    client, _retriever = _upload_client(monkeypatch, tmp_path, _principal("alice", "finance"))
    monkeypatch.setattr(chat, "load_document", lambda path: (_ for _ in ()).throw(ValueError("boom")))

    upload = client.post(
        "/api/v1/upload",
        files={"file": ("policy.pdf", b"%PDF-1.4 broken body", "application/pdf")},
        data={"classification": "1", "department": "finance"},
    )

    assert upload.status_code == 500
    assert upload.json()["detail"] == "document_parse_failed"

    rows = catalog.current_documents()
    assert [(row["filename"], row["parse_status"], row["ownership"]) for row in rows] == [
        ("policy.pdf", "failed", "owned")
    ]
    assert rows[0]["owner_id"] == "alice"
    # The stored file is still there, which is what keeps the row resolvable.
    assert Path(rows[0]["storage_path"]).exists()

    # Staff outside the owning department cannot even list it.
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": username,
            "username": username,
            "role": "staff",
            "department": "operations",
        },
    )
    outsider = TestClient(app_module()).get("/api/v1/documents/catalog", headers=_token("mallory"))
    assert outsider.json()["documents"] == []

    # An administrator can, and can retire it for real.
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": username,
            "username": username,
            "role": "admin",
            "department": "",
        },
    )
    monkeypatch.setattr(chat.retriever, "delete_document", lambda name: None)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)
    administrator = TestClient(app_module())
    listed = administrator.get("/api/v1/documents/catalog", headers=_token("root")).json()["documents"]
    assert [row["filename"] for row in listed] == ["policy.pdf"]
    assert listed[0]["parse_status"] == "failed"

    removed = administrator.delete("/api/v1/documents/policy.pdf", headers=_token("root"))

    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "ok"
    assert catalog.current_documents() == []
    assert list(tmp_path.glob("*.pdf")) == []
    assert not (tmp_path / catalog.LOCAL_CATALOG_FILENAME).exists()


def app_module():
    from app.main import app

    return app


def _token(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}
