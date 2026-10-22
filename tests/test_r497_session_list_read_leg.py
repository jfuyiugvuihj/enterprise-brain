# -*- coding: utf-8 -*-
r"""R497 · 会话列表读腿的第③件：一枚聚合替掉「每行一枚 COUNT」，而「谁能看见哪些会话」一个字不许变。

病灶（R484 并树时点名、本单治的那一格）：`app/api/v1/chat.py::_list_sessions` 从前发的是
`SELECT s.*, (SELECT COUNT(*) FROM session_messages WHERE session_id = s.id AND role = 'user') as
msg_count FROM sessions s ORDER BY s.updated_at DESC`——外层整表零谓词，选中列里那枚相关子查询
**按行求值**，真库 1020 行就是 1020 枚 COUNT（在册 EXPLAIN 实测 `loops=1020`）。本单只把它换成
一枚 `GROUP BY` 预聚合 + `LEFT JOIN` + `COALESCE`，其余一概不动。

🔴 归属一个字都没前推，而且本单**不许**前推，理由分两格：
  · 数据态：真库今天 `sessions` 1020 行里库里 user_id 与台账 owner_id 不等的行 0 枚、库行未在册 0 枚，
    但台账另有 7 枚「库里已无此行」的幽灵绑定、28 枚孤儿行，且两侧之间没有 FK、没有解绑口、
    `sessions.user_id` 允许 NULL（R484 已把「owner namespace 偶然承重」记成在册风险）。
    任何一枚 WHERE 筛子只会把「台账说这人所有」的行吃掉，那是可见集合的**收缩**，不是等价。
  · 规矩：在册牙 `tests/test_r484_session_read_leg_owner_filter.py::
    test_the_read_leg_has_no_owner_predicate_in_sql` 把「`FROM sessions` 之后出现
    where/user_id/owner_id/department/principal 任一 Token」与「全仓有人读 `sessions.user_id`」
    都钉成红；判据④要那 19 枚逐字节不动且照绿，所以本单的合规形状只有一个：
    **零前推 ＋ 台账照旧逐枚终审**。
  本件的 `_check_statement_has_no_owner_predicate` 用的是**同一把尺**（`LEDGER.OWNER_PREDICATE_TOKENS`
  与同一个 `FROM sessions` 切分口径），差别只在它量的是代码**真发出去的语句**，所以在册那枚只读盘上
  字面的静态牙看不见、也替不了的形状，这里看得见。

全程离线：`tests/conftest.py` 已把 `DATABASE_URL` 钉在保留端口 `127.0.0.1:1`，真库一根手指都不碰；
一个端口都不开、一枚模型都不打、盘上零写入（变异只落 `tests/_temp_edit_overlay.py` 的影子根）。
库那一侧用进程内 sqlite 影子台账**真求值**改前与改后两句原文：改前那句由
`git show 7126614:app/api/v1/chat.py` 现取，一个字节都不抄派工词。

判据 → 用例

① 成员集合逐枚相等      `test_visible_membership_is_identical_before_and_after_member_by_member`
                        + `test_msg_count_is_identical_before_and_after_row_by_row`
                        + `test_registered_exits_are_up_to_date_with_the_roster_shape`
                        （孤儿那形 `test_orphan_rows_stay_invisible_to_every_roster_principal`、
                         幽灵绑定那形 `test_the_ghost_binding_never_inflates_the_exit`）
② N+1 归零              `test_the_statement_carries_no_subquery_in_its_projection`
                        + `test_exactly_one_aggregate_and_one_round_trip_for_the_whole_table`
                        + `test_the_round_trip_count_does_not_grow_with_the_row_count`
                        （真库 rows/loops/buffers 的实测差由 `docs/testing/
                         r497-session-list-read-leg-2026-09-29.md` 记，测试里不碰网络）
③ 牙                    `test_counter_evidence_a_totals_only_ruler_lets_the_membership_swap_pass`
                        + 下面四把刀，每把都点名红了哪几枚、红句原文照打印
④ 在册钉不改宽          本件不 import 也不改 `tests/test_r484_*`；`_baseline_sql_lines()` 只读 git，
                        `_check_ledger_asks_once_per_row` 反过来证明终审没被短路。
fail-closed             `test_a_missing_messages_table_refuses_before_the_aggregate_runs`
                        + `test_the_aggregate_failing_is_not_swallowed_into_an_empty_list`
                        （两格都要求改前改后同一张脸，绝不许出现 200 + `[]`）
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import re
import sqlite3
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from psycopg import errors as pg_errors

from app.api.v1 import chat
from app.common import auth
from app.common.auth import create_token
from tests import _temp_edit_overlay as overlay
from tests import test_r466_mutation_does_not_leak_into_live_module as r466

#: 同一把尺：R484 的谓词 Token、成员差集与 SQL 锚点正则，本件一律复用，不另造第二套口径。
LEDGER = importlib.import_module("scripts.r484_session_read_leg_ledger")

REPO = Path(__file__).resolve().parents[1]
CHAT_REL = "app/api/v1/chat.py"
CHAT_PY = REPO / CHAT_REL
#: 本单基点：改前那句原文只从这枚 blob 现取。
BASE = "7126614"

ADMIN = "admin"
EVALBOT = "evalbot"
#: 有部门的 staff，台账零绑定：出口必须是空列表，而且必须是 200（会话腿不认部门那把尺）。
DATAOWNER = "dataowner"
#: 不在 `users` 表里的名字：它名下的行就是孤儿那一族（`app/main.py` 查不到人即 401）。
GHOST_OWNER = "r497-outsider"

S_A1 = "r497-sess-admin-1"
S_A2 = "r497-sess-admin-2"
#: 库里 owner 列为 NULL、台账绑 admin：归属前推（`IS NOT NULL` 那类宽筛）第一口就吃掉它。
S_NULL = "r497-column-is-null"
#: 会话在、消息零枚：`LEFT JOIN` 一旦退化成 `JOIN`，这一枚就从出口消失。
S_EMPTY = "r497-no-messages"
#: 有消息但一枚 user 都没有：msg_count 必须是 0，而且行必须在册。
S_ONLYBOT = "r497-assistant-only"
#: 库里写 admin、台账绑 evalbot：归属分叉的其中一半。
S_SPLIT = "r497-column-says-admin"
#: 库里与台账都说 GHOST_OWNER，而 GHOST_OWNER 已不在 users：孤儿那一形。
S_ORPHAN = "r497-orphan-row"
#: 台账绑 admin、库里没有这一行：真库那 7 枚幽灵绑定这一形。
S_GHOST = "r497-ghost-binding"
#: 只有消息、没有会话行：预聚合不许凭空造出一枚会话。
S_STRAY_MSG = "r497-message-without-session"

#: (id, owner 列, updated_at)。updated_at 逐枚不同，所以改前改后的**返回序**也可比。
DB_ROWS = (
    (S_A1, ADMIN, "2026-09-29T09:00:00+08:00"),
    (S_A2, ADMIN, "2026-09-29T08:00:00+08:00"),
    (S_NULL, None, "2026-09-29T07:00:00+08:00"),
    (S_EMPTY, ADMIN, "2026-09-29T06:00:00+08:00"),
    (S_ONLYBOT, EVALBOT, "2026-09-29T05:00:00+08:00"),
    (S_SPLIT, ADMIN, "2026-09-29T04:00:00+08:00"),
    (S_ORPHAN, GHOST_OWNER, "2026-09-29T03:00:00+08:00"),
)

#: (session_id, role)：user 那一档才进 msg_count。
DB_MESSAGES = (
    (S_A1, "user"), (S_A1, "user"), (S_A1, "assistant"),
    (S_A2, "user"),
    (S_NULL, "user"), (S_NULL, "user"), (S_NULL, "user"),
    (S_ONLYBOT, "assistant"), (S_ONLYBOT, "assistant"),
    (S_SPLIT, "user"),
    (S_ORPHAN, "user"),
    (S_STRAY_MSG, "user"),
)

#: 台账绑定：{session_id: owner}。admin 名下四枚在册 ＋ 一枚幽灵；evalbot 名下两枚。
BINDINGS = {
    S_A1: ADMIN,
    S_A2: ADMIN,
    S_NULL: ADMIN,
    S_EMPTY: ADMIN,
    S_GHOST: ADMIN,
    S_ONLYBOT: EVALBOT,
    S_SPLIT: EVALBOT,
    S_ORPHAN: GHOST_OWNER,
}

#: 今天真出口该长这样（顺序就是 `updated_at DESC` 落进路由之后的序）。
EXPECTED_EXIT = {
    ADMIN: [S_A1, S_A2, S_NULL, S_EMPTY],
    EVALBOT: [S_ONLYBOT, S_SPLIT],
    DATAOWNER: [],
}
#: 库里那一列单独作答时 admin 会得到的出口：总数与今天相同（4 枚）、成员换掉两枚。
COLUMN_ONLY_EXIT = {ADMIN: [S_A1, S_A2, S_EMPTY, S_SPLIT]}
EXPECTED_COUNTS = {
    S_A1: 2, S_A2: 1, S_NULL: 3, S_EMPTY: 0, S_ONLYBOT: 0, S_SPLIT: 1, S_ORPHAN: 1,
}
#: 任何 principal 都不许从出口看到的行。
NEVER_VISIBLE = (S_GHOST, S_STRAY_MSG, S_ORPHAN)

_ROLES = {ADMIN: "admin", EVALBOT: "admin", DATAOWNER: "staff"}
_DEPARTMENTS = {DATAOWNER: "财务部"}
#: 真库今天那两形逐枚的形状：28 枚孤儿行（库里挂着已不在 users 的名字）＋ 7 枚幽灵绑定
#: （台账仍绑 admin、库里已经没有这一行）。形状照 R484 的在册读数复现，id 全是合成的。
ORPHAN_IDS = (S_ORPHAN,) + tuple("r497-orphan-%02d" % index for index in range(2, 29))
GHOST_IDS = (S_GHOST,) + tuple("r497-ghost-%02d" % index for index in range(1, 7))
assert len(ORPHAN_IDS) == 28 and len(GHOST_IDS) == 7, "副本形状漂了，本件不再对应 09-29 那格"

DB_ROWS = DB_ROWS + tuple(
    (session_id, GHOST_OWNER, "2026-09-29T00:%02d:00+08:00" % index)
    for index, session_id in enumerate(ORPHAN_IDS[1:], 1)
)
DB_MESSAGES = DB_MESSAGES + tuple((session_id, "user") for session_id in ORPHAN_IDS[1:])
BINDINGS = dict(BINDINGS, **{session_id: GHOST_OWNER for session_id in ORPHAN_IDS})
BINDINGS = dict(BINDINGS, **{session_id: ADMIN for session_id in GHOST_IDS[1:]})
EXPECTED_COUNTS = dict(EXPECTED_COUNTS, **{session_id: 1 for session_id in ORPHAN_IDS[1:]})
NEVER_VISIBLE = GHOST_IDS + (S_STRAY_MSG,) + ORPHAN_IDS

DB_ROW_IDS = tuple(row[0] for row in DB_ROWS)
ORPHAN_ROW_IDS = tuple(sid for sid, owner, _stamp in DB_ROWS if owner == GHOST_OWNER)
LEDGER_ONLY_IDS = tuple(sorted(set(BINDINGS) - set(DB_ROW_IDS)))
assert ORPHAN_ROW_IDS == ORPHAN_IDS, (ORPHAN_ROW_IDS, ORPHAN_IDS)
assert sorted(LEDGER_ONLY_IDS) == sorted(GHOST_IDS), (LEDGER_ONLY_IDS, GHOST_IDS)




# ============================================================================
# 尺子：全部从「代码真发出去的语句」量，不量我抄下来的字面
# ============================================================================


def _user_row(username, role="staff", department=None):
    """真 `get_user` 的形状：只有 username/role/department，🔴 不许有 `id`（R484 的偶然承重那格）。"""
    return {"username": username, "role": role, "department": department}


USERS = tuple(_user_row(name, _ROLES.get(name, "staff"), _DEPARTMENTS.get(name))
              for name in (ADMIN, EVALBOT, DATAOWNER))


class _UserStore:
    def __init__(self, rows):
        self.rows = {row["username"]: dict(row) for row in rows}

    def get_user(self, username):
        row = self.rows.get(username)
        return dict(row) if row else None


def _sql_lines_of(source: str) -> list:
    """从一份 chat.py 源码里取 `_list_sessions` 发给库的那枚三引号 SQL 的**物理行块**。"""
    match = LEDGER.LIST_SQL_RE.search(source)
    assert match is not None, "锚点漂了：这份源码里找不到 _list_sessions 的 conn.execute(三引号 SELECT)"
    start, end = match.span("sql")
    line_start = source.rfind(chr(10), 0, start) + 1
    line_end = source.find(chr(10), end)
    if line_end == -1:
        line_end = len(source)
    return [line.rstrip(chr(13)) for line in source[line_start:line_end].split(chr(10))]


def _disk_statement_block() -> list:
    return _sql_lines_of(CHAT_PY.read_bytes().decode("utf-8"))


def _baseline_statement_block() -> list:
    """改前那句原文（连同三引号标记所在的物理行）：从基点 blob 现取，不抄派工词。"""
    proc = subprocess.run(["git", "-C", str(REPO), "show", BASE + ":" + CHAT_REL],
                          capture_output=True, check=True)
    return _sql_lines_of(proc.stdout.decode("utf-8"))


def _normalize(lines) -> str:
    return " ".join(" ".join(lines).split())


def _projection_of(statement: str) -> str:
    """深度 0 的那枚 SELECT 的投影列（最外层 SELECT 之后、深度 0 的第一个 FROM 之前）。"""
    lowered = statement.lower()
    depth = 0
    outer = -1
    for index, char in enumerate(lowered):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and lowered.startswith("select", index):
            outer = index + len("select")
            break
    assert outer != -1, "这句里找不到深度 0 的 SELECT：" + statement[:200]
    tail = lowered[outer:]
    depth = 0
    for index, char in enumerate(tail):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and tail.startswith(" from ", index):
            return statement[outer:outer + index].strip()
    raise AssertionError("这句在深度 0 上没有 FROM：" + statement[:200])


def _owner_predicate_hits(statement: str) -> list:
    """R484 那把尺搬到「发出去的语句」上：`FROM sessions` 之后出现归属 Token 即命中。"""
    lowered = statement.lower()
    _head, marker, tail = lowered.partition("from sessions")
    assert marker, "这句里没有 FROM sessions，锚点形状变了：" + statement[:200]
    return [token for token in LEDGER.OWNER_PREDICATE_TOKENS if token in tail]


# ============================================================================
# 影子台账：sqlite 真求值改前/改后两句；每一枚发出去的语句与台账问句都记账
# ============================================================================


class _SqliteLedger:
    """`sessions` / `session_messages` 的进程内只读副本。🔴 只回答 SELECT，一次往返都不多走。"""

    def __init__(self, rows=DB_ROWS, messages=DB_MESSAGES):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, user_id TEXT, title TEXT,"
            " created_at TEXT, updated_at TEXT)"
        )
        self.db.execute(
            "CREATE TABLE session_messages (id INTEGER PRIMARY KEY, session_id TEXT,"
            " role TEXT, content TEXT, steps TEXT DEFAULT '[]', created_at TEXT)"
        )
        for session_id, owner, stamp in rows:
            self.db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                            (session_id, owner, session_id, stamp, stamp))
        for session_id, role in messages:
            self.db.execute(
                "INSERT INTO session_messages (session_id, role, content, steps, created_at)"
                " VALUES (?, ?, ?, '[]', ?)",
                (session_id, role, "body-" + session_id, session_id),
            )
        self.statements: list = []
        self._cursor = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=()):
        self.statements.append(" ".join(str(sql).split()))
        self._cursor = self.db.execute(sql, params or ())
        return self

    def fetchall(self):
        return [dict(row) for row in self._cursor.fetchall()]

    def fetchone(self):
        row = self._cursor.fetchone()
        return dict(row) if row is not None else None

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None


class _DirectoryConn:
    """生产口径的替身连接：先答 `to_regclass` 的现查，再在指定那句上原样抛 UndefinedTable。"""

    _REGCLASS = re.compile(r"to_regclass\('public\.(\w+)'\)", re.IGNORECASE)

    def __init__(self, present=(), boom=None, boom_on=None):
        self.present = {str(name).lower() for name in present}
        self.boom = boom
        self.boom_on = boom_on or (lambda text: False)
        self.statements: list = []
        self._rows: list = []

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=()):
        text = " ".join(str(sql).split())
        self.statements.append(text)
        found = self._REGCLASS.search(text)
        if found:
            name = found.group(1).lower()
            self._rows = [{"table_name": name if name in self.present else None}]
            return self
        if self.boom is not None and self.boom_on(text):
            raise self.boom
        self._rows = []
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def commit(self):
        return None

    def close(self):
        return None

    @property
    def probes(self) -> list:
        return [m.group(1) for s in self.statements if (m := self._REGCLASS.search(s))]


def _registry_at(tmp_path):
    from app.storage.sessions import SessionRegistry

    store = SessionRegistry(tmp_path / "r497-sessions.json")
    for session_id, owner in BINDINGS.items():
        store.bind(session_id, _principal(owner))
    return store


def _principal(username):
    from app.agents.contracts import Principal

    return Principal.from_user(_user_row(username, _ROLES.get(username, "staff"),
                                         _DEPARTMENTS.get(username)))

# ============================================================================
# 世界：真读腿 + 真 SQL + 真路由 + 真台账闸门；只有「查人」与「连库」两枚缝被接管
# ============================================================================

#: 路由里唯一拦人的那三行（`GET /sessions` 的台账终审）。
LEDGER_FINALIZER = [
    "            session",
    "            for session in sessions",
    '            if session_registry.is_owned_by(session.get("id", ""), principal)',
]
#: 刀一：摘掉台账终审，只信库里那一列。
COLUMN_FINALIZER = [
    "            session",
    "            for session in sessions",
    '            if str(session.get("user_id") or "") == str(principal.user_id)',
]


def _wire(monkeypatch, tmp_path, rows=DB_ROWS, messages=DB_MESSAGES):
    """把读腿接到 sqlite 影子台账上，交回 (每次往返的记账, 真台账, 台账问句记账)。"""
    ledgers: list = []

    def _connect():
        conn = _SqliteLedger(rows, messages)
        ledgers.append(conn)
        return conn

    registry = _registry_at(tmp_path)
    asked: list = []
    original = registry.is_owned_by

    def counting(session_id, principal):
        verdict = original(session_id, principal)
        asked.append(str(session_id))
        return verdict

    registry.is_owned_by = counting
    monkeypatch.setattr(chat, "_sess_conn", _connect)
    monkeypatch.setattr(chat, "_session_database_available", lambda: True)
    monkeypatch.setattr(chat, "session_registry", registry)
    monkeypatch.setattr(auth, "get_user", _UserStore(USERS).get_user)
    monkeypatch.setenv("APP_ENV", "development")
    return ledgers, registry, asked


def _request(username):
    """`app/common/authorization.py::principal_from_request` 吃 state.username 再查人。"""
    return SimpleNamespace(state=SimpleNamespace(principal=None, username=username))


def _exit_rows(module, username):
    """跑真路由，交回 (状态码, 出口行)。401 与 503 都从 HTTPException 里取状态码。"""
    try:
        payload = asyncio.run(module.list_sessions(_request(username)))
    except HTTPException as exc:
        return exc.status_code, []
    return 200, list(payload.get("sessions", []))


def _snapshot(module, ledgers, asked):
    """一档世界的全量读数：三档 principal ＋ 孤儿档的出口、msg_count、发出去的语句、台账问句。"""
    mark = len(asked)
    exits = {}
    for name in (ADMIN, EVALBOT, DATAOWNER, GHOST_OWNER):
        status, rows = _exit_rows(module, name)
        exits[name] = {
            "status": status,
            "ids": [row.get("id", "") for row in rows],
            "counts": {row.get("id"): row.get("msg_count") for row in rows},
        }
    return {
        "exits": exits,
        "statements": [stmt for conn in ledgers for stmt in conn.statements],
        "round_trips": sum(len(conn.statements) for conn in ledgers),
        "ledger_asks": sorted(asked[mark:]),
    }


# ============================================================================
# 逐条判据（每条都点名：档 / 谓词 / 逐枚 id；只比总数的那把尺在本件里不算数）
# ============================================================================


def _check_projection_has_no_per_row_subquery(ledgers, label):
    assert ledgers, "%s：这一窗里读腿一次都没发语句，检查是空转" % label
    statement = ledgers[-1].statements[-1]
    projection = _projection_of(statement)
    hits = re.findall(r"\bselect\b", projection, re.IGNORECASE)
    assert not hits, (
        "%s 谓词=最外层投影列不许按行求值 | 投影里出现 %d 枚 SELECT（每行一枚的子查询）| 投影=%s | 全句=%s"
        % (label, len(hits), projection[:200], statement[:320])
    )


def _check_one_aggregate_one_round_trip(ledgers, label):
    assert ledgers, "%s：这一窗里读腿一次都没发语句，检查是空转" % label
    statements = ledgers[-1].statements
    assert len(statements) == 1, (
        "%s 谓词=一次读腿一趟往返 | 发出去了 %d 枚语句：%s" % (label, len(statements), statements)
    )
    lowered = statements[0].lower()
    counts, groups = lowered.count("count("), lowered.count("group by")
    assert counts == 1 and groups == 1, (
        "%s 谓词=整表只许一枚聚合 | COUNT( 命中 %d 枚、GROUP BY 命中 %d 枚（要求各 1）| 全句=%s"
        % (label, counts, groups, statements[0][:320])
    )


def _check_statement_has_no_owner_predicate(ledgers, label):
    assert ledgers, "%s：这一窗里读腿一次都没发语句，检查是空转" % label
    statement = ledgers[-1].statements[-1]
    hits = _owner_predicate_hits(statement)
    assert not hits, (
        "%s 谓词=FROM sessions 之后不许出现归属 Token | 命中=%s | 外层=%s"
        % (label, hits, statement.lower()[statement.lower().index("from sessions"):][:220])
    )


def _check_registered_exits(module, label):
    for name, expected in EXPECTED_EXIT.items():
        status, rows = _exit_rows(module, name)
        assert status == 200, "%s 档=%s 谓词=路由出口 | 期望 200，实测 %d" % (label, name, status)
        got = [row.get("id", "") for row in rows]
        diff = LEDGER.member_diff(set(got), set(expected))
        assert diff["members_equal"], (
            "%s 档=%s 谓词=SQL 行交台账终审 | 出口 %d 枚 != 应有 %d 枚 | 少=%s 多=%s | 序=%s vs %s"
            % (label, name, len(got), len(expected),
               diff["only_in_a"], diff["only_in_b"], got, expected)
        )
        assert got == expected, (
            "%s 档=%s 谓词=ORDER BY updated_at DESC | 成员一样但序换了：%s vs %s"
            % (label, name, got, expected)
        )
        for row in rows:
            want = EXPECTED_COUNTS.get(row.get("id"))
            assert row.get("msg_count") == want, (
                "%s 档=%s 谓词=msg_count 逐枚 | %s 这一枚报 %r，逐枚数出来是 %r"
                % (label, name, row.get("id"), row.get("msg_count"), want)
            )


def _check_ledger_asks_once_per_row(module, ledgers, asked, label):
    """终审还是逐枚问的：SQL 答了几行，台账就被问几行——一枚都不许被筛子代答。"""
    mark = len(asked)
    status, rows = _exit_rows(module, ADMIN)
    assert status == 200, label + "：admin 出口不是 200"
    db_row_ids = sorted(row[0] for row in DB_ROWS)
    got = sorted(asked[mark:])
    assert got == db_row_ids, (
        "%s 谓词=每一行都过一遍台账 | 库里 %d 枚，台账被问 %d 枚=%s | 没被问=%s"
        % (label, len(db_row_ids), len(got), got, sorted(set(db_row_ids) - set(got)))
    )


def _check_zero_message_sessions_survive(module, label):
    """LEFT JOIN 退化成 INNER 的那一格：零 user 消息的会话仍然必须在册，msg_count 报 0。"""
    status, rows = _exit_rows(module, ADMIN)
    ids = [row.get("id", "") for row in rows]
    assert S_EMPTY in ids, "%s 档=%s 谓词=会话行不许被聚合吃掉 | 零消息会话 %s 掉出了出口：%s" % (
        label, ADMIN, S_EMPTY, ids)
    status, rows = _exit_rows(module, EVALBOT)
    ids = [row.get("id", "") for row in rows]
    assert S_ONLYBOT in ids, "%s 档=%s 谓词=有消息但零枚 user | %s 掉出了出口：%s" % (
        label, EVALBOT, S_ONLYBOT, ids)

def _check_no_row_invents_or_leaks(module, label):
    """逐枚点名：28 枚孤儿对任何在册档都不出口、7 枚幽灵绑定不放大出口、聚合不凭空造行。"""
    seen = []
    for name in (ADMIN, EVALBOT, DATAOWNER):
        status, rows = _exit_rows(module, name)
        assert status == 200, "%s 档=%s 谓词=路由出口 | 期望 200，实测 %d" % (label, name, status)
        seen.extend(row.get("id", "") for row in rows)
    leaked = sorted(set(seen) & set(NEVER_VISIBLE))
    assert not leaked, (
        "%s | 孤儿 28 枚／幽灵绑定 7 枚／凭空行 1 枚这一族一枚都不许出口，实测漏了 %d 枚：%s"
        % (label, len(leaked), leaked))
    status, _rows = _exit_rows(module, GHOST_OWNER)
    assert status == 401, (
        "%s 档=%s 谓词=查不到人即拒（app/main.py 那枚 roster 闸）| 期望 401，实测 %d"
        % (label, GHOST_OWNER, status))


def _check_the_whole_table_still_travels(module, label):
    """不前推的正面钉：库里每一行都照旧回到 Python，交给台账逐枚终审。

    孤儿之所以看不见，是因为 users 表里没有这个人，不是读腿把行筛掉了——这一格一旦被筛子
    代答，出口就会从「roster 说了算」变成「SQL 说了算」，正是 R484 在册牙守着的那句话。
    """
    rows = module._list_sessions()
    got = sorted(row.get("id", "") for row in rows)
    diff = LEDGER.member_diff(set(got), set(DB_ROW_IDS))
    assert diff["members_equal"], (
        "%s 谓词=SQL 侧整表交给终审 | 读腿交回 %d 枚，库里 %d 枚 | 被筛掉=%s 多出来=%s"
        % (label, len(got), len(DB_ROW_IDS), diff["only_in_a"], diff["only_in_b"]))

# ============================================================================
# 反证窗：变异只落影子根，窗内只换改动的那枚顶层绑定（R253 + R466 姿势）
# ============================================================================


class _R497Edit(overlay.ShadowEdit):
    """一扇 R497 的反证窗：锚点命中不是恰好一处就不落盘；变异文本先过 compile()。"""

    tag = "r497"
    execs_module = False

    def __init__(self, path, edits):
        super().__init__(path)
        self.edits = [(tuple(old), tuple(new)) for old, new in edits]

    def mutate(self, text):
        newline = chr(13) + chr(10) if chr(13) + chr(10) in text else chr(10)
        mutated = text
        for old, new in self.edits:
            needle = newline.join(old)
            hits = mutated.count(needle)
            assert hits == 1, (
                "%s 里锚点命中 %d 处（要求恰好 1 处）：%r —— 变异整体不落盘" % (
                    self.path.name, hits, old[0]))
            mutated = mutated.replace(needle, newline.join(new), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


@contextmanager
def _window(edits):
    """刀窗：影子副本挨变异，活模块只被换上改了的那枚绑定，出门逐枚装回。"""
    module = overlay.module_of(overlay.rel_of(CHAT_PY))
    assert module is not None, "app.api.v1.chat 还没被导入，改绑无处可落"
    with _R497Edit(CHAT_PY, edits) as info, \
            r466.install_mutation(module, CHAT_PY, info.read_text()):
        yield info


def _tracked_sha(path: Path = CHAT_PY) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _edits_back_to_baseline():
    """刀三（同时也是「改前」那一侧的窗）：把一枚聚合改回每行一枚 COUNT 子查询。"""
    disk = _disk_statement_block()
    base = _baseline_statement_block()
    assert disk != base, "盘上的字已经等于基点形态：这扇窗是空转"
    assert any("(SELECT COUNT" in line for line in base), (
        "基点形态里没有每行一枚的 COUNT 子查询，锚点漂了：%s" % base)
    return [(disk, base)]


def _edits_prefilter():
    """刀二：把归属前推成一枚 `WHERE s.user_id IS NOT NULL` 宽筛（派工词点名的形状）。"""
    block = _disk_statement_block()
    order_lines = [line for line in block if "ORDER BY" in line]
    assert len(order_lines) == 1, "外层 ORDER BY 不是恰好一枚：%s" % order_lines
    order_line = order_lines[0]
    indent = order_line[: len(order_line) - len(order_line.lstrip())]
    mutated = []
    for line in block:
        if line == order_line:
            mutated.append(indent + "WHERE s.user_id IS NOT NULL")
        mutated.append(line)
    return [(block, mutated)]


def _edits_inner_join():
    """刀四（本单自加）：LEFT JOIN 退化成 JOIN——「换成一枚聚合」最容易写错的那一格。"""
    block = _disk_statement_block()
    left = [line for line in block if "LEFT JOIN" in line]
    assert len(left) == 1, "LEFT JOIN 不是恰好一枚：%s" % left
    return [(block, [line.replace("LEFT JOIN", "JOIN") for line in block])]


def _edits_trust_the_column():
    """刀一：摘掉台账终审，只信库里那一列。"""
    return [(LEDGER_FINALIZER, COLUMN_FINALIZER)]


def _checks(module, ledgers, asked, label):
    """八条真断言，按钉名交给刀窗挨条跑：红了谁、红句原文，全部现打。"""
    return (
        ("整表照旧交给终审",
         lambda: _check_the_whole_table_still_travels(module, label)),
        ("投影零子查询（N+1）",
         lambda: _check_projection_has_no_per_row_subquery(ledgers, label)),
        ("单枚聚合＋一趟往返",
         lambda: _check_one_aggregate_one_round_trip(ledgers, label)),
        ("语句里零归属谓词",
         lambda: _check_statement_has_no_owner_predicate(ledgers, label)),
        ("三档出口成员逐枚相等",
         lambda: _check_registered_exits(module, label)),
        ("台账逐枚终审",
         lambda: _check_ledger_asks_once_per_row(module, ledgers, asked, label)),
        ("零消息会话仍在册",
         lambda: _check_zero_message_sessions_survive(module, label)),
        ("幽灵/孤儿/凭空行不漏",
         lambda: _check_no_row_invents_or_leaks(module, label)),
    )


def _reds(checks):
    """窗内挨条跑：交回 [(钉名, 红句原文)]；没红的不动。"""
    red = []
    for name, call in checks:
        try:
            call()
        except AssertionError as exc:
            red.append((name, str(exc)))
    return red

# ============================================================================
# 判据① 今天这张脸：三档 principal ＋ 28 枚孤儿 ＋ 7 枚幽灵绑定，逐枚点名
# ============================================================================


def test_registered_exits_reproduce_the_roster_shape(monkeypatch, tmp_path):
    """改后必须一字不改地复现 R484 那四形：库里/台账/出口/差在哪几枚，全部逐枚点名。"""
    ledgers, registry, asked = _wire(monkeypatch, tmp_path)
    _check_registered_exits(chat, "现网码")
    _check_no_row_invents_or_leaks(chat, "现网码")
    _check_the_whole_table_still_travels(chat, "现网码")
    _check_ledger_asks_once_per_row(chat, ledgers, asked, "现网码")
    lines = ["[R497 形状] 库里 %d 行 / 台账 %d 条 / 孤儿 %d 枚 / 幽灵绑定 %d 枚" % (
        len(DB_ROW_IDS), len(BINDINGS), len(ORPHAN_ROW_IDS), len(LEDGER_ONLY_IDS))]
    for name in (ADMIN, EVALBOT, DATAOWNER, GHOST_OWNER):
        status, rows = _exit_rows(chat, name)
        lines.append("  档=%-14s 状态=%d 出口=%d 枚 %s" % (
            name, status, len(rows), [row["id"] for row in rows][:6]))
    print(chr(10).join(lines))


def test_the_disk_ruler_and_the_recorded_statement_read_the_same_sentence(monkeypatch, tmp_path):
    """R484 那把只读盘上字面的静态尺，与本件量的「真发出去的语句」必须一字不差。"""
    ledgers, _registry, _asked = _wire(monkeypatch, tmp_path)
    _check_registered_exits(chat, "现网码")
    recorded = ledgers[-1].statements[-1]
    anchors = LEDGER.check_list_sessions_sql()
    assert anchors["sql"] == recorded, (
        "盘上那枚 SQL 与读腿真发出去的那枚分叉了：尺子量的不是同一句话")
    assert anchors["owner_predicate_hits"] == [], anchors["outer_tail"]
    assert anchors["selects_whole_table"] is True
    assert _owner_predicate_hits(recorded) == []
    readers = LEDGER.check_read_leg_uses_no_user_id_column()
    assert readers["count"] == 0, (
        "全仓 app/** 里出现了读 sessions 那一列的代码行（在册牙会当场红）：%s" % readers["readers"])


def test_the_statement_carries_no_subquery_in_its_projection(monkeypatch, tmp_path):
    """判据②：最外层投影列里一枚子查询 SELECT 都不许有——那「每行一枚 COUNT」就是从这里来的。"""
    ledgers, _registry, _asked = _wire(monkeypatch, tmp_path)
    _check_registered_exits(chat, "现网码")
    _check_projection_has_no_per_row_subquery(ledgers, "现网码")


def test_exactly_one_aggregate_and_one_round_trip_for_the_whole_table(monkeypatch, tmp_path):
    """判据②：整表一趟往返、一枚 COUNT、一枚 GROUP BY。"""
    ledgers, _registry, _asked = _wire(monkeypatch, tmp_path)
    chat._list_sessions()
    _check_one_aggregate_one_round_trip(ledgers, "现网码")


def test_the_round_trip_count_does_not_grow_with_the_row_count(monkeypatch, tmp_path):
    """3 行与 34 行各跑一趟：发出去的语句枚数不随行数长（🔴 这只证 Python 侧没扇出）。"""
    small = tuple(row for row in DB_ROWS[:3])
    small_messages = tuple(item for item in DB_MESSAGES if item[0] in {row[0] for row in small})
    big_ledgers, _r, _a = _wire(monkeypatch, tmp_path)
    big_rows = chat._list_sessions()
    small_ledgers, _r2, _a2 = _wire(monkeypatch, tmp_path, rows=small, messages=small_messages)
    small_rows = chat._list_sessions()
    assert len(big_rows) == len(DB_ROW_IDS) and len(small_rows) == 3, (
        "夹具不成立：两档世界的行数没拉开（%d vs %d）" % (len(big_rows), len(small_rows)))
    assert len(big_ledgers[-1].statements) == 1, big_ledgers[-1].statements
    assert len(small_ledgers[-1].statements) == 1, small_ledgers[-1].statements
    print("[R497 往返] 库里 %d 行发了 %d 枚语句；%d 行发了 %d 枚语句" % (
        len(big_rows), len(big_ledgers[-1].statements),
        len(small_rows), len(small_ledgers[-1].statements)))


def test_msg_count_matches_a_row_by_row_tally_member_by_member(monkeypatch, tmp_path):
    """msg_count 的每一枚都等于「按行数出来的 user 枚数」，零 user 的行报 0、且仍在册。"""
    _ledgers, _registry, _asked = _wire(monkeypatch, tmp_path)
    tally = {}
    for session_id, role in DB_MESSAGES:
        if role == "user":
            tally[session_id] = tally.get(session_id, 0) + 1
    got = {row["id"]: row["msg_count"] for row in chat._list_sessions()}
    want = {session_id: tally.get(session_id, 0) for session_id in DB_ROW_IDS}
    diff = {session_id: (got.get(session_id, "<缺行>"), want[session_id])
            for session_id in want if got.get(session_id) != want[session_id]}
    assert not diff, "谓词=msg_count 逐枚 | 这些行报错了数（实测, 按行数出来）：%s" % sorted(diff.items())
    zeros = sorted(session_id for session_id, value in got.items() if value == 0)
    assert set((S_EMPTY, S_ONLYBOT)) <= set(zeros), (
        "零 user 消息的那两枚没走到 0 这一格：%s" % zeros)
    print("[R497 msg_count] %d 枚逐枚相等，其中报 0 的 %d 枚=%s" % (
        len(got), len(zeros), zeros))


def test_counter_evidence_a_totals_only_ruler_lets_the_membership_swap_pass(monkeypatch, tmp_path):
    """判据③第一枚：总数一样、成员换了——只比总数的尺放过去，逐枚相等的尺必须红。"""
    _ledgers, _registry, _asked = _wire(monkeypatch, tmp_path)
    assert len(COLUMN_ONLY_EXIT[ADMIN]) == len(EXPECTED_EXIT[ADMIN]), (
        "夹具不成立：这两档世界总数本来就不同，量不出「只看总数」的盲点")
    diff = LEDGER.member_diff(set(COLUMN_ONLY_EXIT[ADMIN]), set(EXPECTED_EXIT[ADMIN]))
    assert diff["members_equal"] is False, "夹具不成立：这两档成员本来就一样"
    assert diff["only_in_a"] == [S_SPLIT] and diff["only_in_b"] == [S_NULL], diff

    def _world(ids):
        return {"exits": {name: {"status": 200, "ids": list(ids), "counts": {}}
                          for name in (ADMIN, EVALBOT, DATAOWNER, GHOST_OWNER)},
                "statements": ["SELECT 1", "SELECT 1", "SELECT 1"]}

    with pytest.raises(AssertionError) as caught:
        _assert_snapshots_equal(_world(EXPECTED_EXIT[ADMIN]), _world(COLUMN_ONLY_EXIT[ADMIN]),
                                "成员互换的世界")
    red = str(caught.value)
    assert S_SPLIT in red and S_NULL in red, "红句没点到换掉的那两枚名字：%s" % red
    print("[R497 反证] 同总数不同成员的世界 → 逐枚相等的尺当场红：%s" % red)

# ============================================================================
# 判据① 主证：改前（基点 blob 那句原文）vs 改后，出口成员逐枚相等
# ============================================================================


def _assert_the_window_is_not_idling(before, after, label):
    before_stmt = before["statements"][-1]
    after_stmt = after["statements"][-1]
    assert before_stmt != after_stmt, (
        "%s：窗里那句 SQL 与盘上那枚一字不差，这扇窗是空转，对账就是自己跟自己对" % label)
    assert "(SELECT COUNT" in before_stmt, (
        "%s：改前那一侧没有每行一枚的 COUNT 子查询，锚点漂了：%s" % (label, before_stmt[:240]))
    assert "GROUP BY" in after_stmt and "LEFT JOIN" in after_stmt, (
        "%s：改后那一侧不是「一枚聚合 + LEFT JOIN」的形状：%s" % (label, after_stmt[:240]))


def _assert_snapshots_equal(before, after, label):
    for name in (ADMIN, EVALBOT, DATAOWNER, GHOST_OWNER):
        b, a = before["exits"][name], after["exits"][name]
        assert b["status"] == a["status"], (
            "%s 档=%s 谓词=出口状态 | 改前 %d / 改后 %d" % (label, name, b["status"], a["status"]))
        diff = LEDGER.member_diff(set(b["ids"]), set(a["ids"]))
        assert diff["members_equal"] and b["ids"] == a["ids"], (
            "%s 档=%s 谓词=SQL 行交台账终审 | 改前 %d 枚 / 改后 %d 枚 | 改前独有=%s 改后独有=%s"
            " | 改前序=%s | 改后序=%s" % (
                label, name, len(b["ids"]), len(a["ids"]),
                diff["only_in_a"], diff["only_in_b"], b["ids"], a["ids"]))
        assert b["counts"] == a["counts"], (
            "%s 档=%s 谓词=msg_count 逐枚 | 改前 %s / 改后 %s" % (label, name, b["counts"], a["counts"]))
    assert len(before["statements"]) == len(after["statements"]), (
        "%s | 改前发了 %d 枚语句，改后发了 %d 枚：往返形状变了" % (
            label, len(before["statements"]), len(after["statements"])))


def test_visible_membership_is_identical_before_and_after_member_by_member(monkeypatch, tmp_path):
    """判据①：把 `GET /sessions` 的出口逐档逐枚对账——改前那句原文跑一遍，改后跑一遍，差集必须为空。"""
    ledgers, _registry, asked = _wire(monkeypatch, tmp_path)
    after = _snapshot(chat, ledgers, asked)
    disk_sha = _tracked_sha()
    del ledgers[:]
    del asked[:]
    with _window(_edits_back_to_baseline()) as info:
        before = _snapshot(chat, ledgers, asked)
        _assert_the_window_is_not_idling(before, after, "改前窗")
        _assert_snapshots_equal(before, after, "改前 vs 改后")
    assert info["restored"] is True and _tracked_sha() == disk_sha, "窗没收干净"
    for name in (ADMIN, EVALBOT, DATAOWNER, GHOST_OWNER):
        print("[R497 对账] 档=%-14s 改前=%d 枚 改后=%d 枚 差集=空 状态=%d/%d" % (
            name, len(before["exits"][name]["ids"]), len(after["exits"][name]["ids"]),
            before["exits"][name]["status"], after["exits"][name]["status"]))


def test_every_column_of_every_row_is_identical_before_and_after(monkeypatch, tmp_path):
    """读腿交回的整张表：成员、每一格、返回序，改前与改后逐枚相等。"""
    ledgers, _registry, _asked = _wire(monkeypatch, tmp_path)
    after_rows = chat._list_sessions()
    after_stmt = ledgers[-1].statements[-1]
    disk_sha = _tracked_sha()
    del ledgers[:]
    with _window(_edits_back_to_baseline()) as info:
        before_rows = chat._list_sessions()
        before_stmt = ledgers[-1].statements[-1]
    assert before_stmt != after_stmt, "空转：窗里没换 SQL"
    assert [row["id"] for row in before_rows] == [row["id"] for row in after_rows], (
        "返回序换了：%s vs %s" % ([r["id"] for r in before_rows], [r["id"] for r in after_rows]))
    b = {row["id"]: row for row in before_rows}
    a = {row["id"]: row for row in after_rows}
    assert set(b) == set(a), "成员分叉：只在一侧出现的行 = %s" % sorted(set(b) ^ set(a))
    for session_id in sorted(a):
        assert b[session_id] == a[session_id], (
            "%s 这一行的格变了：改前=%s 改后=%s" % (session_id, b[session_id], a[session_id]))
    assert info["restored"] is True and _tracked_sha() == disk_sha
    print("[R497 逐格] %d 行 × %d 格逐枚相等（含 msg_count）" % (
        len(a), len(next(iter(a.values())))))


# ============================================================================
# fail-closed：库不可用/语句跑挂，都不许多出一张 200 + [] 的脸（R495 在防的形状）
# ============================================================================

_MISSING_MESSAGES = 'relation "session_messages" does not exist'


def _prod_world(monkeypatch, tmp_path, conn):
    monkeypatch.setattr(chat, "_sess_conn", lambda: conn)
    monkeypatch.setattr(chat, "_session_database_available", lambda: True)
    monkeypatch.setattr(chat, "session_registry", _registry_at(tmp_path))
    monkeypatch.setattr(auth, "get_user", _UserStore(USERS).get_user)
    monkeypatch.setenv("APP_ENV", "production")
    return conn


def test_a_missing_messages_table_refuses_before_the_aggregate_runs(monkeypatch, tmp_path):
    """表不在 = 那枚具名错、那只 503；聚合连一次都不许跑，更不许答出一张零消息的表。"""
    conn = _prod_world(monkeypatch, tmp_path, _DirectoryConn(present={"sessions"}))
    with pytest.raises(chat.ChatSchemaNotMigratedError):
        chat._list_sessions()
    with pytest.raises(HTTPException) as caught:
        asyncio.run(chat.list_sessions(_request(ADMIN)))
    assert caught.value.status_code == 503, caught.value.status_code
    assert caught.value.detail == "storage_unavailable"
    # 这一窗里读了两趟（直调一次 + 走路由一次），每趟都先过两枚现查闸，聚合一枚都没发。
    assert conn.probes == ["sessions", "session_messages"] * 2, conn.statements
    assert [s for s in conn.statements if "FROM sessions" in s] == [], conn.statements

    disk_sha = _tracked_sha()
    with _window(_edits_back_to_baseline()):
        before = _prod_world(monkeypatch, tmp_path, _DirectoryConn(present={"sessions"}))
        with pytest.raises(chat.ChatSchemaNotMigratedError):
            chat._list_sessions()
        with pytest.raises(HTTPException) as old_face:
            asyncio.run(chat.list_sessions(_request(ADMIN)))
        assert old_face.value.status_code == 503
        assert before.probes == conn.probes
    assert _tracked_sha() == disk_sha


def test_the_aggregate_failing_is_not_swallowed_into_an_empty_list(monkeypatch, tmp_path):
    """语句自己跑挂（表在、求值炸）：错误照旧往外抛，既没被洗成 503，也没被洗成 200 + `[]`。"""
    boom = pg_errors.UndefinedTable(_MISSING_MESSAGES)
    conn = _prod_world(
        monkeypatch, tmp_path,
        _DirectoryConn(present={"sessions", "session_messages"}, boom=boom,
                       boom_on=lambda text: "FROM sessions" in text))
    with pytest.raises(pg_errors.UndefinedTable):
        chat._list_sessions()
    answer = []
    try:
        answer.append(asyncio.run(chat.list_sessions(_request(ADMIN))))
    except pg_errors.UndefinedTable:
        pass
    assert not answer, "失败被吞成答卷了：%r" % answer
    assert conn.statements and "FROM sessions" in conn.statements[-1], conn.statements

    disk_sha = _tracked_sha()
    with _window(_edits_back_to_baseline()):
        _prod_world(monkeypatch, tmp_path, _DirectoryConn(
            present={"sessions", "session_messages"}, boom=boom,
            boom_on=lambda text: "FROM sessions" in text))
        with pytest.raises(pg_errors.UndefinedTable):
            chat._list_sessions()
    assert _tracked_sha() == disk_sha


def test_the_http_face_still_answers_200_with_the_owner_rows(monkeypatch, tmp_path):
    """真路由真中间件：出口仍是 200 与同一批行、同一批格，一个字段都没多、都没少。"""
    ledgers, _registry, _asked = _wire(monkeypatch, tmp_path)
    from app.main import app

    with TestClient(app) as client:
        client.headers.update({"Authorization": "Bearer " + create_token(ADMIN)})
        response = client.get("/api/v1/sessions")
    assert response.status_code == 200, response.text
    rows = response.json()["sessions"]
    assert [row["id"] for row in rows] == EXPECTED_EXIT[ADMIN], rows
    assert set(rows[0]) == {"id", "user_id", "title", "created_at", "updated_at", "msg_count"}, rows[0]
    assert rows[0]["msg_count"] == EXPECTED_COUNTS[S_A1], rows[0]
    assert ledgers[-1].statements and len(ledgers[-1].statements) == 1
    print("[R497 出口] HTTP 200，%d 枚=%s，msg_count=%s" % (
        len(rows), [row["id"] for row in rows], [row["msg_count"] for row in rows]))

# ============================================================================
# 判据③ 四把刀：每把只动一处，红谁、红句原文，全在打印里；刀身只落影子根
# ============================================================================


def _knife(edits, label, expected_reds, monkeypatch, tmp_path):
    """开一扇刀窗挨条跑真断言收红；出窗再跑一遍，必须回到全绿，且盘上字节一字未动。"""
    ledgers, _registry, asked = _wire(monkeypatch, tmp_path)
    disk_sha = _tracked_sha()
    baseline = _reds(_checks(chat, ledgers, asked, "现网码"))
    assert not baseline, "现网码就有红，刀窗读数不算数：%s" % baseline
    del ledgers[:]
    del asked[:]
    with _window(edits) as info:
        red = _reds(_checks(chat, ledgers, asked, label))
    names = sorted(name for name, _text in red)
    assert names == sorted(expected_reds), (
        "%s：这把刀该红的是 %s，实测红了 %s" % (label, sorted(expected_reds), names))
    for name, text in red:
        print("[R497 %s] 红了「%s」：%s" % (label, name, text))
    assert info["restored"] is True, "刀身没还原：影子副本与盘上的字不同步"
    assert _tracked_sha() == disk_sha, "刀落到了盘上：%s 的字节变了" % CHAT_REL
    del ledgers[:]
    del asked[:]
    after = _reds(_checks(chat, ledgers, asked, "出窗复跑"))
    assert not after, "出窗没回到现网码，红的还是：%s" % [name for name, _t in after]
    print("[R497 %s] 出窗复跑 %d 枚钉全绿；盘上 sha256/16 = %s（进出一致）" % (
        label, len(list(_checks(chat, ledgers, asked, "x"))), disk_sha[:16]))
    return red


def test_knife_1_trusting_the_column_reddens_the_membership_and_finalizer(monkeypatch, tmp_path):
    """刀一：摘掉台账终审、只信库里那一列 → 成员钉与「逐枚终审」钉红，其余不动。"""
    ledgers, _registry, _asked = _wire(monkeypatch, tmp_path)
    disk_sha = _tracked_sha()
    with _window(_edits_trust_the_column()) as info:
        status, rows = _exit_rows(chat, ADMIN)
        got = [row["id"] for row in rows]
        assert status == 200
        assert len(got) == len(EXPECTED_EXIT[ADMIN]), (
            "夹具不成立：这把刀造成的世界总数本来就变了（%d vs %d）"
            % (len(got), len(EXPECTED_EXIT[ADMIN])))
        assert got == COLUMN_ONLY_EXIT[ADMIN], (
            "这把刀该让世界变成「只信那一列」：%s vs %s" % (got, COLUMN_ONLY_EXIT[ADMIN]))
        diff = LEDGER.member_diff(set(got), set(EXPECTED_EXIT[ADMIN]))
        assert diff["only_in_a"] == [S_SPLIT] and diff["only_in_b"] == [S_NULL], diff
        print("[R497 刀一] admin 出口 %d 枚（总数与今天相同）但成员换了：多出=%s 少了=%s" % (
            len(got), diff["only_in_a"], diff["only_in_b"]))
    assert info["restored"] is True and _tracked_sha() == disk_sha
    _knife(_edits_trust_the_column(), "刀一 只信库里那一列", [
        "三档出口成员逐枚相等",
        "台账逐枚终审",
    ], monkeypatch, tmp_path)


def test_knife_2_pushing_a_where_prefilter_reddens_the_predicate_and_membership(monkeypatch, tmp_path):
    """刀二：把归属前推成一枚 `WHERE s.user_id IS NOT NULL` 宽筛 → 谓词钉、整表钉、成员钉、终审钉全红。

    这就是本单不许前推的实测形状：那枚 owner 列为 NULL 的行今天由台账认给 admin，筛子一落，
    它连被终审问一次的机会都没有——可见集合当场少一枚，而「幽灵绑定/孤儿」两侧本来就没被
    任何约束绑在一起，等值无从证明。
    """
    _knife(_edits_prefilter(), "刀二 归属前推成宽筛", [
        "语句里零归属谓词",
        "整表照旧交给终审",
        "三档出口成员逐枚相等",
        "台账逐枚终审",
    ], monkeypatch, tmp_path)


def test_knife_3_reverting_to_the_per_row_count_reddens_only_the_n_plus_1_teeth(monkeypatch, tmp_path):
    """刀三：把一枚聚合改回每行一枚 COUNT 子查询 → 只有 N+1 那两枚钉红，语义钉一枚不红。

    「只有 N+1 红、可见集合不红」正是本单想说的两句话：形状确实变了（这就是收益），
    而归属一个字没动（这就是等价）。
    """
    _knife(_edits_back_to_baseline(), "刀三 聚合改回每行 COUNT", [
        "投影零子查询（N+1）",
        "单枚聚合＋一趟往返",
    ], monkeypatch, tmp_path)


def test_knife_4_inner_join_reddens_the_zero_message_and_membership_pins(monkeypatch, tmp_path):
    """刀四（本单自加）：LEFT JOIN 退化成 JOIN → 零 user 消息的会话被聚合吃掉，四枚钉红。

    这一把是给「换成一枚聚合」这个动作本身准备的：标量子查询改成外连接最容易写错的正是这一格，
    而它一旦写错，掉出去的是真实存在的会话行——不是快慢问题，是可见集合问题。
    """
    _knife(_edits_inner_join(), "刀四 LEFT 退化成 JOIN", [
        "整表照旧交给终审",
        "三档出口成员逐枚相等",
        "台账逐枚终审",
        "零消息会话仍在册",
    ], monkeypatch, tmp_path)


def test_every_knife_leaves_the_tracked_bytes_untouched(monkeypatch, tmp_path):
    """判据③的收尾凭据：四把刀各开一扇窗，盘上 chat.py 与基点比仍是同一串字节。"""
    before = _tracked_sha()
    baseline_sql = _disk_statement_block()
    for label, edits in (("刀一", _edits_trust_the_column()),
                         ("刀二", _edits_prefilter()),
                         ("刀三", _edits_back_to_baseline()),
                         ("刀四", _edits_inner_join())):
        with _window(edits) as info:
            assert _tracked_sha()[:16] == info["before"], label + " 窗内盘上的字就变了"
        assert info["restored"] is True, label + " 没还原"
        assert info["after"] == info["before"], label + " 出门字节换了"
    assert _disk_statement_block() == baseline_sql, "SQL 块的字面被刀窗动过"
    assert _tracked_sha() == before, "chat.py 的字节被刀窗动过"
    print("[R497 还原凭据] 四扇窗进出一致：chat.py sha256/16 = %s" % before[:16])
