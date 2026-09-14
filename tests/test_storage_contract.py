from contextlib import nullcontext
import json
from pathlib import Path

import pytest

from app.db.connection import parse_database_settings
from app.db.migrations import (
    apply_migrations,
    discover_migrations,
    migration_lock_key,
    migration_plan,
)
from app.storage.local import LocalFileStorage


def test_database_settings_validate_without_connecting():
    settings = parse_database_settings("postgresql://user:pass@db.example:5432/brain?sslmode=require")
    assert settings.is_postgresql is True
    assert settings.host == "db.example"
    assert settings.database == "brain"
    assert settings.sslmode == "require"


def test_database_settings_reject_non_postgres_urls():
    with pytest.raises(ValueError):
        parse_database_settings("sqlite:///tmp/app.db")


def test_migration_catalog_is_versioned_checksums_are_stable_and_lock_key_is_scoped():
    migrations = discover_migrations()
    manifest_path = Path(__file__).parents[1] / "migrations" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert [migration.version for migration in migrations] == ["0001", "0002", "0003", "0004"]
    assert migrations[0].name == "core_resource_versions"
    assert manifest["0001_core_resource_versions.sql"] == migrations[0].checksum
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in migrations[0].sql
    assert "CREATE TABLE IF NOT EXISTS resource_versions" in migrations[0].sql
    assert migrations[1].name == "execution_data_lineage"
    for table_name in (
        "datasets",
        "dataset_versions",
        "calculation_runs",
        "agent_runs",
        "agent_steps",
        "tool_calls",
        "model_calls",
        "retrieval_traces",
        "trace_events",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in migrations[1].sql
    assert "ALTER TABLE artifacts" in migrations[1].sql
    assert migrations[2].name == "legacy_runtime_tables"
    for table_name in (
        "users",
        "sessions",
        "session_messages",
        "document_versions",
        "alert_rules",
        "alerts",
        "memories",
        "user_profiles",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in migrations[2].sql
    assert migrations[3].name == "legacy_runtime_compatibility"
    assert "ADD COLUMN IF NOT EXISTS title TEXT" in migrations[3].sql
    assert "ADD COLUMN IF NOT EXISTS updated_at TEXT" in migrations[3].sql
    assert "ADD COLUMN IF NOT EXISTS steps TEXT" in migrations[3].sql
    assert "CREATE TABLE IF NOT EXISTS documents" in migrations[3].sql

    assert migration_plan({}, migrations=migrations) == list(migrations)
    assert migration_plan(
        {migrations[0].version: migrations[0].checksum},
        migrations=migrations,
    ) == [migrations[1], migrations[2], migrations[3]]
    with pytest.raises(ValueError, match="checksum mismatch"):
        migration_plan({migrations[0].version: "incorrect"}, migrations=migrations)
    with pytest.raises(TypeError, match="checksums must be a mapping"):
        migration_plan({migrations[0].version}, migrations=migrations)
    with pytest.raises(TypeError, match="checksums must be a mapping"):
        migration_plan(set(), migrations=migrations)

    assert migration_lock_key("brain").endswith(":brain")
    with pytest.raises(ValueError):
        migration_lock_key("")


def test_legacy_sessions_migration_adds_owner_column_before_its_index():
    migration = next(
        item for item in discover_migrations() if item.name == "legacy_runtime_tables"
    )
    owner_column_sql = (
        "ALTER TABLE IF EXISTS sessions\n"
        "    ADD COLUMN IF NOT EXISTS user_id TEXT;"
    )
    session_index_sql = (
        "CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id, created_at DESC);"
    )

    assert owner_column_sql in migration.sql
    assert migration.sql.index(owner_column_sql) < migration.sql.index(session_index_sql)


def test_migration_executor_uses_a_transaction_lock_and_records_the_checksum():
    migrations = discover_migrations()

    class Result:
        def fetchall(self):
            return []

    class Connection:
        def __init__(self):
            self.calls = []

        def transaction(self):
            return nullcontext()

        def execute(self, query, params=None):
            self.calls.append((query, params))
            return Result()

    connection = Connection()
    applied = apply_migrations(connection, "brain", migrations=migrations)

    assert applied == list(migrations)
    assert "pg_advisory_xact_lock" in connection.calls[0][0]
    assert connection.calls[0][1] == (migration_lock_key("brain"),)
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in connection.calls[1][0]
    assert "CREATE EXTENSION IF NOT EXISTS vector" in connection.calls[3][0]
    assert connection.calls[-1][1] == (
        migrations[-1].version,
        migrations[-1].name,
        migrations[-1].checksum,
    )


def test_local_storage_uses_resource_id_and_atomic_replace(tmp_path: Path):
    storage = LocalFileStorage(tmp_path / "files")
    first = storage.write_bytes("resource-1", b"first", ".bin")
    second = storage.write_bytes("resource-1", b"second", ".bin")

    assert first.path == second.path
    assert storage.read_bytes("resource-1", ".bin") == b"second"
    assert second.size == 6
    assert storage.delete("resource-1", ".bin") is True
    assert storage.delete("resource-1", ".bin") is False


def test_local_storage_rejects_path_traversal_and_filename_ids(tmp_path: Path):
    storage = LocalFileStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.write_bytes("../escape", b"bad")
    with pytest.raises(ValueError):
        storage.write_bytes("client/name.txt", b"bad")
