"""R290: 部门归属要有写口，而这道写口不能自助。

病灶（上一班 Avicenna 取证，本班在基点 ec42480 上自己复过一遍）：用户侧今天只有
``POST /users``（``app/api/v1/auth.py:98``）、``DELETE /users/{user_id}``（:113）、
``PUT /users/password``（:123）三枚写口，而 ``GET /users``（:90）今天是回
``department`` 的（``app/common/auth.py:543`` 那条投影）——读得到、写不了，
"把张三从市场部挪到研发部"只能删号重建。

本文件钉四件事，每一件都对应工单里一条判据：

* ① 新写口的形状照 ``PUT /users/password`` 同一族（body 里带 ``username``），落在
  ``app/api/v1/auth.py:139``；
* ② 闸只问权限、不问是不是本人：``PUT /users/password`` 那半条自助豁免
  （``app/api/v1/auth.py:129``）在部门上必须是禁项，三态各一枚钉；
* ③ 空串与"不改"是两件事：少传字段一个字都不写，清空必须显式发 ``""``；
* ④ 写一笔进的是本仓既有那一条 ``app.common.audit.record_audit``，不新造第二套账。

测试跑在进程内用户表上（``tests/conftest.py`` 把 ``DATABASE_URL`` 钉在保留端口，
``app/common/auth.py`` 的导入期探针必然红，``_using_memory_store()`` 为真）；PG 那一支
另由假表单独判，一条真连接都不建。审计出口一律换成探针：本文件不往台账里写一个字节，
也不碰任何持久化后端。
"""
from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
ROUTE_SOURCE = ROOT / "app" / "api" / "v1" / "auth.py"

ROUTE_PATH = "/api/v1/users/department"
MARKETING = "市场部"
RESEARCH = "研发部"

ADMIN = "r290-admin"
STAFF_SELF = "r290-staff-self"
VICTIM = "r290-victim"


def _record_audit_parameter_names() -> list[str]:
    """``record_audit`` 的真实参数名，在任何人把它换成探针之前取下来。"""
    from app.common.audit import record_audit

    return list(inspect.signature(record_audit).parameters)


RECORD_AUDIT_PARAMETERS = _record_audit_parameter_names()


def headers_for(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


@pytest.fixture()
def users(monkeypatch):
    """A process-local user table this file owns, driven through the real ASGI stack."""
    from app.common import auth

    monkeypatch.setattr(auth, "_MEM_USERS", {})

    def add(username: str, role: str = "staff", department: str | None = MARKETING) -> str:
        ok, message = auth.create_user(username, "r290-secret", role=role, department=department)
        assert ok, message
        return username

    add(ADMIN, role="admin")
    add(STAFF_SELF)
    add(VICTIM)
    return add


@pytest.fixture()
def client(users):
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def journal(monkeypatch):
    """Capture every ``record_audit`` the request path makes, writing nothing.

    Four modules reach the same exit through four different bindings, so all four are
    swapped for one probe: this route holds the module and calls late
    (``audit_log.record_audit``, i.e. the attribute on ``app.common.audit``), while
    ``app.common.authorization``, ``app.main`` and ``app.rag.filters`` imported the name
    at module load and keep their own reference.
    """
    import app.common.authorization as authorization
    import app.main as main
    import app.rag.filters as rag_filters
    from app.common import audit as audit_log

    calls: list[dict] = []

    def spy(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {}

    for module in (audit_log, authorization, main, rag_filters):
        monkeypatch.setattr(module, "record_audit", spy)
    return calls


def _shape(call: dict) -> dict:
    """Project one captured call onto the parameter names of ``record_audit``.

    The names are read at import time, before the ``journal`` fixture swaps the exit for a
    probe: asking ``inspect.signature`` later would describe the spy (``*args, **kwargs``)
    instead of the real signature, which is exactly the shape this pin is supposed to check.
    """
    row = {RECORD_AUDIT_PARAMETERS[index]: value for index, value in enumerate(call["args"])}
    row.update(call["kwargs"])
    return row


def _lines(journal: list[dict], action: str) -> list[dict]:
    return [_shape(call) for call in journal if _shape(call).get("action") == action]


def _department_of(username: str) -> str:
    from app.common import auth

    return str((auth.get_user(username) or {}).get("department") or "")

# --------------------------------------------------------------- 判据②：三态各一枚钉


def test_an_admin_moves_another_account(client, journal):
    """第一态：持 ``users:manage`` 的调用点改得动，而且改的是数据库里那一列。"""
    response = client.put(
        ROUTE_PATH,
        json={"username": VICTIM, "department": RESEARCH},
        headers=headers_for(ADMIN),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["department"] == RESEARCH
    assert body["changed"] is True
    assert _department_of(VICTIM) == RESEARCH
    # GET /users 那条读投影（app/common/auth.py:543）必须立刻看得见同一枚值，否则前端 G10
    # 写完还得不到回执。
    listed = client.get("/api/v1/users", headers=headers_for(ADMIN)).json()["users"]
    assert next(row for row in listed if row["username"] == VICTIM)["department"] == RESEARCH


def test_a_staff_cannot_move_itself(client, journal):
    """第二态（本单最重要的一格）：本人改自己同样拒，而且拒的是权限那张脸。

    回 400「参数不合法」也算"拒了"，但那是把闸做成了校验：调用方会从 body 里读出
    "原来只是参数写错了"，换一种拼法再来一次。这里钉的是码与语义，不是状态码不为 200。
    """
    before = _department_of(STAFF_SELF)

    response = client.put(
        ROUTE_PATH,
        json={"username": STAFF_SELF, "department": RESEARCH},
        headers=headers_for(STAFF_SELF),
    )

    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert "users:manage" in detail, detail
    assert "permission_denied" in detail, detail
    assert _department_of(STAFF_SELF) == before == MARKETING


def test_a_staff_cannot_move_someone_else(client, journal):
    """第三态：改别人也拒，读回的还是原值。"""
    response = client.put(
        ROUTE_PATH,
        json={"username": VICTIM, "department": RESEARCH},
        headers=headers_for(STAFF_SELF),
    )

    assert response.status_code == 403, response.text
    assert "users:manage" in response.json()["detail"]
    assert _department_of(VICTIM) == MARKETING


def test_the_authority_face_comes_before_any_validation(client, journal):
    """闸在第一行：连 ``department`` 都没传，staff 拿到的仍然是 403 而不是 200 空转。

    少了这一格，"少传即不改"就变成 staff 探测别人归属的免费读口。
    """
    response = client.put(
        ROUTE_PATH,
        json={"username": VICTIM},
        headers=headers_for(STAFF_SELF),
    )

    assert response.status_code == 403, response.text
    assert "users:manage" in response.json()["detail"]


def test_a_staff_probing_an_unknown_account_does_not_learn_it_exists(client, journal):
    """不存在的账号在闸后面才看得见：staff 问 ``ghost`` 得到的是 403，不是 404。"""
    response = client.put(
        ROUTE_PATH,
        json={"username": "r290-ghost", "department": RESEARCH},
        headers=headers_for(STAFF_SELF),
    )

    assert response.status_code == 403, response.text
    assert "users:manage" in response.json()["detail"]


def test_an_anonymous_request_never_reaches_the_handler(client, journal):
    response = client.put(ROUTE_PATH, json={"username": VICTIM, "department": RESEARCH})

    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "authentication_required"
    assert _department_of(VICTIM) == MARKETING


# ------------------------------------------------------- 判据③：空串与"不改"是两件事


def test_a_missing_field_leaves_the_department_alone(client, journal, monkeypatch):
    """少传字段 ⇒ 原值不动，而且一次写都不发。

    ``create_user`` 那支 ``department=data.department or None``（app/api/v1/auth.py:106）
    说明这一列今天本来就允许空；正因为它允许空，"漏传"绝不能被读成"清空"。
    """
    from app.common import auth

    seen = []
    real = auth.update_department

    def spy(username, department):
        seen.append((username, department))
        return real(username, department)

    monkeypatch.setattr(auth, "update_department", spy)

    response = client.put(
        ROUTE_PATH,
        json={"username": VICTIM},
        headers=headers_for(ADMIN),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is False
    assert body["department"] == MARKETING
    assert seen == [], seen
    assert _department_of(VICTIM) == MARKETING


def test_an_explicit_null_leaves_the_department_alone(client, journal):
    """``department: null`` 与"没说"同解：清空只有 ``""`` 这一条路。

    前端把未选的 select 序列化成 null 是常态，那一发不能把人踢出部门。
    """
    response = client.put(
        ROUTE_PATH,
        json={"username": VICTIM, "department": None},
        headers=headers_for(ADMIN),
    )

    assert response.status_code == 200, response.text
    assert response.json()["changed"] is False
    assert _department_of(VICTIM) == MARKETING


def test_clearing_the_department_is_an_explicit_action(client, journal):
    """显式空串 ⇒ 清空；内存表落 ""、PG 落 NULL，读侧同解（见 PG 支那一枚钉）。"""
    response = client.put(
        ROUTE_PATH,
        json={"username": VICTIM, "department": ""},
        headers=headers_for(ADMIN),
    )

    assert response.status_code == 200, response.text
    assert response.json()["department"] == ""
    assert response.json()["changed"] is True
    assert _department_of(VICTIM) == ""


def test_a_departmentless_staff_is_frozen_out_not_widened(client, journal):
    """"无归属能看到什么"是现取的，不是文案：清空之后检索面整条拒掉。

    ``app/rag/filters.py:135`` 对非管理员的空部门直接 ``authorization_unavailable``，
    ``app/common/policy.py:206`` 对任何带部门的资源判 ``resource_scope_missing``。
    所以"挪出去"是关掉数据范围，而不是放开——这一格钉住它，免得哪天有人把清空写成福利。
    """
    from app.agents.contracts import Principal
    from app.common import auth
    from app.rag.filters import RetrievalScopeError, resolve_document_retrieval_scope

    client.put(
        ROUTE_PATH,
        json={"username": VICTIM, "department": ""},
        headers=headers_for(ADMIN),
    )
    principal = Principal.from_user(auth.get_user(VICTIM))
    assert principal.department == ""

    with pytest.raises(RetrievalScopeError) as refused:
        resolve_document_retrieval_scope(principal)
    assert refused.value.code == "authorization_unavailable"

# --------------------------------------------- 判据①＋④：形状照同族，留痕走既有那一本


def test_the_route_is_a_put_with_a_username_in_the_body(client):
    """形状钉：``PUT /api/v1/users/department``，body 与 ``ChangePasswordRequest`` 同族。

    用 OpenAPI 表徵来判而不是数装饰器：``tests/test_deployment_guards.py:555`` 早就说过
    新版 Starlette 直接遍历 ``app.routes`` 会漏掉已挂载的路由。
    """
    spec = client.get("/openapi.json").json()
    record = spec["paths"][ROUTE_PATH]["put"]
    reference = record["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    component = spec["components"]["schemas"][reference.rsplit("/", 1)[-1]]

    assert reference.endswith("UpdateDepartmentRequest"), reference
    assert set(component["properties"]) == {"username", "department"}, component["properties"]
    assert component["required"] == ["username"], component["required"]
    assert "anyOf" in component["properties"]["department"], component["properties"]["department"]


def test_a_successful_move_records_one_line_in_the_existing_journal(client, journal):
    """判据④：闸那一笔与本单这一笔在同一本账里，动作码同一枚 ``users:manage``。

    回放时"谁批准了这次挪动、把谁从哪挪到哪"是同一本账的两行，不是两套口径；五枚位置参
    与既有调用点（``app/api/v1/artifacts.py:42``）逐位同形，没有为本单新设字段。
    """
    from app.common.permissions import ACTION_MANAGE_USERS

    response = client.put(
        ROUTE_PATH,
        json={"username": VICTIM, "department": RESEARCH},
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 200, response.text

    lines = _lines(journal, ACTION_MANAGE_USERS)
    assert [line["outcome"] for line in lines] == ["allowed", "allowed"], lines
    gate, write = lines
    assert gate["resource"] == "users"
    assert write["resource"] == f"users:{VICTIM}"
    assert write["reason"] == "department_updated"
    assert write["before_summary"] == {"department": MARKETING}
    assert write["after_summary"] == {"department": RESEARCH}
    assert write["principal"].username == ADMIN, "主体由 record_audit 自己投影，本单不另填"


def test_a_refused_move_is_recorded_by_the_gate_itself(client, journal):
    """拒也要有账，而且那本账是既有闸记的：本单没有为拒绝另写一条通路。"""
    from app.common.permissions import ACTION_MANAGE_USERS

    client.put(
        ROUTE_PATH,
        json={"username": VICTIM, "department": RESEARCH},
        headers=headers_for(STAFF_SELF),
    )

    denied = [line for line in _lines(journal, ACTION_MANAGE_USERS) if line["outcome"] == "denied"]
    assert len(denied) == 1, denied
    assert denied[0]["reason"] == "permission_denied"
    assert denied[0]["principal"].username == STAFF_SELF


def test_an_attempt_against_an_unknown_account_is_recorded_as_a_failure(client, journal):
    """404 那一支也留痕：有人拿别人的用户名为探针试这扇门，台账里要查得到。"""
    from app.common.permissions import ACTION_MANAGE_USERS

    response = client.put(
        ROUTE_PATH,
        json={"username": "r290-ghost", "department": RESEARCH},
        headers=headers_for(ADMIN),
    )
    assert response.status_code == 404, response.text

    lines = _lines(journal, ACTION_MANAGE_USERS)
    assert [line["outcome"] for line in lines] == ["allowed", "failure"], lines
    assert lines[1]["reason"] == "user_not_found"
    assert lines[1]["resource"] == "users:r290-ghost"


def test_the_endpoint_invented_no_parallel_audit_machinery():
    """④的另一半：本仓用户侧今天有审计出口（``app/common/audit.py:512``），照它用。"""
    source = ROUTE_SOURCE.read_text(encoding="utf-8")

    assert "from app.common import audit as audit_log" in source
    assert "from app.common.audit import" not in source, "迟到绑定才让台账可测（alerts.py:19 的教训）"
    assert "def record" not in source, "不许在路由文件里长出第二枚记账函数"
    assert "logging" not in source, "不许另开一条日志通路冒充审计"


# --------------------------------------------- 判据③的存储那一半：PG 支与生产拒绝


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _TempUsers:
    """一张只认归属那一句 UPDATE 的临时 users 表（写法照 tests/test_auth.py:195）。"""

    STATEMENT = "update users set department = %s where username = %s"

    def __init__(self, rows: dict[str, str | None]):
        self.rows = dict(rows)
        self.statements: list[tuple[str, tuple]] = []
        self.commits = 0

    def connect(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def commit(self):
        self.commits += 1

    def close(self):
        return None

    def execute(self, sql, params=()):
        statement = " ".join(sql.split()).lower()
        self.statements.append((statement, tuple(params)))
        if statement != self.STATEMENT:
            raise AssertionError(f"the temporary users table does not speak: {statement}")
        department, username = params
        if username not in self.rows:
            return _Result(rowcount=0)
        self.rows[username] = department
        return _Result(rowcount=1)


@pytest.fixture()
def pg_users(monkeypatch, test_database_url):
    """把 ``app.common.auth`` 接到临时表上，一条真连接都不许建（R20 口径）。"""
    from app.common import auth

    driver = auth.psycopg
    if driver is None:  # 没装驱动也要走同一条 PG 代码分支
        from types import SimpleNamespace

        driver = SimpleNamespace(errors=SimpleNamespace(UniqueViolation=RuntimeError))

    def refuse_real_connection(*_args, **_kwargs):
        raise AssertionError("R290 不许碰宿主数据库")

    monkeypatch.setattr(driver, "connect", refuse_real_connection, raising=False)
    monkeypatch.setattr(auth, "psycopg", driver, raising=False)
    monkeypatch.setattr(auth, "_db_ready", True)
    assert auth._PG_URL == test_database_url, auth._PG_URL
    assert auth._using_memory_store() is False

    def use(table: _TempUsers):
        monkeypatch.setattr(auth, "_raw_conn", table.connect)
        return auth

    return use


def test_the_pg_branch_writes_the_named_row_only(pg_users):
    auth = pg_users(_TempUsers({VICTIM: MARKETING, "someone-else": RESEARCH}))
    table = auth._raw_conn()

    ok, message = auth.update_department(VICTIM, RESEARCH)

    assert ok is True, message
    assert table.rows == {VICTIM: RESEARCH, "someone-else": RESEARCH}
    assert table.commits == 1
    statement, params = table.statements[0]
    assert statement == _TempUsers.STATEMENT, statement
    assert params == (RESEARCH, VICTIM), params
    assert "like" not in statement, "R20 删掉的扫荡不许从生产侧长回来"


def test_the_pg_branch_stores_null_for_a_cleared_department(pg_users):
    """清空在 PG 里是 NULL，与 ``create_user`` 那支 ``data.department or None`` 同一口径。"""
    auth = pg_users(_TempUsers({VICTIM: MARKETING}))
    table = auth._raw_conn()

    ok, _ = auth.update_department(VICTIM, None)

    assert ok is True
    assert table.statements[0][1] == (None, VICTIM), table.statements
    assert table.rows[VICTIM] is None


def test_the_pg_branch_reports_an_unknown_account_without_changing_any_row(pg_users):
    auth = pg_users(_TempUsers({VICTIM: MARKETING}))
    table = auth._raw_conn()

    ok, message = auth.update_department("r290-ghost", RESEARCH)

    assert ok is False
    assert message == auth.USER_NOT_FOUND
    assert table.rows == {VICTIM: MARKETING}


def test_production_refuses_to_move_a_department_in_the_process_local_table(monkeypatch):
    """生产 + 内存表 ⇒ 拒。归属是权限范围，两台 worker 各记一份就是两个答案。"""
    from app.common import auth

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "psycopg", None, raising=False)
    monkeypatch.setattr(auth, "_db_ready", False)
    monkeypatch.setattr(
        auth,
        "_MEM_USERS",
        {VICTIM: {"id": 1, "username": VICTIM, "role": "staff", "department": MARKETING}},
    )

    ok, message = auth.update_department(VICTIM, RESEARCH)

    assert ok is False
    assert message == "production_user_store_unavailable"
    assert auth._MEM_USERS[VICTIM]["department"] == MARKETING

def test_the_refusal_and_the_miss_answer_with_the_existing_words(client, journal):
    """对外那张脸的原文钉：403 用既有闸那句，404 用 DELETE /users 那句，都不新造。"""
    refused = client.put(
        ROUTE_PATH,
        json={"username": STAFF_SELF, "department": RESEARCH},
        headers=headers_for(STAFF_SELF),
    )
    assert refused.status_code == 403, refused.text
    assert refused.json() == {"detail": "权限不足: users:manage (permission_denied)"}, refused.json()

    missing = client.put(
        ROUTE_PATH,
        json={"username": "r290-ghost", "department": RESEARCH},
        headers=headers_for(ADMIN),
    )
    assert missing.status_code == 404, missing.text
    assert missing.json() == {"detail": "用户不存在"}, missing.json()

    anonymous = client.put(ROUTE_PATH, json={"username": VICTIM, "department": RESEARCH})
    assert anonymous.status_code == 401, anonymous.text
    assert anonymous.json() == {"detail": "authentication_required"}, anonymous.json()


# ------------------------------------------------- 判据⑦：反证钉（摘闸 / 少传即清空）

GATE_CALL = 'authorize_request(request, ACTION_MANAGE_USERS, resource_name="users")'
PASSWORD_STYLE_GATE = """principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    if data.username != principal.username and ACTION_MANAGE_USERS not in principal.permissions:
        raise HTTPException(status_code=403, detail="权限不足: users:manage")"""


def _route_node(source: str, name: str = "update_user_department"):
    for node in ast.parse(source).body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"找不到 {name}，本钉无从下手")


def _body_statements(route) -> list[ast.stmt]:
    body = list(route.body)
    first = body[0] if body else None
    value = getattr(first, "value", None) if isinstance(first, ast.Expr) else None
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        body = body[1:]  # 去掉 docstring，别让散文参与判定
    return body


def _is_manage_gate(node) -> bool:
    call = node.value if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) else None
    if call is None or getattr(call.func, "id", "") != "authorize_request":
        return False
    return "ACTION_MANAGE_USERS" in " ".join(ast.unparse(argument) for argument in call.args)


def _has_self_service_exemption(route) -> bool:
    """``data.username != principal.username`` 与权限并排出现 = 自助豁免那一支。

    两半是 ``and`` 连起来的，所以 ``BoolOp`` 也得判：只看 ``Compare`` 会漏掉整支豁免
    （单个比较的 unparse 里根本没有 ``ACTION_MANAGE_USERS``），那是一枚假绿。
    """
    for node in ast.walk(route):
        if isinstance(node, (ast.Compare, ast.BoolOp, ast.UnaryOp)):
            text = ast.unparse(node)
            if "principal.username" in text and "ACTION_MANAGE_USERS" in text:
                return True
    return False


def _no_op_branch_index(body) -> int | None:
    for index, node in enumerate(body):
        if isinstance(node, ast.If) and "data.department is None" in ast.unparse(node.test):
            if any(isinstance(inner, ast.Return) for inner in ast.walk(node)):
                return index
    return None


def _write_call_index(body) -> int | None:
    for index, node in enumerate(body):
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and ast.unparse(inner.func).endswith("update_department"):
                return index
    return None


def _gate_report(source: str) -> dict:
    route = _route_node(source)
    body = _body_statements(route)
    no_op = _no_op_branch_index(body)
    write = _write_call_index(body)
    return {
        "gate_first": bool(body) and _is_manage_gate(body[0]),
        "self_service_exemption": _has_self_service_exemption(route),
        "missing_field_is_a_no_op": no_op is not None and (write is None or no_op < write),
    }


def test_the_route_gates_on_authority_only():
    """正面钉：闸在第一行、没有自助豁免、少传在任何写点之前回空。"""
    report = _gate_report(ROUTE_SOURCE.read_text(encoding="utf-8"))

    assert report == {
        "gate_first": True,
        "self_service_exemption": False,
        "missing_field_is_a_no_op": True,
    }, report


def test_the_password_route_keeps_its_exemption_and_this_one_does_not():
    """两把钥匙开两扇门，差别是故意的，不是漏写。"""
    source = ROUTE_SOURCE.read_text(encoding="utf-8")

    assert _has_self_service_exemption(_route_node(source, "change_password")) is True
    assert _has_self_service_exemption(_route_node(source)) is False


def test_counter_evidence_a_self_service_exemption_turns_the_gate_pin_red():
    """反证一（判据②）：把 ``PUT /users/password`` 那半条豁免塞回来，钉必须红。

    只判"今天在位"的门是死的——能被塞回来的代码才需要牙。改动落在内存里的一份副本上，
    收尾再核一次工作树的 sha256：反证钉不许动源码（写法照
    ``tests/test_r246_honest_readiness_claims.py:337``）。
    """
    source = ROUTE_SOURCE.read_text(encoding="utf-8")
    digest = hashlib.sha256(ROUTE_SOURCE.read_bytes()).hexdigest()

    # 只在本路由那一段里替换：GET/POST/DELETE /users 用的是同一句 authorize_request，
    # 全文件替换会塞到别人的函数里去，那枚假绿看起来和真红一样整齐。
    route = _route_node(source)
    segment = ast.get_source_segment(source, route)
    assert segment and GATE_CALL in segment, segment
    mutated_segment = segment.replace(GATE_CALL, PASSWORD_STYLE_GATE, 1)
    assert mutated_segment != segment, "塞不回去就不是反证"
    mutated = source.replace(segment, mutated_segment, 1)
    ast.parse(mutated)

    report = _gate_report(mutated)
    assert report["gate_first"] is False, report
    assert report["self_service_exemption"] is True, report
    assert hashlib.sha256(ROUTE_SOURCE.read_bytes()).hexdigest() == digest, "反证钉不许动工作树"


def test_counter_evidence_dropping_the_no_op_branch_turns_the_semantics_pin_red():
    """反证二（判据③）：删掉"少传即不改"那一支，语义钉必须红。

    删掉之后 ``department`` 缺席会一路走到写点，前端漏传一个字段 = 把人踢出部门，
    正是本单要钉死的那个默认值。
    """
    source = ROUTE_SOURCE.read_text(encoding="utf-8")
    digest = hashlib.sha256(ROUTE_SOURCE.read_bytes()).hexdigest()

    route = _route_node(source)
    body = _body_statements(route)
    index = _no_op_branch_index(body)
    assert index is not None, "工作树里已经没有少传那一支，反证无从下手"
    segment = ast.get_source_segment(source, body[index])
    assert segment and "return" in segment, segment

    mutated = source.replace(segment, "pass", 1)
    assert mutated != source, "删不掉就不是反证"
    ast.parse(mutated)

    assert _gate_report(mutated)["missing_field_is_a_no_op"] is False
    assert _write_call_index(_body_statements(_route_node(mutated))) is not None
    assert hashlib.sha256(ROUTE_SOURCE.read_bytes()).hexdigest() == digest, "反证钉不许动工作树"