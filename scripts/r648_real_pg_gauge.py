#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""R648 · R46 判据① 从「离线形状」升到「真库读数」的量具（出厂默认一枚库都不连）。

## 本件量的是哪一格欠账

R46 的代码三棒全部在树（R152 回填 + R195 消费 + R153 强度校准），判据① 却只证到**离线形状**：
``app/rag/retriever.py::activity_priors`` 与 ``rank_hits_by_activity`` 的读回与界，历史上全部打在
假 ``row_reader`` 上；在册 R525 把真库那一格量成了「0 行 ⇒ 无可读」。⇒ **真 PG 上的并发打点与
真检索次序，从立案到今天一次都没量过**。本件补的就是这两条腿。

## 连库姿势（本机的真坑：宿主 5432 上是一枚野 PG）

现量到的事实（``leg_identity`` 每次复跑都会重新交回，不靠纸上的话）：

* 部署容器 ``enterprise-brain-postgres-1`` 的 ``HostConfig.PortBindings`` 是 ``{}`` ⇒ 容器 PG
  没有发布宿主端口，从宿主 psycopg 直连 5432 永远打不到它。
* 宿主 5432 由一枚原生 ``postgres`` 进程监听（R525 记作面 B「野 PG」，它连 ``schema_migrations``
  都没有）⇒ 拿它当真库得到的是一枚假绿。
* ⇒ 本件唯一的真连接通道是 ``docker exec ... psql``，且一律带 ``-h 127.0.0.1 -p 5432`` 走 TCP，
  好让 ``inet_server_addr()`` / ``inet_server_port()`` 交回**非 NULL** 的读数（容器内 unix socket
  姿势那两枚恒 NULL，本件两种姿势都量了，差异写在读数里）。
* 一枚 ``docker exec ... psql`` = 一枚真后端连接（``pg_backend_pid()`` 逐枚点名），所以「至少两枚
  真连接同时打点」在这里是可数的：并发波次期间另有第三枚连接现读 ``pg_stat_activity`` 记账。

## 闸门（出厂默认关，且关掉时不许把未量到扮成绿）

``R648_REAL_PG=on``（``on`` / ``1`` / ``true`` / ``yes``）才连库。关着时每一格交回
``{"status": "unmeasured", "reason_code": "r648_real_pg_opt_in_not_declared"}``。
没有 ``skip``、没有 ``xfail``、没有「没设 env 就当通过」；未量到的格子里压根没有测量键，
所以伪 0 无从出现（``walk_measurement_keys`` 就是用来证明这一格的）。

## 写域（跑完当场清账）

只打沙盒库 ``eb_r59_sandbox`` 的 ``document_activity_signals`` 一张表，只写 ``r648_`` 前缀的假
filename，跑完 ``DELETE`` 并交回「行数回到原值」的读数。生产库名在 ``assert_sandbox_database``
当场拒绝；每条写脚本再过 ``assert_write_script_allowed`` 那道闸。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(os.environ.get("R648_REPO") or Path(__file__).resolve().parents[1]).resolve()

#: 以脚本方式直接跑时，sys.path 里只有 scripts/，产品模块 import 不到：这里把仓根补上
#: （影子端把 R648_REPO 指回真仓，与 R545 那套「影子模块的 ROOT 指回真仓」同一口径）。
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: 真次序腿的三档腿宽（派工词点名 5 / 12 / 40 各测一次；与 R525 在册同一组数）。
LEG_WIDTHS = (5, 12, 40)

#: R153 定下的那根界：本单只量它成不成立，一个字不许改、不许重新校准。
#: 🔴 这枚数是**钉在这里**的，不从被量的模块里读——否则「把界的分母换成腿宽」那种刀
#: 会把界一起改掉，读数就永远成立（K2 咬的正是这一格）。
R153_BOOKED_MAX_SHIFT_RANKS = 1

# ==================== 闸门 ====================

#: 具名 opt-in（合格先例 = R602_REAL_PG / R525_REAL_STORE）：出厂默认关。
OPT_IN_ENV = "R648_REAL_PG"
OPT_IN_ON_VALUES = frozenset({"on", "1", "true", "yes"})

#: 未量到的原因码：只准这一枚，别在纸里换成「大概是没设 env」。
REASON_GATE_OFF = "r648_real_pg_opt_in_not_declared"

#: 未量到的格子里**不许出现**的测量键（判据⑤的机器形状：伪 0 只会从这些键里钻进来）。
MEASUREMENT_KEYS = frozenset({
    "rows", "row_count", "count", "accepted", "rejected", "accepted_count", "rejected_count",
    "expected", "observed", "lost_updates", "missing", "max_abs_places_moved",
    "carriers_shifted", "concurrent_backends", "rc", "sessions", "statements", "shifts",
})


class GaugeRefused(RuntimeError):
    """闸门 / 写域拒绝：带原因码抛出，读数里能点名。"""

    def __init__(self, message, *, reason_code):
        super().__init__(message)
        self.reason_code = reason_code


def gate_declared(env=None) -> bool:
    """唯一一道闸：只有显式写了 opt-in 才放行连库。"""
    source = os.environ if env is None else env
    raw = str(source.get(OPT_IN_ENV, "") or "").strip().lower()
    return raw in OPT_IN_ON_VALUES


def require_opt_in(env=None) -> None:
    if not gate_declared(env):
        raise GaugeRefused(
            "R648 量具默认不连库：设 " + OPT_IN_ENV + "=on 才开真腿",
            reason_code=REASON_GATE_OFF,
        )


def unmeasured(*, note) -> dict:
    """未量到那一格的出厂形状：状态 + 原因码 + 一句话，一个测量键都没有。"""
    return {"status": "unmeasured", "reason_code": REASON_GATE_OFF, "note": note}


def walk_measurement_keys(node, *, path="report") -> list:
    """把产物里所有测量键的位置找出来（判据⑤用它证明未量到的格子里没有伪 0）。"""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = path + "." + str(key)
            if key in MEASUREMENT_KEYS:
                found.append(here)
            found.extend(walk_measurement_keys(value, path=here))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(walk_measurement_keys(value, path=path + "[" + str(index) + "]"))
    return found


# ==================== 连库口径（在册件现取，一律不自己编） ====================

#: 容器 / 用户 / 库名的出处逐枚点名：``scripts/r525_activity_prior_readout.py``（容器与 psql 姿势）、
#: ``scripts/r382_matched_corpus.py`` 的 ``SANDBOX_DB``、
#: ``scripts/r633_dual_write_off_precondition.py`` 的 ``SANDBOX_DATABASES`` 与沙盒库名形状。
CONTAINER = "enterprise-brain-postgres-1"
PG_USER = "enterprise_brain"
PG_HOST = "127.0.0.1"
PG_PORT = "5432"
SANDBOX_DB = "eb_r59_sandbox"

#: 生产库名：一字节都不许打。出处 = ``deploy/.env.server`` 的 ``POSTGRES_DB`` 与镜像默认库。
PRODUCTION_DB_NAMES = frozenset({"enterprise_brain", "postgres", "template0", "template1"})

#: 与 r633 同一枚形状（那一族的名字口径以在册件为准，不在这里另立一套）。
SANDBOX_DATABASE_SHAPE = re.compile(r"^eb_r\w*_(sandbox|drill)\Z")

#: 本单唯一允许的写点：假 filename 的形状（r648_ 前缀 + 在册语料那一族的后缀）。
FAKE_FILENAME_SHAPE = re.compile(r"^r648_[a-z][a-z0-9_]{0,40}\.(md|txt|pdf)\Z")
FAKE_LIKE_PATTERN = "r648\\_%"
#: 词表里**没有** do：产品那条 UPSERT 自带 ON CONFLICT ... DO UPDATE SET，把 do 当禁词会把
#: 被测语句本身拦在门外（本件第一枚正控就是这条语句必须过闸）。
_WRITE_FORBIDDEN_WORDS = ("merge", "create", "alter", "drop", "truncate", "grant",
                          "revoke", "copy", "vacuum", "reindex", "cluster", "refresh", "call",
                          "prepare", "deallocate", "lock", "notify", "listen")
_WRITE_STATEMENT_HEADS = ("insert", "update", "delete")
_IDENTIFIER_STOPWORDS = frozenset({"set", "where", "values", "as", "select", "conflict", "on",
                                   "filename", "accepted_count", "rejected_count"})
_READ_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|create|alter|drop|truncate|grant|revoke|copy|vacuum|"
    r"reindex|cluster|refresh|call|do|prepare|deallocate|lock|notify|listen)\b",
    re.IGNORECASE,
)
_READ_ALLOWED_HEADS = ("select", "with", "show", "set", "begin", "commit", "rollback")


def assert_sandbox_database(name) -> str:
    """只准打沙盒库那一族；生产库名当场拒绝（原因码可点名）。"""
    text = str(name or "")
    if text in PRODUCTION_DB_NAMES:
        raise GaugeRefused("生产库名 " + text + " 一字节不许打",
                           reason_code="production_database_refused")
    if not SANDBOX_DATABASE_SHAPE.match(text):
        raise GaugeRefused("库名 " + text + " 不在沙盒那一族（形状 "
                           + SANDBOX_DATABASE_SHAPE.pattern + "）",
                           reason_code="database_not_in_sandbox_family")
    return text


def assert_fake_filename(name) -> str:
    text = str(name or "")
    if not FAKE_FILENAME_SHAPE.match(text):
        raise GaugeRefused("写入用的 filename 必须是 r648_ 前缀的假名，拿到 " + repr(text),
                           reason_code="filename_not_r648_fake")
    return text


def assert_select_only(sql) -> str:
    """只读取证那道闸（与 R525 量具同口径）：非只读语句或命中禁词都抛。"""
    text = str(sql).strip().rstrip(";").strip()
    head = text.split(None, 1)[0].lower() if text else ""
    if head not in _READ_ALLOWED_HEADS:
        raise GaugeRefused("R648 只读取证：非只读语句 " + text[:80],
                           reason_code="read_gate_statement")
    hit = _READ_FORBIDDEN.search(text)
    if hit:
        raise GaugeRefused("R648 只读取证：语句命中禁词 " + hit.group(0) + " => " + text[:80],
                           reason_code="read_gate_forbidden_word")
    return text


def assert_write_script_allowed(script) -> str:
    """写腿唯一的闸：禁词清单外一律不许出现、只准碰 0011 那一张表、只准用 r648_ 假名。

    这枚函数是「写域」的机器证明：常驻件把它当纯函数跑（不连库），所以本单的写域
    不需要真打一次库才成立；真腿每次落库前也逐枚过这道闸。
    """
    body = str(script or "")
    lowered = body.lower()
    heads = tuple(re.findall(r"^\s*(insert|update|delete)\b", lowered, flags=re.MULTILINE))
    if not heads:
        for verb in _WRITE_STATEMENT_HEADS:
            if re.search(r"\b" + verb + r"\b", lowered):
                heads = (verb,)
                break
    for verb in heads:
        if verb not in _WRITE_STATEMENT_HEADS:
            raise GaugeRefused("写腿语句头不认识：" + verb, reason_code="write_gate_statement_head")
    for verb in _WRITE_FORBIDDEN_WORDS:
        if verb in _WRITE_STATEMENT_HEADS:
            continue
        if re.search(r"\b" + verb + r"\b", lowered):
            raise GaugeRefused("写腿禁词 " + verb, reason_code="write_gate_forbidden_word")
    tables = set(re.findall(r"\b(?:from|into|update)\s+([a-z_][a-z0-9_.]*)", lowered))
    tables = {item.split(".")[-1] for item in tables} - _IDENTIFIER_STOPWORDS
    tables.discard("document_activity_signals")
    if tables:
        raise GaugeRefused("写腿里出现了别的表：" + ", ".join(sorted(tables)),
                           reason_code="write_gate_other_table")
    for literal in re.findall(r"'([^']*)'", body):
        if literal.startswith("r648") and "%" not in literal:
            assert_fake_filename(literal)
    if "r648" not in lowered:
        raise GaugeRefused("写腿里一个 r648_ 假名都没有：不给打点",
                           reason_code="write_gate_no_fake_name")
    return body

# ==================== 传输（本件唯一一处子进程出口） ====================

_COMMAND_LOG: list = []


def command_of(argv) -> str:
    """命令原文在这里生成，不在纸里手抄第二份。"""
    out = []
    for item in argv:
        text = str(item)
        out.append('"' + text.replace('"', '""') + '"' if re.search(r"[\s;|'`]", text) else text)
    return " ".join(out)


def docker_exec(argv, *, stdin_text=None, timeout=240, leg="read"):
    """闸门关着时没有任何路径能走到这里（K3 咬的就是这一格）。"""
    proc = subprocess.run(
        list(argv),
        input=(stdin_text.encode("utf-8") if stdin_text is not None else b""),
        capture_output=True,
        timeout=timeout,
    )
    stderr = proc.stderr.decode("utf-8", "replace").strip()
    record = {"leg": leg, "command": command_of(argv), "rc": int(proc.returncode),
              "stderr": stderr[:600]}
    _COMMAND_LOG.append(record)
    return {"rc": int(proc.returncode), "stdout": proc.stdout.decode("utf-8", "replace"),
            "stderr": stderr, "command": record["command"]}


def psql_argv(*, database=SANDBOX_DB, over_tcp=True, script=False) -> list:
    assert_sandbox_database(database)
    argv = ["docker", "exec", "-i", CONTAINER, "psql"]
    if over_tcp:
        argv += ["-h", PG_HOST, "-p", PG_PORT]
    argv += ["-U", PG_USER, "-d", database, "-At", "-v", "ON_ERROR_STOP=1"]
    argv += ["-f", "-"] if script else ["-c"]
    return argv


def psql_read(sql, *, database=SANDBOX_DB, leg="read", over_tcp=True) -> list:
    """发一条只读语句，交回数据行（psql 回显的 SET 不是数据，剔掉）。"""
    argv = psql_argv(database=database, over_tcp=over_tcp) + [assert_select_only(sql)]
    proc = docker_exec(argv, leg=leg, timeout=120)
    if proc["rc"] != 0:
        raise RuntimeError("psql 读数失败 rc=" + str(proc["rc"]) + ": " + proc["stderr"])
    return [line for line in proc["stdout"].splitlines()
            if line.strip() and line.strip() != "SET"]


def psql_scalar(sql, **kwargs) -> str:
    rows = psql_read(sql, **kwargs)
    return rows[0].strip() if rows else ""


def psql_values(sql, **kwargs) -> list:
    return [line.split("|") for line in psql_read(sql, **kwargs)]


def psql_json(inner_sql, **kwargs) -> list:
    """逐行 ``row_to_json``：正文里的换行由 JSON 转义，打断不了行协议（与 R525 同一形状）。"""
    wrapped = "SELECT row_to_json(t) FROM (" + assert_select_only(inner_sql) + ") t"
    return [json.loads(line) for line in psql_read(wrapped, **kwargs) if line.strip()]


def assert_read_script_allowed(script) -> str:
    """多语句只读脚本逐条过只读闸：一条脚本里混进写语句就当场抛（名次腿走的就是这一道）。"""
    parts = [part for part in str(script or "").split(";") if part.strip()]
    if not parts:
        raise GaugeRefused("空脚本", reason_code="read_script_empty")
    for part in parts:
        assert_select_only(part)
    return str(script)


def psql_write(script, *, database=SANDBOX_DB, leg="write", timeout=240) -> dict:
    assert_write_script_allowed(script)
    return docker_exec(psql_argv(database=database, script=True), stdin_text=script,
                       leg=leg, timeout=timeout)


# ==================== 口径只有一个：从产品源码现读 ====================

def _module_top_level_constant(path, name):
    tree = ast.parse(Path(path).read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise KeyError(Path(path).name + " 里找不到顶层常量 " + name)


def product_upsert_sql() -> str:
    """打点语句 = 产品写路径那条 UPSERT 原文（``app/api/v1/feedback.py::_UPSERT_SQL``）。"""
    return _module_top_level_constant(REPO / "app" / "api" / "v1" / "feedback.py", "_UPSERT_SQL")


def product_signal_select() -> str:
    """读回语句 = 产品读腿那条 SELECT 原文（AST 现读，不重抄第二份；口径同 R525 量具）。"""
    source = (REPO / "app" / "rag" / "retriever.py").read_text(encoding="utf-8-sig")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "execute":
            for arg in node.args:
                if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                        and "document_activity_signals" in arg.value
                        and arg.value.strip().lower().startswith("select")):
                    return " ".join(arg.value.split())
    raise KeyError("retriever 里找不到那条读回 SELECT")

def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def render_statement(sql, params) -> str:
    """把产品语句里的 ``%s`` 按序换成字面量（psql 没有参数位，只有文本）。"""
    parts = str(sql).split("%s")
    values = list(params)
    if len(parts) - 1 != len(values):
        raise GaugeRefused("占位符与参数枚数不等：" + str(len(parts) - 1) + " vs "
                           + str(len(values)), reason_code="render_placeholder_mismatch")
    out = []
    for index, part in enumerate(parts):
        out.append(part)
        if index < len(values):
            out.append(sql_literal(values[index]))
    return " ".join("".join(out).split())


def upsert_statement(filename, accepted, rejected) -> str:
    """打点用的语句 = 产品那条 UPSERT 原文渲染成字面量形式（一个字节都不自己编）。"""
    assert_fake_filename(filename)
    return render_statement(product_upsert_sql(), (filename, int(accepted), int(rejected))) + ";"


def product_upsert_touches_first_signal_at() -> bool:
    """静态一格真读数：产品那条 UPSERT 的 ``DO UPDATE SET`` 子句里到底有没有 first_signal_at。"""
    parts = product_upsert_sql().split("DO UPDATE SET", 1)
    if len(parts) != 2:
        raise GaugeRefused("产品 UPSERT 里没有 DO UPDATE SET 子句", reason_code="upsert_shape_changed")
    return "first_signal_at" in parts[1]


def read_then_write_script(filename, accepted_delta, rejected_delta, *, read_sleep=0.0,
                           write_sleep=0.7) -> str:
    r"""反证刀 K1 的那一枚形状：客户端先 SELECT、睡一段、再 UPDATE 回去（读后写）。

    🔴 这**不是**本单的被测物，是给并发腿准备的对照形状：两枚真连接按 ``read_sleep`` 错开
    起跑、都在对方提交之前读到同一个基数 ⇒ 必现丢更新。并发腿若抓不到它，那枚「零丢更新」
    就是假的。基数走 psql 的 ``\gset`` 落在**客户端**，所以陈旧读是客户端手里的陈旧读，
    与产品那条单语句 UPSERT（服务端原子相加，基数由服务端自己读）正好互为对照。
    """
    assert_fake_filename(filename)
    quoted = sql_literal(filename)
    return (
        "BEGIN;\n"
        "SELECT accepted_count AS base_a, rejected_count AS base_b FROM document_activity_signals"
        " WHERE filename = " + quoted + " \\gset\n"
        "SELECT pg_backend_pid() || ' read ' || :base_a || ' ' || :base_b;\n"
        + ("SELECT pg_sleep(" + str(float(read_sleep)) + ");\n" if read_sleep else "")
        + "SELECT pg_sleep(" + str(float(write_sleep)) + ");\n"
        "UPDATE document_activity_signals SET accepted_count = :base_a + "
        + str(int(accepted_delta)) + ", rejected_count = :base_b + " + str(int(rejected_delta))
        + ", last_signal_at = NOW() WHERE filename = " + quoted + ";\n"
        "COMMIT;\n"
    )


def upsert_session_script(filename, statements, *, align=0.2, gap=0.0) -> str:
    """一枚真连接的波次脚本：先报自己的 backend pid，再连打 N 枚产品 UPSERT。"""
    lines = ["SELECT pg_backend_pid();"]
    if align:
        lines.append("SELECT pg_sleep(" + str(float(align)) + ");")
    for accepted, rejected in statements:
        lines.append(upsert_statement(filename, accepted, rejected))
        if gap:
            lines.append("SELECT pg_sleep(" + str(float(gap)) + ");")
    lines.append("SELECT 'tail';")
    return "\n".join(lines) + "\n"


def run_sessions(scripts, *, database=SANDBOX_DB, leg="concurrency", observer_sql=None,
                 observe_after=0.6, timeout=240) -> dict:
    """把 N 枚脚本同时投进 N 枚真连接；波次中途现读一次 ``pg_stat_activity``。"""
    results = [None] * len(scripts)
    observed = {}

    def worker(index, script):
        results[index] = psql_write(script, database=database, leg=leg + "_s" + str(index),
                                    timeout=timeout)

    def observer():
        time.sleep(observe_after)
        try:
            observed["count"] = psql_scalar(observer_sql, database=database, leg=leg + "_observe")
        except Exception as exc:
            observed["error"] = type(exc).__name__ + ": " + str(exc)[:200]

    threads = [threading.Thread(target=worker, args=(index, script))
               for index, script in enumerate(scripts)]
    watch = (threading.Thread(target=observer) if observer_sql else None)
    started = time.time()
    for thread in threads:
        thread.start()
    if watch is not None:
        watch.start()
    for thread in threads:
        thread.join()
    if watch is not None:
        watch.join()
    return {"sessions": len(scripts), "results": results,
            "observer_backends": observed.get("count", ""),
            "observer_error": observed.get("error", ""),
            "wall_seconds": round(time.time() - started, 3)}

# ==================== 读数辅助 ====================

#: 波次进行中现读「同一刻有几枚真后端在打同一张表」。
OBSERVER_SQL = (
    "SELECT count(*)::text FROM pg_stat_activity WHERE datname = " + sql_literal(SANDBOX_DB)
    + " AND backend_type = 'client backend' AND pid <> pg_backend_pid()"
    " AND state <> 'idle'"
)
COLUMNS = ("accepted_count", "rejected_count")


def read_signal_row(filename, *, database=SANDBOX_DB) -> dict:
    """现读一行（走产品那条 SELECT 的列口径，只是加了点查条件）。"""
    assert_fake_filename(filename)
    sql = ("SELECT filename, accepted_count, rejected_count,"
           " first_signal_at, last_signal_at FROM document_activity_signals"
           " WHERE filename = " + sql_literal(filename))
    rows = psql_json(sql, database=database, leg="readback")
    return rows[0] if rows else {}


def count_r648_rows(*, database=SANDBOX_DB) -> int:
    return int(psql_scalar("SELECT count(*)::text FROM document_activity_signals"
                           " WHERE filename LIKE " + sql_literal(FAKE_LIKE_PATTERN),
                           database=database, leg="count"))


def reset_fake_rows(*names, database=SANDBOX_DB) -> dict:
    """把本单要用的假名先清一遍：复跑的读数才与首跑同尺（只碰 r648_ 假名这一格）。"""
    statements = ["DELETE FROM document_activity_signals WHERE filename = "
                  + sql_literal(assert_fake_filename(name)) + ";" for name in names]
    done = psql_write("\n".join(statements) + "\n", database=database, leg="reset_rows")
    return {"rc": int(done["rc"]), "names": len(statements)}


def lost_updates(expected, observed) -> list:
    """把「该有多少」与「库里现读到多少」逐列对平，点名丢了哪一枚（判据①① 的机器形状）。"""
    out = []
    for column in COLUMNS:
        want = int((expected or {}).get(column, 0))
        got = int((observed or {}).get(column, 0))
        if want != got:
            out.append({"column": column, "expected": want, "observed": got,
                        "missing": want - got})
    return out


def parse_backend_pids(results) -> list:
    """逐枚点名每根连接自己的 ``pg_backend_pid()``：两枚真连接不是嘴上说的。"""
    pids = []
    for item in results or []:
        for line in str((item or {}).get("stdout", "")).splitlines():
            text = line.strip()
            if text.isdigit():
                pids.append(text)
                break
    return pids


def parse_read_pairs(results) -> list:
    """读后写形状里每根连接**自己报的**基数（``PID read a b``），陈旧读的凭据。"""
    out = []
    for item in results or []:
        for line in str((item or {}).get("stdout", "")).splitlines():
            match = re.match(r"^(\d+)\s+read\s+(\d+)\s+(\d+)$", line.strip())
            if match:
                out.append({"pid": match.group(1), "base_a": int(match.group(2)),
                            "base_b": int(match.group(3))})
                break
    return out


# ==================== 腿一：打的是哪台 PG（身份自证） ====================

def leg_identity(*, database=SANDBOX_DB) -> dict:
    tcp = psql_json(
        "SELECT current_database() AS database, inet_server_addr()::text AS inet_addr,"
        " inet_server_port()::text AS inet_port,"
        " current_setting('server_version') AS server_version,"
        " current_setting('data_directory') AS data_directory,"
        " pg_postmaster_start_time()::text AS postmaster_start,"
        " pg_backend_pid()::text AS backend_pid",
        database=database, leg="identity_tcp")
    sock = psql_json(
        "SELECT current_database() AS database, coalesce(inet_server_addr()::text,'NULL')"
        " AS inet_addr, coalesce(inet_server_port()::text,'NULL') AS inet_port,"
        " pg_backend_pid()::text AS backend_pid",
        database=database, leg="identity_socket", over_tcp=False)
    show = psql_scalar("SHOW server_version", database=database, leg="identity_show")
    ports = docker_exec(["docker", "inspect", CONTAINER, "--format",
                         "{{json .HostConfig.PortBindings}}"], leg="identity_ports", timeout=60)
    listed = psql_values("SELECT datname FROM pg_database ORDER BY 1", database=database,
                         leg="identity_databases")
    binding = (ports["stdout"] or "").strip()
    return {
        "status": "measured",
        "over_tcp": tcp[0] if tcp else {},
        "over_unix_socket": sock[0] if sock else {},
        "show_server_version": show,
        "container_port_bindings": binding,
        "container_publishes_host_port": binding not in ("", "{}", "null"),
        "databases_on_this_server": [row[0] for row in listed],
        "database_is_sandbox_family": bool(SANDBOX_DATABASE_SHAPE.match(str(database))),
        "production_names_present": sorted(
            {row[0] for row in listed} & set(PRODUCTION_DB_NAMES)),
    }


# ==================== 腿二：真库并发打点（UPSERT 形状 ⇒ 零丢更新） ====================

def leg_concurrency(*, filename="r648_concurrency_primary.md", sessions=8, statements=10,
                    align=0.3, database=SANDBOX_DB) -> dict:
    assert_fake_filename(filename)
    reset_fake_rows(filename, database=database)
    base = read_signal_row(filename, database=database)
    scripts = [upsert_session_script(filename, [(1, 1)] * statements, align=align)
                for _ in range(int(sessions))]
    wave = run_sessions(scripts, database=database, leg="concurrency",
                        observer_sql=OBSERVER_SQL, observe_after=align * 0.6)
    row = read_signal_row(filename, database=database)
    expected = {"accepted_count": int(base.get("accepted_count", 0)) + sessions * statements,
                "rejected_count": int(base.get("rejected_count", 0)) + sessions * statements}
    mismatches = lost_updates(expected, row)
    row_count = int(psql_scalar("SELECT count(*)::text FROM document_activity_signals"
                                " WHERE filename = " + sql_literal(filename),
                                database=database, leg="concurrency_rows"))
    return {
        "status": "measured",
        "shape": "product_upsert_single_statement",
        "filename": filename,
        "rows_before_wave": {column: int(base.get(column, 0)) for column in COLUMNS},
        "sessions": int(sessions),
        "statements_per_session": int(statements),
        "backend_pids": parse_backend_pids(wave["results"]),
        "concurrent_backends": int(wave["observer_backends"] or 0),
        "observer_error": wave["observer_error"],
        "wall_seconds": wave["wall_seconds"],
        "expected": expected,
        "observed": {column: int(row.get(column, 0)) for column in COLUMNS},
        "lost_updates": mismatches,
        "row_count": row_count,
        "exact_no_lost_update": not mismatches,
        "one_row_not_more_not_less": row_count == 1,
        "session_rc": [int((item or {}).get("rc", -1)) for item in wave["results"]],
    }
#: 读后写对照那两枚席位：各打一列，谁被覆盖就能按列点名。
RMW_SESSIONS = ({"id": "S_A", "accepted": 1, "rejected": 0, "read_sleep": 0.0},
                {"id": "S_B", "accepted": 0, "rejected": 1, "read_sleep": 0.4})


def leg_read_then_write_control(*, filename="r648_control_read_then_write.md", write_sleep=0.9,
                                database=SANDBOX_DB) -> dict:
    """把产品那条单语句 UPSERT 换成「客户端先 SELECT 再 UPDATE」——并发腿必须抓到丢更新。

    这枚是 **K1 的正反两面**：形状本身不是被测物，被测的是本件有没有能力把它量红。
    两枚真连接按 ``read_sleep`` 错开、都在对方提交之前读到同一个基数 ⇒ 必丢一枚。
    """
    assert_fake_filename(filename)
    reset_fake_rows(filename, database=database)
    seed = psql_write(upsert_session_script(filename, [(1, 0)], align=0.0),
                      database=database, leg="rmw_seed")
    base = read_signal_row(filename, database=database)
    scripts = [read_then_write_script(filename, item["accepted"], item["rejected"],
                                      read_sleep=item["read_sleep"], write_sleep=write_sleep)
               for item in RMW_SESSIONS]
    wave = run_sessions(scripts, database=database, leg="rmw", observer_sql=OBSERVER_SQL,
                        observe_after=0.2, timeout=120)
    after = read_signal_row(filename, database=database)
    base_a, base_b = int(base.get("accepted_count", 0)), int(base.get("rejected_count", 0))
    expected = {"accepted_count": base_a + 1, "rejected_count": base_b + 1}
    mismatches = lost_updates(expected, after)
    reads = parse_read_pairs(wave["results"])
    stale = bool(reads) and all(item["base_a"] == base_a and item["base_b"] == base_b
                                for item in reads)
    landed = {"accepted_count": int(after.get("accepted_count", 0)) - base_a,
              "rejected_count": int(after.get("rejected_count", 0)) - base_b}
    owner = {"accepted_count": RMW_SESSIONS[0], "rejected_count": RMW_SESSIONS[1]}
    pids = {item["id"]: (reads[index]["pid"] if index < len(reads) else "")
            for index, item in enumerate(RMW_SESSIONS)}
    victims = []
    for mismatch in mismatches:
        column = mismatch["column"]
        loser = owner.get(column) or {}
        winner = [item for item in RMW_SESSIONS if item is not loser]
        victims.append({
            "lost_column": column,
            "missing": mismatch["missing"],
            "expected_landed": 1,
            "actually_landed": landed.get(column),
            "victim_session": loser.get("id", ""),
            "victim_pid": pids.get(loser.get("id", ""), ""),
            "overwritten_by_session": winner[0]["id"] if winner else "",
            "overwritten_by_pid": pids.get(winner[0]["id"], "") if winner else "",
            "landed_readings": landed,
        })
    return {
        "status": "measured",
        "shape": "client_read_then_write",
        "filename": filename,
        "seed_rc": int(seed["rc"]),
        "base": {"accepted_count": base_a, "rejected_count": base_b},
        "expected": expected,
        "observed": {column: int(after.get(column, 0)) for column in COLUMNS},
        "lost_updates": mismatches,
        "victims_named": victims,
        "session_reads": reads,
        "backend_pids_by_session": pids,
        "both_sessions_read_the_same_base": stale,
        "concurrent_backends": int(wave["observer_backends"] or 0),
        "backend_pids": parse_backend_pids(wave["results"]),
        "session_rc": [int((item or {}).get("rc", -1)) for item in wave["results"]],
    }


def real_signal_reader(database=SANDBOX_DB):
    """产品那条 SELECT 的原文 + 真库往返：返回 ``(filename, accepted, rejected)`` 三元组。"""
    sql = product_signal_select()

    def read():
        rows = psql_values(sql + "", database=database, leg="product_select")
        return [tuple(row) for row in rows if row]

    return read


def fold_rows_to_priors(rows) -> dict:
    """行折成先验字典的口径只有一个：交给产品自己的 ``activity_priors`` 去折。"""
    from app.rag.retriever import activity_priors, reset_activity_priors

    reset_activity_priors()
    try:
        return activity_priors(row_reader=lambda: list(rows))
    finally:
        reset_activity_priors()


def leg_mixed_columns(*, filename="r648_mixed_columns.md", unmarked="r648_never_marked.md",
                      rounds=6, sessions=4, database=SANDBOX_DB) -> dict:
    """采纳与驳回各若干混排：两列不许被做成一枚净值（迁移注释那句「0/0 与 5/5 是两件事」）。

    四枚真连接同时打同一枚 filename：偶数席位只打采纳、奇数席位只打驳回，所以**净值恰好为
    0** 而两列都必须是非零整数——净值一列的方案在这里会直接吐出一个假 0。
    """
    assert_fake_filename(filename)
    assert_fake_filename(unmarked)
    reset_fake_rows(filename, unmarked, database=database)
    scripts = []
    for index in range(int(sessions)):
        delta = (1, 0) if index % 2 == 0 else (0, 1)
        scripts.append(upsert_session_script(filename, [delta] * int(rounds), align=0.25))
    wave = run_sessions(scripts, database=database, leg="mixed", observer_sql=OBSERVER_SQL,
                        observe_after=0.15)
    row = read_signal_row(filename, database=database)
    want = sessions // 2 * rounds
    expected = {"accepted_count": want, "rejected_count": want}
    mismatches = lost_updates(expected, row)
    priors = fold_rows_to_priors([list(row_tuple) for row_tuple in real_signal_reader(database)()])
    from app.rag.retriever import activity_prior_value

    marked = priors.get(filename) or {}
    return {
        "status": "measured",
        "filename": filename,
        "unmarked_filename": unmarked,
        "sessions": int(sessions),
        "rounds_per_session": int(rounds),
        "backend_pids": parse_backend_pids(wave["results"]),
        "concurrent_backends": int(wave["observer_backends"] or 0),
        "expected": expected,
        "observed": {column: int(row.get(column, 0)) for column in COLUMNS},
        "lost_updates": mismatches,
        "net_value": int(row.get("accepted_count", 0)) - int(row.get("rejected_count", 0)),
        "both_columns_nonzero": (int(row.get("accepted_count", 0)) > 0
                                 and int(row.get("rejected_count", 0)) > 0),
        "read_back_through_product_reader": {"accepted": int(marked.get("accepted", -1)),
                                             "rejected": int(marked.get("rejected", -1))},
        "unmarked_row_absent_from_priors": unmarked not in priors,
        "prior_value_at_net_zero_and_at_no_signal": {
            "five_five": activity_prior_value({"accepted": want, "rejected": want}),
            "zero_zero": activity_prior_value({"accepted": 0, "rejected": 0}),
            "absent": activity_prior_value(None),
        },
        "session_rc": [int((item or {}).get("rc", -1)) for item in wave["results"]],
    }

# ==================== 腿三：first/last 两枚时间戳的真库行为 ====================

def read_signal_row_millis(filename, *, database=SANDBOX_DB) -> dict:
    """时间戳取回毫秒整数：单调性用字符串比是比不准的（时区与微秒位都会骗人）。"""
    assert_fake_filename(filename)
    rows = psql_json(
        "SELECT filename, accepted_count, rejected_count,"
        " floor(extract(epoch from first_signal_at) * 1000)::bigint AS first_ms,"
        " floor(extract(epoch from last_signal_at) * 1000)::bigint AS last_ms"
        " FROM document_activity_signals WHERE filename = " + sql_literal(filename),
        database=database, leg="timestamps")
    return rows[0] if rows else {}


def leg_timestamps(*, filename="r648_timestamps.md", waves=3, gap=0.35, database=SANDBOX_DB) -> dict:
    assert_fake_filename(filename)
    reset_fake_rows(filename, database=database)
    psql_write(upsert_session_script(filename, [(1, 0)], align=0.0), database=database,
               leg="timestamps_seed")
    snaps = [read_signal_row_millis(filename, database=database)]
    for _ in range(int(waves)):
        time.sleep(gap)
        psql_write(upsert_session_script(filename, [(2, 1)], align=0.0), database=database,
                   leg="timestamps_wave")
        snaps.append(read_signal_row_millis(filename, database=database))
    firsts = [int(item.get("first_ms", 0)) for item in snaps]
    lasts = [int(item.get("last_ms", 0)) for item in snaps]
    return {
        "status": "measured",
        "filename": filename,
        "waves": int(waves) + 1,
        "first_ms_series": firsts,
        "last_ms_series": lasts,
        "first_signal_at_rewritten": len(set(firsts)) > 1,
        "first_signal_at_constant": len(set(firsts)) == 1,
        "last_signal_at_monotonic_non_decreasing": all(
            later >= earlier for earlier, later in zip(lasts, lasts[1:])),
        "last_at_least_first": all(last >= first for last, first in zip(lasts, firsts)),
        "max_backwards_step_ms": max([max(0, earlier - later) for earlier, later
                                      in zip(lasts, lasts[1:])] or [0]),
        "product_upsert_touches_first_signal_at": product_upsert_touches_first_signal_at(),
        "row": {column: int(snaps[-1].get(column, 0)) for column in COLUMNS},
        "expected_row": {"accepted_count": 1 + 2 * int(waves), "rejected_count": int(waves)},
        "lost_updates": lost_updates({"accepted_count": 1 + 2 * int(waves),
                                      "rejected_count": int(waves)}, snaps[-1]),
    }


# ==================== 腿四：表上那几道约束在真库里到底拦不拦 ====================

def booked_0011_constraint_names() -> list:
    """在册 0011 里点名的约束逐枚现读（🔴 不改 ``migrations/**``，只读它的文本）。"""
    text = (REPO / "migrations" / "0011_document_activity_signals.sql").read_text(
        encoding="utf-8-sig")
    return sorted(set(re.findall(r"CONSTRAINT\s+(\w+)", text)))


def leg_constraints(*, zero_probe="r648_probe_zero_zero.md", database=SANDBOX_DB) -> dict:
    assert_fake_filename(zero_probe)
    reset_fake_rows(zero_probe, database=database)
    failed = psql_write(upsert_session_script(zero_probe, [(0, 0)], align=0.0),
                        database=database, leg="constraints_zero_zero")
    inventory = psql_json(
        "SELECT conname, contype, convalidated FROM pg_constraint"
        " WHERE conrelid = 'document_activity_signals'::regclass ORDER BY conname",
        database=database, leg="constraints_inventory")
    row_count = int(psql_scalar("SELECT count(*)::text FROM document_activity_signals"
                                " WHERE filename = " + sql_literal(zero_probe),
                                database=database, leg="constraints_row"))
    booked = booked_0011_constraint_names()
    live = sorted(item["conname"] for item in inventory)
    return {
        "status": "measured",
        "zero_zero_probe_filename": zero_probe,
        "zero_zero_rc": int(failed["rc"]),
        "zero_zero_refused": int(failed["rc"]) != 0,
        "zero_zero_constraint_named_in_stderr":
            "document_activity_signals_not_empty_check" in failed["stderr"],
        "zero_zero_stderr": failed["stderr"][:300],
        "rows_after_refusal": row_count,
        "live_constraints": inventory,
        "booked_constraint_names": booked,
        "booked_names_missing_live": sorted(set(booked) - set(live)),
        "primary_key_count": sum(1 for item in inventory if item["contype"] == "p"),
        "unvalidated_constraints": [item["conname"] for item in inventory
                                    if not item["convalidated"]],
    }

# ==================== 腿五：真库名次 + 真库先验 ⇒ 那条界成不成立 ====================

#: 打点位置（1-based，落在真库 ANN 窗口里）：三档腿宽都要有东西可挪；一枚净值为 0 的样本
#: （5/5）在场，好把「两列不是净值」带到排序腿里；一枚**只有驳回**的样本（0/4）在场，好让
#: 界的负侧也有真读数（R153 那句「正负两侧同一个数」不能只量正的那半边）。
SIGNAL_PLAN = ((2, 3, 0), (7, 1, 0), (13, 0, 2), (20, 5, 5), (31, 2, 0), (10, 0, 4))


class _StatementRecorder:
    """把产品读腿自己那条排名语句**原样录下来**，再交给 psql 跑（口径只有一份）。"""

    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((sql, tuple(params or ())))
        return self

    def fetchall(self):
        return []


def product_ranking_statement(query_vector, k: int):
    """从 ``app/rag/pg_store.py::search_vectors`` 现取排名语句与它同一笔事务里钉的候选宽度。

    🔴 本件不另写一条 ANN 语句：算符、列清单、``LIMIT``、``set_config`` 的写法全都是产品自己
    交回来的，影子端把那枚函数换掉时，本件跟着换（K2/K5 才咬得住）。
    """
    from app.rag import pg_store

    recorder = _StatementRecorder()
    pg_store.search_vectors(connection=recorder, vector_table=pg_store.DEFAULT_VECTOR_TABLE,
                            distance_function=SCOPE["distance_function"],
                            query_vector=query_vector, k=int(k), where=None)
    width = pg_store.configured_hnsw_ef_search()
    return recorder.statements, int(width)


def read_vector_scope(database=SANDBOX_DB) -> dict:
    rows = psql_json("SELECT embedding_model, dimension, distance_function, schema_version"
                     " FROM vector_scope ORDER BY schema_version", database=database,
                     leg="vector_scope")
    if not rows:
        raise GaugeRefused("沙盒库 vector_scope 是空的：没有算符与维度就不许自称真库名次",
                           reason_code="vector_scope_empty")
    return rows[0]


SCOPE: dict = {}


def query_vector_of(dimension: int, seed: int) -> list:
    """定种子随机向量：本单不许打模型（R525 在册同一手法，出处写进读数）。"""
    rng = random.Random(int(seed))
    return [round(rng.uniform(-1.0, 1.0), 6) for _ in range(int(dimension))]


def rank_rows_from_real_store(*, k=40, seed=20261004, database=SANDBOX_DB) -> dict:
    """真库 ANN 回来的名次（只读 ``chunk_vectors``，一字节都不写它）。"""
    global SCOPE
    if not SCOPE:
        SCOPE = read_vector_scope(database)
    vector = query_vector_of(int(SCOPE["dimension"]), seed)
    statements, width = product_ranking_statement(vector, k)
    ranking_sql, params = statements[-1]
    rendered = render_statement(ranking_sql, params)
    wrapper = (
        "BEGIN;\n"
        "SELECT set_config('hnsw.ef_search', " + sql_literal(str(width)) + ", TRUE);\n"
        "SELECT row_to_json(w) FROM ("
        " SELECT prod.vector_id, prod.filename, prod.chunk_index, prod.classification,"
        " prod.department, prod.distance,"
        " left(prod.content, 24) AS content_head,"
        " row_number() OVER (ORDER BY prod.distance, prod.vector_id) AS rank"
        " FROM (" + rendered + ") prod ORDER BY rank) w;\n"
        "COMMIT;\n"
    )
    argv = psql_argv(database=database, script=True)
    proc = docker_exec(argv, stdin_text=assert_read_script_allowed(wrapper), leg="ann_rank",
                       timeout=180)
    if proc["rc"] != 0:
        raise RuntimeError("真库名次取数失败 rc=" + str(proc["rc"]) + ": " + proc["stderr"])
    rows = [json.loads(line) for line in proc["stdout"].splitlines()
            if line.strip().startswith("{")]
    distances = [float(row["distance"]) for row in rows]
    return {
        "rows": rows,
        "ef_search_width": width,
        "set_config_statement": statements[0][0],
        "ranking_statement_chars": len(rendered),
        "ranking_statement_sha256": hashlib_sha(rendered),
        "scope": dict(SCOPE),
        "query_seed": int(seed),
        "requested_k": int(k),
        "returned_rows": len(rows),
        "distinct_distances": len(set(distances)),
        "distances_monotonic": distances == sorted(distances),
    }


def hashlib_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def fake_name_map(real_names) -> dict:
    """真 filename ⇒ r648_ 假名的单射（次序按首次出现）：写域只准落假名，改名不改变名次形状。"""
    out = {}
    for name in real_names:
        if name not in out:
            out[name] = "r648_doc%02d.md" % (len(out) + 1)
    return out


def product_hit_dicts(rows, module=None) -> list:
    """命中字典由产品自己的 ``_hit_dicts`` 生成，本件一个键都不自己定义（同 R525 手法）。"""
    if module is None:
        from app.rag import retriever as module
    metadatas = [{"filename": row["filename"], "chunk_index": row["chunk_index"],
                  "classification": row["classification"], "department": row["department"]}
                 for row in rows]
    return module.DocumentRetriever._hit_dicts(None, [row["content_head"] for row in rows],
                                               metadatas,
                                               module.DocumentRetriever.MODE_SEMANTIC, "")


def displacement_report(hits, priors, *, widths=LEG_WIDTHS, module=None,
                        bound=R153_BOOKED_MAX_SHIFT_RANKS) -> dict:
    """纯算术那一半：把先验喂进 ``rank_hits_by_activity``，逐档量位移对那根界。

    🔴 界 ``bound`` 由调用方钉死（默认 = R153 在册那枚 1），**不读被量模块的常量**：
    把界的分母换成腿宽那种刀（K2）改的正是模块常量与轮数，读它的值就等于让它自己出题。
    """
    if module is None:
        from app.rag import retriever as module
    out = {}
    for width in widths:
        window = list(hits[:int(width)])
        ranked = module.rank_hits_by_activity(window, priors)
        notes = [hit["activity_prior"] for hit in ranked
                 if isinstance(hit, dict) and "activity_prior" in hit]
        moves = []
        for hit in ranked:
            note = hit.get("activity_prior") if isinstance(hit, dict) else None
            if not isinstance(note, dict):
                continue
            moves.append({"source": hit.get("source"),
                          "previous_rank": note.get("previous_rank"),
                          "new_rank": note.get("new_rank"),
                          "places_moved": int(note.get("places_moved", 0)),
                          "shift_ranks": round(float(note.get("shift_ranks", 0.0)), 6),
                          "accepted": int(note.get("accepted", 0)),
                          "rejected": int(note.get("rejected", 0))})
        shifts = [abs(item["places_moved"]) for item in moves]
        plain = list(hits[:int(width)])
        out[str(int(width))] = {
            "width": int(width),
            "distinct_filenames": len({hit.get("source") for hit in window}),
            "carriers_noted": len(notes),
            "moves": moves,
            "max_abs_places_moved": max(shifts) if shifts else 0,
            "carriers_shifted": sum(1 for item in moves if item["places_moved"]),
            "bound_booked": int(bound),
            "bound_constant_in_module": int(module.ACTIVITY_PRIOR_MAX_SHIFT_RANKS),
            "within_bound": bool(shifts) and max(shifts) <= int(bound),
            "no_signal_returns_same_object": module.rank_hits_by_activity(plain, {}) is plain,
        }
    return out

def leg_order(*, database=SANDBOX_DB, widths=LEG_WIDTHS, seed=20261004,
              signal_plan=SIGNAL_PLAN) -> dict:
    """真次序腿：真库名次 + 真库读回的先验 ⇒ R153 那根界在真数据上成不成立。

    🔴 名次/距离/集中度全部是真库读数；只有 ``filename`` 经过一枚**单射改名**落到 ``r648_``
    假名那一格（写域只准假名）。改名是一对一的，名次形状与「同篇占几席」的集中度一个字没动，
    而那两样才是位移算术的输入。
    """
    ann = rank_rows_from_real_store(k=max(widths), seed=seed, database=database)
    rows = ann["rows"]
    names = [row["filename"] for row in rows]
    mapping = fake_name_map(names)
    relabeled = [dict(row, filename=mapping[row["filename"]]) for row in rows]
    plan: dict = {}
    for position, accepted, rejected in signal_plan:
        if position > len(relabeled):
            continue
        name = relabeled[position - 1]["filename"]
        slot = plan.setdefault(name, {"accepted": 0, "rejected": 0, "ranks": []})
        slot["accepted"] += accepted
        slot["rejected"] += rejected
        slot["ranks"].append(int(position))
    targets_pre = sorted(plan)
    statements = [upsert_statement(name, plan[name]["accepted"], plan[name]["rejected"])
                  for name in targets_pre]
    targets = [{"filename": name, "accepted": plan[name]["accepted"],
                "rejected": plan[name]["rejected"], "ranks": plan[name]["ranks"]}
               for name in targets_pre]
    reset_fake_rows(*targets_pre, database=database)
    psql_write("\n".join(statements) + "\n", database=database, leg="order_signals")
    live_rows = real_signal_reader(database)()
    priors = fold_rows_to_priors([list(item) for item in live_rows])
    from app.rag import retriever as module
    hits = product_hit_dicts(relabeled, module)
    report = displacement_report(hits, priors, widths=widths, module=module)
    concentration: dict = {}
    for width in widths:
        window = [row["filename"] for row in relabeled[:int(width)]]
        concentration[str(int(width))] = len(set(window))
    return {
        "status": "measured",
        "provenance": {key: value for key, value in ann.items() if key != "rows"},
        "ann_rows": [{"rank": index, "real_filename": row["filename"],
                      "fake_filename": mapping[row["filename"]],
                      "chunk_index": row["chunk_index"],
                      "classification": row["classification"],
                      "department": row["department"],
                      "distance": round(float(row["distance"]), 6)}
                     for index, row in enumerate(rows, start=1)],
        "distinct_real_filenames": len(set(names)),
        "fake_name_map_pairs": len(mapping),
        "fake_name_map_is_injective": len(set(mapping.values())) == len(mapping),
        "relabeled_concentration": concentration,
        "signal_targets": targets,
        "rows_seen_by_product_reader": len(live_rows),
        "priors_read_back": {name: priors[name] for name in sorted(priors)},
        "displacement": report,
    }


# ==================== 清账 ====================

def leg_baseline(database=SANDBOX_DB) -> dict:
    total = int(psql_scalar("SELECT count(*)::text FROM document_activity_signals",
                            database=database, leg="baseline_total"))
    r648 = count_r648_rows(database=database)
    return {"status": "measured", "row_count": total, "r648_rows": r648,
            "relation": "document_activity_signals", "database": database}


def leg_cleanup(baseline, *, database=SANDBOX_DB) -> dict:
    deleted = psql_write("DELETE FROM document_activity_signals WHERE filename LIKE "
                         + sql_literal(FAKE_LIKE_PATTERN) + ";\n",
                         database=database, leg="cleanup_delete")
    after = count_r648_rows(database=database)
    total = int(psql_scalar("SELECT count(*)::text FROM document_activity_signals",
                            database=database, leg="cleanup_total"))
    return {
        "status": "measured",
        "delete_rc": int(deleted["rc"]),
        "deleted_echo": deleted["stdout"].strip()[:80],
        "r648_rows_before": baseline.get("r648_rows", 0),
        "r648_rows_after": after,
        "total_rows_before": baseline.get("row_count", 0),
        "row_count": total,
        "rows_returned_to_original": after == baseline.get("r648_rows") and total == baseline.get("row_count"),
    }


# ==================== 组装 ====================

LEG_NAMES = ("identity", "baseline", "concurrency", "read_then_write", "mixed_columns",
             "timestamps", "constraints", "order", "cleanup")

_NOTES = {
    "identity": "打的是哪台 PG：current_database / inet_server_addr / inet_server_port / server_version",
    "baseline": "document_activity_signals 的开跑前行数与 r648_ 假名行数",
    "concurrency": "至少两枚真连接对同一枚 filename 打 UPSERT：逐列对平、行数、backend pid 逐枚点名",
    "read_then_write": "K1 的对照形状（客户端先 SELECT 再 UPDATE）：并发腿必须抓到丢更新并点名",
    "mixed_columns": "采纳与驳回各若干混排：两列不许被做成一枚净值（0/0 与 5/5 是两件事）",
    "timestamps": "first_signal_at 不被后续打点改写、last_signal_at 单调",
    "constraints": "0/0 那一笔必须被 0011 的 CHECK 拦下；PK 只有一枚；约束台账与在册 0011 对平",
    "order": "真库名次 + 真库读回先验 ⇒ R153 那根界（最大位移 ≤ 1 名次）在腿宽 5/12/40 上成不成立",
    "cleanup": "r648_ 假名当场 DELETE，行数回到开跑前的原值",
}


def run_report(*, legs=LEG_NAMES, env=None, database=SANDBOX_DB) -> dict:
    """默认态：一枚库都不连，每一格交回显式「未量到」＋原因码（没有测量键，也就没有伪 0）。"""
    declared = gate_declared(env)
    report = {
        "tool": "r648_real_pg_gauge",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "opt_in": {"env": OPT_IN_ENV, "declared": bool(declared),
                   "reason_code": "" if declared else REASON_GATE_OFF},
        "database": database,
        "legs": {},
        "commands": [],
    }
    if not declared:
        for name in legs:
            report["legs"][name] = unmeasured(note=_NOTES.get(name, name))
        report["transport_calls"] = 0
        return report
    assert_sandbox_database(database)
    runners = {
        "identity": lambda: leg_identity(database=database),
        "baseline": lambda: leg_baseline(database),
        "concurrency": lambda: leg_concurrency(database=database),
        "read_then_write": lambda: leg_read_then_write_control(database=database),
        "mixed_columns": lambda: leg_mixed_columns(database=database),
        "timestamps": lambda: leg_timestamps(database=database),
        "constraints": lambda: leg_constraints(database=database),
        "order": lambda: leg_order(database=database),
        "cleanup": None,
    }
    baseline: dict = {"status": "measured", "row_count": 0, "r648_rows": 0}

    def guarded(action):
        """每一枚腿的异常都折成可读数（不许把一枚炸掉的腿洗成「未量到」，也不许洗成绿）。"""
        try:
            return action()
        except Exception as exc:
            return {"status": "error", "reason_code": type(exc).__name__,
                    "detail": str(exc)[:300]}

    for name in legs:
        before = len(_COMMAND_LOG)
        if name == "cleanup":
            reading = guarded(lambda: leg_cleanup(baseline, database=database))
        elif name == "baseline":
            baseline = guarded(lambda: leg_baseline(database))
            reading = baseline
        else:
            reading = guarded(runners[name])
        report["legs"][name] = reading
        report["legs"][name].setdefault("commands", _COMMAND_LOG[before:])
    report["transport_calls"] = len(_COMMAND_LOG)
    return report


def assert_artifact_path_outside_repo(path) -> Path:
    """产物一律落仓外：仓内不许留真库读数文件（同族纪律见 R545 的「产物落仓外」那道闸）。"""
    target = Path(path).resolve()
    if str(target).lower().startswith(str(REPO).lower() + os.sep):
        raise GaugeRefused("产物不许落在仓内：" + str(target), reason_code="artifact_inside_repo")
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R648 真库腿量具（默认零连库）")
    parser.add_argument("--json-out", required=True, help="读数产物路径（必须落在仓外）")
    parser.add_argument("--legs", default=",".join(LEG_NAMES))
    parser.add_argument("--database", default=SANDBOX_DB)
    args = parser.parse_args(argv)
    target = assert_artifact_path_outside_repo(args.json_out)
    names = tuple(item.strip() for item in str(args.legs).split(",") if item.strip())
    report = run_report(legs=names, database=args.database)
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tool": report["tool"], "opt_in": report["opt_in"],
                      "statuses": {name: report["legs"][name].get("status") for name in names},
                      "transport_calls": report.get("transport_calls", 0),
                      "json_out": str(target)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
