# -*- coding: utf-8 -*-
"""R484 · 会话读腿的归属取证（只读；零写库、零建号、零产品码）。

病：库里 `sessions` 1020 行，`GET /sessions` 对 `evalbot` 只回 656 条；那 364 之差自 R470 4
「本单不判」起今天没人 owning。本单**不修**，只做三件事：把这段形状取证、把定性钉住、
把「谁在拦人」指名到现读的代码上。

三处锚点由本件 `--anchors` 现扫现证（行号会漂，所以只认函数名与谓词，不认行号）:

1. `app/api/v1/chat.py` 的 `_list_sessions()`: SQL 是
   `SELECT s.*, (...) as msg_count FROM sessions s ORDER BY s.updated_at DESC`
   -- SQL 侧一个字的 owner/部门 WHERE 都没有, 库里整表进 Python。
2. 同一个文件的 `GET /sessions`: 在 **Python 侧** 逐条过
   `session_registry.is_owned_by(session.get("id", ""), principal)`。
3. `app/storage/sessions.py` 自述 `Transitional owner registry` /
   `JSON-backed owner mapping until the canonical Session table is migrated`,
   判定式 `record.owner_id == str(principal.user_id)`。

=> 本单要钉住的那句话: **拦人的是 JSON 台账, 库里那枚 `sessions.user_id` 列在读腿上今天
一根手指都没碰过。** 它今天与台账 `owner_id` 同为「用户名字符串」, 是因为
`app/common/auth.py` 的 `get_user()` 只 SELECT `username, role, department` -- 不含 `id` --
于是 `Principal.from_user` 落到 `user.get("username")`。这格是**偶然承重**而不是设计,
所以它同时是本件报出的那枚 load-bearing 风险: 谁给那枚 SELECT 补上 `id`,
`principal.user_id` 当场翻成 bigint 字符串, 台账零命中, `GET /sessions` 对所有人静默回空列表
(不报错、不 403、不降级)。这一族由 `tests/test_r484_session_read_leg_owner_filter.py` 钉。

四条口径 (照 `scripts/r483_empty_tables_triage.py` 的房规, 不在别处抄第二份):

* 读数只经 `docker exec <pg 容器> psql ... -c "SET default_transaction_read_only = on"
  -c "<SELECT>"`。一条写语句、一条 DDL 都不发: `assert_select_only()` 是唯一出口闸,
  命中禁词直接抛。宿主 `127.0.0.1:5432` 上另有**野 PG** (本席第一次读数就拿到 36 行、
  `user_id` 全 NULL 的假库, 与在册的 R470 二同一格), 所以本件从不直连宿主端口。
* JSON 台账**直读文件** (`docker exec ... cat`), 绝不 import `SessionRegistry` 来读:
  它的 `__init__` 会 `mkdir`, `bind()` 会 `_save()` 落盘 -- 取证件一旦 import 就自己变成写者。
* 三形四列与孤儿归属全部由**纯函数** `ledger_view()` 算出: 零 I/O、零环境依赖,
  所以同一枚尺能被测试件拿去在假世界上复现 (判据 3「逐枚相等不许退化成看总数」就这么钉)。
* `--live` 只是旁证: 进 backend 容器用 `app.common.auth.create_token` 本地签 JWT 打真出口
  (不走 `/api/v1/login`, 因此不写 audit), 并自己核 `audit_events` 前后计数; 它只对
  **在 `users` 表里的**名字发请求 -- 401 那条路会经 `app/main.py:_file_anonymous_denial`
  落 `record_audit` (本席实测两枚 401 就是 +2 行), 取证件不许留下这种账。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

NL = chr(10)
REPO_ROOT = Path(__file__).resolve().parents[1]

PG_CONTAINER = "enterprise-brain-postgres-1"
BACKEND_CONTAINER = "enterprise-brain-backend-1"
PG_USER = "enterprise_brain"
PG_DB = "enterprise_brain"
READ_ONLY_PREFIX = "SET default_transaction_read_only = on"

#: SELECT 里一枚都不许出现的词: 「一条写语句都不发」的代码化。
FORBIDDEN_IN_SELECT = (
    "insert", "update", "delete", "create", "alter", "drop", "truncate", "grant", "revoke",
    "copy", "vacuum", "analyze", "call", "merge", "refresh", "comment", "prepare",
    "deallocate", "set",
)

def assert_select_only(sql: str) -> str:
    """唯一的读数出口闸: 不是 SELECT 就抛, 命中禁词也抛。"""
    body = sql.strip().rstrip(";").strip()
    lowered = body.lower()
    if not lowered.startswith(("select", "with")):
        raise ValueError("R484 只许发 SELECT, 收到的是: " + body[:120])
    for word in FORBIDDEN_IN_SELECT:
        if re.search(r"\b" + word + r"\b", lowered):
            raise ValueError("R484 的 SELECT 里出现禁词 " + word + ": " + body[:120])
    return body


def run_argv(argv, timeout: int = 180) -> tuple:
    """唯一的对外执行出口: 原样发出 argv, 返回 (rc, stdout, stderr)。"""
    proc = subprocess.run([str(item) for item in argv], capture_output=True, timeout=timeout)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def psql_select(sql: str, docker_bin: str = "docker") -> list:
    """进 pg 容器发一条只读 SELECT, 返回数据行 (psql 回显的 `SET` 不是数据, 剔掉)。"""
    guarded = assert_select_only(sql)
    argv = [docker_bin, "exec", PG_CONTAINER, "psql", "-U", PG_USER, "-d", PG_DB, "-At",
            "-v", "ON_ERROR_STOP=1", "-c", READ_ONLY_PREFIX, "-c", guarded]
    code, out, err = run_argv(argv)
    if code != 0:
        raise RuntimeError("psql 读数失败 rc=%d: %s" % (code, err.strip()[:300]))
    return [line for line in out.split(NL) if line.strip() and line.strip() != "SET"]


#: 台账侧唯一读数: 在 backend 容器里把 JSON **原样**吐成 stdout。
#: 🔴 这里 import 的是 stdlib 的 os/json, 不是 app.storage.sessions -- 见模块 docstring。
LEDGER_SNIPPET = (
    "import json,os;"
    "p=os.environ['SESSION_REGISTRY_PATH'];"
    "d=json.load(open(p,encoding='utf-8'));"
    "print(json.dumps(d.get('sessions',[]),sort_keys=True))"
)


def read_ledger(docker_bin: str = "docker") -> list:
    """直读容器内 JSON 台账, 返回条目 dict 列表。零 import、零实例化、因此零落盘。"""
    argv = [docker_bin, "exec", BACKEND_CONTAINER, "python3", "-c", LEDGER_SNIPPET]
    code, out, err = run_argv(argv)
    if code != 0:
        raise RuntimeError("台账读数失败 rc=%d: %s" % (code, err.strip()[:300]))
    records = json.loads(out.strip())
    if not isinstance(records, list):
        raise RuntimeError("台账形状不是 list: " + type(records).__name__)
    return records


#: 库侧两枚读数。都只 SELECT; 名字与条数一起带回, 孤儿那格就不必再猜。
SESSIONS_SQL = "SELECT id, COALESCE(user_id, E'<NULL>') FROM sessions ORDER BY id"
USERS_SQL = "SELECT username, role, COALESCE(department, E'<NULL>') FROM users ORDER BY username"
AUDIT_COUNT_SQL = "SELECT COUNT(*) FROM audit_events"


def read_sessions(docker_bin: str = "docker") -> list:
    rows = psql_select(SESSIONS_SQL, docker_bin)
    out = []
    for line in rows:
        sid, _, owner = line.partition("|")
        out.append({"session_id": sid, "user_id": owner})
    return out


def read_users(docker_bin: str = "docker") -> list:
    out = []
    for line in psql_select(USERS_SQL, docker_bin):
        parts = line.split("|")
        if len(parts) != 3:
            raise RuntimeError("users 读数形状不对: " + line[:120])
        out.append({"username": parts[0], "role": parts[1], "department": parts[2]})
    return out

# ============================================================================
# 纯函数内核: 零 I/O、零 docker、零环境依赖。测试件 import 的就是这一格,
# 所以「纸上判据」与「读数判据」用的是同一枚尺, 不是两份。
# ============================================================================

#: 读腿的谓词, 逐字对着 app/api/v1/chat.py:3879-3885 与 app/storage/sessions.py:85-87 写:
#: 出口遍历的是**库行**, 每行再过台账 owner 判定。台账独有条目因此永不放大出口。
def visible_ids(db_rows: list, ledger: list, name: str) -> set:
    """某一形在真出口上该看到的 session id 集合: 库行交台账 owner 命中。"""
    owned = {r["session_id"] for r in ledger
             if r.get("owner_id") == name and r.get("status") == "active"}
    return {row["session_id"] for row in db_rows if row["session_id"] in owned}


def member_diff(a: set, b: set) -> dict:
    """判据 3 的尺: 逐枚相等, 不是数长度。只数长度就分不开「总数对上而成员换了」。"""
    return {
        "count_a": len(a),
        "count_b": len(b),
        "only_in_a": sorted(a - b),
        "only_in_b": sorted(b - a),
        "members_equal": a == b,
    }


#: `departments=None` 那档的真源: 尺在 app/common/policy.py, 判定支在 app/rag/filters.py:119。
#: 🔴 本件不去 filters.py 里加第二把尺, 只把它今天给谁 `departments=None` 现读出来。
ADMIN_ROLES_RE = re.compile(r"_ADMINISTRATOR_ROLES\s*=\s*frozenset\(\{([^}]*)\}\)")


def administrator_roles(repo_root: Path = REPO_ROOT) -> frozenset:
    """现读 `_ADMINISTRATOR_ROLES` 的字面, 不 import app.common.policy (取证件零副作用)。"""
    source = (repo_root / "app" / "common" / "policy.py").read_text(encoding="utf-8")
    match = ADMIN_ROLES_RE.search(source)
    if match is None:
        raise RuntimeError("锚点漂了: 在 app/common/policy.py 里找不到 _ADMINISTRATOR_ROLES 的 frozenset 字面")
    return frozenset(re.findall(r"[a-z_]+", match.group(1)))


def ledger_view(db_rows: list, ledger: list, users: list, shapes: tuple = ("admin", "evalbot"),
                admin_roles: frozenset = frozenset({"admin"})) -> dict:
    """判据 1 与判据 2 的全部数, 由三张表算出, 一个数都不抄。

    每一形交回四列: 库里总行数 / 台账在册数 / 该形实际可见数 / 差在哪几行。
    第四列交回的是**成员** (session id 列表), 因为「总数对上而成员互换」正是本单要防的那形,
    只报数就分不开它。
    """
    db_ids = {row["session_id"] for row in db_rows}
    ledger_ids = {r["session_id"] for r in ledger}
    known = {u["username"] for u in users}

    # 先按「所有在册 principal」各算一遍可见成员: 判据 2 要说「任何 principal 都看不见孤儿」,
    # 那就要有「任何」这个并集, 而不是只并 admin/evalbot 两枚点名档。
    seen_by = {u["username"]: visible_ids(db_rows, ledger, u["username"]) for u in users}
    anyone_seen = set().union(*seen_by.values()) if seen_by else set()

    per_shape = {}
    for name in shapes:
        db_owned = {row["session_id"] for row in db_rows if row["user_id"] == name}
        led_owned = {r["session_id"] for r in ledger if r.get("owner_id") == name}
        seen = seen_by.get(name) or visible_ids(db_rows, ledger, name)
        per_shape[name] = {
            "db_rows": len(db_owned),
            "ledger_rows": len(led_owned),
            "visible": len(seen),
            "db_not_in_ledger": sorted(db_owned - seen),
            "extra_visible_ids": sorted(seen - db_owned),
            "ledger_not_in_db": sorted(led_owned - db_ids),
            "visible_ids": sorted(seen),
            "members_equal_to_db_owned": seen == db_owned,
        }

    # 第三形: `departments=None` 那档 (无部门不受限)。今天在库里落进这档的是 role 命中
    # _ADMINISTRATOR_ROLES 的账号。这一形的上界是「该档各成员可见并集」, 不是整表 --
    # 因为会话读腿过的是 app/storage/sessions.py 的 owner 等式, filters.py 那把尺根本不在这条腿上。
    nodept_names = sorted(u["username"] for u in users if u["role"] in admin_roles)
    nodept_union = set().union(*[seen_by[n] for n in nodept_names]) if nodept_names else set()

    orphan_names = sorted({row["user_id"] for row in db_rows if row["user_id"] not in known})
    orphans = {}
    for name in orphan_names:
        rows = {row["session_id"] for row in db_rows if row["user_id"] == name}
        orphans[name] = {
            "db_rows": len(rows),
            "session_ids": sorted(rows),
            "ledger_backed": sorted(rows & ledger_ids),
            "seen_by_any_principal": sorted(rows & anyone_seen),
        }
    orphan_ids = {sid for info in orphans.values() for sid in info["session_ids"]}

    # 未落账: 既不在任何在册档的可见并集里, 也不是孤儿 -- 今天该是 0 枚。非 0 就必须点名。
    unaccounted = sorted(db_ids - anyone_seen - orphan_ids)

    return {
        "db_total": len(db_rows),
        "ledger_total": len(ledger),
        "db_ids_unique": len(db_ids),
        "users": sorted(known),
        "shapes": per_shape,
        "nodept_member": nodept_names,
        "nodept_union_visible": len(nodept_union),
        "nodept_union_ids": sorted(nodept_union),
        "nodept_ceiling_if_filters_applied": len(db_rows),
        "orphans": orphans,
        "orphan_rows": len(orphan_ids),
        "orphan_seen_by_any_principal": len(orphan_ids & anyone_seen),
        "unaccounted_rows": unaccounted,
        "db_minus_ledger": sorted(db_ids - ledger_ids),
        "ledger_minus_db": sorted(ledger_ids - db_ids),
        "ledger_minus_db_owners": sorted({str(r.get("owner_id")) for r in ledger
                                          if r["session_id"] not in db_ids}),
        "owner_disagree": sorted({row["session_id"] for row in db_rows
                                  for r in ledger
                                  if r["session_id"] == row["session_id"]
                                  and str(r.get("owner_id")) != str(row["user_id"])}),
    }

# ============================================================================
# 锚点自检: 把「SQL 侧零 owner/部门 WHERE」这一格从注释升级成能跑的牙。
# ============================================================================

#: 从 _list_sessions 源码里抠出发给 sessions 的那句 SELECT。行号会漂, 所以只认函数名。
#: 🔴 这里不能用 r"""...""" 把三引号写进模式: 字面三引号会当场截断自己那个 raw 串。
_QUOTE3 = chr(34) * 3
LIST_SQL_RE = re.compile(
    "def _list_sessions\\(\\).*?conn\\.execute\\(\\s*" + _QUOTE3 + "(?P<sql>.*?)" + _QUOTE3,
    re.S,
)
#: 只看**外层**查询里出现即判「SQL 侧已经开始拦人」的词。
#: 🔴 不许拿整句去撞 "where": 子查询 `(SELECT COUNT(*) FROM session_messages WHERE session_id
#: = s.id AND role = 'user')` 里那枚 where 是数消息条数的, 不是拦人的。撞它会得出「SQL 侧已有
#: owner 过滤」这句假话, 而本单要钉的恰恰是它的反面。
OWNER_PREDICATE_TOKENS = ("where", "user_id", "owner_id", "department", "principal")


def check_list_sessions_sql(repo_root: Path = REPO_ROOT) -> dict:
    """现读 `_list_sessions` 源码, 交回那句 SELECT 与它**外层**的 owner/部门谓词命中。"""
    source = (repo_root / "app" / "api" / "v1" / "chat.py").read_text(encoding="utf-8")
    match = LIST_SQL_RE.search(source)
    if match is None:
        raise RuntimeError("锚点漂了: 在 chat.py 里找不到 _list_sessions 的 conn.execute(三引号 SELECT)")
    sql = " ".join(match.group("sql").split())
    lowered = sql.lower()
    head, marker, tail = lowered.partition("from sessions")
    if not marker:
        raise RuntimeError("锚点形状不对, SELECT 里没有 FROM sessions: " + sql[:160])
    hits = [token for token in OWNER_PREDICATE_TOKENS if token in tail]
    return {
        "sql": sql,
        "outer_tail": sql[sql.lower().index("from sessions"):],
        "subquery_head": head.strip(),
        "owner_predicate_hits": hits,
        "selects_whole_table": not hits,
    }


def check_read_leg_uses_no_user_id_column(repo_root: Path = REPO_ROOT) -> dict:
    """判据 1 的第三形依据: 整个 app/** 里有没有谁读 `sessions.user_id`。

    取的是**源码字面**而非注释: 注释里那三个字不算读者, 所以先剔注释行再扫。
    """
    readers = []
    for path in sorted((repo_root / "app").rglob("*.py")):
        try:
            lines = path.read_text(encoding="utf-8").split(NL)
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if re.search(r"\bs\.user_id\b|\bsessions\.user_id\b", stripped):
                readers.append("%s:%d: %s" % (path.relative_to(repo_root), number, stripped[:120]))
    return {"readers": readers, "count": len(readers)}


#: 真出口读数: 在 backend 容器里**本地签** JWT 再打 127.0.0.1:8001。
#: 🔴 不走 /api/v1/login -- 那会写 audit; 签 token 是纯函数, 一次数据库都不碰。
EXIT_SNIPPET = """
import json, sys, urllib.request
from app.common.auth import create_token
out = {}
for name in json.loads(sys.argv[1]):
    req = urllib.request.Request(
        "http://127.0.0.1:8001/api/v1/sessions",
        headers={"Authorization": "Bearer " + create_token(name)},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        rows = json.load(resp)["sessions"]
    out[name] = sorted(r.get("id", "") for r in rows)
print(json.dumps(out, sort_keys=True))
"""


def read_live_exit(names: list, docker_bin: str = "docker") -> dict:
    """对**在册**用户名取真出口成员集。零写库, 但只许用在 users 表里的名字 (见 docstring)。"""
    argv = [docker_bin, "exec", "-i", "-w", "/app", BACKEND_CONTAINER,
            "python3", "-", json.dumps(sorted(names), ensure_ascii=False)]
    stdin_bytes = EXIT_SNIPPET.encode("utf-8")
    proc = subprocess.run([str(item) for item in argv], input=stdin_bytes,
                          capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("真出口读数失败 rc=%d: %s"
                           % (proc.returncode, proc.stderr.decode("utf-8", "replace")[:300]))
    return json.loads(proc.stdout.decode("utf-8", "replace").strip())

# ============================================================================
# 对账: 判据 4「判红要有名字」的代码化。每一条红都带着 档名 / 谓词名 / 行数 / 逐枚 id。
# ============================================================================


def reconcile(view: dict) -> list:
    """把纯函数读数压成**具名**结论 (判据 4)。每条红都带 档名 / 谓词 / 行数 / 逐枚 id。"""
    fails = []
    for name, shape in sorted(view["shapes"].items()):
        # 🔴 「台账条目不在库」不算红: 台账今天没有解绑口 (app/storage/sessions.py 只有
        # bind / get_active / is_owned_by, 没有 unbind), 删会话只删库行, 所以「台账是库的超集」
        # 是既有形状, 本件只点名不判红。该红的是反向那格: 库里有行而台账没绑 => 那行对谁都
        # 不出口, 是静默丢失。
        if shape["db_not_in_ledger"]:
            fails.append(
                "档=%s 谓词=is_owned_by: 台账 owner_id == str(principal.user_id)"
                " | 库行未进台账 %d 枚=%s (这些行对任何 principal 都不出口)"
                % (name, len(shape["db_not_in_ledger"]), shape["db_not_in_ledger"][:5]))
        if shape["db_not_in_ledger"] or shape["extra_visible_ids"]:
            fails.append(
                "档=%s 谓词=出口遍历库行再交台账 | 可见成员 != 库里该档成员: 可见 %d / 库里 %d"
                " | 该档少 %d 枚=%s | 该档多 %d 枚=%s"
                % (name, shape["visible"], shape["db_rows"],
                   len(shape["db_not_in_ledger"]), shape["db_not_in_ledger"][:5],
                   len(shape["extra_visible_ids"]), shape["extra_visible_ids"][:5]))
    if view["owner_disagree"]:
        fails.append("档=整表 谓词=库里 user_id 应等于台账 owner_id (今天同为用户名 namespace) | 不等 %d 枚=%s"
                     % (len(view["owner_disagree"]), view["owner_disagree"][:5]))
    if view["orphan_seen_by_any_principal"]:
        named = {k: v["seen_by_any_principal"] for k, v in view["orphans"].items()
                 if v["seen_by_any_principal"]}
        fails.append("档=孤儿(库里 user_id 不在 users) 谓词=任何在册 principal 都不得读回 | 漏 %d 枚 | 逐枚=%s"
                     % (view["orphan_seen_by_any_principal"], named))
    if view["unaccounted_rows"]:
        fails.append("档=整表 谓词=每行必须落进「在册可见 / 孤儿 / 未落账」三格之一 | 未落账 %d 枚=%s"
                     % (len(view["unaccounted_rows"]), view["unaccounted_rows"][:5]))
    accounted = view["nodept_union_visible"] + view["orphan_rows"] + len(view["unaccounted_rows"])
    if accounted != view["db_total"]:
        fails.append("档=整表 谓词=总账算式 在册可见+孤儿+未落账==库里行数 | %d+%d+%d=%d != %d"
                     % (view["nodept_union_visible"], view["orphan_rows"],
                        len(view["unaccounted_rows"]), accounted, view["db_total"]))
    return fails


def render(view: dict, anchors: dict, live) -> str:
    lines = ["", "== R484 会话读腿归属取证 (只读) =="]
    lines.append("库里 sessions: %d 行 (唯一 id %d)   JSON 台账: %d 条   users: %d 枚=%s"
                 % (view["db_total"], view["db_ids_unique"], view["ledger_total"],
                    len(view["users"]), ",".join(view["users"])))
    lines.append(NL + "判据1 · 逐形四列 (差在哪几行 = 成员, 不是数)")
    lines.append("  %-10s %8s %8s %8s  %s" % ("档", "库里行数", "台账在册", "实际可见", "差"))
    for name in sorted(view["shapes"]):
        shape = view["shapes"][name]
        gap = []
        if shape["ledger_not_in_db"]:
            gap.append("台账独有 %d 枚(库里无此行, 因此永不进出口)" % len(shape["ledger_not_in_db"]))
        if shape["db_not_in_ledger"]:
            gap.append("库行未在册 %d 枚=%s" % (len(shape["db_not_in_ledger"]),
                                                shape["db_not_in_ledger"][:3]))
        lines.append("  %-10s %8d %8d %8d  %s"
                     % (name, shape["db_rows"], shape["ledger_rows"], shape["visible"],
                        "; ".join(gap) or "无差"))
    lines.append("  %-10s %8d %8s %8d  成员=%s | 该档上界是成员可见并集, 不是整表: 整表 %d 枚, 差 %d 枚"
                 % ("无部门档", view["db_total"], "-", view["nodept_union_visible"],
                    ",".join(view["nodept_member"]) or "(空)", view["db_total"],
                    view["db_total"] - view["nodept_union_visible"]))
    lines.append(NL + "判据2 · 孤儿逐枚点名 (库里 user_id 已不在 users 表)")
    for name in sorted(view["orphans"]):
        info = view["orphans"][name]
        lines.append("  %-22s 库里 %2d 枚 | 台账仍绑 %2d 枚 | 被任何在册 principal 读回 %d 枚"
                     % (name, info["db_rows"], len(info["ledger_backed"]),
                        len(info["seen_by_any_principal"])))
    lines.append("  孤儿合计 %d 枚; 台账总条目 - 库行数 = %d 枚, 属主=%s"
                 % (view["orphan_rows"], len(view["ledger_minus_db"]),
                    ",".join(sorted(set(view["ledger_minus_db_owners"]))) or "-"))
    lines.append("  库里有而台账无(该形可见数=0): %d 枚; 库里 user_id 与台账 owner_id 不等的行: %d 枚"
                 % (len(view["db_minus_ledger"]), len(view["owner_disagree"])))
    lines.append(NL + "锚点自检")
    lines.append("  _list_sessions 外层(From sessions 之后): %s" % anchors["outer_tail"][:160])
    lines.append("  外层 owner/部门谓词命中=%s -> 整表捞=%s"
                 % (anchors["owner_predicate_hits"] or "无", anchors["selects_whole_table"]))
    readers = anchors["user_id_readers"]
    lines.append("  全仓 app/** 里读 sessions.user_id 的代码行: %d 枚 %s"
                 % (readers["count"], readers["readers"] or "[]"))
    if live is not None:
        lines.append(NL + "--live 旁证 (真出口成员集 vs 本件算出的该见集合)")
        lines.append("  audit_events 前后 delta = %s (必须 0, 否则这条读数道不是零写入)"
                     % live.get("_audit_events_delta"))
        for name in sorted(key for key in live if not key.startswith("_")):
            lines.append("  %-10s live=%s computed=%s 成员相等=%s"
                         % (name, live[name]["live_visible"], live[name]["computed_visible"],
                            live[name]["members_equal"]))
    fails = reconcile(view)
    lines.append(NL + "对账: %s" % ("闭合" if not fails else "不闭合 ->") )
    lines.extend(("  RED " + item) for item in fails)
    return NL.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R484 会话读腿归属取证 (只读)")
    parser.add_argument("--json", action="store_true", help="把 view/anchors 原样打成 JSON")
    parser.add_argument("--live", action="store_true",
                        help="进 backend 容器本地签 JWT 打真出口, 与 --shapes 对拍成员")
    parser.add_argument("--shapes", default="admin,evalbot", help="逗号分隔的在册用户名")
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--fail-on-open", action="store_true", help="对账不闭合就退 1")
    args = parser.parse_args(argv)

    shapes = tuple(name for name in args.shapes.split(",") if name)
    db_rows = read_sessions(args.docker)
    ledger = read_ledger(args.docker)
    users = read_users(args.docker)
    view = ledger_view(db_rows, ledger, users, shapes, administrator_roles())
    anchors = check_list_sessions_sql()
    anchors["user_id_readers"] = check_read_leg_uses_no_user_id_column()

    live = None
    if args.live:
        known = {u["username"] for u in users}
        missing = [name for name in shapes if name not in known]
        if missing:
            raise RuntimeError("--live 只对在册用户名签发; %s 不在 users 表, 打过去会写 audit" % missing)
        # 零写入自证: 真出口只读, 所以 audit_events 前后计数必须一字不动。
        audit_before = int(psql_select(AUDIT_COUNT_SQL, args.docker)[0])
        counts = read_live_exit(list(shapes), args.docker)
        audit_after = int(psql_select(AUDIT_COUNT_SQL, args.docker)[0])
        if audit_after != audit_before:
            raise RuntimeError("--live 打出口前后 audit_events 从 %d 变到 %d: 这条读数道不是零写入"
                               % (audit_before, audit_after))
        live = {name: {"live_visible": len(ids),
                       "computed_visible": view["shapes"][name]["visible"],
                       "members_equal": sorted(ids) == view["shapes"][name]["visible_ids"]}
                for name, ids in counts.items()}
        live["_audit_events_delta"] = audit_after - audit_before

    print(json.dumps({"view": view, "anchors": anchors, "live": live,
                      "fails": reconcile(view)},
                     ensure_ascii=False, sort_keys=True, default=str)
             if args.json else render(view, anchors, live))
    return 1 if (args.fail_on_open and reconcile(view)) else 0


if __name__ == "__main__":
    raise SystemExit(main())