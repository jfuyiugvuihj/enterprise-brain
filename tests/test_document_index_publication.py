"""Index publication wiring for the document lifecycle (S4, Wave 3).

Uploading a document publishes an index version and writes the chunk record; deleting it
retires that version again. Every assertion here runs against an in-memory stand-in for
``index_registry`` / ``index_versions`` / ``chunks``: nothing connects to a server and no
migration is applied, because the SQL and the transaction shape are what is under test.
"""
import asyncio
from copy import deepcopy
import io
import json

import pytest
from fastapi import UploadFile


CHUNK_COLUMNS = (
    "chunk_id",
    "owner_id",
    "resource_type",
    "resource_id",
    "resource_version_id",
    "index_version_id",
    "content",
    "metadata",
)

_MIRROR_TABLES = ("index_registry", "index_versions", "chunks", "resource_versions")
_COUNTER_TABLES = ("documents", "document_versions")

_SCHEMA = {
    "index_registry": ("index_id", "owner_id", "resource_type", "status", "current_version_id", "metadata"),
    "index_versions": (
        "index_version_id",
        "index_id",
        "owner_id",
        "source_version_id",
        "backend",
        "chunk_count",
        "checksum",
        "status",
        "published_at",
        "superseded_at",
        "metadata",
    ),
    "chunks": CHUNK_COLUMNS + ("embedding", "created_at"),
    "resource_versions": (
        "resource_type",
        "resource_id",
        "version_id",
        "owner_id",
        "department_ids",
        "classification",
        "visibility",
        "status",
        "content_sha256",
        "metadata",
        "superseded_at",
    ),
    "documents": ("filename", "chunk_count"),
    "document_versions": ("filename", "version", "chunk_count"),
}


class _Cursor:
    """psycopg3's cursor: execute, executemany, fetch, and usable as a context manager."""

    def __init__(self, rows=(), rowcount=0, database=None):
        self._rows = list(rows)
        self.rowcount = rowcount
        self.database = database

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def executemany(self, sql, parameters_seq):
        for parameters in parameters_seq:
            self.database.execute(sql, parameters)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _Connection:
    """One connection is one publication: a rollback must undo every statement of it."""

    def __init__(self, database):
        self.database = database
        self._marker = database.snapshot()

    def execute(self, sql, params=()):
        return self.database.execute(sql, params)

    def cursor(self):
        # Deliberately not a shortcut for execute(): psycopg3 owns executemany on the
        # cursor, so a connection here must not answer to it. Code that reaches for
        # connection.executemany has to fail here exactly as it fails on a real server.
        return _Cursor(database=self.database)

    def commit(self):
        self.database.commits += 1
        self._marker = self.database.snapshot()

    def rollback(self):
        self.database.rollbacks += 1
        self.database.restore(self._marker)

    def close(self):
        self.database.closes += 1


class FakeIndexDatabase:
    """The subset of PostgreSQL this slice touches, as a dictionary."""

    def __init__(self, *, migrated=True, counters=True):
        self.tables = {
            "index_registry": {},
            "index_versions": {},
            "chunks": {},
            "resource_versions": {},
        }
        self.document_chunk_count = {}
        self.version_chunk_count = {}
        self.columns = set()
        for table, columns in _SCHEMA.items():
            if not migrated and table in _MIRROR_TABLES:
                continue
            for column in columns:
                if not counters and column == "chunk_count" and table in _COUNTER_TABLES:
                    continue
                self.columns.add((table, column))
        self.statements = []
        self.failures = {}
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0
        self.connections = 0

    # ------------------------------------------------------------------ helpers
    def connection(self):
        self.connections += 1
        return _Connection(self)

    def snapshot(self):
        return deepcopy({"tables": self.tables, "documents": self.document_chunk_count, "versions": self.version_chunk_count})

    def restore(self, snapshot):
        restored = deepcopy(snapshot)
        self.tables = restored["tables"]
        self.document_chunk_count = restored["documents"]
        self.version_chunk_count = restored["versions"]

    def chunk_rows(self):
        return list(self.tables["chunks"].values())

    def version_rows(self):
        return list(self.tables["index_versions"].values())

    def resource_version_rows(self):
        return list(self.tables["resource_versions"].values())

    def statements_matching(self, fragment):
        return [sql for sql, _ in self.statements if fragment in sql]

    # ------------------------------------------------------------------ executor
    def execute(self, sql, params=()):
        normalized = " ".join(sql.split()).lower()
        self.statements.append((normalized, params))
        for fragment, error in self.failures.items():
            if fragment in normalized:
                raise error
        if "information_schema.columns" in normalized:
            return _Cursor(
                [{"table_name": table, "column_name": column} for table, column in sorted(self.columns)]
            )
        if "delete from chunks" in normalized:
            resource_type, resource_id = params
            removed = [
                key
                for key, row in self.tables["chunks"].items()
                if row["resource_type"] == resource_type and row["resource_id"] == resource_id
            ]
            for key in removed:
                del self.tables["chunks"][key]
            return _Cursor(rowcount=len(removed))
        if "count(*) from chunks" in normalized:
            if "index_version_id" in normalized:
                matching = [
                    row for row in self.tables["chunks"].values() if row["index_version_id"] == params[0]
                ]
            else:
                matching = [
                    row
                    for row in self.tables["chunks"].values()
                    if (row["resource_type"], row["resource_id"]) == tuple(params)
                ]
            return _Cursor([{"count": len(matching)}])
        if "insert into resource_versions" in normalized:
            (
                resource_type,
                resource_id,
                version_id,
                owner_id,
                department_ids,
                classification,
                visibility,
                status,
                content_sha256,
                metadata,
                superseded_at,
            ) = params
            key = (resource_type, resource_id, version_id)
            row = self.tables["resource_versions"].get(key, {})
            row.update(
                {
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "version_id": version_id,
                    "owner_id": row.get("owner_id") or owner_id,
                    "department_ids": json.loads(department_ids),
                    "classification": classification,
                    "visibility": visibility,
                    "status": status,
                    "content_sha256": content_sha256 or row.get("content_sha256"),
                    "metadata": json.loads(metadata),
                    "superseded_at": row.get("superseded_at") or superseded_at,
                }
            )
            self.tables["resource_versions"][key] = row
            return _Cursor(rowcount=1)
        if "insert into index_registry" in normalized:
            index_id, owner_id, resource_type, status, current_version_id, metadata = params
            self.tables["index_registry"][index_id] = {
                "index_id": index_id,
                "owner_id": owner_id,
                "resource_type": resource_type,
                "status": status,
                "current_version_id": current_version_id,
                "metadata": json.loads(metadata),
            }
            return _Cursor(rowcount=1)
        if "insert into index_versions" in normalized:
            (
                index_version_id,
                index_id,
                owner_id,
                source_version_id,
                backend,
                chunk_count,
                checksum,
                status,
                metadata,
            ) = params
            row = self.tables["index_versions"].get(index_version_id, {})
            row.update(
                {
                    "index_version_id": index_version_id,
                    "index_id": index_id,
                    "owner_id": owner_id,
                    "source_version_id": source_version_id,
                    "backend": backend,
                    "chunk_count": chunk_count,
                    "checksum": checksum,
                    "status": status,
                    "published_at": row.get("published_at"),
                    "superseded_at": row.get("superseded_at"),
                    "metadata": json.loads(metadata),
                }
            )
            self.tables["index_versions"][index_version_id] = row
            return _Cursor(rowcount=1)
        if "insert into chunks" in normalized:
            values = dict(zip(CHUNK_COLUMNS, params))
            values["metadata"] = json.loads(values["metadata"])
            self.tables["chunks"][values["chunk_id"]] = values
            return _Cursor(rowcount=1)
        if "update index_versions" in normalized and "'superseded'" in normalized:
            row = self.tables["index_versions"].get(params[0])
            if row is not None:
                row["status"] = "superseded"
                row["superseded_at"] = "now"
            return _Cursor(rowcount=1)
        if "update index_versions" in normalized:
            status, index_version_id = params
            row = self.tables["index_versions"].get(index_version_id)
            if row is not None:
                row["status"] = status
                row["published_at"] = row.get("published_at") or "now"
                row["superseded_at"] = None
            return _Cursor(rowcount=1)
        if "update index_registry" in normalized:
            status, current_version_id, owner_id, index_id = params
            row = self.tables["index_registry"].get(index_id, {"index_id": index_id})
            row["status"] = status
            row["current_version_id"] = current_version_id
            row["owner_id"] = row.get("owner_id") or owner_id
            self.tables["index_registry"][index_id] = row
            return _Cursor(rowcount=1)
        if "update document_versions set chunk_count" in normalized:
            if len(params) == 1:
                (filename,) = params
                self.version_chunk_count[filename] = 0
            else:
                count, filename, version = params
                self.version_chunk_count[(filename, version)] = count
            return _Cursor(rowcount=1)
        if "update documents set chunk_count" in normalized:
            if len(params) == 1:
                (filename,) = params
                self.document_chunk_count[filename] = 0
            else:
                count, filename = params
                self.document_chunk_count[filename] = count
            return _Cursor(rowcount=1)
        raise AssertionError(f"unexpected statement: {normalized}")


class _VectorStore:
    """Stands in for Chroma: it holds the chunks and can enumerate them back."""

    def __init__(self, chunks=("first chunk", "second chunk", "third chunk")):
        self.indexed = {}
        self.chunk_texts = chunks
        self.deletions = []

    def add_document(self, filename, content, classification, department):
        self.indexed[filename] = list(self.chunk_texts)
        return True, f"added {len(self.chunk_texts)} chunks"

    def document_chunks(self, filename):
        return [
            {
                "vector_id": f"{filename}_{ordinal}",
                "content": text,
                "chunk_index": ordinal,
                "classification": 1,
                "department": "finance",
                "hash": "vector-hash",
            }
            for ordinal, text in enumerate(self.indexed.get(filename, []))
        ]

    def delete_document(self, filename):
        self.indexed.pop(filename, None)
        self.deletions.append(filename)


class _BlindVectorStore:
    """A vector store that cannot say what it holds, so there is nothing to publish."""

    def __init__(self):
        self.indexed = {}

    def add_document(self, filename, content, classification, department):
        self.indexed[filename] = content
        return True, "indexed"

    def delete_document(self, filename):
        self.indexed.pop(filename, None)


class _BrokenVectorStore(_VectorStore):
    """A store that fails when the publication asks what it holds."""

    def document_chunks(self, filename):
        raise RuntimeError("the collection is unreachable")


def _principal(username="alice", department="finance", role="staff"):
    from app.agents.contracts import Principal

    return Principal.from_user(
        {"id": username, "username": username, "role": role, "department": department}
    )


def _wire(monkeypatch, tmp_path, database, *, vector=None):
    from app.api.v1 import chat
    from app.agents import tools
    from app.documents import catalog
    from app.rag.indexing import IndexPublisher, IndexRegistry, PostgresIndexStore

    vector = vector if vector is not None else _VectorStore()
    monkeypatch.setattr(chat, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(catalog, "DOCUMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(chat, "retriever", vector)
    monkeypatch.setattr(chat, "catalog_database_available", lambda: False, raising=False)
    monkeypatch.setattr(catalog, "_database_available", lambda: False)
    monkeypatch.setattr(chat, "peek_next_document_version", lambda filename: 1)
    monkeypatch.setattr(tools, "rebuild_bm25", lambda: None)
    publisher = IndexPublisher(
        IndexRegistry(tmp_path / "index-versions.json"),
        store=PostgresIndexStore(connection_factory=database.connection, available=lambda: True),
    )
    monkeypatch.setattr(chat, "index_publisher", lambda: publisher)
    return chat, publisher, vector


def _client(chat, principal=None):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    probe = FastAPI()
    probe.include_router(chat.router, prefix="/api/v1")
    if principal is not None:
        @probe.middleware("http")
        async def _attach(request, call_next):
            request.state.principal = principal
            request.state.username = principal.username
            return await call_next(request)
    return TestClient(probe)


def _upload(client, body=b"policy body one\npolicy body two"):
    return client.post(
        "/api/v1/upload",
        files={"file": ("policy.txt", io.BytesIO(body), "text/plain")},
        data={"classification": "2", "department": "finance"},
    )


def _delete(client, filename="policy.txt"):
    return client.delete(f"/api/v1/documents/{filename}")


# --------------------------------------------------------------------- upload
def test_upload_publishes_one_row_in_each_index_table(monkeypatch, tmp_path):
    from app.rag.indexing import document_index_id

    database = FakeIndexDatabase()
    chat, publisher, vector = _wire(monkeypatch, tmp_path, database)
    client = _client(chat, _principal())

    response = _upload(client)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["chunk_count"] == 3
    assert payload["index_publication"]["status"] == "published"
    assert payload["index_publication"]["mirrored"] is True

    index_id = document_index_id("policy.txt")
    registry = database.tables["index_registry"]
    assert list(registry) == [index_id]
    assert registry[index_id]["status"] == "active"
    assert registry[index_id]["resource_type"] == "document"

    versions = database.version_rows()
    assert len(versions) == 1
    version = versions[0]
    assert version["chunk_count"] == 3
    assert version["status"] == "published"
    assert version["backend"] == "chroma"
    assert version["source_version_id"] == "policy.txt|v1"
    assert version["owner_id"] == "alice"
    assert registry[index_id]["current_version_id"] == version["index_version_id"]

    rows = database.chunk_rows()
    assert len(rows) == 3
    assert {row["resource_id"] for row in rows} == {"policy.txt"}
    assert {row["resource_version_id"] for row in rows} == {"policy.txt|v1"}
    assert {row["index_version_id"] for row in rows} == {version["index_version_id"]}
    assert [row["metadata"]["ordinal"] for row in rows] == [0, 1, 2]
    assert [row["content"] for row in rows] == list(vector.chunk_texts)

    resource_versions = database.resource_version_rows()
    assert len(resource_versions) == 1
    resource = resource_versions[0]
    assert (resource["resource_type"], resource["resource_id"], resource["version_id"]) == (
        "document",
        "policy.txt",
        "policy.txt|v1",
    )
    assert resource["owner_id"] == "alice"
    assert resource["status"] == "active"
    assert resource["visibility"] == "private"
    assert resource["department_ids"] == ["finance"]
    # The resource row and the chunk rows must agree: one scope read from the catalog,
    # written twice on purpose so an authorization read cannot miss the chunk write.
    assert resource["classification"] == str(rows[0]["metadata"]["classification"])
    assert resource["metadata"]["department"] == rows[0]["metadata"]["department"]
    assert resource["superseded_at"] is None
    assert {row["resource_version_id"] for row in rows} == {resource["version_id"]}


def test_upload_keeps_scope_in_metadata_and_never_writes_an_embedding(monkeypatch, tmp_path):
    database = FakeIndexDatabase()
    _chat, _publisher, _vector = _wire(monkeypatch, tmp_path, database)
    client = _client(_chat, _principal())

    assert _upload(client).status_code == 200

    row = database.chunk_rows()[0]
    assert row["metadata"]["classification"] == 2
    assert row["metadata"]["department"] == "finance"
    assert row["metadata"]["vector_id"] == "policy.txt_0"
    assert "classification" not in row
    assert "embedding" not in row
    assert database.statements_matching("embedding") == []
    insert = next(sql for sql, _ in database.statements if "insert into chunks" in sql)
    assert "(chunk_id, owner_id, resource_type, resource_id, resource_version_id, index_version_id, content, metadata)" in insert


def test_chunk_count_matches_the_chunk_rows_that_were_written(monkeypatch, tmp_path):
    database = FakeIndexDatabase()
    chat, _publisher, _vector = _wire(monkeypatch, tmp_path, database)
    client = _chat_client(chat)

    response = client.post(
        "/api/v1/upload",
        files={"file": ("policy.txt", io.BytesIO(b"one two three"), "text/plain")},
        data={"classification": "1", "department": "finance"},
    )

    assert response.status_code == 200, response.text
    assert len(database.chunk_rows()) == 3
    assert database.document_chunk_count["policy.txt"] == 3
    assert database.version_chunk_count[("policy.txt", 1)] == 3
    assert database.version_rows()[0]["chunk_count"] == len(database.chunk_rows())


def _chat_client(chat):
    return _client(chat, _principal())


def test_an_unowned_version_is_recorded_without_an_invented_owner(monkeypatch, tmp_path):
    from app.api.v1 import chat

    database = FakeIndexDatabase()
    _chat, _publisher, _vector = _wire(monkeypatch, tmp_path, database)

    response = asyncio.run(chat.upload_document(UploadFile(filename="policy.txt", file=io.BytesIO(b"body"))))

    assert response["status"] == "ok"
    assert response["owner_id"] is None
    row = database.chunk_rows()[0]
    assert row["owner_id"] is None
    assert row["metadata"]["ownership"] == "legacy"
    version = database.version_rows()[0]
    assert version["owner_id"] is None
    assert database.tables["index_registry"][version["index_id"]]["owner_id"] is None
    resource = database.resource_version_rows()[0]
    assert resource["owner_id"] is None
    assert resource["metadata"]["ownership"] == "legacy"


def test_upload_is_not_reported_as_published_when_the_store_cannot_enumerate_chunks(monkeypatch, tmp_path):
    from app.api.v1 import chat

    database = FakeIndexDatabase()
    _wire(monkeypatch, tmp_path, database, vector=_BlindVectorStore())

    response = asyncio.run(chat.upload_document(UploadFile(filename="policy.txt", file=io.BytesIO(b"body"))))

    assert response["status"] == "ok"
    assert response["index_publication"]["status"] == "skipped"
    assert response["index_publication"]["reason"] == "no_indexed_chunks"
    assert response["chunk_count"] == 0
    assert database.chunk_rows() == []
    assert database.version_rows() == []
    assert database.commits == 0


def test_an_unmigrated_index_mirror_degrades_instead_of_failing_the_upload(monkeypatch, tmp_path):
    database = FakeIndexDatabase(migrated=False)
    chat, _publisher, _vector = _wire(monkeypatch, tmp_path, database)
    client = _chat_client(chat)

    response = _upload(client)

    assert response.status_code == 200, response.text
    publication = response.json()["index_publication"]
    assert publication["mirrored"] is False
    assert any("not migrated" in warning for warning in publication["warnings"])
    assert database.tables["index_registry"] == {}


def test_a_missing_chunk_count_column_is_reported_and_not_written(monkeypatch, tmp_path):
    database = FakeIndexDatabase(counters=False)
    chat, _publisher, _vector = _wire(monkeypatch, tmp_path, database)
    client = _chat_client(chat)

    response = _upload(client)

    publication = response.json()["index_publication"]
    assert publication["status"] == "published"
    assert any("migrations/0007" in warning for warning in publication["warnings"])
    assert database.document_chunk_count == {}
    assert database.statements_matching("set chunk_count") == []


# ------------------------------------------------------------------ failure path
@pytest.mark.parametrize(
    "fragment, stage",
    [
        ("insert into resource_versions", "resource_versions"),
        ("insert into chunks", "chunks"),
        ("update index_registry", "publish"),
        ("update document_versions set chunk_count", "chunk_count"),
    ],
)
def test_a_failing_step_rolls_back_and_names_its_stage(monkeypatch, tmp_path, fragment, stage):
    from app.rag.indexing import IndexPublicationError

    database = FakeIndexDatabase()
    database.failures = {fragment: RuntimeError("the mirror refused the write")}
    chat, publisher, vector = _wire(monkeypatch, tmp_path, database)

    vector.add_document("policy.txt", "policy body", 1, "finance")
    publication = chat._document_publication(
        filename="policy.txt",
        version=1,
        owner_id="alice",
        classification=1,
        department="finance",
    )
    assert publication.chunk_count == 3
    with pytest.raises(IndexPublicationError) as exc_info:
        chat._publish_document_index(publication)

    assert exc_info.value.stage == stage
    assert database.rollbacks == 1
    assert database.commits == 0
    assert database.chunk_rows() == []
    assert database.resource_version_rows() == []
    assert database.version_rows() == []
    assert database.tables["index_registry"] == {}
    assert database.version_rows() == []
    assert database.tables["index_registry"] == {}
    assert database.document_chunk_count == {}
    assert database.closes == 1, "the failed publication must not leak its connection"
    with pytest.raises(KeyError):
        publisher.registry.current(publication.index_id)


def test_upload_answers_index_publish_failed_when_the_registry_refuses_to_publish(monkeypatch, tmp_path):
    database = FakeIndexDatabase()
    chat, publisher, _vector = _wire(monkeypatch, tmp_path, database)
    client = _chat_client(chat)

    def refuse(index_version_id):
        raise RuntimeError("the local metadata file is read only")

    monkeypatch.setattr(publisher.registry, "publish", refuse)

    response = _upload(client)

    assert response.status_code == 500, response.text
    body = response.json()["detail"]
    assert body["code"] == "index_publish_failed"
    assert body["retryable"] is True
    assert body["details"]["stage"] == "publish"
    assert body["details"]["filename"] == "policy.txt"
    # Nothing downstream of the failed step was left behind, in the database or on disk.
    assert database.rollbacks == 1
    assert database.chunk_rows() == []
    assert database.version_rows() == []
    assert publisher._current_id("document:policy.txt") is None


# ------------------------------------------------------------------ retirement
def test_delete_retires_the_published_version_and_clears_its_chunks(monkeypatch, tmp_path):
    database = FakeIndexDatabase()
    chat, publisher, vector = _wire(monkeypatch, tmp_path, database)
    client = _client(chat, _principal())

    assert _upload(client).status_code == 200
    published = database.version_rows()[0]

    response = _delete(client)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["index_retirement"]["status"] == "retired"

    assert database.chunk_rows() == []
    versions = {row["index_version_id"]: row for row in database.version_rows()}
    assert versions[published["index_version_id"]]["status"] == "superseded"
    tombstone = [row for key, row in versions.items() if key != published["index_version_id"]][0]
    assert tombstone["status"] == "published"
    assert tombstone["chunk_count"] == 0
    assert tombstone["metadata"]["ownership"] == "owned"
    assert tombstone["metadata"]["retirement"] is True
    assert published["metadata"]["retirement"] is False

    registry = database.tables["index_registry"]["document:policy.txt"]
    assert registry["status"] == "retired"
    assert registry["current_version_id"] == tombstone["index_version_id"]

    resources = database.resource_version_rows()
    assert len(resources) == 1
    assert resources[0]["status"] == "retired"
    assert resources[0]["superseded_at"] == "now"

    assert database.document_chunk_count["policy.txt"] == 0
    assert database.version_chunk_count["policy.txt"] == 0
    assert publisher._retirement_is_pending("document:policy.txt") is False
    assert vector.deletions == ["policy.txt"]


def test_a_document_that_never_published_has_nothing_to_retire(monkeypatch, tmp_path):
    """Retirement describes an existing index version; with none, it must not invent one."""
    database = FakeIndexDatabase()
    chat, publisher, _vector = _wire(monkeypatch, tmp_path, database)

    retirement = chat._document_publication(
        filename="ghost.txt",
        version=1,
        owner_id="alice",
        classification=1,
        department="finance",
        retirement=True,
    )
    outcome = chat._publish_document_index(retirement)

    assert outcome == {
        "status": "skipped",
        "reason": "no_published_index",
        "index_id": retirement.index_id,
        "source_version_id": "ghost.txt|v1",
        "chunk_count": 0,
        "mirrored": False,
        "warnings": [],
    }
    assert database.tables["index_registry"] == {}
    assert database.version_rows() == []
    assert database.commits == 0
    with pytest.raises(KeyError):
        publisher.registry.current(retirement.index_id)


def test_a_retired_index_is_not_retired_a_second_time(monkeypatch, tmp_path):
    database = FakeIndexDatabase()
    chat, _publisher, _vector = _wire(monkeypatch, tmp_path, database)
    client = _client(chat, _principal())

    assert _upload(client).status_code == 200
    assert _delete(client).status_code == 200
    versions_before = len(database.version_rows())
    commits_before = database.commits

    retirement = chat._document_publication(
        filename="policy.txt",
        version=1,
        owner_id="alice",
        classification=1,
        department="finance",
        retirement=True,
    )
    assert chat._publish_document_index(retirement)["reason"] == "no_published_index"
    assert len(database.version_rows()) == versions_before
    assert database.commits == commits_before


def test_a_vector_store_that_cannot_answer_fails_the_publication(monkeypatch, tmp_path):
    database = FakeIndexDatabase()
    _chat, _publisher, _vector = _wire(monkeypatch, tmp_path, database, vector=_BrokenVectorStore())
    client = _client(_chat, _principal())

    response = _upload(client)

    assert response.status_code == 500, response.text
    body = response.json()["detail"]
    assert body["code"] == "index_publish_failed"
    assert body["details"]["stage"] == "chunks"
    assert database.chunk_rows() == []
    assert database.commits == 0


def test_delete_answers_index_publish_failed_when_the_retirement_cannot_be_published(monkeypatch, tmp_path):
    from app.common import auth

    database = FakeIndexDatabase()
    chat, publisher, vector = _wire(monkeypatch, tmp_path, database)
    client = _client(chat, _principal())
    assert _upload(client).status_code == 200
    published_version = database.version_rows()[0]["index_version_id"]

    database.failures = {"delete from chunks": RuntimeError("the mirror is refusing writes")}
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {"id": username, "username": username, "role": "staff", "department": "finance"},
    )

    response = _delete(client)

    assert response.status_code == 500, response.text
    body = response.json()["detail"]
    assert body["code"] == "index_publish_failed"
    assert body["details"]["stage"] == "chunks"
    # The retirement rolled back, so the published version and its chunks are intact.
    assert database.version_rows()[0]["index_version_id"] == published_version
    assert database.version_rows()[0]["status"] == "published"
    assert len(database.chunk_rows()) == 3
    assert database.rollbacks == 1
    # The document was not half removed: its stored file and its catalog row survive.
    assert vector.deletions == ["policy.txt"]
    assert chat.list_document_versions("policy.txt")


def test_each_publication_writes_through_its_own_connection(monkeypatch, tmp_path):
    """The store is process-wide; the transaction is not.

    Two uploads sharing one connection would commit each other's half-written chunks, so
    the mirror has to open and close one connection per publication.
    """
    database = FakeIndexDatabase()
    chat, _publisher, vector = _wire(monkeypatch, tmp_path, database)
    vector.add_document("a.txt", "body", 1, "finance")
    vector.add_document("b.txt", "body", 1, "finance")

    for name in ("a.txt", "b.txt"):
        chat._publish_document_index(
            chat._document_publication(
                filename=name,
                version=1,
                owner_id="alice",
                classification=1,
                department="finance",
            )
        )

    assert database.connections == 2
    assert database.closes == 2
    assert database.commits == 2
    assert len(database.chunk_rows()) == 6
    assert len(database.version_rows()) == 2
