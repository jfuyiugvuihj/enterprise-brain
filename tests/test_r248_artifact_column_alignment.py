"""R248 J-2 —— 列对齐静态钉：``ArtifactRecord`` 的字段集与 ``artifacts`` 的列集双向相等。

防的是"表里有 owner 列、代码从来不写"这种假接入。所以两头都比：
表里有、记录里没有 → 红；记录里有、表里装不下 → 也红。靶子是迁移原文
``migrations/0001_core_resource_versions.sql`` 自己，不是任何人的转述——本单一枚新迁移
都不建、``migrations/manifest.json`` 一个字都不改（那两样归 R251），所以这枚钉读到的
列集就是今天要落的那张表。

再加一枚动态钉：真发给库的 ``INSERT`` 点了哪些列。静态相等只证明"名字对得上"，
它证明不了"值真的写出去"。
"""
import dataclasses
import re
from pathlib import Path

import pytest

from app.storage import artifacts as artifact_module
from app.storage.artifacts import ARTIFACT_COLUMNS, ArtifactRecord, ArtifactRegistry
from app.storage.persistence import PostgresPersistenceAdapter

REPO = Path(__file__).resolve().parents[1]
MIGRATION = REPO / "migrations" / "0001_core_resource_versions.sql"
TABLE_BLOCK = re.compile(
    r"CREATE TABLE IF NOT EXISTS artifacts \((?P<body>.*?)\n\);",
    re.DOTALL | re.IGNORECASE,
)
CONSTRAINT_WORDS = ("primary", "unique", "foreign", "constraint", "check", "exclude")

# 表里有、而控制面适配器的列元组没写的列。这不是"接入做完了"的一部分，是一笔可以重新长出来的
# 账：app/storage/persistence.py 的 _TABLES["artifacts"].columns 才是决定哪些列真能落库的那张表。
# 今天它是空的——R256 把 deleted_at 补进了那枚列元组（跟进单 §100.4 判据①：在那之前 R248 的
# "退役"只活在内存里，进程一重启 deleted_at 与 status 就一起复活）。DDL 侧本来就不欠这一枚：
# 0001 建 artifacts 时就带着 deleted_at TIMESTAMPTZ，欠的只有适配器那一行。常量保留、值改空，
# 是因为它会被人重新写满：谁少写一枚列，这里红一次，逼着他回来对这句话。
# （派工词当初把这枚缺口归给 R251——那是告警台账的单——总控在 §100.4 已订正归 R256。）
DOCUMENTED_GAP = frozenset()


def _artifact_columns():
    """迁移原文里 artifacts 的列声明：{列名: (NOT NULL, 有 DEFAULT)}。"""
    sql = MIGRATION.read_text(encoding="utf-8")
    match = TABLE_BLOCK.search(sql)
    assert match, "0001 里找不到 artifacts 的 CREATE TABLE，靶子变了"
    declarations = {}
    for raw in match.group("body").splitlines():
        line = raw.split("--", 1)[0].strip().rstrip(",").strip()
        if not line:
            continue
        name, _, rest = line.partition(" ")
        if name.lower().strip("(") in CONSTRAINT_WORDS or name.lower().startswith(CONSTRAINT_WORDS):
            continue
        upper = rest.upper()
        declarations[name] = (
            "NOT NULL" in upper or "PRIMARY KEY" in upper,
            "DEFAULT" in upper,
        )
    assert declarations, "解析出来一枚列都没有，是解析的问题而不是表的问题"
    return declarations


def _fields():
    return {field.name: field for field in dataclasses.fields(ArtifactRecord)}


def _record(tmp_path, name="revenue.png"):
    """经真登记路径造一枚记录：不走这条路，列对齐就成了手工摆的样子货。"""
    from app.agents.contracts import Principal

    root = tmp_path / "static"
    registry = ArtifactRegistry(root, metadata_path=tmp_path / "sidecar.json")
    path = root / name
    path.write_bytes(b"\x89PNG chart bytes")
    principal = Principal.from_user(
        {"id": "keeper", "username": "keeper", "role": "manager", "department": "finance"}
    )
    return registry, registry.register(path, artifact_type="chart", principal=principal)


def test_record_fields_and_table_columns_agree_both_ways():
    columns = set(_artifact_columns())
    fields = set(_fields())
    assert fields - columns == set(), f"记录里有表里装不下的字段：{sorted(fields - columns)}"
    assert columns - fields == set(), f"表里有代码不认的列（假接入）：{sorted(columns - fields)}"
    assert len(columns) >= 8, f"解析到的列太少，先看解析：{sorted(columns)}"


def test_the_module_column_tuple_is_the_table_column_tuple():
    columns = set(_artifact_columns())
    assert isinstance(ARTIFACT_COLUMNS, tuple)
    assert len(ARTIFACT_COLUMNS) == len(set(ARTIFACT_COLUMNS)), "列名重复了"
    assert set(ARTIFACT_COLUMNS) == columns


def test_required_fields_line_up_with_not_null_columns():
    """必填字段必须落在不可空的列上；可空的列必须有默认值，否则 NULL 读回来构造不出记录。

    ``PRIMARY KEY`` 按 PostgreSQL 的语义就是 NOT NULL，所以解析把它也算作不可空。
    """
    for name, field in _fields().items():
        not_null, _column_default = _artifact_columns()[name]
        has_default = (
            field.default is not dataclasses.MISSING
            or field.default_factory is not dataclasses.MISSING
        )
        if not has_default:
            assert not_null, f"{name} 是必填字段，却在表里可空：写 NULL 会当场炸"
        if not_null:
            continue
        assert has_default, f"{name} 可空，字段却没有默认值：NULL 读回来构造不出记录"


def test_a_registered_record_hands_the_store_every_column(tmp_path):
    registry, record = _record(tmp_path)

    row = artifact_module._to_row(record)

    assert set(row) == set(_artifact_columns()), sorted(set(row) ^ set(_artifact_columns()))
    assert row["owner_id"] == "keeper"
    assert row["status"] == "active"
    assert row["artifact_id"] == row["resource_id"] == record.artifact_id
    assert row["resource_type"] == artifact_module.ARTIFACT_RESOURCE_TYPE
    assert row["storage_key"] == record.storage_path
    assert row["content_sha256"] and set(row["content_sha256"]) <= set("0123456789abcdef")
    assert isinstance(row["metadata"], dict)
    assert set(row["metadata"]) == set(artifact_module.SCOPE_METADATA_KEYS)


def test_the_columns_written_to_the_table_are_named_not_assumed(tmp_path):
    """真发出去的 INSERT 点了哪些列：一枚都不许多，也一枚都不许少。

    静态相等只证明"名字对得上"，这一枚证明"值真的写出去"——把 owner_id 从写出的列里摘掉，
    它当场红（R248 反证 ① 的另一半）。R248 落这枚钉时表里 12 枚列、适配器只点名 11 枚，缺的
    那枚记在 DOCUMENTED_GAP 上；R256 补列之后那本明账归零，所以今天判的是"零枚缺口"——谁再
    少写一枚，这里红，而不是往常量里塞个名字把它盖过去。
    """
    statements = []

    class _Row:
        def __init__(self, row):
            self._row = row

        def fetchone(self):
            return dict(self._row) if self._row else None

        def fetchall(self):
            return [dict(self._row)] if self._row else []

    class _Recorder:
        def __init__(self, table):
            self.table = table

        def execute(self, sql, params=None):
            text = " ".join(str(sql).split())
            statements.append(text)
            if text.upper().startswith("INSERT"):
                names = [item.strip() for item in text.split("(", 1)[1].split(")")[0].split(",")]
                self.table.update(dict(zip(names, params or ())))
            return _Row(self.table)

        def commit(self):
            return None

        def close(self):
            return None

    from app.agents.contracts import Principal

    table = {}
    root = tmp_path / "static"
    registry = ArtifactRegistry(
        root,
        metadata_path=tmp_path / "sidecar.json",
        persistence=PostgresPersistenceAdapter(lambda: _Recorder(table)),
    )
    path = root / "revenue.png"
    path.write_bytes(b"\x89PNG chart bytes")
    record = registry.register(
        path,
        artifact_type="chart",
        principal=Principal.from_user(
            {"id": "keeper", "username": "keeper", "role": "manager", "department": "finance"}
        ),
    )

    insert = next(sql for sql in statements if sql.upper().startswith("INSERT"))
    written = {item.strip() for item in insert.split("(", 1)[1].split(")")[0].split(",")}

    columns = set(_artifact_columns())
    assert written <= columns, f"INSERT 写了表里没有的列：{sorted(written - columns)}"
    assert columns - written == DOCUMENTED_GAP, (
        f"表里有 {sorted(columns - written)} 没被写；R256 之后明账是空的（{sorted(DOCUMENTED_GAP)}），"
        "要么补上 app/storage/persistence.py 的列元组，要么改 DOCUMENTED_GAP 并说明理由"
    )
    assert table["owner_id"] == "keeper" and table["status"] == "active"
    assert table["artifact_id"] == record.artifact_id


def test_no_state_lives_outside_the_columns(tmp_path):
    """派生属性只许读列：字段之外再藏一份状态，就有了第二个事实源。"""
    _, record = _record(tmp_path)

    assert set(vars(record)) == set(_fields())
    for name in artifact_module.SCOPE_METADATA_KEYS + ("storage_path",):
        assert isinstance(getattr(ArtifactRecord, name), property), f"{name} 不该是第二份状态"


def test_the_retired_flat_shape_is_not_a_record():
    """JSON 那套扁平键只活在导入腿里，构造不出一枚记录。"""
    with pytest.raises(TypeError):
        ArtifactRecord(artifact_id="a", artifact_type="chart", storage_path="x", filename="x")
