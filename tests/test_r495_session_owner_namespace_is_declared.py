# -*- coding: utf-8 -*-
"""R495 常驻闸：会话归属键用哪套命名空间，从此是**声明**，不是 SELECT 恰好少一列（判据②③④）。

病（现读自基点 438d67d，三格串起来是一句偶然）：

* `app/common/auth.py::get_user` 那句 SELECT 只交 `username, role, department`，**不含 `id`**；
* `app/agents/contracts.py::Principal.from_user` 取的是 `user.get("id") or user.get("username")`，
  所以 `principal.user_id` 今天**恰好**等于用户名；
* `app/storage/sessions.py` 的归属判定吃的正是这枚 `user_id`，JSON 台账里的 `owner_id` 因此
  也是用户名——两边同一命名空间，比得上，`GET /api/v1/sessions` 今天是对的。

🔴 谁给那句 SELECT 补上 `id`（前端要 user id、审计要 user id 都是极自然的改动），
`principal.user_id` 当场翻成 bigint 字符串，台账零命中，会话读腿对**全员**静默回 `[]`：
状态码 200、不报错、不告警。R484 的 K5 刀证明这条腿今天有牙（红 14 枚），但那 14 枚咬的是
假表；生产代码里这层承重当时没有任何显式约定。

R495 把这层承重搬到纸面上，且只搬一次：

| 件 | 它是什么 |
| --- | --- |
| `app/storage/sessions.py::SESSION_OWNER_NAMESPACE` | 台账按哪套键认人——全仓唯一一处把这句话写成字面 |
| `app/storage/sessions.py::session_owner_key()` | 归属键的唯一算式：写腿与读腿都从这一处取键，不许长出第二把尺 |
| `app/storage/sessions.py::session_owner_namespace()` | 现读一枚主体的键属于哪套；只出证词，不判归属 |
| `app/common/auth.py::USER_LOOKUP_COLUMNS` / `USER_LOOKUP_SQL` | 查人交出哪些列：内存表与 PG 两支从此共用同一枚声明 |
| `SessionOwnerNamespaceError` | 命名空间被换掉时写腿当场抛（它 `isinstance` 那格是 `PermissionError`，对外沿用 chat.py 既有的 403 `permission_denied`，本单不新造码） |

读腿那一半为什么不 raise：`tests/test_r484_session_read_leg_owner_filter.py:406` 把「bigint
那套 namespace 不该被台账认得」钉成了 `is False`，把它改成报错就是拿一种新形状换掉既有判定。
R495 保留那格 `False`，但补一条 ERROR 证词——「命名空间漂了」与「这个人确实没有会话」从此
在日志里长得不一样，200 + `[]` 不再是无人看守的形状。

反证三刀（判据④，全走 R253 影子根：变异只落 `%TEMP%` 副本，被跟踪文件全程只读）：
刀一 给真源那句 SELECT 补 `id`；刀二 把归属判定改成恒真；刀三 把新增的显式真源整个摘掉，
退回基点那份「靠 SELECT 形状」。每把都在窗内点名「哪几格必须红」，落下去不红就当场 fail。
整轮复跑法（同机别跑全量门，本单只跑会话归属这一簇）：

    $env:R495_KNIFE = "one"   # 或 "two" / "three"
    python -m pytest <会话归属簇> -p tests.test_r495_session_owner_namespace_is_declared -o addopts= -q

没有环境变量时上面两枚钩子一声不响，本件就是十二枚常驻钉。
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import uuid
from contextlib import contextmanager

import pytest

from app.agents.contracts import Principal
from app.common import auth
from app.storage import sessions as sessions_module
from tests import _temp_edit_overlay as overlay
from tests import test_r466_mutation_does_not_leak_into_live_module as r466

REPO = overlay.REPO
AUTH_REL = "app/common/auth.py"
SESSIONS_REL = "app/storage/sessions.py"
CHAT_REL = "app/api/v1/chat.py"
KNIFE_ENV = "R495_KNIFE"

ADMIN = "admin"
EVALBOT = "evalbot"
BOB = "r495-bob"
#: R495 之前落盘的那份台账原件的形状：四列、`owner_id` 是用户名字符串、一个新键都不许有。
#: 这格形状不是随手编的——它与 `tests/test_r484_session_read_leg_owner_filter.py` 直读
#: `registry.metadata_path` 拿到的字节同构。
LEGACY_ROWS = (
    {"session_id": "r495-sess-admin-1", "owner_id": ADMIN, "status": "active",
     "created_at": "2026-09-29T00:00:00+00:00"},
    {"session_id": "r495-sess-admin-2", "owner_id": ADMIN, "status": "active",
     "created_at": "2026-09-29T00:00:01+00:00"},
    {"session_id": "r495-sess-eval-1", "owner_id": EVALBOT, "status": "active",
     "created_at": "2026-09-29T00:00:02+00:00"},
)
#: 台账命名空间这一句话在全仓被「写成字面」的那一形（不是引用，是赋值）。
NAMESPACE_ASSIGNMENT = "SESSION_OWNER_NAMESPACE = "

_SCAN_MEMO: dict = {}


def _scan_key():
    """扫描缓存的键必须带上影子副本自己：同一枚文件上换一刀，窗名不变、字节却变了。

    只用 `open_windows()` 当键会串刀——刀二在 sessions.py 上留过一次扫描，刀三进门时窗名
    一模一样，于是读到刀二那份还带着显式真源的字，「摘掉真源」那一格就假绿了。
    """
    windows = overlay.open_windows()
    if not windows:
        return ("disk",)
    return ("shadow",) + tuple(
        (rel, overlay.sha16_of_bytes(overlay.SHADOW.read_bytes(rel))) for rel in windows
    )


def _src(rel: str) -> str:
    """窗内读影子副本、窗外读盘上的被跟踪文件：同一份解析代码，两种视图（R253 的口径）。"""
    return overlay.authoritative_text(rel)


def _app_sources() -> list:
    """整棵 `app/**` 的当前该算数的那份字节。按开窗状态缓存，刀下的重扫不会读到盘上的旧字。"""
    key = _scan_key()
    cached = _SCAN_MEMO.get(key)
    if cached is not None:
        return cached
    out = []
    for path in sorted((REPO / "app").rglob("*.py")):
        rel = path.relative_to(REPO).as_posix()
        out.append((rel, _src(rel)))
    _SCAN_MEMO[key] = out
    return out


class _Recorder:
    """替 sessions 模块挡住 logger：证词要数得出来，不能依赖 handler 挂没挂。"""

    def __init__(self) -> None:
        self.messages: list = []

    def _sink(self, level, message, args):
        self.messages.append("%s: %s" % (level, message % args if args else message))

    def error(self, message, *args):
        self._sink("error", message, args)

    def warning(self, message, *args):
        self._sink("warning", message, args)

    def info(self, message, *args):
        self._sink("info", message, args)

    def debug(self, message, *args):
        self._sink("debug", message, args)

    @property
    def drift_lines(self) -> list:
        return [line for line in self.messages if "命名空间漂移" in line]


def _use_recorder(monkeypatch) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(sessions_module, "logger", recorder)
    return recorder


def _username_principal(username: str = ADMIN, role: str = "admin") -> Principal:
    """今天真源交出的形状：查人不带 id，所以 principal.user_id 就是用户名。"""
    return Principal.from_user({"username": username, "role": role, "department": ""})


def _id_namespace_principal(username: str = ADMIN, user_id: int = 17) -> Principal:
    """刀一那一形的主体：SELECT 补了 id，`from_user` 当场优先取 id，键翻成 bigint 字符串。"""
    return Principal.from_user(
        {"id": user_id, "username": username, "role": "admin", "department": ""}
    )


def _legacy_registry(tmp_path):
    """拿 R495 之前的台账字节起一枚真 registry（`SessionRegistry` 现取，刀下不读旧绑定）。"""
    path = tmp_path / "r495-legacy-ledger.json"
    path.write_text(json.dumps({"sessions": [dict(row) for row in LEGACY_ROWS]}), encoding="utf-8")
    return sessions_module.SessionRegistry(path)


def _memory_username(username: str) -> str:
    """在进程内用户表里造一个人，交回用户名；调用方负责收尾（`_forget_user`）。"""
    name = "%s-%s" % (username, uuid.uuid4().hex[:8])
    created, note = auth.create_user(name, "r495-secret", "staff")
    assert created, "进程内用户表造人失败：%s" % note
    return name


def _forget_user(username: str) -> None:
    auth._MEM_USERS.pop(username, None)


def _function_source(rel: str, name: str) -> str:
    """按函数名取源码段（行号会漂，本件一律只认名字与文本）。"""
    tree = ast.parse(_src(rel))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = _src(rel).splitlines()[node.lineno - 1: node.end_lineno]
            return chr(10).join(segment)
    raise AssertionError("%s 里找不到函数 %s：锚点漂了" % (rel, name))


# ============================================================================
# 判据② · 唯一真源：一句话说清「归属键＝用户名」，全仓只写一次
# ============================================================================


def _check_namespace_declared_once():
    """台账命名空间只有一枚赋值，且它说的就是「用户名」。"""
    hits = [rel for rel, text in _app_sources() if NAMESPACE_ASSIGNMENT in text]
    assert hits == [SESSIONS_REL], (
        "归属键命名空间的字面声明今天有 %d 处=%s（要求恰好 1 处，且在 %s）"
        % (len(hits), hits, SESSIONS_REL)
    )
    declared = getattr(sessions_module, "SESSION_OWNER_NAMESPACE", None)
    assert declared == "username", (
        "SESSION_OWNER_NAMESPACE 今天不再是 'username'（读到 %r）：台账那 343 枚按用户名写下"
        "的归属键要重画" % declared
    )


def _check_owner_key_formula_is_unique():
    """归属键的算式只有一枚：`session_owner_key` 全仓定义一次，别处一根手指都不碰 user_id。"""
    defs = [rel for rel, text in _app_sources() if "def session_owner_key(" in text]
    assert defs == [SESSIONS_REL], (
        "归属键算式今天被 %d 枚模块定义=%s（要求恰好 1 枚，且在 %s）"
        % (len(defs), defs, SESSIONS_REL)
    )
    source = _src(SESSIONS_REL)
    assert "str(principal.user_id)" not in source, (
        "谓词=session_owner_key 唯一算式 | app/storage/sessions.py 里又长出裸的 "
        "str(principal.user_id)：那是第二把尺，归属层重新退回靠 SELECT 形状"
    )
    stray = _user_id_reads_outside_the_formula()
    assert stray == [], (
        "谓词=session_owner_key 唯一算式 | 除算式本身之外还有 %d 处直接读 principal.user_id：%s"
        % (len(stray), stray)
    )


def _user_id_reads_outside_the_formula() -> list:
    """现读 sessions.py：`session_owner_key` 之外还有谁读 `principal.user_id`。"""
    tree = ast.parse(_src(SESSIONS_REL))
    bad = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "session_owner_key":
            continue
        for attr in ast.walk(node):
            if isinstance(attr, ast.Attribute) and attr.attr == "user_id":
                bad.append(attr.lineno or 0)
    return sorted(bad)


def _check_granting_comparison_is_one():
    """判归属那一句比较式全仓只长两枚：读腿一枚、写腿的重绑检查一枚，两边都吃同一枚键。"""
    source = _src(SESSIONS_REL)
    read_leg = source.count("record.owner_id == session_owner_key(principal)")
    write_leg = source.count("existing.owner_id != owner_key")
    assert read_leg == 1, (
        "谓词=读腿归属比较式 | 今天命中 %d 处（要求恰好 1 处）：读腿不再只认 session_owner_key"
        % read_leg
    )
    assert write_leg == 1, (
        "谓词=写腿重绑比较式 | 今天命中 %d 处（要求恰好 1 处）：bind 的闸门与读腿分叉了"
        % write_leg
    )


# ============================================================================
# 判据② · 真源那句 SELECT 对账
# ============================================================================


def _check_user_lookup_declares_no_id():
    """查人交出哪些列是声明；这枚声明今天不许带 `id`，否则 principal.user_id 就换命名空间。"""
    columns = tuple(auth.USER_LOOKUP_COLUMNS)
    assert "id" not in columns, (
        "真源 SELECT 交出 %s：principal.user_id 已翻成 bigint 那套键，而台账 "
        "SESSION_OWNER_NAMESPACE 仍声明 username——补 id 必须与台账迁移同单进行"
        % (columns,)
    )
    selected = auth.USER_LOOKUP_SQL.partition("SELECT")[2].partition("FROM")[0]
    spelled = tuple(part.strip() for part in selected.split(","))
    assert spelled == columns, (
        "查人的列名声明 %s 与它拼出来的 SQL 实际交出的列 %s 分叉了" % (columns, spelled)
    )
    assert " FROM users WHERE username = %s" in auth.USER_LOOKUP_SQL, (
        "USER_LOOKUP_SQL 不再是对 users 按用户名取那一枚：本件记的对账对象换了"
    )
    body = _function_source(AUTH_REL, "get_user")
    assert "USER_LOOKUP_SQL" in body and "_project_user_row" in body, (
        "get_user 不再吃 USER_LOOKUP_SQL/_project_user_row：列名声明被绕过，成了第二份形状"
    )
    assert "SELECT" not in body, (
        "get_user 里手写了一句 SELECT：真源不再是列名声明，命名空间对账会读空"
    )


def _check_real_lookup_hands_the_declared_namespace():
    """拿**真** auth.create_user / auth.get_user 造一枚主体，现读它的归属键在不在声明的那套里。"""
    username = _memory_username("r495-ns")
    try:
        row = auth.get_user(username)
        assert row is not None, "进程内用户表刚造的人现读不到"
        assert tuple(sorted(row)) == tuple(sorted(auth.USER_LOOKUP_COLUMNS)), (
            "get_user 交回的键 %s 与列名声明 %s 不一致：两支（内存表 / PG）又各写各的了"
            % (sorted(row), sorted(auth.USER_LOOKUP_COLUMNS))
        )
        principal = Principal.from_user(row)
        namespace = sessions_module.session_owner_namespace(principal)
        assert namespace == sessions_module.SESSION_OWNER_NAMESPACE, (
            "真源查人交回的主体属于命名空间 %r，而台账声明的是 %r：这两句此刻开始各说各话，"
            "会话读腿会对全员回 200 + []" % (namespace, sessions_module.SESSION_OWNER_NAMESPACE)
        )
        assert sessions_module.session_owner_key(principal) == username, (
            "归属键不再等于用户名（读到 %r）" % sessions_module.session_owner_key(principal)
        )
    finally:
        _forget_user(username)


# ============================================================================
# 判据③ · fail-loud
# ============================================================================


def _check_write_leg_refuses_a_swapped_namespace(tmp_path):
    """命名空间一换：写腿当场抛，台账字节一个字都不许多长出一套键。"""
    registry = _legacy_registry(tmp_path)
    before = registry.metadata_path.read_bytes()
    error = sessions_module.SessionOwnerNamespaceError
    with pytest.raises(error) as refused:
        registry.bind("r495-sess-new", _id_namespace_principal(ADMIN))
    message = str(refused.value)
    assert "username" in message and "user_id" in message, (
        "报错没说清是从哪套键换到哪套键：%s" % message
    )
    assert ADMIN not in message and EVALBOT not in message, (
        "成因里落了用户名：这条读腿别人家的会话也会走到，主体不该进这行字"
    )
    assert registry.metadata_path.read_bytes() == before, (
        "拒写之外还改了台账字节：这一格应当零写入"
    )


def _check_outward_code_is_the_existing_one():
    """这不是对外新码：它借的正是 chat.py 写腿那条 `except PermissionError` → 403 的口径。"""
    assert issubclass(sessions_module.SessionOwnerNamespaceError, PermissionError), (
        "SessionOwnerNamespaceError 不再是 PermissionError 的子类：它就落不进 chat.py 那格"
        "既有的 403 permission_denied，等于对外新造了一枚码"
    )
    ask_leg = _function_source(CHAT_REL, "ask")
    bind_line = [
        line for line in ask_leg.splitlines() if "session_registry.bind(" in line
    ]
    assert bind_line, "ask 腿里找不到 session_registry.bind()：写腿的接法换了，本件要重画"
    assert "except PermissionError" in ask_leg and "permission_denied" in ask_leg, (
        "ask 腿不再把 bind 的 PermissionError 折成 permission_denied：本单沿用不了既有码，"
        "fail-loud 会退化成裸 500"
    )
    invented = [rel for rel, text in _app_sources() if 'detail="session_owner_namespace' in text]
    assert invented == [], "app/** 里新造了对外码 %s：本单只许借用既有那格" % invented


def _check_read_leg_stays_a_denial_with_a_testimony(tmp_path, monkeypatch):
    """读腿保留 R484 钉过的那格 False，但必须留下证词：漂了与「确实没有」不再是同一张脸。"""
    recorder = _use_recorder(monkeypatch)
    registry = _legacy_registry(tmp_path)
    assert registry.is_owned_by("r495-sess-admin-1", _id_namespace_principal(ADMIN)) is False, (
        "台账竟然认得 bigint 那套 namespace：R484:406 那格判定被换掉了"
    )
    assert recorder.drift_lines, (
        "读腿在命名空间漂移时一声不响：200 + [] 又变回无人看守的形状"
    )
    recorder.messages.clear()
    assert registry.is_owned_by("r495-sess-eval-1", _username_principal(BOB)) is False, (
        "别人的会话竟然判成了自己的"
    )
    assert recorder.drift_lines == [], (
        "「这个人确实没有会话」那一形被记成了命名空间漂移：证词就不是漂的证词了：%s"
        % recorder.drift_lines
    )


def _check_a_wholesale_namespace_migration_still_answers(tmp_path, monkeypatch):
    """要么归属仍然正确：整套键一起换（新台账、读写同源自 user_id）时不报错也不清空。"""
    recorder = _use_recorder(monkeypatch)
    registry = sessions_module.SessionRegistry(tmp_path / "r495-fresh-ledger.json")
    principal = _id_namespace_principal("r495-fresh-owner", user_id=99)
    record = registry.bind("r495-fresh-session", principal)
    assert record.owner_id == sessions_module.session_owner_key(principal) == "99", (
        "新台账的归属键不再是那一枚算式的产物：读写两头分叉了"
    )
    assert registry.is_owned_by("r495-fresh-session", principal) is True, (
        "命名空间整套一致时归属应当成立，却读成了不属于"
    )
    assert recorder.drift_lines == [], (
        "一套干净的键（台账里没有任何按用户名写下的行）被误判成漂移：%s" % recorder.drift_lines
    )


def _check_foreign_principals_learn_nothing(tmp_path):
    """显式化不许把闸门改松：别人的会话对别人仍然像不存在。"""
    registry = _legacy_registry(tmp_path)
    bob = _username_principal(BOB)
    for row in LEGACY_ROWS:
        assert registry.is_owned_by(row["session_id"], bob) is False, (
            "谓词=is_owned_by(归属键=用户名) | 档=%s 外来主体读到了 %s"
            % (BOB, row["session_id"])
        )
    with pytest.raises(PermissionError):
        registry.bind("r495-sess-admin-1", bob)
    assert "r495-sess-admin-1" in {
        record["session_id"] for record in json.loads(
            registry.metadata_path.read_text(encoding="utf-8")
        )["sessions"]
    }, "重绑被拒时不该动台账，那一枚条目应当还在原处"


# ============================================================================
# 十二枚常驻钉（窗外真状态）
# ============================================================================


def test_the_owner_namespace_is_declared_in_exactly_one_place():
    _check_namespace_declared_once()


def test_the_owner_key_formula_is_the_only_one_in_the_repository():
    _check_owner_key_formula_is_unique()


def test_the_granting_comparison_is_one_read_leg_and_one_rebind_gate():
    _check_granting_comparison_is_one()


def test_the_real_user_lookup_declares_no_id_column():
    _check_user_lookup_declares_no_id()


def test_a_principal_built_by_the_real_lookup_is_username_keyed():
    _check_real_lookup_hands_the_declared_namespace()


def test_the_write_leg_refuses_a_swapped_owner_namespace(tmp_path):
    _check_write_leg_refuses_a_swapped_namespace(tmp_path)


def test_the_refusal_borrows_the_existing_outward_code():
    _check_outward_code_is_the_existing_one()


def test_the_read_leg_stays_a_denial_and_leaves_a_testimony(tmp_path, monkeypatch):
    _check_read_leg_stays_a_denial_with_a_testimony(tmp_path, monkeypatch)


def test_a_wholesale_namespace_migration_still_answers_correctly(tmp_path, monkeypatch):
    _check_a_wholesale_namespace_migration_still_answers(tmp_path, monkeypatch)


def test_foreign_principals_still_learn_nothing(tmp_path):
    _check_foreign_principals_learn_nothing(tmp_path)


def test_the_ledger_bytes_r495_reads_are_still_the_pre_r495_shape(tmp_path):
    """显式化不许改台账格式：R495 之前落盘的字节要能被今天原样读回来。"""
    registry = _legacy_registry(tmp_path)
    payload = json.loads(registry.metadata_path.read_text(encoding="utf-8"))
    assert [row["session_id"] for row in payload["sessions"]] == [
        row["session_id"] for row in LEGACY_ROWS
    ], "台账条目集合被改写"
    assert {tuple(sorted(row)) for row in payload["sessions"]} == {
        ("created_at", "owner_id", "session_id", "status")
    }, "R495 给台账长出了新列——旧文件会被 SessionRecord(**raw) 拒读，那是假话式退役"
    assert registry.get_active("r495-sess-admin-1") is not None


def test_the_namespace_word_is_not_reinvented_in_the_user_store():
    """`app/common/auth.py` 只声明列名，不再复述命名空间那句话；否则真源就有两枚。"""
    source = _src(AUTH_REL)
    assert NAMESPACE_ASSIGNMENT not in source, "auth.py 里又赋了一枚 SESSION_OWNER_NAMESPACE"
    assert "SESSION_OWNER_NAMESPACE" in source, (
        "auth.py 不再指向台账那枚真源：列名声明与命名空间声明失去了联系"
    )

# ============================================================================
# 判据④ · 三把反证刀（R253 影子根：变异只落 %TEMP% 副本，被跟踪文件全程只读）
# ============================================================================


#: 「改前」锚在 R495 的基点 sha 上，不锚 HEAD。本单并入主干之后 HEAD 就含本单了：锚 HEAD 现取的
#: 那份字里已经写着 SESSION_OWNER_NAMESPACE，于是 fixture 的「改前不成立」当场炸 5 枚 error，
#: 刀三换上的替换文本又与原文一模一样 ⇒ 空转（09-29 并树 8d228be 后干净树实测 1 failed / 5 errors，
#: 事故 #96 同族第二例，由「并树后必须干净态复跑」这条新规当场抓获）。
PRISTINE_BASE = "438d67d"


def _pristine_text(rel: str) -> str:
    """从 git 对象库现取**基点锚 sha** 那份字：刀三与「改前／改后」对照都用它。"""
    out = subprocess.run(
        ["git", "show", PRISTINE_BASE + ":" + rel],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert out.returncode == 0, "git show %s:%s 失败：%s" % (PRISTINE_BASE, rel, out.stderr)
    if rel == SESSIONS_REL:
        assert "SESSION_OWNER_NAMESPACE" not in out.stdout, (
            "锚 sha %s 交回的 %s 已经带着 R495 的显式真源：锚漂了或历史被改写，"
            "本件的「改前」与刀三的替换文本都不成立" % (PRISTINE_BASE, rel))
    return out.stdout


class _Knife(overlay.ShadowEdit):
    """一扇 R495 的反证窗：锚点命中不是恰好一处就整片不落；变异文本先过 compile()。"""

    tag = "r495"
    #: 🔴 R556：三把刀仍要被真执行（写腿与读腿真跑一遍），但不再进门 exec 整份码体——由
    #: ``_knife_window`` 走 ``r466.install_mutation``，只把**变了的那几枚顶层绑定**装进活模块；
    #: 落在 ``SessionRegistry`` 类体里的那一把由姿势件的类支在活命名空间里现编那一枚类语句，
    #: 方法体的 ``__globals__`` 仍是这一枚模块的字典，窗内 ``_use_recorder`` 装的替身照样看得见。
    execs_module = False

    def __init__(self, path, edits=(), replacement=None):
        super().__init__(path)
        self.edits = [(tuple(old), tuple(new)) for old, new in edits]
        self.replacement = replacement

    def mutate(self, text):
        if self.replacement is not None:
            assert text != self.replacement, "影子副本与替换文本一模一样：这扇窗是空转"
            compile(self.replacement, str(self.path), "exec")
            return self.replacement
        newline = chr(13) + chr(10) if chr(13) + chr(10) in text else chr(10)
        mutated = text
        for old, new in self.edits:
            needle = newline.join(old)
            hits = mutated.count(needle)
            assert hits == 1, (
                "%s 里锚点命中 %d 处（要求恰好 1 处）：%r —— 变异整体不落"
                % (self.path.name, hits, old[0])
            )
            mutated = mutated.replace(needle, newline.join(new), 1)
        compile(mutated, str(self.path), "exec")
        return mutated


#: 刀一：真源那句查人 SELECT 补上 `id`。这是最自然的一次改动，也正是本单要当场咬住的那一次。
def KNIFE_ONE():
    return _Knife(
        REPO / AUTH_REL,
        edits=[
            (
                ('USER_LOOKUP_COLUMNS: tuple[str, ...] = ("username", "role", "department")',),
                ('USER_LOOKUP_COLUMNS: tuple[str, ...] = ("id", "username", "role", "department")',),
            )
        ],
    )


#: 刀二：把读腿那句归属判定改成恒真（松绑闸门，外来主体从此读得到别人的会话）。
def KNIFE_TWO():
    return _Knife(
        REPO / SESSIONS_REL,
        edits=[
            (
                ("        owned = record.owner_id == session_owner_key(principal)",),
                ("        owned = True  # 刀二：归属判定恒真",),
            )
        ],
    )


#: 刀三：把新增的显式真源整个摘掉，退回基点那份「靠 SELECT 恰好少一列」。
def KNIFE_THREE():
    return _Knife(REPO / SESSIONS_REL, replacement=_pristine_text(SESSIONS_REL))


@contextmanager
def _knife_window(builder):
    """R556 新口径的开窗器：影子副本落变异 -> 只装变了的那几枚顶层绑定 -> 出窗逐枚装回。

    交回 ``(window, info)`` 而不只是 info：``_replay`` 收尾要报 ``window.rel``（被跟踪文件全程
    只读那一格凭它点名），旧写法是 `window = builder(); with window as info:`，两者等价。
    """
    window = builder()
    with window as info:
        module = overlay.module_of(window.rel)
        assert module is not None, (
            "%s 对应的模块还没被导入：变异无处可装，这把刀是空的" % window.rel)
        with r466.install_mutation(module, window.path, info.read_text()) as mutant:
            info["installed_bindings"] = sorted(mutant)
            yield window, info


_KNIFE_BUILDERS = {"one": KNIFE_ONE, "two": KNIFE_TWO, "three": KNIFE_THREE}
_REDS = (AssertionError, pytest.fail.Exception)


def _checks(tmp_path, monkeypatch):
    """本单的判据集合：反证只准在这里列一遍，窗外是十二枚常驻钉，窗内是「红了几格」。"""
    return [
        ("命名空间声明唯一", lambda: _check_namespace_declared_once()),
        ("归属键算式唯一", lambda: _check_owner_key_formula_is_unique()),
        ("归属比较式只两枚", lambda: _check_granting_comparison_is_one()),
        ("真源SELECT对账", lambda: _check_user_lookup_declares_no_id()),
        ("真principal形状", lambda: _check_real_lookup_hands_the_declared_namespace()),
        ("写腿拒换命名空间", lambda: _check_write_leg_refuses_a_swapped_namespace(tmp_path)),
        ("读腿的证词", lambda: _check_read_leg_stays_a_denial_with_a_testimony(tmp_path, monkeypatch)),
        ("既有对外码", lambda: _check_outward_code_is_the_existing_one()),
        ("外来主体学不到东西", lambda: _check_foreign_principals_learn_nothing(tmp_path)),
        ("整套迁移仍正确", lambda: _check_a_wholesale_namespace_migration_still_answers(tmp_path, monkeypatch)),
    ]


def _replay(builder, must_go_red, tmp_path, monkeypatch, probe=None):
    """开一扇刀窗：逐格重跑在册判据，点名红的；该红的一格没红就当场 fail。"""
    with _knife_window(builder) as (window, info):
        red, green = [], []
        for label, call in _checks(tmp_path, monkeypatch):
            try:
                call()
            except _REDS as exc:
                red.append((label, str(exc).splitlines()[0]))
            else:
                green.append(label)
        missing = sorted(set(must_go_red) - {label for label, _ in red})
        assert not missing, (
            "这把刀没砍到东西：%s 落下去仍然全绿。此刻红的=%s / 绿的=%s"
            % (missing, [label for label, _ in red], green)
        )
        verdict = probe(tmp_path, monkeypatch) if probe is not None else {}
    assert info["restored"] and info["shadow_clean"], (
        "出门核对失败：被跟踪文件 %s 在这扇窗里被写过（restored=%s）"
        % (window.rel, info["restored"])
    )
    print(
        "[r495] \u5200 %s on %s | \u7ea2 %d \u679a=%s | \u7eff %d \u679a=%s | probe=%s"
        % (
            builder.__name__,
            window.rel,
            len(red),
            "; ".join("%s: %s" % pair for pair in red)[:900],
            len(green),
            green,
            verdict,
        )
    )
    return red, green


def _require_no_global_knife():
    name = (os.environ.get(KNIFE_ENV) or "").strip()
    if name:
        pytest.skip(
            "R495_KNIFE=%s 已经在本进程开了一扇贯穿全轮的窗：影子根同一枚文件上不许嵌套" % name
        )


def _knife_one_probe(tmp_path, monkeypatch):
    """刀一里唯一要紧的那格：同一个人按用户名写下的旧行，此刻必须「拒写 + 出声」，而不是无声消失。"""
    username = _memory_username("r495-k1")
    recorder = _use_recorder(monkeypatch)
    registry = _registry_keyed_on(tmp_path, username, ("r495-k1-sess-1", "r495-k1-sess-2"))
    before = registry.metadata_path.read_bytes()
    try:
        principal = Principal.from_user(auth.get_user(username))
        namespace = sessions_module.session_owner_namespace(principal)
        raised = ""
        try:
            registry.bind("r495-k1-sess-new", principal)
        except sessions_module.SessionOwnerNamespaceError as exc:
            raised = type(exc).__name__
        read_back = registry.is_owned_by("r495-k1-sess-1", principal)
        assert namespace == sessions_module.OWNER_NAMESPACE_FROM_USER_ID, (
            "刀一落下去 principal 的键竟然没换命名空间：这扇窗是空转（读到 %r）" % namespace
        )
        assert raised == "SessionOwnerNamespaceError", (
            "刀一竟然没让写腿响：归属键翻成 bigint 而旧台账按用户名写着 2 行，写腿却照写 —— "
            "这正是「全员 200 + []」的开端"
        )
        assert registry.metadata_path.read_bytes() == before, "拒写之外还动了台账字节"
        assert read_back is False, "读腿在刀下竟然换了形状（R484:406 钉着 False）"
        assert recorder.drift_lines, "读腿在刀下一声不响：200 + [] 又成了无人看守的形状"
        return {"namespace": namespace, "raised": raised, "read_back": read_back,
                "testimony": len(recorder.drift_lines)}
    finally:
        _forget_user(username)


def _registry_keyed_on(tmp_path, owner, session_ids):
    """造一份「这个人 R495 之前就已经有会话」的台账：owner_id 逐枚按用户名写下。"""
    path = tmp_path / ("r495-keyed-%s.json" % session_ids[0])
    rows = [
        {"session_id": sid, "owner_id": owner, "status": "active",
         "created_at": "2026-09-29T00:00:00+00:00"}
        for sid in session_ids
    ]
    path.write_text(json.dumps({"sessions": rows}), encoding="utf-8")
    return sessions_module.SessionRegistry(path)


def test_counter_evidence_knife_one_adding_id_goes_red_and_goes_loud(tmp_path, monkeypatch):
    """刀一（SELECT 补 `id`）：对账钉当场红，写腿当场响，读腿留下证词。"""
    _require_no_global_knife()
    _replay(
        KNIFE_ONE,
        ("真源SELECT对账", "真principal形状"),
        tmp_path,
        monkeypatch,
        probe=_knife_one_probe,
    )


def test_counter_evidence_knife_two_a_true_owner_comparison_is_caught(tmp_path, monkeypatch):
    """刀二（归属判定恒真）：闸门一松，外来主体那一格与比较式那两格必须一起红。"""
    _require_no_global_knife()
    _replay(
        KNIFE_TWO,
        ("外来主体学不到东西", "归属比较式只两枚", "读腿的证词"),
        tmp_path,
        monkeypatch,
    )


def test_counter_evidence_knife_three_removing_the_source_is_caught(tmp_path, monkeypatch):
    """刀三（摘掉显式真源，退回靠 SELECT 形状）：行为一格没变，但承重必须当场可见地红。"""
    _require_no_global_knife()
    red, green = _replay(
        KNIFE_THREE,
        ("命名空间声明唯一", "归属键算式唯一", "归属比较式只两枚",
         "写腿拒换命名空间", "读腿的证词"),
        tmp_path,
        monkeypatch,
    )
    labels = {label for label, _ in red}
    assert "真源SELECT对账" not in labels, (
        "刀三只动 sessions.py，SELECT 对账那一格不该被牵连：牵连了说明刀身越界"
    )
    assert "外来主体学不到东西" in green, (
        "刀三本该只把「显式化」摘掉，不该把闸门改松：闸门那一格都红了就是改错地方"
    )


# ============================================================================
# 整轮复跑钩子：$env:R495_KNIFE = one|two|three 时，本件被 -p 当插件装载并把刀贯穿整轮
# ============================================================================

_KNIFE_STATE: dict = {}


def pytest_configure(config):
    """没有环境变量时这一钩子一声不响；开了窗也只改影子副本，被跟踪文件全程只读。"""
    name = (os.environ.get(KNIFE_ENV) or "").strip()
    if not name:
        return
    builder = _KNIFE_BUILDERS.get(name)
    if builder is None:
        raise RuntimeError("R495_KNIFE 只认 %s，读到 %r" % (sorted(_KNIFE_BUILDERS), name))
    ctx = _knife_window(builder)
    window, info = ctx.__enter__()
    _KNIFE_STATE["context"] = ctx
    _KNIFE_STATE["window"] = window
    _KNIFE_STATE["info"] = info
    print("[r495] knife=%s open on %s (shadow only, install_mutation)" % (name, window.rel))


def pytest_unconfigure(config):
    window = _KNIFE_STATE.get("window")
    if window is None:
        return
    info = _KNIFE_STATE["info"]
    ctx = _KNIFE_STATE.get("context")
    if ctx is not None:
        ctx.__exit__(None, None, None)   # 先把装进活模块的那几枚绑定逐枚装回，再关窗
    else:
        window.__exit__(None, None, None)
    print(
        "[r495] knife closed installed=%s tracked-file-untouched=%s shadow_clean=%s"
        % (info.get("installed_bindings"), info["restored"], info["shadow_clean"])
    )
    _KNIFE_STATE.clear()