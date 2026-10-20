"""R356 · `GET /users` 不许把「存储拒答」说成「这家公司没有用户」。

病（一手现场，`app/common/auth.py:534-536` 修前原文）：

    def list_users() -> list[dict]:
        if _memory_store_denied("user listing"):
            return []

同一枚文件里写侧遇到同一个闸答的是 `return False, "production_user_store_unavailable"`
（`:555-556`）。同一个事实，读侧伪装成空集合，写侧才说实话。`_memory_store_denied` 的
docstring 自己写着「Every caller keeps its previous default-deny behaviour」——对「列名册」
这件事，把拒绝翻译成「零个人」不是 deny，是假话：消费端（`GET /users`，闸在
`ACTION_MANAGE_USERS`）拿到 200 零行，只能画「这一发回包里没有行」。

本文件钉的是三张脸各归各位，而且**两两不共用任何一句措辞**：

| 脸 | 什么时候发生 | 钉它的那一枚 |
|---|---|---|
| 403 `权限不足: users:manage (permission_denied)` | 过了身份、没过 `users:manage` 闸 | `test_the_authorization_gate_still_runs_before_the_roster_is_read` |
| 503 `storage_unavailable` | 生产 + 进程内内存表，`_memory_store_denied("user listing")` 为真 | `test_the_route_answers_503_when_the_user_store_refuses_the_roster` |
| 200 `{"users": []}` | 存储答了话，名册真的零行（干净的库） | `test_a_clean_store_answers_200_with_zero_rows` |

零新增错误码：503 那一格逐字用仓里已有的 `storage_unavailable`
（`app/agents/contracts.py::ErrorEnvelope.code` 的成员），`tests/test_r142_error_code_table_sync.py`
与 `tests/test_error_code_vocabulary.py` 因此必须继续全绿，本文件另钉一次成员制。

`auth.list_users()` 无参调用返回 `[]` 这一枚**遗留读数**今天由三枚外来钉钉着
（`tests/test_r229_auth_semantics.py:88`、`tests/test_deployment_guards.py:288`、
`tests/test_r230_db_ready_selfheal.py:54` + `:577` 的 `type(result) is type([])`），那三枚
文件不在本单写域，所以本单不摘别人的断言，只把路由接到说实话的那一格，并留下
`test_every_production_call_site_asks_for_the_truthful_shape` 这把尺子：`app/**` 里谁调
`list_users()` 谁就必须显式选 `DENIAL_RAISES`，新长一处没选就红——把「忘了表态」挡在
生产代码外，而不是挡在散文里。
"""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
APP_DIR = REPO / "app"
ROUTE_REL = "app/api/v1/auth.py"
CONTRACTS_REL = "app/agents/contracts.py"

DENIED_DETAIL = "storage_unavailable"
GATE_DENIED_DETAIL = "权限不足: users:manage (permission_denied)"


class _Rows:
    """`dict_row` 口径的假结果：只回答 `list_users()` 真会发的那一句 SELECT。"""

    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, rows):
        self._rows = rows
        self.closed = False

    def execute(self, statement, params=None):
        assert statement.startswith("SELECT id, username, role, department, created_at"), statement
        return _Rows(self._rows)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def store_refuses(monkeypatch):
    """生产 + 进程内内存表：`_memory_store_denied("user listing")` 为真的那一副世界。

    `psycopg is None` 让 R230 的重探直接不试（缺驱动不是抖动，见 `_retry_readiness_probe`
    代价 4），所以这一格既不建连也不开 socket；本 fixture 另把两枚建连入口换成记账桩，
    「拒答的路上一次连接都不该开」是读数而不是推测。
    """
    from app.common import auth

    connects = []

    def _no_connect():
        connects.append(1)
        raise AssertionError("拒答那一格不该开任何一次连接")

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "psycopg", None)
    monkeypatch.setattr(auth, "_db_ready", False)
    monkeypatch.setattr(auth, "_raw_conn", _no_connect)
    monkeypatch.setattr(auth, "_connect_for_request", lambda operation: connects.append(1))
    return SimpleNamespace(connects=connects)


def _identity(monkeypatch, username: str, role: str) -> dict:
    """把门禁那一层的账号 lookup 换成受控值，好让请求真的走到路由（401 不是本单要画的脸）。"""
    from app.common import auth

    monkeypatch.setattr(
        auth,
        "get_user",
        lambda name: {"username": username, "role": role, "department": "ops"} if name == username else None,
    )
    return {"Authorization": f"Bearer {auth.create_token(username)}"}


def _clean_store(monkeypatch, rows: list[dict] | None = None) -> None:
    """把这一副世界换成「存储答了话」：驱动在位、探针说连上了、名册由 `_get_conn` 给。

    三枚一起摆是必须的：`_using_memory_store()` = `psycopg is None or not _db_ready`，
    少摆一枚就退回进程内内存表，那张脸读的是 `_MEM_USERS`，测出来的就不是"干净的库"。
    """
    from app.common import auth

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "psycopg", object())
    monkeypatch.setattr(auth, "_db_ready", True)
    monkeypatch.setattr(auth, "_get_conn", lambda: _Conn(rows=list(rows or [])))


# ------------------------------------------------------------------ 判据①③：503 那张脸


def test_the_route_answers_503_when_the_user_store_refuses_the_roster(client, store_refuses, monkeypatch):
    response = client.get("/api/v1/users", headers=_identity(monkeypatch, "r356-admin", "admin"))

    assert response.status_code == 503, response.text
    assert response.json() == {"detail": DENIED_DETAIL}
    assert store_refuses.connects == [], "拒答那一格仍然不该开任何一次连接"


def test_a_refusal_is_never_rendered_as_an_empty_roster(client, store_refuses, monkeypatch):
    """本单的唯一动机：这一格回包里的每一枚字节都在说「问不到」，没有一处在说「没人」。"""
    response = client.get("/api/v1/users", headers=_identity(monkeypatch, "r356-admin", "admin"))

    assert '"users"' not in response.text, response.text
    assert "users" not in response.json(), response.json()


def test_the_helper_raises_a_typed_refusal_when_asked_for_the_truthful_shape(store_refuses):
    from app.common import auth

    with pytest.raises(auth.UserStoreUnavailable):
        auth.list_users(denial=auth.DENIAL_RAISES)


def test_the_legacy_default_still_answers_the_pinned_empty_reading(store_refuses):
    """取证钉，不是许可：无参调用今天仍回 `[]`，因为三枚外来钉把它钉在那儿（见模块 docstring）。

    这一格不主张「这样对」，它主张「摘钉这一步不在本单写域里」。谁改了默认形状，那三枚钉
    先红；同时本文件的调用点尺子会要求生产代码显式表态。
    """
    from app.common import auth

    got = auth.list_users()

    assert got == []
    assert type(got) is list


def test_an_unknown_denial_shape_is_not_read_as_the_lie_again(store_refuses):
    from app.common import auth

    with pytest.raises(ValueError):
        auth.list_users(denial="raise")  # 拼错的那一枚：宁可当场抛，不许静默退回空名册


# ------------------------------------------------------------------ 判据③：200 零行那张脸


def test_a_clean_store_answers_200_with_zero_rows(client, monkeypatch):
    """生产 + PostgreSQL 连得上 + 名册真的空：这张脸必须还能发生，且与 503 不是一句话。"""
    _clean_store(monkeypatch)

    response = client.get("/api/v1/users", headers=_identity(monkeypatch, "r356-admin", "admin"))

    assert response.status_code == 200, response.text
    assert response.json() == {"users": []}


def test_the_roster_projection_still_answers_the_five_keys_r316_reads(client, monkeypatch):
    """判据⑥：`created_at` 仍按现状给，那一屏认的还是这五枚键，一个不多一个不少。"""
    row = {"id": 3, "username": "ops-1", "role": "staff", "department": "ops", "created_at": "2026-09-27T00:00:00+08:00"}
    _clean_store(monkeypatch, [row])

    body = client.get("/api/v1/users", headers=_identity(monkeypatch, "r356-admin", "admin")).json()

    assert set(body) == {"users"}
    assert [sorted(user) for user in body["users"]] == [["created_at", "department", "id", "role", "username"]]
    assert body["users"][0]["created_at"] == row["created_at"]


# ------------------------------------------------------------------ 判据⑥：闸与头的顺序不动


def test_the_authorization_gate_still_runs_before_the_roster_is_read(client, store_refuses, monkeypatch):
    """存储同时处在「拒答」状态时，没过闸的人拿的还是原来那句 403，不是 503。

    顺序钉：`authorize_request(..., ACTION_MANAGE_USERS)` 必须仍在读名册之前。把它挪到后面
    （或对无权者先探存储）这一格当场红——无权者从此可以靠 403/503 的区别探到存储状态，
    那是本单不该顺手打开的一条侧信道。
    """
    response = client.get("/api/v1/users", headers=_identity(monkeypatch, "r356-staff", "staff"))

    assert response.status_code == 403, response.text
    assert response.json() == {"detail": GATE_DENIED_DETAIL}


def test_neither_face_grows_a_cache_header(client, store_refuses, monkeypatch):
    """判据⑥：这一格的响应头今天没有 `Cache-Control`/`Pragma`，本单一枚都不新增。"""
    denied = client.get("/api/v1/users", headers=_identity(monkeypatch, "r356-admin", "admin"))
    _clean_store(monkeypatch)
    clean = client.get("/api/v1/users", headers=_identity(monkeypatch, "r356-admin", "admin"))

    assert denied.status_code == 503 and clean.status_code == 200, (denied.text, clean.text)
    for response in (denied, clean):
        assert "cache-control" not in response.headers, dict(response.headers)
        assert "pragma" not in response.headers, dict(response.headers)


def test_the_three_faces_share_no_words(client, store_refuses, monkeypatch):
    """403 / 503 / 200 三张脸的原文各说各的事，两两不相等，谁也不许替谁说话。"""
    gate = client.get("/api/v1/users", headers=_identity(monkeypatch, "r356-staff", "staff"))
    refused = client.get("/api/v1/users", headers=_identity(monkeypatch, "r356-admin", "admin"))
    _clean_store(monkeypatch)
    empty = client.get("/api/v1/users", headers=_identity(monkeypatch, "r356-admin", "admin"))

    assert [gate.status_code, refused.status_code, empty.status_code] == [403, 503, 200]
    payloads = {gate.text, refused.text, empty.text}
    assert len(payloads) == 3, f"两张脸共用了措辞：{payloads}"
    assert GATE_DENIED_DETAIL in gate.text
    assert refused.text == '{"detail":"storage_unavailable"}', refused.text
    assert empty.text == '{"users":[]}', empty.text


# ------------------------------------------------------------------ 判据①：零新增错误码


def _enum_codes() -> list[str]:
    """从 `app/agents/contracts.py` 现扫 `ErrorEnvelope.code`，本文件零手抄码表。"""
    for node in ast.walk(ast.parse((REPO / CONTRACTS_REL).read_text(encoding="utf-8"))):
        if isinstance(node, ast.ClassDef) and node.name == "ErrorEnvelope":
            for stmt in node.body:
                annotation = getattr(stmt, "annotation", None)
                if isinstance(annotation, ast.Subscript) and getattr(annotation.value, "id", "") == "Literal":
                    codes = [e.value for e in annotation.slice.elts if isinstance(e, ast.Constant)]
                    if codes:
                        return codes
    raise AssertionError("contracts.py 里读不到 ErrorEnvelope.code 的 Literal，判器不许降级成恒真")


def test_the_refusal_face_uses_a_code_the_repository_already_registers():
    assert DENIED_DETAIL in _enum_codes(), "本单不许为了「存储拒答」新造一枚码"


# ------------------------------------------------------------------ 判据②：调用点取证尺子


def _list_users_calls() -> list[dict]:
    """`app/**` 里对 `auth.list_users(...)` / `list_users(...)` 的每一处**调用**（不含定义）。"""
    found = []
    for path in sorted(APP_DIR.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute):
                if getattr(func.value, "id", "") != "auth":
                    continue
                callee = func.attr
            elif isinstance(func, ast.Name):
                callee = func.id
            else:
                continue
            if callee != "list_users":
                continue
            denial = next((kw.value for kw in node.keywords if kw.arg == "denial"), None)
            found.append({
                "file": path.relative_to(REPO).as_posix(),
                "line": node.lineno,
                "denial": getattr(denial, "attr", None) if isinstance(denial, ast.Attribute) else None,
                "on": getattr(getattr(denial, "value", None), "id", "") if isinstance(denial, ast.Attribute) else None,
            })
    return found


def test_every_production_call_site_asks_for_the_truthful_shape():
    """判据②的尺子：生产代码里每一处名册读取都必须显式选 `DENIAL_RAISES`。

    顺手把「实测只有一处」钉住：现在只有路由那一枚消费者。将来长出第二处而没表态，这一格
    当场红——异常不许从缝里漏出去，拒答也不许从缝里漏成空集合，两个方向由同一把尺子量。
    """
    calls = _list_users_calls()

    assert [call["file"] for call in calls] == [ROUTE_REL], calls
    for call in calls:
        assert call["denial"] == "DENIAL_RAISES", call
        assert call["on"] == "auth", f"{call} 必须取 auth 模块那枚具名常量，不许自己拼字符串"


def test_the_route_does_not_re_derive_the_refusal_itself():
    """接线钉：路由只调 `auth.list_users`，本单没在路由里再抄一份「存储可用性」判定。"""
    source = (REPO / ROUTE_REL).read_text(encoding="utf-8")

    assert "auth.list_users(denial=auth.DENIAL_RAISES)" in source
    assert "_memory_store_denied" not in source, "路由绕过 helper 自己问那道闸 = 第二本手抄账"
    assert "user_storage_state" not in source, "用存储状态反推拒答同样是第二本账"
