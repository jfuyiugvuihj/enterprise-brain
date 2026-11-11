import pytest


class _Result:
    def __init__(self, table_name):
        self._table_name = table_name

    def fetchone(self):
        return {"table_name": self._table_name}


class _Connection:
    def __init__(self, table_names):
        if isinstance(table_names, (set, list, tuple)):
            self.table_names = set(table_names)
        elif table_names:
            self.table_names = {table_names}
        else:
            self.table_names = set()
        self.statements = []

    def execute(self, statement, params=None):
        self.statements.append(statement)
        text = str(statement)
        for table_name in self.table_names:
            if table_name in text:
                return _Result(table_name)
        return _Result(None)

    def commit(self):
        raise AssertionError("production schema checks must not commit runtime DDL")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


@pytest.mark.parametrize(
    ("module_name", "table_name"),
    [
        ("app.memory.long_term", "memories"),
        ("app.memory.profile", "user_profiles"),
        ("app.documents.catalog", "document_versions"),
        ("app.api.v1.alerts", {"alert_rules", "alerts"}),
    ],
)
def test_production_memory_schema_checks_do_not_execute_runtime_ddl(monkeypatch, module_name, table_name):
    module = __import__(module_name, fromlist=["_ensure"])
    connection = _Connection(table_name)

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(module, "_initialized", False, raising=False)
    monkeypatch.setattr(module, "_conn", lambda: connection)

    module._ensure()

    assert any("to_regclass" in statement for statement in connection.statements)
    assert not any(
        statement.lstrip().upper().startswith(("CREATE", "ALTER"))
        for statement in connection.statements
    )


@pytest.mark.parametrize(
    ("module_name", "table_name"),
    [
        ("app.memory.long_term", None),
        ("app.memory.profile", None),
        ("app.documents.catalog", None),
        ("app.api.v1.alerts", None),
    ],
)
def test_production_memory_schema_requires_migration(monkeypatch, module_name, table_name):
    module = __import__(module_name, fromlist=["_ensure"])
    connection = _Connection(table_name)

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(module, "_initialized", False, raising=False)
    monkeypatch.setattr(module, "_conn", lambda: connection)

    with pytest.raises(RuntimeError, match="run migrations first"):
        module._ensure()
