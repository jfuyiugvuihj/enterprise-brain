"""R249 真机验收（可选腿）：两张表在真的 PostgreSQL 上写得进、读得回。

口径照 tests/test_postgres_execution_persistence.py：只有操作者显式导出
``EB_PG_ACCEPTANCE_URL`` 指向一枚一次性验收库时才跑，离线全量门里它是 **skip，不是 pass**
—— 本单在开发机上没有 PostgreSQL，所以 J-1/J-2 的达标证据来自假连接，这一文件是留给真机的
那道复核，特别是 TIMESTAMPTZ 读回来是 datetime、JSONB 读回来是 dict 这两条规范化路径。

它拒绝任何可能是应用库的目标：端口 5432、非本机主机、库名不带 enterprise_brain_accept 前缀
都当场 RuntimeError。
"""
from __future__ import annotations

import os
import uuid
from typing import Iterator
from urllib.parse import urlsplit

import psycopg
import pytest

from app.agents.contracts import Principal
from app.storage.datasets import DATASET_TABLE, DATASET_VERSION_TABLE, DatasetRegistry, PostgresDatasetTableStore

DATABASE_URL = os.getenv("EB_PG_ACCEPTANCE_URL", "").strip()

_TABLES = (DATASET_TABLE, DATASET_VERSION_TABLE)


def _target_or_skip() -> str:
    if not DATABASE_URL:
        pytest.skip("设置 EB_PG_ACCEPTANCE_URL 才跑 R249 的 PostgreSQL 真机验收")
    parsed = urlsplit(DATABASE_URL)
    database = (parsed.path or "").lstrip("/")
    port = parsed.port or 5432
    if not database.startswith("enterprise_brain_accept"):
        raise RuntimeError("acceptance URL must target an enterprise_brain_accept* database")
    if port == 5432 or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("acceptance URL must not target the default application database")
    return DATABASE_URL


@pytest.fixture(scope="module")
def url() -> str:
    return _target_or_skip()


@pytest.fixture
def connection(url) -> Iterator[psycopg.Connection]:
    handle = psycopg.connect(url, connect_timeout=5)
    try:
        yield handle
    finally:
        handle.rollback()
        handle.close()


@pytest.fixture
def owner(connection) -> Iterator[str]:
    """一个带 tag 的 owner_id，用例写完就把这个 owner 在两表里的行全部清掉。"""
    owner_id = "r249-acc-" + uuid.uuid4().hex[:10]
    yield owner_id
    for table in _TABLES:
        connection.execute(f"DELETE FROM {table} WHERE owner_id = %s", (owner_id,))
    connection.commit()


@pytest.fixture
def registry(tmp_path, url, owner) -> DatasetRegistry:
    store = PostgresDatasetTableStore(database_url=url)
    registry = DatasetRegistry(root=tmp_path, store=store)
    registry.principal = Principal.from_user(  # type: ignore[attr-defined]
        {"id": owner, "username": owner, "role": "manager", "department": "r249-acceptance"}
    )
    return registry


def _register(registry: DatasetRegistry, filename: str, body: str):
    """把文件落到存储根里再登记：登记只认根内的字节，这是表的边界，不是测试的偏好。"""
    path = registry.root / filename
    path.write_text(body, encoding="utf-8")
    return registry.register(path, principal=registry.principal, filename=filename)


def test_a_registration_lands_in_both_real_tables(registry, connection, owner) -> None:
    record = _register(registry, "sales.csv", "department,revenue\nfinance,100\n")

    dataset_row = connection.execute(
        f"SELECT dataset_id, current_version_id, status FROM {DATASET_TABLE} WHERE owner_id = %s",
        (owner,),
    ).fetchone()
    version_rows = connection.execute(
        f"SELECT version_number, content_sha256 FROM {DATASET_VERSION_TABLE} WHERE dataset_id = %s",
        (record.dataset_id,),
    ).fetchall()
    connection.commit()

    assert dataset_row is not None and str(dataset_row[0]) == record.dataset_id
    assert str(dataset_row[1]) == record.version_id
    assert len(version_rows) == 1 and int(version_rows[0][0]) == 1


def test_a_restarted_registry_reads_the_same_fields_back(registry, url, owner) -> None:
    """真库上的 J-1：TIMESTAMPTZ 与 JSONB 读回来的形状必须还原成同一枚记录。"""
    record = _register(registry, "sales.csv", "department,revenue\nfinance,100\n")

    reopened = DatasetRegistry(
        root=registry.root, store=PostgresDatasetTableStore(database_url=url)
    )

    assert reopened.get(record.dataset_id) == record
    assert reopened.list() == [record]


def test_three_registrations_make_three_version_rows_on_the_real_tables(registry, connection, owner) -> None:
    """真库上的 J-2：一行 datasets、三行 dataset_versions，部分唯一索引不许被绕过。"""
    dataset_ids = set()
    for index in range(3):
        record = _register(registry, "sales.csv", f"department,revenue\nfinance,{index}\n")
        dataset_ids.add(record.dataset_id)
    connection.commit()

    datasets = connection.execute(
        f"SELECT count(*) FROM {DATASET_TABLE} WHERE owner_id = %s", (owner,)
    ).fetchone()
    versions = connection.execute(
        f"SELECT version_number, content_sha256 FROM {DATASET_VERSION_TABLE} WHERE dataset_id = %s"
        " ORDER BY version_number",
        (next(iter(dataset_ids)),),
    ).fetchall()
    connection.commit()

    assert len(dataset_ids) == 1
    assert int(datasets[0]) == 1
    assert [int(row[0]) for row in versions] == [1, 2, 3]
    assert len({str(row[1]) for row in versions}) == 3


def test_a_second_active_row_with_the_same_name_is_refused(registry, connection, owner, tmp_path) -> None:
    """``datasets_active_filename_idx`` 是真的：绕过 registry 直接写第二行必须撞约束。"""
    record = _register(registry, "sales.csv", "department,revenue\nfinance,1\n")

    with pytest.raises(psycopg.errors.UniqueViolation):
        connection.execute(
            f"INSERT INTO {DATASET_TABLE}"
            " (dataset_id, owner_id, filename, department_ids, classification, visibility,"
            " storage_key, content_sha256, status, current_version_id, metadata)"
            " VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s::jsonb)",
            (
                "r249-twin",
                owner,
                "sales.csv",
                '["r249-acceptance"]',
                "internal",
                "private",
                record.storage_path,
                record.content_sha256,
                "active",
                "r249-twin:v1",
                "{}",
            ),
        )
    connection.rollback()
