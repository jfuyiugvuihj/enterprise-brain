"""R357 · 角色名单四本手抄账收成一枚真源；`auditor` 的缺席必须问得出原因（R413 已回答，见下）。

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
**一处真源 + 三处 import**（判据⑦）。判据⑧那一格由 R413 改口：H13 已于 2026-09-28 结案＝甲
（未标注密级按 1 级入库，写进契约），同批裁定 `auditor` 的密级档位 = 3、与 `admin` 同档，可创建
集合因此从三枚涨到四枚 —— auditor 不再是「有权限集、没档位」的那一枚。两枚差集钉跟着从**恰好
`{"auditor"}`** 换成**恰好空集**：R357 那天它们盯着「补了档位就得回答准入问题」，今天这个问题已
经回答，于是同一枚钉改盯「三本账不许再漂」，多一枚少一枚照样红。🔴 强度不许降：把 `== set()`
松成 `<= {"auditor"}` 那种收法照样能把漂移洗白 —— 钝刀的两个方向当场都不红（R413 交回账里的
K5 反证读数）。判据⑨那四条（不给 `clearance_for()` 加 `raise`、不加日志、不改可观察行为）
一个字没废：R413 只往 `ROLE_CLEARANCE` 加了一格，`.get(role or "staff", 1)` 那枚兜底原样在位，
继续替没在册的角色说话 —— 只是 auditor 从此不再需要它替自己说话，这一格从「取证」变成「裁定落地」。

判据⑪那把「全仓不许长出第二份名单」的尺子，口径与盲区都写在这里（明写，不装没有）：

* **范围 = `app/**` 的生产代码**（外加 `scripts/`、`deploy/`，今天零命中）。`tests/**` 不在
  范围内：那里的角色名是**用例矩阵**不是账本——`tests/test_r179_chat_denials.py:476` 是一枚
  参数化列表，`tests/test_r251_alert_disposal.py:103` 是一枚逐角色循环，
  `tests/_r250_route_client.py:14` 是测试桩的用户表形状。把它们收进 import 等于摘掉「这个用例
  逐枚点名叫过谁」，而判据⑧要的正是不点名不许过。
* **只认「一整枚常量容器恰好就是那几枚角色名」**：`set` / `list` / `tuple` 字面量，以及
  `set(...)` / `frozenset(...)` 包住的那一枚。形状由真源现推（`ROLE_PERMISSIONS` 的键集、
  `CREATABLE_ROLES` 自己），再加一枚 **R413 之前的旧准入形状**：真源涨到四枚以后，手抄的三元组
  就不在任何一本账的形状里了，那把尺会当场变钝（R413 实测把这条红交回过总控）—— 所以旧形状必须
  继续算违规：抄回来的不是「另一本名单」，是一句今天已经是假话的名单。
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

#: 判据⑧的两枚边界账：它们**不是第四份、第五份名单**，唯一的作用是「多一枚少一枚都算越界」。
#: 所以必须写死；真源再漂，本文件必须连这句理由一起改口，不许悄悄对齐成真源的新值。
#: `ADMISSION_AT_R357` 还兼着尺子的一枚形状（见 `_roster_shapes`）：把旧三元组抄回生产代码要红。
ADMISSION_AT_R357 = frozenset({"staff", "manager", "admin"})
#: R413 落地那天（H13 结案＝甲、auditor 认 3 档）的准入形状，判据⑧的越界账改到这一枚。
ADMISSION_AFTER_R413 = frozenset({"staff", "manager", "admin", "auditor"})


# ------------------------------------------------------------------ 判据⑪：尺子本体


def _roster_shapes() -> tuple[frozenset, ...]:
    """「一整枚名单」的形状账：权限面键集与可创建集合（两枚由真源现推），加 R413 前的旧准入形状。

    第三枚不是第四本名单，是尺子：真源涨到四枚以后，只靠前两枚就咬不到手抄回来的三元组了。
    """
    return frozenset(ROLE_PERMISSIONS), CREATABLE_ROLES, ADMISSION_AT_R357


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
    seen = set()
    for node in ast.walk(tree):
        elts = _container_elements(node)
        if elts is None or id(node) in sanctioned:
            continue
        names = [e.value for e in elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if not names or len(names) != len(elts):
            continue
        if frozenset(names) in shapes:
            # frozenset({...}) 这种写法会被 ast.walk 走两遍（Call 与它包着的 Set）：同一行同一
            # 形状只记一枚，「手抄了一份」读起来才是一枚命中；去重不摘任何违规，只去重复计数。
            key = (node.lineno, frozenset(names))
            if key in seen:
                continue
            seen.add(key)
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

    三格缺一不可：① 手抄的**三元组**（R413 之前的旧准入形状）必须报 —— 真源涨到四枚以后这一格
    差点变成假绿，是 R413 交回来的红；② 手抄的**四元组**（今天的形状）必须报；③ 真源自己那一枚
    必须**不**报，否则「零命中」永远读不出来。全程只在内存里解析，不落任何文件（R253）。
    """
    narrow = _roster_literals("GUESSED = ('staff', 'manager', 'admin')\n", "app/common/synthetic_r357.py")
    assert [hit["names"] for hit in narrow] == [sorted(ADMISSION_AT_R357)], narrow

    wide = _roster_literals(
        "GUESSED = frozenset({'auditor', 'manager', 'staff', 'admin'})\n", "app/common/synthetic_r413.py"
    )
    assert [hit["names"] for hit in wide] == [sorted(ADMISSION_AFTER_R413)], wide

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


# ------------------------------------ 判据⑧（R413 改口）：三本账同集，差集恰好空集


def test_the_admission_ledger_is_the_same_set_as_the_permission_ledger():
    """差集钉 1（R413 改口）：从「恰好 auditor 一枚」换成「恰好空集」，双向都判，多一枚少一枚都红。

    🔴 不许松成 `gap <= {"auditor"}`：那种形状下「准入面把 auditor 漏掉」当场不红，正是 R357
    当年判过的钝刀（>= 那一族），今天照旧算洗白。
    """
    wider = set(ROLE_PERMISSIONS) - set(CREATABLE_ROLES)
    narrower = set(CREATABLE_ROLES) - set(ROLE_PERMISSIONS)

    assert wider == set(), f"三本账今天必须同集，权限面比准入宽出的不是空集：{sorted(wider)}"
    assert narrower == set(), f"准入面反过来比权限面宽出 {sorted(narrower)}：权限面没登记的角色建不出才是对的"


def test_the_clearance_ledger_is_the_same_set_as_the_permission_ledger():
    """差集钉 2（R413 改口）：与密级面比也是恰好空集，双向都判。

    R357 那天这枚钉与上一枚同时红就是「有人补了档位却没回答准入」；今天两枚一起改成同集账，
    谁让「有档位」与「可创建」再分家（漏一枚或多一枚，任一向），两枚钉里至少一枚当场红。
    """
    wider = set(ROLE_PERMISSIONS) - set(ROLE_CLEARANCE)
    narrower = set(ROLE_CLEARANCE) - set(ROLE_PERMISSIONS)

    assert wider == set(), f"三本账今天必须同集，权限面比密级面宽出的不是空集：{sorted(wider)}"
    assert narrower == set(), f"密级面反过来比权限面宽出 {sorted(narrower)}：给没在册的角色配档位是假档位"


def test_admission_is_exactly_the_four_roles_r413_admitted():
    """判据⑧的越界账改到 R413 那天：与落地那天逐字相同，多一枚少一枚都算越界。

    第二行钉的是方向：R413 是**加一枚**，不是换一枚也不是缩回去 —— 旧三元组必须是今天的真子集。
    """
    assert CREATABLE_ROLES == ADMISSION_AFTER_R413, sorted(CREATABLE_ROLES)
    assert ADMISSION_AT_R357 < CREATABLE_ROLES, "准入面不许缩回 R413 之前的三枚形状"


def test_the_same_identity_now_holds_because_h13_answered_it():
    """那句人话的对面：auditor 既在准入集合里，也在密级面里，档位是裁的 3，不是随手一档。

    `CREATABLE_ROLES == frozenset(ROLE_CLEARANCE)` 说的还是「有档位才可创建」这条同一性 —— 今天
    它由两枚账同时满足；谁补了档位不回答准入、或放了枚没档位的进来，这一枚当场红。
    """
    assert CREATABLE_ROLES == frozenset(ROLE_CLEARANCE), (sorted(CREATABLE_ROLES), sorted(ROLE_CLEARANCE))
    assert ROLE_CLEARANCE["auditor"] == ROLE_CLEARANCE["admin"] == 3, "H13 裁的是 3 档，与 admin 同档"


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


# -------------------------------------------- 判据⑧/⑨（R413 改口）：准入行为与兜底形状


def test_an_auditor_is_created_and_an_unknown_role_keeps_the_unchanged_refusal(monkeypatch):
    """改口的行为面：auditor 建得出来；`非法角色: <role>` 那句原文与拒答本身一个字没漂。

    开发态 + 受控内存表（口径同下一条），不碰库、不碰模型、不发 HTTP。
    """
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(auth, "_MEM_USERS", {})
    monkeypatch.setattr(auth, "_using_memory_store", lambda: True)

    admitted = auth.create_user("r357-auditor", "pass1234", role="auditor")

    assert admitted == (True, "创建成功"), admitted
    assert auth.get_user("r357-auditor")["role"] == "auditor"

    refused = auth.create_user("r357-ghost", "pass1234", role="developer")

    assert refused == (False, "非法角色: developer"), refused


@pytest.mark.parametrize("role", sorted(CREATABLE_ROLES))
def test_the_admissible_roles_are_still_the_only_ones_that_pass_validation(role, monkeypatch):
    """逐枚点名：真源里的每一枚准入角色都建得出来（开发态 + 受控内存表，不碰库、不碰模型）。

    参数吃真源，所以 R413 加第四枚时这里自动多一格；少一格就是准入面与权限面重新分家。
    """
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(auth, "_MEM_USERS", {})
    monkeypatch.setattr(auth, "_using_memory_store", lambda: True)

    ok, message = auth.create_user("r357-ok", "pass1234", role=role)

    assert ok is True, message
    assert auth.get_user("r357-ok")["role"] == role


def test_sso_assigns_an_auditor_and_still_downgrades_a_role_the_roster_does_not_know():
    """`X-SSO-Role: auditor` 不再被降成 staff；降级那一支仍在位，只是不再替 auditor 说话。"""
    assert sso.normalize_role("auditor") == "auditor"
    identity = sso.extract_sso_identity({"X-SSO-User": "r357-sso", "X-SSO-Role": "auditor"})

    assert identity["role"] == "auditor", identity
    assert sso.normalize_role("developer") == "staff", "词表外仍须降级：这条不许跟着改口一起松掉"


def test_the_auditor_tier_is_the_ruling_now_and_the_fallback_still_catches_the_rest():
    """R357 那格取证钉的对面：auditor 今天在册拿 3 档，`.get` 兜底只替没在册的角色说话。

    🔴 这一格从「记录事实」变成「裁定落地」（H13 已于 2026-09-28 结案＝甲，auditor = 3 与 admin
    同档）。兜底本身照旧不许改成 raise、不许加日志 —— 下一条把「形状没动」钉住；没在册的角色
    今天仍然静默拿 1 档，那一格 R413 没替谁决定。
    """
    assert ROLE_CLEARANCE["auditor"] == 3
    assert clearance_for("auditor") == 3
    assert allowed_levels("auditor") == [1, 2, 3]
    assert clearance_for("developer") == 1, "兜底那一支不许顺手改成 raise"


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
