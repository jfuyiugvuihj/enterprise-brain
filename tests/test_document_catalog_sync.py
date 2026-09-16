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


# ------------------------------------------------- chunk bookkeeping (migration 0007)
def _migration(version: str):
    from app.db.migrations import MIGRATIONS

    return next(migration for migration in MIGRATIONS if migration.version == version)


def _statements(version: str) -> list[str]:
    """Executable statements only: the commentary explains intent, it is not SQL."""
    lines = [line for line in _migration(version).sql.splitlines() if not line.strip().startswith("--")]
    return [" ".join(statement.split()).lower() for statement in "\n".join(lines).split(";") if statement.strip()]


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


def test_the_offline_migration_plan_loads_every_version_through_0008():
    """被 C-R13 更新：原来这条叫 ..._accepts_0007，钉的是"0007 是最新一版"。

    0008 落地后那个字面量必然过期，所以断言换成一串仍然成立的性质，并且**继续显式钉住
    目录尾号**：将来谁加 0009，必须像这次一样主动改这条，而不是让它静默失去意义。
    """
    from app.db.migrations import MIGRATIONS, discover_migrations, migration_plan

    versions = [migration.version for migration in MIGRATIONS]
    assert versions == sorted(versions) and len(set(versions)) == len(versions)
    assert versions[-1] == "0008"
    assert [migration.version for migration in migration_plan({})] == [
        migration.version for migration in MIGRATIONS
    ]
    # The manifest checksums are what make this load at all; a drifted file raises here.
    assert discover_migrations() == MIGRATIONS
