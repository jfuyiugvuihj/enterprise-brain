"""R249 判据 J-3 / J-4 —— 列对齐的静态钉，与 JSON 写点归零。

J-3 拿 ``migrations/0002_execution_data_lineage.sql`` 的建表体**加上其后每一版点名本表的
ADD COLUMN**（0015 起真有这样一版）当事实源，与
`DatasetRecord` / `DatasetVersionRecord` 的字段集**双向**比对：表多一列、记录多一字段都算红。
顺带把 CAST 家族（jsonb / timestamptz / date）与 DDL 列类型对齐，否则 `%s::jsonb` 可以指着
一列 TEXT 而不被任何人发现。

J-4 用 AST 数本模块里的 JSON 写点（写模式打开、write_text/write_bytes、mkstemp、os.replace、
json.dump 全算），要求为 0；读模式允许（一次性导入与哈希都得读）。行为半边钉住"读得到、写不回"。

不起服务、不连库：这两枚钉都是静态加内存表的读数。
"""
from __future__ import annotations

import ast
import dataclasses
import json
import re
from pathlib import Path

import pytest

from app.agents.contracts import Principal
from app.db.migrations import MIGRATIONS
from app.storage import datasets as dataset_storage
from app.storage.datasets import (
    DATASET_TABLE,
    DATASET_VERSION_TABLE,
    DatasetRecord,
    DatasetRegistry,
    DatasetVersionRecord,
    DatasetRowConflict,
    InMemoryDatasetTableStore,
    UnknownDatasetTable,
)
from test_r183_184_migration_pair import (  # noqa: T401  共用那把认字面量的语句切刀
    executable_statements,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = REPO_ROOT / "migrations" / "0002_execution_data_lineage.sql"
MODULE_PATH = REPO_ROOT / "app" / "storage" / "datasets.py"
_OWNER = {"id": "u-r249-cols", "username": "r249-cols", "role": "manager", "department": "finance"}


def _create_table_sql(table: str) -> str:
    source = MIGRATION.read_text(encoding="utf-8")
    marker = f"CREATE TABLE IF NOT EXISTS {table} ("
    start = source.index(marker) + len(marker)
    depth = 1
    for index in range(start, len(source)):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                return source[start:index]
    raise AssertionError(f"{table} 的建表语句没读完")


#: 建表体之后的前滚迁移给本表补上的列：``ALTER TABLE ... ADD COLUMN IF NOT EXISTS 列 类型``。
_ADD_COLUMN = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?P<table>\w+)\s+ADD\s+COLUMN\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?(?P<column>\w+)\s+(?P<definition>.+)",
    re.IGNORECASE | re.DOTALL,
)
#: 这两张表的出生地。比它新的每一版都可能有补列的语句。
BASE_VERSION = "0002"


def _added_columns(table: str) -> list[tuple[str, str]]:
    """``0002`` 之后每一版里点名本表的 ``ADD COLUMN``，按版次与语句次序排列。

    R256 起这枚钉不能只读建表体：``dataset_versions`` 的 scope 两列由迁移 0015 前滚补上，而
    建表体永远停在 0002 那一版。只读建表体的钉会得出两种假话——「记录多了两个字段」或「表里
    少了两列」，取决于先动哪一头。切语句用 ``test_r183_184_migration_pair`` 那把认字面量的刀，
    与 0012/0014 那批件同一把：散文里的分号不该把一枚 ``ADD COLUMN`` 切成两半。
    """
    added: list[tuple[str, str]] = []
    for item in MIGRATIONS:
        if item.version <= BASE_VERSION:
            continue
        for statement in executable_statements(item.sql):
            match = _ADD_COLUMN.match(statement.strip())
            if match is None or match.group("table").lower() != table:
                continue
            added.append((match.group("column").lower(), " ".join(match.group("definition").split())))
    return added


def _ddl_columns(table: str) -> list[tuple[str, str]]:
    """``[(column, type)]`` in declared order, skipping table-level constraints.

    声明次序 = 建表体的次序 ＋ 每一版 ``ADD COLUMN`` 的次序，也就是 PostgreSQL 里
    ``attnum`` 的次序。``DatasetVersionRecord`` 那两枚新字段排在末尾，正是为了对上这句话。
    """
    rows: list[tuple[str, str]] = []
    for line in _create_table_sql(table).splitlines():
        line = line.strip().rstrip(",")
        if not line or is_constraint(line):
            continue
        name, _, rest = line.partition(" ")
        rows.append((name, rest.strip()))
    return rows + _added_columns(table)


TABLE_LEVEL_CONSTRAINTS = ("PRIMARY KEY", "UNIQUE", "CHECK", "CONSTRAINT", "FOREIGN KEY")


def is_constraint(line: str) -> bool:
    """Skip the table-level constraint lines: they start with a keyword, not a column name."""
    return any(line.upper().startswith(word) for word in TABLE_LEVEL_CONSTRAINTS)


def _record_columns(record: type) -> tuple[str, ...]:
    return tuple(field.name for field in dataclasses.fields(record))


# ================================================================= J-3 列对齐静态钉


@pytest.mark.parametrize(
    "table, record, declared",
    [
        (DATASET_TABLE, DatasetRecord, dataset_storage.DATASET_COLUMNS),
        (DATASET_VERSION_TABLE, DatasetVersionRecord, dataset_storage.DATASET_VERSION_COLUMNS),
    ],
)
def test_record_fields_and_table_columns_agree_both_ways(table, record, declared) -> None:
    """字段集 ↔ 列集：任一侧多出来的成员都必须让这条件变红。"""
    columns = [name for name, _type in _ddl_columns(table)]

    assert set(columns) - set(_record_columns(record)) == set(), (
        f"{table} 有列而 {record.__name__} 没字段：{sorted(set(columns) - set(_record_columns(record)))}"
    )
    assert set(_record_columns(record)) - set(columns) == set(), (
        f"{record.__name__} 有字段而 {table} 没列：{sorted(set(_record_columns(record)) - set(columns))}"
    )
    assert len(columns) == len(_record_columns(record)) == len(declared)
    assert declared == tuple(columns), "写 INSERT 的顺序就是建表声明的顺序，漂移要响"


@pytest.mark.parametrize(
    "table, record",
    [(DATASET_TABLE, DatasetRecord), (DATASET_VERSION_TABLE, DatasetVersionRecord)],
)
def test_cast_families_match_the_declared_column_types(table, record) -> None:
    """每一条显式 CAST 都指着它声称的那一列类型，反向也不许漏一列。"""
    declared = set(_record_columns(record))
    typed = {
        "jsonb": {name for name, body in _ddl_columns(table) if body.upper().startswith("JSONB")},
        "timestamptz": {
            name for name, body in _ddl_columns(table) if "TIMESTAMPTZ" in body.upper()
        },
        "date": {name for name, body in _ddl_columns(table) if body.upper().startswith("DATE")},
    }
    families = {
        "jsonb": set(dataset_storage._JSON_COLUMNS) & declared,
        "timestamptz": set(dataset_storage._TIMESTAMP_COLUMNS) & declared,
        "date": set(dataset_storage._DATE_COLUMNS) & declared,
    }
    for kind, columns in typed.items():
        assert columns == families[kind], f"{table}：{kind} 列 {sorted(columns)} 与 CAST 家族 {sorted(families[kind])} 不等"


def test_the_store_refuses_a_table_it_does_not_own() -> None:
    """登记表只有两张：第三条名字是笔误，也是没人签字的新写点，必须是失败而不是空表。"""
    store = InMemoryDatasetTableStore()

    with pytest.raises(UnknownDatasetTable):
        store.select("artifacts")
    with pytest.raises(UnknownDatasetTable):
        store.apply([("agent_runs", {"agent_run_id": "run-1"}, "insert")])


def test_a_row_cannot_carry_a_column_the_table_does_not_have() -> None:
    """把字段写进表里没有的列，是"改了记录就等于改了表"这种自欺，静态钉抓不住，这条抓。"""
    store = InMemoryDatasetTableStore()

    with pytest.raises(ValueError, match="columns the table does not have"):
        store.apply([(DATASET_TABLE, {"dataset_id": "d1", "not_a_column": 1}, "insert")])


def test_the_uniqueness_rules_of_the_ddl_are_enforced_not_assumed(tmp_path) -> None:
    """主键、`datasets (filename) WHERE active`、`dataset_versions (dataset_id, version_number)` 三条都要拦得住。"""
    store = InMemoryDatasetTableStore()
    path = tmp_path / "sales.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    registry = DatasetRegistry(root=tmp_path, store=store)
    record = registry.register(path, principal=Principal.from_user(_OWNER))
    row = dataclasses.asdict(record)

    with pytest.raises(DatasetRowConflict, match="primary key"):
        store.apply([(DATASET_TABLE, row, "insert")])
    with pytest.raises(DatasetRowConflict, match="datasets_active_filename_idx"):
        twin = {**row, "dataset_id": "twin", "current_version_id": "twin:v1"}
        store.apply([(DATASET_TABLE, twin, "insert")])
    with pytest.raises(DatasetRowConflict, match="version_number"):
        dupe = {
            "dataset_version_id": f"{record.dataset_id}:v1-dupe",
            "dataset_id": record.dataset_id,
            "owner_id": record.owner_id,
            "version_number": 1,
            "storage_key": row["storage_key"],
            "content_sha256": row["content_sha256"],
            "status": "active",
        }
        store.apply([(DATASET_VERSION_TABLE, dupe, "insert")])


# ===================================================================== J-4 JSON 写点


_WRITE_MODES = ("w", "a", "x", "+")


def _open_mode_literal(node: ast.Call) -> str | None | bool:
    """The mode of an ``open`` call: ``path.open(\"rb\")`` and ``open(path, \"rb\")`` are different arities.

    ``None`` means no mode was written at all -- which for both shapes is the library default
    ``"r"``, i.e. a read. ``False`` means a mode exists but is not a literal this pin can read,
    and an unreadable mode is treated as a write site: a pin that only catches the obvious
    spelling is a pin that gets walked through.
    """
    args = node.args
    offset = 1 if isinstance(node.func, ast.Attribute) else 0
    if len(args) > offset and isinstance(args[offset], ast.Constant):
        return str(args[offset].value)
    for keyword in node.keywords:
        if keyword.arg == "mode":
            if isinstance(keyword.value, ast.Constant):
                return str(keyword.value)
            return False
    if args and not isinstance(args[offset - 1 if offset else 0], ast.Constant):
        return False
    return None


def _json_write_sites(path: Path) -> list[str]:
    """AST 数写点：写模式打开、write_text/write_bytes、mkstemp、os.replace、json.dump、copy。

    读模式不算（``path.open(\"rb\")`` 算哈希、``read_text`` 读遗留台账，两条都是 J-4 允许的那一半）；
    ``mkdir`` 不算（它建目录，不动 JSON 内容）。``json.dumps`` 不算 —— 它是把值序列化成 SQL
    参数，落不落盘不归它管；``json.dump`` 才算，它需要一个打开的文件。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    sites: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if name == "open":
            mode = _open_mode_literal(node)
            if mode is False:
                sites.append(f"line {node.lineno}: open(...) 的模式读不出来")
            elif mode and any(character in mode for character in _WRITE_MODES):
                sites.append(f"line {node.lineno}: open(..., {mode!r})")
        elif name in {"write_text", "write_bytes", "touch"}:
            sites.append(f"line {node.lineno}: {name}()")
        elif name in {"mkstemp", "NamedTemporaryFile", "dump", "copy", "copyfile", "replace", "truncate"}:
            sites.append(f"line {node.lineno}: {name}()")
    return sites


def test_datasets_module_has_zero_json_write_sites() -> None:
    """写模式 0、读模式允许（同 R248 口径）：JSON 台账从这一文件里正式退役。"""
    sites = _json_write_sites(MODULE_PATH)

    assert sites == [], f"app/storage/datasets.py 仍有 {len(sites)} 枚写点：{sites}"


def test_the_module_no_longer_builds_a_json_persistence_ledger() -> None:
    """`_save` 与 `_persistence_row` 这类镜像写法不许留下尸体，否则退役只是改了个名字。"""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

    assert "_save" not in names, names
    assert "_persistence_row" not in names, names
    assert "_load" not in names, names
    assert "tempfile" not in imported, imported
    assert "build_persistence_adapter" not in imported, imported


def test_registering_writes_no_json_ledger(tmp_path) -> None:
    """行为半边：登记之后根目录里一个 JSON 台账都不许多出来。"""
    registry = DatasetRegistry(root=tmp_path, store=InMemoryDatasetTableStore())
    path = tmp_path / "sales.csv"
    path.write_text("department,revenue\nfinance,100\n", encoding="utf-8")

    registry.register(path, principal=Principal.from_user(_OWNER))

    assert not registry.metadata_path.exists()
    assert [item.name for item in registry.root.iterdir() if item.suffix == ".json"] == []


# ============================================================== 只读一次性导入


def _legacy_payload(root: Path, rows: list[dict]) -> Path:
    path = root / ".dataset-metadata.json"
    path.write_text(json.dumps({"datasets": rows}, sort_keys=True), encoding="utf-8")
    return path


def _legacy_row(dataset_id: str, filename: str, root: Path, **updates) -> dict:
    (root / filename).write_text(f"department,revenue\nfinance,{dataset_id}\n", encoding="utf-8")
    row = {
        "dataset_id": dataset_id,
        "filename": filename,
        "owner_id": "u-legacy",
        "department_ids": ["finance"],
        "classification": "internal",
        "visibility": "private",
        "storage_path": str(root / filename),
        "content_sha256": dataset_storage._hash_file(root / filename),
        "status": "active",
        "created_at": "2026-09-20T00:00:00+00:00",
        "version_id": f"{dataset_id}:v1",
    }
    row.update(updates)
    return row


def test_the_legacy_ledger_is_imported_once_into_both_tables(tmp_path) -> None:
    """JSON 只读一次：导入后两张表各有其行，台账文件一个字都没变。"""
    rows = [
        _legacy_row("legacy-1", "one.csv", tmp_path),
        _legacy_row("legacy-2", "two.csv", tmp_path, status="deleted"),
        _legacy_row("legacy-3", "three.csv", tmp_path, storage_path=str(Path(tmp_path.parent) / "outside.csv")),
    ]
    ledger = _legacy_payload(tmp_path, rows)
    before = ledger.read_text(encoding="utf-8")
    registry = DatasetRegistry(root=tmp_path, store=InMemoryDatasetTableStore())

    counts = registry.import_legacy_metadata()
    after = ledger.read_text(encoding="utf-8")

    assert counts == {"datasets": 2, "dataset_versions": 2}, counts
    assert after == before, "导入是只读的"
    assert registry.get("legacy-1").content_sha256 == rows[0]["content_sha256"]
    assert registry.get("legacy-2").status == "deleted"
    assert registry.get("legacy-3") is None, "越出存储根的遗留条目跳过，但不许拖走整本台账"
    assert [item.version_number for item in registry.versions("legacy-1")] == [1]
    assert registry.get("legacy-1").metadata["legacy_import"] == str(ledger.resolve())


def test_importing_twice_adds_no_rows(tmp_path) -> None:
    """一次性导入必须可重入：第二次读数 0，表里行数不变。"""
    ledger = _legacy_payload(tmp_path, [_legacy_row("legacy-1", "one.csv", tmp_path)])
    registry = DatasetRegistry(root=tmp_path, store=InMemoryDatasetTableStore())

    first = registry.import_legacy_metadata()
    second = registry.import_legacy_metadata()

    assert first["datasets"] == 1
    assert second == {"datasets": 0, "dataset_versions": 0}
    assert len(registry.store.select(DATASET_TABLE)) == 1
    assert len(registry.store.select(DATASET_VERSION_TABLE)) == 1
    assert ledger.read_text(encoding="utf-8") != ""


def test_an_imported_dataset_keeps_its_identity_when_it_gets_a_new_version(tmp_path) -> None:
    """切表之后同名的下一次登记是 v2，不是第二个 dataset：稳定 ID 跨过这次迁移。"""
    row = _legacy_row("legacy-1", "one.csv", tmp_path)
    _legacy_payload(tmp_path, [row])
    registry = DatasetRegistry(root=tmp_path, store=InMemoryDatasetTableStore())
    path = tmp_path / "one.csv"
    path.write_text("department,revenue\nfinance,200\n", encoding="utf-8")

    record = registry.register(path, principal=Principal.from_user(_OWNER))

    assert record.dataset_id == "legacy-1"
    assert record.version_id == "legacy-1:v2"
    assert [item.version_number for item in registry.versions("legacy-1")] == [1, 2]
    assert registry.get("legacy-1").owner_id == "u-r249-cols", "当前行跟着新的登记者走"
    assert registry.versions("legacy-1")[0].owner_id == "u-legacy", "历史行留着它的原主"


def test_the_first_use_imports_without_being_asked(tmp_path) -> None:
    """导入挂在首次使用上，不挂在 import 上：模块级 registry 建起来时一次库都不碰。"""
    _legacy_payload(tmp_path, [_legacy_row("legacy-1", "one.csv", tmp_path)])
    registry = DatasetRegistry(root=tmp_path, store=InMemoryDatasetTableStore())
    assert registry._legacy_import_done is False

    assert [item.dataset_id for item in registry.list()] == ["legacy-1"]
    assert registry._legacy_import_done is True
