"""Durable audit-journal acceptance tests for the S2 slice (offline only).

These tests never contact PostgreSQL, Redis, or Ollama. The PostgreSQL contract is
verified against the checked-in migration text, and cross-process replay is verified
with two short-lived ``sys.executable`` subprocesses writing to a JSON journal.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from app.common.audit import (
    AUDIT_COLLECTION,
    AuditPersistenceError,
    audit_storage_status,
    clear_audit_events,
    configure_audit_storage,
    get_audit_events,
    hydrate_audit_events,
    purge_expired_audit_events,
    record_audit,
    reset_audit_storage,
)
from app.common.identity import Principal
from app.db.migrations import MIGRATIONS, migration_plan
from app.storage.persistence import (
    JsonPersistenceAdapter,
    PersistenceWriteError,
    _TABLES,
)

ROOT = Path(__file__).resolve().parents[1]

CHILD_SCRIPT = '''
import json
import os
import sys

sys.path.insert(0, sys.argv[3])

from app.common.audit import get_audit_events, record_audit
from app.common.identity import Principal

mode, journal, root = sys.argv[1], sys.argv[2], sys.argv[3]
os.environ["PERSISTENCE_BACKEND"] = "json"
os.environ["PERSISTENCE_FALLBACK_PATH"] = journal

principal = Principal.from_user(
    {"id": 7, "username": "s2-replay", "role": "auditor", "department": "finance"}
)
principal.request_id = "req-replay-1"

if mode == "write":
    event = record_audit(
        principal,
        "resource:view",
        "denied",
        "doc-replay",
        "clearance_insufficient",
        resource_scope={
            "resource_type": "document",
            "resource_id": "doc-replay",
            "department_ids": ["finance"],
            "classification": "confidential",
        },
    )
    print(json.dumps({"event_id": event["event_id"], "persisted": event["persisted"]}))
else:
    replayed = get_audit_events()
    keys = (
        "event_id",
        "action",
        "outcome",
        "reason",
        "request_id",
        "resource",
        "resource_scope",
        "policy_version",
    )
    print(json.dumps([{key: event.get(key) for key in keys} for event in replayed]))
'''


def make_principal(role: str = "staff", username: str = "alice", department: str = "finance"):
    principal = Principal.from_user(
        {"id": 1, "username": username, "role": role, "department": department}
    )
    principal.request_id = "req-test-1"
    return principal


class RecordingAdapter:
    """Minimal adapter stand-in used to inject deterministic backend failures."""

    def __init__(self, *, write_error: Exception | None = None, read_error: Exception | None = None):
        self.records: dict[str, dict] = {}
        self.write_error = write_error
        self.read_error = read_error
        self.writes = 0
        self.reads = 0

    def upsert(self, collection, record_id, record):
        self.writes += 1
        if self.write_error is not None:
            raise self.write_error
        self.records[record_id] = dict(record)
        return dict(record)

    def get(self, collection, record_id):
        value = self.records.get(record_id)
        return dict(value) if value else None

    def list(self, collection):
        self.reads += 1
        if self.read_error is not None:
            raise self.read_error
        return [dict(record) for record in self.records.values()]


@pytest.fixture
def journal(tmp_path, monkeypatch):
    path = tmp_path / "persistence.json"
    monkeypatch.setenv("PERSISTENCE_BACKEND", "json")
    monkeypatch.setenv("PERSISTENCE_FALLBACK_PATH", str(path))
    monkeypatch.delenv("AUDIT_PERSISTENCE", raising=False)
    monkeypatch.delenv("AUDIT_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_audit_storage()
    yield path
    reset_audit_storage()


def stored_records(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get(AUDIT_COLLECTION, {})


def run_child(mode: str, child: Path, journal_path: Path, root: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(child), mode, str(journal_path), str(root)],
        cwd=str(root),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_legacy_signature_still_returns_the_original_keys(journal):
    event = record_audit(make_principal(), "resource:view", "allowed", "doc-1", "owner_match")

    for key in ("timestamp", "username", "role", "action", "resource", "outcome", "reason"):
        assert key in event
    assert event["username"] == "alice"
    assert event["role"] == "staff"
    assert event["persisted"] is True
    assert event["storage_mode"] == "json"


def test_events_survive_a_restart_and_replay_in_order(journal):
    first = record_audit(make_principal(), "resource:view", "allowed", "doc-1", "owner_match")
    second = record_audit(
        make_principal("admin", "root", ""),
        "resource:delete",
        "denied",
        "doc-2",
        "permission_denied",
    )

    assert set(stored_records(journal)) == {first["event_id"], second["event_id"]}

    reset_audit_storage()
    replayed = get_audit_events()

    assert [event["event_id"] for event in replayed] == [first["event_id"], second["event_id"]]
    assert replayed[0]["reason"] == "owner_match"
    assert replayed[1]["outcome"] == "denied"
    assert replayed[1]["request_id"] == "req-test-1"
    assert replayed[1]["persisted"] is True


def test_judgment_chain_replays_across_two_processes(tmp_path, journal):
    child = tmp_path / "audit_child.py"
    child.write_text(CHILD_SCRIPT, encoding="utf-8")

    written = run_child("write", child, journal, ROOT)
    assert written["persisted"] is True

    events = run_child("read", child, journal, ROOT)

    assert [event["event_id"] for event in events] == [written["event_id"]]
    assert events[0]["action"] == "resource:view"
    assert events[0]["outcome"] == "denied"
    assert events[0]["reason"] == "clearance_insufficient"
    assert events[0]["request_id"] == "req-replay-1"
    assert events[0]["resource"] == "doc-replay"
    assert events[0]["policy_version"] == "resource-policy-v2"
    assert events[0]["resource_scope"]["classification"] == "confidential"


def test_injected_write_failure_is_observable_and_never_reports_success(journal, caplog):
    adapter = RecordingAdapter(write_error=PersistenceWriteError("simulated backend outage"))
    configure_audit_storage(persistence=adapter)

    with caplog.at_level(logging.ERROR, logger="enterprise_brain"):
        event = record_audit(make_principal(), "data:query", "allowed", "ds-1", "owner_match")

    assert adapter.writes == 1
    assert event["persisted"] is False
    assert "simulated backend outage" in event["persistence_error"]
    assert any("审计事件持久化失败" in message for message in caplog.messages)
    status = audit_storage_status()
    assert status["write_failures"] == 1
    assert status["persisted_events"] == 0
    assert status["durable"] is True
    assert status["degraded"] is True
    assert status["health"] == "write_failing"
    assert "simulated backend outage" in status["degraded_reason"]
    assert get_audit_events()[0]["event_id"] == event["event_id"]

    with pytest.raises(AuditPersistenceError, match="simulated backend outage"):
        record_audit(
            make_principal(),
            "data:query",
            "denied",
            "ds-2",
            "permission_denied",
            raise_on_write_failure=True,
        )
    assert audit_storage_status()["write_failures"] == 2


def test_read_only_journal_surfaces_a_permission_error(journal, tmp_path, caplog):
    record_audit(make_principal(), "resource:view", "allowed", "doc-1", "owner_match")
    os.chmod(journal, stat.S_IREAD)
    probe = tmp_path / "probe.tmp"
    probe.write_text("{}", encoding="utf-8")
    try:
        os.replace(probe, journal)
        denied = False
    except OSError:
        denied = True
    finally:
        probe.unlink(missing_ok=True)
    if not denied:
        os.chmod(journal, stat.S_IWRITE | stat.S_IREAD)
        pytest.skip("this platform does not deny writes into a read-only journal file")

    try:
        configure_audit_storage()
        with caplog.at_level(logging.ERROR, logger="enterprise_brain"):
            event = record_audit(
                make_principal("admin", "root", ""),
                "resource:delete",
                "allowed",
                "doc-2",
                "permission_granted",
            )
    finally:
        os.chmod(journal, stat.S_IWRITE | stat.S_IREAD)

    assert event["persisted"] is False
    error = event["persistence_error"]
    assert "PersistenceWriteError" in error
    assert any(marker in error for marker in ("WinError", "PermissionError", "Errno 13")), error
    assert any("审计事件持久化失败" in message for message in caplog.messages)
    assert audit_storage_status()["write_failures"] >= 1
    assert get_audit_events()[-1]["persisted"] is False


def test_unreachable_configured_backend_degrades_instead_of_faking_persistence(journal, monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    reset_audit_storage()

    event = record_audit(make_principal(), "resource:view", "denied", "doc-9", "authentication_required")

    assert event["persisted"] is False
    assert "DATABASE_URL" in event["persistence_error"]
    assert event["storage_mode"] == "memory_only"
    status = audit_storage_status()
    assert status["backend"] == "postgres"
    assert status["durable"] is False
    assert status["degraded"] is True
    assert status["mode"] == "memory_only"
    with pytest.raises(AuditPersistenceError, match="DATABASE_URL"):
        record_audit(
            make_principal(),
            "resource:view",
            "denied",
            "doc-9",
            "authentication_required",
            raise_on_write_failure=True,
        )


def test_explicitly_disabled_persistence_is_reported_as_memory_only(journal, monkeypatch):
    monkeypatch.setenv("AUDIT_PERSISTENCE", "disabled")
    reset_audit_storage()

    event = record_audit(make_principal(), "resource:view", "allowed", "doc-1", "owner_match")

    assert event["persisted"] is False
    assert event["storage_mode"] == "memory_only"
    assert not journal.exists()
    assert audit_storage_status()["degraded_reason"] == "AUDIT_PERSISTENCE is disabled"


def test_unreadable_journal_keeps_the_process_view_honest(journal):
    event = record_audit(make_principal(), "resource:view", "allowed", "doc-1", "owner_match")
    journal.write_text("{ this is not json", encoding="utf-8")
    configure_audit_storage()

    assert get_audit_events() == []
    status = audit_storage_status()
    assert status["view_complete"] is False
    assert status["read_failures"] >= 1
    assert status["degraded"] is True

    follow_up = record_audit(
        make_principal(), "resource:view", "denied", "doc-2", "clearance_insufficient"
    )
    assert follow_up["persisted"] is False
    assert [item["event_id"] for item in get_audit_events()] == [follow_up["event_id"]]
    assert event["event_id"] not in [item["event_id"] for item in get_audit_events()]


def test_request_id_scope_and_policy_version_are_recorded_when_supplied(journal):
    event = record_audit(
        make_principal(),
        "data:export",
        "denied",
        "dataset-4",
        "department_scope_denied",
        request_id="req-explicit-9",
        resource_scope={
            "resource_type": "dataset",
            "resource_id": "dataset-4",
            "department_ids": ["hr"],
            "classification": 2,
            "unexpected_blob": "x" * 400,
        },
        policy_version="resource-policy-v3",
    )

    assert event["request_id"] == "req-explicit-9"
    assert event["policy_version"] == "resource-policy-v3"
    assert event["policy_version_source"] == "explicit"
    assert event["resource_scope_source"] == "explicit"
    assert event["resource_scope"]["resource_id"] == "dataset-4"
    assert event["resource_scope"]["department_ids"] == ["hr"]
    assert event["resource_scope"]["_omitted_keys"] == 1
    durable = stored_records(journal)[event["event_id"]]
    assert durable["resource_scope"]["resource_type"] == "dataset"
    assert durable["request_id"] == "req-explicit-9"
    assert durable["policy_version"] == "resource-policy-v3"


def test_scope_is_projected_from_a_resource_scope_object(journal):
    from app.agents.contracts import ResourceScope

    event = record_audit(
        make_principal(),
        "resource:view",
        "allowed",
        "art-1",
        "owner_match",
        resource_scope=ResourceScope(
            resource_type="artifact",
            resource_id="art-1",
            owner_id="1",
            department_ids=["finance"],
            classification="internal",
        ),
    )

    assert event["resource_scope_source"] == "explicit"
    assert event["resource_scope"]["resource_type"] == "artifact"
    assert event["resource_scope"]["classification"] == "internal"


def test_missing_correlation_data_is_left_empty_not_invented(journal):
    principal = Principal.from_user({"id": 5, "username": "ghost", "role": "staff"})

    event = record_audit(principal, "resource:view", "denied", "", "authentication_required")

    assert event["request_id"] == ""
    assert event["resource_scope"] == {}
    assert event["resource_scope_source"] == "unavailable"
    assert event["username"] == "ghost"


def test_summaries_are_bounded_redacted_and_survive_replay(journal):
    event = record_audit(
        make_principal(),
        "data:update",
        "allowed",
        "ds-7",
        "owner_match",
        before_summary={"token": "super-secret", "rows": 120, "note": "y" * 5000},
        after_summary={"rows": 130, "history": [{"jwt": "abc"}, {"jwt": "def"}]},
    )

    assert event["before_summary"]["token"] == "[REDACTED]"
    assert event["before_summary"]["note"].endswith("[truncated len=5000]")
    assert event["after_summary"]["history"]["length"] == 2
    assert event["after_summary"]["history"]["sample"][0]["jwt"] == "[REDACTED]"
    assert "super-secret" not in json.dumps(event)
    assert "super-secret" not in journal.read_text(encoding="utf-8")

    reset_audit_storage()
    replayed = get_audit_events()[-1]
    assert replayed["before_summary"]["token"] == "[REDACTED]"
    assert replayed["after_summary"]["rows"] == 130


def test_retention_window_is_stamped_and_expired_events_are_tombstoned(journal):
    default_event = record_audit(make_principal(), "resource:view", "allowed", "doc-1", "owner_match")
    short_event = record_audit(
        make_principal(),
        "data:export",
        "allowed",
        "ds-1",
        "department_scope_match",
        before_summary={"rows": 12},
        after_summary={"rows": 14},
        retention_days=7,
    )

    assert default_event["retention_days"] == 180
    assert short_event["retention_days"] == 7
    assert short_event["expires_at"] > short_event["created_at"]

    future = datetime.now(timezone.utc) + timedelta(days=30)
    preview = purge_expired_audit_events(future, dry_run=True)
    assert preview["status"] == "ok"
    assert preview["expired"] == 1
    assert preview["purged"] == 0
    assert stored_records(journal)[short_event["event_id"]]["resource"] == "ds-1"

    result = purge_expired_audit_events(future)
    assert result["purged"] == 1
    tombstone = stored_records(journal)[short_event["event_id"]]
    assert tombstone["purged_at"]
    assert tombstone["resource"] == ""
    assert tombstone["before_summary"] == {}
    assert tombstone["actor_username"] == "[REDACTED]"
    assert tombstone["payload"]["purge_reason"] == "retention_window_elapsed"

    assert purge_expired_audit_events(future)["expired"] == 0
    events = {event["event_id"]: event for event in get_audit_events()}
    assert events[short_event["event_id"]]["resource"] == ""
    assert events[default_event["event_id"]]["resource"] == "doc-1"
    assert hydrate_audit_events() == 2


def test_invalid_retention_configuration_falls_back_to_the_default(journal, monkeypatch):
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "not-a-number")

    event = record_audit(make_principal(), "resource:view", "allowed", "doc-1", "owner_match")

    assert event["retention_days"] == 180
    assert audit_storage_status()["retention_days"] == 180


def test_clear_resets_the_view_but_not_the_append_only_journal(journal):
    event = record_audit(make_principal(), "resource:view", "denied", "doc-1", "permission_denied")

    clear_audit_events()

    assert get_audit_events() == []
    assert event["event_id"] in stored_records(journal)
    assert hydrate_audit_events() == 1
    assert get_audit_events()[0]["event_id"] == event["event_id"]


def test_get_audit_events_is_backward_compatible_and_filterable(journal):
    allowed = record_audit(make_principal(), "resource:view", "allowed", "doc-a", "owner_match")
    denied = record_audit(
        make_principal("staff", "bob", "hr"),
        "resource:delete",
        "denied",
        "doc-b",
        "permission_denied",
    )

    assert [event["event_id"] for event in get_audit_events()] == [
        allowed["event_id"],
        denied["event_id"],
    ]
    assert [event["event_id"] for event in get_audit_events(outcome="denied")] == [denied["event_id"]]
    assert [event["event_id"] for event in get_audit_events(username="bob")] == [denied["event_id"]]
    assert [event["event_id"] for event in get_audit_events(action="resource:view")] == [
        allowed["event_id"]
    ]
    assert [event["event_id"] for event in get_audit_events(request_id="req-test-1")] == [
        allowed["event_id"],
        denied["event_id"],
    ]
    assert [event["event_id"] for event in get_audit_events(limit=1)] == [denied["event_id"]]
    assert get_audit_events(username="nobody") == []


def test_audit_collection_contract_matches_the_0005_migration():
    definition = _TABLES[AUDIT_COLLECTION]
    migration = next(item for item in MIGRATIONS if item.name == "audit_events")
    body = migration.sql[migration.sql.index("CREATE TABLE IF NOT EXISTS audit_events") :]
    body = body[: body.index("\n);")]
    declared = [
        line.strip().split()[0]
        for line in body.splitlines()[1:]
        if line.strip() and not line.strip().startswith("--")
    ]

    assert int(migration.version) > 4
    assert migration in migration_plan({})
    assert definition.table == "audit_events"
    assert definition.id_column == "event_id"
    assert definition.order_column == "created_at"
    assert list(definition.columns) == declared
    assert "CREATE INDEX IF NOT EXISTS audit_events_retention_idx" in migration.sql
    assert "CREATE INDEX IF NOT EXISTS audit_events_request_idx" in migration.sql


class FakePostgresConnection:
    """Record the statements the shared adapter emits; never opens a socket."""

    def __init__(self):
        self.statements: list[tuple[str, tuple]] = []
        # Keyed by event_id so the fake reproduces ON CONFLICT (event_id) semantics.
        self.rows: dict[str, tuple] = {}
        self.commits = 0
        self.closes = 0

    def execute(self, sql, params=None):
        self.statements.append((sql, tuple(params or ())))
        if sql.startswith("INSERT INTO audit_events"):
            values = tuple(params or ())
            self.rows[str(values[0])] = values
        return self

    def fetchall(self):
        return list(self.rows.values())

    def fetchone(self):
        rows = list(self.rows.values())
        return rows[0] if rows else None

    def commit(self):
        self.commits += 1

    def close(self):
        self.closes += 1


def _inserted_row(connection: FakePostgresConnection, index: int = -1) -> dict:
    columns = _TABLES[AUDIT_COLLECTION].columns
    inserts = [item for item in connection.statements if item[0].startswith("INSERT INTO audit_events")]
    _, params = inserts[index]
    return dict(zip(columns, params))


def test_postgres_backend_writes_the_declared_columns_offline(journal):
    from app.storage.persistence import PostgresPersistenceAdapter

    connection = FakePostgresConnection()
    configure_audit_storage(persistence=PostgresPersistenceAdapter(lambda: connection))

    event = record_audit(
        make_principal(),
        "resource:view",
        "denied",
        "doc-pg",
        "clearance_insufficient",
        request_id="req-pg-1",
        resource_scope={"resource_type": "document", "resource_id": "doc-pg", "classification": 3},
        before_summary={"rows": 3, "api_key": "super-secret"},
        after_summary={"rows": 0},
    )

    assert event["persisted"] is True
    assert event["storage_mode"] == "postgres"
    assert audit_storage_status()["backend"] == "postgres"
    assert connection.commits >= 1

    insert = next(item for item in connection.statements if item[0].startswith("INSERT INTO audit_events"))
    assert "ON CONFLICT (event_id) DO UPDATE SET" in insert[0]
    for column in _TABLES[AUDIT_COLLECTION].columns:
        assert column in insert[0]

    row = _inserted_row(connection)
    assert row["event_id"] == event["event_id"]
    assert row["request_id"] == "req-pg-1"
    assert row["actor_username"] == "alice"
    assert row["outcome"] == "denied"
    assert row["reason_code"] == "clearance_insufficient"
    assert row["policy_version"] == "resource-policy-v2"
    assert json.loads(row["resource_scope"])["resource_id"] == "doc-pg"
    assert json.loads(row["before_summary"])["api_key"] == "[REDACTED]"
    assert json.loads(row["payload"])["resource"] == "doc-pg"
    assert "super-secret" not in insert[0] + repr(insert[1])
    assert row["retention_days"] == 180
    assert row["expires_at"] > row["created_at"]


def test_postgres_retention_purge_is_tombstoned_offline(journal):
    from app.storage.persistence import PostgresPersistenceAdapter

    connection = FakePostgresConnection()
    configure_audit_storage(persistence=PostgresPersistenceAdapter(lambda: connection))
    event = record_audit(
        make_principal(),
        "data:export",
        "allowed",
        "ds-pg",
        "department_scope_match",
        retention_days=7,
    )

    result = purge_expired_audit_events(datetime.now(timezone.utc) + timedelta(days=30))

    assert result["expired"] == 1
    assert result["purged"] == 1
    row = _inserted_row(connection)
    assert row["event_id"] == event["event_id"]
    assert row["resource"] == ""
    assert row["actor_username"] == "[REDACTED]"
    assert row["expires_at"] is None
    assert json.loads(row["payload"])["purge_reason"] == "retention_window_elapsed"
    assert purge_expired_audit_events(datetime.now(timezone.utc) + timedelta(days=30))["expired"] == 0


def test_adding_the_audit_collection_cannot_change_existing_collections():
    newly_json_encoded = {"resource_scope", "before_summary", "after_summary"}

    for name, definition in _TABLES.items():
        if name == AUDIT_COLLECTION:
            continue
        assert not newly_json_encoded.intersection(definition.columns), name

    assert AUDIT_COLLECTION not in JsonPersistenceAdapter._OWNER_REQUIRED
    assert set(_TABLES[AUDIT_COLLECTION].columns) == newly_json_encoded.union(
        {"event_id", "request_id", "actor_username", "actor_role", "owner_id", "action",
         "resource", "outcome", "reason_code", "policy_version", "payload", "retention_days",
         "expires_at", "created_at"}
    )