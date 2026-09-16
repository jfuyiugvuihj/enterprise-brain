"""0008_pending_approvals 与迁移清单的 fail-closed 门禁。

规矩来自 migrations/README.md:7-8：SQL 文件必须逐字登记在 manifest.json 里并带
SHA-256；缺失、多出的文件、改名、空文件、内容漂移一律拒绝。本文件另外钉住两件事：
一是 0008 的列必须能回答"谁批 / 批什么动作 / 什么时候到期"（不是一个 blob），
二是**应用启动**必须走这道校验——校验不过就不许起应用。
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

from app.db.migrations import (
    MIGRATIONS,
    _DEFAULT_MIGRATIONS_DIR,
    discover_migrations,
    migration_plan,
)

MIGRATIONS_DIR = Path(_DEFAULT_MIGRATIONS_DIR)


def _table_body(sql: str, table: str) -> str:
    start = sql.index(f"CREATE TABLE IF NOT EXISTS {table}")
    rest = sql[start:]
    return rest[: rest.index("\n);")]


def _declared_columns(body: str) -> list[str]:
    return [
        line.strip().split()[0]
        for line in body.splitlines()[1:]
        if line.strip() and not line.strip().startswith(("--", "CONSTRAINT", "PRIMARY", "UNIQUE"))
    ]


def _copy_catalog(target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    for path in MIGRATIONS_DIR.glob("*.sql"):
        (target / path.name).write_bytes(path.read_bytes())
    (target / "manifest.json").write_bytes(
        (MIGRATIONS_DIR / "manifest.json").read_bytes()
    )
    return target


# ---------------------------------------------------------------- 清单


def test_every_checked_in_sql_file_is_registered_with_its_own_sha256():
    manifest = json.loads((MIGRATIONS_DIR / "manifest.json").read_text(encoding="utf-8"))
    on_disk = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))

    assert sorted(manifest) == on_disk, (
        "SQL 文件与 manifest.json 必须一一对应（README:7-8）"
    )
    for filename, digest in manifest.items():
        text = (MIGRATIONS_DIR / filename).read_text(encoding="utf-8")
        assert digest == hashlib.sha256(text.encode("utf-8")).hexdigest(), filename


def test_the_recorded_checksum_is_what_the_runner_will_apply():
    for migration in MIGRATIONS:
        assert migration.checksum == hashlib.sha256(
            migration.sql.encode("utf-8")
        ).hexdigest(), migration.name


# ---------------------------------------------------------------- 0008 形状


def test_0008_registers_pending_approvals_as_the_eighth_version():
    names = [migration.name for migration in MIGRATIONS]
    assert "pending_approvals" in names
    migration = next(item for item in MIGRATIONS if item.name == "pending_approvals")

    assert migration.version == "0008"
    assert migration in migration_plan({}), "它必须还在待执行计划里，不是被既往迁移覆盖"


def test_pending_approvals_columns_answer_who_what_and_until_when():
    migration = next(item for item in MIGRATIONS if item.name == "pending_approvals")
    declared = _declared_columns(_table_body(migration.sql, "pending_approvals"))

    # 谁批、哪个会话、批什么动作、什么时候到期/决策，全部是**列**而不是单个 blob
    for column in (
        "session_id",
        "owner_user_id",
        "parked_steps",
        "status",
        "created_at",
        "expires_at",
        "decided_at",
    ):
        assert column in declared, column
    for column in ("request_id", "trace_id", "task_id"):
        assert column in declared, column
    assert declared.count("parked_steps") == 1
    assert "jsonb" in _table_body(migration.sql, "pending_approvals").lower()


def test_pending_approvals_status_domain_is_the_five_documented_states():
    migration = next(item for item in MIGRATIONS if item.name == "pending_approvals")
    body = migration.sql
    check = re.search(
        r"pending_approvals_status_check\s+CHECK\s*\(\s*status\s+IN\s*\(([^)]*)\)",
        body,
        re.IGNORECASE,
    )
    assert check, "status 必须有封闭取值域，面板不能拿到自造状态"
    allowed = {item.strip().strip("'") for item in check.group(1).split(",")}
    assert allowed == {"awaiting", "resumed", "refused", "abandoned", "stale"}


def test_the_pending_list_query_the_panel_uses_is_indexed():
    migration = next(item for item in MIGRATIONS if item.name == "pending_approvals")
    assert (
        "CREATE INDEX IF NOT EXISTS pending_approvals_owner_idx" in migration.sql
    ), "列端点按 (owner_user_id, status) 取自己的待办，缺索引就是全表扫"


# ---------------------------------------------------------------- fail-closed


def test_the_catalog_gate_refuses_a_sql_file_that_is_not_in_the_manifest(tmp_path):
    directory = _copy_catalog(tmp_path / "untracked")
    (directory / "0099_sneaky_change.sql").write_text(
        "ALTER TABLE pending_approvals ADD COLUMN sneaky TEXT;\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="untracked files"):
        discover_migrations(directory)


def test_the_catalog_gate_refuses_an_edited_file_under_an_old_digest(tmp_path):
    directory = _copy_catalog(tmp_path / "drift")
    # 刻意选最早那份（0001）而不是本批新增的：这条钉的是清单机制本身，与 0008 存在与否无关
    target = sorted(directory.glob("*.sql"))[0]
    original = target.read_text(encoding="utf-8")
    target.write_text(original + "\n-- silently edited after review\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        discover_migrations(directory)


def test_the_catalog_gate_refuses_a_manifest_entry_whose_file_vanished(tmp_path):
    directory = _copy_catalog(tmp_path / "missing")
    victim = min(path.name for path in directory.glob("*.sql"))
    (directory / victim).unlink()

    with pytest.raises(ValueError, match="missing files"):
        discover_migrations(directory)


def test_the_catalog_gate_refuses_an_empty_migration(tmp_path):
    directory = _copy_catalog(tmp_path / "empty")
    target = sorted(directory.glob("*.sql"))[0]
    target.write_text("\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must not be empty"):
        discover_migrations(directory)


def test_booting_the_app_verifies_the_catalog_and_refuses_a_broken_one(monkeypatch):
    """应用启动必须过同一道校验：校验不过就不许起应用。"""
    import app.main as main_module

    assert callable(main_module._verify_migration_catalog)
    assert main_module._verify_migration_catalog() == len(MIGRATIONS)

    def refuse(*_args, **_kwargs):
        raise ValueError("migration manifest mismatch (untracked files: 9999_x.sql)")

    monkeypatch.setattr("app.db.migrations.discover_migrations", refuse)
    with pytest.raises(ValueError, match="untracked files"):
        main_module._verify_migration_catalog()


def test_the_catalog_check_runs_at_import_time_not_only_in_the_deploy_runner():
    """`python -c "import app.main"` 就应当被拦住，而不是等运维跑 scripts/migrate.py。"""
    import app.main as main_module

    source = Path(main_module.__file__).read_text(encoding="utf-8")
    assert re.search(r"^_verify_migration_catalog\(\)$", source, re.MULTILINE), (
        "guard 必须在模块顶层被调用，放进函数体就等于没人调用时静默失效"
    )