import pytest


class _Result:
    def __init__(self, table_name):
        self.table_name = table_name

    def fetchone(self):
        return {"table_name": self.table_name}


class _Connection:
    def __init__(self, table_names):
        self.table_names = set(table_names)
        self.statements = []

    def execute(self, statement, params=None):
        statement = str(statement)
        self.statements.append(statement)
        for table_name in self.table_names:
            if table_name in statement:
                return _Result(table_name)
        return _Result(None)

    def commit(self):
        raise AssertionError("production schema checks must not commit runtime DDL")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


@pytest.mark.parametrize(
    ("function_name", "table_names"),
    [
        ("_ensure_sessions_table", {"sessions", "session_messages"}),
        ("_ensure_documents_table", {"documents"}),
    ],
)
def test_chat_production_schema_checks_do_not_execute_runtime_ddl(
    monkeypatch,
    function_name,
    table_names,
):
    from app.api.v1 import chat

    connection = _Connection(table_names)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(chat, "_session_database_available", lambda: True)
    monkeypatch.setattr(chat, "_sess_conn", lambda: connection)

    getattr(chat, function_name)()

    assert any("to_regclass" in statement for statement in connection.statements)
    assert not any(
        statement.lstrip().upper().startswith(("CREATE", "ALTER"))
        for statement in connection.statements
    )


def test_chat_production_session_write_requires_authenticated_owner(monkeypatch):
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "_session_database_available", lambda: True)

    with pytest.raises(RuntimeError, match="authenticated user_id"):
        chat._ensure_session("session-1")
