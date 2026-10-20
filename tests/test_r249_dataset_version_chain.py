"""R249 判据 J-1 / J-2 —— datasets 与 dataset_versions 两张表是唯一事实源，版本是真版本。

J-1 重启可恢复：登记之后换一枚全新的 registry（新实例、新 store、零内存共享）读回来，
`get` / `list` 必须逐字段相同。全程不许要真库：按 tests/test_r229_connect_retry.py 的范式
用假连接记录 SQL，只在假连接里跑 0002 那两张表的读写。

J-2 版本链：同一文件连续 register 三次 ⇒ `datasets` 一行、`dataset_versions` 三行，
version_number 单调、按版本可取回各自的内容哈希。这条是本单的核心判据。

全进程内：不起服务、不打模型、不连 PostgreSQL（conftest 已把 DATABASE_URL 钉在
127.0.0.1:1 的保留端口上，本文件再加一枚哨兵，真驱动一旦想 connect 就当场炸）。
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import pytest

from app.agents.contracts import Principal
from app.storage import datasets as dataset_storage
from app.storage.persistence import PersistenceWriteError
from app.storage.datasets import (
    DATASET_TABLE,
    DATASET_VERSION_TABLE,
    DatasetRegistry,
    PostgresDatasetTableStore,
)

psycopg = pytest.importorskip("psycopg")

_OWNER = {"id": "u-r249", "username": "r249-owner", "role": "manager", "department": "finance"}

_INSERT_RE = re.compile(r"^INSERT INTO (\w+) \(([^)]*)\) VALUES \((.*)\)$")
_UPDATE_RE = re.compile(r"^UPDATE (\w+) SET (.*?) WHERE (\w+) = (.*)$")
_SELECT_RE = re.compile(
    r"^SELECT (.*?) FROM (\w+)(?: WHERE (.*?))?(?: ORDER BY (\w+)( DESC)?)?$", re.IGNORECASE
)

#: 与 0002 迁移的列类型对齐：读回来的时候假库要按驱动的形状交还，不能让测试只认自己写进去的串。
_JSON_COLUMNS = {"department_ids", "metadata", "schema_snapshot"}
_TIMESTAMP_COLUMNS = {"created_at", "updated_at", "published_at", "superseded_at"}


class _FakeIntegrityError(RuntimeError):
    """假库的唯一约束违例：真 psycopg 在这种情况下抛 IntegrityError。"""


def _sort_key(value):
    if value is None:
        return (0, "")
    if isinstance(value, bool):
        return (1, str(value))
    if isinstance(value, (int, float)):
        return (2, float(value))
    return (3, str(value))


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeLineageDB:
    """两张表的假 PostgreSQL：记录每一条 SQL，并在内存里守住 DDL 的三条唯一约束。

    它不是给 registry 用的旁路存储，而是"表本身"的替身 —— registry 只能靠 SELECT 拿到东西，
    所以 J-1 想证的那件事（进程里没有可信副本）在这里必须成立。
    """

    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict]] = {DATASET_TABLE: {}, DATASET_VERSION_TABLE: {}}
        self.statements: list[tuple[str, tuple]] = []
        self.commits = 0
        self.rollbacks = 0
        self._closed = 0

    # ------------------------------------------------------------------ SQL 的一面

    def execute(self, sql: str, params=()) -> _Result:
        self.statements.append((sql, tuple(params or ())))
        match = _INSERT_RE.match(sql)
        if match:
            return self._insert(*match.groups(), params)
        match = _UPDATE_RE.match(sql)
        if match:
            return self._update(match.group(1), match.group(2), match.group(3), params)
        match = _SELECT_RE.match(sql)
        if match:
            return self._select(*match.groups(), params)
        raise AssertionError(f"FakeLineageDB 看不懂这条 SQL：{sql}")

    @staticmethod
    def _column_type(token: str) -> str | None:
        _, _, cast = token.partition("::")
        return cast or None

    @staticmethod
    def _target(token: str) -> str:
        return token.split("::", 1)[0].strip()

    def _store_value(self, column: str, value, cast: str | None):
        if column in _JSON_COLUMNS:
            return json.loads(value) if isinstance(value, str) else value
        if column in _TIMESTAMP_COLUMNS and isinstance(value, str):
            return datetime.fromisoformat(value)
        return value

    def _primary_key(self, table: str) -> str:
        return "dataset_id" if table == DATASET_TABLE else "dataset_version_id"

    def _insert(self, table: str, column_text: str, _holders: str, params) -> _Result:
        columns = [name.strip() for name in column_text.split(",")]
        holders = [name.strip() for name in _holders.split(",")]
        if len(columns) != len(params):
            raise AssertionError(f"{table} 插入的列数与参数数不符：{columns} / {params}")
        row = {
            column: self._store_value(column, value, self._column_type(holder))
            for column, value, holder in zip(columns, params, holders)
        }
        primary_key = self._primary_key(table)
        identity = str(row[primary_key])
        if identity in self.tables[table]:
            raise _FakeIntegrityError(f"duplicate key value violates unique constraint {table}_pkey")
        if table == DATASET_TABLE:
            for other in self.tables[table].values():
                if (
                    str(other.get("filename")) == str(row.get("filename"))
                    and str(other.get("status")) == "active"
                ):
                    raise _FakeIntegrityError("datasets_active_filename_idx")
        else:
            for other in self.tables[table].values():
                if (
                    str(other.get("dataset_id")) == str(row.get("dataset_id"))
                    and int(other.get("version_number") or 0) == int(row.get("version_number") or 0)
                ):
                    raise _FakeIntegrityError("dataset_versions_dataset_id_version_number_key")
            if str(row.get("dataset_id")) not in self.tables[DATASET_TABLE]:
                raise _FakeIntegrityError("dataset_versions_dataset_id_fkey")
        self.tables[table][identity] = row
        return _Result([])

    def _update(self, table: str, set_text: str, key_column: str, params) -> _Result:
        assignments = [item.strip() for item in set_text.split(",")]
        names = [item.split("=", 1)[0].strip() for item in assignments]
        holders = [item.split("=", 1)[1].strip() for item in assignments]
        values = list(params)
        identity = str(values.pop())
        rows = self.tables[table]
        if identity not in rows:
            raise _FakeIntegrityError(f"update 打不到存在的 {table} 行：{identity}")
        for name, holder, value in zip(names, holders, values):
            rows[identity][name] = self._store_value(name, value, self._column_type(holder))
        if table == DATASET_TABLE:
            for other_identity, other in rows.items():
                if (
                    other_identity != identity
                    and str(other.get("filename")) == str(rows[identity].get("filename"))
                    and str(other.get("status")) == "active"
                    and str(rows[identity].get("status")) == "active"
                ):
                    raise _FakeIntegrityError("datasets_active_filename_idx")
        return _Result([])

    def _select(self, _columns, table: str, where_text: str | None, order_column, descending, params) -> _Result:
        rows = list(self.tables[table].values())
        values = list(params or ())
        if where_text:
            for condition in where_text.split(" AND "):
                name, holder = condition.split("=", 1)
                value = values.pop(0)
                name = name.strip()
                if name in _JSON_COLUMNS and isinstance(value, str):
                    value = json.loads(value)
                if name in _TIMESTAMP_COLUMNS and isinstance(value, str):
                    value = datetime.fromisoformat(value)
                rows = [row for row in rows if _sort_key(row.get(name)) == _sort_key(value)]
        rows.sort(key=lambda row: _sort_key(row.get((order_column or "created_at").strip())), reverse=bool(descending))
        return _Result(rows)

    # ------------------------------------------------------------------ 连接的一面

    def connection(self) -> "FakeLineageConnection":
        return FakeLineageConnection(self)

    def statements_for(self, table: str) -> list[tuple[str, tuple]]:
        return [item for item in self.statements if table in item[0]]


class FakeLineageConnection:
    """假连接：execute / commit / close，一次网络都不碰。"""

    def __init__(self, db: FakeLineageDB):
        self.db = db

    def execute(self, sql, params=None):
        return self.db.execute(sql, params)

    def commit(self):
        self.db.commits += 1

    def rollback(self):
        self.db.rollbacks += 1

    def close(self):
        self.db._closed += 1


@pytest.fixture(autouse=True)
def no_real_driver_connect(monkeypatch):
    """哨兵：本文件任何用例都不许经真驱动建连（假 conn 一律走 connection_factory 注入）。"""

    def refuse(*args, **kwargs):
        raise AssertionError("tests/test_r249_dataset_version_chain.py 试图开一条真 PostgreSQL 连接")

    monkeypatch.setattr(psycopg, "connect", refuse, raising=False)
    yield


def _registry(root, db: FakeLineageDB) -> DatasetRegistry:
    """一枚全新的 registry：新实例 + 新 store，只共享"表"，不共享任何进程内副本。"""
    return DatasetRegistry(
        root=root,
        metadata_path=root / ".dataset-metadata.json",
        store=PostgresDatasetTableStore(connection_factory=db.connection),
    )


def _principal(**updates) -> Principal:
    user = {**_OWNER, **updates}
    return Principal.from_user(user)


def _write(root, filename: str, body: str):
    path = root / filename
    path.write_text(body, encoding="utf-8")
    return path


# =============================================================== J-1 重启可恢复


def test_a_restarted_process_reads_back_the_same_dataset(tmp_path) -> None:
    """同一登记"进程重启"后 get/list 逐字段相同 —— 读的是表，不是上一个进程的内存。"""
    first = _registry(tmp_path, db := FakeLineageDB())
    path = _write(tmp_path, "sales.csv", "department,revenue\nfinance,100\n")
    registered = first.register(path, principal=_principal())

    second = _registry(tmp_path, db)

    assert second.get(registered.dataset_id) == registered
    assert second.list() == first.list()
    assert second.get_active_by_filename("sales.csv") == registered
    assert [item.dataset_id for item in second.list()] == [registered.dataset_id]


def test_the_recovery_read_goes_to_the_two_tables_and_not_to_json(tmp_path) -> None:
    """恢复的读数必须来自 SELECT datasets / dataset_versions，且全程没写过 JSON 台账。"""
    registry = _registry(tmp_path, db := FakeLineageDB())
    path = _write(tmp_path, "sales.csv", "department,revenue\nfinance,100\n")
    record = registry.register(path, principal=_principal())

    _registry(tmp_path, db).get(record.dataset_id)

    statements = [sql for sql, _params in db.statements]
    assert any(sql.startswith(f"SELECT ") and DATASET_TABLE in sql for sql in statements), statements
    assert any("INSERT INTO dataset_versions" in sql for sql in statements), statements
    assert not (tmp_path / ".dataset-metadata.json").exists()
    assert db.commits == 1, "一次登记一次事务，两张表要么一起落要么都不落"


def test_a_row_the_table_refused_is_never_reported_as_registered(tmp_path) -> None:
    """写回读不到就当失败：register 交回的记录是从表里读回来的，不是自己拼的那份。"""

    class SwallowInsertDB(FakeLineageDB):
        def _insert(self, table, column_text, holders, params):
            return _Result([])

    db = SwallowInsertDB()
    registry = _registry(tmp_path, db)
    path = _write(tmp_path, "sales.csv", "department,revenue\nfinance,1\n")

    with pytest.raises(PersistenceWriteError, match="not readable after register"):
        registry.register(path, principal=_principal())

    assert db.tables[DATASET_TABLE] == {}, "假库没落行，registry 也不许留下可信副本"
    assert registry.list() == []
    assert registry.get("any-id") is None


# =============================================================== J-2 版本链


def test_three_registrations_leave_one_dataset_and_three_versions(tmp_path) -> None:
    """本单的核心判据：连续 register 三次同一文件 ⇒ datasets 一行、dataset_versions 三行。"""
    db = FakeLineageDB()
    registry = _registry(tmp_path, db)
    hashes = []
    for index in range(3):
        path = _write(tmp_path, "sales.csv", f"department,revenue\nfinance,{index}\n")
        registry.register(path, principal=_principal())
        hashes.append(dataset_storage._hash_file(path))

    dataset_rows = db.tables[DATASET_TABLE]
    version_rows = db.tables[DATASET_VERSION_TABLE]
    assert len(dataset_rows) == 1, dataset_rows
    assert len(version_rows) == 3, version_rows

    dataset_id = next(iter(dataset_rows))
    versions = registry.versions(dataset_id)
    assert [item.version_number for item in versions] == [1, 2, 3]
    assert all(item.dataset_id == dataset_id for item in versions)
    assert [item.content_sha256 for item in versions] == hashes


def test_each_version_stays_addressable_with_its_own_content_hash(tmp_path) -> None:
    """版本不是覆盖：v1 的哈希在 v3 之后还取回来，指针只跟着当前版本走。"""
    db = FakeLineageDB()
    registry = _registry(tmp_path, db)
    records = []
    for index in range(3):
        path = _write(tmp_path, "sales.csv", f"department,revenue\nfinance,{index}\n")
        records.append(registry.register(path, principal=_principal()))

    assert len({item.dataset_id for item in records}) == 1, "稳定 ID：三次登记同一个 dataset"
    assert [item.version_id for item in records] == [
        f"{records[0].dataset_id}:v1",
        f"{records[0].dataset_id}:v2",
        f"{records[0].dataset_id}:v3",
    ]
    live = registry.get(records[0].dataset_id)
    assert live.current_version_id == records[2].version_id
    assert live.content_sha256 == records[2].content_sha256
    for number, expected in zip((1, 2, 3), records):
        version = registry.get_version(live.dataset_id, number)
        assert version is not None
        assert version.content_sha256 == expected.content_sha256
        assert version.storage_key == expected.storage_path


def test_superseding_a_version_is_a_write_to_the_row_it_replaces(tmp_path) -> None:
    """旧版本被标成 superseded 并留下时刻，而不是从表里消失。"""
    db = FakeLineageDB()
    registry = _registry(tmp_path, db)
    for index in range(2):
        path = _write(tmp_path, "sales.csv", f"department,revenue\nfinance,{index}\n")
        registry.register(path, principal=_principal())

    versions = registry.versions(next(iter(db.tables[DATASET_TABLE])))
    assert [item.status for item in versions] == ["superseded", "active"]
    assert versions[0].superseded_at
    assert versions[1].superseded_at is None
    assert versions[0].metadata["previous_version_id"] is None
    assert versions[1].metadata["previous_version_id"] == versions[0].dataset_version_id


def test_a_retired_dataset_frees_its_name_for_a_brand_new_chain(tmp_path) -> None:
    """soft_delete 之后同名再登记是新 dataset 新链：0002 的部分唯一索引只管 active 行。"""
    db = FakeLineageDB()
    registry = _registry(tmp_path, db)
    path = _write(tmp_path, "sales.csv", "department,revenue\nfinance,1\n")
    first = registry.register(path, principal=_principal())
    assert registry.soft_delete(first.dataset_id) is True

    second = registry.register(path, principal=_principal())

    assert second.dataset_id != first.dataset_id
    assert second.version_id == f"{second.dataset_id}:v1"
    assert len(db.tables[DATASET_TABLE]) == 2
    assert [item.version_number for item in registry.versions(first.dataset_id)] == [1]
    assert registry.get(first.dataset_id).status == "deleted"
    assert [item.status for item in registry.versions(first.dataset_id)] == ["deleted"]
