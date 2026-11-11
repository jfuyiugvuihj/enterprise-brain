"""R256 判据④ —— 0015 在真的 PostgreSQL 上跑过一次，并且**每次跑都换一枚一次性库**。

口径照 tests/test_r249_dataset_pg_acceptance.py：只有操作者显式导出
``EB_PG_ACCEPTANCE_URL`` 指向 127.0.0.1:5433 上那枚 ``enterprise_brain_accept*`` 库时才跑；
离线全量门里它是 **skip，不是 pass**。目标端口 5432、非本机主机、库名不带那个前缀，一律
RuntimeError —— 本文件会 CREATE / DROP DATABASE，所以它比 R249 那件更需要"绝不落在应用库"。

为什么要另造一次性库而不是复用 ``EB_PG_ACCEPTANCE_URL`` 指的那一枚：R249 那件在同名
``sales.csv`` 上按 owner 清行，而 ``dataset_id`` 是按逻辑文件名算的，一枚共享库跑到第二遍
就会把上一遍的版本行一起数进来（实测 9 == 1）。那是量具的形状，不是产品的缺陷，所以这里
每枚用例自己造库、自己拆库。

三件事各自会漂，分开钉：
1. 整条目录（0001..0015）在一枚空库上跑到尾，账本尾号就是 0015（A-1/A-3）；
2. 0015 这个文件**本身**可以被重放：列的形状与行数逐字不变（A-2）；
3. 两列在真库上是有类型的东西，而版本行真的存得下自己那一份口径，换一枚登记表（=重启）
   读回来还是那一份；抹成 0015 之前的形状 ⇒ 交回 None，不继承父行（A-3/A-4/A-5）。
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from app.agents.contracts import Principal
from app.db.connection import parse_database_settings
from app.db.migrations import MIGRATIONS, apply_migrations
from app.storage.datasets import (
    DATASET_VERSION_TABLE,
    DatasetRegistry,
    PostgresDatasetTableStore,
)

REPO = Path(__file__).resolve().parents[1]
FILENAME = "0015_dataset_version_scope_columns.sql"
MIGRATION_PATH = REPO / "migrations" / FILENAME
VERSION = "0015"
DEPT_A = "r256-accept-finance"
DEPT_B = "r256-accept-hr"
SCOPE_COLUMNS = ("classification", "department_ids")


def _acceptance_url() -> str:
    raw = os.getenv("EB_PG_ACCEPTANCE_URL", "").strip()
    if not raw:
        pytest.skip("设置 EB_PG_ACCEPTANCE_URL 才跑 R256 的 PostgreSQL 真库验收")
    parsed = urlsplit(raw)
    database = (parsed.path or "").lstrip("/")
    if not database.startswith("enterprise_brain_accept"):
        raise RuntimeError("acceptance URL must target an enterprise_brain_accept* database")
    if parsed.port == 5432 or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("acceptance URL must not target the default application database")
    return raw


def _maintenance_url(url: str) -> str:
    """把验收库换成同集群上的 ``postgres`` 维护库：CREATE / DROP DATABASE 要在别处发。"""
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment))


@pytest.fixture
def live_url() -> Iterator[str]:
    """一枚只属于本用例的一次性库：跑之前不存在，跑完一定不在。"""
    if not (os.getenv("EMBEDDING_MODEL", "").strip() and os.getenv("EMBEDDING_DIMENSION", "").strip()):
        pytest.skip("0010 要一份申报过的 embedding profile（EMBEDDING_MODEL + EMBEDDING_DIMENSION），缺就不猜宽度")
    base = _acceptance_url()
    name = urlsplit(base).path.lstrip("/") + "_" + uuid.uuid4().hex[:8]
    admin = psycopg.connect(_maintenance_url(base), autocommit=True, connect_timeout=5)
    created = False
    try:
        admin.execute("CREATE DATABASE " + quote_ident(name))
        created = True
        parts = urlsplit(base)
        yield urlunsplit((parts.scheme, parts.netloc, "/" + name, "", ""))
    finally:
        if created:
            admin.execute("DROP DATABASE IF EXISTS " + quote_ident(name) + " WITH (FORCE)")
        admin.close()


def quote_ident(name: str) -> str:
    """库名来自 uuid，仍然按 PostgreSQL 的规矩引用，不拼裸标识符。"""
    assert re.fullmatch(r"[a-z0-9_]+", name), name
    return '"' + name + '"'


@pytest.fixture
def migrated(live_url: str) -> list:
    """把整条目录跑在这枚一次性库上，回 runner 说"这一跑落了哪几枚"。"""
    connection = psycopg.connect(live_url, autocommit=True, connect_timeout=5)
    try:
        return apply_migrations(connection, urlsplit(live_url).path.lstrip("/"))
    finally:
        connection.close()


def _columns(url: str) -> dict[str, dict[str, str]]:
    connection = psycopg.connect(url, connect_timeout=5)
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type, is_nullable, coalesce(column_default, '(-)') "
                "FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = ANY(%s)",
                (DATASET_VERSION_TABLE, list(SCOPE_COLUMNS)),
            )
            return {
                str(name): {"type": str(dtype), "null": str(null), "default": str(default)}
                for name, dtype, null, default in cur.fetchall()
            }
    finally:
        connection.rollback()
        connection.close()


def _statement_count(url: str) -> int:
    connection = psycopg.connect(url, connect_timeout=5)
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT count(*) FROM dataset_versions")
            return int(cur.fetchone()[0])
    finally:
        connection.rollback()
        connection.close()


def _user(departments: list[str]) -> dict:
    return {
        "id": "u-" + uuid.uuid4().hex[:8],
        "username": "r256-acceptance",
        "role": "manager",
        "department": departments[0],
        "department_ids": departments,
    }


def _registry(url: str, tmp_path: Path, departments: list[str]) -> DatasetRegistry:
    registry = DatasetRegistry(root=tmp_path, store=PostgresDatasetTableStore(database_url=url))
    registry.principal = Principal.from_user(_user(departments))  # type: ignore[attr-defined]
    return registry


def _write(tmp_path: Path, filename: str, body: str) -> Path:
    path = tmp_path / filename
    path.write_text("department,revenue\n" + body + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- 1. 整条目录在真库上跑到尾


def test_the_whole_catalog_applies_on_a_real_database(live_url, migrated) -> None:
    """A-1：空库上从 0001 跑到 0015，账本尾号就是 0015。

    这就是裸机那条路（``python scripts/migrate.py`` 背后同一个入口）今天真实的走法：0010 之前
    由 runner 申报 embedding profile，缺申报就停 —— 那一格不猜宽度。
    """
    versions = [item.version for item in migrated]

    assert versions, "runner 说一枚都没落：这枚库不是空库，本文件的证据不成立"
    assert VERSION in versions
    assert versions == [f"{number:04d}" for number in range(1, int(VERSION) + 1)], versions

    connection = psycopg.connect(live_url, connect_timeout=5)
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT version, name FROM schema_migrations ORDER BY version")
            ledger = [(str(v), str(n)) for v, n in cur.fetchall()]
    finally:
        connection.rollback()
        connection.close()

    assert ledger[-1] == (VERSION, "dataset_version_scope_columns"), ledger[-1]
    assert len(ledger) == len(MIGRATIONS), (len(ledger), len(MIGRATIONS))


def test_re_applying_0015_changes_nothing_on_a_real_database(live_url, migrated) -> None:
    """A-2：直接执行 0015 的原文第二遍 —— 列的形状与行数逐字不变。

    这一枚等价于 ``psql -v ON_ERROR_STOP=1 -f migrations/0015_*.sql``：列已在位时两枚
    ``ADD COLUMN IF NOT EXISTS`` 必须一句 DDL 都不做，两枚 ``COMMENT ON`` 也不碰数据。
    它同时是"这一版迁移可以安全重放"那句主张的可查形状 —— 不是注释，是执行。
    """
    assert migrated, "上一枚没把链跑完，这一枚就没有可比的前像"
    before = _columns(live_url)
    rows_before = _statement_count(live_url)

    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    connection = psycopg.connect(live_url, autocommit=True, connect_timeout=5)
    try:
        connection.execute(sql)
    finally:
        connection.close()

    assert _columns(live_url) == before, "重放 0015 改动了列的形状"
    assert _statement_count(live_url) == rows_before, "重放 0015 动了行 —— 它承诺过不写任何一行"


def test_the_two_columns_have_the_declared_shape(live_url, migrated) -> None:
    """A-3：两列在真库上是 ``text`` / ``jsonb``，``NOT NULL``，默认值各是 ``''`` 与 ``'[]'``。"""
    columns = _columns(live_url)

    assert set(columns) == set(SCOPE_COLUMNS), columns
    assert columns["classification"]["type"] == "text"
    assert columns["department_ids"]["type"] == "jsonb"
    for name in SCOPE_COLUMNS:
        assert columns[name]["null"] == "NO", f"{name} 可空：0015 声明的是 NOT NULL"
    assert columns["classification"]["default"] == "''::text", columns["classification"]
    assert columns["department_ids"]["default"] == "'[]'::jsonb", columns["department_ids"]


# ---------------------------------------------------------------- 2. 版本行真的存得下自己那一份口径


def test_a_registered_version_carries_its_own_scope_in_the_real_table(live_url, migrated, tmp_path) -> None:
    """A-4：登记把当时那一份口径抄在版本行上，换一枚登记表（=重启）读回来还是那一份。

    同步钉的是「列在 information_schema 里存在」；这一枚钉的是「产品真的写进了那两列」，
    而且经 PG 的 JSONB 规范化之后读回来仍是同一份部门集。
    """
    registry = _registry(live_url, tmp_path, [DEPT_A, DEPT_B])
    record = registry.register(
        _write(tmp_path, "sales.csv", "finance,100"),
        principal=registry.principal,
        filename="sales.csv",
        classification="confidential",
    )

    connection = psycopg.connect(live_url, connect_timeout=5)
    try:
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT classification, department_ids FROM {DATASET_VERSION_TABLE} "
                "WHERE dataset_version_id = %s",
                (record.current_version_id,),
            )
            row = cur.fetchone()
    finally:
        connection.rollback()
        connection.close()

    assert row is not None, "登记没在真库里留下这一版"
    assert str(row[0]) == "confidential", row
    assert list(row[1]) == [DEPT_A, DEPT_B], row

    restarted = _registry(live_url, tmp_path, [DEPT_A, DEPT_B])
    version = restarted.get_version(record.dataset_id, 1)
    assert version is not None
    assert version.classification == "confidential"
    assert version.department_ids == [DEPT_A, DEPT_B]


def test_a_version_row_without_a_recorded_scope_is_refused_not_inherited(live_url, migrated, tmp_path) -> None:
    """A-5：把版本行抹回 0015 之前的形状 ⇒ 按版本寻址交回 None（拒绝），不继承父行当前的口径。

    这正是 0015 存在的理由：降密父行不得一并放宽历史版本。真库上这一枚说的是
    ``DEFAULT ''`` / ``DEFAULT '[]'`` 这两枚默认值**行为上**确实是"没记过"，而不是"记成公开"。
    """
    registry = _registry(live_url, tmp_path, [DEPT_A])
    record = registry.register(
        _write(tmp_path, "sales.csv", "finance,100"),
        principal=registry.principal,
        filename="sales.csv",
        classification="confidential",
    )
    assert registry.scope_for_version(record.current_version_id) is not None

    connection = psycopg.connect(live_url, autocommit=True, connect_timeout=5)
    try:
        connection.execute(
            f"UPDATE {DATASET_VERSION_TABLE} SET classification = '', department_ids = '[]'::jsonb "
            "WHERE dataset_version_id = %s",
            (record.current_version_id,),
        )
    finally:
        connection.close()

    reopened = _registry(live_url, tmp_path, [DEPT_A])
    version = reopened.get_version(record.dataset_id, 1)
    assert version is not None and version.classification == "" and version.department_ids == []
    assert reopened.scope_for_version(record.current_version_id) is None, (
        "没记过口径的版本读回了父行当前的口径 —— 0015 要堵的那一枚洞又开了"
    )
