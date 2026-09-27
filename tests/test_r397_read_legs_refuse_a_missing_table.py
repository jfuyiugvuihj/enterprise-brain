# -*- coding: utf-8 -*-
r"""R397 · 会话读腿的两张裸 500 脸：`GET /sessions` 与 `GET /sessions/{id}` 在「生产 + 缺表」这一格折成 503。

接单线索 = R384 的「只报不改」（`5f19e3f` 结转）：那一单只折了 `ask` 一条腿，两枚读腿留在账上。
本件读数一律取自 ``TestClient(app, raise_server_exceptions=False)``，替身台账只对「`to_regclass`
这一次现查怎么答」与「缺表时 DML 怎么失败」作答 —— 不连真库、不求值真 SQL、不起服务、不碰模型端口。

## 现场取证（本单基点 `49489c3` 实测；行号 = 基点）

| 出口 | 修前（生产 + 缺表） | 修后 | 谁先拒 | 另一条腿发不发语句 |
| --- | --- | --- | --- | --- |
| `GET /sessions` | **500** `text/plain` `Internal Server Error`，台账 1 句 SELECT | 503 `{"detail":"storage_unavailable"}` | list 腿（一句 SQL 同时读两枚账） | —— |
| `GET /sessions/{id}`，两枚账都缺 | **500** `text/plain`，台账只有 messages 那句 | 503 | messages 腿 | **不发**：session 腿连现查都不做 |
| `GET /sessions/{id}`，只缺 `sessions` | **500** `text/plain`，台账 2 句都发了 | 503 | session 腿（messages 腿先读完） | **已发**：messages 读完了才轮到它拒 |

⚠️ 台账对「缺表时 DML 怎么失败」按**语句里出现的全部已知账名**作答（``_referenced``），不只看第一个
``FROM``：`GET /sessions` 那一句里同时引用 `sessions` 与 `session_messages`，只看第一个就会把
「`sessions` 缺」量成「200 空列表」——那一格今天真是 500（现场复测过），是台账口径不够，不是脸不对。

## 判据②：不许洗的两格邻居（改前 = 改后，逐格现读）

- 驱动缺失：`_sess_conn` 那句 `RuntimeError("PostgreSQL driver is unavailable")`。两枚读腿改前是裸 500
  `text/plain`，改后**仍是**裸 500 `text/plain`（闸在 `with _sess_conn()` 里面，驱动没起来就到不了闸）。
- 缺身份：`_ensure_session` 那句 `RuntimeError("an authenticated user_id is required to persist a session")`。
  它是写腿 `_ensure_session` 的话，两枚读腿根本不经过它；本件钉的是「新接法只接 `ChatSchemaNotMigratedError`
  一种」，所以这枚错既不会被读腿接住、也不会被折成 503。

## 反证刀

四把在盘上落、按字节复原（进/出 sha 与咬住的用例名记在交回单里）：① 摘掉两枚新接法 ② 把缺表洗成
200 空列表 ③ 把驱动缺失一并洗成 503（这一把必须咬判据②那两格）④ 只接 messages 腿不接 session 腿。
外加 **K0**：在真·基点 `49489c3` 的干净影子克隆上先量本件红数。本件自己一个字节都不写盘（R253）。
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from psycopg import errors

from app.api.v1 import chat
from app.common import auth
from app.main import app

REPO = Path(__file__).resolve().parents[1]
CHAT_REL = "app/api/v1/chat.py"
CHAT = REPO / CHAT_REL
CONTRACT_REL = "docs/api/contract-v1.md"
CONTRACT = REPO / CONTRACT_REL
BASE = "49489c3"

FAMILY = "ChatSchemaNotMigratedError"
GATE = "_require_sessions_read_schema"
PROBE = "_require_migrated_tables"
SENTENCE = "run migrations first"
STORAGE_CODE = "storage_unavailable"
BARE_500_BODY = "Internal Server Error"

LIST_PATH = "/api/v1/sessions"
DETAIL_PATH = "/api/v1/sessions/s-r397"
ADMIN = "r397-admin"
ACCOUNT = {"id": "u-r397", "username": ADMIN, "role": "admin", "department": "", "status": "active"}

SESSIONS_TABLE = "sessions"
MESSAGES_TABLE = "session_messages"
BOTH_TABLES = {SESSIONS_TABLE, MESSAGES_TABLE}

_REGCLASS = re.compile(r"to_regclass\('public\.(\w+)'\)", re.IGNORECASE)
_REFERENCED = re.compile(r"(?:FROM|INTO|UPDATE)\s+([A-Za-z_]\w*)", re.IGNORECASE)
_KNOWN = {SESSIONS_TABLE, MESSAGES_TABLE, "documents", "document_versions", "users"}
_ALIAS_NOISE = {"s"}


def _sentence(table_name: str) -> str:
    """那句现查的话：拼出来，不抄源码字面量（抄来的行号/文本每演进一次红一次）。"""
    return f"{table_name} table is required in production; {SENTENCE}"


class SubstituteLedger:
    """只对「目录里现在有没有这一枚」作答的替身台账：不连库、不求值真 SQL。

    缺表时对 DML 抛**真的** ``psycopg.errors.UndefinedTable``（与真 PG 同一枚异常类）。
    """

    def __init__(self, tables=()):
        self.tables = {str(name).lower() for name in tables}
        self.statements: list[str] = []
        self._rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        text = " ".join(str(sql).split())
        self.statements.append(text)
        found = _REGCLASS.search(text)
        if found:
            name = found.group(1).lower()
            self._rows = [{"table_name": name if name in self.tables else None}]
            return self
        for name in (m.group(1).lower() for m in _REFERENCED.finditer(text)):
            if name in _KNOWN and name not in self.tables and name not in _ALIAS_NOISE:
                raise errors.UndefinedTable('relation "%s" does not exist' % name)
        self._rows = []
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def commit(self):
        return None

    def rollback(self):
        return None

    def close(self):
        return None

    @property
    def probed_tables(self) -> list[str]:
        return [m.group(1) for s in self.statements if (m := _REGCLASS.search(s))]

    def selects_of(self, table: str) -> list[str]:
        needle = table.lower()
        return [s for s in self.statements
                if not _REGCLASS.search(s) and needle in s.lower()]


class LogRecorder:
    """出口那几行日志是「缺哪枚表」唯一的现场证据。"""

    def __init__(self):
        self.lines: list[tuple[str, str]] = []

    def _record(self, level, message, *args, **kwargs):
        self.lines.append((level, str(message)))

    def debug(self, message, *args, **kwargs):
        self._record("debug", message, *args, **kwargs)

    info = warning = error = exception = debug

    def mentions(self, needle: str) -> list[str]:
        return [text for _level, text in self.lines if needle in text]


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {auth.create_token(ADMIN)}"}


def _world(monkeypatch, *, env: str, pg_up: bool, tables, driver_missing: bool = False):
    """架一具离线的读腿：真中间件、真路由、真闸；只有连接是替身台账。"""
    monkeypatch.setattr(
        auth, "get_user", lambda username: dict(ACCOUNT) if username == ADMIN else None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: pg_up)
    ledger = SubstituteLedger(tables)
    if driver_missing:
        monkeypatch.setattr(chat, "_sess_conn",
                            lambda: (_ for _ in ()).throw(
                                RuntimeError("PostgreSQL driver is unavailable")))
    else:
        monkeypatch.setattr(chat, "_sess_conn", lambda: ledger)
    recorder = LogRecorder()
    monkeypatch.setattr(chat, "logger", recorder)
    monkeypatch.setattr(chat.session_registry, "is_owned_by", lambda *_a, **_k: True)
    monkeypatch.setattr(chat, "_MEM_SESSIONS", {})
    monkeypatch.setattr(chat, "_MEM_SESSION_MESSAGES", {})
    monkeypatch.setenv("APP_ENV", env)
    return TestClient(app, raise_server_exceptions=False), ledger, recorder


def _get(client, path: str = LIST_PATH):
    return client.get(path, headers=_headers())


# ==================== 判据①②：`GET /sessions` 那张脸 ====================
def test_the_list_exit_refuses_production_with_either_table_missing(monkeypatch):
    """判据①：生产 + 库在 + 表缺 —— 修前实测裸 500 `text/plain`，本单治好这一格。"""
    # 现查按名逐枚问，第一枚缺就开口：两格点名的账不一样，正好把「缺哪枚」分开说清。
    for tables, probes, named in (
        (set(), [SESSIONS_TABLE], SESSIONS_TABLE),
        ({SESSIONS_TABLE}, [SESSIONS_TABLE, MESSAGES_TABLE], MESSAGES_TABLE),
    ):
        client, ledger, recorder = _world(monkeypatch, env="production", pg_up=True, tables=tables)
        response = _get(client)
        assert response.status_code == 503, response.text
        assert response.json() == {"detail": STORAGE_CODE}
        assert ledger.probed_tables == probes, ledger.statements
        assert recorder.mentions(_sentence(named)), recorder.lines


def test_the_bare_500_plain_text_face_is_gone_from_the_list_exit(monkeypatch):
    """裸 500 的病灶是「无码 + 纯文本」：这一格两样都不许留下。"""
    client, _ledger, _recorder = _world(
        monkeypatch, env="production", pg_up=True, tables=set())
    response = _get(client)

    assert response.status_code != 500
    assert response.text != BARE_500_BODY
    assert "application/json" in response.headers["content-type"]


def test_the_list_exit_logs_one_warning_that_names_the_code(monkeypatch):
    client, _ledger, recorder = _world(
        monkeypatch, env="production", pg_up=True, tables={SESSIONS_TABLE})
    _get(client)

    lines = recorder.mentions("code=" + STORAGE_CODE)
    assert len(lines) == 1, lines
    assert "route=list_sessions" in lines[0], lines[0]
    assert "session_messages table" in lines[0], lines[0]


def test_the_list_leg_probes_before_it_selects(monkeypatch):
    """现查必须排在读语句之前：拒答留下的台账里不许有那句 SELECT。"""
    client, ledger, _recorder = _world(
        monkeypatch, env="production", pg_up=True, tables=set())
    _get(client)

    assert ledger.probed_tables == [SESSIONS_TABLE], ledger.statements
    assert ledger.selects_of(SESSIONS_TABLE) == [], ledger.statements


def test_a_fully_migrated_production_list_still_answers_200(monkeypatch):
    """两枚账都在：这张脸一个字都不许多出来。"""
    client, ledger, recorder = _world(
        monkeypatch, env="production", pg_up=True, tables=BOTH_TABLES)
    response = _get(client)

    assert response.status_code == 200, response.text
    assert response.json() == {"sessions": []}
    assert ledger.probed_tables == [SESSIONS_TABLE, MESSAGES_TABLE]
    assert not recorder.mentions(SENTENCE)


# ==================== 判据④：`GET /sessions/{id}` 的两条腿分别可拒 ====================
def test_the_messages_leg_refuses_first_and_sends_the_session_leg_nothing(monkeypatch):
    """两枚账都缺：messages 腿先跑先拒，session 腿连现查都不做 —— 半张屏不许有。"""
    client, ledger, recorder = _world(
        monkeypatch, env="production", pg_up=True, tables=set())
    response = _get(client, DETAIL_PATH)

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": STORAGE_CODE}
    assert ledger.probed_tables == [MESSAGES_TABLE], ledger.statements
    assert ledger.selects_of(SESSIONS_TABLE) == [], ledger.statements
    assert recorder.mentions(_sentence(MESSAGES_TABLE)), recorder.lines


def test_the_session_leg_refuses_after_the_messages_leg_read_what_it_can(monkeypatch):
    """只缺 `sessions`：messages 腿读完自己的份，session 腿再指名 —— 两条腿各自可拒。"""
    client, ledger, recorder = _world(
        monkeypatch, env="production", pg_up=True, tables={MESSAGES_TABLE})
    response = _get(client, DETAIL_PATH)

    assert response.status_code == 503, response.text
    assert ledger.probed_tables == [MESSAGES_TABLE, SESSIONS_TABLE], ledger.statements
    assert len(ledger.selects_of(MESSAGES_TABLE)) == 1, ledger.statements
    assert ledger.selects_of(SESSIONS_TABLE) == [], ledger.statements
    assert recorder.mentions(_sentence(SESSIONS_TABLE)), recorder.lines
    assert "route=get_session" in recorder.mentions("code=" + STORAGE_CODE)[0]


def test_the_refusal_body_carries_no_half_rendered_page(monkeypatch):
    """拒答那一格交回去的是**只有码**一枚：不许半真半假地带上 messages / session 键。"""
    client, _ledger, _recorder = _world(
        monkeypatch, env="production", pg_up=True, tables={MESSAGES_TABLE})
    response = _get(client, DETAIL_PATH)

    assert set(response.json()) == {"detail"}, response.json()
    for key in ("session", "messages", "withheld_turns"):
        assert key not in response.text


def test_a_migrated_detail_pair_keeps_its_shape(monkeypatch):
    client, ledger, _recorder = _world(
        monkeypatch, env="production", pg_up=True, tables=BOTH_TABLES)
    response = _get(client, DETAIL_PATH)

    assert response.status_code == 200, response.text
    assert response.json() == {"session": None, "messages": [], "withheld_turns": 0}
    assert ledger.probed_tables == [MESSAGES_TABLE, SESSIONS_TABLE]
    assert len(ledger.selects_of(SESSIONS_TABLE)) == 1, ledger.statements


def test_the_detail_exit_logs_exactly_one_warning_per_refusal(monkeypatch):
    client, _ledger, recorder = _world(
        monkeypatch, env="production", pg_up=True, tables=set())
    _get(client, DETAIL_PATH)

    assert len(recorder.mentions("code=" + STORAGE_CODE)) == 1, recorder.lines


# ==================== 判据②：其余 RuntimeError 一律不洗 ====================
@pytest.mark.parametrize("path", [LIST_PATH, DETAIL_PATH])
def test_a_missing_driver_is_still_a_bare_500_at_both_exits(monkeypatch, path):
    """驱动缺失那格改前 = 改后：裸 500 `text/plain`，本单不许把它洗成 503。"""
    client, _ledger, recorder = _world(
        monkeypatch, env="production", pg_up=True, tables=set(), driver_missing=True)
    response = _get(client, path)

    assert response.status_code == 500, response.text
    assert response.text == BARE_500_BODY
    assert not recorder.mentions(SENTENCE), recorder.lines


def test_the_missing_user_id_error_is_not_a_member_of_the_caught_family():
    """缺身份那格（`_ensure_session`）与新接法无缘：它不是这一族，接法也就接不到它。"""
    assert issubclass(chat.ChatSchemaNotMigratedError, RuntimeError)
    assert not issubclass(RuntimeError, chat.ChatSchemaNotMigratedError)
    assert chat.ChatSchemaNotMigratedError is not RuntimeError


# ==================== 判据③：开发 / 裸机 / 离线三张脸一字不动 ====================
def test_the_offline_face_of_the_list_exit_is_unchanged(monkeypatch):
    """离线：内存表那一支一个字节都不许多发语句，也就永远不答 503。"""
    chat._MEM_SESSIONS["s-r397"] = {"id": "s-r397", "title": "旧话", "created_at": "1", "updated_at": "2"}
    client, ledger, recorder = _world(
        monkeypatch, env="production", pg_up=False, tables=set())
    monkeypatch.setattr(chat, "_MEM_SESSIONS", {"s-r397": {
        "id": "s-r397", "title": "旧话", "created_at": "1", "updated_at": "2"}})
    response = _get(client)

    assert response.status_code == 200, response.text
    assert [item["title"] for item in response.json()["sessions"]] == ["旧话"]
    assert ledger.statements == [], ledger.statements
    assert not recorder.mentions(SENTENCE)


def test_the_offline_face_of_the_detail_exit_is_unchanged(monkeypatch):
    client, ledger, _recorder = _world(
        monkeypatch, env="production", pg_up=False, tables=set())
    monkeypatch.setattr(chat, "_MEM_SESSIONS", {"s-r397": {
        "id": "s-r397", "title": "旧话", "created_at": "1", "updated_at": "2"}})
    response = _get(client, DETAIL_PATH)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "session": {"id": "s-r397", "title": "旧话", "created_at": "1", "updated_at": "2"},
        "messages": [], "withheld_turns": 0,
    }
    assert ledger.statements == [], ledger.statements


def test_development_with_missing_tables_keeps_its_bare_face(monkeypatch):
    """开发态 + 缺表改前改后同一张脸：闸只认生产，这一格仍是裸 500（本单不接管）。"""
    for path in (LIST_PATH, DETAIL_PATH):
        client, ledger, recorder = _world(
            monkeypatch, env="development", pg_up=True, tables=set())
        response = _get(client, path)

        assert response.status_code == 500, (path, response.text)
        assert response.text == BARE_500_BODY
        assert ledger.probed_tables == [], "非生产那一腿不该做现查"
        assert not recorder.mentions(SENTENCE)


def test_development_with_the_tables_present_answers_200(monkeypatch):
    client, _ledger, _recorder = _world(
        monkeypatch, env="development", pg_up=True, tables=BOTH_TABLES)
    assert _get(client).status_code == 200
    assert _get(client, DETAIL_PATH).status_code == 200


# ==================== 闸本身的形状（现读，不抄数） ====================
def test_the_gate_raises_the_family_with_the_unchanged_sentence(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    ledger = SubstituteLedger({SESSIONS_TABLE})
    with pytest.raises(chat.ChatSchemaNotMigratedError) as caught:
        chat._require_sessions_read_schema(ledger, MESSAGES_TABLE)

    assert str(caught.value) == _sentence(MESSAGES_TABLE)
    assert isinstance(caught.value, RuntimeError), "基类一换就会弄红别人的旧账"


@pytest.mark.parametrize("env", ["development", "prod", "PRODUCTION "])
def test_the_gate_only_speaks_where_the_ask_leg_spoke_it(monkeypatch, env):
    """非生产一格不发语句；生产两枚账分开点名。"""
    monkeypatch.setenv("APP_ENV", env)
    ledger = SubstituteLedger(set())
    if env.strip().lower() in {"production", "prod"}:
        with pytest.raises(chat.ChatSchemaNotMigratedError):
            chat._require_sessions_read_schema(ledger, SESSIONS_TABLE)
        assert ledger.probed_tables == [SESSIONS_TABLE]
    else:
        assert chat._require_sessions_read_schema(ledger, SESSIONS_TABLE, MESSAGES_TABLE) is None
        assert ledger.statements == [], ledger.statements


def test_the_gate_probes_only_what_the_leg_is_about_to_read(monkeypatch):
    """三格点名各查各的账：list 两枚、messages 一枚、session 一枚（判据④的「分别可拒」靠它）。"""
    monkeypatch.setenv("APP_ENV", "production")
    cases = {
        "list": [SESSIONS_TABLE, MESSAGES_TABLE],
        "messages": [MESSAGES_TABLE],
        "session": [SESSIONS_TABLE],
    }
    client, ledger, _recorder = _world(monkeypatch, env="production", pg_up=True, tables=BOTH_TABLES)
    _get(client)
    assert ledger.probed_tables == cases["list"]
    client, ledger, _recorder = _world(monkeypatch, env="production", pg_up=True, tables=BOTH_TABLES)
    _get(client, DETAIL_PATH)
    assert ledger.probed_tables == cases["messages"] + cases["session"]


def test_the_probe_stays_the_only_raiser_of_the_family():
    """具名族只有一个抛出方：闸只是转发它，出口只是接它，谁都不自己举。"""
    raisers = [
        (scope.name, node.lineno)
        for scope in _function_scopes(_tree())
        for node in ast.walk(scope)
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
        and getattr(node.exc.func, "id", "") == FAMILY
    ]

    assert len(raisers) == 1, raisers
    assert raisers[0][0] == PROBE, raisers


def test_every_read_leg_gate_call_sits_behind_the_production_branch():
    """新闸自己也只有一支现查，且那一支必须在生产分支里（跑出去就是替非生产打掩护）。"""
    tree = _tree()
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and getattr(node.func, "id", "") == PROBE]
    gate = next(node for node in _function_scopes(tree)
                if isinstance(node, ast.FunctionDef) and node.name == GATE)
    gate_calls = [node for node in ast.walk(gate)
                  if isinstance(node, ast.Call) and getattr(node.func, "id", "") == PROBE]

    assert len(gate_calls) == 1, gate_calls
    assert len(calls) == 3, [node.lineno for node in calls]
    for call in calls:
        guards = [node for node in ast.walk(tree)
                  if isinstance(node, ast.If) and node.lineno <= call.lineno <= (node.end_lineno or node.lineno)
                  and "_is_production_environment" in ast.unparse(node.test)]
        assert guards, f"{PROBE} 的调用点 :{call.lineno} 跑出了生产分支"


def test_the_two_new_exits_catch_exactly_one_type_each():
    """宽捕获会把真 bug 一起洗成 503：两枚出口各只接 `ChatSchemaNotMigratedError` 一种。"""
    scopes = _function_scopes(_tree())
    owners = {scope.name: scope for scope in scopes if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef))}

    for name in ("list_sessions", "get_session"):
        handlers = [node for node in ast.walk(owners[name])
                    if isinstance(node, ast.ExceptHandler) and node.type is not None]
        assert [ast.unparse(node.type) for node in handlers] == [FAMILY], (name, handlers)
        body = " ".join(ast.unparse(stmt) for stmt in handlers[0].body)
        assert body.count("raise HTTPException") == 1, body
        assert body.count("logger.warning") == 1, body
        assert STORAGE_CODE in body, body


def test_the_new_exits_reuse_the_existing_code_verbatim():
    """零新增错误码：新出口的 detail 与既有那枚逐字相同，且都是常量字面量。"""
    tree = _tree()
    details = {}
    for scope in _function_scopes(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(scope):
            if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                    and getattr(node.exc.func, "id", "") == "HTTPException"):
                continue
            for keyword in node.exc.keywords:
                if keyword.arg == "status_code" and getattr(keyword.value, "value", None) == 503:
                    for extra in node.exc.keywords:
                        if extra.arg == "detail" and isinstance(extra.value, ast.Constant):
                            details.setdefault(scope.name, []).append(extra.value.value)

    for name in ("ask", "hitl_pending", "list_sessions", "get_session"):
        assert details[name] == [STORAGE_CODE], (name, details.get(name))
    assert len({value for values in details.values() for value in values}) == 1, details


def test_no_status_tier_was_invented_at_the_two_read_exits():
    """两枚读腿里出现的 status 档位只有闸带来的那一枚 503（401 是闸外的既有脸）。"""
    scopes = {scope.name: scope for scope in _function_scopes(_tree())
              if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name in ("list_sessions", "get_session"):
        statuses = {node.value.value for node in ast.walk(scopes[name])
                    if isinstance(node, ast.keyword) and node.arg == "status_code"
                    and isinstance(node.value, ast.Constant)}
        assert statuses <= {503}, (name, statuses)


def test_the_ask_leg_conversion_is_untouched():
    """本单一个字不许动写腿：`ask` 那一支仍是一枚接法、一句 warning、一枚 503。"""
    scopes = {scope.name: scope for scope in _function_scopes(_tree())
              if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef))}
    handlers = [node for node in ast.walk(scopes["ask"])
                if isinstance(node, ast.ExceptHandler) and node.type is not None
                and ast.unparse(node.type) == FAMILY]
    body = " ".join(ast.unparse(stmt) for node in handlers for stmt in node.body)

    assert len(handlers) == 1, handlers
    assert body.count("raise HTTPException") == 1, body
    assert body.count("logger.warning") == 1, body
    assert "_ensure_sessions_table()" in ast.unparse(scopes["ask"]), "写腿那道闸被本单挪走了"


def _tree() -> ast.Module:
    return ast.parse(CHAT.read_text(encoding="utf-8"))


def _function_scopes(tree: ast.Module) -> list[ast.AST]:
    return [node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]


# ==================== 契约：只许尾部追加一枚节，中段一个字节不许动 ====================
def _base_contract_text() -> str:
    """基点那份契约：`git show` 交回的是**仓库里那份**（本机 `core.autocrlf=true` ⇒ LF），
    所以两边都折成 LF 再比前缀 —— R388 的口径，别拿裸字节比，那会比出一张假红。"""
    raw = subprocess.run(["git", "show", f"{BASE}:{CONTRACT_REL}"], cwd=str(REPO),
                         capture_output=True, check=True).stdout
    return raw.decode("utf-8").replace("\r\n", "\n")


def test_the_contract_appends_one_section_and_deletes_nothing():
    base = _base_contract_text()
    shipped = CONTRACT.read_text(encoding="utf-8").replace("\r\n", "\n")

    assert shipped.startswith(base), "契约被中改或删了字节：本单只许尾部追加"
    assert len(shipped) > len(base)


def test_the_new_heading_is_unique_and_the_section_count_moves_by_one():
    base = _base_contract_text()
    shipped = CONTRACT.read_text(encoding="utf-8").replace("\r\n", "\n")
    heading = "## R397 · 会话读腿的两张裸 500 脸折成 503（`GET /sessions` 与 " \
              "`GET /sessions/{session_id}`，2026-09-27）"

    def h2(text: str) -> int:
        """行首那枚 `## ` 才算一枚节：正文里出现的 `## ` 不算（表格与行内都写得到它）。"""
        return len(re.findall(r"(?m)^## ", text))

    assert h2(shipped) == h2(base) + 1, (h2(base), h2(shipped))
    assert shipped.count(heading) == 1, "新标题全文必须唯一，且就是这一枚"
    assert heading in shipped.splitlines(), "新标题必须独占一行"


def test_the_contract_and_the_module_keep_their_byte_shape():
    for path in (CONTRACT, CHAT):
        data = path.read_bytes()
        assert data.count(b"\r") == data.count(b"\n"), f"{path.name} 行尾漂了"
        # 裸 LF = 一枚前面不是 CR 的 LF；裸 CR = 一枚后面不是 LF 的 CR。（`\n\r` 不是病灶：
        # 纯 CRLF 文件里 `\r\n\r\n` 本来就含 `\n\r`。）
        assert not data.startswith(b"\xef\xbb\xbf"), f"{path.name} 长了 BOM"
        assert sum(1 for i, c in enumerate(data)
                   if c == 0x0A and (i == 0 or data[i - 1] != 0x0D)) == 0, f"{path.name} 有裸 LF"
        assert sum(1 for i, c in enumerate(data)
                   if c == 0x0D and (i == len(data) - 1 or data[i + 1] != 0x0A)) == 0, f"{path.name} 有裸 CR"
        assert "\ufffd" not in data.decode("utf-8"), f"{path.name} 有替换符"
