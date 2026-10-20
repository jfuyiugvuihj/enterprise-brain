"""R256 判据② —— ``dataset_versions`` 有了自己的 scope 两列，历史版本不再跟着父行一起放宽。

三件事分开钉，因为它们各自会漂：

1. **迁移的形状**（``_0015`` 那几格）：0015 只发 ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``
   与 ``COMMENT ON``，两列都 ``NOT NULL`` 带常量默认值，不 DROP、不回填。前滚目录的规矩与
   0012/0013/0014 同一形状。
2. **读数的规则**（``_no_wider_scope`` 那几格）：口径取两行里**更严**的那一枚，部门取交集。
   两个方向都不许放宽——把父行降密不放宽历史版本（判据②点名的那一格），把父行**升**密也不
   许把历史版本读到比父行更宽。坏词与没记过的口径一律走向拒绝。
3. **落盘的事实**（``register`` 那几格）：版本行里真的存着自己那一份，换了登记表（＝重启）
   还是那一份。

全程离线：``InMemoryDatasetTableStore`` 与迁移文本，不连库。真库那一格在 5433 上另跑。
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from app.agents.contracts import Principal
from app.common.permissions import ACTION_VIEW
from app.common.policy import authorization_decision
from app.db.migrations import MIGRATIONS, discover_migrations
from app.storage.datasets import (
    DATASET_VERSION_TABLE,
    DatasetRecord,
    DatasetRegistry,
    DatasetVersionRecord,
    InMemoryDatasetTableStore,
    _no_wider_scope,
    _strictness,
)
from test_r183_184_migration_pair import executable_statements, statement_head, writes_rows

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO / "migrations"
VERSION = "0015"
FILENAME = "0015_dataset_version_scope_columns.sql"
PATH = MIGRATIONS_DIR / FILENAME
DEPT_A = "r256-finance"
DEPT_B = "r256-hr"
DEPT_C = "r256-legal"


def _migration():
    return next(item for item in MIGRATIONS if item.version == VERSION)


def _added_columns():
    """0015 送出的 ``(表, 列)`` 名单，取自语句本身而不是任何转述。"""
    from test_r249_dataset_table_columns import _ADD_COLUMN, BASE_VERSION  # noqa: PLC0415

    added = []
    assert VERSION > BASE_VERSION
    for statement in executable_statements(_migration().sql):
        match = _ADD_COLUMN.match(statement.strip())
        if match is not None:
            added.append((match.group("table").lower(), match.group("column").lower()))
    return added


# ============================================================ 1. 迁移的形状（前滚纪律）


def test_0015_ships_exactly_the_two_scope_columns_and_nothing_else():
    assert _migration().name == "dataset_version_scope_columns"
    statements = executable_statements(_migration().sql)

    assert statements, "0015 一句可执行语句都没有"
    assert {statement_head(item) for item in statements} <= {"alter table", "comment on"}, statements
    assert _added_columns() == [
        ("dataset_versions", "department_ids"),
        ("dataset_versions", "classification"),
    ], "判据②要的就是这两列，多一枚少一枚都回到这里改口"


def test_every_added_column_is_guarded_not_null_and_defaults_to_a_constant():
    """``IF NOT EXISTS`` + ``NOT NULL DEFAULT``：存量行不必回填也能过，重跑是 no-op。"""
    from test_r249_dataset_table_columns import _ADD_COLUMN  # noqa: PLC0415

    for statement in executable_statements(_migration().sql):
        match = _ADD_COLUMN.match(statement.strip())
        if match is None:
            continue
        definition = match.group("definition").upper()
        assert "NOT NULL" in definition, statement
        assert "DEFAULT" in definition, statement
        assert statement.upper().startswith("ALTER TABLE IF EXISTS"), statement
        assert "ADD COLUMN IF NOT EXISTS" in statement.upper(), statement


def test_0015_writes_no_rows_and_breaks_nothing():
    """不许回填（0012/0014 同一理由：没人有权替历史行编一个当时没记的口径），也不许 DROP。

    判的是**可执行语句**，不是整篇文本：0015 的散文里就写着它不做什么（第 55-57 行那句
    "no DROP TABLE, no DROP COLUMN"），拿关键字在注释里搜会把诚实的自述读成违约。判据⑤
    防的是同一类误判，只是方向相反——那一次是分号，这一次是关键字。
    """
    statements = executable_statements(_migration().sql)

    assert [item for item in statements if writes_rows(item)] == [], statements
    joined = " ".join(statements).upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "DROP CONSTRAINT", "DROP DEFAULT", "SET DEFAULT"):
        assert forbidden not in joined, forbidden
    assert [item for item in statements if "UPDATE" in item.upper()] == [], statements


def test_the_two_columns_are_the_tail_of_the_record_and_of_the_insert():
    """新列排在末尾 = PostgreSQL 的 ``attnum`` 次序，也是 INSERT 的列次序。"""
    from app.storage.datasets import DATASET_VERSION_COLUMNS  # noqa: PLC0415

    assert DATASET_VERSION_COLUMNS[-2:] == ("department_ids", "classification")
    assert DATASET_VERSION_COLUMNS.index("department_ids") == len(DATASET_VERSION_COLUMNS) - 2
    assert len(set(DATASET_VERSION_COLUMNS)) == len(DATASET_VERSION_COLUMNS) == 16


def test_the_bytes_on_disk_the_manifest_and_the_loader_are_one_document():
    """行尾不许改数字：本件按 LF 落盘，归一前后必须同一个 sha256。"""
    raw = PATH.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    text = PATH.read_text(encoding="utf-8")
    manifest = json.loads((MIGRATIONS_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert raw.count(b"\r") == 0, "0015 按 LF 落盘：混进 CR 会让 manifest 的 sha256 与磁盘脱钩"
    assert raw == normalized
    assert normalized.endswith(b"\n") and not normalized.endswith(b"\n\n")
    assert sha256(raw).hexdigest() == sha256(text.encode("utf-8")).hexdigest()
    assert manifest[FILENAME] == _migration().checksum == sha256(raw).hexdigest()
    assert discover_migrations() == MIGRATIONS


# =============================================================== 2. 读数的规则（只严不宽）


def _dataset(classification: str, departments: list[str]) -> DatasetRecord:
    return DatasetRecord(
        dataset_id="d-1",
        owner_id="u-1",
        filename="sales.csv",
        department_ids=list(departments),
        classification=classification,
        visibility="department",
        storage_key="data/sales.csv",
        content_sha256="0" * 64,
        status="active",
        current_version_id="d-1:v1",
    )


def _version(classification: str, departments: list[str]) -> DatasetVersionRecord:
    return DatasetVersionRecord(
        dataset_version_id="d-1:v1",
        dataset_id="d-1",
        owner_id="u-1",
        version_number=1,
        storage_key="data/sales.csv",
        content_sha256="0" * 64,
        classification=classification,
        department_ids=list(departments),
    )


@pytest.mark.parametrize(
    "version_class, version_departments, dataset_class, dataset_departments, expected",
    [
        # 判据②点名的那一格：父行被后来那次登记降密，历史版本不许跟着放宽。
        ("confidential", [DEPT_A], "public", [DEPT_A], "confidential"),
        # 反方向：父行升密，历史版本也不许读到比父行更宽——两行只取更严的那一枚。
        ("public", [DEPT_A], "confidential", [DEPT_A], "confidential"),
        # 同一级不同词（secret 与 confidential 在 policy 里同为 3）：版本自己那一份原样交回。
        ("secret", [DEPT_A], "confidential", [DEPT_A], "secret"),
        ("confidential", [DEPT_A], "secret", [DEPT_A], "confidential"),
        # 两行同词：不改变。
        ("internal", [DEPT_A], "internal", [DEPT_A], "internal"),
        # 父行是一句 policy 排不出序的坏词：坏词排在所有好词之上，交回去由 policy 指名拒绝。
        ("public", [DEPT_A], "unclassified-by-anyone", [DEPT_A], "unclassified-by-anyone"),
    ],
)
def test_the_scope_of_a_version_is_the_stricter_of_the_two_rows(
    version_class, version_departments, dataset_class, dataset_departments, expected
) -> None:
    scope = _no_wider_scope(_version(version_class, version_departments), _dataset(dataset_class, dataset_departments))

    assert scope is not None
    assert scope.classification == expected
    assert scope.version_id == "d-1:v1"
    assert scope.resource_id == "d-1"


def test_departments_are_intersected_never_merged():
    """两份部门名单只能取交集：并集会造出一枚当时没人授权过的版本。"""
    scope = _no_wider_scope(
        _version("internal", [DEPT_A, DEPT_B]), _dataset("internal", [DEPT_B, DEPT_C])
    )

    assert scope is not None
    assert scope.department_ids == [DEPT_B]


def test_an_emptied_department_intersection_answers_no_scope():
    """交集为空时交回的是空名单，policy 把它读成 resource_scope_missing —— 拒绝，不是放行。"""
    version = _version("internal", [DEPT_A])
    dataset = _dataset("internal", [DEPT_C])
    scope = _no_wider_scope(version, dataset)

    assert scope is not None and scope.department_ids == []
    decision = authorization_decision(
        Principal.from_user(
            {"id": "u-x", "username": "x", "role": "manager", "department": DEPT_C}
        ),
        scope,
        action=ACTION_VIEW,
        require_resource_scope=True,
    )
    assert decision.allowed is False
    assert decision.reason_code == "resource_scope_missing"


def test_a_version_that_recorded_nothing_answers_none_rather_than_the_parents_word():
    """0015 之前落的老行就是这个形状：没记过就是没记过，不许拿父行的词冒充它当时说过。"""
    assert _no_wider_scope(_version("", [DEPT_A]), _dataset("confidential", [DEPT_A])) is None
    assert _no_wider_scope(_version("   ", [DEPT_A]), _dataset("confidential", [DEPT_A])) is None


def test_a_bad_word_on_the_version_travels_back_as_written():
    assert _strictness("confidential") < _strictness("nonsense")
    assert _strictness("public") < _strictness("core")
    scope = _no_wider_scope(_version("nonsense", [DEPT_A]), _dataset("public", [DEPT_A]))

    assert scope is not None and scope.classification == "nonsense"


# ============================================================ 3. 落盘的事实（换进程读回来）


def _user(departments: list[str], role: str = "manager") -> dict:
    return {"id": "u-owner", "username": "owner", "role": role, "department": departments[0], "department_ids": departments}


def _registry(tmp_path: Path) -> DatasetRegistry:
    return DatasetRegistry(root=tmp_path, store=InMemoryDatasetTableStore())


def _write(path: Path, body: str) -> Path:
    path.write_text(f"department,revenue\n{body}\n", encoding="utf-8")
    return path


def test_a_registration_stamps_its_own_scope_onto_the_version_row(tmp_path):
    """每次登记把自己的口径抄在版本行上，之后父行被改写也改不到它。"""
    registry = _registry(tmp_path)
    first = registry.register(
        _write(tmp_path / "sales.csv", "1"), principal=Principal.from_user(_user([DEPT_A])),
        classification="confidential",
    )
    second = registry.register(
        _write(tmp_path / "sales.csv", "2"), principal=Principal.from_user(_user([DEPT_A])),
        filename="sales.csv", classification="public",
    )

    assert registry.get(first.dataset_id).classification == "public"
    rows = {row["dataset_version_id"]: row for row in registry.store.select(DATASET_VERSION_TABLE)}
    assert rows[f"{first.dataset_id}:v1"]["classification"] == "confidential"
    assert rows[second.current_version_id]["classification"] == "public"
    assert rows[f"{first.dataset_id}:v1"]["department_ids"] == [DEPT_A]


def test_the_stamped_scope_survives_a_new_registry_over_the_same_table(tmp_path):
    """换一枚登记表读回来，v1 记的还是当时那一份——这一格是判据②的可查形状。"""
    registry = _registry(tmp_path)
    first = registry.register(
        _write(tmp_path / "sales.csv", "1"), principal=Principal.from_user(_user([DEPT_A, DEPT_B])),
        classification="confidential",
    )
    registry.register(
        _write(tmp_path / "sales.csv", "2"), principal=Principal.from_user(_user([DEPT_B, DEPT_C])),
        filename="sales.csv", classification="public",
    )

    restarted = _registry(tmp_path)
    restarted.store._rows = registry.store._rows  # 同一份表，两个进程
    version = restarted.get_version(first.dataset_id, 1)

    assert version is not None
    assert version.classification == "confidential"
    assert version.department_ids == [DEPT_A, DEPT_B]
    scope = restarted.scope_for_version(f"{first.dataset_id}:v1")
    assert scope is not None
    assert scope.classification == "confidential"
    assert scope.department_ids == [DEPT_B], "父行已经是 B+C，交集只剩 B；密级那一边更严的词赢"


def test_an_old_row_with_no_recorded_scope_is_refused_not_inherited(tmp_path):
    """把版本行的 classification 抹成空串，模拟 0015 之前落的那一行：交回 None。"""
    registry = _registry(tmp_path)
    record = registry.register(
        _write(tmp_path / "sales.csv", "1"), principal=Principal.from_user(_user([DEPT_A])),
        classification="confidential",
    )
    registry.store.apply(
        [(DATASET_VERSION_TABLE, {"dataset_version_id": record.current_version_id, "classification": ""}, "update")]
    )

    assert registry.scope_for_version(record.current_version_id) is None
    decision = authorization_decision(
        Principal.from_user(_user([DEPT_A])),
        registry.scope_for_version(record.current_version_id),
        action=ACTION_VIEW,
        require_resource_scope=True,
    )
    assert decision.allowed is False
    assert decision.reason_code == "resource_scope_missing"