"""R296 · 画像里的 department 降为只读派生：唯一事实源是 ``users`` 那一行。

病灶（本班在基点 27068de 自己复现过一遍，不是照抄工单）：

* ``app/memory/profile.py`` 的 ``get_profile`` 拿 ``user_profiles.department`` **覆盖**调用方从
  ``users`` 带来的权威值——PG 那一支在 SELECT 里带着这一列，内存那一支整枚 ``update``；
* ``PUT /api/v1/auth.py`` 的 ``PUT /profile`` 是员工**自助可写**的，自报的部门直接进那一列；
* ``app/agents/nodes.py`` 的 ``load_memory`` 再把它拼进 prompt。

上班工单还说 ``load_memory`` 的 fallback「来自 users」——本文件实测它其实恒为空：
``AgentState``（``app/agents/state.py``）根本没有 ``department`` 这一格。也就是说画像块里那一行
``department:`` 今天唯一可能的来源就是那列自助可写的遗留值，本单把它改成现取 ``users``。

口径（防写过头）：``user_profiles`` 不是授权输入，``Principal`` 读的是 ``users`` 那一行，所以这是
标注／提示污染，**不是越权提级**；本单一个字都没动授权判定。

判据对应：① 三枚读路径用例（两条读腿各一枚）＋② 五枚 API 用例＋③ 两枚拼接用例＋
④ 三枚反证（自报不变／管理员挪动立刻可见／恢复覆盖那一行必红）＋⑤ 源码面扫描。
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
PROFILE_SOURCE = ROOT / "app" / "memory" / "profile.py"
ROUTE_SOURCE = ROOT / "app" / "api" / "v1" / "auth.py"

PROFILE_PATH = "/api/v1/profile"
DEPARTMENT_PATH = "/api/v1/users/department"

RESEARCH = "研发部"
MARKETING = "市场部"
#: 遗留列里已经躺在表里的旧值：它过去会盖住权威值，今天任何读路径都不许再把它当事实。
LEGACY = "旧部门遗留值"
#: 员工自助想塞进去的那一枚（判据②要拒的就是它）。
SELF_REPORTED = "自报的任意部门"

ADMIN = "r296-admin"
STAFF = "r296-staff"
PASSWORD = "r296-secret"
POSITION = "工程师"
PREFERENCES = ["图表优先"]

STABLE_CODE = "department_override_denied"


# ==================== 测试替身 ====================


class _FakeCursor:
    __slots__ = ("_row",)

    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeProfileStore:
    """一张只认「语句真正选出的列」的假 ``user_profiles`` 表。

    刻意按 SELECT 的列名裁剪返回行：假表要是什么都回，读路径「不再选这一列」就永远测不出来——
    遗留值会从假表多回的那一格漏进画像。它同时记下每一条落地的语句，供写路径点名。
    """

    def __init__(self, row):
        self.row = dict(row)
        self.statements: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        text = " ".join(sql.split())
        self.statements.append((text, tuple(params or ())))
        upper = text.upper()
        if upper.startswith("SELECT") and "USER_PROFILES" in upper:
            tail = upper[len("SELECT"):].split("FROM")[0]
            columns = [name.strip().lower() for name in tail.split(",")]
            present = {name: self.row[name] for name in columns if name in self.row}
            return _FakeCursor(present or None)
        return _FakeCursor(None)

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _legacy_row():
    return {
        "user_id": STAFF,
        "department": LEGACY,
        "position": POSITION,
        "preferences": json.dumps(PREFERENCES, ensure_ascii=False),
        "updated_at": "2026-09-25T00:00:00+08:00",
    }


@pytest.fixture()
def users(monkeypatch):
    """进程内用户表（``users`` 的替身）：本文件独占，测试结束后随 monkeypatch 撤掉。"""
    from app.common import auth

    monkeypatch.setattr(auth, "_MEM_USERS", {})

    def add(username: str, role: str = "staff", department: str = RESEARCH) -> str:
        ok, message = auth.create_user(username, PASSWORD, role=role, department=department)
        assert ok, message
        return username

    add(ADMIN, role="admin")
    add(STAFF)
    return add


@pytest.fixture()
def client(users):
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def headers(users):
    from app.common.auth import create_token

    def for_user(username: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_token(username)}"}

    return for_user


@pytest.fixture()
def memory_store(monkeypatch, users):
    """画像走进程内那本内存表（生产环境判定一并钉死，免得跟着宿主 .env 漂）。"""
    from app.memory import profile

    monkeypatch.setattr(profile, "_database_available", lambda: False)
    monkeypatch.setattr(profile, "_is_production_environment", lambda: False)
    monkeypatch.setattr(profile, "_MEM_PROFILES", {})
    return profile


@pytest.fixture()
def pg_store(monkeypatch, users):
    """画像走假 PG 那一支；用户表仍然是进程内的 ``users`` 替身。"""
    from app.memory import profile

    store = _FakeProfileStore(_legacy_row())
    monkeypatch.setattr(profile, "_database_available", lambda: True)
    monkeypatch.setattr(profile, "_initialized", True)
    monkeypatch.setattr(profile, "_conn", lambda: store)
    return store


def _json(body: dict) -> str:
    return json.dumps(body, ensure_ascii=False, default=str)


# ==================== 判据①：画像读到的 department 只可能来自 users ====================


def test_the_postgres_leg_no_longer_selects_the_legacy_column(pg_store):
    """遗留列躺在假表里，读路径不选它、也不剥完再合并回来。"""
    from app.memory.profile import get_profile

    profile = get_profile(STAFF, fallback={"department": RESEARCH})

    assert profile["department"] == RESEARCH, profile
    assert LEGACY not in _json(profile)
    # 其余字段照旧读得回来——本单缩的是 department 一格，不是整枚画像。
    assert profile["position"] == POSITION
    assert profile["preferences"] == PREFERENCES
    selects = [text for text, _params in pg_store.statements if text.upper().startswith("SELECT")]
    assert selects, pg_store.statements
    assert all("department" not in text.lower() for text in selects), selects


def test_the_in_memory_leg_drops_the_legacy_key_before_merging(memory_store):
    """另一条读腿（无 PG 的内存表）同口径：老 dict 里带 department 也进不了返回值。"""
    memory_store._MEM_PROFILES[STAFF] = {"department": LEGACY, "position": POSITION}

    profile = memory_store.get_profile(STAFF, fallback={"department": RESEARCH})

    assert profile["department"] == RESEARCH, profile
    assert profile["position"] == POSITION
    assert LEGACY not in profile.values()


def test_get_profile_invents_no_department_when_the_caller_supplies_none(pg_store):
    """没有权威值时宁可缺这一格，也不从遗留列「编」一枚出来。"""
    from app.memory.profile import get_profile

    assert "department" not in get_profile(STAFF)


# ==================== 判据②：PUT /profile 带 department 就整发拒 ====================


def test_a_self_reported_department_is_refused_whole(client, memory_store, headers, monkeypatch):
    """员工自报部门 ⇒ 403 + 稳定码；而且这一发什么都没写。"""
    from app.api.v1 import auth as auth_api

    writes: list[tuple] = []
    monkeypatch.setattr(auth_api, "upsert_profile", lambda *a, **k: writes.append((a, k)) or True)

    response = client.put(
        PROFILE_PATH,
        json={"department": SELF_REPORTED, "position": "自称的职位"},
        headers=headers(STAFF),
    )

    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert detail["code"] == STABLE_CODE, detail
    assert isinstance(detail["message"], str) and len(detail["message"]) > 10, detail
    assert "department" in detail["message"], detail
    # 「收了但不用」与「静默丢字段」都长在这一枚探针上：真拒了，写存储那一趟一次都不该走。
    assert writes == [], writes
    assert memory_store._MEM_PROFILES == {}, memory_store._MEM_PROFILES

    listed = client.get(PROFILE_PATH, headers=headers(STAFF)).json()["profile"]
    assert listed["department"] == RESEARCH, listed
    assert SELF_REPORTED not in _json(listed)


def test_an_empty_department_claim_is_refused_too(client, memory_store, headers):
    """空串也算「带了 department」：判据不能靠值是否非空来放行，否则清空归属这条路还在。"""
    response = client.put(PROFILE_PATH, json={"department": ""}, headers=headers(STAFF))

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == STABLE_CODE
    assert memory_store._MEM_PROFILES == {}


def test_a_body_without_department_still_saves_position_and_preferences(client, memory_store, headers):
    """拒的是那一格，不是整条路由：不带 department 的画像写照旧成功、读得回来。"""
    response = client.put(
        PROFILE_PATH,
        json={"position": "数据分析", "preferences": PREFERENCES},
        headers=headers(STAFF),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}
    listed = client.get(PROFILE_PATH, headers=headers(STAFF)).json()["profile"]
    assert listed["position"] == "数据分析"
    assert listed["preferences"] == PREFERENCES
    assert listed["department"] == RESEARCH, listed


def test_an_admin_cannot_write_the_legacy_column_here_either(client, memory_store, headers):
    """只读派生就是只读派生：管理员也一样拒。改部门只有 R290 那扇门。"""
    response = client.put(PROFILE_PATH, json={"department": MARKETING}, headers=headers(ADMIN))

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == STABLE_CODE
    assert memory_store._MEM_PROFILES == {}


def test_the_refusal_reuses_the_code_that_is_already_licensed():
    """不许为这一格新造裸码：那枚码的后端登记与前端归一本来就齐（新造会两头欠账）。"""
    from app.common.authorization import DEPARTMENT_SELF_REPORT_DENIED

    assert DEPARTMENT_SELF_REPORT_DENIED == STABLE_CODE


# ==================== 判据③：prompt 拼接照旧在，只是取值换了源头 ====================


def _load_memory_context(monkeypatch, store, department_in_users: str = RESEARCH) -> str:
    from app.agents import nodes
    from app.agents.contracts import Principal
    from app.common import auth

    monkeypatch.setattr(nodes, "recall", lambda *_a, **_k: [])
    from langchain_core.messages import HumanMessage

    auth.update_department(STAFF, department_in_users)
    principal = Principal.from_user(auth.get_user(STAFF))
    result = nodes.load_memory(
        {"messages": [HumanMessage(content="这个月的产出怎么样")], "principal": principal}
    )
    assert store.statements, store.statements
    return result["memory"]["profile_context"]


def test_the_prompt_block_uses_the_authoritative_department(pg_store, monkeypatch):
    """遗留列就在假表里、还带着旧值：拼进 prompt 的必须是 users 那一行。"""
    context = _load_memory_context(monkeypatch, pg_store)

    assert f"department: {RESEARCH}" in context, context
    assert LEGACY not in context, context


def test_the_context_block_loses_no_line_and_keeps_its_shape(memory_store):
    """整段拼接一个字都不减：四行标签、行序、画像存储里其余字段都还在。"""
    from app.memory.profile import compose_profile_context

    text = compose_profile_context(
        {"department": RESEARCH, "position": POSITION, "preferences": PREFERENCES, "role": "staff"}
    )

    assert text.splitlines() == [
        f"department: {RESEARCH}",
        f"position: {POSITION}",
        "preferences: " + ", ".join(PREFERENCES),
        "role: staff",
    ], text


def test_load_memory_still_splices_when_the_user_row_is_unreachable(pg_store, monkeypatch):
    """读不到 users 时退回 Principal 快照（同一行的投影），而不是留空、也不是退回遗留列。"""
    from app.agents import nodes
    from app.agents.contracts import Principal
    from app.common import auth
    from langchain_core.messages import HumanMessage

    monkeypatch.setattr(nodes, "recall", lambda *_a, **_k: [])
    principal = Principal.from_user(auth.get_user(STAFF))

    def explode(_username):
        raise RuntimeError("users is unreachable")

    monkeypatch.setattr(auth, "get_user", explode)
    result = nodes.load_memory({"messages": [HumanMessage(content="你好")], "principal": principal})

    context = result["memory"]["profile_context"]
    assert f"department: {RESEARCH}" in context, context
    assert LEGACY not in context, context


# ==================== 判据④：反证 ====================


def test_counter_evidence_a_self_report_changes_nothing_at_all(client, pg_store, headers, monkeypatch):
    """反证一：员工自报部门之后，权威值与 prompt 都不许动一个字。"""
    from app.agents import nodes
    from app.agents.contracts import Principal
    from app.common import auth
    from langchain_core.messages import HumanMessage

    monkeypatch.setattr(nodes, "recall", lambda *_a, **_k: [])
    before = client.get(PROFILE_PATH, headers=headers(STAFF)).json()["profile"]["department"]
    assert before == RESEARCH

    refused = client.put(PROFILE_PATH, json={"department": SELF_REPORTED}, headers=headers(STAFF))
    assert refused.status_code == 403, refused.text

    after = client.get(PROFILE_PATH, headers=headers(STAFF)).json()["profile"]["department"]
    assert after == RESEARCH == before, after

    principal = Principal.from_user(auth.get_user(STAFF))
    context = nodes.load_memory(
        {"messages": [HumanMessage(content="你好")], "principal": principal}
    )["memory"]["profile_context"]
    assert f"department: {RESEARCH}" in context, context
    assert SELF_REPORTED not in _json(context), context


def test_an_admin_move_shows_up_in_get_profile_immediately(client, pg_store, headers):
    """反证二：管理员挪完部门，``GET /profile`` 当场跟着变——遗留列里的旧值盖不住它。

    ``pg_store`` 那张假表从头到尾都存着 ``LEGACY``，正对着工单里「管理员挪完部门，
    ``GET /profile`` 仍报旧部门」那一句：今天它报的是 users 的新值。
    """
    listed = client.get(PROFILE_PATH, headers=headers(STAFF)).json()["profile"]
    assert listed["department"] == RESEARCH, listed

    moved = client.put(
        DEPARTMENT_PATH,
        json={"username": STAFF, "department": MARKETING},
        headers=headers(ADMIN),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["department"] == MARKETING

    after = client.get(PROFILE_PATH, headers=headers(STAFF)).json()["profile"]
    assert after["department"] == MARKETING, after
    assert LEGACY not in _json(after), after


def _mutated_profile_module(mutations):
    """在内存里把 ``profile.py`` 改回案发形状，返回改过的模块命名空间（一个字节都不落盘）。"""
    source = PROFILE_SOURCE.read_text(encoding="utf-8")
    for old, new in mutations:
        assert source.count(old) == 1, (old[:48], source.count(old))
        source = source.replace(old, new, 1)
    namespace = {"__name__": "r296_mutated_profile"}
    exec(compile(source, "app/memory/profile.py (mutated in memory)", "exec"), namespace)
    namespace["_database_available"] = lambda: True
    namespace["_initialized"] = True
    namespace["_conn"] = lambda: _FakeProfileStore(_legacy_row())
    return namespace


#: 恢复病灶的两半：SELECT 里把这一列选回来 + 合并时不再剥掉它。
MUTATE_SELECT_BACK = (
    '"SELECT position, preferences, updated_at FROM user_profiles WHERE user_id = %s"',
    '"SELECT department, position, preferences, updated_at FROM user_profiles WHERE user_id = %s"',
)
MUTATE_OVERRIDE_BACK = (
    "stored = _without_legacy_department(dict(row))",
    "stored = dict(row)",
)


def test_counter_evidence_restoring_the_override_turns_the_read_pin_red():
    """反证三：把「覆盖」那一行恢复回去，判据①那枚钉必然红（本用例就是它的现场重放）。"""
    mutated = _mutated_profile_module([MUTATE_SELECT_BACK, MUTATE_OVERRIDE_BACK])

    profile = mutated["get_profile"](STAFF, fallback={"department": RESEARCH})

    # 遗留值又赢了 ⇒ test_the_postgres_leg_no_longer_selects_the_legacy_column 的
    # ``profile["department"] == RESEARCH`` 与 ``LEGACY not in _json(profile)`` 两句同时挂。
    assert profile["department"] == LEGACY, profile
    assert profile["department"] != RESEARCH


def test_counter_evidence_each_guard_alone_still_holds_the_line():
    """两半各是一道独立闸：只恢复其中一半，权威值仍然读得回来（所以恢复必须成对才看得见红）。"""
    only_select = _mutated_profile_module([MUTATE_SELECT_BACK])["get_profile"](
        STAFF, fallback={"department": RESEARCH}
    )
    only_merge = _mutated_profile_module([MUTATE_OVERRIDE_BACK])["get_profile"](
        STAFF, fallback={"department": RESEARCH}
    )

    assert only_select["department"] == RESEARCH, only_select
    assert only_merge["department"] == RESEARCH, only_merge


def _refusal_guard_line(source: str) -> int | None:
    """``PUT /profile`` 里那道拒的起始行：只认「测 model_fields_set 且当场 raise 稳定码」。"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "update_my_profile":
            for statement in ast.walk(node):
                if not isinstance(statement, ast.If):
                    continue
                if "model_fields_set" not in ast.dump(statement.test):
                    continue
                raised = [
                    inner
                    for inner in ast.walk(statement)
                    if isinstance(inner, ast.Raise)
                    and "DEPARTMENT_SELF_REPORT_DENIED" in ast.dump(inner)
                ]
                if raised:
                    return statement.lineno
    return None


def _upsert_call_line(source: str) -> int:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "update_my_profile":
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "upsert_profile":
                    return call.lineno
    raise AssertionError("PUT /profile 里已经没有 upsert_profile 这一行了")


def test_the_refusal_stands_before_any_write():
    """拒必须写在落库之前：先存后拒就是「收了但不用」换了个说法。"""
    source = ROUTE_SOURCE.read_text(encoding="utf-8")

    guard = _refusal_guard_line(source)
    assert guard is not None, "PUT /profile 里没有那道拒了"
    assert guard < _upsert_call_line(source), (guard, _upsert_call_line(source))


def test_counter_evidence_a_silent_drop_would_turn_that_pin_red():
    """把拒改成工单禁的形状（永远不拒，字段收下再丢），上面那枚钉当场失去立足点。"""
    source = ROUTE_SOURCE.read_text(encoding="utf-8")
    mutated = source.replace(
        'if "department" in data.model_fields_set:',
        'if False:  # mutated: silently drop the field and save the rest',
        1,
    )
    assert mutated != source, "变异锚点没命中，这枚反证是空的"

    assert _refusal_guard_line(mutated) is None
    assert _refusal_guard_line(source) is not None


# ==================== 判据⑤：已存的旧值不许再被任何读路径当成事实 ====================


def test_no_production_sql_touches_the_legacy_column_anymore():
    """app/** 里任何碰 user_profiles 的语句都不许再出现 department 列（读也不选、写也不喂）。"""
    offenders: list[str] = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "user_profiles" not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if "user_profiles" not in node.value:
                continue
            statement = " ".join(node.value.split()).lower()
            touches_department = "department" in statement
            writes_column = "insert into user_profiles" in statement and "department" in statement.split("values")[0]
            updates_column = "department = excluded" in statement
            reads_column = statement.startswith("select") and touches_department
            if reads_column or writes_column or updates_column:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}: {statement[:72]}")

    assert offenders == [], "第二份真相还挂在读／写路径上：" + " | ".join(offenders)


def test_the_profile_store_no_longer_writes_the_legacy_column(pg_store):
    """写路径点名：新写的 INSERT 与 ON CONFLICT 都不带这一列，表里的旧值因此一个字都不动。"""
    from app.memory.profile import upsert_profile

    assert upsert_profile(STAFF, position="数据分析", preferences=PREFERENCES) is True

    inserts = [(text, params) for text, params in pg_store.statements if text.upper().startswith("INSERT")]
    assert inserts, pg_store.statements
    for text, params in inserts:
        assert "department" not in text.lower(), text
        assert LEGACY not in _json(params), params


def test_upsert_profile_never_stores_a_department_passed_by_a_caller(memory_store, monkeypatch):
    """内存那一腿同口径：内部调用点就算把 department 递上来，也不进存储（并有日志可查）。"""
    from app.memory import profile

    warned: list[str] = []
    monkeypatch.setattr(profile.logger, "warning", lambda message, *_a: warned.append(str(message)))

    assert profile.upsert_profile(STAFF, department=SELF_REPORTED, position=POSITION) is True

    assert profile._MEM_PROFILES[STAFF]["position"] == POSITION
    assert "department" not in profile._MEM_PROFILES[STAFF], profile._MEM_PROFILES[STAFF]
    assert any("R296" in line for line in warned), warned


def test_the_read_model_reports_the_users_projection_and_nothing_else(client, pg_store, headers):
    """端到端一句真话：画像接口吐的部门 == ``GET /users`` 那条 users 投影里的部门。"""
    mine = client.get(PROFILE_PATH, headers=headers(STAFF)).json()["profile"]
    listed = next(
        row for row in client.get("/api/v1/users", headers=headers(ADMIN)).json()["users"]
        if row["username"] == STAFF
    )

    assert mine["department"] == listed["department"] == RESEARCH, (mine, listed)
    assert LEGACY not in _json(mine)