"""R494 · GET /api/v1/profile 多出来的那枚 ``clearance`` 只能是真源的影子，不许是第二把尺。

病（改前现场，取证 = 主树 HEAD 5b8d767）：``app/api/v1/auth.py`` 的 ``GET /profile`` 回
``{"profile": ...}``，那一格里只有 ``auth.get_user()`` 从 ``users`` 现取的三列
（username / role / department），加上画像存储真读到的 position / preferences / updated_at。
**没有 ``clearance``。** 于是员工在界面上问第三句最基本的话——「我能读到哪几级文档」——无处可查，
而这个数检索闸门今天本来就算得出来：``app/rag/filters.py`` 拿 ``principal.clearance`` 生成
``classification_levels``，``app/agents/contracts.py::Principal.from_user`` 又拿
``app/common/rbac.py::clearance_for(role)`` 造出它。本单补的是「把已经算得出的事说出去」这一格，
不是再算一遍，更不是再立一把尺。

判据 → 用例

| 判据 | 钉 |
|---|---|
| ① 只加一枚只读派生字段，值现场取自 ``clearance_for(role)`` | test_every_role_gets_the_level_the_role_table_gives / test_the_level_is_the_same_ruler_the_retrieval_gate_uses / test_the_cell_is_a_plain_positive_integer |
| ① 读不到 role 就整格不出现，绝不猜一枚 1（理由写在路由 docstring 里） | test_an_unreadable_user_row_omits_the_cell_instead_of_guessing_one / test_a_user_row_without_a_role_omits_the_cell_too |
| ① 不写第二份档位表／第二把尺 | test_the_route_owns_no_second_clearance_table / test_no_api_route_invents_a_role_to_level_map / test_the_role_is_read_from_the_authoritative_row_not_the_merged_profile |
| ④ 词表外的角色走真源自己的答案：本单不在出口加白名单（加了就是第二把尺） | test_an_unknown_role_gets_the_true_sources_own_answer |
| ③ 除这一格外这张回执一字未改；R296 那支拒自报部门的闸没被挪动 | test_the_rest_of_the_answer_is_unchanged / test_a_self_reported_department_is_still_refused_whole |
| ⑤ 职位与偏好真能写回去（夹具内），回执里的档位仍与真源同源 | test_the_write_leg_still_round_trips_position_and_preferences |
| ① 判据落在 docstring 上，不是落在注释里（摘掉说理就红） | test_the_docstring_says_why_the_cell_can_be_absent |

🔴 反证三刀（逐枚读数写在交回里；手法＝把生产码摘掉后复跑本件，变异只在临时副本，盘上被跟踪文件全程只读）：
**刀一** 摘掉 ``if role:`` 那一格守卫（无条件写 ``clearance_for(role)``）⇒ ②那两枚「整格不出现」当场红；
**刀二** 把 ``clearance_for(role)`` 换成常量 1（第二把尺最省事的写法）⇒ ①的三枚档位钉全红；
**刀三** 把角色到档位的映射抄进 ``auth.py`` ⇒ 两枚「不许长第二份表」的形状钉红。

🔴 效力边界：全部跑在 ``TestClient`` + 进程内替身台账上，不求值真实 SQL、不碰真库、不起服务、
不打模型、不动容器；它证明的是「这一格与真源同源、读不到就不开口」，闸门的运行时行为仍归
``tests/test_retrieval_permissions.py`` 那一族负责。
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.common.rbac import ROLE_CLEARANCE, allowed_levels, clearance_for

ROOT = Path(__file__).resolve().parents[1]
ROUTE_REL = "app/api/v1/auth.py"
PROFILE_PATH = "/api/v1/profile"

PASSWORD = "r494-secret"
RESEARCH = "研发部"
POSITION = "工程师"
PREFERENCES = ["图表优先"]
UNKNOWN_ROLE = "developer"
#: 四档角色：名单取真源 ROLE_CLEARANCE 的键，本文件不抄第二份角色表。
ROLE_ROWS = {role: f"r494-{role}" for role in ROLE_CLEARANCE}


# ==================== 现读工具 ====================


def _route_source() -> str:
    return (ROOT / ROUTE_REL).read_text(encoding="utf-8")


def _route_tree() -> ast.Module:
    return ast.parse(_route_source())


def _function(tree: ast.Module, name: str):
    """找路由函数：``async def`` 与 ``def`` 两种形状都得认，否则锚点自己先瞎。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _role_to_int_dicts(tree: ast.Module):
    """扫「>=2 枚角色名做键、>=2 个整数做值」的 dict 字面量——那就是第二份档位表的形状。"""
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        ints = [v for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, int)]
        if len(keys & set(ROLE_CLEARANCE)) >= 2 and len(ints) >= 2:
            hits.append((node.lineno, sorted(keys & set(ROLE_CLEARANCE))))
    return hits


# ==================== 测试替身 ====================


@pytest.fixture()
def users(monkeypatch):
    """进程内用户表（``users`` 的替身）：本文件独占，随 monkeypatch 撤掉。"""
    from app.common import auth

    monkeypatch.setattr(auth, "_MEM_USERS", {})

    def add(username: str, role: str = "staff", department: str = RESEARCH) -> str:
        ok, message = auth.create_user(username, PASSWORD, role=role, department=department)
        assert ok, message
        return username

    for role, username in ROLE_ROWS.items():
        add(username, role=role)
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


def _profile_of(client, headers, username) -> dict:
    response = client.get(PROFILE_PATH, headers=headers(username))
    assert response.status_code == 200, response.text
    return response.json()["profile"]


# ==================== 判据①：这一格与真源同源 ====================


def test_every_role_gets_the_level_the_role_table_gives(client, headers):
    """四档各发一次 GET：回执里的档位逐枚等于 ``clearance_for(role)``，也就是 ``ROLE_CLEARANCE``。"""
    seen = {}
    for role, username in ROLE_ROWS.items():
        body = _profile_of(client, headers, username)
        assert "clearance" in body, f"{role} 这一档今天没拿到档位：{body}"
        assert body["clearance"] == clearance_for(role), body
        assert body["clearance"] == ROLE_CLEARANCE[role], body
        seen[role] = body["clearance"]
    # 档位不是四枚同值的装饰：staff 与 admin 必须不同，否则上面三行等价于一句空话
    assert seen["staff"] < seen["admin"], seen
    assert seen["manager"] == seen["admin"] - 1, seen


def test_the_level_is_the_same_ruler_the_retrieval_gate_uses(client, headers):
    """同一枚档位必须与身份层算出的那个数逐字相等：一把尺，不是两本账。

    ``Principal.from_user`` 造 ``principal.clearance``，而 ``app/rag/filters.py`` 把它展开成
    ``classification_levels``。界面那一格若与这两个读数不同，说的就是假话。
    """
    from app.agents.contracts import Principal
    from app.common import auth

    for role, username in ROLE_ROWS.items():
        body = _profile_of(client, headers, username)
        row = auth.get_user(username)
        assert row is not None, username
        assert body["clearance"] == Principal.from_user(row).clearance, (role, body)
        assert list(allowed_levels(role)) == list(range(1, body["clearance"] + 1)), (role, body)


def test_the_cell_is_a_plain_positive_integer(client, headers):
    """界面直接要画它，所以形状钉死：int、正数、不是 bool、也不是「1-3」这种字符串。"""
    for username in ROLE_ROWS.values():
        value = _profile_of(client, headers, username)["clearance"]
        assert isinstance(value, int) and not isinstance(value, bool), repr(value)
        assert value > 0, repr(value)


# ==================== 判据②：读不到 role 就整格不出现 ====================


def test_an_unreadable_user_row_omits_the_cell_instead_of_guessing_one(memory_store, monkeypatch):
    """``users`` 那一行读不到（``get_user`` 答 None）⇒ 出口只交 username，档位那一格整格缺席。

    这是本单最硬的一格：``clearance_for("")`` 自己会回 1（``ROLE_CLEARANCE.get(role or "staff", 1)``），
    所以「猜一枚 1」在代码里长得跟「算出 1」一模一样，屏上那句「你能读到第 1 级」就是假话。

    走的是**直接调路由**而不是发 HTTP：``app/main.py`` 的鉴权中介自己也要 ``get_user``，人不在时
    它先答 401 ``authentication_required``，那一发根本到不了出口——所以 HTTP 这一腿今天证的是
    「闸门先拒」，而本判据要问的是出口在拿到一枚读不到角色的记录时怎么开口。两种形状各钉一枚：
    行完全读不到（本枚，直接调）与行在、角色那一列为空（下一枚，走真 HTTP）。
    """
    import asyncio

    from app.api.v1.auth import get_my_profile
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: None)
    request = SimpleNamespace(state=SimpleNamespace(username=ROLE_ROWS["manager"]))

    body = asyncio.run(get_my_profile(request))["profile"]

    assert "clearance" not in body, f"读不到角色却给了档位：{body}"
    assert body["username"] == ROLE_ROWS["manager"], body


def test_a_user_row_without_a_role_omits_the_cell_too(client, headers, monkeypatch):
    """行在、但角色那一列是空的（缺键 / 空串 / 全空格三种形状）⇒ 同样整格不出现，不落回 staff。"""
    from app.common import auth

    shapes = (
        {"username": ROLE_ROWS["admin"]},
        {"username": ROLE_ROWS["admin"], "role": ""},
        {"username": ROLE_ROWS["admin"], "role": "   "},
    )
    for row in shapes:
        monkeypatch.setattr(auth, "get_user", lambda username, _row=row: dict(_row))

        body = _profile_of(client, headers, ROLE_ROWS["admin"])

        assert "clearance" not in body, f"角色那一格读不出，档位却出现了：{row} -> {body}"


# ==================== 判据①的边界：不给出口加白名单 ====================


def test_an_unknown_role_gets_the_true_sources_own_answer(client, headers, monkeypatch):
    """词表外的角色：本单照真源答（``clearance_for`` 的兜底），不在出口再判一次「这角色认不认」。

    钉的是「只有一把尺」而不是「档位有多大」：``tests/test_r357_single_role_roster.py`` 已经把这枚
    静默兜底钉成现状（「不许顺手改成 raise」），出口若在这里加白名单就是第二把尺。
    """
    from app.common import auth

    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {"username": username, "role": UNKNOWN_ROLE, "department": RESEARCH},
    )

    body = _profile_of(client, headers, "r494-whoever")

    assert body["clearance"] == clearance_for(UNKNOWN_ROLE), body
    assert body["clearance"] == clearance_for("staff") == 1, body


# ==================== 判据①的形状：不许长第二份档位表 ====================


def test_the_route_owns_no_second_clearance_table():
    """``app/api/v1/auth.py`` 里不许出现「角色→档位」的字面映射，也不许绕过函数直接取表。"""
    tree = _route_tree()
    route = _function(tree, "get_my_profile")
    assert route is not None, "GET /profile 那枚路由不见了，本件的锚点得先跟着改口"

    # ① 整枚文件里不许有 role→int 的 dict 字面量
    assert _role_to_int_dicts(tree) == [], f"auth.py 长出了一份档位表：{_role_to_int_dicts(tree)}"

    # ② 那枚赋值必须现场调 clearance_for(...)，不是取常量、不是取表
    assigned = [
        node for node in ast.walk(route)
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value == "clearance"
            for t in node.targets
        )
    ]
    assert len(assigned) == 1, f"档位那一格写了 {len(assigned)} 处，判据①要的是恰好一处"
    value = assigned[0].value
    assert isinstance(value, ast.Call), f"档位不是现场算的：{ast.unparse(value)}"
    func = value.func
    assert isinstance(func, ast.Name) and func.id == "clearance_for", ast.unparse(value)

    # ③ 代码只认那把尺的名字，不碰它底下的表（docstring 里提到它是说理，不算读表）
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}
    assert "ROLE_CLEARANCE" not in names | imported, "出口直接读了档位表：那是绕过 clearance_for 的第二种口径"


def test_the_role_is_read_from_the_authoritative_row_not_the_merged_profile():
    """档位问的是 ``users`` 那一行（``base``），不是合并后的画像字典：别让「谁说了算」变两本账。"""
    route = _function(_route_tree(), "get_my_profile")
    assert route is not None
    role_read = [
        ast.unparse(node.value)
        for node in ast.walk(route)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "role" for t in node.targets)
    ]
    assert len(role_read) == 1, role_read
    assert "base.get" in role_read[0], role_read[0]
    assert "profile" not in role_read[0], f"档位改问画像字典了：{role_read[0]}"


def test_no_api_route_invents_a_role_to_level_map():
    """常驻闸：``app/api/v1/`` 里任何一枚出口都不许多长一份「角色→档位」表。

    本单只在 GET /profile 加一枚读数；这一枚钉让下一班想「顺手在这里再算一次档位」时当场红。
    """
    offenders = []
    for path in sorted((ROOT / "app" / "api" / "v1").glob("*.py")):
        for lineno, keys in _role_to_int_dicts(ast.parse(path.read_text(encoding="utf-8"))):
            offenders.append(f"{path.name}:{lineno}:{keys}")
    assert offenders == [], f"出现了第二份档位表：{offenders}"


# ==================== 判据③⑤：除这一格外一字未改，写腿照旧 ====================


def test_the_rest_of_the_answer_is_unchanged(client, headers, memory_store):
    """加这一格的代价只能是这一格：``users`` 那三列 + 画像那三列，一枚不多一枚不少。"""
    username = ROLE_ROWS["staff"]
    body = _profile_of(client, headers, username)

    assert body["username"] == username, body
    assert body["role"] == "staff", body
    assert body["department"] == RESEARCH, body
    # 画像存储这轮什么都没写，所以那三列不该凭空出现（R383 的「部分但诚实」那张脸没被折坏）
    for column in ("position", "preferences", "updated_at"):
        assert column not in body, f"画像没写过 {column}，回执却凭空有了它：{body}"
    assert set(body) == {"username", "role", "department", "clearance"}, body


def test_a_self_reported_department_is_still_refused_whole(client, headers, memory_store):
    """R296 判据②那支闸没被本单挪动：出现 ``department`` 就整发拒，码还是那枚在册码。"""
    from app.common.authorization import DEPARTMENT_SELF_REPORT_DENIED

    response = client.put(
        PROFILE_PATH,
        json={"department": "自报的任意部门", "position": POSITION},
        headers=headers(ROLE_ROWS["staff"]),
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == DEPARTMENT_SELF_REPORT_DENIED, response.json()
    assert memory_store._MEM_PROFILES == {}, memory_store._MEM_PROFILES


def test_the_write_leg_still_round_trips_position_and_preferences(client, headers, memory_store):
    """判据④的后端那一腿：请求体里没有 ``department`` 这枚键，职位与偏好就真写得回、读得到。"""
    username = ROLE_ROWS["staff"]
    body = {"position": POSITION, "preferences": PREFERENCES}

    response = client.put(PROFILE_PATH, json=body, headers=headers(username))

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}, response.json()
    written = memory_store._MEM_PROFILES[username]
    assert "department" not in written, written

    listed = _profile_of(client, headers, username)

    assert listed["position"] == POSITION, listed
    assert listed["preferences"] == PREFERENCES, listed
    assert listed["department"] == RESEARCH, listed
    assert listed["clearance"] == clearance_for("staff"), listed


def test_the_docstring_says_why_the_cell_can_be_absent():
    """docstring 里那句「整格不出现」是本单的判据而不是注释装饰：摘掉说理就红。"""
    route = _function(_route_tree(), "get_my_profile")
    assert route is not None
    doc = ast.get_docstring(route) or ""
    assert "clearance_for" in doc, "档位真源的调用点没在 docstring 里指出来：判据①要求点名"
    assert "整格不出现" in doc, doc
    assert "filters.py" in doc, "判据①要求 docstring 指到调用点（检索闸门那一处 classification_levels）"
