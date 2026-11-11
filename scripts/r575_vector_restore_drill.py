#!/usr/bin/env python
"""R575｜真库向量备份—恢复演练：把"这份 dump 能不能把生产向量库整枚恢复回来"做成可重跑的件。

为什么还要一枚新件（在册那枚真机演练够不到的地方，全部现取）
----------------------------------------------------------------
``tests/test_postgres_backup_recovery.py`` 是 R283 立的隔离演练，它要 ``EB_PG_ACCEPTANCE_URL``
（一条 **TCP** 连接）加 ``EB_PG_BIN_DIR``（**宿主**的 pg_dump/pg_restore），而它的
``_target_or_skip`` 当场拒 5432、拒非本机、拒库名不带 ``enterprise_brain_accept`` 前缀。生产这枚
PG 是 Docker 容器，**没有宿主端口映射**：本单现取 ``docker port enterprise-brain-postgres-1``
为空，宿主 5432 上监听的是原生 ``postgres.exe``（PID 现读），宿主直连容器 IP ``172.18.0.7:5432``
亦不可达。于是那条路**在生产数据上永远跑不到**——计划书「真库恢复演练」那一格等的一直是它，
而它在这台机上只能对一次性库跑。本件补的就是这一格：走部署里唯一存在的通道，``docker exec``
进容器跑 psql/pg_dump/pg_restore，产物用 ``docker cp`` 搬到仓外，量的是一库里的那 1008 枚真向量。

它证什么、不证什么（别把本件读大）
----------------------------------------------------------------
证：① 一份真 dump 的字节数与 sha256 在案，且容器内那枚与仓外那枚逐字节同；② 同一 PG 实例里
新建的库能把它恢复回来，恢复库与生产库**逐枚同数**——行数 / 向量枚数 / 列类型与维度 /
全零向量枚数 / ``vector_scope`` 行数与整行内容 / ``documents``+``chunks`` 行数 / 迁移集合，
外加两枚自己的牙齿：逐行向量内容的 md5 指纹、``chunk_vectors`` 索引定义清单；③ 恢复库能交出
与生产库**同样的 top-k**——读腿那句 SQL 由 ``app.rag.pg_store.search_vectors`` 自己拼（含 R386
那笔"同一事务、排名之前"的 ``hnsw.ef_search`` 钉），本件一个字都不抄、一个数字都不写死，
只把传输层换成 psql，并把会话里现读的候选宽度一并取回。
不证：物理备份与异地容灾、Chroma 那一侧、翻默认之后的召回质量与热集时延（计划书另外几格）。

R587 补的那一格（为什么"报一下"不够）：``pg_dump`` 按构造不带库级 ``ALTER DATABASE ... SET``，
而 ``app/db/migrations.py:57``/``:82`` 读的正是 ``app.embedding_dimension`` / ``app.embedding_model``
这两枚库级 setting。老口径里它们只进 ``EXTRA_ITEMS`` 照实上报，于是"12 项指纹全等 + 备份日志全绿"
的恢复库里这两枚是 MISSING——E 门「备份恢复演练通过」要的恰恰不是这个。今天两枚读数升到门控
（``globals_profile`` / ``globals_session``），备份工序另交一份与 dump 同目录同前缀的成对产物
（``*.globals.json`` / ``*.globals.sql``，里面记着归档 sha），恢复工序在**任何校验之前**把它打在
恢复库上并立刻现读现证；成对产物缺失、与归档 sha 不成对、被人手改开过，一律 REFUSE。

安全边界（写在代码里，不是写在纸上的承诺）
----------------------------------------------------------------
* 生产库全程只读，两道独立闸：每条语句先过 :func:`guard_statement`（前缀白名单 + 写关键字
  黑名单），整批再套进 ``BEGIN; SET LOCAL transaction_read_only = on;``；并且
  :func:`run_psql` 对 ``enterprise_brain`` 直接拒收任何非只读批次——就算本件有 bug，服务器也
  不许它写。
* 建库/删库只认 ``eb_r575_drill`` 这一枚名字（:func:`assert_creatable` / :func:`assert_droppable`
  各一道闸，把 ``enterprise_brain`` 递进去当场 REFUSE），恢复失败即自行删掉那枚半截库，不留残留。
* 产物一律落仓外 ``C:\\Users\\fengx\\PycharmProjects\\r575-drill\\``：:func:`assert_outside_worktree`
  逐级看 ``.git``，落进任何 git 工作树就 REFUSE。本件对工作树零写入。
* 全程不需要口令：容器内 unix socket 是 trust（现取实测），所以本件不读 ``deploy/.env.server``，
  也就没有把口令打印出来的可能。角色的存在与口令散列也不进 globals 产物（``pg_dumpall
  --globals-only`` 一手现取就交回一行带 SCRAM 散列的 ``ALTER ROLE``）；集群级
  ``ALTER ROLE ... SET`` 一律只上报不施加——它会改整台实例的所有库。
* globals 施加件只准打在恢复库上：:func:`apply_globals` 拿到 ``enterprise_brain`` 当场 REFUSE，
  施加走 ``BEGIN;``/``COMMIT;`` 一笔事务（真机实测一句坏话会让两枚 ALTER 一起回滚），
  所以恢复库里要么两枚 setting 都在、要么一枚都没有。

退出码（不可合并，合并就是说谎）
----------------------------------------------------------------
0 全部达标 ／ 1 未预期错误 ／ 2 前置不满足或危险动作被拒（不出任何对账结论）／
3 对账不等（判据②/①红） ／ 4 检索对账红（``only_in_*`` 非 0） ／ 5 残留（库名集合没回到演练前）

跑法
----------------------------------------------------------------
``.venv\\Scripts\\python.exe -X utf8 scripts/r575_vector_restore_drill.py full``
分步：``preflight`` / ``backup`` / ``restore`` / ``reconcile`` / ``recall`` / ``cleanup``
（``restore`` 之后的单步要 ``--archive <dump 路径>``，或 ``full --skip-backup --archive ...``）。
三把反证（判据④，命令与读数见 ``docs/testing/r575-vector-restore-drill-2026-10-03.md``）：
``restore --archive <半截副本>`` ⇒ rc=2；同一枚再加 ``--expect-sha256 <原 sha>`` ⇒ 更早一道红；
``reconcile --skip-vector-check`` ⇒ rc=3（对账缺项即红，不许绿）；
``preflight --source-db eb_does_not_exist`` ⇒ rc=2 且明写是哪一枚库。
R587 的三把（判据④，同交摘前/摘后 sha256）：摘掉 :func:`apply_globals` 那一步 ⇒ 第③格必须红；
把恢复库一枚 setting 改成别的值 ⇒ 必须红；把恢复库那两枚 RESET 空（= 老口径下"恢复库为空"）⇒
必须红。常驻版在 ``tests/test_r587_globals_pair_gates_the_e_gate.py``，真库读数与 sha 对在
``docs/testing/r587-globals-pair-in-the-e-gate-2026-10-03.md``。
离线钉（不连库、桩住 docker）：``tests/test_r575_vector_restore_drill.py``。
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONTAINER_DEFAULT = "enterprise-brain-postgres-1"
PG_USER = "enterprise_brain"
SOURCE_DB = "enterprise_brain"
DRILL_DB = "eb_r575_drill"
MAINT_DB = "postgres"
ARTIFACT_DIR_DEFAULT = r"C:\Users\fengx\PycharmProjects\r575-drill"
SCRATCH_ROOT = "/tmp/r575-drill"
NULL_MARK = "__R575_NULL__"
BOUNDARY = "@@R575_BOUNDARY@@"
READ_ONLY_PIN = "SET LOCAL transaction_read_only = on"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2
EXIT_MISMATCH = 3
EXIT_RECALL = 4
EXIT_RESIDUE = 5

#: 落点清单沿用 R283 那两枚名字：归档里缺定义或缺数据的，一律 REFUSE。
VECTOR_LANDING_TABLES = ("chunks", "chunk_vectors")
#: 本件只点名这几枚表来数行，表名不从外部输入拼接。
COUNTED_TABLES = ("chunk_vectors", "vector_scope", "documents", "chunks")

#: 判据②那七项在件里的读数名（documents/chunks 是一组两项读数）。
RECON_ITEMS = (
    "chunk_vectors_rows",
    "embedding_count",
    "embedding_column_type",
    "embedding_dims",
    "zero_vector_rows",
    "vector_scope_rows",
    "vector_scope_profile",
    "documents_rows",
    "chunks_rows",
    "schema_migrations",
    "vector_content_md5",
    "chunk_vector_indexes",
    #: R587：库级/角色级 setting 升进门控。pg_dump 按构造不带它们，不门控就是假绿。
    "globals_profile",
    "globals_session",
)
#: 反证②摘掉的就是这一族：摘了还报绿，等于对账里没有向量列。
VECTOR_CHECK_ITEMS = (
    "embedding_count",
    "embedding_column_type",
    "embedding_dims",
    "zero_vector_rows",
    "vector_content_md5",
)
#: 门禁之外照实上报的两项。原来这三项里的两枚（db_local_settings / local_embedding_gucs）读的是
#: 同一件事——库级 setting 在不在——R587 把它升成门控（见 RECON_ITEMS），一格只留一个口径。剩下的
#: 两枚都是恢复单库这件事管不着的集群级读数：globals_deferred（ALTER ROLE ... SET，施加它会改整台
#: 实例，所以只上报）、cluster_roles（角色清单；pg_dumpall --globals-only 会把 SCRAM 口令散列一起
#: 抄进备份件，本件不抄，也就没有把口令打印出来的可能）。
EXTRA_ITEMS = ("globals_deferred", "cluster_roles")

_ALLOWED_PREFIX = re.compile(
    r"^\s*(SELECT|WITH|SHOW|BEGIN|COMMIT|ROLLBACK|END|SAVEPOINT|RELEASE)\b", re.I)
_WRITE_KEYWORDS = (
    "DELETE", "UPDATE", "INSERT", "TRUNCATE", "DROP", "ALTER", "CREATE", "GRANT", "REVOKE",
    "COPY", "VACUUM", "REINDEX", "REFRESH", "CALL", "DO", "PREPARE", "DEALLOCATE", "COMMENT",
    "CLUSTER", "LOCK", "CHECKPOINT", "DISCARD", "LISTEN", "UNLISTEN", "NOTIFY", "RESET",
    "MERGE", "ANALYZE", "REASSIGN", "SECURITY",
)
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

COUNT_SQL_TEMPLATE = "SELECT count(*) FROM {}"
COUNT_COLUMN_SQL_TEMPLATE = "SELECT count({}) FROM {}"
EMBEDDING_TYPE_SQL = (
    "SELECT coalesce(format_type(atttypid, atttypmod), 'MISSING') FROM pg_attribute "
    "WHERE attrelid = 'chunk_vectors'::regclass AND attname = 'embedding' "
    "AND attnum > 0 AND NOT attisdropped"
)
EMBEDDING_DIMS_SQL = (
    "SELECT coalesce(min(vector_dims(embedding))::text || '..' || "
    "max(vector_dims(embedding))::text, 'EMPTY') FROM chunk_vectors"
)
VECTOR_SCOPE_PROFILE_SQL = (
    "SELECT coalesce(string_agg(format('%s|%s|%s|%s|%s|%s|%s|%s', schema_version, "
    "embedding_model, dimension, distance_function, hnsw_m, hnsw_ef_construction, "
    "created_at, updated_at), ' ;; ' ORDER BY schema_version), 'EMPTY') FROM vector_scope")
MIGRATIONS_SQL = ("SELECT coalesce(string_agg(version, ',' ORDER BY version), 'EMPTY') "
                  "FROM schema_migrations")
CONTENT_MD5_SQL = (
    "SELECT coalesce(md5(string_agg(vector_id || '#' || embedding::text, ';' ORDER BY "
    "vector_id)), 'EMPTY') FROM chunk_vectors")
INDEXES_SQL = (
    "SELECT coalesce(string_agg(indexname || ' :: ' || indexdef, ' ;; ' ORDER BY indexname), "
    "'NONE') FROM pg_indexes WHERE tablename = 'chunk_vectors'")
ROLES_SQL = (
    "SELECT coalesce(string_agg(rolname || ':' || CASE WHEN rolsuper THEN 'super' "
    "ELSE 'nosuper' END, ',' ORDER BY rolname), 'NONE') FROM pg_roles")
#: R587 摘掉的两枚旧读数常量（DB_LOCAL_SETTINGS_SQL / LOCAL_GUC_SQL）：它们读的就是「库级 setting
#: 在不在」这一件事，现在由 collect_globals 一处取、进门控。一枚口径两处取，早晚各说各话——R393
#: 那笔现形账就是两枚并排放着、一窄一宽量出来的。恢复库叫别的名字，所以旧那枚 db=%s 形状两侧永远
#: 不等，也只能上报；新的对账钥匙（globals_profile_key）天生不带库名。
SAMPLE_VECTORS_SQL_TEMPLATE = (
    "SELECT vector_id, embedding::text FROM chunk_vectors "
    "ORDER BY md5(vector_id), vector_id LIMIT {}")
LIST_DATABASES_SQL = "SELECT datname FROM pg_database ORDER BY datname"
SESSION_IDENTITY_SQL = ("SELECT current_setting('server_version') || '/' || "
                        "system_identifier::text FROM pg_control_system()")
WIDTH_PROBE_SQL = "SELECT current_setting('hnsw.ef_search')"
ENSURE_VECTOR_LIB_SQL = "SELECT NULL::vector IS NULL"
WIDTH_BOUNDS_SQL = (
    "SELECT coalesce(min_val, 'NULL') || '/' || coalesce(max_val, 'NULL') || '/' || "
    "coalesce(boot_val, 'NULL') FROM pg_settings WHERE name = 'hnsw.ef_search'")

# ============================================================================
# R587｜库级/角色级 setting（globals）：备份成对取，恢复在校验之前重新施加
# ----------------------------------------------------------------------------
# 为什么这一族必须进件（不是"再报一次数"）：``pg_dump`` 按构造不带 ``ALTER DATABASE ... SET``
# ——总控 10-03 现取那枚真 dump 的 269 条目录里零命中，而 ``pg_db_role_setting`` 上
# ``enterprise_brain`` 与 ``eb_r59_sandbox`` 两枚都挂着 ``app.embedding_dimension=768`` /
# ``app.embedding_model=nomic-embed-text``。消费方就在树上：``app/db/migrations.py`` 里那两枚
# ``EMBEDDING_*_GUC``（0010 靠它们判"这库声明了哪套向量档"，读不到就当场停）。于是老口径是：
# 备份日志全绿、12 项指纹全等、恢复库里这两枚却是 MISSING——E 门「备份恢复演练通过」因此是
# 一枚假绿。R575 纸面 §7 发现一早就把它记成了一笔"照实上报"，而上报不等于判红，本单升成门控。
#
# 三条设计约束（都是被在册的钉与真机行为逼出来的，不是口味）：
# * 施加的语句文本由**服务器**自己 ``format()`` 出来再 ``\gexec`` 执行，Python 一头不拼库名：
#   库名走 ``current_database()``，所以这一份产物天生跟着恢复库走，抄给别的库也用不成。
#   （同一个理由见 ``app/db/migrations.py`` 里那笔 ``%I``/``%L`` 的注释。）
# * 集群级的 ``ALTER ROLE ... SET``（``setdatabase`` 为空）**只上报不施加**：施加它会改整台实例
#   上所有库，越出一库一机的私有化边界。角色的存在与口令也不进产物——本席一手现取
#   ``pg_dumpall --globals-only`` 只交回一行 ``CREATE ROLE`` 加一行带 SCRAM 口令散列的
#   ``ALTER ROLE``，把口令抄进备份件不是这单要开的口子。
# * 施加走"整份文件原样进一枚新 psql 会话"（``BEGIN;`` + 逐枚 ``\gexec`` + ``COMMIT;``）：真机
#   实测掺一句坏话会让 ``ON_ERROR_STOP=1`` 中止且整笔事务回滚（两枚 ALTER 全部没落地），所以
#   恢复库里要么两枚都在、要么一枚都没有——不许出现半套 setting。
# ============================================================================

#: 成对产物的名字只从归档名派生：同目录、同前缀，一眼能核对是哪一枚 dump 的 globals。
GLOBALS_JSON_SUFFIX = ".globals.json"
GLOBALS_SQL_SUFFIX = ".globals.sql"
#: 产物里带这一枚 kind，读的时候先验身份：别的件生成的同名文件不许冒充。
GLOBALS_KIND = "r587-database-globals"
#: 三种作用域；``deferred`` 指集群级角色 setting，本件只上报、绝不施加。
GLOBALS_SCOPES = ("database", "role_in_database", "deferred")
#: 判据①点名的三列（setdatabase / setrole / setconfig）逐枚在位，另外四列只把 oid 翻译回名字、
#: 把 setconfig 那一枚数组摊平成「一名一句」。WHERE 收到「当前这库」：库级行按名对，setdatabase
#: 为空的集群级行也按 current_database() 归到当前库（它们确实对当前会话生效），所以它们进了
#: deferred 这一栏被点名上报，而不是被静悄悄地丢掉。
GLOBALS_SQL = (
    "SELECT CASE WHEN st.setdatabase IS NULL THEN 'deferred' "
    "WHEN st.setrole = 0 THEN 'database' ELSE 'role_in_database' END, "
    "st.setdatabase, st.setrole, coalesce(db.datname, current_database()), "
    "coalesce(r.rolname, '(all)'), split_part(cfg.item, '=', 1), "
    "substring(cfg.item FROM position('=' in cfg.item) + 1) "
    "FROM pg_db_role_setting st "
    "LEFT JOIN pg_database db ON db.oid = st.setdatabase "
    "LEFT JOIN pg_roles r ON r.oid = st.setrole "
    "CROSS JOIN LATERAL unnest(st.setconfig) AS cfg(item) "
    "WHERE coalesce(db.datname, current_database()) = current_database() "
    "ORDER BY 1, 2, 3, 6"
)
#: 一库多行时 ``(all)`` 是"这库里的所有角色"这一**标签**，不是库名，也不碰黑名单里的 CLUSTER。
GLOBALS_ALL_ROLES_LABEL = "(all)"
#: 会话里读一枚 setting 的形状；名字来自 ``app/db/migrations.py``，名与值都不写死。
SESSION_GUC_SQL_PREFIX = "SELECT coalesce(current_setting("
#: 施加模板：占位符只吃"验过的名字 + 字面量化后的值"，库名一律由 ``current_database()`` 现算。
DATABASE_APPLY_LINE = (
    "SELECT format('ALTER DATABASE %I SET {name} = %L', "
    "current_database(), {value}) \\gexec")
ROLE_APPLY_LINE = (
    "SELECT format('ALTER ROLE %I IN DATABASE %I SET {name} = %L', "
    "{role}, current_database(), {value}) \\gexec")
#: ``setting`` 名要进 SQL 文本，所以它先得长得像一个名字（值走 ``sql_literal``，不受此限）。
_SETTINGS_NAME = re.compile(r"^[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*$")
#: ``pg_db_role_setting`` 一行摊平成"一名一句"之后，件内认得的七列。
GLOBALS_COLUMNS = ("scope", "setdatabase", "setrole", "database", "role", "name", "value")


def checked_setting_name(name) -> str:
    if not _SETTINGS_NAME.match(name or ""):
        raise Refuse(f"setting 名必须是小写点分标识符，拿到 {name!r}")
    return name


def session_guc_sql(name: str) -> str:
    return SESSION_GUC_SQL_PREFIX + sql_literal(checked_setting_name(name)) + ", TRUE), 'MISSING')"


def required_global_settings() -> tuple:
    """恢复库必须逐枚等上的那几枚名字——真源是迁移件，本件不再抄一份。"""
    from app.db import migrations

    return (migrations.EMBEDDING_DIMENSION_GUC, migrations.EMBEDDING_MODEL_GUC)


def globals_paths_for(archive) -> dict:
    archive = Path(archive)
    base = str(archive.parent / archive.stem)
    return {"archive": archive, "json": Path(base + GLOBALS_JSON_SUFFIX),
            "sql": Path(base + GLOBALS_SQL_SUFFIX)}


def globals_profile_key(row: dict) -> str:
    """对账的钥匙不带库名：恢复库本来就叫别的名字，带上它两侧永远不等（老口径的死因）。"""
    return f"{row['scope']}|{row['role']}|{row['name']}"


def globals_profile(rows) -> str:
    applied = [row for row in rows if row["scope"] != "deferred"]
    return " ;; ".join(sorted(globals_profile_key(row) + "=" + str(row["value"])
                              for row in applied)) or "EMPTY"


def globals_session_values(session: dict, names) -> list:
    """逐枚点名每颗 setting 的会话读数；``None`` 只准在这里现形，落进对账串它就变成 MISSING 了。"""
    return [(name, session.get(name)) for name in names]


def globals_session_profile(session: dict, names) -> str:
    return " ;; ".join(f"{name}={value}" for name, value in globals_session_values(session, names))


def globals_deferred_profile(rows) -> str:
    deferred = [row for row in rows if row["scope"] == "deferred"]
    return " ;; ".join(sorted(f"role={row['role']} {row['name']}={row['value']}"
                              for row in deferred)) or "NONE"


def checked_globals_row(cells) -> dict:
    """一行 setting 先得是七列，名字与值都得是能跑的形态。"""
    values = [None] if isinstance(cells, dict) else list(cells)
    if isinstance(cells, dict):
        values = [cells.get(key) for key in GLOBALS_COLUMNS]
    values = values + [None] * (7 - len(values))
    scope, setdatabase, setrole, database, role, name, value = values[:7]
    if scope not in GLOBALS_SCOPES:
        raise Refuse("globals 读数交了认不得的作用域 " + repr(scope)
                     + "（在册：" + ", ".join(GLOBALS_SCOPES) + "）")
    checked_setting_name(name)
    if value is None:
        raise Refuse(f"setting {name!r} 的值读成了空：pg_db_role_setting 的行形被改坏了")
    return {"scope": scope, "setdatabase": setdatabase, "setrole": setrole,
            "database": database, "role": role, "name": name, "value": value}


def checked_globals_rows(rows) -> list:
    if not isinstance(rows, list):
        raise Refuse(f"globals 产物里的 rows 不是清单：{type(rows).__name__}")
    checked = [checked_globals_row(row) for row in rows]
    for row in checked:
        if row["scope"] == "deferred" and row["setdatabase"] is not None:
            raise Refuse("globals 读数自相矛盾：deferred 行带着 setdatabase="
                         + str(row["setdatabase"]))
        if row["scope"] != "deferred" and not row["database"]:
            raise Refuse("globals 读数自相矛盾：库级行没有库名")
        if row["scope"] == "role_in_database" and not row["role"]:
            raise Refuse("globals 读数自相矛盾：角色级行没有角色名")
    keys = [globals_profile_key(row) for row in checked if row["scope"] != "deferred"]
    duplicated = sorted({key for key in keys if keys.count(key) > 1})
    if duplicated:
        raise Refuse("同一库里同一枚作用域出现了重名 setting：" + ", ".join(duplicated))
    return checked


def collect_globals(container: str, database: str) -> dict:
    """现取这库的库级/角色级 setting，外加会话里那几枚必读项的读数。"""
    rows = [checked_globals_row(cells) for cells in
            run_psql(container, database, [GLOBALS_SQL], timeout=300)[0]]
    names = list(required_global_settings())
    sets = run_psql(container, database, [session_guc_sql(name) for name in names], timeout=300)
    session = {name: (result[0][0] if result and result[0] else None)
               for name, result in zip(names, sets)}
    return {"database": database, "rows": rows, "session": session, "names": names,
            "profile": globals_profile(rows),
            "session_profile": globals_session_profile(session, names),
            "deferred_profile": globals_deferred_profile(rows)}


def globals_apply_line(row: dict) -> str:
    if row["scope"] == "deferred":
        raise Refuse("集群级 ALTER ROLE ... SET 不许由本件施加（它会改整台实例的所有库）："
                     + f"{row['role']} {row['name']}")
    template = DATABASE_APPLY_LINE if row["scope"] == "database" else ROLE_APPLY_LINE
    value = sql_literal(row["value"])
    # 先换名字、再换角色、最后才换值：值里若带着 "{name}" 这样的字面文本，不能被二次替换。
    line = template.replace("{name}", checked_setting_name(row["name"]))
    if row["scope"] == "role_in_database":
        line = line.replace("{role}", sql_literal(row["role"]))
    return line.replace("{value}", value)


def globals_apply_lines(rows) -> list:
    applied = sorted((row for row in rows if row["scope"] != "deferred"),
                     key=lambda row: (row["scope"], str(row["role"]), row["name"]))
    return [globals_apply_line(row) for row in applied]


def globals_sql_body(text: str) -> list:
    """施加件里真正是语句的那几行（注释与事务壳剥掉，逐字节比要用）。"""
    body = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--") or stripped in ("BEGIN;", "COMMIT;"):
            continue
        body.append(stripped)
    return body


def render_globals_sql(payload: dict) -> str:
    archive = payload["archive"]
    deferred = [row for row in payload["rows"] if row["scope"] == "deferred"]
    header = [
        "-- R587｜库级/角色级 setting 的施加件：与同名 .dump 成对，别单飞。",
        f"-- 源库 {payload['source_db']} 现取于 {payload['captured_utc']}；库名只进注释作账，"
        "语句里一枚都不带（库名由 current_database() 现算）。",
        f"-- 配对凭据：{archive['name']} sha256={archive['sha256']}",
        f"-- 施加 {len(payload['apply_lines'])} 枚；集群级 {len(deferred)} 枚只上报，逐枚点名：",
    ]
    header += [f"-- deferred role={row['role']} {row['name']}={row['value']}" for row in deferred]
    return "\n".join(header + ["BEGIN;"] + list(payload["apply_lines"]) + ["COMMIT;"]) + "\n"


def write_globals_artifacts(artifact_dir: Path, reading: dict, *, archive,
                           stamp: str | None = None) -> dict:
    """判据①的落盘：同目录、同前缀、带归档 sha 的成对产物（json 是账，sql 是能跑的件）。"""
    archive = Path(archive)
    if not archive.is_file():
        raise Refuse(f"globals 产物要配对归档，可归档不存在：{archive}")
    paths = globals_paths_for(archive)
    assert_outside_worktree(paths["json"].parent)
    payload = {
        "kind": GLOBALS_KIND,
        "source_db": reading["database"],
        "captured_utc": stamp or utc_stamp(),
        "archive": {"name": archive.name, "path": str(archive),
                    "bytes": archive.stat().st_size, "sha256": sha256_file(archive)},
        "rows": reading["rows"],
        "session": reading["session"],
        "names": list(reading["names"]),
        "profile": reading["profile"],
        "session_profile": reading["session_profile"],
        "deferred_profile": reading["deferred_profile"],
        "apply_lines": globals_apply_lines(reading["rows"]),
    }
    paths["json"].write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
                             encoding="utf-8")
    paths["sql"].write_text(render_globals_sql(payload), encoding="utf-8")
    return {"json": str(paths["json"]), "sql": str(paths["sql"]),
            "json_sha256": sha256_file(paths["json"]), "sql_sha256": sha256_file(paths["sql"]),
            "archive": str(archive), "archive_sha256": payload["archive"]["sha256"],
            "applied": len(payload["apply_lines"]),
            "deferred": len([row for row in payload["rows"] if row["scope"] == "deferred"]),
            "profile": payload["profile"], "session_profile": payload["session_profile"]}


def read_globals_artifact(archive, *, paths: dict | None = None) -> dict:
    """把成对产物读回一枚可信的 payload；四处不成对任一处红，都不许"缺失但看起来能跑"。"""
    archive = Path(archive)
    paths = paths or globals_paths_for(archive)
    absent = [str(paths[key]) for key in ("json", "sql") if not Path(paths[key]).is_file()]
    if absent:
        raise Refuse("备份没有成对的 globals 产物（判据①）：" + "、".join(absent)
                     + "——少了它，恢复库的 " + "/".join(required_global_settings())
                     + " 就是 MISSING，备份日志再绿也是假绿")
    try:
        payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Refuse(f"globals 产物读不动：{paths['json']}（{exc}）") from exc
    if not isinstance(payload, dict):
        raise Refuse(f"globals 产物不是对象：{paths['json']}")
    if payload.get("kind") != GLOBALS_KIND:
        raise Refuse("globals 产物的 kind 不对：期望 " + GLOBALS_KIND + "，实得 "
                     + repr(payload.get("kind")) + f"（{paths['json']}）")
    recorded = (payload.get("archive") or {}).get("sha256")
    actual = sha256_file(archive)
    if not recorded or recorded != actual:
        raise Refuse("globals 产物与归档不成对：产物记的归档 sha=" + str(recorded)[:12]
                     + f"，{archive.name} 实得 sha={actual[:12]}——这两枚不是同一次备份")
    rows = checked_globals_rows(payload.get("rows"))
    names = list(required_global_settings())
    session = payload.get("session")
    if not isinstance(session, dict):
        raise Refuse(f"globals 产物里没有会话读数那本账：{paths['json']}")
    unread = [name for name in names if name not in session]
    if unread:
        raise Refuse("globals 产物里没有这几枚必读 setting 的源值：" + ", ".join(unread))
    lines = globals_apply_lines(rows)
    if payload.get("apply_lines") != lines:
        raise Refuse("globals 产物里记的施加语句与按 rows 现算的不等（产物被改开过？）："
                     + f"{len(payload.get('apply_lines') or [])} 枚 vs {len(lines)} 枚")
    body = globals_sql_body(Path(paths["sql"]).read_text(encoding="utf-8"))
    if body != lines:
        raise Refuse(".globals.sql 里的语句与产物记录逐字节不等（被人手改开过？）："
                     + f"{len(body)} 枚 vs {len(lines)} 枚")
    payload.update({"rows": rows, "names": names, "apply_lines": lines,
                    "json_path": str(paths["json"]), "sql_path": str(paths["sql"]),
                    "archive_path": str(archive), "archive_sha256": actual})
    return payload


def apply_globals(container: str, database: str, payload: dict) -> dict:
    """判据②：整份施加件原样进一枚新 psql 会话，落在恢复库上，生产库当场拒收。"""
    if database == SOURCE_DB:
        raise Refuse(f"globals 施加件只准打在恢复库上，{SOURCE_DB} 一枚都不许碰")
    if database != DRILL_DB:
        raise Refuse(f"globals 施加件只准打在 {DRILL_DB} 上，拿到 {database!r}")
    sql_path = Path(payload["sql_path"])
    body = sql_path.read_text(encoding="utf-8")
    if not body.strip():
        raise Refuse(f"globals 施加件是空的：{sql_path}")
    note_statement(database, "psql -f " + sql_path.name
                   + "（R587 库级/角色级 setting 重新施加，BEGIN/COMMIT 一笔事务）",
                   kind="globals_apply")
    docker_exec(container, psql_argv(database), stdin=body, timeout=300)
    return {"sql": str(sql_path), "json": payload["json_path"],
            "applied": len(payload["apply_lines"]),
            "deferred": len([row for row in payload["rows"] if row["scope"] == "deferred"]),
            "archive_sha256": payload["archive_sha256"], "database": database}


def verify_globals(container: str, database: str, payload: dict) -> list:
    """施加完立刻在新库里现读现证：不等就是红，而且这条红发生在任何对账之前。"""
    got = collect_globals(container, database)
    problems = []
    wanted = {globals_profile_key(row): str(row["value"]) for row in payload["rows"]
              if row["scope"] != "deferred"}
    have = {globals_profile_key(row): str(row["value"]) for row in got["rows"]
            if row["scope"] != "deferred"}
    for key in sorted(set(wanted) | set(have)):
        if key not in have:
            problems.append(f"{key}: 备份里有、恢复库没有（施加那一步没落地）")
        elif key not in wanted:
            problems.append(f"{key}={have[key]}: 恢复库里多出一枚备份没有的 setting")
        elif wanted[key] != have[key]:
            problems.append(f"{key}: 备份={wanted[key]!r} 恢复库={have[key]!r}")
    for name, value in globals_session_values(got["session"], payload["names"]):
        recorded = payload["session"].get(name)
        if value is None:
            problems.append(f"{name}: 恢复库里读不到会话读数（件里没这条答案）")
        elif value in ("", "MISSING"):
            problems.append(f"{name}: 恢复库里它是 MISSING——正是"
                            "「备份日志全绿、恢复后读腿维度是错的」那枚假绿")
        elif recorded is not None and str(recorded) != str(value):
            problems.append(f"{name}: 备份记的会话值={recorded!r} 恢复库现读={value!r}")
    return problems


def gate_required_globals(source: dict, restored: dict) -> list:
    """判据③的对账那一腿：逐枚等才算过，读不到也判红，两侧都 MISSING 同样判红。"""
    problems = []
    for name in required_global_settings():
        before = (source.get("globals_session_map") or {}).get(name)
        after = (restored.get("globals_session_map") or {}).get(name)
        label = f"globals_session[{name}]: 生产={before!r} 恢复={after!r}"
        if before is None or after is None:
            problems.append("globals 读数取不到：" + label + "（对账缺项即红，沉默不是通过）")
        elif before in ("", "MISSING"):
            problems.append("源库上它本来就没声明：" + label + "——备份配不出可信的施加件")
        elif after in ("", "MISSING"):
            problems.append("恢复库里它是 MISSING：" + label
                            + "。向量一枚不少、备份日志全绿，读腿维度仍是错的——R587 拆的就是这枚假绿")
        elif str(before) != str(after):
            problems.append("恢复库与源库不等：" + label)
    return problems


LEDGER: list = []


class Refuse(RuntimeError):
    """前置不满足或危险动作：不出任何对账结论（EXIT_REFUSED）。"""


class Mismatch(RuntimeError):
    """对账不等（EXIT_MISMATCH）。"""


class RecallRed(RuntimeError):
    """恢复库交出的 top-k 与生产库不同（EXIT_RECALL）。"""


class Residue(RuntimeError):
    """演练收尾后库名集合没回到演练前那一集（EXIT_RESIDUE）。"""


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def note_statement(database: str, statement: str, kind: str = "psql") -> None:
    LEDGER.append({"database": database, "kind": kind, "statement": statement})


def ledger_for(database: str) -> list:
    return [item["statement"] for item in LEDGER if item["database"] == database]


def guard_statement(statement: str) -> None:
    """只读语句才活得过这道闸。

    前缀白名单是在册读腿与数数语句真正拼出来的那几种开头；写关键字黑名单是第二道带子：一句
    话里任何位置出现写动词——注释里、字符串里、随你哪里——都在碰到 socket 之前被拒。词边界让
    这道带子不会咬自己的列名：``updated_at`` 不是 ``UPDATE``，``set_config`` 不是 ``SET``。
    """
    text = statement.strip()
    if not _ALLOWED_PREFIX.match(text):
        raise Refuse(f"只读闸门：语句不以白名单前缀开头 ⇒ {text[:160]!r}")
    hits = sorted({word for word in _WRITE_KEYWORDS
                   if re.search(r"\b" + word + r"\b", text, re.I)})
    if hits:
        raise Refuse("只读闸门：语句里出现写关键字 " + ",".join(hits) + f" ⇒ {text[:160]!r}")


def checked_identifier(name: str, what: str) -> str:
    if not _IDENT.match(name or ""):
        raise Refuse(f"{what} 必须是裸标识符，拿到 {name!r}")
    return name


def assert_creatable(name: str, existing) -> None:
    checked_identifier(name, "新建库名")
    if name != DRILL_DB:
        raise Refuse(f"本件只准建 {DRILL_DB}，拿到 {name!r}")
    if name in set(existing):
        raise Refuse("库 " + name + " 已存在（现取清单：" + ", ".join(sorted(existing))
                     + "）；重跑不许产生第二枚，要么先 cleanup，要么明写 --replace-drill-db")


def assert_droppable(name: str) -> None:
    checked_identifier(name, "待删库名")
    if name != DRILL_DB:
        raise Refuse(f"只准删 {DRILL_DB}，拒绝删 {name!r}")


def assert_outside_worktree(path: Path) -> Path:
    resolved = Path(os.path.abspath(str(path)))
    for candidate in [resolved, *resolved.parents]:
        if (candidate / ".git").exists():
            raise Refuse(f"产物不许落进 git 工作树：{candidate} 带着 .git（换 --artifact-dir）")
    return resolved

def _run(argv: list, *, input_text: str | None = None, timeout: int = 900):
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", input=input_text, timeout=timeout)


def docker_exec(container: str, argv: list, *, stdin: str | None = None, timeout: int = 900):
    prefix = ["docker", "exec", "-i"] if stdin is not None else ["docker", "exec"]
    result = _run([*prefix, container, *argv], input_text=stdin, timeout=timeout)
    if result.returncode != 0:
        err = (result.stderr or "").strip()
        out = (result.stdout or "").strip()
        raise Refuse(f"docker exec {argv[0]} 在 {container} 上失败 rc={result.returncode}"
                     f"\n-- stderr --\n{err[-1500:] or '（空）'}"
                     f"\n-- stdout 尾 --\n{out[-300:] or '（空）'}")
    return result


def docker_cp_from(container: str, remote: str, local: Path) -> Path:
    note_statement(MAINT_DB, f"docker cp {container}:{remote} -> {local}", kind="docker_cp")
    result = _run(["docker", "cp", f"{container}:{remote}", str(local)], timeout=900)
    if result.returncode != 0:
        raise Refuse("docker cp 取出失败：" + ((result.stderr or "") + (result.stdout or ""))[-300:])
    return local


def docker_cp_to(container: str, local: Path, remote: str) -> None:
    note_statement(MAINT_DB, f"docker cp {local} -> {container}:{remote}", kind="docker_cp")
    result = _run(["docker", "cp", str(local), f"{container}:{remote}"], timeout=900)
    if result.returncode != 0:
        raise Refuse("docker cp 放入失败：" + ((result.stderr or "") + (result.stdout or ""))[-300:])


def psql_argv(database: str) -> list:
    return ["psql", "-U", PG_USER, "-d", database, "-X", "-q", "-t", "--csv",
            "-v", "ON_ERROR_STOP=1", "-P", f"null={NULL_MARK}", "-f", "-"]


def split_results(stdout: str, expected: int) -> list:
    """把一整个 psql 会话的输出按边界行切成 ``expected`` 段结果。"""
    records = [row for row in csv.reader(io.StringIO((stdout or "").replace("\r\n", "\n"))) if row]
    sets = [[]]
    for record in records:
        if record == [BOUNDARY]:
            sets.append([])
        else:
            sets[-1].append([None if cell == NULL_MARK else cell for cell in record])
    if len(sets) != expected + 1:
        raise Refuse(f"psql 输出切分不合：期望 {expected} 段，实得 {len(sets) - 1}")
    return sets[:-1]


def run_psql(container: str, database: str, statements: list, *, readonly: bool = True,
             transaction: bool = True, timeout: int = 900) -> list:
    """一枚 psql 会话里跑完这批语句，逐条交回结果集。"""
    if not statements:
        raise Refuse("run_psql 拿到空语句清单")
    if database == SOURCE_DB and not readonly:
        raise Refuse(f"生产库 {SOURCE_DB} 上不许发非只读批次：{statements[0][:80]!r}")
    if readonly and not transaction:
        raise Refuse("SET LOCAL 只在事务里有效：readonly 必须配 transaction")
    if readonly:
        for statement in statements:
            guard_statement(statement)
    lines = []
    if transaction:
        lines.append("BEGIN;")
    if readonly:
        lines.append(READ_ONLY_PIN + ";")
    for statement in statements:
        note_statement(database, statement)
        lines.append(statement.rstrip(";") + ";")
        lines.append(f"SELECT '{BOUNDARY}';")
    if transaction:
        lines.append("COMMIT;")
    result = docker_exec(container, psql_argv(database), stdin="\n".join(lines), timeout=timeout)
    return split_results(result.stdout, len(statements))


def scalar(container: str, database: str, statement: str):
    rows = run_psql(container, database, [statement])[0]
    return rows[0][0] if rows and rows[0] else None


def sql_count(table: str) -> str:
    if table not in COUNTED_TABLES:
        raise Refuse(f"本件只点名这几枚表来数行，拿到 {table!r}")
    return COUNT_SQL_TEMPLATE.format(table)


def zero_vector_sql(dimension: int) -> str:
    if not isinstance(dimension, int) or dimension < 1:
        raise Refuse(f"零向量字面量要一个正整数维度，拿到 {dimension!r}")
    return ("SELECT count(*) FROM chunk_vectors WHERE embedding = "
            "('[' || array_to_string(array_fill(0.0::double precision, ARRAY["
            + "%d" % dimension + "]), ',') || ']')::vector")


def max_dimension(dims: str):
    """``'768..768'`` -> ``768``；``'EMPTY'`` -> None；读不出整数就拒。"""
    if not dims or dims == "EMPTY":
        return None
    high = dims.split("..")[-1].strip()
    if not high.isdigit():
        raise Refuse(f"维度读数读不出整数：{dims!r}")
    return int(high)


FIRST_READS = (
    ("chunk_vectors_rows", lambda: sql_count("chunk_vectors")),
    ("embedding_count", lambda: COUNT_COLUMN_SQL_TEMPLATE.format("embedding", "chunk_vectors")),
    ("embedding_column_type", lambda: EMBEDDING_TYPE_SQL),
    ("embedding_dims", lambda: EMBEDDING_DIMS_SQL),
    ("vector_scope_rows", lambda: sql_count("vector_scope")),
    ("vector_scope_profile", lambda: VECTOR_SCOPE_PROFILE_SQL),
    ("documents_rows", lambda: sql_count("documents")),
    ("chunks_rows", lambda: sql_count("chunks")),
    ("schema_migrations", lambda: MIGRATIONS_SQL),
    ("vector_content_md5", lambda: CONTENT_MD5_SQL),
    ("chunk_vector_indexes", lambda: INDEXES_SQL),
)
GUARD_READS = (
    #: R587：库级 setting 的取数不再走这里（它有自己的那一族），这里只留集群级的角色清单。
    ("cluster_roles", lambda: ROLES_SQL),
)


def collect_fingerprint(container: str, database: str) -> dict:
    """判据里的每个数都从库上现取，没有一个来自件里的常量。"""
    statements = [builder() for _, builder in FIRST_READS]
    sets = run_psql(container, database, statements, timeout=900)
    found = {}
    for (key, _), rows in zip(FIRST_READS, sets):
        found[key] = rows[0][0] if rows and rows[0] else None
    dimension = max_dimension(found["embedding_dims"])
    found["zero_vector_rows"] = ("0" if dimension is None
                                 else scalar(container, database, zero_vector_sql(dimension)))
    sets = run_psql(container, database, [builder() for _, builder in GUARD_READS], timeout=600)
    for (key, _), rows in zip(GUARD_READS, sets):
        found[key] = rows[0][0] if rows and rows[0] else None
    readings = collect_globals(container, database)
    found["globals_profile"] = readings["profile"]
    found["globals_session"] = readings["session_profile"]
    found["globals_deferred"] = readings["deferred_profile"]
    #: 结构化那本账也一起带走：对账门要按枚点名，拿上面两枚字符串反解就是自找口径漂移。
    found["globals_session_map"] = readings["session"]
    found["globals_rows"] = readings["rows"]
    return found


def compare_fingerprints(source: dict, restored: dict, *, skip_vector_check: bool = False) -> dict:
    """只比点名的那几项；缺项即红，沉默不是通过。"""
    items = list(RECON_ITEMS)
    if skip_vector_check:
        items = [item for item in items if item not in VECTOR_CHECK_ITEMS]
        raise Mismatch(
            "对账缺项：向量列校验一族（" + " ".join(VECTOR_CHECK_ITEMS) + "）被摘掉，剩下的读数"
            "不足以判「恢复回来的还是不是那库向量」。摘掉校验的演练不许报绿：本次比对口径 "
            + str(len(items)) + " 项 < 要求 " + str(len(RECON_ITEMS)) + " 项")
    absent = sorted({item for item in items if item not in source or item not in restored})
    if absent:
        raise Mismatch("对账缺项：" + ", ".join(absent))
    differences = []
    for item in items:
        if str(source.get(item)) != str(restored.get(item)):
            differences.append(f"{item}: 生产={source.get(item)} 恢复={restored.get(item)}")
    #: 判据③：库级 setting 逐枚等才算过。上面那一圈比的是整串，两侧都 MISSING 会"相等"——那正是
    #: 本单要拆的假绿，所以这里再补一道按枚点名的门：读不到、两侧都缺、缺一枚，一律红。
    differences += gate_required_globals(source, restored)
    extras = {}
    for item in EXTRA_ITEMS:
        extras[item] = {"source": source.get(item), "restored": restored.get(item),
                        "equal": str(source.get(item)) == str(restored.get(item))}
    return {"compared": items, "differences": differences, "extras": extras}


def compare_before_after(before: dict, after: dict) -> list:
    keys = list(RECON_ITEMS) + list(EXTRA_ITEMS)
    return [f"{key}: 演练前={before.get(key)} 演练后={after.get(key)}" for key in keys
            if str(before.get(key)) != str(after.get(key))]

def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if value is True:
        return "TRUE"
    if value is False:
        return "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    text = str(value)
    if "\x00" in text:
        raise Refuse("NUL 进不了 PostgreSQL 文本列")
    return "'" + text.replace("'", "''") + "'"


def render_sql(sql: str, params: tuple) -> str:
    """把 psycopg 式占位符就地填成字面量，让在册读腿那句 SQL 能走 psql 出门。"""
    parts = sql.split("%s")
    if len(parts) - 1 != len(params):
        raise Refuse(f"占位符 {len(parts) - 1} 枚与参数 {len(params)} 枚不等：{sql[:160]!r}")
    out = parts[0]
    for value, tail in zip(params, parts[1:]):
        out += sql_literal(value) + tail
    return out


class StatementSink:
    """``pg_store.search_vectors`` 以为自己正在说话的那枚 connection。

    它不执行任何东西，只留下生产读腿本来会发出去的每一句 SQL 与本来会绑上的每一个参数。
    执行由 :func:`run_psql` 接手——因为宿主对容器那枚 5432 没有路（件头写明）。
    """

    def __init__(self) -> None:
        self.statements: list = []

    def execute(self, sql, params=()):
        self.statements.append(render_sql(sql, tuple(params or ())))
        return self

    def fetchall(self):
        return []

    def fetchone(self):
        return None


def leg_statements(distance_function: str, query_vector, k: int) -> list:
    """SQL 由在册读腿自己拼：本件不抄算符、不抄列清单、不抄候选宽度。"""
    from app.rag import pg_store

    sink = StatementSink()
    pg_store.search_vectors(connection=sink, vector_table=pg_store.DEFAULT_VECTOR_TABLE,
                            distance_function=distance_function, query_vector=query_vector,
                            k=k, where=None)
    if len(sink.statements) < 2:
        raise Refuse(f"读腿只拼出 {len(sink.statements)} 句，不足「先钉宽度再排名」两句的形状")
    if "set_config" not in sink.statements[0]:
        raise Refuse("读腿第一句不是候选宽度那枚 set_config：" + sink.statements[0][:120])
    return sink.statements


def parse_vector(text: str) -> list:
    body = (text or "").strip().strip("[]")
    if not body:
        raise Refuse("题向量读回来是空的，这轮对账作废")
    try:
        return [float(part) for part in body.split(",")]
    except ValueError as exc:
        raise Refuse(f"题向量解析失败：{exc}") from exc


def sample_query_vectors(container: str, database: str, count: int) -> list:
    if count < 1:
        raise Refuse(f"题量至少 1 枚，拿到 {count}")
    rows = run_psql(container, database, [SAMPLE_VECTORS_SQL_TEMPLATE.format(int(count))])[0]
    if len(rows) != count:
        raise Refuse(f"题名要 {count} 枚，库里现取交回 {len(rows)} 枚")
    return [(row[0], parse_vector(row[1])) for row in rows]


def read_scope_field(container: str, database: str, field: str) -> str:
    from app.rag import pg_store

    if field not in ("embedding_model", "dimension", "distance_function"):
        raise Refuse(f"scope 探针只认这三枚字段，拿到 {field!r}")
    statement = render_sql(pg_store._READ_SCOPE_SQL, (pg_store.VECTOR_SCHEMA_VERSION,))
    rows = run_psql(container, database, [statement])[0]
    if not rows or not rows[0]:
        raise Refuse(f"{database} 的 vector_scope 里没有 schema_version="
                     + str(pg_store.VECTOR_SCHEMA_VERSION) + " 那一行，读腿无从取算符")
    return rows[0][("embedding_model", "dimension", "distance_function").index(field)]


def hnsw_width_bounds(container: str, database: str) -> dict:
    """Ask the server what candidate widths its GUC actually accepts.

    The GUC only exists in a session that has loaded the vector library, so the probe goes
    first -- the same order :mod:`scripts.r59_recall_compare` learned the hard way. No bound
    in this file is a copy of a number: 0.8.6 answers ``1/1000/40``, and a deployment that
    ever moves that bound moves the drill's arithmetic with it.
    """
    rows = run_psql(container, database, [ENSURE_VECTOR_LIB_SQL, WIDTH_BOUNDS_SQL])
    hits = rows[1][0][0].split("/")
    if len(hits) != 3:
        raise Refuse(f"hnsw.ef_search 的界读不出来：{hits!r}")
    low, high, boot = hits
    try:
        return {"min": int(low), "max": int(high), "factory": int(boot)}
    except ValueError:
        raise Refuse(f"hnsw.ef_search 的界不是整数：{hits!r}") from None


def recall(container: str, *, source: str, drill: str, queries: int, top_k: int,
           exact_cross_check: bool = True) -> dict:
    from app.rag import pg_store

    distance_function = read_scope_field(container, source, "distance_function")
    pairs = sample_query_vectors(container, source, queries)
    true_source = pg_store.configured_hnsw_ef_search()
    bounds = hnsw_width_bounds(container, source)
    passes = [{"label": "production-width", "width": None}]
    if exact_cross_check:
        rows = int(scalar(container, source, sql_count("chunk_vectors")) or 0)
        cap = max(bounds["min"], min(rows, bounds["max"]))
        passes.append({"label": ("exhaustive" if rows <= bounds["max"]
                                 else f"near-exhaustive-guc-cap-{bounds['max']}"),
                       "width": cap, "table_rows": rows})
    results = [_recall_pass(container, distance_function=distance_function, pairs=pairs,
                             top_k=top_k, width=one["width"], label=one["label"],
                             source=source, drill=drill) for one in passes]
    return {"distance_function": distance_function, "true_source_ef_search": true_source,
            "hnsw_ef_search_bounds": bounds, "queries": len(pairs),
            "query_ids": [vector_id for vector_id, _ in pairs],
            "passes": results}


def _recall_pass(container: str, *, distance_function: str, pairs: list, top_k: int,
                 width, label: str, source: str, drill: str) -> dict:
    from app.rag import pg_store

    captured = []
    previous = os.environ.pop(pg_store.ENV_HNSW_EF_SEARCH, None)
    if width is not None:
        os.environ[pg_store.ENV_HNSW_EF_SEARCH] = str(int(width))
    try:
        for vector_id, vector in pairs:
            captured.append((vector_id, leg_statements(distance_function, vector, top_k)))
    finally:
        if previous is not None:
            os.environ[pg_store.ENV_HNSW_EF_SEARCH] = previous
    rows_by_db = {}
    for database in (source, drill):
        statements = []
        for _, legs in captured:
            statements.extend(legs)
            statements.append(WIDTH_PROBE_SQL)
        rows_by_db[database] = run_psql(container, database, statements, timeout=1800)
    per_query = []
    only_in_source = only_in_drill = max_shift = 0
    max_top1_delta = 0.0
    widths_seen = set()
    for position, (vector_id, legs) in enumerate(captured):
        stride = len(legs) + 1
        ranks = {}
        top1_distance = {}
        for database in (source, drill):
            offset = position * stride
            body = rows_by_db[database][offset + len(legs) - 1]
            widths_seen.add(rows_by_db[database][offset + len(legs)][0][0])
            ranks[database] = [row[0] for row in body]
            top1_distance[database] = float(body[0][-1]) if body else None
        left, right = ranks[source], ranks[drill]
        extra_left = [item for item in left if item not in right]
        extra_right = [item for item in right if item not in left]
        shift = max([abs(left.index(item) - right.index(item)) for item in left
                     if item in right] or [0])
        delta = (abs(top1_distance[source] - top1_distance[drill])
                 if top1_distance[source] is not None and top1_distance[drill] is not None
                 else 0.0)
        only_in_source += len(extra_left)
        only_in_drill += len(extra_right)
        max_shift = max(max_shift, shift)
        max_top1_delta = max(max_top1_delta, delta)
        per_query.append({"query_vector_id": vector_id, "source_top1": left[0] if left else None,
                          "drill_top1": right[0] if right else None,
                          "only_in_source": extra_left, "only_in_drill": extra_right,
                          "rank_shift": shift, "top1_distance_delta": delta})
    report = {"label": label,
              "requested_ef_search": (width if width is not None else
                                      pg_store.configured_hnsw_ef_search()),
              "ef_search_seen_in_session": sorted(widths_seen), "top_k": top_k,
              "queries": len(captured),
              "only_in_source": only_in_source, "only_in_drill": only_in_drill,
              "max_rank_shift": max_shift, "max_top1_distance_delta": max_top1_delta,
              "per_query": per_query}
    if widths_seen != {str(report["requested_ef_search"])}:
        raise Refuse(f"[{label}] 会话里现读的候选宽度是 {sorted(widths_seen)}，与本件请求的 "
                     f"{report['requested_ef_search']} 不等：钉下去没生效，这轮读数作废")
    if only_in_source or only_in_drill:
        raise RecallRed(f"[{label}] 恢复库与生产库的 top-{top_k} 集合不等："
                        f"只在生产={only_in_source}、只在恢复={only_in_drill}"
                        f"（名次最大位移 {max_shift}）")
    return report

def container_sha256(container: str, remote: str) -> str:
    return docker_exec(container, ["sha256sum", remote]).stdout.split()[0]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def list_databases(container: str) -> list:
    rows = run_psql(container, MAINT_DB, [LIST_DATABASES_SQL])[0]
    return sorted(row[0] for row in rows)


def container_preflight(container: str, source: str) -> dict:
    names = list_databases(container)
    if source not in names:
        raise Refuse("库里没有 " + source + "（现取清单：" + ", ".join(names)
                     + "）——本单不发任何对账结论")
    running = _run(["docker", "inspect", "-f", "{{.State.Running}}", container])
    image = _run(["docker", "inspect", "-f", "{{.Config.Image}}", container])
    if running.returncode != 0 or running.stdout.strip() != "true":
        raise Refuse(f"容器 {container} 不在架（running={running.stdout.strip()!r}）")
    extension = scalar(container, source,
                       "SELECT coalesce(extversion, 'MISSING') FROM pg_extension "
                       "WHERE extname = 'vector'")
    if extension in (None, "MISSING"):
        raise Refuse(f"{source} 没装 pgvector 扩展，恢复演练无从谈起")
    return {"container": container, "image": image.stdout.strip(),
            "databases_before": sorted(names), "pgvector_extension": extension,
            "system_identity": scalar(container, source, SESSION_IDENTITY_SQL),
            "source_db": source, "drill_db_exists": DRILL_DB in names}


def pg_restore_list(container: str, remote: str) -> list:
    note_statement(MAINT_DB, f"pg_restore --list {remote}", kind="pg_restore")
    out = docker_exec(container, ["pg_restore", "--list", remote], timeout=900)
    return [line for line in (out.stdout or "").splitlines() if line.strip()]


def landing_gaps(entries: list, required) -> set:
    from scripts.backup_database import missing_landing_tables

    return missing_landing_tables(entries, required)


def toc_danger_lines(entries: list) -> list:
    """归档目录里若出现指向别处的集群级 ALTER，一律拒收。

    ``pg_dump`` 按构造不带 ``ALTER DATABASE ... SET``（那是 ``pg_dumpall`` 的活，本单实测目录
    里零命中），但恢复这一步的权限太大，不该靠"按理说不会"过日子：先看目录，命中而名字不是
    本件那枚恢复库，当场 REFUSE。
    """
    danger = []
    for line in entries:
        if re.search(r"\bALTER\s+(DATABASE|ROLE)\b", line, re.I) and DRILL_DB not in line:
            danger.append(line)
    return danger


def backup(container: str, *, source: str, artifact_dir: Path) -> dict:
    stamp = utc_stamp()
    scratch_dir = f"{SCRATCH_ROOT}-{stamp}"
    remote = f"{scratch_dir}/eb_r575_drill-{stamp}.dump"
    docker_exec(container, ["mkdir", "-p", scratch_dir])
    note_statement(source, f"pg_dump --format=custom --file={remote} {source}", kind="pg_dump")
    docker_exec(container, ["pg_dump", "-U", PG_USER, "--format=custom", "--file", remote,
                            source], timeout=1800)
    remote_sha = container_sha256(container, remote)
    remote_bytes = int(docker_exec(container, ["stat", "-c", "%s", remote]).stdout.split()[0])
    artifact_dir.mkdir(parents=True, exist_ok=True)
    local = artifact_dir / f"eb_r575_drill-{stamp}.dump"
    docker_cp_from(container, remote, local)
    local_sha = sha256_file(local)
    local_bytes = local.stat().st_size
    if local_sha != remote_sha or local_bytes != remote_bytes:
        raise Refuse("容器与仓外的 dump 不是同一枚文件：bytes 容器=" + str(remote_bytes)
                     + " 仓外=" + str(local_bytes) + "；sha 容器=" + remote_sha[:12]
                     + " 仓外=" + local_sha[:12])
    if local_bytes == 0:
        raise Refuse("pg_dump 交回 0 字节的「备份」")
    entries = pg_restore_list(container, remote)
    absent = landing_gaps(entries, VECTOR_LANDING_TABLES)
    if absent:
        raise Refuse(f"归档目录缺落点（定义或数据其一）：{', '.join(sorted(absent))}")
    #: 判据①：备份工序连库级/角色级 setting 一起取，落成与这枚 dump 同目录同前缀的成对产物。
    #: 源库里那几枚必读项读不到就当场 REFUSE——不给「备份成功、globals 空着」留后路。
    readings = collect_globals(container, source)
    undeclared = [name for name in required_global_settings()
                  if readings["session"].get(name) in (None, "", "MISSING")]
    if undeclared:
        raise Refuse("源库 " + source + " 上这几枚 setting 本来就取不到：" + ", ".join(undeclared)
                     + "；没有源值就配不出可信的施加件，本件不许交一份缺 globals 的备份")
    pair = write_globals_artifacts(artifact_dir, readings, archive=local, stamp=stamp)
    manifest = {"path": str(local), "sha256": local_sha, "bytes": local_bytes,
                "container_scratch": remote, "created_utc": stamp, "entries": len(entries),
                "landing_tables": list(VECTOR_LANDING_TABLES), "globals": pair}
    (artifact_dir / "r575-archive-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def drop_drill(container: str, drill: str, why: str) -> None:
    assert_droppable(drill)
    note_statement(MAINT_DB, f'DROP DATABASE "{drill}"（{why}）', kind="maintenance")
    run_psql(container, MAINT_DB, [f'DROP DATABASE "{drill}"'], readonly=False,
             transaction=False)


def restore(container: str, *, archive: Path, drill: str, expect_sha256: str | None = None,
            replace: bool = False) -> dict:
    archive = Path(archive)
    if not archive.is_file() or archive.stat().st_size == 0:
        raise Refuse(f"归档文件不存在或 0 字节：{archive}")
    actual = sha256_file(archive)
    if expect_sha256 and actual != expect_sha256:
        raise Refuse("归档 sha 与备份时记下的不等：期望 " + expect_sha256[:12] + "，实得 "
                     + actual[:12] + f"（{archive.name}，{archive.stat().st_size} 字节）"
                     "——这份件不是那枚备份")
    stamp = utc_stamp()
    remote_dir = f"{SCRATCH_ROOT}-{stamp}"
    remote = f"{remote_dir}/{archive.name}"
    docker_exec(container, ["mkdir", "-p", remote_dir])
    docker_cp_to(container, archive, remote)
    try:
        entries = pg_restore_list(container, remote)
        if not entries:
            raise Refuse(f"pg_restore --list 在 {remote} 上交回空目录：这不是可读的归档")
        absent = landing_gaps(entries, VECTOR_LANDING_TABLES)
        if absent:
            raise Refuse(f"归档目录缺落点（定义或数据其一）：{', '.join(sorted(absent))}")
        dangerous = toc_danger_lines(entries)
        if dangerous:
            raise Refuse("归档里带着指向别处的集群级 ALTER，拒收：\n  "
                         + "\n  ".join(dangerous[:5]))
        #: 判据①的门：成对的 globals 产物必须先读通再谈建库。这一步零枚 docker 调用，所以在册
        #: 那枚「归档 sha 不对就什么都不发」没被挪动；而建一枚没有 globals 的库同样算违规。
        payload = read_globals_artifact(archive)
        existing = list_databases(container)
        if drill in existing:
            # 判据⑤：重跑不许长出第二枚同名库。默认就此打住；只有明写 --replace-drill-db
            # 才准删——而且删的必须还是那一枚，assert_droppable 在后头等着。
            if not replace:
                raise Refuse("库 " + drill + " 已在（现取清单：" + ", ".join(existing)
                             + "）；重跑不许产生第二枚，要么先 cleanup，要么明写 --replace-drill-db")
            drop_drill(container, drill, "--replace-drill-db：只准删这一枚同名库")
        assert_creatable(drill, list_databases(container))
        note_statement(MAINT_DB, f'CREATE DATABASE "{drill}" TEMPLATE template0',
                       kind="maintenance")
        run_psql(container, MAINT_DB, [f'CREATE DATABASE "{drill}" TEMPLATE template0'],
                 readonly=False, transaction=False)
        try:
            note_statement(drill, f"pg_restore --dbname {drill} --no-owner --exit-on-error "
                                  f"{remote}", kind="pg_restore")
            docker_exec(container, ["pg_restore", "-U", PG_USER, "--dbname", drill,
                                    "--no-owner", "--exit-on-error", remote], timeout=3600)
            #: 判据②：施加与现读现证排在 ANALYZE 之前——恢复工序跑的每一枚校验都得跑在「这库已经
            #: 和生产声明同一套向量档」这个前提上，否则量的就是另一道题。
            applied = apply_globals(container, drill, payload)
            problems = verify_globals(container, drill, payload)
            if problems:
                raise Mismatch("globals 施加之后恢复库仍与备份记录不等：\n  "
                               + "\n  ".join(problems))
            run_psql(container, drill, ["ANALYZE chunk_vectors", "ANALYZE chunks"],
                     readonly=False, transaction=True)
        except (Refuse, Mismatch):
            if drill in list_databases(container):
                drop_drill(container, drill, "恢复失败即清理，不留半截库")
            raise
    finally:
        docker_exec(container, ["rm", "-rf", remote_dir])
    return {"archive": str(archive), "sha256": actual, "bytes": archive.stat().st_size,
            "drill_db": drill, "entries": len(entries), "remote_scratch": remote,
            "globals": applied}


def cleanup(container: str, *, drill: str) -> dict:
    before = list_databases(container)
    if drill in before:
        drop_drill(container, drill, "判据⑤：演练收尾只删这一枚")
    after = list_databases(container)
    docker_exec(container, ["sh", "-c", "rm -rf " + SCRATCH_ROOT + "-*"], timeout=300)
    return {"databases_before_cleanup": before, "databases_after_cleanup": after,
            "drill_dropped": drill in before and drill not in after}


def check_residue(before, after, *, drill_db: str, keep: bool) -> dict:
    """判据⑤的账：别人家的库一枚不许多、一枚不许少；恢复库自己的去留只按 ``--keep`` 说了算。

    ``--replace-drill-db`` 的语义就是「上一轮那枚同名库是我自己留下的，这一轮删掉重来」，
    所以恢复库本身不许算进「少了」那一栏——否则不带 ``--keep`` 的那一轮必然自证失败
    （真机 2026-10-03 实测：修复前这一支返回 rc=5，报「少了 eb_r575_drill」，而它删的正是
    自己该删的那枚）。反过来，只准它一枚多出来，且必须具名上报。
    """
    expected = set(before)
    got = set(after)
    others_before = expected - {drill_db}
    others_after = got - {drill_db}
    extra = sorted(others_after - others_before)
    missing = sorted(others_before - others_after)
    problems = []
    if extra:
        problems.append("多出 " + ", ".join(extra))
    if missing:
        problems.append("少了 " + ", ".join(missing))
    if keep:
        if drill_db not in got:
            problems.append("--keep 要留着 " + drill_db + "，演练后它却不在盘上")
    elif drill_db in got:
        problems.append(drill_db + " 没删干净，还在盘上")
    report = {"databases_before": sorted(expected), "databases_after": sorted(got),
              "unexpected_extra": extra, "missing": missing,
              "kept_by_request": sorted({drill_db} & got) if keep else [],
              "drill_present_before": drill_db in expected,
              "drill_present_after": drill_db in got}
    if problems:
        exc = Residue("演练后的库名集合没回到演练前那一集：" + "；".join(problems)
                      + "（演练前：" + ", ".join(sorted(expected))
                      + "；演练后：" + ", ".join(sorted(got)) + "）")
        exc.residue = report
        raise exc
    return report


def write_artifacts(artifact_dir: Path, reading: dict) -> dict:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    reading["written_utc"] = utc_stamp()
    stamp = reading.get("run_stamp") or utc_stamp()
    reading.setdefault("run_stamp", stamp)
    json_path = artifact_dir / f"r575-drill-reading-{stamp}.json"
    json_path.write_text(json.dumps(reading, ensure_ascii=False, indent=2,
                                   default=str), encoding="utf-8")
    production = ledger_for(reading.get("source_db") or SOURCE_DB)
    txt_path = artifact_dir / f"r575-production-statements-{stamp}.txt"
    body = ["# R575 对生产库发出的语句逐条清单（本件自证：全部只读）",
            "# 每条都在 BEGIN; SET LOCAL transaction_read_only = on; 的事务里，"
            "且都先过 guard_statement。",
            f"# 合计 {len(production)} 条。", ""]
    body += [f"{index + 1:04d}. {statement}" for index, statement in enumerate(production)]
    txt_path.write_text("\n".join(body) + "\n", encoding="utf-8")
    latest = artifact_dir / "r575-latest.json"
    latest.write_text(json.dumps({"run_stamp": stamp, "reading": str(json_path),
                                  "statements": str(txt_path)}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return {"json": str(json_path), "statements": str(txt_path), "latest_pointer": str(latest),
            "production_statement_count": len(production),
            "ledger_kinds": {kind: sum(1 for item in LEDGER if item["kind"] == kind)
                             for kind in sorted({item["kind"] for item in LEDGER})}}

def run_full(args) -> int:
    """Every full run leaves a凭据 behind, including the ones that end in a red.

    The stamp goes on the file names so a re-run cannot destroy the evidence of the run that
    came before it -- the dump itself is already stamped, and the manifest is overwritten by
    the run that made it, which is the one the stamped reading names.
    """
    artifact_dir = assert_outside_worktree(Path(args.artifact_dir))
    reading = {"run_stamp": utc_stamp(), "source_db": args.source_db,
               "drill_db": args.drill_db, "steps": []}
    try:
        return _full_steps(args, artifact_dir, reading)
    except (Refuse, Mismatch, RecallRed, Residue) as exc:
        reading["status"] = type(exc).__name__
        reading["failure"] = str(exc)
        captured = getattr(exc, "residue", None)
        if captured:
            reading["residue"] = captured
        reading["artifacts"] = write_artifacts(artifact_dir, reading)
        raise


def _full_steps(args, artifact_dir: Path, reading: dict) -> int:
    container = args.container
    pre = container_preflight(container, args.source_db)
    if DRILL_DB in pre["databases_before"] and not args.replace_drill_db:
        raise Refuse("上一轮的 " + DRILL_DB + " 还在（现取清单："
                     + ", ".join(pre["databases_before"]) + "）；先跑 cleanup 或明写 --replace-drill-db")
    baseline = collect_fingerprint(container, args.source_db)
    pre["fingerprint_before"] = baseline
    reading["preflight"] = pre
    reading["steps"].append("preflight: OK")
    if args.skip_backup:
        if not args.archive:
            raise Refuse("--skip-backup 必须配 --archive <dump 路径>")
        archive = Path(args.archive)
        if not archive.is_file():
            raise Refuse(f"--archive 指的件不存在：{archive}")
        manifest = {"path": str(archive), "sha256": sha256_file(archive),
                    "bytes": archive.stat().st_size, "reused": True}
    else:
        manifest = backup(container, source=args.source_db, artifact_dir=artifact_dir)
        archive = Path(manifest["path"])
    reading["backup"] = {key: manifest.get(key) for key in
                         ("path", "sha256", "bytes", "entries", "landing_tables", "reused",
                          "globals")}
    reading["steps"].append(f"backup: OK bytes={manifest['bytes']} sha={manifest['sha256'][:12]}")
    reading["restore"] = restore(container, archive=archive, drill=args.drill_db,
                                 expect_sha256=manifest.get("sha256"),
                                 replace=args.replace_drill_db)
    reading["steps"].append("restore: OK")
    prod = collect_fingerprint(container, args.source_db)
    restored = collect_fingerprint(container, args.drill_db)
    reading["fingerprint_source"] = prod
    reading["fingerprint_drill"] = restored
    reading["reconcile"] = compare_fingerprints(prod, restored,
                                                skip_vector_check=args.skip_vector_check)
    if reading["reconcile"]["differences"]:
        raise Mismatch("恢复库对账不等：\n  "
                       + "\n  ".join(reading["reconcile"]["differences"]))
    reading["steps"].append(f"reconcile: OK {len(reading['reconcile']['compared'])} 项全等")
    reading["recall"] = recall(container, source=args.source_db, drill=args.drill_db,
                               queries=args.queries, top_k=args.top_k)
    worst = max(one["max_rank_shift"] for one in reading["recall"]["passes"])
    reading["steps"].append("recall: OK only_in_*=0 名次最大位移=" + str(worst)
                            + " ef_search 会话现读="
                            + str(reading["recall"]["passes"][0]["ef_search_seen_in_session"]))
    after = collect_fingerprint(container, args.source_db)
    reading["fingerprint_source_after"] = after
    drift = compare_before_after(baseline, after)
    if drift:
        raise Mismatch("生产库在演练期间被改动过（本单最不该出现的一行）：\n  " + "\n  ".join(drift))
    reading["steps"].append("postflight: 生产库前后逐枚同数 OK")
    if not args.keep:
        reading["cleanup"] = cleanup(container, drill=args.drill_db)
        reading["steps"].append("cleanup: OK")
    reading["databases_final"] = list_databases(container)
    reading["residue"] = check_residue(pre["databases_before"], reading["databases_final"],
                                       drill_db=args.drill_db, keep=args.keep)
    reading["status"] = "PASS"
    reading["artifacts"] = write_artifacts(artifact_dir, reading)
    report(reading)
    return EXIT_OK


def report(reading: dict) -> None:
    pre = reading["preflight"]
    print(f"preflight  : {pre['image']} identity={pre['system_identity']} "
          f"pgvector={pre['pgvector_extension']}")
    print(f"backup     : {reading['backup']['bytes']} bytes "
          f"sha={reading['backup']['sha256'][:12]} -> {reading['backup']['path']}")
    pair = reading["backup"].get("globals") or {}
    print(f"globals    : 施加 {pair.get('applied')} 枚 / 集群级只上报 {pair.get('deferred')} 枚；"
          f"json sha={str(pair.get('json_sha256'))[:12]} sql sha={str(pair.get('sql_sha256'))[:12]} "
          f"配对归档 sha={str(pair.get('archive_sha256'))[:12]}")
    print(f"reconcile  : {len(reading['reconcile']['compared'])} 项全等；"
          f"额外上报 {json.dumps(reading['reconcile']['extras'], ensure_ascii=False)}")
    for one in reading["recall"]["passes"]:
        print(f"recall[{one['label']}] 请求 ef_search={one['requested_ef_search']} "
              f"会话现读={one['ef_search_seen_in_session']} only_in_source={one['only_in_source']} "
              f"only_in_drill={one['only_in_drill']} max_rank_shift={one['max_rank_shift']} "
              f"max_top1_delta={one['max_top1_distance_delta']}")
    print(f"cleanup    : {json.dumps(reading.get('cleanup', {}), ensure_ascii=False)}")
    print(f"artifacts  : {json.dumps(reading['artifacts'], ensure_ascii=False)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R575 真库向量备份—恢复演练（可重跑）")
    parser.add_argument("step", nargs="?", default="full",
                        choices=("full", "preflight", "backup", "restore", "reconcile",
                                 "recall", "cleanup"))
    parser.add_argument("--container", default=CONTAINER_DEFAULT)
    parser.add_argument("--source-db", default=SOURCE_DB)
    parser.add_argument("--drill-db", default=DRILL_DB)
    parser.add_argument("--artifact-dir", default=ARTIFACT_DIR_DEFAULT)
    parser.add_argument("--archive", default=None)
    parser.add_argument("--expect-sha256", default=None)
    parser.add_argument("--skip-backup", action="store_true")
    parser.add_argument("--replace-drill-db", action="store_true")
    parser.add_argument("--skip-vector-check", action="store_true")
    parser.add_argument("--keep", action="store_true", help="演练后留着恢复库，供人现场看")
    parser.add_argument("--queries", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=10)
    return parser


def run_step(args) -> int:
    container = args.container
    if args.drill_db != DRILL_DB:
        raise Refuse(f"--drill-db 只能等于 {DRILL_DB}，拿到 {args.drill_db!r}")
    if args.step == "preflight":
        artifact_dir = assert_outside_worktree(Path(args.artifact_dir))
        pre = container_preflight(container, args.source_db)
        pre["fingerprint"] = collect_fingerprint(container, args.source_db)
        print(json.dumps(pre, ensure_ascii=False, indent=2))
        return EXIT_OK
    if args.step == "backup":
        artifact_dir = assert_outside_worktree(Path(args.artifact_dir))
        container_preflight(container, args.source_db)
        print(json.dumps(backup(container, source=args.source_db,
                               artifact_dir=artifact_dir), ensure_ascii=False, indent=2))
        return EXIT_OK
    if args.step == "restore":
        assert_outside_worktree(Path(args.artifact_dir))
        if not args.archive:
            raise Refuse("restore 需要 --archive <dump 路径>")
        print(json.dumps(restore(container, archive=Path(args.archive), drill=args.drill_db,
                                 expect_sha256=args.expect_sha256,
                                 replace=args.replace_drill_db), ensure_ascii=False, indent=2))
        return EXIT_OK
    if args.step == "reconcile":
        prod = collect_fingerprint(container, args.source_db)
        restored = collect_fingerprint(container, args.drill_db)
        result = compare_fingerprints(prod, restored, skip_vector_check=args.skip_vector_check)
        if result["differences"]:
            raise Mismatch("恢复库对账不等：\n  " + "\n  ".join(result["differences"]))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return EXIT_OK
    if args.step == "recall":
        print(json.dumps(recall(container, source=args.source_db, drill=args.drill_db,
                                queries=args.queries, top_k=args.top_k),
                         ensure_ascii=False, indent=2))
        return EXIT_OK
    print(json.dumps(cleanup(container, drill=args.drill_db), ensure_ascii=False, indent=2))
    return EXIT_OK


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"full": run_full, "preflight": run_step, "backup": run_step,
                "restore": run_step, "reconcile": run_step, "recall": run_step,
                "cleanup": run_step}
    try:
        return handlers[args.step](args)
    except Refuse as exc:
        print(f"REFUSED（rc={EXIT_REFUSED}）：{exc}", file=sys.stderr)
        return EXIT_REFUSED
    except Mismatch as exc:
        print(f"MISMATCH（rc={EXIT_MISMATCH}）：{exc}", file=sys.stderr)
        return EXIT_MISMATCH
    except RecallRed as exc:
        print(f"RECALL RED（rc={EXIT_RECALL}）：{exc}", file=sys.stderr)
        return EXIT_RECALL
    except Residue as exc:
        print(f"RESIDUE（rc={EXIT_RESIDUE}）：{exc}", file=sys.stderr)
        return EXIT_RESIDUE
    except subprocess.TimeoutExpired as exc:
        print(f"TIMEOUT（rc={EXIT_ERROR}）：{exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
