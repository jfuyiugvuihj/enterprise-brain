"""The first administrator has to reach the durable user table.

``migrations/0003`` creates ``users`` with no rows and every route that can add a user
already requires a session, so a production deployment booted with no account at all
and no way to create one.
"""

import bcrypt
import pytest


class _Cursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _SchemaDatabase:
    """Records the statements the import-time schema probe issues."""

    def __init__(self, users=None, table_exists=True):
        self.users = list(users or [])
        self.table_exists = table_exists
        self.statements = []

    def execute(self, sql, params=()):
        normalized = " ".join(sql.lower().split())
        self.statements.append(normalized)
        if normalized.startswith("select to_regclass"):
            return _Cursor(row={"table_name": "users"} if self.table_exists else None)
        if normalized.startswith("select count(*) as c from users"):
            return _Cursor(row={"c": len(self.users)})
        if normalized.startswith("insert into users"):
            username, password_hash, role, department = params
            if any(existing["username"] == username for existing in self.users):
                if "on conflict" not in normalized:
                    raise RuntimeError("duplicate key value violates unique constraint")
                return _Cursor()
            self.users.append(
                {
                    "username": username,
                    "password_hash": password_hash,
                    "role": role,
                    "department": department,
                }
            )
            return _Cursor()
        if normalized.startswith(("create table", "alter table")):
            return _Cursor()
        raise AssertionError(f"Unhandled SQL: {sql}")

    def commit(self):
        return None

    def close(self):
        return None


class _Recorder:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(message)

    def warning(self, message):
        self.messages.append(message)

    def error(self, message):
        self.messages.append(message)


@pytest.fixture
def production_auth(monkeypatch):
    from app.common import auth

    monkeypatch.setattr(auth, "_is_production_environment", lambda: True)
    monkeypatch.setattr(auth, "logger", _Recorder())
    monkeypatch.setenv("AUTH_USERNAME", "root")
    monkeypatch.setenv("AUTH_PASSWORD_HASH", "$2b$12$configuredhashisnotarealsecret")
    return auth


def test_production_schema_seeds_the_configured_administrator(production_auth):
    database = _SchemaDatabase()

    production_auth._create_schema(database)

    assert [user["username"] for user in database.users] == ["root"]
    assert database.users[0]["role"] == "admin"
    assert database.users[0]["password_hash"] == "$2b$12$configuredhashisnotarealsecret"


def test_production_seed_leaves_an_operated_user_table_alone(production_auth):
    database = _SchemaDatabase(
        users=[{"username": "ops", "password_hash": "hash", "role": "staff"}]
    )

    production_auth._create_schema(database)

    assert [user["username"] for user in database.users] == ["ops"]


def test_production_seed_refuses_a_missing_user_table(production_auth):
    with pytest.raises(RuntimeError, match="run migrations first"):
        production_auth._create_schema(_SchemaDatabase(table_exists=False))


def test_services_seeding_the_same_database_do_not_clash(production_auth):
    database = _SchemaDatabase()

    production_auth._create_schema(database)
    production_auth._create_schema(database)

    assert len(database.users) == 1


def test_the_seed_can_give_the_administrator_a_department(production_auth, monkeypatch):
    monkeypatch.setenv("AUTH_DEPARTMENT", "finance")

    database = _SchemaDatabase()
    production_auth._create_schema(database)

    assert database.users[0]["department"] == "finance"


def test_the_seed_leaves_the_department_unset_when_the_operator_gives_none(
    production_auth, monkeypatch
):
    monkeypatch.delenv("AUTH_DEPARTMENT", raising=False)

    database = _SchemaDatabase()
    production_auth._create_schema(database)

    assert database.users[0]["department"] is None


def test_the_seed_does_not_log_the_password_hash(production_auth):
    production_auth._create_schema(_SchemaDatabase())

    assert not any(
        "configuredhashisnotarealsecret" in message
        for message in production_auth.logger.messages
    )


def test_missing_bootstrap_credentials_are_refused_in_production(
    production_auth, monkeypatch
):
    monkeypatch.delenv("AUTH_USERNAME")
    monkeypatch.delenv("AUTH_PASSWORD_HASH")

    with pytest.raises(RuntimeError, match="AUTH_USERNAME is required"):
        production_auth._create_schema(_SchemaDatabase())


def test_development_schema_still_seeds_a_default_admin(monkeypatch):
    from app.common import auth

    monkeypatch.setattr(auth, "_is_production_environment", lambda: False)
    monkeypatch.setattr(auth, "logger", _Recorder())
    monkeypatch.delenv("AUTH_USERNAME", raising=False)
    monkeypatch.delenv("AUTH_PASSWORD_HASH", raising=False)
    database = _SchemaDatabase()

    auth._create_schema(database)

    assert [user["username"] for user in database.users] == ["admin"]
    assert bcrypt.checkpw(b"admin123", database.users[0]["password_hash"].encode())
