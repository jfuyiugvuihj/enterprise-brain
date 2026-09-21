#!/usr/bin/env python
"""R145：向量镜像「集合面」的只读对账 —— 零模型、零写入、不比距离。

`scripts/compare_vector_recall.py` 的第 4 条前置要 Ollama 在场（题向量必须由生产侧同一个
embedder 产出），所以它那一半在别的单子在跑真机实测时不能碰。本脚本只做**不需要 embed 的
那一半**：把 Chroma 的 id 集合与 PG `chunk_vectors` 的行集合摆在一起比形状、比归属，一条向量
都不算、一个 token 都不发。它是第⑦步的开场，不是第⑦步的结论。

四个问题，每条都指名到行（`--list-limit` 管名单长度，`--out` 里的 JSON 是全文）：

  Q1 两侧各自的集合：只在 Chroma / 只在 PG / 两边都有，三个数 + 三份名单。
     「总数相等」不算答案 —— 两边各 985 行但错位重合，是 Q1 要当场揭穿的那种事。
  Q2 `index_version_id IS NULL` 有多少、是哪些文档，按 R76 之后的新语义判读：刚写进镜像还
     没被任何发布收编 = 正常待回填，不许当故障；反过来，「镜像里这行的写入时间早于该文档最
     近一次发布、行却还是 NULL」才是需要人看的那一张脸（详见
     docs/handoff/2026-09-17-pgvector-adoption-plan.md 的 R76 三段）。
  Q3 `embedding_model` / `embedding_dimension` 的分组清单：只应有一代。出现第二代就是 R76
     那道拒发闸要当场拒掉的形状，本脚本把它具名报出来（不修、不清洗、不假装没看见）。
  Q4 孤儿：PG 有向量行而 `chunks` 没有对应 chunk、或反过来。外加「chunk_id 派生不出
     vector_id」那一类 —— 派生规则是 migrations/0010 的触发器在用的那条，文件名里带 `#`
     或 `|v` 就会派生错，所以它必须先被点名，不能让错派生冒充成孤儿。

跑法（业主真机；PG 取数按工单指定的容器内 psql，一条写都不发）：

    python scripts/audit_vector_mirror_sets.py --out /tmp/r145_mirror_sets.json

    # 本机宿主 PG（没有 docker 时的等价路线，同一份 SQL、同样 READ ONLY + ROLLBACK）：
    python scripts/audit_vector_mirror_sets.py --pg-transport psycopg --out r145.json

只读的三条独立保证（不是注释，是代码）：

  1. `_assert_read_only()` 在把 SQL 交出去之前逐条数语句，白名单只有 SELECT / WITH；
     出现任何 DML / DDL / 事务控制词 ⇒ 当场拒发，一个字节都不到服务端。
  2. 每个会话都以 `BEGIN; SET TRANSACTION READ ONLY;` 开头、以 `ROLLBACK;` 结尾。就算白名单
     漏了什么，服务端也会用 25006 把那一笔挡回去。
  3. Chroma 侧先整目录拷到临时副本再打开（`chromadb.PersistentClient` 对 sqlite 即使只读
     也会落 WAL/SHM），仓库里那份 `chroma_db/` 从头到尾只被读、只被哈希；报告里带
     `chroma_source.sha256_before/after` 两枚清单，跑完自己比。

退出码（沿用第⑦步那一份口径，别再造第二套）：
  0 = 四个问题都问得出且没有差异；1 = 问得出且有差异（正常结论，交人判读）；
  2 = 前置不满足（表没迁移 / 目录缺失 / collection 取不到），此时一个问题都不下结论 ——
      空集合永远不当成「一致」。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from dataclasses import dataclass
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 工单指定的取数路线原样：容器里的 psql，USER/DB 都取自容器环境变量。
DEFAULT_CONTAINER = "enterprise-brain-postgres-1"
PSQL_INNER = 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA -q -v ON_ERROR_STOP=1 -f -'


def docker_psql_command(container: str = DEFAULT_CONTAINER) -> list:
    """工单点名的那条命令：用户与库名都留在容器环境里，不进命令行、也不进报告。"""
    return ["docker", "exec", "-i", str(container), "sh", "-c", PSQL_INNER]


DOCKER_PSQL = docker_psql_command()

DEFAULT_VECTOR_TABLE = "chunk_vectors"
DEFAULT_CHUNKS_TABLE = "chunks"
DEFAULT_SCOPE_TABLE = "vector_scope"
DEFAULT_COLLECTION = "enterprise_docs"
DEFAULT_LIST_LIMIT = 20

#: psql 的非对齐模式分不出 NULL 与空串，所以每一列都用哨兵投影，读回来再换回 None。
NULL_SENTINEL = "<NULL>"
#: 字段分隔符用 0x1f（unit separator）：文件名里出现它的概率与出现 `|` 的概率不是一个量级，
#: 而且 Q4 里有一条专门把控制字符点名（见 q4_chunk_id_shapes），不靠"应该不会吧"。
FIELD_SEP = "\x1f"
ROW_PREFIX = "R" + FIELD_SEP

TX_BEGIN = ["BEGIN", "SET TRANSACTION READ ONLY"]
TX_END = ["ROLLBACK"]

#: 白名单之外的任何一个词都不许离开本机。\b 让 created_at / updated_at 这类列名自然放行。
_WRITE_WORDS = (
    "insert", "update", "delete", "merge", "upsert", "alter", "create", "drop", "truncate",
    "reindex", "vacuum", "analyze", "comment", "grant", "revoke", "copy", "call", "do",
    "prepare", "deallocate", "discards", "commit", "savepoint", "release", "lock", "refresh",
    "cluster", "vacuumfull", "setrole", "explain",
)
_WRITE_PATTERN = re.compile(r"\b(" + "|".join(_WRITE_WORDS) + r")\b", re.IGNORECASE)


# --------------------------------------------------------------------- SQL 构造件
_SAFE_TABLE = re.compile(r"[a-z_][a-z0-9_]*\Z")

#: app/rag/indexing.py 的 document_index_id() 拼法：f"{RESOURCE_TYPE_DOCUMENT}:{filename}"。
#: 本脚本不 import app/**（那会顺带把模型路径拖进来），所以这里自带一枚，并由
#: tests/test_r145_* 现读源码钉住它 —— 漂了就红，不许靠"应该还是 document:"。
INDEX_ID_PREFIX = "document:"


def safe_table(name: str) -> str:
    """表名来自命令行，所以它只能是一个裸标识符，不是一条语句的开头。"""
    value = str(name or "").strip().lower()
    if not _SAFE_TABLE.match(value):
        raise ValueError("不是合法的表名：" + repr(name))
    return value


def P(*columns: str) -> str:
    """把若干列投影成一行文本：`R` + 0x1f + 各列，NULL 用哨兵顶掉。

    两件事一次解决：psql 的 `-tA` 分不出 NULL 与空串；而 `|` 是合法的 PostgreSQL 标识符字符
    （文件名里真有 `a|b.pdf` 时它会字段错位）。分隔符换成 0x1f 之后，Q4 那条控制字符检查还能
    顺势把脏 id 点名，而不是让解析器悄悄吞掉。
    """
    parts = ", ".join("coalesce((%s)::text, '%s')" % (column, NULL_SENTINEL) for column in columns)
    return "'R' || chr(31) || concat_ws(chr(31), " + parts + ")"


@dataclass(frozen=True)
class Query:
    """一条只读查询。`name` 进 SQL 注释、进报告的 sql_transcript，也进离线假件的分支。"""

    name: str
    columns: tuple[str, ...]
    sql: str


def _strip_sql_comments(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        stripped = line.split("--", 1)[0]
        if stripped.strip():
            lines.append(stripped)
    return "\n".join(lines)


def _assert_read_only(sql: str) -> None:
    """白名单 + 关键字闸：不通过就一个字节都不许离开本机。

    逐条语句看首词（只许 SELECT / WITH），再过一遍写关键字表。`BEGIN` / `SET TRANSACTION
    READ ONLY` / `ROLLBACK` 是代码里的固定前缀后缀，不走这个函数 —— 报告的 sql_transcript
    把每个会话的完整脚本文本原样打出来，谁都能重数一遍，确认没有第四种事务控制、更没有 COMMIT。
    """
    for raw in sql.split(";"):
        statement = _strip_sql_comments(raw).strip()
        if not statement:
            continue
        lead = statement.split(None, 1)[0].lower()
        if lead not in ("select", "with"):
            raise AssertionError("R145 只发 SELECT/WITH，这条不是：" + statement[:80])
        hit = _WRITE_PATTERN.search(statement)
        if hit:
            raise AssertionError(
                "R145 拒绝发送含写关键字的语句（%s）：%s" % (hit.group(1), statement[:80])
            )


def build_queries(vector_table: str, chunks_table: str, scope_table: str) -> dict:
    """四个问题的全部 SQL 集中在这一处，是为了让 sql_transcript 可复核、假件可分支。"""
    vec = safe_table(vector_table)
    chk = safe_table(chunks_table)
    scp = safe_table(scope_table)
    #: 两个 id 空间不同：chunks.chunk_id = "<filename>|v<version>#<ordinal>"，而
    #: chunk_vectors.vector_id = "<filename>_<ordinal>"。对账不许自创第二把尺，这里逐字照抄
    #: migrations/0010_pgvector_chunks.sql 里 sync_chunk_embedding() 的那一条派生 —— 连它用
    #: NULLIF 把「取不到 ordinal」变成"匹配不上"（而不是匹配到 `a.pdf_`）的口径一起照抄。
    derived = (
        "split_part(chunk_id, '|v', 1) || '_' || NULLIF(split_part(chunk_id, '#', 2), '')"
    )
    #: 同一支触发器还有第二条规则：chunks.metadata 里真存着字符串型 vector_id 时（写侧
    #: app/rag/indexing.py 的 chunk 行就是这么落的），它以显式键为准，派生只是兜底。
    #: Q4 的键必须按同一优先级取，否则"文件名里带 # 或 |v"的文档会被报成假孤儿。
    #: 判存在用 jsonb_typeof(...) = 'string' 而不是触发器原文的 `metadata ? 'vector_id'`：
    #: 语义等价，而 `?` 在部分驱动里是占位符，不值得为省一次括号冒这个险。
    chunk_key = (
        "coalesce(CASE WHEN jsonb_typeof(metadata -> 'vector_id') = 'string'"
        " THEN metadata ->> 'vector_id' END, " + derived + ")"
    )
    #: POSIX 类而不是 \x 转义：文本列里本来就存不下 NUL（R130 那笔），别在这里假装能匹配它。
    control = "'[[:cntrl:]]'"

    queries: list[Query] = [
        Query(
            "preconditions",
            ("table_name", "column_name"),
            "SELECT " + P("table_name", "column_name") + "\n"
            "FROM information_schema.columns\n"
            "WHERE table_schema = current_schema()\n"
            "  AND table_name IN ('" + vec + "', '" + chk + "', 'index_versions', "
            "'index_registry', '" + scp + "')\n"
            "ORDER BY table_name, column_name",
        ),
        # Q1：PG 侧全量 id。集合在 Python 里比，"总数相等"永远不算答案。
        Query("q1_pg_vector_ids", ("vector_id",), "SELECT " + P("vector_id") + "\nFROM " + vec),
        # Q2：NULL 行按文档聚合，并带出该文档的发布事实，才能按 R76 语义分类。
        Query(
            "q2_null_rows",
            ("filename", "null_rows", "newest_vector_write", "bound_versions", "last_published_at"),
            "WITH nulls AS (\n"
            "  SELECT filename, count(*) AS null_rows, max(created_at) AS newest_vector_write\n"
            "  FROM " + vec + "\n"
            "  WHERE index_version_id IS NULL\n"
            "  GROUP BY filename\n"
            "), published AS (\n"
            "  SELECT c.resource_id AS filename,\n"
            "         count(DISTINCT c.index_version_id) AS bound_versions,\n"
            "         max(iv.published_at) AS last_published_at\n"
            "  FROM " + chk + " c\n"
            "  LEFT JOIN index_versions iv ON iv.index_version_id = c.index_version_id\n"
            "  GROUP BY c.resource_id\n"
            ")\n"
            "SELECT " + P("n.filename", "n.null_rows", "n.newest_vector_write",
                          "coalesce(p.bound_versions, 0)", "p.last_published_at") + "\n"
            "FROM nulls n\n"
            "LEFT JOIN published p ON p.filename = n.filename\n"
            "ORDER BY n.null_rows DESC, n.filename",
        ),
        # Q2 的另一半：镜像总量。它与"按文档聚合出来的 NULL 数"是两条独立算法，必须对得上。
        Query(
            "q2_mirror_totals",
            ("total_rows", "tagged_rows"),
            "SELECT " + P("count(*)", "count(index_version_id)") + "\nFROM " + vec,
        ),
        # Q2 附加：chunk_vectors.index_version_id 这一列在 0010 里没有外键，所以指错要自己查。
        Query(
            "q2_dangling_bindings",
            ("vector_id", "index_version_id", "reason"),
            "SELECT " + P("cv.vector_id", "cv.index_version_id",
                          "CASE WHEN iv.index_version_id IS NULL THEN 'no_such_index_version' "
                          "ELSE 'not_the_current_version' END") + "\n"
            "FROM " + vec + " cv\n"
            "LEFT JOIN index_versions iv ON iv.index_version_id = cv.index_version_id\n"
            "LEFT JOIN index_registry ir ON ir.index_id = '" + INDEX_ID_PREFIX
            + "' || cv.filename\n"
            "WHERE cv.index_version_id IS NOT NULL\n"
            "  AND (iv.index_version_id IS NULL\n"
            "       OR cv.index_version_id IS DISTINCT FROM ir.current_version_id)\n"
            "ORDER BY cv.vector_id",
        ),
        # Q3：镜像里到底有几代向量；declared 那一代来自 vector_scope。
        Query(
            "q3_pg_generations",
            ("embedding_model", "embedding_dimension", "rows", "first_write", "last_write"),
            "SELECT " + P("embedding_model", "embedding_dimension", "count(*)",
                          "min(created_at)", "max(created_at)") + "\n"
            "FROM " + vec + "\n"
            "GROUP BY embedding_model, embedding_dimension\n"
            "ORDER BY count(*) DESC, embedding_model, embedding_dimension",
        ),
        Query(
            "q3_declared_scope",
            ("schema_version", "embedding_model", "dimension", "distance_function"),
            "SELECT " + P("schema_version", "embedding_model", "dimension",
                          "distance_function") + "\n"
            "FROM " + scp + "\nORDER BY schema_version",
        ),
        Query(
            "q3_shape_lies",
            ("vector_id", "declared_dimension", "actual_dimension"),
            "SELECT " + P("vector_id", "embedding_dimension", "vector_dims(embedding)") + "\n"
            "FROM " + vec + "\n"
            "WHERE vector_dims(embedding) <> embedding_dimension\n"
            "ORDER BY vector_id",
        ),
        # Q4：孤儿两个方向 + 派生尺适用性两条。
        Query(
            "q4_vectors_without_chunks",
            ("vector_id", "filename", "chunk_index", "index_version_id", "last_write"),
            "SELECT " + P("cv.vector_id", "cv.filename", "cv.chunk_index",
                          "cv.index_version_id", "cv.updated_at") + "\n"
            "FROM " + vec + " cv\n"
            "WHERE NOT EXISTS (\n"
            "  SELECT 1 FROM " + chk + " c WHERE (" + chunk_key + ") = cv.vector_id\n"
            ")\nORDER BY cv.filename, cv.chunk_index",
        ),
        Query(
            "q4_chunks_without_vectors",
            ("vector_id", "chunk_rows", "bound_chunk_rows", "current_version_rows"),
            "WITH keys AS (\n"
            "  SELECT (" + chunk_key + ") AS vector_id,\n"
            "         count(*) AS chunk_rows,\n"
            "         count(*) FILTER (WHERE index_version_id IS NOT NULL) AS bound_chunk_rows,\n"
            "         count(*) FILTER (WHERE index_version_id IN (\n"
            "             SELECT current_version_id FROM index_registry"
             " WHERE current_version_id IS NOT NULL\n"
            "         )) AS current_version_rows\n"
            "  FROM " + chk + "\n"
            "  GROUP BY 1\n"
            ")\n"
            "SELECT " + P("k.vector_id", "k.chunk_rows", "k.bound_chunk_rows",
                          "k.current_version_rows") + "\n"
            "FROM keys k\n"
            "WHERE NOT EXISTS (SELECT 1 FROM " + vec + " cv WHERE cv.vector_id = k.vector_id)\n"
            "ORDER BY k.current_version_rows DESC, k.vector_id",
        ),
        Query(
            "q4_chunk_id_shapes",
            ("chunk_id", "resource_id", "index_version_id"),
            "SELECT " + P("chunk_id", "resource_id", "index_version_id") + "\n"
            "FROM " + chk + "\n"
            "WHERE chunk_id !~ '^[^#]+[|]v[0-9]+#[0-9]+$'\n"
            "ORDER BY chunk_id",
        ),
        Query(
            "q4_vector_id_shapes",
            ("vector_id", "filename", "chunk_index"),
            "SELECT " + P("vector_id", "filename", "chunk_index") + "\n"
            "FROM " + vec + "\n"
            "WHERE vector_id <> filename || '_' || chunk_index::text\n"
            "   OR vector_id ~ " + control + "\n"
            "ORDER BY vector_id",
        ),
        # 自证：审计前后各跑一次，两张表的行数必须一模一样。
        Query(
            "self_check_counts",
            ("table_name", "rows"),
            "SELECT " + P("'" + vec + "'", "count(*)") + " FROM " + vec + "\n"
            "UNION ALL\n"
            "SELECT " + P("'" + chk + "'", "count(*)") + " FROM " + chk,
        ),
    ]
    return {query.name: query for query in queries}


# ================================================================== 取数通道
class MirrorUnavailable(RuntimeError):
    """PG 侧问不出来时用的一族具名原因（表没迁移、连不上、查询被服务端拒）。"""


def parse_rows(query: Query, stdout: str) -> tuple[list, list]:
    """只认 `R` + 0x1f 开头的行。

    psql 就算带 `-q` 也可能被版本/环境塞进命令标签（BEGIN / SET / ROLLBACK），所以这里不是
    "顺手过滤一下噪声"，而是唯一的取数边界：不带行首标记的一律不进结果。列数对不上的行不猜，
    原样退回成 malformed —— 文件名里真藏了一个 0x1f 时，本函数要把这件事报出来而不是错位。
    """
    rows: list = []
    malformed: list = []
    for line in str(stdout or "").replace("\r\n", "\n").split("\n"):
        if not line.startswith(ROW_PREFIX):
            continue
        fields = line[len(ROW_PREFIX):].split(FIELD_SEP)
        if len(fields) != len(query.columns):
            malformed.append(line)
            continue
        rows.append(tuple(None if field == NULL_SENTINEL else field for field in fields))
    return rows, malformed


class DockerPsqlReader:
    """工单指定的那条路线：容器里的 psql，一个查询一个会话，会话只 ROLLBACK。

    每次调用发出去的完整脚本文本都进 `transcript`，报告里原样附带 —— 这是"没写 PG"的第一层
    证据：整个 transcript 里只有 BEGIN / SET TRANSACTION READ ONLY / SELECT / ROLLBACK。
    """

    label = "docker-exec-psql"

    def __init__(self, container: str = DEFAULT_CONTAINER, runner=None):
        self.command = docker_psql_command(container)
        self._run = runner or subprocess.run
        self.transcript: list = []
        self.malformed: list = []

    def script_for(self, query: Query) -> str:
        #: 第一行进的是 psql 的 stdin，也会出现在服务端日志与 pg_stat_activity 的语句里，所以标
        #: 上查询名：出了岔子能立刻知道是哪一问，而不是回去数第几条。
        marker = "-- r145:" + query.name + "\n"
        return marker + ";\n".join(
            list(TX_BEGIN) + [query.sql] + list(TX_END)) + ";\n"

    def rows(self, query: Query) -> list:
        _assert_read_only(query.sql)
        script = self.script_for(query)
        self.transcript.append({"query": query.name, "script": script})
        completed = self._run(
            self.command, input=script, capture_output=True, text=True, encoding="utf-8"
        )
        if getattr(completed, "returncode", 0):
            raise MirrorUnavailable(
                "psql 退出码 %s：%s" % (
                    completed.returncode,
                    str(getattr(completed, "stderr", "") or "")[-400:],
                )
            )
        rows, malformed = parse_rows(query, getattr(completed, "stdout", "") or "")
        self.malformed.extend(malformed)
        return rows

    def close(self) -> None:
        return None


class PsycopgReader:
    """同一份 SQL 的第二条通道：本机宿主 PG（没有 docker 时用）。

    整场审计坐在**一个** READ ONLY 事务里，收尾只有 ROLLBACK —— 没有任何一条路径会 COMMIT，
    所以就算白名单与关键字闸都漏了，服务端也不会有任何持久化。
    """

    label = "psycopg-read-only"

    def __init__(self, dsn: str, connect=None):
        self._dsn = str(dsn or "")
        self._connect = connect
        self._connection = None
        self.transcript: list = []
        self.malformed: list = []

    def _ensure(self):
        if self._connection is not None:
            return
        if self._connect is not None:
            self._connection = self._connect(self._dsn)
        else:
            import psycopg

            self._connection = psycopg.connect(
                self._dsn, autocommit=False, connect_timeout=5, application_name="r145-audit"
            )
        self._connection.execute(TX_BEGIN[0])
        self._connection.execute(TX_BEGIN[1])
        self.transcript.append({"query": "#transaction", "script": ";\n".join(TX_BEGIN) + ";"})

    def _reopen(self) -> None:
        #: 失败之后必须重开一个只读事务：psycopg 的 aborted transaction 会让同一事务里的后续
        #: 查询只回"当前事务被终止"，于是四问报的全是同一个二级错，真因（表不存在）被盖掉。
        #: 这里只 rollback 自己那笔没结束的事务，然后重新 BEGIN + SET TRANSACTION READ ONLY。
        try:
            self._connection.rollback()
        except Exception:  # pragma: no cover - 连接已断时没什么可回滚的
            pass
        self._connection.execute(TX_BEGIN[0])
        self._connection.execute(TX_BEGIN[1])
        self.transcript.append({
            "query": "#transaction",
            "script": ";".join(TX_BEGIN) + "; -- reopened after a failed statement",
        })

    def rows(self, query: Query) -> list:
        _assert_read_only(query.sql)
        self._ensure()
        self.transcript.append({"query": query.name, "script": query.sql})
        try:
            cursor = self._connection.execute(query.sql)
            records = cursor.fetchall() or []
        except Exception:
            self._reopen()
            raise
        rows: list = []
        for record in records:
            line = str(record[0] if isinstance(record, (tuple, list)) else record)
            parsed, malformed = parse_rows(query, line)
            rows.extend(parsed)
            self.malformed.extend(malformed)
        return rows

    def close(self) -> None:
        if self._connection is None:
            return
        self.transcript.append({"query": "#transaction", "script": TX_END[0]})
        try:
            self._connection.rollback()
        except Exception:  # pragma: no cover - 连接已断时没什么可回滚的
            pass
        try:
            self._connection.close()
        except Exception:  # pragma: no cover
            pass
        self._connection = None


# ================================================================== Chroma 侧
def file_manifest(directory: Path) -> dict:
    """目录里每个文件的 size + sha256 前 16。跑完再算一次，两次必须逐位相同。"""
    manifest = {}
    if not directory.exists():
        return manifest
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        manifest[str(path.relative_to(directory))] = {
            "bytes": path.stat().st_size,
            "sha256_16": digest.hexdigest()[:16],
        }
    return manifest


def copy_chroma_source(source: Path, work_root: str | None) -> tuple[Path, Path]:
    """把整目录拷进临时区，之后所有打开动作只对着副本。

    为什么非要拷：`chromadb.PersistentClient` 即使只是 get，也会在 sqlite 上落 -wal/-shm，
    并把元数据 schema 往它自己认得的版本迁移一次 —— 那对仓库里被 git 跟踪的 `chroma_db/`
    就是写。工单那条红线（业主正在处置那批脏文件）靠这个函数满足，不靠"我只读"的声明。
    """
    source = Path(source)
    if not source.exists():
        raise MirrorUnavailable("Chroma 目录不存在：" + str(source) + "（本脚本不新建目录）")
    if work_root:
        #: 调用方给的临时区可能还没存在（--work-dir 是命令行来的）。mkdtemp 对着不存在的
        #: 目录会直接 FileNotFoundError，那不是"审计结论"，所以先把它建出来 —— 只建在临时区，
        #: 源目录自始至终只被 copytree 读。
        Path(work_root).mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="r145-chroma-", dir=work_root)) / source.name
    shutil.copytree(source, destination, dirs_exist_ok=False)
    return destination, source


def open_chroma(collection_name: str, chroma_dir: Path, client_factory=None):
    """只 get，永不 query / add / upsert / delete。取不到 collection 就是前置不满足。"""
    if client_factory is None:
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - 取决于装了些什么
            raise MirrorUnavailable("chromadb 不可用：" + str(exc))
        client_factory = chromadb.PersistentClient
    client = client_factory(path=str(chroma_dir))
    try:
        return client.get_collection(name=collection_name)
    except Exception as exc:
        raise MirrorUnavailable(
            "取不到 collection " + repr(collection_name) + "：" + str(exc)
        )


def read_chroma(collection, page: int = 5000, with_shapes: bool = True) -> dict:
    """Chroma 侧的 id 全集与宽度分布。宽度是"形状"，不是距离 —— 一个向量都不算。"""
    ids: list = []
    widths: dict = {}
    documents: dict = {}
    offset = 0
    calls = 0
    while True:
        #: metadatas 永远要（按文档聚合靠它的 filename）；embeddings 只在要形状时读，
        #: 而读 embeddings 是"量长度"，本脚本一次都不拿它去算距离。
        include = ["metadatas"] + (["embeddings"] if with_shapes else [])
        try:
            page_result = collection.get(include=include, limit=page, offset=offset)
        except TypeError:
            page_result = collection.get(include=include)
        calls += 1
        batch_ids = [str(item) for item in ((page_result or {}).get("ids") or [])]
        metadatas = (page_result or {}).get("metadatas")
        for position, vector_id in enumerate(batch_ids):
            metadata = (metadatas[position]
                        if metadatas is not None and position < len(metadatas) else None)
            filename = str((metadata or {}).get("filename") or "").strip()
            if not filename:
                #: 没有 metadata.filename 的行只能按 "<filename>_<ordinal>" 反切一刀，
                #: 切不准时它只是一个"数枚数"的标签，不参与任何一致性判定。
                filename = vector_id.rpartition("_")[0] or vector_id
            documents[filename] = documents.get(filename, 0) + 1
        if with_shapes:
            vectors = (page_result or {}).get("embeddings")
            for position, vector_id in enumerate(batch_ids):
                width = None
                if vectors is not None and position < len(vectors):
                    try:
                        width = len(vectors[position])
                    except TypeError:
                        width = None
                widths[str(width)] = widths.get(str(width), 0) + 1
        ids.extend(batch_ids)
        if len(batch_ids) < page or calls > 1000:
            break
        offset += page
    return {
        "ids": sorted(ids),
        "total": len(ids),
        "distinct": len(set(ids)),
        "widths": widths,
        "documents": documents,
        "get_calls": calls,
    }


# ================================================================== 判读
#: 每个桶都对应一句人话，写在报告里，免得读的人回头去猜脚本想了什么。
NULL_BUCKET_WORDS = {
    "never_published": "该文档在 chunks 里没有任何带 index_version_id 的行 —— 向量刚进镜像、"
                       "还没被任何发布收编，按 R76 语义是正常待回填，不是故障",
    "written_after_last_publication": "该行比该文档最近一次发布更晚写进镜像 —— 正常待回填："
                                      "下一次发布会把它收编（R76 的 vector_index_version 步）",
    "publication_newer_than_write": "该文档已经有过发布、而这一行却还挂在新发布之前 —— "
                                    "需要人看：要么这一代发布早于 R76 上线，要么绑定漏了",
    "legacy_before_r76": "同上，但该文档的发布时间早于 --r76-deployed-at，也就是 R76 上线之前的"
                         "存量：回填它只需要再发布一次，不是缺陷",
    "unpublished_versions": "该文档在 chunks 里有带版本号的行，但那些版本一次都没发布成功过 —— "
                            "NULL 是应有之义（发布没发生过，回填步也就没跑过）",
    "unparsable_timestamp": "这一桶要拿两个时间戳比大小，而本机要么解析不了服务端回的值，要么"
                            "两者一个带时区一个不带（比较本身没有定义）—— 桶只能停在'未分类'："
                            "宁可多一问，不猜一个桶名把人支错方向",
}

CLEAN = "clean"
ATTENTION = "attention"
CANNOT_ASK = "cannot_ask"


def _run_query(reader, queries, name) -> dict:
    """一条查询的三种结局：有行、零行、问不出来。第三种绝不许塌缩成第二种。"""
    query = queries[name]
    try:
        rows = reader.rows(query)
    except Exception as exc:  # 表不存在、权限、服务端拒、docker 不在
        return {
            "asked": False,
            "rows": [],
            "error": "%s: %s" % (type(exc).__name__, str(exc).strip()[:300]),
        }
    return {"asked": True, "rows": list(rows), "error": ""}


def _limit(items: list, limit: int) -> dict:
    return {
        "count": len(items),
        "shown": len(items) if not limit or limit <= 0 else min(limit, len(items)),
        "list": items if not limit or limit <= 0 else items[:limit],
        "truncated": bool(limit and limit > 0 and len(items) > limit),
    }


def _parse_timestamp(value: str):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace(" ", "T", 1))
    except ValueError:
        return None


def answer_q1(reader, queries, chroma, options) -> dict:
    """Q1：两侧集合。三个数 + 三份名单，外加"总数相等但集合不同"那一格。"""
    result = _run_query(reader, queries, "q1_pg_vector_ids")
    if not result["asked"]:
        return {"status": CANNOT_ASK, "blocked_reason": result["error"]}
    pg_ids = [str(row[0]) for row in result["rows"]]
    chroma_ids = [str(item) for item in chroma["ids"]]
    pg_set, chroma_set = set(pg_ids), set(chroma_ids)
    only_chroma = sorted(chroma_set - pg_set)
    only_pg = sorted(pg_set - chroma_set)
    both = sorted(pg_set & chroma_set)
    reasons: list = []
    if only_chroma:
        reasons.append("%d 枚 id 只在 Chroma，PG 镜像没有行" % len(only_chroma))
    if only_pg:
        reasons.append("%d 枚 id 只在 PG，Chroma 已经没有它" % len(only_pg))
    if len(pg_ids) != len(chroma_ids) and not only_chroma and not only_pg:
        reasons.append("集合相同但条数不同（一侧有重复 id）")
    if len(pg_ids) == len(chroma_ids) and (only_chroma or only_pg):
        reasons.append("count_equal_but_sets_differ：两边各 %d 枚却互有缺失" % len(pg_ids))
    if chroma["total"] != chroma["distinct"]:
        reasons.append("Chroma 侧同一 id 出现多次（%d 枚 / %d distinct）" % (
            chroma["total"], chroma["distinct"]))
    if not pg_ids and not chroma_ids:
        reasons.append("两侧都没有行：这一问没有对象，0/0 不许读成'一致'")
    elif not pg_ids:
        reasons.append("镜像一张行都没有（双写从没跑过？）：Chroma 的 %d 枚全部只在单侧" % len(chroma_ids))
    status = CANNOT_ASK if (not pg_ids and not chroma_ids) else (
        ATTENTION if reasons else CLEAN)
    return {
        "status": status,
        "only_in_chroma": len(only_chroma),
        "only_in_pg": len(only_pg),
        "both": len(both),
        "pg_total_rows": len(pg_ids),
        "pg_distinct_ids": len(pg_set),
        "chroma_total_rows": chroma["total"],
        "chroma_distinct_ids": chroma["distinct"],
        "lists": {
            "only_in_chroma": _limit(only_chroma, options.list_limit),
            "only_in_pg": _limit(only_pg, options.list_limit),
        },
        #: Chroma 侧按文档聚合：名单要能指到文档，而不是一串裸 id。
        "chroma_documents": len(chroma.get("documents") or {}),
        "reasons": reasons,
    }


def answer_q2(reader, queries, options) -> dict:
    """Q2：NULL 行的分布与 R76 语义分类。派生桶由服务端算，时间戳比较不在本机重做。"""
    result = _run_query(reader, queries, "q2_null_rows")
    if not result["asked"]:
        return {"status": CANNOT_ASK, "blocked_reason": result["error"]}
    dangling = _run_query(reader, queries, "q2_dangling_bindings")
    totals = _run_query(reader, queries, "q2_mirror_totals")
    mirror_total = mirror_tagged = None
    if totals["asked"] and totals["rows"]:
        mirror_total = int(totals["rows"][0][0] or 0)
        mirror_tagged = int(totals["rows"][0][1] or 0)
    documents: list = []
    buckets: dict = {}
    total = 0
    for filename, null_rows, newest_write, bound_versions, last_published in result["rows"]:
        count = int(null_rows or 0)
        total += count
        published = _parse_timestamp(last_published)
        written = _parse_timestamp(newest_write)
        if int(bound_versions or 0) == 0 or published is None:
            bucket = "never_published" if int(bound_versions or 0) == 0 else "unpublished_versions"
        elif written is None:
            bucket = "unparsable_timestamp"
        else:
            try:
                newer_than_publication = written > published
            except TypeError:
                # 一个带时区一个不带：TIMESTAMPTZ 正常都带，走到这里说明口径已经不正常了。
                # 停在"未分类"报人看，而不是挑一个方向把人支走。
                newer_than_publication = None
                bucket = "unparsable_timestamp"
            else:
                bucket = ("written_after_last_publication" if newer_than_publication
                          else "publication_newer_than_write")
        if bucket == "publication_newer_than_write":
            deployed = options.r76_deployed_at
            if deployed is not None:
                try:
                    before_r76 = published < deployed
                except TypeError:
                    before_r76 = False
                if before_r76:
                    bucket = "legacy_before_r76"
        buckets[bucket] = buckets.get(bucket, 0) + count
        documents.append({
            "filename": filename,
            "null_rows": count,
            "newest_vector_write": newest_write,
            "bound_versions": bound_versions,
            "last_published_at": last_published,
            "bucket": bucket,
            "reading": NULL_BUCKET_WORDS.get(bucket, "桶名未登记，按需要人看处理"),
        })
    attention = [key for key in buckets if key not in (
        "never_published", "written_after_last_publication")]
    cross_checks: list = []
    if mirror_total is None:
        cross_checks.append("镜像总量读不到（%s）：NULL 计数没有对照，只能看分桶" % (
            totals["error"] or "无行"))
    else:
        if mirror_total == 0:
            return {
                "status": CANNOT_ASK,
                "blocked_reason": "%s 是空表：一枚行都没有，'有没有待回填'这一问问不出对象，"
                                  "0 枚 NULL 不许读成全部已回填" % options.vector_table,
                "null_rows_total": 0,
                "documents_with_null_rows": 0,
                "rows": [],
                "documents_total": 0,
                "by_bucket": {},
                "mirror_rows": 0,
                "cross_checks": cross_checks,
            }
        if mirror_total - mirror_tagged != total:
            cross_checks.append(
                "两条独立算法对不上：按文档聚合的 NULL = %d，按总量反推的 NULL = %d"
                "（审计期间镜像在被写，或聚合口径漏了形状）" % (total, mirror_total - mirror_tagged))
            attention.append("totals_mismatch")
    report = {
        "status": ATTENTION if (attention or dangling["rows"] or not dangling["asked"]) else CLEAN,
        "null_rows_total": total,
        "documents_with_null_rows": len(documents),
        "rows": documents if not options.list_limit or options.list_limit <= 0 else documents[
            : options.list_limit
        ],
        "documents_total": len(documents),
        "mirror_rows": mirror_total,
        "mirror_rows_tagged": mirror_tagged,
        "cross_checks": cross_checks,
        "by_bucket": buckets,
        "binding_anomalies": _limit(
            ["%s -> %s (%s)" % (row[0], row[1], row[2]) for row in dangling["rows"]],
            options.list_limit,
        ) if dangling["asked"] else {"blocked": dangling["error"]},
        "note": "total=0 且镜像里有行 = 全部已被 R76 回填；镜像本身是空表时，这一问没有可判读"
                "的对象，报告按 cannot_ask 处理，不当成一致。",
    }
    return report


def answer_q3(reader, queries, chroma, options) -> dict:
    """Q3：几代向量。第二代就是 R76 那道拒发闸要当场拒掉的形状。"""
    result = _run_query(reader, queries, "q3_pg_generations")
    if not result["asked"]:
        return {"status": CANNOT_ASK, "blocked_reason": result["error"]}
    scope = _run_query(reader, queries, "q3_declared_scope")
    shapes = _run_query(reader, queries, "q3_shape_lies")
    declared = None
    if scope["asked"] and scope["rows"]:
        declared = {
            "schema_version": scope["rows"][0][0],
            "embedding_model": scope["rows"][0][1],
            "dimension": scope["rows"][0][2],
            "distance_function": scope["rows"][0][3],
        }
    generations = [
        {
            "embedding_model": row[0],
            "embedding_dimension": row[1],
            "rows": int(row[2] or 0),
            "first_write": row[3],
            "last_write": row[4],
            "matches_declared_scope": None if declared is None else (
                str(row[0]) == str(declared["embedding_model"])
                and str(row[1]) == str(declared["dimension"])),
        }
        for row in result["rows"]
    ]
    reasons: list = []
    if not generations:
        reasons.append("镜像里一行都没有：这一问问不出东西，别读成'只有一代'")
    if len(generations) > 1:
        reasons.append("出现 %d 代向量（%s）：R76 的 vector_index_version 闸会拒掉任何把"
                       "这种镜像标成新版本的发布" % (
                           len(generations),
                           ", ".join("%s/%s×%d" % (g["embedding_model"],
                                                   g["embedding_dimension"], g["rows"])
                                     for g in generations)))
    for generation in generations:
        if generation["matches_declared_scope"] is False:
            reasons.append("代 %s/%s 与 vector_scope 声明的 %s/%s 不符" % (
                generation["embedding_model"], generation["embedding_dimension"],
                declared["embedding_model"], declared["dimension"]))
        if str(generation["embedding_model"] or "") == "":
            reasons.append("有行的 embedding_model 是空串：0010 首写者贴标之前就这样写坏了行")
    if declared is None:
        reasons.append("vector_scope 读不到（%s）：没有声明口径，代际比对只能看分组自身" % (
            scope["error"] or "无行"))
    shape_rows = [] if not shapes["asked"] else [
        "%s 声明 %s 实宽 %s" % (row[0], row[1], row[2]) for row in shapes["rows"]
    ]
    if shape_rows:
        reasons.append("%d 行的 vector_dims(embedding) 与自己的 embedding_dimension 不符" % len(shape_rows))
    chroma_widths = {key: value for key, value in chroma.get("widths", {}).items()}
    if len([key for key in chroma_widths if key != "None"]) > 1:
        reasons.append("Chroma 侧宽度也不止一种：%s" % chroma_widths)
    return {
        "status": CANNOT_ASK if not generations else (ATTENTION if reasons else CLEAN),
        "declared_scope": declared,
        "generations": generations,
        "generation_count": len(generations),
        "declared_scope_blocked": (not scope["asked"]) and scope["error"],
        "shape_lies": _limit(shape_rows, options.list_limit) if shapes["asked"] else {
            "blocked": shapes["error"]},
        "chroma_widths": chroma_widths,
        "reasons": reasons,
    }


def answer_q4(reader, queries, options) -> dict:
    """Q4：孤儿两个方向，外加"派生尺不适用"那一类必须先点名。"""
    vectors = _run_query(reader, queries, "q4_vectors_without_chunks")
    chunks = _run_query(reader, queries, "q4_chunks_without_vectors")
    if not vectors["asked"] or not chunks["asked"]:
        return {
            "status": CANNOT_ASK,
            "blocked_reason": "; ".join(
                item["error"] for item in (vectors, chunks) if not item["asked"]),
        }
    vector_orphans = [
        "%s (filename=%s chunk_index=%s index_version_id=%s)" % (row[0], row[1], row[2], row[3])
        for row in vectors["rows"]
    ]
    chunk_orphans = [
        {"vector_id": row[0], "chunk_rows": row[1], "bound_chunk_rows": row[2],
         "current_version_rows": row[3]}
        for row in chunks["rows"]
    ]
    live_chunk_orphans = [
        item for item in chunk_orphans if int(item["current_version_rows"] or 0) > 0
    ]
    shapes = _run_query(reader, queries, "q4_chunk_id_shapes")
    id_shapes = _run_query(reader, queries, "q4_vector_id_shapes")
    reasons: list = []
    if vector_orphans:
        reasons.append("%d 行向量在 chunks 里派生不出对应 chunk（镜像有、账上没有）" % len(vector_orphans))
    if live_chunk_orphans:
        reasons.append("%d 枚 chunk 属于当前发布版本却没有向量行（账上有、镜像没有）" % len(live_chunk_orphans))
    if shapes["asked"] and shapes["rows"]:
        reasons.append("%d 行 chunk_id 不符合 '<filename>|v<version>#<ordinal>'，"
                       "0010 那条派生尺对它们不成立 —— 上面的孤儿判定对这几行不可信" % len(shapes["rows"]))
    if id_shapes["asked"] and id_shapes["rows"]:
        reasons.append("%d 行 vector_id <> filename || '_' || chunk_index，"
                       "或有控制字符" % len(id_shapes["rows"]))
    return {
        "status": ATTENTION if reasons else CLEAN,
        "vectors_without_chunks": _limit(vector_orphans, options.list_limit),
        "chunks_without_vectors": _limit(
            ["%s(chunk_rows=%s,bound=%s,current=%s)" % (
                item["vector_id"], item["chunk_rows"], item["bound_chunk_rows"],
                item["current_version_rows"]) for item in chunk_orphans],
            options.list_limit),
        "chunks_without_vectors_total": len(chunk_orphans),
        "chunks_without_vectors_on_current_version": len(live_chunk_orphans),
        "chunk_id_shapes_not_derivable": _limit(
            ["%s (resource_id=%s)" % (row[0], row[1]) for row in shapes["rows"]],
            options.list_limit) if shapes["asked"] else {"blocked": shapes["error"]},
        "vector_id_shape_violations": _limit(
            [row[0] for row in id_shapes["rows"]], options.list_limit) if id_shapes["asked"] else {
            "blocked": id_shapes["error"]},
        "reasons": reasons,
    }


# ================================================================== 前置与编排
#: 每问需要哪些表/列在场。缺了就说"问不出来"，绝不把缺表读成"零差异"。
REQUIRED_COLUMNS = {
    "chunk_vectors": (
        "vector_id", "filename", "chunk_index", "index_version_id",
        "embedding_model", "embedding_dimension", "created_at", "updated_at",
    ),
    "chunks": ("chunk_id", "resource_id", "index_version_id", "metadata"),
    "index_versions": ("index_version_id", "published_at"),
    "index_registry": ("index_id", "current_version_id"),
}
OPTIONAL_COLUMNS = {
    "vector_scope": ("schema_version", "embedding_model", "dimension", "distance_function"),
}
QUESTION_NEEDS = {
    "q1": ("chunk_vectors",),
    "q2": ("chunk_vectors", "chunks", "index_versions", "index_registry"),
    "q3": ("chunk_vectors",),
    "q4": ("chunk_vectors", "chunks", "index_registry"),
}


def check_preconditions(reader, queries) -> dict:
    """一次 information_schema 读，换回四问各自的"能不能问"。"""
    result = _run_query(reader, queries, "preconditions")
    if not result["asked"]:
        return {
            "ok": False,
            "present": {},
            "askable": {key: False for key in QUESTION_NEEDS},
            "blocking": ["PG 侧读不到 information_schema：" + result["error"]],
            "per_question": {},
            "missing": {},
        }
    present: dict = {}
    for table, column in result["rows"]:
        present.setdefault(str(table), set()).add(str(column))
    missing: dict = {}
    for table, columns in REQUIRED_COLUMNS.items():
        absent = sorted(column for column in columns if column not in present.get(table, set()))
        if absent:
            missing[table] = absent
    askable: dict = {}
    per_question: dict = {}
    for question, tables in QUESTION_NEEDS.items():
        blockers = []
        for table in tables:
            if table not in present:
                blockers.append("表 %s 不存在（未跑 0002/0010 的迁移？）" % table)
            elif table in missing:
                blockers.append("表 %s 缺列 %s" % (table, ", ".join(missing[table])))
        askable[question] = not blockers
        per_question[question] = blockers
    return {
        "ok": all(askable.values()),
        "present": {table: sorted(columns) for table, columns in sorted(present.items())},
        "askable": askable,
        "per_question": per_question,
        "missing": missing,
        "blocking": sorted({line for block in per_question.values() for line in block}),
        "optional_absent": sorted(
            table for table in OPTIONAL_COLUMNS if table not in present),
    }


def _counts(reader, queries) -> dict:
    result = _run_query(reader, queries, "self_check_counts")
    if not result["asked"]:
        return {"asked": False, "error": result["error"], "tables": {}}
    return {
        "asked": True,
        "tables": {str(row[0]): int(row[1] or 0) for row in result["rows"]},
    }


def audit(reader, queries, chroma_view, options) -> dict:
    """四问逐条作答。任何一问被前置挡住 ⇒ cannot_ask，且整体退出码 2。"""
    pre = check_preconditions(reader, queries)
    before = _counts(reader, queries)
    answers: dict = {}
    for question, answer in (
        ("q1", lambda: answer_q1(reader, queries, chroma_view, options)),
        ("q2", lambda: answer_q2(reader, queries, options)),
        ("q3", lambda: answer_q3(reader, queries, chroma_view, options)),
        ("q4", lambda: answer_q4(reader, queries, options)),
    ):
        if not pre["askable"].get(question):
            answers[question] = {
                "status": CANNOT_ASK,
                "blocked_reason": "; ".join(pre["per_question"].get(question, [])),
            }
        else:
            answers[question] = answer()
    after = _counts(reader, queries)
    if not (before.get("asked") and after.get("asked")):
        #: 前后两次数行都没数出来（表不存在、查询被服务端拒）⇒ 这一格是「没测到」，
        #: 不是「测到了变化」。把 None 打成 False 会把读者的注意力支去查并发写。
        stable = None
    else:
        stable = before["tables"] == after["tables"]
    statuses = {key: value["status"] for key, value in answers.items()}
    return {
        "schema": "r145-vector-mirror-set-audit/1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "pg_transport": getattr(reader, "label", "unknown"),
        "vector_table": options.vector_table,
        "chunks_table": options.chunks_table,
        "scope_table": options.scope_table,
        "collection": options.collection,
        "r76_deployed_at": (options.r76_deployed_at.isoformat()
                            if getattr(options, "r76_deployed_at", None) else None),
        "chroma": chroma_view,
        "preconditions": pre,
        "questions": answers,
        "verdict": statuses,
        "self_check": {
            "row_counts_before": before,
            "row_counts_after": after,
        "row_counts_stable": stable,
            "statement_transcript": list(getattr(reader, "transcript", [])),
            "malformed_output_lines": list(getattr(reader, "malformed", [])),
            "model_calls": 0,
            "distance_comparisons": 0,
        },
    }


def exit_code_for(report: dict) -> int:
    statuses = report.get("verdict", {})
    if not report.get("chroma", {}).get("ok", False):
        return 2
    if any(status == CANNOT_ASK for status in statuses.values()) or len(statuses) < 4:
        return 2
    if any(status == ATTENTION for status in statuses.values()):
        return 1
    return 0


def render(report: dict, limit: int) -> str:
    """给人看的四段。每一段先说能不能问、再说读数、最后给名单。"""
    lines = [
        "R145 向量镜像集合面对账（只读、零模型、不比距离）",
        "  PG 通道 = %s / collection = %s" % (report["pg_transport"], report["collection"]),
        "  前置 ok=%s %s" % (
            report["preconditions"]["ok"],
            "" if report["preconditions"]["ok"] else report["preconditions"]["blocking"][:4],
        ),
        "  Chroma 副本 = %d 枚 id / %d 个文档，宽度分布 %s" % (
            report["chroma"].get("total", 0),
            len(report["chroma"].get("documents") or {}),
            report["chroma"].get("widths", {})),
    ]
    q1 = report["questions"]["q1"]
    if q1["status"] == CANNOT_ASK:
        lines.append("Q1 问不出来：%s" % q1.get("blocked_reason", ""))
    else:
        lines.append("Q1 只在 Chroma=%d 只在 PG=%d 两边都有=%d（%s）" % (
            q1["only_in_chroma"], q1["only_in_pg"], q1["both"], q1["status"]))
        for name, block in (q1.get("lists") or {}).items():
            for item in block["list"][:limit or len(block["list"])]:
                lines.append("    %s: %s" % (name, item))
    lines.append("  --r76-deployed-at = %s" % (report.get("r76_deployed_at") or "未给（"
                 "publication_newer_than_write 不拆 R76 上线前后）"))
    q2 = report["questions"]["q2"]
    if q2["status"] == CANNOT_ASK:
        lines.append("Q2 问不出来：%s" % q2.get("blocked_reason", ""))
    else:
        lines.append("Q2 NULL 行=%d 涉及文档=%d 分桶=%s（%s）" % (
            q2["null_rows_total"], q2["documents_with_null_rows"], q2["by_bucket"], q2["status"]))
        for row in (q2.get("rows") or [])[:limit or 9999]:
            lines.append("    %s: %d 枚 → %s" % (
                row["filename"], row["null_rows"], row["bucket"]))
    q3 = report["questions"]["q3"]
    if q3["status"] == CANNOT_ASK:
        lines.append("Q3 问不出来：%s" % q3.get("blocked_reason", ""))
    else:
        lines.append("Q3 代际=%d 声明=%s（%s）" % (
            q3["generation_count"], q3.get("declared_scope"), q3["status"]))
        for generation in q3["generations"]:
            lines.append("    %s/%s × %s  首写 %s 末写 %s" % (
                generation["embedding_model"], generation["embedding_dimension"],
                generation["rows"], generation["first_write"], generation["last_write"]))
        for reason in q3["reasons"]:
            lines.append("    ! %s" % reason)
    q4 = report["questions"]["q4"]
    if q4["status"] == CANNOT_ASK:
        lines.append("Q4 问不出来：%s" % q4.get("blocked_reason", ""))
    else:
        lines.append("Q4 向量无 chunk=%d 当前版本 chunk 无向量=%d 派生不适用=%d（%s）" % (
            q4["vectors_without_chunks"]["count"],
            q4["chunks_without_vectors_on_current_version"],
            (q4["chunk_id_shapes_not_derivable"] or {}).get("count", 0),
            q4["status"]))
        for item in q4["vectors_without_chunks"]["list"][:limit or 9999]:
            lines.append("    孤儿(向量侧): %s" % item)
        for item in q4["chunks_without_vectors"]["list"][:limit or 9999]:
            lines.append("    孤儿(chunk 侧): %s" % item)
    stable = report["self_check"]["row_counts_stable"]
    lines.append("  自证：审计前后行数稳定=%s，模型调用=%d，距离比较=0" % (
        "问不出来（两张表读不到）" if stable is None else stable,
        report["self_check"]["model_calls"]))
    return "\n".join(lines)


# ================================================================== CLI
def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="R145：向量镜像「集合面」只读对账（零模型、零写入、不比距离）",
    )
    parser.add_argument("--pg-transport", choices=("docker", "psycopg"), default="docker",
                        help="docker＝工单指定的容器内 psql（默认）；psycopg＝同一份 SQL 走宿主 PG")
    parser.add_argument("--container", default=DEFAULT_CONTAINER)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "") or "",
                        help="仅 --pg-transport psycopg 用；默认取环境变量 DATABASE_URL")
    parser.add_argument("--chroma-dir", default=os.getenv("CHROMA_DIR", "./chroma_db"))
    parser.add_argument("--work-dir", default=None, help="临时副本的父目录，默认交给 tempfile（系统临时目录）")
    parser.add_argument("--keep-copy", action="store_true", help="跑完不删临时副本，便于二次核查")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--vector-table", default=DEFAULT_VECTOR_TABLE)
    parser.add_argument("--chunks-table", default=DEFAULT_CHUNKS_TABLE)
    parser.add_argument("--scope-table", default=DEFAULT_SCOPE_TABLE)
    parser.add_argument("--list-limit", type=int, default=DEFAULT_LIST_LIMIT,
                        help="名单打印/写入的条数，0 = 全量")
    parser.add_argument("--chroma-page", type=int, default=5000)
    parser.add_argument("--no-shapes", action="store_true",
                        help="只要 id 集合，不读 embeddings（连宽度都不比）")
    parser.add_argument("--r76-deployed-at", default="",
                        help="ISO 时间戳。给了它才能把「发布比行新却仍是 NULL」拆成 R76 上线前的历史遗留")
    parser.add_argument("--out", default=None, help="完整 JSON 报告的落点")
    return parser.parse_args(argv)


def make_reader(args) -> DockerPsqlReader | PsycopgReader:
    if args.pg_transport == "psycopg":
        if not args.database_url:
            raise MirrorUnavailable("--pg-transport psycopg 需要 --database-url 或环境变量 DATABASE_URL")
        return PsycopgReader(args.database_url)
    return DockerPsqlReader(container=args.container)


def main(argv=None, *, reader_factory=None, client_factory=None) -> int:
    args = parse_args(argv)
    raw_deployed = str(args.r76_deployed_at or "")
    # 归一成一个不变式：往下走的 options.r76_deployed_at 只有 None 与"带时区的 datetime"两种形，
    # 判读函数因此不必再猜空串。
    args.r76_deployed_at = None
    if raw_deployed:
        parsed = _parse_timestamp(raw_deployed)
        if parsed is None:
            sys.stderr.write("[前置不满足] --r76-deployed-at 不是可解析的 ISO 时间戳：" + raw_deployed + "\n")
            return 2
        if parsed.tzinfo is None:
            # 不给时区就当 UTC，并把这句话打到 stderr：这个桶的判读是"发布是否早于 R76 上线"，
            # 差一个钟头就可能在两个桶之间来回跳，所以口径必须说出来而不是留给读者猜。
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
            sys.stderr.write(
                "[口径] --r76-deployed-at 未带时区，按 UTC 解释为 " + parsed.isoformat() + "\n"
            )
        args.r76_deployed_at = parsed

    queries = build_queries(args.vector_table, args.chunks_table, args.scope_table)
    source = Path(args.chroma_dir).resolve()
    manifest_before = file_manifest(source)
    chroma_view: dict = {
        "ok": False, "ids": [], "total": 0, "distinct": 0, "widths": {},
        "get_calls": 0, "source_path": str(source),
    }
    copy_dir: Path | None = None
    reader = None
    report: dict | None = None
    exit_code = 2
    try:
        try:
            copy_dir, _copied_from = copy_chroma_source(source, args.work_dir)
            collection = open_chroma(
                args.collection, copy_dir, client_factory=client_factory)
            view = read_chroma(
                collection, page=args.chroma_page, with_shapes=not args.no_shapes)
            view.update({
                "ok": True, "collection": args.collection,
                #: 两个路径都要留在报告里：opened_path 证明开的是副本，source_path 证明
                #: 逐文件哈希对的是仓库里那一个，不是随手挑的目录。
                "source_path": str(source), "opened_path": str(copy_dir),
            })
            chroma_view = view
        except MirrorUnavailable as exc:
            chroma_view["error"] = str(exc)
        reader = reader_factory(args) if reader_factory else make_reader(args)
        report = audit(reader, queries, chroma_view, args)
        report["chroma"]["source_manifest_before"] = manifest_before
        exit_code = exit_code_for(report)
    finally:
        if reader is not None:
            reader.close()
        manifest_after = file_manifest(source)
        cleanup = {"attempted": copy_dir is not None and not args.keep_copy}
        if cleanup["attempted"]:
            #: Windows 上 chromadb 可能还握着副本里的文件句柄，rmtree 会静默失败；拿
            #: ignore_errors=True 一盖，就是把 200MB 临时目录悄悄留在客户机器上。这里改成
            #: 说出来：删不掉就把路径写进报告与 stderr，让运维自己清（仓库目录未受影响）。
            root = copy_dir.parent
            cleanup["path"] = str(root)
            try:
                shutil.rmtree(root)
            except OSError as exc:
                cleanup["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:200])
            cleanup["removed"] = not root.exists()
            if not cleanup["removed"]:
                sys.stderr.write("[待清理] 临时副本没能删除（多半是 chromadb 还握着句柄）："
                                 + str(root) + " —— 请手工删除；仓库 Chroma 目录未受影响" + "\n")
        if report is not None:
            report["chroma_copy_cleanup"] = cleanup
            report["chroma"]["source_manifest_after"] = manifest_after
            report["chroma"]["source_untouched"] = manifest_after == manifest_before
            report["self_check"]["chroma_source_files"] = len(manifest_after)
            if args.out:
                Path(args.out).write_text(
                    json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8",
                )
            print(render(report, args.list_limit))
            print("  仓库 Chroma 目录逐文件哈希前后一致 = %s（清单条目 %d 枚）" % (
                report["chroma"].get("source_untouched"), len(manifest_after)))
            print("  完整 SQL transcript：%d 条，全部 SELECT/WITH，收尾只有 ROLLBACK" % len(
                report["self_check"]["statement_transcript"]))
            if args.out:
                print("  JSON 报告 = " + str(args.out))
        else:
            print("[前置不满足] 仓库 Chroma 目录未被写入 = %s" % (manifest_after == manifest_before))
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())