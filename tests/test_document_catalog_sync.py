from pathlib import Path
import re

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


def test_the_offline_migration_plan_loads_every_version_through_0016():
    """被 C-R13 更新过一轮，R15-b 又更新了一次：钉的是"最新一版是谁"。

    那个字面量必然随每一版过期，所以断言换成一串仍然成立的性质，并且**继续显式钉住
    目录尾号**：将来谁加下一版，必须像 0010（R58 pgvector 双写）、0011（R46 活动信号
    计数）、0012（R183/R184 两本台账的归属列）、0013（R190 放开挂起台账 status 的取值域）、
    0014（R251 告警台账的处置列）、0015（R256 给 dataset_versions 补上的 scope 两列）与 0016（R299
    通知中心的读者生命周期表 notification_states）这七次一样主动改这条，而不是让它静默失去意义。
    0012 那一枚由总控落笔（R58 先例：该写域在施工方之外），0013、0014、0015 与
    0016 这四枚由施工方本人改口——尾号引信留在哪一版手里，下一版就归谁动。
    """
    from app.db.migrations import MIGRATIONS, discover_migrations, migration_plan

    versions = [migration.version for migration in MIGRATIONS]
    assert versions == sorted(versions) and len(set(versions)) == len(versions)
    assert versions[-1] == "0016"
    assert [migration.version for migration in migration_plan({})] == [
        migration.version for migration in MIGRATIONS
    ]
    # The manifest checksums are what make this load at all; a drifted file raises here.
    assert discover_migrations() == MIGRATIONS
