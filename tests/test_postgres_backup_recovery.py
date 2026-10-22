"""Isolated PostgreSQL backup and restore drill.

The same opt-in acceptance database used by the execution persistence tests is dumped,
restored into a freshly created sibling database, and compared. A restore therefore
never overwrites the source and never touches the configured application database.

Requires ``EB_PG_ACCEPTANCE_URL`` plus ``EB_PG_BIN_DIR`` pointing at the matching
PostgreSQL client tools. Without them this file reports as skipped: it is the only way the
drill can prove a real dump restores, and it must never aim at the application database.

================================================= R283: the drill has to name both landing points
Before this ticket the drill named ``chunks`` and stopped. ``chunk_vectors`` -- the table the
PGVector dual write maintains, and the row-for-row mirror of the vector collection the read
path still serves from Chroma (PGVector is the decided production vector store; Chroma is the
legacy store being retired and still answers reads today) -- was never named. So the drill
could go green while the mirrored half of the vector library was missing from the archive.
A whole-database ``pg_dump`` covers every table by construction, and that is reasoning, not
a drill: the reason this file exists is to replace that reasoning with a measurement.

Every landing point in ``VECTOR_LANDING_TABLES`` is therefore proven four separate ways:

1. the archive's own table of contents carries it -- as a relation definition *and* as
   ``TABLE DATA``, because an archive can name a table while holding no rows of it;
2. the restored database counts the same number of this drill's rows as the source does,
   and both equal the number the drill wrote -- compared per landing point, never as one
   whole-database number;
3. every seeded row's ``embedding`` in the restored database still equals the vector the
   drill wrote, at the recorded column width: this is what counts cannot see, since a
   shifted, truncated or re-typed vector column keeps its row count;
4. a real nearest-neighbour query runs against both databases under both operators, and the
   restored top-1 equals the source's, which equals a key declared before any database was
   asked.

``tests/test_r283_backup_covers_vector_table.py`` drives the same functions and the same SQL
against fake handles offline, including the damages listed above, so the assertions have
visible teeth in the offline gate as well. Taking ``chunk_vectors`` out of this drill turns
that file red -- by design, not by text matching.

判据④ —— 本文件的真机那一格在 R283 交回时（2026-09-26）**未验**，读数至今是 skip，不是 pass
------------------------------------------------------------------------------
本文件会 CREATE / DROP DATABASE，而 R283 落在离线：本机没有可连的一次性验收库（live-PG 凭据
不可连是记账里的已知欠账），所以本班一个字都没连、一枚库都没建。「真 dump 真恢复真相似度」
这一格今天没有被证过，把它当成通过就是假话；离线件
``tests/test_r283_backup_covers_vector_table.py`` 只证**判据的形状**（摘掉镜像会不会漏），
不证 PostgreSQL 的恢复行为。计划书「备份恢复演练覆盖 PG 向量列」那一格要等下面这条跑法真绿
一次才有得勾，R60（停写退役 Chroma）排在它后面。

复跑（一台跑得动隔离集群的机器；绝不指向应用库）：

1. 客户端工具要与服务器大版本配套。本机实测在位：
   ``$env:EB_PG_BIN_DIR = 'C:\\Program Files\\PostgreSQL\\16\\bin'``（``pg_dump.exe`` /
   ``pg_restore.exe`` 两枚都已确认存在）。
2. 一次性集群：``127.0.0.1:5433``。``_target_or_skip`` 拒 5432、拒非本机、拒库名不带
   ``enterprise_brain_accept`` 前缀；口令沿 ``tmp/pgvector-isolated-5433.secret``（DPAPI，
   永不打印），入口形状照 ``tmp/r256_acc.ps1``，方法学见
   ``docs/handoff/2026-09-15-orchestration-board.md`` §4CH「真库验收的两条方法学」。
3. 建库、按**本族夹具的宽度**声明二维、再迁移（照跑分窗定 768 会被 ``_require_drill_profile``
   当场拒；空库直接跑会被 ``UndefinedTable`` 拒，必须先迁移）：
   ``createdb -h 127.0.0.1 -p 5433 -U postgres enterprise_brain_accept_r283``
   ``psql  -h 127.0.0.1 -p 5433 -U postgres -d postgres -c "ALTER DATABASE enterprise_brain_accept_r283 SET app.embedding_dimension = 2"``
   ``python scripts/migrate.py --database-url postgresql://postgres@127.0.0.1:5433/enterprise_brain_accept_r283``
4. 跑点名片（不带全量门）：
   ``$env:EB_PG_ACCEPTANCE_URL = 'postgresql://postgres@127.0.0.1:5433/enterprise_brain_accept_r283'``
   ``$env:LOCAL_MODEL_NAME = '__eb_test_disabled__'``
   ``python -m pytest -q --no-header -p no:cacheprovider tests/test_postgres_backup_recovery.py tests/test_r283_backup_covers_vector_table.py``
   恢复兄弟库 ``enterprise_brain_accept_r283_restore`` 由本文件的 ``administrator`` 夹具自己
   CREATE、自己 DROP，不需要预先建。
5. 达标读数：本文件 ``3 passed`` 且 **0 skipped**（只要它报 skip，这一格就不算验过），
   离线件 ``22 passed``。两枚都达标之后，计划书那一格才具备被勾的条件。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import shutil
import uuid

import psycopg
import pytest

from scripts.backup_database import backup_database, missing_landing_tables
from scripts.restore_database import list_backup, restore_database
from tests.test_postgres_execution_persistence import _target_or_skip

PG_BIN = os.getenv("EB_PG_BIN_DIR", "").strip()

pytestmark = pytest.mark.skipif(
    not PG_BIN,
    reason="set EB_PG_BIN_DIR to run the PostgreSQL backup and restore drill",
)

_LEDGER_TABLES = (
    "datasets",
    "artifacts",
    "agent_runs",
    "agent_steps",
    "tool_calls",
    "model_calls",
    "retrieval_traces",
    "trace_events",
    "chunks",
)

#: R283 判据① 的唯一事实源：演练必须逐枚点名、证明能从备份文件里恢复回来的两枚向量落点。
#: ``chunks`` 是授权过滤与向量检索读的那一枚（含它的 ``embedding`` 列）；
#: ``chunk_vectors`` 是 PGVector 双写维护的那一枚，也就是读路径仍在服务的向量集合的行级镜像。
#: 把这里任何一枚摘掉，本文件的真机演练和同名离线钉都会变红——不许拿"整库 dump 必然覆盖"当证据。
VECTOR_LANDING_TABLES: tuple[str, ...] = ("chunks", "chunk_vectors")

#: 整个 ``_counts`` 台账比对覆盖的表：账本表加上两枚落点，落点不再只靠 owner 台账被顺带数到。
_COUNTED_TABLES = _LEDGER_TABLES + tuple(
    table for table in VECTOR_LANDING_TABLES if table not in _LEDGER_TABLES
)

#: 夹具的向量宽度。本族既有件（``test_postgres_execution_persistence``）插的就是二维向量，
#: 所以一次性验收库的 ``chunks`` / ``chunk_vectors`` 必须都定在 ``vector(2)``。
DRILL_DIMENSION = 2

#: 相似度探针向量。它到 ``[1,0]`` 的距离严格小于到本文件任何其它一枚向量的距离，
#: 所以"取回原 top-1"这句话有一个先于数据库的答案，而不是从库里读回来再比一次。
DRILL_QUERY_VECTOR = "[0.98,0.02]"

#: pgvector 里 ``<=>`` 是余弦距离、``<->`` 是 L2。``migrations/0010_pgvector_chunks.sql`` 把
#: L2 记进 ``vector_scope.distance_function``，既有演练写的是 ``<=>``。两把尺子都跑，才排除
#: "恢复回来的向量只在一把尺子下碰巧还对"。
DRILL_DISTANCE_OPERATORS = ("<=>", "<->")

#: 写进镜像列的模型标签，与 ``vector_scope`` 记的那一枚同源（一次性库按它建库）。
DRILL_EMBEDDING_MODEL = "nomic-embed-text"

_INSERT_CHUNK_SQL = (
    "INSERT INTO chunks (chunk_id, owner_id, resource_type, resource_id,"
    " resource_version_id, content, embedding)"
    " VALUES (%s, %s, 'document', %s, 'v1', %s, %s::vector)"
)

_INSERT_VECTOR_SQL = (
    "INSERT INTO chunk_vectors (vector_id, filename, chunk_index, content,"
    " classification, department, content_sha256, embedding, embedding_model,"
    " embedding_dimension, distance_function)"
    " VALUES (%s, %s, %s, %s, 1, 'finance', %s, %s::vector, %s, %s, 'l2')"
)


@dataclass(frozen=True)
class _Landing:
    """一枚落点在演练里的全部身份：怎么写、怎么数、怎么问最近邻。"""

    table: str
    key_column: str
    scope_column: str
    scope_value: str
    nearest_key: str
    statement: str
    #: 每行 ``(主键, 正文, 写进去的向量, 应当恢复出的向量)``。第三格为 ``None`` 的那一行是
    #: 故意留空的：它由 ``migrations/0010`` 的 ``sync_chunk_embedding()`` 触发器从镜像认领，
    #: 走的就是生产链路本身（``app/rag/indexing.py`` 从不写 ``chunks.embedding``）。
    rows: tuple[tuple[str, str, str | None, str], ...]


def _landings(tag: str) -> tuple[_Landing, ...]:
    """演练在两枚落点上写的行。

    顺序不是风格问题：镜像必须先落库，``chunks`` 里那一枚留空的 ``embedding`` 才有人认领。
    生产链路本来就是这个次序（先写向量集合，再发布 chunks 行），这里照它。

    每枚落点都有三行以上、方向互不相同的向量，最近邻严格唯一——否则"恢复回来的 top-1"
    可以靠并列撞对，那就不算取证。
    """
    return (
        _Landing(
            table="chunk_vectors",
            key_column="vector_id",
            scope_column="filename",
            scope_value=tag + ".doc",
            nearest_key=tag + ".doc_0",
            statement=_INSERT_VECTOR_SQL,
            rows=(
                (tag + ".doc_0", "chunk alpha", "[1,0]", "[1,0]"),
                (tag + ".doc_1", "chunk beta", "[0.7,0.7]", "[0.7,0.7]"),
                (tag + ".doc_2", "chunk gamma", "[0.2,0.9]", "[0.2,0.9]"),
            ),
        ),
        _Landing(
            table="chunks",
            key_column="chunk_id",
            scope_column="owner_id",
            scope_value="owner:" + tag,
            nearest_key=tag + ":near",
            statement=_INSERT_CHUNK_SQL,
            rows=(
                (tag + ":near", "chunk near", "[1,0]", "[1,0]"),
                (tag + ":mid", "chunk mid", "[0.7,0.7]", "[0.7,0.7]"),
                (tag + ":far", "chunk far", "[0,1]", "[0,1]"),
                # 正文与镜像的 doc_2 逐字相同，主键按 0010 的规则推出 vector_id "<tag>.doc_2"，
                # 于是触发器认领 [0.2,0.9]：这一行同时钉住"镜像恢复了"与"镜像到 chunks 的回填链
                # 在恢复后的库里仍然走得通"。
                (tag + ".doc|v1#2", "chunk gamma", None, "[0.2,0.9]"),
            ),
        ),
    )


def _tool(name: str) -> str:
    candidate = Path(PG_BIN) / (name + (".exe" if os.name == "nt" else ""))
    if candidate.is_file():
        return str(candidate)
    found = shutil.which(name)
    if not found:
        pytest.skip(name + " was not found; point EB_PG_BIN_DIR at the PostgreSQL bin directory")
    return found


@pytest.fixture(scope="module")
def targets() -> tuple[str, str, str]:
    source = _target_or_skip()
    if "://" not in source:
        raise RuntimeError("acceptance URL must be absolute")
    scheme, _, rest = source.partition("://")
    credentials, _, location = rest.rpartition("@")
    host_port, _, database = location.partition("/")
    restore_name = database + "_restore"
    if not restore_name.startswith("enterprise_brain_accept"):
        raise RuntimeError("the restore target must stay inside the acceptance namespace")
    target = scheme + "://" + credentials + "@" + host_port + "/" + restore_name
    return source, restore_name, target


@pytest.fixture
def administrator(targets):
    source, restore_name, _target = targets
    scheme, _, rest = source.partition("://")
    credentials, _, location = rest.rpartition("@")
    host_port, _, _database = location.partition("/")
    handle = psycopg.connect(
        scheme + "://" + credentials + "@" + host_port + "/postgres",
        autocommit=True,
        connect_timeout=5,
    )
    yield handle, restore_name
    handle.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
        (restore_name,),
    )
    handle.execute("DROP DATABASE IF EXISTS " + restore_name)
    handle.close()


def _require_drill_profile(handle) -> None:
    """把"这枚一次性库得是 vector(2) 且已经跑过 0010"说明白，别让 psycopg 抛裸 22000。"""
    if handle.execute("SELECT to_regclass('vector_scope')").fetchone()[0] is None:
        raise RuntimeError(
            "验收库没有 migrations/0010 落下的 vector_scope 台账：先跑"
            " python scripts/migrate.py --database-url <URL>"
        )
    dimension = int(handle.execute(
        "SELECT dimension FROM vector_scope WHERE schema_version = 1"
    ).fetchone()[0])
    if dimension != DRILL_DIMENSION:
        raise RuntimeError(
            f"验收库的向量宽度是 {dimension}，本族夹具写的是 {DRILL_DIMENSION} 维向量。"
            "一次性库要按被测族定宽度：ALTER DATABASE <库> SET app.embedding_dimension ="
            f" {DRILL_DIMENSION}; 再 python scripts/migrate.py --database-url <URL>"
        )


def _seed_parameters(landing: _Landing, tag: str, row: tuple[str, str, str | None, str]) -> tuple:
    key, content, written, _expected = row
    if landing.table == "chunks":
        return (key, landing.scope_value, tag + ":doc", content, written)
    return (
        key,
        landing.scope_value,
        int(key.rsplit("_", 1)[1]),
        content,
        "c" * 64,
        written,
        DRILL_EMBEDDING_MODEL,
        DRILL_DIMENSION,
    )


def _seed(source: str, tag: str) -> tuple[str, tuple[str, ...]]:
    """写入演练行，返回 ``(owner_id, 本次真写过行的落点表名)``。

    第二个返回值不是装饰：``verify_vector_landings`` 拿它所在的夹具集合与
    ``VECTOR_LANDING_TABLES`` 逐字比相等，所以"还在往镜像写行、却把镜像从断言里摘掉"
    这种演练会当场变红。
    """
    owner_id = "owner:" + tag
    written: list[str] = []
    with psycopg.connect(source, connect_timeout=5) as handle:
        _require_drill_profile(handle)
        handle.execute(
            "INSERT INTO datasets (dataset_id, owner_id, filename, department_ids,"
            " classification, visibility, storage_key, content_sha256, status, metadata)"
            " VALUES (%s, %s, %s, %s::jsonb, 'confidential', 'department', %s, %s, 'active',"
            " '{\"rows\": 7}'::jsonb)",
            (
                tag + ":dataset",
                owner_id,
                tag + ".xlsx",
                '["finance", "board"]',
                "datasets/" + tag + ".xlsx",
                "d" * 64,
            ),
        )
        handle.execute(
            "INSERT INTO agent_runs (agent_run_id, owner_id, request_id, trace_id, task_id,"
            " session_id, worker, status, error_code, metadata)"
            " VALUES (%s, %s, %s, %s, %s, %s, 'orchestrator', 'failed', 'model_unavailable',"
            " '{\"agent_result\": {\"evidence_count\": 2}}'::jsonb)",
            (tag + ":run", owner_id, tag + ":req", tag, tag + ":task", tag + ":session"),
        )
        for landing in _landings(tag):
            for row in landing.rows:
                handle.execute(landing.statement, _seed_parameters(landing, tag, row))
            written.append(landing.table)
        handle.commit()
    return owner_id, tuple(written)


def _counts(handle) -> dict[str, int]:
    return {
        table: handle.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        for table in _COUNTED_TABLES
    }


def _landing_count(handle, landing: _Landing) -> int:
    """那枚落点上属于本次演练的行数——逐枚数，不是一整本库一起数。"""
    return int(handle.execute(
        "SELECT COUNT(*) FROM " + landing.table
        + " WHERE " + landing.scope_column + " = %s",
        (landing.scope_value,),
    ).fetchone()[0])


def _landing_embedding_column(handle, landing: _Landing) -> str:
    row = handle.execute(
        "SELECT format_type(atttypid, atttypmod) FROM pg_attribute"
        " WHERE attrelid = %s::regclass AND attname = 'embedding'"
        " AND attnum > 0 AND NOT attisdropped",
        (landing.table,),
    ).fetchone()
    return "" if row is None or row[0] is None else str(row[0])


def _landing_vector_row(handle, landing: _Landing, key: str, expected_vector: str):
    """逐行取回向量：文本、宽度，以及它是否还等于演练写进去的那一发。"""
    return handle.execute(
        "SELECT embedding::text, vector_dims(embedding), embedding = %s::vector"
        " FROM " + landing.table + " WHERE " + landing.key_column + " = %s AND "
        + landing.scope_column + " = %s",
        (expected_vector, key, landing.scope_value),
    ).fetchone()


def _similarity_top1(handle, landing: _Landing, *, operator: str) -> tuple[str, float] | None:
    """真做一发向量相似度查询：按距离排序取 top-1，并把那一段距离一起取回来。

    光比行数不够——行数相等但向量错位、被截断或宽度不对，这里都会露出来。
    """
    row = handle.execute(
        "SELECT " + landing.key_column
        + ", round((embedding " + operator + " %s::vector)::numeric, 6)"
        " FROM " + landing.table + " WHERE " + landing.scope_column + " = %s"
        " ORDER BY embedding " + operator + " %s::vector LIMIT 1",
        (DRILL_QUERY_VECTOR, landing.scope_value, DRILL_QUERY_VECTOR),
    ).fetchone()
    return None if row is None else (str(row[0]), float(row[1]))


def verify_vector_landings(source, copy, *, tag: str, dimension: int = DRILL_DIMENSION):
    """R283 判据①＋②：两枚落点逐枚取证——行数、向量、宽度、最近邻四样都要对上。

    ``source`` / ``copy`` 只要支持 ``execute(sql, params)``：真机用例给两枚 psycopg 连接，
    离线件 ``tests/test_r283_backup_covers_vector_table.py`` 给一对假句柄。同一批函数、
    同一批 SQL，所以离线钉住的"判据到底有没有牙齿"不是另写一份平行断言。
    """
    fixtures = {landing.table: landing for landing in _landings(tag)}
    assert set(fixtures) == set(VECTOR_LANDING_TABLES), (
        "演练写入的落点集合与被断言的落点集合不再一致：夹具="
        + ", ".join(sorted(fixtures)) + " 断言=" + ", ".join(sorted(VECTOR_LANDING_TABLES))
        + "。两枚向量落点必须一起点名，整库 dump 不是证据。"
    )
    handles = (("来源库", source), ("恢复库", copy))
    report: dict[str, dict[str, object]] = {}
    for landing in _landings(tag):
        table = landing.table
        seeded = len(landing.rows)

        counts = {label: _landing_count(handle, landing) for label, handle in handles}
        assert counts["恢复库"] == counts["来源库"], (
            table + ": 恢复库数到 " + str(counts["恢复库"]) + " 行，来源库是 "
            + str(counts["来源库"]) + " 行——这枚落点没有整枚从备份里回来"
        )
        assert counts["恢复库"] == seeded, (
            table + ": 演练写入 " + str(seeded) + " 行，恢复库里数到 "
            + str(counts["恢复库"]) + " 行"
        )

        columns = {label: _landing_embedding_column(handle, landing) for label, handle in handles}
        assert columns["恢复库"] == "vector(" + str(dimension) + ")", (
            table + ": 恢复库的 embedding 列宽是 " + repr(columns["恢复库"])
            + "，不是 vector(" + str(dimension) + ")"
        )
        assert columns["来源库"] == columns["恢复库"], (
            table + ": 恢复库的 embedding 列宽与来源库不同："
            + repr(columns["来源库"]) + " vs " + repr(columns["恢复库"])
        )

        vectors: dict[str, dict[str, tuple[str, int]]] = {}
        for label, handle in handles:
            per_row: dict[str, tuple[str, int]] = {}
            for key, _content, _written, expected_vector in landing.rows:
                row = _landing_vector_row(handle, landing, key, expected_vector)
                assert row is not None, table + ": " + key + " 在" + label + "里数不到行"
                text, dims, equals = str(row[0]), row[1], row[2]
                assert equals is True, (
                    table + ": " + key + " 在" + label + "里的向量不再等于演练写入的 "
                    + expected_vector + "（实得 " + text + "）——行数相等不代表向量还在原位"
                )
                assert dims == dimension, (
                    table + ": " + key + " 在" + label + "里的向量宽度是 " + str(dims)
                    + "，不是 " + str(dimension)
                )
                per_row[key] = (text, int(dims))
            vectors[label] = per_row
        assert vectors["来源库"] == vectors["恢复库"], (
            table + ": 恢复库的向量列与来源库逐行不一致"
        )

        tops: dict[str, tuple[str, float]] = {}
        for operator in DRILL_DISTANCE_OPERATORS:
            source_top = _similarity_top1(source, landing, operator=operator)
            copy_top = _similarity_top1(copy, landing, operator=operator)
            assert source_top is not None and copy_top is not None, (
                table + ": " + operator + " 最近邻查询在链路上查不到任何一行"
            )
            assert source_top[0] == landing.nearest_key, (
                table + ": 来源库的 " + operator + " top-1 就不是预先声明的 "
                + landing.nearest_key + "（实得 " + source_top[0] + "）——夹具失去了区分度"
            )
            assert copy_top == source_top, (
                table + ": " + operator + " 最近邻在恢复库里变了："
                + repr(copy_top) + " != " + repr(source_top)
            )
            tops[operator] = copy_top

        report[table] = {
            "rows": counts["恢复库"],
            "column": columns["恢复库"],
            "vectors": vectors["恢复库"],
            "top1": tops,
        }
    assert set(report) == set(VECTOR_LANDING_TABLES), (
        "演练只点名了 " + ", ".join(sorted(report)) + "，落点清单是 "
        + ", ".join(sorted(VECTOR_LANDING_TABLES))
    )
    return report


def _delete_drill_rows(source: str, tag: str, owner_id: str) -> None:
    with psycopg.connect(source, connect_timeout=5) as handle:
        for landing in _landings(tag):
            handle.execute(
                "DELETE FROM " + landing.table + " WHERE " + landing.scope_column + " = %s",
                (landing.scope_value,),
            )
        for table in _LEDGER_TABLES:
            handle.execute("DELETE FROM " + table + " WHERE owner_id = %s", (owner_id,))
        handle.commit()


def test_backup_restores_schema_ownership_and_vectors(administrator, targets, tmp_path) -> None:
    source, restore_name, target = targets
    admin, _name = administrator
    tag = "brp-" + uuid.uuid4().hex[:8]
    owner_id, written = _seed(source, tag)
    assert set(written) == set(VECTOR_LANDING_TABLES), (
        "演练只往 " + ", ".join(sorted(written)) + " 写了行，落点清单要求 "
        + ", ".join(sorted(VECTOR_LANDING_TABLES))
    )
    try:
        archive = tmp_path / "acceptance.dump"
        backup_database(
            source,
            archive,
            pg_dump_path=_tool("pg_dump"),
            required_tables=VECTOR_LANDING_TABLES,
            pg_restore_path=_tool("pg_restore"),
        )
        assert archive.stat().st_size > 0

        entries = list_backup(archive, pg_restore_path=_tool("pg_restore"))
        joined = "\n".join(entries)
        for table in ("datasets", "agent_runs", "chunks", "schema_migrations"):
            assert table in joined, "the archive must contain " + table

        # 判据①（备份文件这一头）：两枚落点都必须以"关系定义 + 数据"两条目录出现。
        # 只出现表名不算证据——一张空表的目录行和一张被筛掉的表长得一样。
        absent = missing_landing_tables(entries, VECTOR_LANDING_TABLES)
        assert not absent, "归档目录没有带上（定义或数据）：" + ", ".join(sorted(absent))

        admin.execute("CREATE DATABASE " + restore_name)
        assert restore_database(
            archive, target, pg_restore_path=_tool("pg_restore")
        ) == restore_name

        with psycopg.connect(source, connect_timeout=5) as original, psycopg.connect(
            target, connect_timeout=5
        ) as copy:
            assert _counts(original) == _counts(copy)
            assert original.execute(
                "SELECT version, checksum FROM schema_migrations ORDER BY version").fetchall() == copy.execute(
                "SELECT version, checksum FROM schema_migrations ORDER BY version").fetchall()
            assert copy.execute(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone() is not None

            # 0010 的回填触发器必须随库一起回来：没有它，chunks.embedding 那半张脸在
            # 恢复后的库里永远填不满，而这一点光看行数看不出来。
            assert copy.execute(
                "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"
                " AND tgrelid = 'chunks'::regclass AND tgname = 'chunks_sync_embedding'"
            ).fetchone() is not None, "恢复库里没有 chunks_sync_embedding 触发器"

            source_row = original.execute(
                "SELECT owner_id, classification, visibility, jsonb_array_elements_text(department_ids)"
                " FROM datasets WHERE dataset_id = %s", (tag + ":dataset",)).fetchall()
            copy_row = copy.execute(
                "SELECT owner_id, classification, visibility, jsonb_array_elements_text(department_ids)"
                " FROM datasets WHERE dataset_id = %s", (tag + ":dataset",)).fetchall()
            assert source_row == copy_row
            assert [row[0] for row in copy_row] == [owner_id, owner_id]
            assert {row[3] for row in copy_row} == {"finance", "board"}

            run = copy.execute(
                "SELECT status, error_code, metadata -> 'agent_result' ->> 'evidence_count'"
                " FROM agent_runs WHERE agent_run_id = %s", (tag + ":run",)).fetchone()
            assert run == ("failed", "model_unavailable", "2")

            landing_report = verify_vector_landings(original, copy, tag=tag)
            assert set(landing_report) == set(VECTOR_LANDING_TABLES)
            for table, evidence in landing_report.items():
                assert evidence["rows"] > 0, table + ": 恢复库里这枚落点是空的"
                assert all(operator in evidence["top1"] for operator in DRILL_DISTANCE_OPERATORS), (
                    table + ": 相似度查询没有在两把尺子下都跑过"
                )

            with pytest.raises(psycopg.IntegrityError):
                copy.execute(
                    "INSERT INTO agent_steps (agent_step_id, agent_run_id, owner_id,"
                    " step_id, worker, status, sequence) VALUES (%s, %s, %s, %s,"
                    " 'doc_agent', 'completed', 1)",
                    (tag + ":orphan", tag + ":nope", owner_id, tag + ":orphan"),
                )
            copy.rollback()
    finally:
        _delete_drill_rows(source, tag, owner_id)


def test_restore_refuses_an_empty_archive(tmp_path, targets) -> None:
    empty = tmp_path / "empty.dump"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="missing or empty"):
        list_backup(empty, pg_restore_path=_tool("pg_restore"))
    with pytest.raises(ValueError, match="missing or empty"):
        restore_database(empty, targets[2], pg_restore_path=_tool("pg_restore"))


def test_restore_rejects_a_non_postgres_url() -> None:
    with pytest.raises(ValueError, match="PostgreSQL scheme"):
        restore_database("ignored.dump", "mysql://user:***@127.0.0.1:3306/anything")
