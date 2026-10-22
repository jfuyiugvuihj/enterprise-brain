"""The document delete chain: authorization, index rollback, physical cleanup, audit.

Four stages, and every one of them has to be observable. An earlier version of this
path could not be entered at all (an owner got ``permission_denied`` and an
administrator got ``department_scope_denied``), which also meant the removal never
produced an audit trail to reconstruct the decision from.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_UNSET = object()


def _token(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _account(username: str, department: str, role: str) -> dict[str, str]:
    return {"id": username, "username": username, "role": role, "department": department}


class _VersionStore:
    """Stand in for the catalog so a deletion is visible to the next read."""

    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]
        self.deleted: list[tuple[str, tuple[str, ...]]] = []

    def list(self, filename, *args, **kwargs):
        return [dict(row) for row in self.rows if row["filename"] == filename]

    def delete(self, filename, storage_paths=()):
        self.deleted.append((filename, tuple(storage_paths)))
        self.rows = [row for row in self.rows if row["filename"] != filename]


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeConnection:
    """Hands back what psycopg3 with ``dict_row`` would, including the probe''s one row."""

    def __init__(self, regclass_row=_UNSET, refuse_probe=False):
        self.executed = []
        self.committed = False
        self._regclass_row = {"documents_table": "documents"} if regclass_row is _UNSET else regclass_row
        self._refuse_probe = refuse_probe

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "to_regclass" in sql:
            if self._refuse_probe:
                raise OSError("probe refused")
            return _FakeResult(self._regclass_row)
        return _FakeResult(None)

    def commit(self):
        self.committed = True

    def deletes(self):
        return [sql for sql, _ in self.executed if "delete from" in sql.lower()]


@pytest.fixture
def audit_journal(tmp_path, monkeypatch):
    """Keep the audit journal inside tmp_path and start from an empty view."""
    from app.common.audit import get_audit_events, reset_audit_storage

    journal = tmp_path / "audit-journal.json"
    monkeypatch.setenv("PERSISTENCE_BACKEND", "json")
    monkeypatch.setenv("PERSISTENCE_FALLBACK_PATH", str(journal))
    monkeypatch.delenv("AUDIT_PERSISTENCE", raising=False)
    reset_audit_storage()
    try:
        yield lambda: get_audit_events()
    finally:
        reset_audit_storage()


def _wire_document(monkeypatch, chat, store, tmp_path, body="policy body"):
    from app.agents import tools
    from app.main import app

    first = tmp_path / "policy__v1.txt"
    first.write_text(body, encoding="utf-8")
    newest = tmp_path / "policy__v2.txt"
    newest.write_text(body, encoding="utf-8")
    for row in store.rows:
        row.setdefault("storage_path", str(newest))
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "list_document_versions", store.list)
    monkeypatch.setattr(chat, "delete_document_versions", store.delete)
    monkeypatch.setattr(chat.retriever, "delete_document", lambda name: None)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)
    return first, newest


def _delete(app, filename="policy.txt", username="alice"):
    return TestClient(app).delete(f"/api/v1/documents/{filename}", headers=_token(username))


def test_delete_document_versions_removes_all_rows_for_filename(monkeypatch):
    """Every catalog row of one logical document, in a single transaction (R8).

    This case used to assert "exactly one statement", which was the defect rather than a
    guarantee: ``_upsert_document`` writes the logical ``documents`` row on upload and
    nothing removed it, so a completed delete left a row naming a file that no longer
    existed. It now asserts both rows go and that one commit covers them.
    """
    from app.documents import catalog

    connection = _FakeConnection()
    monkeypatch.setattr(catalog, "_database_available", lambda: True)
    monkeypatch.setattr(catalog, "_ensure", lambda: None)
    monkeypatch.setattr(catalog, "_conn", lambda: connection)
    monkeypatch.setattr(catalog, "_drop_local_versions", lambda *args, **kwargs: None)

    catalog.delete_document_versions("policy.txt")

    assert connection.committed is True
    assert [params for _, params in connection.executed if "delete from" in _.lower()] == [("policy.txt",)] * 2
    assert [sql.lower() for sql, _ in connection.executed if "delete from" in sql.lower()] == [
        "delete from document_versions where filename = %s",
        "delete from documents where filename = %s",
    ]


def test_a_missing_logical_table_still_lets_the_version_rows_go(monkeypatch):
    """The table is created lazily, so its absence may not veto the cascade that does exist.

    ``to_regclass`` answers NULL there; an unconditional DELETE would abort the
    transaction and take the version rows with it - the opposite of a cascade.
    """
    from app.documents import catalog

    connection = _FakeConnection(regclass_row={"documents_table": None})
    monkeypatch.setattr(catalog, "_database_available", lambda: True)
    monkeypatch.setattr(catalog, "_ensure", lambda: None)
    monkeypatch.setattr(catalog, "_conn", lambda: connection)
    monkeypatch.setattr(catalog, "_drop_local_versions", lambda *args, **kwargs: None)

    catalog.delete_document_versions("policy.txt")

    assert connection.deletes() == ["DELETE FROM document_versions WHERE filename = %s"]
    assert connection.committed is True


def test_a_refused_probe_cannot_take_the_version_deletion_down(monkeypatch):
    """A probe that cannot be answered is reported as absent, never as a failed delete."""
    from app.documents import catalog

    connection = _FakeConnection(refuse_probe=True)
    monkeypatch.setattr(catalog, "_database_available", lambda: True)
    monkeypatch.setattr(catalog, "_ensure", lambda: None)
    monkeypatch.setattr(catalog, "_conn", lambda: connection)
    monkeypatch.setattr(catalog, "_drop_local_versions", lambda *args, **kwargs: None)

    catalog.delete_document_versions("policy.txt")

    assert connection.deletes() == ["DELETE FROM document_versions WHERE filename = %s"]
    assert connection.committed is True


def test_the_sidecar_path_needs_no_database_to_forget_a_document(monkeypatch, tmp_path):
    """The offline catalogue is the other half of the two persistence paths."""
    from app.documents import catalog

    stored = tmp_path / "resource-9001.txt"
    stored.write_text("policy", encoding="utf-8")
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    catalog.record_local_document_version(
        "policy.txt",
        classification=1,
        department="finance",
        storage_path=str(stored),
        version=1,
        owner_id="alice",
        parse_status="ready",
    )

    catalog.delete_document_versions("policy.txt")

    assert catalog.current_documents() == []


def test_delete_document_versions_prunes_the_local_sidecar(tmp_path, monkeypatch):
    """The JSON path keeps ownership offline, so it must also forget deleted rows."""
    from app.documents import catalog

    stored = tmp_path / "resource-0001.txt"
    stored.write_text("policy", encoding="utf-8")
    other = tmp_path / "other-0002.txt"
    other.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    catalog.record_local_document_version(
        "policy.txt",
        classification=1,
        department="finance",
        storage_path=str(stored),
        version=1,
        owner_id="alice",
        parse_status="ready",
    )
    catalog.record_local_document_version(
        "keep.txt",
        classification=1,
        department="finance",
        storage_path=str(other),
        version=1,
        owner_id="alice",
        parse_status="ready",
    )

    catalog.delete_document_versions("policy.txt", storage_paths=[str(stored)])

    records = catalog._read_sidecar(tmp_path / catalog.LOCAL_CATALOG_FILENAME)
    assert list(records) == ["keep.txt|v1"]
    assert records["keep.txt|v1"]["owner_id"] == "alice"
    assert [row["filename"] for row in catalog.current_documents()] == ["keep.txt"]


def test_owner_deletes_their_own_document_end_to_end(monkeypatch, tmp_path, audit_journal):
    from app.api.v1 import chat
    from app.common import auth
    from app.common.permissions import ACTION_DELETE
    from app.main import app

    store = _VersionStore(
        [
            {
                "filename": "policy.txt",
                "version": 2,
                "classification": 1,
                "department": "finance",
                "owner_id": "alice",
                "parse_status": "ready",
            }
        ]
    )
    _first, newest = _wire_document(monkeypatch, chat, store, tmp_path)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: _account(username, "finance", "staff"),
    )

    response = _delete(app, username="alice")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"
    assert response.json()["catalog_rows_remaining"] == 0
    assert not newest.exists()
    assert store.deleted == [("policy.txt", (str(newest),))]
    events = [
        event
        for event in audit_journal()
        if event["action"] == ACTION_DELETE and event["resource"] == "policy.txt"
    ]
    assert [event["outcome"] for event in events] == ["allowed", "allowed"]
    authorization, completion = events
    assert authorization["reason"] == "owner_match"
    assert authorization["resource_scope"]["owner_id"] == "alice"
    assert authorization["policy_version"] == "resource-policy-v2"
    assert completion["before_summary"]["versions"] == 1
    assert completion["after_summary"]["stage"] == "completed"
    assert completion["after_summary"]["files_removed"] == 1


def test_administrator_without_a_department_deletes_any_document(monkeypatch, tmp_path, audit_journal):
    from app.api.v1 import chat
    from app.common import auth
    from app.common.permissions import ACTION_DELETE
    from app.main import app

    store = _VersionStore(
        [
            {
                "filename": "policy.txt",
                "version": 1,
                "classification": 2,
                "department": "finance",
                "owner_id": "someone-else",
            }
        ]
    )
    _, stored = _wire_document(monkeypatch, chat, store, tmp_path)
    monkeypatch.setattr(auth, "get_user", lambda username: _account(username, "", "admin"))

    response = _delete(app, username="root")

    assert response.status_code == 200, response.text
    assert not stored.exists()
    reasons = [
        event["reason"]
        for event in audit_journal()
        if event["action"] == ACTION_DELETE and event["resource"] == "policy.txt"
    ]
    assert reasons == ["administrator_scope", "administrator_scope"]


def test_legacy_unowned_document_is_only_deletable_by_the_management_level(
    monkeypatch, tmp_path
):
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    store = _VersionStore(
        [
            {
                "filename": "policy.txt",
                "version": 1,
                "classification": 1,
                "department": "finance",
                "owner_id": None,
            }
        ]
    )
    _, stored = _wire_document(monkeypatch, chat, store, tmp_path)
    monkeypatch.setattr(auth, "get_user", lambda username: _account(username, "finance", "staff"))

    denied = _delete(app, username="alice")

    assert denied.status_code == 403
    assert denied.json()["detail"] == "permission_denied"
    assert stored.exists()
    assert store.deleted == []

    monkeypatch.setattr(auth, "get_user", lambda username: _account(username, "", "admin"))
    allowed = _delete(app, username="root")

    assert allowed.status_code == 200, allowed.text
    assert not stored.exists()


def test_index_rollback_failure_does_not_claim_the_document_was_deleted(monkeypatch, tmp_path, audit_journal):
    from app.api.v1 import chat
    from app.agents import tools
    from app.common import auth
    from app.common.permissions import ACTION_DELETE
    from app.main import app

    store = _VersionStore(
        [
            {
                "filename": "policy.txt",
                "version": 1,
                "classification": 1,
                "department": "finance",
                "owner_id": "alice",
            }
        ]
    )
    _, stored = _wire_document(monkeypatch, chat, store, tmp_path)
    monkeypatch.setattr(auth, "get_user", lambda username: _account(username, "finance", "admin"))

    def broken_rollback(filename):
        raise RuntimeError("chroma is unavailable")

    monkeypatch.setattr(chat.retriever, "delete_document", broken_rollback)

    response = _delete(app, username="root")

    assert response.status_code == 500
    body = response.json()["detail"]
    assert body["code"] == "index_publish_failed"
    assert body["retryable"] is True
    assert body["details"]["stage"] == "index_rollback"
    # Nothing downstream of the failed stage ran.
    assert stored.exists()
    assert store.deleted == []
    assert store.list("policy.txt")
    events = [
        event
        for event in audit_journal()
        if event["action"] == ACTION_DELETE and event["resource"] == "policy.txt"
    ]
    assert events[-1]["outcome"] == "failed"
    assert events[-1]["reason"] == "index_rollback_failed"
    assert events[-1]["after_summary"]["deleted"] is False


def test_keyword_index_failure_also_blocks_a_success_claim(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.agents import tools
    from app.common import auth
    from app.main import app

    store = _VersionStore(
        [
            {
                "filename": "policy.txt",
                "version": 1,
                "classification": 1,
                "department": "finance",
                "owner_id": "alice",
            }
        ]
    )
    _, stored = _wire_document(monkeypatch, chat, store, tmp_path)
    monkeypatch.setattr(auth, "get_user", lambda username: _account(username, "finance", "admin"))

    def broken_rebuild():
        raise RuntimeError("rank_bm25 is unavailable")

    monkeypatch.setattr(tools, "rebuild_bm25", broken_rebuild)

    response = _delete(app, username="root")

    assert response.status_code == 500
    assert response.json()["detail"]["details"]["stage"] == "keyword_index"
    assert stored.exists()
    assert store.deleted == []


def test_stored_file_that_cannot_be_removed_keeps_the_catalog_row(monkeypatch, tmp_path):
    """A document whose file survives is not reported as deleted.

    The stored path is a directory here, so removing it fails for a real reason
    instead of through a patched-out filesystem.
    """
    from app.agents import tools
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    blocker = tmp_path / "policy__v1.txt"
    blocker.mkdir()
    store = _VersionStore(
        [
            {
                "filename": "policy.txt",
                "version": 1,
                "classification": 1,
                "department": "finance",
                "owner_id": "alice",
                "storage_path": str(blocker),
            }
        ]
    )
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "list_document_versions", store.list)
    monkeypatch.setattr(chat, "delete_document_versions", store.delete)
    monkeypatch.setattr(chat.retriever, "delete_document", lambda name: None)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)
    monkeypatch.setattr(auth, "get_user", lambda username: _account(username, "finance", "admin"))

    response = _delete(app, username="root")

    assert response.status_code == 500
    body = response.json()["detail"]
    assert body["code"] == "internal_error"
    assert body["details"]["stage"] == "physical_cleanup"
    assert blocker.exists()
    assert store.deleted == []
    assert store.list("policy.txt")


def test_the_index_record_is_retired_after_the_indexes_and_before_the_file(monkeypatch, tmp_path):
    """The order of the delete chain is part of the contract.

    A document that still answers from an index may not be recorded as retired, and a
    document whose file is already gone has nothing left to roll back. The published record
    therefore moves last among the index stages and first among the destructive ones.
    """
    from types import SimpleNamespace

    from app.agents import tools
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    store = _VersionStore(
        [
            {
                "filename": "policy.txt",
                "version": 1,
                "classification": 1,
                "department": "finance",
                "owner_id": "alice",
            }
        ]
    )
    _, stored = _wire_document(monkeypatch, chat, store, tmp_path)
    monkeypatch.setattr(auth, "get_user", lambda username: _account(username, "finance", "admin"))
    order: list = []

    class _Publisher:
        def apply(self, publication):
            order.append(("index_record", publication.resource_version_id, stored.exists()))
            return SimpleNamespace(
                as_dict=lambda: {
                    "status": "retired",
                    "index_id": publication.index_id,
                    "source_version_id": publication.resource_version_id,
                    "chunk_count": 0,
                    "mirrored": True,
                    "warnings": [],
                }
            )

    monkeypatch.setattr(chat.retriever, "delete_document", lambda name: order.append(("vector_index", name)))
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: order.append(("keyword_index", "bm25")))
    monkeypatch.setattr(chat, "index_publisher", lambda: _Publisher())

    response = _delete(app)

    assert response.status_code == 200, response.text
    assert [entry[0] for entry in order] == ["vector_index", "keyword_index", "index_record"]
    assert order[2][1] == "policy.txt|v1"
    assert order[2][2] is True, "the stored file was already gone when the record was retired"
    assert not stored.exists()
    assert response.json()["index_retirement"]["status"] == "retired"
    assert store.deleted == [(  "policy.txt", (str(stored),))]
