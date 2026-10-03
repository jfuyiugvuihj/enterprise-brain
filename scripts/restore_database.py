"""Restore or inspect a PostgreSQL logical backup without exposing credentials in argv.

The companion of ``scripts/backup_database.py``. A restore drill must run against an
explicitly named target database so an operator can verify a backup in isolation before
promoting it.

R596 adds the half that ``pg_dump`` structurally cannot carry. Library-level and
role-in-database settings live in ``pg_db_role_setting``, which appears nowhere in a
custom-format archive's table of contents: a restored database answers
``current_setting('app.embedding_dimension')`` with MISSING even when every vector row came
back, which is exactly the "green backup, wrong read path" false pass R587 documented. The
backup side therefore hands over a paired artifact next to the archive
(``<archive stem>.globals.json`` and ``<archive stem>.globals.sql``); this side reads it
*before* touching the target, applies it right after ``pg_restore`` and before any
reconciliation, then compares the restored database against the recorded source item by
item. The wire shape is R587's shape -- same suffixes, same ``kind``, the same seven columns,
the same database-agnostic profile key, the same two apply templates whose statements compute
the database name from ``current_database()`` -- so the drill and the shipped CLI keep one
book of accounts instead of two.

Exit codes: 0 restored and reconciled; 1 an operation failed; 2 refused before the target was
touched (no ``DATABASE_URL``, no paired globals artifact, an artifact that does not match its
archive, an apply statement that names a database literally); 3 the restore ran but the
globals do not reconcile, every unequal item named.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv


def _pg_environment(database_url: str) -> tuple[dict[str, str], str]:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use a PostgreSQL scheme")
    if not parsed.hostname or not parsed.path or parsed.path == "/":
        raise ValueError("DATABASE_URL must include host and database name")

    environment = os.environ.copy()
    environment["PGHOST"] = parsed.hostname
    environment["PGPORT"] = str(parsed.port or 5432)
    if parsed.username:
        environment["PGUSER"] = unquote(parsed.username)
    if parsed.password is not None:
        environment["PGPASSWORD"] = unquote(parsed.password)
    environment.pop("DATABASE_URL", None)
    return environment, unquote(parsed.path.lstrip("/"))


def _run(command: list[str], environment: dict[str, str], *, capture: bool = False) -> subprocess.CompletedProcess:
    """Execute a PostgreSQL client tool with redaction-safe error reporting."""
    try:
        return subprocess.run(
            command,
            env=environment,
            check=True,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"{command[0]} failed: {detail[-500:]}") from exc


class RefuseError(RuntimeError):
    """前置不满足（退出码 2）：不碰目标库，也不出一份对账结论。"""


class MismatchError(RuntimeError):
    """对账不等（退出码 3）：每一条都得点名，沉默不算通过。"""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems) or "globals 对账不等，而且一枚读数都没交回")
        self.problems = list(problems)


# ============================================================================
# R596｜库级/角色级 setting 的成对产物：pg_dump 交不出、pg_restore 建不回的那一族。
#
# 这一族住在 ``pg_db_role_setting`` 里，custom 格式归档的目录（TOC）根本没有它，所以恢复库
# ``current_setting('app.embedding_dimension')`` 读出来是 MISSING，而向量一枚不少、备份日志
# 全绿。形状照 R587 那一本账（同名后缀、同一枚 kind、同七列、同一把不带库名的对账钥匙、同两
# 枚施加模板），本文件不另起第三套格式；差别只有一处：出厂 CLI 在宿主侧用 psql 读，一行七列
# 里的 value 允许带竖线，所以这里把七列逐枚起名、整批以一枚 JSON 交回。
# ============================================================================

#: 成对产物的名字只从归档名派生：同目录、同前缀，一眼能核对是哪一枚 dump 的 globals。
GLOBALS_JSON_SUFFIX = ".globals.json"
GLOBALS_SQL_SUFFIX = ".globals.sql"
#: 产物里带这一枚 kind，读的时候先验身份：别的件生成的同名文件不许冒充。
GLOBALS_KIND = "r587-database-globals"
#: 三种作用域；``deferred`` 指集群级角色 setting，只上报、绝不施加（施加它会改整台实例）。
GLOBALS_SCOPES = ("database", "role_in_database", "deferred")
#: 一库多行时 ``(all)`` 是"这库里的所有角色"这一**标签**，不是库名。
GLOBALS_ALL_ROLES_LABEL = "(all)"
#: ``pg_db_role_setting`` 一行摊平成"一名一句"之后认得的七列；列名在这枚 SQL 里就地起好。
GLOBALS_COLUMNS = ("scope", "setdatabase", "setrole", "database", "role", "name", "value")
GLOBALS_SQL = (
    "SELECT CASE WHEN st.setdatabase IS NULL THEN 'deferred' "
    "WHEN st.setrole = 0 THEN 'database' ELSE 'role_in_database' END AS scope, "
    "st.setdatabase, st.setrole, coalesce(db.datname, current_database()) AS database, "
    "coalesce(r.rolname, '(all)') AS role, split_part(cfg.item, '=', 1) AS name, "
    "substring(cfg.item FROM position('=' in cfg.item) + 1) AS value "
    "FROM pg_db_role_setting st "
    "LEFT JOIN pg_database db ON db.oid = st.setdatabase "
    "LEFT JOIN pg_roles r ON r.oid = st.setrole "
    "CROSS JOIN LATERAL unnest(st.setconfig) AS cfg(item) "
    "WHERE coalesce(db.datname, current_database()) = current_database() "
    "ORDER BY 1, 2, 3, 6"
)
#: 七列一次交回的一枚 JSON 数组；空表交 ``[]``，不许交"什么都没有"混成"读成功"。
GLOBALS_ROWS_JSON_SQL = "SELECT coalesce(json_agg(t), '[]'::json)::text FROM (" + GLOBALS_SQL + ") t"
GLOBALS_DATABASE_SQL = "SELECT current_database()"
#: 会话读数：一名一枚，读不到就是 MISSING，绝不折成空串。名字来自 ``app/db/migrations.py``。
SESSION_GUC_SQL_HEAD = (
    "SELECT json_object_agg(name, coalesce(current_setting(name, TRUE), 'MISSING'))::text "
    "FROM unnest(ARRAY["
)
SESSION_GUC_SQL_TAIL = "]) AS name"
#: 集群角色清单：只报名字与是否 superuser，绝不报 ``rolpassword``——那是 pg_dumpall 会抄进
#: 备份件的 SCRAM 口令散列，本件一个字都不抄。只上报，绝不当对账项。
CLUSTER_ROLES_SQL = (
    "SELECT coalesce(string_agg(rolname || ':' || CASE WHEN rolsuper THEN 'super' "
    "ELSE 'nosuper' END, ',' ORDER BY rolname), 'NONE') FROM pg_roles"
)
#: 施加模板：占位符只吃"验过的名字 + 字面量化后的值"，库名一律由 ``current_database()`` 现算。
DATABASE_APPLY_LINE = (
    "SELECT format('ALTER DATABASE %I SET {name} = %L', "
    "current_database(), {value}) \\gexec"
)
ROLE_APPLY_LINE = (
    "SELECT format('ALTER ROLE %I IN DATABASE %I SET {name} = %L', "
    "{role}, current_database(), {value}) \\gexec"
)
#: 施加件正文里每枚语句必须长这两枚形状之一；形状之外的东西（比如被人手改成写死库名的
#: ``ALTER DATABASE enterprise_brain SET ...``）一律当场拒收。
_APPLY_SHAPES = {
    "database": re.compile(
        r"^SELECT format\('ALTER DATABASE %I SET ([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*) = %L', "
        r"current_database\(\), .+\) \\gexec$"
    ),
    "role_in_database": re.compile(
        r"^SELECT format\('ALTER ROLE %I IN DATABASE %I SET ([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*) = %L', "
        r"'.+', current_database\(\), .+\) \\gexec$"
    ),
}
#: ``setting`` 名要进 SQL 文本，所以它先得长得像一个名字（值走 ``sql_literal``，不受此限）。
_SETTINGS_NAME = re.compile(r"^[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*$")
#: 只读那一腿的语句里一枚写动词都不许出现（字面量里的词先摘掉再问）。
_WRITE_VERB = re.compile(
    r"\b(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|TRUNCATE|GRANT|REVOKE|COPY|VACUUM|ANALYZE|"
    r"REINDEX|REFRESH|LOCK|COMMENT|MERGE)\b",
    re.IGNORECASE,
)

#: 进门控的两项 globals 读数，名字与 R587 的 ``RECON_ITEMS``（12→14 新增的那两格）同一本账。
RECON_ITEMS = ("globals_profile", "globals_session")
#: 照实上报、绝不当对账项的两项，同样沿用 R587 的 ``EXTRA_ITEMS`` 那两枚名字：
#: ``globals_deferred`` 是 ``ALTER ROLE ... SET`` 那一族（恢复单库管不着整台实例），
#: ``cluster_roles`` 是角色清单（单库恢复既不建角色也不删角色）。
EXTRA_ITEMS = ("globals_deferred", "cluster_roles")


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
        raise RefuseError("NUL 进不了 PostgreSQL 文本列")
    return "'" + text.replace("'", "''") + "'"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def checked_setting_name(name) -> str:
    if not _SETTINGS_NAME.match(str(name or "")):
        raise RefuseError(f"setting 名必须是小写点分标识符，拿到 {name!r}")
    return str(name)


def required_global_settings() -> tuple[str, ...]:
    """恢复库必须逐枚等上的那几枚名字——真源是迁移件，本件不再抄一份。"""
    from app.db import migrations

    return (migrations.EMBEDDING_DIMENSION_GUC, migrations.EMBEDDING_MODEL_GUC)


def session_guc_sql(names) -> str:
    checked = [sql_literal(checked_setting_name(name)) for name in names]
    if not checked:
        raise RefuseError("会话读数没有必读 setting 名：宁可乐死也不交一本空账")
    return SESSION_GUC_SQL_HEAD + ", ".join(checked) + SESSION_GUC_SQL_TAIL


def globals_paths_for(archive: str | Path) -> dict[str, Path]:
    source = Path(archive)
    base = str(source.parent / source.stem)
    return {"archive": source, "json": Path(base + GLOBALS_JSON_SUFFIX),
            "sql": Path(base + GLOBALS_SQL_SUFFIX)}


def globals_profile_key(row: dict) -> str:
    """对账的钥匙不带库名：恢复库本来就叫别的名字，带上它两侧永远不等（老口径的死因）。"""
    return f"{row['scope']}|{row['role']}|{row['name']}"


def globals_profile(rows) -> str:
    applied = [row for row in rows if row["scope"] != "deferred"]
    return " ;; ".join(sorted(globals_profile_key(row) + "=" + str(row["value"])
                              for row in applied)) or "EMPTY"


def globals_deferred_profile(rows) -> str:
    deferred = [row for row in rows if row["scope"] == "deferred"]
    return " ;; ".join(sorted(f"role={row['role']} {row['name']}={row['value']}"
                              for row in deferred)) or "NONE"


def globals_session_values(session: dict, names) -> list:
    """逐枚点名每颗 setting 的会话读数；``None`` 只准在这里现形，落进对账串就变成 MISSING 了。"""
    return [(name, session.get(name)) for name in names]


def globals_session_profile(session: dict, names) -> str:
    return " ;; ".join(f"{name}={value}" for name, value in globals_session_values(session, names))


def checked_globals_row(cells) -> dict:
    """一行 setting 先得是七列，名字与值都得是能跑的形态。"""
    values = [cells.get(key) for key in GLOBALS_COLUMNS] if isinstance(cells, dict) else list(cells)
    values = values + [None] * (7 - len(values))
    scope, setdatabase, setrole, database, role, name, value = values[:7]
    if scope not in GLOBALS_SCOPES:
        raise RefuseError("globals 读数交了认不得的作用域 " + repr(scope)
                          + "（在册：" + ", ".join(GLOBALS_SCOPES) + "）")
    checked_setting_name(name)
    if value is None:
        raise RefuseError(f"setting {name!r} 的值读成了空：pg_db_role_setting 的行形被改坏了")
    return {"scope": scope, "setdatabase": setdatabase, "setrole": setrole,
            "database": database, "role": role, "name": name, "value": value}


def checked_globals_rows(rows) -> list[dict]:
    if not isinstance(rows, list):
        raise RefuseError(f"globals 读数不是清单：{type(rows).__name__}")
    checked = [checked_globals_row(row) for row in rows]
    for row in checked:
        if row["scope"] == "deferred" and row["setdatabase"] is not None:
            raise RefuseError("globals 读数自相矛盾：deferred 行带着 setdatabase="
                              + str(row["setdatabase"]))
        if row["scope"] != "deferred" and not row["database"]:
            raise RefuseError("globals 读数自相矛盾：库级行没有库名")
        if row["scope"] == "role_in_database" and not row["role"]:
            raise RefuseError("globals 读数自相矛盾：角色级行没有角色名")
    keys = [globals_profile_key(row) for row in checked if row["scope"] != "deferred"]
    duplicated = sorted({key for key in keys if keys.count(key) > 1})
    if duplicated:
        raise RefuseError("同一库里同一枚作用域出现了重名 setting：" + ", ".join(duplicated))
    return checked


def globals_apply_line(row: dict) -> str:
    if row["scope"] == "deferred":
        raise RefuseError("集群级 ALTER ROLE ... SET 不许由本件施加（它会改整台实例的所有库）："
                          + f"{row['role']} {row['name']}")
    template = DATABASE_APPLY_LINE if row["scope"] == "database" else ROLE_APPLY_LINE
    line = template.replace("{name}", checked_setting_name(row["name"]))
    if row["scope"] == "role_in_database":
        line = line.replace("{role}", sql_literal(row["role"]))
    line = line.replace("{value}", sql_literal(row["value"]))
    shape = _APPLY_SHAPES[row["scope"]]
    if not shape.match(line):
        raise RefuseError("施加语句的形状不对，正文里疑似带了库名或别的语句：" + line[:160])
    return line


def globals_apply_lines(rows) -> list[str]:
    applied = sorted((row for row in rows if row["scope"] != "deferred"),
                     key=lambda row: (row["scope"], str(row["role"]), row["name"]))
    return [globals_apply_line(row) for row in applied]


def globals_sql_body(text: str) -> list[str]:
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
        "-- R596｜库级/角色级 setting 的施加件：与同名 .dump 成对，别单飞。",
        f"-- 源库 {payload['source_db']} 现取于 {payload['captured_utc']}；库名只进注释作账，"
        "语句里一枚都不带（库名由 current_database() 现算）。",
        f"-- 配对凭据：{archive['name']} sha256={archive['sha256']}",
        f"-- 施加 {len(payload['apply_lines'])} 枚；集群级 {len(deferred)} 枚只上报，逐枚点名：",
    ]
    header += [f"-- deferred role={row['role']} {row['name']}={row['value']}" for row in deferred]
    return "\n".join(header + ["BEGIN;"] + list(payload["apply_lines"]) + ["COMMIT;"]) + "\n"


def _psql_argv(psql_path: str, database_name: str, statement: str) -> list[str]:
    """只读那一腿：库名走 ``--dbname``，口令只在 env 里，``ON_ERROR_STOP`` 让 psql 不许咽错。"""
    return [
        psql_path,
        "--dbname", database_name,
        "--no-psqlrc",
        "--quiet",
        "--tuples-only",
        "--no-align",
        "--variable=ON_ERROR_STOP=1",
        "--command", statement,
    ]


def _run_psql(command: list[str], environment: dict[str, str], *, label: str,
              stdin_text: str | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=stdin_text,
        )
    except FileNotFoundError as exc:
        raise RefuseError(
            f"找不到 {command[0]}：镜像里没装 postgresql-client-17，任何走 psql 的备份/恢复腿都"
            "结构性跑不起来（判据③；见 Dockerfile 与 docs/testing/r596-*.md）"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"psql {label} failed: {detail[-500:]}") from exc


def checked_read_statement(statement: str) -> str:
    text = (statement or "").strip()
    if not text.upper().startswith(("SELECT", "WITH")):
        raise RefuseError("只读那一腿只发 SELECT/WITH，拿到：" + text[:80])
    bare = re.sub(r"'[^']*'", "", text)
    verbs = sorted({hit.upper() for hit in _WRITE_VERB.findall(bare)})
    if verbs:
        raise RefuseError("只读那一腿里出现了写动词 " + ", ".join(verbs) + "：" + text[:80])
    return text


def _psql_lines(database_url: str, statement: str, *, psql_path: str, label: str) -> list[str]:
    environment, database_name = _pg_environment(database_url)
    result = _run_psql(_psql_argv(psql_path, database_name, checked_read_statement(statement)),
                       environment, label=label)
    return [line for line in (result.stdout or "").splitlines() if line.strip()]


def _read_one(database_url: str, statement: str, *, psql_path: str, label: str) -> str:
    """取一枚标量：多一行就是没读懂，宁可乐死也不猜。"""
    lines = _psql_lines(database_url, statement, psql_path=psql_path, label=label)
    if len(lines) != 1:
        raise RefuseError(f"{label} 期望一枚值，psql 交了 {len(lines)} 行："
                          + " | ".join(line[:60] for line in lines[:3]))
    return lines[0].strip()


def _read_json(database_url: str, statement: str, *, psql_path: str, label: str):
    """取一枚 JSON 值：PostgreSQL 会把聚合出来的 JSON 在元素之间换行。

    本机 PostgreSQL 16.15 现取（``docker exec ... psql -X -q -t -A -c``）：
    ``json_agg`` 交回的是 ``[{"a":"x"}, `` + 换行 + ``{"a":"y"}]``——换行落在元素之间，
    是合法的 JSON 空白，不是两条记录。按行读会把两枚 setting 判成"psql 交了 2 行"当场拒，
    所以这里把整段输出拼回去再解一次；解不出来仍然拒，绝不退成空账。
    """
    lines = _psql_lines(database_url, statement, psql_path=psql_path, label=label)
    if not lines:
        raise RefuseError(f"{label} 一枚值都没交回：psql 输出为空")
    text = "\n".join(line.strip() for line in lines)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise RefuseError(f"{label} 交回来的不是 JSON：{text[:160]!r}（{exc}）") from exc


def collect_globals(database_url: str, *, psql_path: str = "psql") -> dict:
    """现取这库的库级/角色级 setting，外加会话里那几枚必读项的读数。"""
    source_db = _read_one(database_url, GLOBALS_DATABASE_SQL, psql_path=psql_path,
                          label="current_database()")
    rows = checked_globals_rows(_read_json(database_url, GLOBALS_ROWS_JSON_SQL,
                                           psql_path=psql_path, label="pg_db_role_setting") or [])
    names = list(required_global_settings())
    session = _read_json(database_url, session_guc_sql(names), psql_path=psql_path,
                         label="session setting")
    if not isinstance(session, dict):
        raise RefuseError(f"会话读数不是对象：{type(session).__name__}")
    unread = [name for name in names if name not in session]
    if unread:
        raise RefuseError("psql 没交回这几枚必读 setting 的会话读数：" + ", ".join(unread))
    kept = {name: session[name] for name in names}
    return {"database": source_db, "rows": rows, "session": kept, "names": names,
            "profile": globals_profile(rows),
            "session_profile": globals_session_profile(kept, names),
            "deferred_profile": globals_deferred_profile(rows)}


def write_globals_pair(database_url: str, archive: str | Path, *, psql_path: str = "psql",
                       stamp: str | None = None) -> dict:
    """判据①的落盘：同目录、同前缀、带归档 sha 的成对产物（json 是账，sql 是能跑的件）。"""
    source = Path(archive).resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise RefuseError(f"globals 产物要配对归档，可归档不存在或为空：{source}")
    reading = collect_globals(database_url, psql_path=psql_path)
    paths = globals_paths_for(source)
    payload = {
        "kind": GLOBALS_KIND,
        "source_db": reading["database"],
        "captured_utc": stamp or utc_stamp(),
        "archive": {"name": source.name, "path": str(source),
                    "bytes": source.stat().st_size, "sha256": sha256_file(source)},
        "rows": reading["rows"],
        "session": reading["session"],
        "names": list(reading["names"]),
        "profile": reading["profile"],
        "session_profile": reading["session_profile"],
        "deferred_profile": reading["deferred_profile"],
        "apply_lines": globals_apply_lines(reading["rows"]),
    }
    rendered = render_globals_sql(payload)
    if globals_sql_body(rendered) != payload["apply_lines"]:
        raise RefuseError("施加件正文与按 rows 现算的语句不等（生成逻辑自己就不配对）")
    _write_text(paths["json"], json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")
    _write_text(paths["sql"], rendered)
    return {"json": str(paths["json"]), "sql": str(paths["sql"]),
            "json_sha256": sha256_file(paths["json"]), "sql_sha256": sha256_file(paths["sql"]),
            "archive": str(source), "archive_sha256": payload["archive"]["sha256"],
            "source_db": reading["database"],
            "applied": len(payload["apply_lines"]),
            "deferred": len([row for row in payload["rows"] if row["scope"] == "deferred"]),
            "profile": payload["profile"], "session_profile": payload["session_profile"]}


def _write_text(path: Path, text: str) -> None:
    """成对产物一律按 LF 落盘：同一份内容在 Windows 与容器里要交回同一枚 sha256。"""
    path.write_text(text, encoding="utf-8", newline="\n")


def read_globals_pair(archive: str | Path, *, paths: dict | None = None) -> dict:
    """把成对产物读回一枚可信的 payload；四处不成对任一处红，都不许"缺失但看起来能跑"。"""
    source = Path(archive).resolve()
    paths = paths or globals_paths_for(source)
    absent = [str(paths[key]) for key in ("json", "sql") if not Path(paths[key]).is_file()]
    if absent:
        raise RefuseError("备份没有成对的 globals 产物（判据①）：" + "、".join(absent)
                          + "——少了它，恢复库的 " + "/".join(required_global_settings())
                          + " 就是 MISSING，备份日志再绿也是假绿")
    if not source.is_file() or source.stat().st_size == 0:
        raise RefuseError(f"归档不存在或为空：{source}")
    try:
        payload = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RefuseError(f"globals 产物读不动：{paths['json']}（{exc}）") from exc
    if not isinstance(payload, dict):
        raise RefuseError(f"globals 产物不是对象：{paths['json']}")
    if payload.get("kind") != GLOBALS_KIND:
        raise RefuseError("globals 产物的 kind 不对：期望 " + GLOBALS_KIND + "，实得 "
                          + repr(payload.get("kind")) + f"（{paths['json']}）")
    recorded = (payload.get("archive") or {}).get("sha256")
    actual = sha256_file(source)
    if not recorded or recorded != actual:
        raise RefuseError("globals 产物与归档不成对：产物记的归档 sha=" + str(recorded)[:12]
                          + f"，{source.name} 实得 sha={actual[:12]}——这两枚不是同一次备份")
    rows = checked_globals_rows(payload.get("rows"))
    names = list(required_global_settings())
    session = payload.get("session")
    if not isinstance(session, dict):
        raise RefuseError(f"globals 产物里没有会话读数那本账：{paths['json']}")
    unread = [name for name in names if name not in session]
    if unread:
        raise RefuseError("globals 产物里没有这几枚必读 setting 的源值：" + ", ".join(unread))
    lines = globals_apply_lines(rows)
    if payload.get("apply_lines") != lines:
        raise RefuseError("globals 产物里记的施加语句与按 rows 现算的不等（产物被改开过？）："
                          + f"{len(payload.get('apply_lines') or [])} 枚 vs {len(lines)} 枚")
    body = globals_sql_body(Path(paths["sql"]).read_text(encoding="utf-8"))
    if body != lines:
        raise RefuseError(".globals.sql 里的语句与产物记录逐字节不等（被人手改开过？）："
                          + f"{len(body)} 枚 vs {len(lines)} 枚")
    payload.update({"rows": rows, "names": names, "apply_lines": lines,
                    "json_path": str(paths["json"]), "sql_path": str(paths["sql"]),
                    "archive_path": str(source), "archive_sha256": actual})
    return payload


def list_backup(archive: str | Path, *, pg_restore_path: str = "pg_restore") -> list[str]:
    """Return the archive table of contents so a backup can be verified before use."""
    source = Path(archive).resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError("backup archive is missing or empty")
    environment = os.environ.copy()
    result = _run([pg_restore_path, "--list", str(source)], environment, capture=True)
    return [line for line in (result.stdout or "").splitlines() if line.strip() and not line.startswith(";")]


def restore_database(
    archive: str | Path,
    database_url: str,
    *,
    pg_restore_path: str = "pg_restore",
) -> str:
    """Restore into the database named by ``database_url`` and return that name."""
    environment, database_name = _pg_environment(database_url)
    source = Path(archive).resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError("backup archive is missing or empty")
    _run(
        [
            pg_restore_path,
            "--dbname",
            database_name,
            "--no-owner",
            "--exit-on-error",
            str(source),
        ],
        environment,
    )
    return database_name


def apply_globals(database_url: str, payload: dict, *, psql_path: str = "psql") -> dict:
    """判据①的落点：整份施加件原样进一枚 psql 会话，打在恢复库上，跑在任何对账之前。

    语句里一枚库名都不带——每枚库名都由 ``current_database()`` 现算，所以同一份
    .globals.sql 打在演练库上是演练库的 setting，打在客户库上是客户库的 setting。
    """
    environment, database_name = _pg_environment(database_url)
    sql_path = Path(payload["sql_path"])
    body = sql_path.read_text(encoding="utf-8")
    if not body.strip():
        raise RefuseError(f"globals 施加件是空的：{sql_path}")
    if globals_sql_body(body) != payload["apply_lines"]:
        raise RefuseError(f"globals 施加件与产物记录逐字节不等，拒促进恢复库：{sql_path}")
    _run_psql(
        [psql_path, "--dbname", database_name, "--no-psqlrc", "--quiet",
         "--variable=ON_ERROR_STOP=1", "--file", "-"],
        environment,
        label="globals apply",
        stdin_text=body,
    )
    return {"sql": str(sql_path), "json": payload["json_path"], "database": database_name,
            "applied": len(payload["apply_lines"]),
            "deferred": len([row for row in payload["rows"] if row["scope"] == "deferred"]),
            "archive_sha256": payload["archive_sha256"]}


def globals_profile_problems(payload: dict, now: dict) -> list[str]:
    """``globals_profile`` 那一格的逐枚点名：少一枚、多一枚、值不等，各说一句人话。"""
    wanted = {globals_profile_key(row): str(row["value"]) for row in payload["rows"]
              if row["scope"] != "deferred"}
    have = {globals_profile_key(row): str(row["value"]) for row in now["rows"]
            if row["scope"] != "deferred"}
    problems = []
    for key in sorted(set(wanted) | set(have)):
        if key not in have:
            problems.append(f"globals_profile[{key}]: 备份里有、恢复库没有（施加那一步没落地）")
        elif key not in wanted:
            problems.append(f"globals_profile[{key}]={have[key]}: 恢复库里多出一枚备份没有的 setting")
        elif wanted[key] != have[key]:
            problems.append(f"globals_profile[{key}]: 备份={wanted[key]!r} 恢复库={have[key]!r}")
    return problems


def globals_session_problems(payload: dict, now: dict) -> list[str]:
    """``globals_session`` 那一格的逐枚点名：改一枚值也得点名是谁（判据②的人话样例）。"""
    problems = []
    for name, value in globals_session_values(now["session"], payload["names"]):
        recorded = payload["session"].get(name)
        label = f"globals_session[{name}]: 生产={recorded!r} 恢复={value!r}"
        if recorded is None or value is None:
            problems.append("globals 读数取不到：" + label + "（对账缺项即红，沉默不是通过）")
        elif recorded in ("", "MISSING"):
            problems.append("源库上它本来就没声明：" + label + "——备份配不出可信的施加件")
        elif value in ("", "MISSING"):
            problems.append("恢复库里它是 MISSING：" + label
                            + "。向量一枚不少、备份日志全绿，读腿维度仍是错的——R587 拆的就是这枚假绿")
        elif str(recorded) != str(value):
            problems.append("恢复库与源库不等：" + label)
    return problems


def reconcile_globals(database_url: str, payload: dict, *, psql_path: str = "psql") -> dict:
    """判据②：globals 两格进门控逐枚等，``globals_deferred`` 与 ``cluster_roles`` 只上报。

    施加那一步刚跑完就来现读现证。两侧算的是同一枚 ``globals_profile`` /
    ``globals_session`` 串（同一个 builder、同一把不带库名的钥匙），再叠一层逐枚点名，
    这样一枚值被改也不会只剩「两串不等」那种没法查的读数。
    """
    now = collect_globals(database_url, psql_path=psql_path)
    problems: list[str] = []
    items: dict[str, dict[str, str]] = {}
    for name, recorded, current in (
        ("globals_profile", payload["profile"], now["profile"]),
        ("globals_session", payload["session_profile"], now["session_profile"]),
    ):
        items[name] = {"recorded": str(recorded), "restored": str(current)}
        if str(recorded) != str(current):
            problems.append(f"{name}: 备份={str(recorded)!r} 恢复库={str(current)!r}")
    problems.extend(globals_profile_problems(payload, now))
    problems.extend(globals_session_problems(payload, now))
    extras = {
        "globals_deferred": {"recorded": str(payload.get("deferred_profile") or "NONE"),
                             "restored": now["deferred_profile"]},
        #: 成对产物按设计不带角色清单（带了就是往备份件里抄 SCRAM 散列那一族），所以
        #: 这一格只有恢复库的现读，没有源侧记录，也绝不进门控。
        "cluster_roles": {"recorded": None,
                          "restored": _read_one(database_url, CLUSTER_ROLES_SQL,
                                                psql_path=psql_path, label="cluster roles")},
    }
    return {"items": items, "extras": extras, "problems": problems,
            "gated": list(RECON_ITEMS), "reported": list(EXTRA_ITEMS),
            "database": now["database"]}


def restore_backup_with_globals(
    archive: str | Path,
    database_url: str,
    *,
    pg_restore_path: str = "pg_restore",
    psql_path: str = "psql",
) -> dict:
    """出厂恢复工序的完整顺序（判据①②）：读成对产物 → ``pg_restore`` → 施加 → 对账。

    成对产物**先读再进库**：一份没有配对 globals 的归档不该把恢复跑到一半才告出来，而
    ``--list`` 那条只读目录的路径本来就不进库，保持原样。施加一定落在 ``pg_restore`` 之后、
    任何对账之前：``pg_restore`` 重建得出对象，重建不出 ``pg_db_role_setting`` 的行，而任何
    对账比的都是施加之后的现读值。
    """
    payload = read_globals_pair(archive)
    database_name = restore_database(archive, database_url, pg_restore_path=pg_restore_path)
    applied = apply_globals(database_url, payload, psql_path=psql_path)
    report = reconcile_globals(database_url, payload, psql_path=psql_path)
    if report["problems"]:
        raise MismatchError(report["problems"])
    return {"database": database_name, "applied": applied, "reconcile": report,
            "items": report["items"], "extras": report["extras"],
            "problems": report["problems"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore an Enterprise Brain PostgreSQL backup.")
    parser.add_argument("archive")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--pg-restore", default="pg_restore")
    parser.add_argument(
        "--psql",
        default="psql",
        dest="psql_path",
        help="psql used to re-apply and reconcile the database-level settings pg_dump cannot "
             "carry; the production image installs postgresql-client-17 for it",
    )
    parser.add_argument("--list", action="store_true", dest="list_only")
    args = parser.parse_args(argv)

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    try:
        if args.list_only:
            entries = list_backup(args.archive, pg_restore_path=args.pg_restore)
            print(f"entries={len(entries)}")
            return 0
        database_url = (args.database_url or os.getenv("DATABASE_URL") or "").strip()
        if not database_url:
            print("DATABASE_URL is required", file=sys.stderr)
            return 2
        result = restore_backup_with_globals(
            args.archive, database_url, pg_restore_path=args.pg_restore,
            psql_path=args.psql_path,
        )
    except RefuseError as exc:
        print(f"database restore refused: {exc}", file=sys.stderr)
        return 2
    except MismatchError as exc:
        print("database restore reconciled unequal:", file=sys.stderr)
        for problem in exc.problems:
            print("  " + problem, file=sys.stderr)
        return 3
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"database restore failed: {exc}", file=sys.stderr)
        return 1
    print(f"restored={result['database']}")
    print(f"globals_applied={result['applied']['applied']} "
          f"globals_deferred={result['applied']['deferred']}")
    for name in RECON_ITEMS:
        item = result["items"][name]
        print(f"reconcile {name}: 备份={item['recorded']} 恢复库={item['restored']} 等=True")
    for name in EXTRA_ITEMS:
        print(f"reported {name}（只上报，不当对账项）: {result['extras'][name]['restored']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())