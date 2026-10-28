from pathlib import Path
import re

from fastapi.testclient import TestClient

from test_alert_scan_scope import alert_pg


def test_doc_panel_uses_catalog_endpoint():
    source = Path("frontend/src/components/DocPanel.vue").read_text(encoding="utf-8")

    assert "/documents/catalog" in source
    assert 'axios.get(`${API}/documents`' not in source


def test_document_catalog_route_returns_metadata(monkeypatch, tmp_path, alert_pg):
    from app.documents import catalog
    from app.rag import pg_store
    from app.common import auth
    from app.common.auth import create_token
    from app.main import app

    monkeypatch.setattr(pg_store, '_connect', lambda *args, **kwargs: alert_pg())
    monkeypatch.setattr(catalog, '_conn', alert_pg)
    monkeypatch.setattr(catalog, '_initialized', True)
    monkeypatch.setattr(catalog, '_db_available', True)
    monkeypatch.setenv('EMBEDDING_MODEL', 'isolated-alert-test')
    monkeypatch.setenv('EMBEDDING_DIMENSION', '8')
    file = tmp_path / 'policy.txt'
    file.write_text('Synthetic catalog acceptance', encoding='utf-8')
    catalog.record_document_version('policy.txt', 1, 'finance', str(file), owner_id='document-owner')
    monkeypatch.setattr(auth, 'get_user', lambda username: {
        'id':username, 'username':username, 'role':'admin', 'department':'finance'})
    client = TestClient(app)
    headers = {'Authorization':f'Bearer {create_token("admin")}'}
    response = client.get('/api/v1/documents/catalog', headers=headers)
    assert response.status_code == 200
    row = response.json()['documents'][0]
    assert (row['filename'], row['classification'], row['department']) == ('policy.txt', 1, 'finance')

    def unavailable(*args, **kwargs):
        raise ConnectionError('isolated storage outage')
    monkeypatch.setattr(pg_store, '_connect', unavailable)
    denied = client.get('/api/v1/documents/catalog', headers=headers)
    assert denied.status_code == 503 and denied.json()['detail'] == 'storage_unavailable'


# ------------------------------------------------- chunk bookkeeping (migration 0007)
def _migration(version: str):
    from app.db.migrations import MIGRATIONS

    return next(migration for migration in MIGRATIONS if migration.version == version)


_COMMENT_LINE = re.compile(r"^[ \t]*--.*$", re.MULTILINE)


def split_statements(sql: str) -> list[str]:
    """Cut SQL into statements the way PostgreSQL reads it: a ``;`` inside a quoted literal is
    not a statement terminator, so prose in a ``COMMENT ON ... IS '...'`` must not split one
    migration in two. R251 hit exactly this on 0014 and answered it by deleting the semicolon
    from its own literal (T-9 of tests/test_r251_alert_disposal_migration.py); R256 fixed the
    cutter instead, because the next migration should not have to be written around a tool.
    """
    parts: list[str] = []
    current: list[str] = []
    in_string = False
    index = 0
    while index < len(sql):
        char = sql[index]
        if char == "'":
            if in_string and sql[index + 1 : index + 2] == "'":
                current.append("''")
                index += 2
                continue
            in_string = not in_string
        if char == ";" and not in_string:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    assert not in_string, "an unclosed string literal: this cut is not defined on it"
    return [part for part in parts if part.strip()]


def _statements(version: str) -> list[str]:
    """Executable statements only: the commentary explains intent, it is not SQL."""
    body = _COMMENT_LINE.sub("", _migration(version).sql)
    return [" ".join(statement.split()).lower() for statement in split_statements(body)]


def test_0007_adds_a_nullable_chunk_count_to_both_catalog_tables():
    statements = _statements("0007")

    assert _migration("0007").name == "document_chunk_count"
    assert sum("add column if not exists chunk_count" in statement for statement in statements) == 2
    assert any(statement.startswith("alter table if exists documents") for statement in statements)
    assert any(
        statement.startswith("alter table if exists document_versions") for statement in statements
    )
    # NULL means "never published a count"; 0 means "published an empty index". A NOT NULL
    # default would make every historical row claim the second one.
    assert not [item for item in statements if "chunk_count integer not null" in item]
    assert not [item for item in statements if "default 0" in item]


def test_0007_stays_additive_and_never_touches_the_vector_column():
    statements = _statements("0007")

    assert not [statement for statement in statements if statement.startswith("create table")]
    assert all("if exists" in statement or "if not exists" in statement for statement in statements)
    assert not [
        statement
        for statement in statements
        if "chunks" in statement and "add column" in statement
    ], "chunks keeps its column set: classification and department belong in metadata"
    joined = " ".join(statements)
    assert "embedding" not in joined
    assert "vector(" not in joined
    assert "hnsw" not in joined
    assert "ivfflat" not in joined


def test_0007_lets_the_owner_be_absent_in_every_mirrored_table():
    statements = _statements("0007")
    relaxed = {
        statement.split()[4]
        for statement in statements
        if "alter column owner_id drop not null" in statement
    }

    assert relaxed == {
        "chunks",
        "index_registry",
        "index_versions",
        # resource_versions is not an index table but the authorization view of one stored
        # version, and the index mirror writes the owner it read from the catalog. A legacy
        # document has no owner, and the ownership slice forbids inventing one, so NULL here
        # reads as legacy-not-public rather than as a row anyone may reach.
        "resource_versions",
    }
    # Everything the migration touches is an additive statement against a table that may
    # not exist yet, so re-running it against a migrated database stays a no-op.
    assert all(
        statement.startswith("alter table if exists") or statement.startswith("create index if not exists")
        for statement in statements
    )


def test_offline_migration_plan_loads_the_discovered_catalog():
    """All discovered migrations load and enter an empty database's plan."""
    from app.db.migrations import MIGRATIONS, discover_migrations, migration_plan

    versions = [migration.version for migration in MIGRATIONS]
    assert versions == sorted(versions) and len(set(versions)) == len(versions)
    assert [migration.version for migration in migration_plan({})] == [
        migration.version for migration in MIGRATIONS
    ]
    # The manifest checksums are what make this load at all; a drifted file raises here.
    assert discover_migrations() == MIGRATIONS
