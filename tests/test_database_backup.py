from pathlib import Path


def test_backup_database_uses_pg_dump_environment_without_url_in_arguments(tmp_path, monkeypatch):
    from scripts import backup_database

    observed = {}

    def fake_run(command, *, env, check):
        observed["command"] = command
        observed["env"] = env
        observed["check"] = check
        Path(command[command.index("--file") + 1]).write_bytes(b"backup")

    monkeypatch.setattr(backup_database.subprocess, "run", fake_run)

    output = tmp_path / "database.dump"
    backup_database.backup_database(
        "postgresql://backup_user:secret@127.0.0.1:5432/enterprise_brain",
        output,
        pg_dump_path="pg_dump.exe",
    )

    assert observed["command"] == [
        "pg_dump.exe",
        "--format=custom",
        "--file",
        str(output),
        "enterprise_brain",
    ]
    assert observed["env"]["PGHOST"] == "127.0.0.1"
    assert observed["env"]["PGPORT"] == "5432"
    assert observed["env"]["PGUSER"] == "backup_user"
    assert observed["env"]["PGPASSWORD"] == "secret"
    assert "postgresql://" not in " ".join(observed["command"])
    assert output.read_bytes() == b"backup"
