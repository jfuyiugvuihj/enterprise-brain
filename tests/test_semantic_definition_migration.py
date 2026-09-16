"""迁移 0009（R15-b）的形状与清单门禁：语义字段回真列，核对状态成为可消除的枚举。

这里的判据全部是静态的：本批评不了容器，也不允许动宿主的 enterprise_brain 库，所以
"这条迁移能在真库上跑通" 是待总控复验项；本文件钉死的是它**声明了什么**、是否被
fail-closed 清单记账、以及应用代码读的列与它声明的列是否一一对得上——后者正是"偷渡读法"
再犯一次时最早会响的警报。
"""
import hashlib
import json
import re
from pathlib import Path

import pytest

from app.db.migrations import (
    _DEFAULT_MIGRATIONS_DIR,
    discover_migrations,
    migration_plan,
)
from app.semantics import registry

MIGRATIONS_DIR = Path(_DEFAULT_MIGRATIONS_DIR)
FILENAME = "0009_metric_definition_semantics.sql"
VERSION = "0009"

# 曾经在 filters JSONB 保留键里偷渡的字段
SMUGGLED_COLUMNS = {
    "metric_name",
    "definition_text",
    "time_granularity",
    "origin",
    "match_terms",
}
VERIFICATION_COLUMNS = {
    "verification_state",
    "verified_document",
    "verified_section",
    "verified_by",
    "verified_at",
    "source_relation_id",
}


def _sql(filename: str) -> str:
    return (MIGRATIONS_DIR / filename).read_text(encoding="utf-8")


def _migration():
    return next(item for item in MIGRATIONS_DIR.glob(f"{VERSION}_*.sql"))


def _added_columns(sql: str) -> set[str]:
    return set(re.findall(r"ADD COLUMN IF NOT EXISTS\s+([a-z_]+)", sql, re.IGNORECASE))


def _table_body(sql: str, table: str) -> str:
    start = sql.index(f"CREATE TABLE IF NOT EXISTS {table}")
    rest = sql[start:]
    return rest[: rest.index("\n);")]


def _declared_columns(body: str) -> set[str]:
    return {
        line.strip().split()[0]
        for line in body.splitlines()[1:]
        if line.strip() and not line.strip().startswith(("--", "CONSTRAINT", "PRIMARY", "UNIQUE"))
    }


def _backfill_statement(sql: str) -> str:
    start = sql.index("WITH smuggled AS")
    return sql[start : sql.index(";", sql.index("WHERE md.metric_definition_id"))]


def _copy_catalog(target: Path) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    for path in MIGRATIONS_DIR.glob("*.sql"):
        (target / path.name).write_bytes(path.read_bytes())
    (target / "manifest.json").write_bytes((MIGRATIONS_DIR / "manifest.json").read_bytes())
    return target


# ------------------------------------------------------------------- 清单记账


def test_0009_is_the_ninth_version_and_is_registered_with_its_own_digest():
    manifest = json.loads(_sql("manifest.json"))
    assert FILENAME in manifest, "0009 必须逐字登记在 manifest.json（migrations/README.md:7-8）"
    assert manifest[FILENAME] == hashlib.sha256(_sql(FILENAME).encode("utf-8")).hexdigest()
    assert manifest[FILENAME] == re.fullmatch(r"[0-9a-f]{64}", manifest[FILENAME]).group(0)

    versions = [item.version for item in migration_plan({})]
    assert versions == [f"{index:04d}" for index in range(1, len(versions) + 1)]
    assert versions[-1] == VERSION, "空账本上它必须排在最后一条，不能插到已发布迁移之前"
    assert _migration().name == f"{VERSION}_metric_definition_semantics.sql"


def test_the_published_migrations_still_match_their_recorded_digests():
    """已发布的 0001–0008 一个字都不许改：改了就等于给存量库换了一份 schema 定义。"""
    manifest = json.loads(_sql("manifest.json"))
    for filename, digest in manifest.items():
        if filename == FILENAME:
            continue
        assert int(filename[:4]) <= 8
        assert digest == hashlib.sha256(_sql(filename).encode("utf-8")).hexdigest(), filename


def test_the_catalog_gate_still_refuses_an_unregistered_or_tampered_file(tmp_path):
    untracked = _copy_catalog(tmp_path / "untracked")
    (untracked / "0010_sneaky.sql").write_text("ALTER TABLE metric_definitions ADD COLUMN sneaky TEXT;\n", encoding="utf-8")
    with pytest.raises(ValueError, match="untracked files"):
        discover_migrations(untracked)

    drift = _copy_catalog(tmp_path / "drift")
    (drift / FILENAME).write_text(_sql(FILENAME) + "\n-- silently edited after review\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        discover_migrations(drift)


# ------------------------------------------------------------------ 列的形状


def test_the_fields_that_used_to_travel_in_jsonb_are_real_columns():
    added = _added_columns(_sql(FILENAME))
    assert SMUGGLED_COLUMNS <= added, added
    assert VERIFICATION_COLUMNS <= added, added
    assert "metric_definitions" in _sql(FILENAME)


def test_the_columns_the_catalog_reads_are_the_columns_the_schema_declares():
    """代码读写的列集必须与 0002 + 0009 声明的列集完全一致——多一列少一列都是漂移。"""
    declared = _declared_columns(_table_body(_sql("0002_execution_data_lineage.sql"), "metric_definitions"))
    declared |= _added_columns(_sql(FILENAME))
    declared -= {"created_at"}  # 只出现在 ORDER BY，不参与读写列集

    assert set(registry._SELECT_COLUMNS) == declared, (
        f"只在代码里: {set(registry._SELECT_COLUMNS) - declared} / 只在库里: {declared - set(registry._SELECT_COLUMNS)}"
    )
    assert registry._INSERT_COLUMNS == registry._SELECT_COLUMNS
    assert "verified_document" not in _table_body(_sql("0002_execution_data_lineage.sql"), "metric_definitions"), (
        "核对字段必须来自 0009，已发布的 0002 不能被就地补列"
    )


def test_verification_state_is_a_closed_enum_and_verified_demands_named_evidence():
    sql = _sql(FILENAME)
    state = re.search(
        r"verification_state\s+IN\s*\(([^)]*)\)", sql, re.IGNORECASE
    )
    assert state, "verification_state 必须有封闭取值域，warning 才谈得上可消除"
    allowed = {item.strip().strip("'") for item in state.group(1).split(",")}
    assert allowed == set(registry.VERIFICATION_STATES)

    evidence = re.search(
        r"metric_definitions_verified_evidence_check(.*?)\n\s*\);", sql, re.IGNORECASE | re.DOTALL
    )
    assert evidence, "verified 必须由证据撑住，否则只是一个自证标记"
    demanded = {column for column in registry.VERIFICATION_EVIDENCE if column in evidence.group(1)}
    assert demanded == set(registry.VERIFICATION_EVIDENCE), demanded
    assert "verification_state <> 'verified'" in evidence.group(1).replace("\n", " ").replace("  ", " ")


def test_the_jsonb_mirror_still_carries_the_label_for_an_application_rollback():
    """写路径保留镜像是刻意的：应用可以回滚，schema 不会跟着回滚。"""
    assert registry.SEMANTICS_KEY == "semantics"
    values = registry._row_values(
        registry._code_definitions()[0], registry.SYSTEM_OWNER_ID, "md:system:x:v1"
    )
    mirror = values["filters"][registry.SEMANTICS_KEY]
    assert mirror["metric_name"] == "\u4f4f\u5bbf\u8d39\u6807\u51c6"
    assert mirror["origin"] == registry.SOURCE_CODE
    assert values["metric_name"] == "\u4f4f\u5bbf\u8d39\u6807\u51c6", "真列必须同时写上，读侧才不必依赖镜像"
    assert values["verification_state"] == registry.UNVERIFIED_STATE
    assert registry.SEMANTICS_KEY not in registry._JSON_COLUMNS
    assert "match_terms" in registry._JSON_COLUMNS


def test_no_verification_field_is_backfilled_or_read_from_the_mirror():
    backfill = _backfill_statement(_sql(FILENAME))
    assert "verification" not in backfill and "verified" not in backfill, (
        "从 JSONB 回填核对状态等于让一行自己给自己发合格证"
    )
    assert "coalesce(md." in backfill and "IS NULL" in backfill, "回填必须只补空列，可重放"


def test_the_migration_is_idempotent_and_destroys_nothing():
    sql = _sql(FILENAME)
    assert sql.count("ADD COLUMN ") == sql.count("ADD COLUMN IF NOT EXISTS")
    assert sql.count("ADD CONSTRAINT ") == sql.count("DROP CONSTRAINT IF EXISTS ")
    assert sql.count("CREATE INDEX ") == sql.count("CREATE INDEX IF NOT EXISTS")
    assert not re.search(r"\bDROP (TABLE|COLUMN|INDEX)\b", sql, re.IGNORECASE)
    assert not re.search(r"\b(DELETE FROM|TRUNCATE)\b", sql, re.IGNORECASE)
    for update in re.finditer(r"UPDATE metric_definitions[\s\S]*?;", sql, re.IGNORECASE):
        assert "WHERE" in update.group(0), "无条件 UPDATE 会让第二次重放覆盖运维改过的行"


# ------------------------------------------------------------------ R15-d


def test_no_graph_database_was_introduced():
    forbidden = ("neo4j", "networkx", "memgraph", "graphdb", "apache-age", "ag_catalog")
    sources = list(Path("app/knowledge_graph").glob("*.py")) + [
        *sorted(MIGRATIONS_DIR.glob("*.sql")),
        Path("pyproject.toml"),
    ]
    for path in sources:
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text, f"{path}: 引入了 {token}"
