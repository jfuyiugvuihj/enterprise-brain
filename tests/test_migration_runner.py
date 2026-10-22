from __future__ import annotations


def test_migration_runner_requires_database_url(monkeypatch):
    from scripts.migrate import main

    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main([]) == 2


def test_migration_runner_applies_catalog(monkeypatch):
    from scripts import migrate

    observed = {}

    class Connection:
        def close(self):
            observed["closed"] = True

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example/brain")
    monkeypatch.setattr(migrate, "open_connection", lambda settings: Connection())
    monkeypatch.setattr(
        migrate,
        "apply_migrations",
        lambda connection, database_name: observed.update(
            connection=connection,
            database_name=database_name,
        ) or [],
    )

    assert migrate.main([]) == 0
    assert observed["database_name"] == "brain"
    assert observed["closed"] is True


def test_migration_runner_reports_database_failure(monkeypatch, capsys):
    from scripts import migrate

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example/brain")
    monkeypatch.setattr(migrate, "open_connection", lambda _settings: (_ for _ in ()).throw(RuntimeError("vector missing")))

    assert migrate.main([]) == 1
    assert "database connection failed" in capsys.readouterr().err
