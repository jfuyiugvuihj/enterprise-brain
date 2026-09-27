"""R357 · 角色名单四本手抄账收成一枚真源；`auditor` 的缺席必须问得出原因。

病（四本账，行号为修前一手现场）：

| 位置 | 装的是什么 | 枚数 |
|---|---|---|
| `app/common/permissions.py:12-17` `ROLE_PERMISSIONS` | 角色 → 权限面 | **4**：staff / manager / admin / auditor |
| `app/common/auth.py:552`（建号）与 `:599`（SSO 改派） | 手抄 `("staff", "manager", "admin")` | **3** |
| `app/common/sso.py:4` `ALLOWED_ROLES` | 手抄 `{"staff", "manager", "admin"}` | **3** |
| `app/common/rbac.py:31` `ROLE_CLEARANCE` | 角色 → 密级档位 | **3** |

`clearance_for()` 用 `.get(role or "staff", 1)`，所以一枚 `auditor` 落到那里**静默拿到 staff
那一档**，日志里什么都没有。本仓这一族病今天已经收了四回（`test_r238` 行号账、R349 迁移尾号账、
`test_r304` sha 账、R345/R337/R355 告警巡检扩展名账），本单是第五回。

🔴 正解不是「把四处都改成 4」：那只是把四枚雷重新埋一遍，还顺手放宽了谁能被建号。本单做的是
**一处真源 + 三处 import**（判据⑦），可创建集合今天仍是 `staff / manager / admin` 三枚
（判据⑧：多一枚少一枚都红），而 `auditor` 不在里面的**唯一合法理由**写成一条显式断言加一句
人话：它还没有密级档位（`rbac.py:31`），密级口径 = **H13，业主未定**。两枚差集钉
（`ROLE_PERMISSIONS - CREATABLE_ROLES` 与 `ROLE_PERMISSIONS - ROLE_CLEARANCE`，都必须**恰好**
`{"auditor"}`）盯着的就是这件事：谁给 auditor 补了档位，这两枚钉会同时要求他回答「要不要让它
可创建」，而不是让名单悄悄漂移。

本文件刻意不做的事（判据⑨，H13 未决期间一格都不许动）：不给 `clearance_for()` 加 `raise`、
不给 `auditor` 编档位、不加日志、不改可观察行为。它只**记事实**：今天 auditor 走的确实是
`.get` 兜底拿到 1 档，这一格是取证，不是裁定。

判据⑪那把「全仓不许长出第二份名单」的尺子，口径与盲区都写在这里（明写，不装没有）：

* **范围 = `app/**` 的生产代码**（外加 `scripts/`、`deploy/`，今天零命中）。`tests/**` 不在
  范围内：那里的角色名是**用例矩阵**不是账本——`tests/test_r179_chat_denials.py:476` 是一枚
  参数化列表，`tests/test_r251_alert_disposal.py:103` 是一枚逐角色循环，
  `tests/_r250_route_client.py:14` 是测试桩的用户表形状。把它们收进 import 等于摘掉「这个用例
  逐枚点名叫过谁」，而判据⑧要的正是不点名不许过。
* **只认「一整枚常量容器恰好就是那几枚角色名」**：`set` / `list` / `tuple` 字面量，以及
  `set(...)` / `frozenset(...)` 包住的那一枚。判据用的两枚形状由真源现推（`ROLE_PERMISSIONS`
  的键集、`CREATABLE_ROLES` 自己），本文件不另抄一份名单当尺子。
* **dict 不算名单**：`ROLE_PERMISSIONS`（角色→权限）与 `ROLE_CLEARANCE`（角色→档位）是两本
  各自独立的账，判据⑧要判的恰是它们的**差集**；把它们收成一枚就是替 H13 做决定。这是盲区，
  明写在这里。
"""

import ast
from pathlib import Path

import pytest

from app.common import auth, rbac, sso
from app.common.permissions import CREATABLE_ROLES, ROLE_PERMISSIONS
from app.common.rbac import ROLE_CLEARANCE, allowed_levels, clearance_for

REPO = Path(__file__).resolve().parents[1]
PERMISSIONS_REL = "app/common/permissions.py"
AUTH_REL = "app/common/auth.py"
SSO_REL = "app/common/sso.py"
RBAC_REL = "app/common/rbac.py"
SCAN_ROOTS = ("app", "scripts", "deploy")

#: 判据⑧的边界账：这一枚三元组**不是第四份名单**，它唯一的作用是「多一枚少一枚都算越界」。
#: 所以它必须写死；真源若漂了，本文件必须连这句理由一起改口，不许悄悄对齐成真源的新值。
TODAYS_ADMISSION = frozenset({"staff", "manager", "admin"})


# ------------------------------------------------------------------ 判据⑪：尺子本体


def _roster_shapes() -> tuple[frozenset, frozenset]:
    """"一整枚名单"的两种形状：权限面的键集与可创建集合，全部由真源现推。"""
    return frozenset(ROLE_PERMISSIONS), CREATABLE_ROLES


def _container_elements(node):
    """这枚节点装的是不是一串纯字符串元素？是就把元素交出来。"""
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return node.elts
    if (
        isinstance(node, ast.Call)
        and getattr(node.func, "id", "") in {"set", "frozenset"}
        and len(node.args) == 1
        and isinstance(node.args[0], (ast.Set, ast.List, ast.Tuple))
    ):
        return node.args[0].elts
    return None


def _roster_literals(source: str, rel: str) -> list[dict]:
    """扫一份源码里「一整枚常量就是角色名单」的容器，唯一真源那一处除外。"""
    tree = ast.parse(source)
    sanctioned: set[int] = set()
    for stmt in tree.body:
        if rel != PERMISSIONS_REL:
            continue
        if isinstance(stmt, ast.AnnAssign):
            target, value = stmt.target, stmt.value
        elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            target, value = stmt.targets[0], stmt.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id == "CREATABLE_ROLES" and value is not None:
            sanctioned.update(id(sub) for sub in ast.walk(value))

    shapes = _roster_shapes()
    found = []
    for node in ast.walk(tree):
        elts = _container_elements(node)
        if elts is None or id(node) in sanctioned:
            continue
        names = [e.value for e in elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if not names or len(names) != len(elts):
            continue
        if frozenset(names) in shapes:
            found.append({"file": rel, "line": node.lineno, "names": sorted(names)})
    return found


def _app_roster_copies() -> list[dict]:
    found = []
    for name in SCAN_ROOTS:
        root = REPO / name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            found.extend(_roster_literals(path.read_text(encoding="utf-8"), rel))
    return found


def test_no_module_in_production_code_carries_a_second_role_roster():
    """判据⑪：生产代码里「一整枚就是那几枚角色名」的容器，只许是真源那一处。"""
    copies = _app_roster_copies()

    assert copies == [], f"长出了第二份手抄名单，每一枚都得收进 permissions::CREATABLE_ROLES 的 import：{copies}"


def test_the_scanner_is_not_blind_and_the_true_source_still_counts_as_one():
    """反空转（同 `test_r142` 的对照组纪律）：解析不到不许降级成恒真。

    ① 合成源码里塞一份手抄三元组 ⇒ 尺子必须报；② 真源自己那一枚必须**不**报，否则「零命中」
    永远读不出来。全程只在内存里解析，不落任何文件（R253 那条「测试不许写被跟踪文件」）。
    """
    planted = "GUESSED = ('staff', 'manager', 'admin')\n"
    hits = _roster_literals(planted, "app/common/synthetic_r357.py")
    assert [hit["names"] for hit in hits] == [sorted(TODAYS_ADMISSION)], hits

    true_source = (REPO / PERMISSIONS_REL).read_text(encoding="utf-8")
    assert _roster_literals(true_source, PERMISSIONS_REL) == [], "真源把自己判红了"


def _definition_of(source: str, name: str):
    """模块级那一枚 `NAME = ...` / `NAME: T = ...` 的赋值节点。"""
    hits = []
    for stmt in ast.parse(source).body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == name:
            hits.append(stmt)
        elif isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in stmt.targets):
            hits.append(stmt)
    return hits


def test_the_true_source_is_a_literal_not_a_derivation_or_an_env_read():
    """真源必须是写得出来的字面量（口径同 R349「不许 `MIGRATIONS[-1]` 派生式」）。

    派生式会让准入跟着现实漂，「谁能被建号」这句主张从此问不出来；从环境读更是判据⑫明令
    禁止的那种「把决定藏进环境变量」。
    """
    source = (REPO / PERMISSIONS_REL).read_text(encoding="utf-8")
    definitions = _definition_of(source, "CREATABLE_ROLES")
    assert len(definitions) == 1, definitions
    value = definitions[0].value
    assert isinstance(value, ast.Call) and getattr(value.func, "id", "") == "frozenset", ast.dump(value)
    inner = value.args[0]
    assert isinstance(inner, ast.Set), ast.dump(inner)
    assert all(isinstance(elt, ast.Constant) and isinstance(elt.value, str) for elt in inner.elts)
    assert "getenv" not in source, "可创建集合不许从环境读"


def test_the_creatable_roster_is_defined_exactly_once_across_production_code():
    """判据⑦的计数尺子：`CREATABLE_ROLES` 的定义在全仓**恰一枚**，且就在权限面那一枚文件里。"""
    definitions = []
    for name in SCAN_ROOTS:
        root = REPO / name
        for path in sorted(root.rglob("*.py")) if root.is_dir() else []:
            rel = path.relative_to(REPO).as_posix()
            for stmt in _definition_of(path.read_text(encoding="utf-8"), "CREATABLE_ROLES"):
                definitions.append((rel, stmt.lineno))
    assert len(definitions) == 1, f"真源定义应当恰一枚，实测 {definitions}"
    assert [rel for rel, _ in definitions] == [PERMISSIONS_REL], definitions


# ------------------------------------------------------------------ 判据⑦：三处 import 真在用它


def _not_in_targets(source: str) -> list[str]:
    """源码里 `... not in <X>` 的右端名字。"""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.NotIn) for op in node.ops):
            right = node.comparators[0]
            if isinstance(right, ast.Name):
                found.append(right.id)
    return found


def test_auth_asks_the_true_source_twice_and_keeps_no_copied_tuple():
    """建号与 SSO 改派两格都必须判 `CREATABLE_ROLES`；手抄三元组一枚都不许剩。"""
    source = (REPO / AUTH_REL).read_text(encoding="utf-8")
    checks = _not_in_targets(source)

    assert checks.count("CREATABLE_ROLES") == 2, checks
    imported = [
        alias.name
        for node in ast.parse(source).body
        if isinstance(node, ast.ImportFrom) and node.module == "app.common.permissions"
        for alias in node.names
    ]
    assert imported == ["CREATABLE_ROLES"], imported


def test_sso_reexports_the_true_source_instead_of_keeping_a_second_ledger():
    """`sso.ALLOWED_ROLES is CREATABLE_ROLES`——判 `is` 不判 `==`。

    再抄一份集合照样 `==`，却从此不再同源，而那正是本单要根治的病。名字留着只为不断既有读者
    （`normalize_role` 与这枚模块的对外形状），它持有的就是真源那一个对象。
    """
    assert sso.ALLOWED_ROLES is CREATABLE_ROLES
    assert auth.CREATABLE_ROLES is CREATABLE_ROLES
    assert _roster_literals((REPO / SSO_REL).read_text(encoding="utf-8"), SSO_REL) == []


# ------------------------------------------------------------------ 判据⑧：差集恰好 auditor 一枚


def test_the_permission_ledger_is_exactly_one_role_wider_than_the_admission_ledger():
    """差集钉 1：恰好一枚，多一枚少一枚都红（`>=` 是钝刀，见反证刀 4）。"""
    wider = set(ROLE_PERMISSIONS) - set(CREATABLE_ROLES)

    assert wider == {"auditor"}, f"权限面比准入宽出的不是恰好 auditor 一枚：{sorted(wider)}"


def test_the_permission_ledger_is_exactly_one_role_wider_than_the_clearance_ledger():
    """差集钉 2：与密级面比也是恰好一枚。两枚钉同时红 = 「补了档位就得回答准入问题」。"""
    wider = set(ROLE_PERMISSIONS) - set(ROLE_CLEARANCE)

    assert wider == {"auditor"}, f"权限面比密级面宽出的不是恰好 auditor 一枚：{sorted(wider)}"


def test_admission_is_unchanged_still_exactly_the_three_accounts_today():
    """判据⑧「本单不放宽准入」：可创建集合与开工那天逐字相同，多一枚少一枚都算越界。"""
    assert CREATABLE_ROLES == TODAYS_ADMISSION, sorted(CREATABLE_ROLES)


def test_the_gap_has_one_reason_and_it_is_the_missing_clearance_tier():
    """把那句人话写成断言：auditor 不在准入集合里，是因为它没有密级档位，不是因为谁偏好。

    `CREATABLE_ROLES == frozenset(ROLE_CLEARANCE)` 说的是「有档位才可创建」这条同一性：它一红
    就说明有人补了档位却没在这里回答准入问题，或者反过来放了个没档位的角色进来。
    """
    assert CREATABLE_ROLES == frozenset(ROLE_CLEARANCE), (sorted(CREATABLE_ROLES), sorted(ROLE_CLEARANCE))
    assert "auditor" not in ROLE_CLEARANCE


def test_the_true_source_states_its_reason_in_human_language():
    """理由必须写在读得到真源的那一格里，而不是只活在本文件或工单里。"""
    text = (REPO / PERMISSIONS_REL).read_text(encoding="utf-8")

    assert "H13" in text, "没写清这是 H13 未决期的边界"
    assert "密级档位" in text, "没写出 auditor 缺席的那句人话理由"
    assert "ROLE_CLEARANCE" in text, "理由没指回密级面那一枚账本"


def test_no_new_switch_was_buried_in_the_environment():
    """判据⑫：不许长出 `ALLOW_AUDITOR_ROLES` 这类开关——那是把决定藏进环境变量。"""
    read = []
    for rel in (PERMISSIONS_REL, AUTH_REL, SSO_REL):
        for node in ast.walk(ast.parse((REPO / rel).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "getenv" and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    read.append(first.value)
    buried = [name for name in read if "ROLE" in name.upper() or "AUDITOR" in name.upper()]
    assert buried == [], f"角色准入被塞进环境变量了：{buried}（全量读数 {sorted(set(read))}）"


# ------------------------------------------------------------------ 判据⑧/⑨：准入行为与事实记录


def test_an_auditor_still_cannot_be_created_and_the_message_is_unchanged():
    """行为面零放宽：`非法角色: auditor` 这句原文与拒答本身都不许漂。"""
    refused = auth.create_user("r357-ghost", "pass1234", role="auditor")

    assert refused == (False, "非法角色: auditor"), refused


@pytest.mark.parametrize("role", sorted(CREATABLE_ROLES))
def test_the_three_admissible_roles_are_still_the_only_ones_that_pass_validation(role, monkeypatch):
    """逐枚点名：三枚准入角色仍然建得出来（开发态 + 受控内存表，不碰库、不碰模型）。"""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(auth, "_MEM_USERS", {})
    monkeypatch.setattr(auth, "_using_memory_store", lambda: True)

    ok, message = auth.create_user("r357-ok", "pass1234", role=role)

    assert ok is True, message
    assert auth.get_user("r357-ok")["role"] == role


def test_sso_cannot_assign_a_role_without_a_tier_either():
    """`X-SSO-Role: auditor` 今天被降成 staff——既有行为，本单一字未动，钉住它没漂。"""
    assert sso.normalize_role("auditor") == "staff"
    identity = sso.extract_sso_identity({"X-SSO-User": "r357-sso", "X-SSO-Role": "auditor"})

    assert identity["role"] == "staff", identity


def test_an_auditor_still_lands_on_the_staff_tier_by_the_silent_fallback():
    """判据⑨的取证钉：今天 auditor 走的确实是 `.get` 兜底拿到 1 档。

    🔴 这一格**记录事实，不做裁定**：密级口径属 H13，业主未定，本单不许替它编档位、不许改成
    raise、不许加日志（下一条把「没加」也钉住）。等谁真的给 auditor 定了档位，这一枚会当场红
    ——那时该讨论的是 H13，不是一个可以顺手带过的默认值。
    """
    assert ROLE_CLEARANCE.get("auditor") is None
    assert clearance_for("auditor") == 1
    assert allowed_levels("auditor") == [1]


def test_clearance_for_still_swallows_quietly_and_that_is_pinned_as_unchanged():
    """形状钉：`clearance_for` 今天没有 raise、没有日志、只有一枚 `.get(..., 1)` 兜底。

    本单判的是「零可观察改动」，所以连函数体形状一起钉：将来无论谁要动它（H13 落定也好、补
    审计日志也好），都必须连同这一格一起改口，不许在别人单里悄悄发生。
    """
    function = next(
        node
        for node in ast.parse((REPO / RBAC_REL).read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef) and node.name == "clearance_for"
    )

    assert not [node for node in ast.walk(function) if isinstance(node, ast.Raise)], "本单不许给兜底加 raise"
    assert not [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in {"info", "warning", "error", "debug"}
    ], "本单不许顺手加日志改变可观察行为"
    returns = [node for node in function.body if isinstance(node, ast.Return)]
    assert len(returns) == 1, returns
    call = returns[0].value
    assert isinstance(call, ast.Call) and getattr(call.func, "attr", "") == "get", ast.dump(call)
    assert rbac.clearance_for.__code__.co_filename.endswith("rbac.py")
