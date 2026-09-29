# -*- coding: utf-8 -*-
"""R413 · auditor 的密级档位与准入同批落地：四档「权限统一」今天才真能用。

病（09-27 复评现取，本单一手复验）：``app/common/permissions.py`` 的角色权限面早就四枚齐了，
可 ``app/common/rbac.py:31`` 的 ``ROLE_CLEARANCE`` 只给 staff / manager / admin 三枚档位 ⇒
``permissions.py:41`` 的 ``CREATABLE_ROLES`` 不收 auditor ⇒ ``app/common/auth.py:606``（建号）与
``:653``（SSO 改派）拒它 ⇒ ``app/common/sso.py:9`` 的 ``ALLOWED_ROLES`` 连 SSO 头里递进来的
auditor 身份也一起降成 staff。四档统一今天只有三档落得了地：审计员那一行写着 view / download /
audit，账号却开不出来。

挡住它的不是代码而是 H13（密级口径未裁）。H13 已于 2026-09-28 结案＝甲（未标注密级按 1 级入库写进
契约），同批裁定 **auditor 的密级档位 = 3，与 admin 同档**：审计员读不到机密件就是假审计，而「读到
但改不动」靠的是权限集，不是密级档。所以本单只动两枚真源（补一格档位、把 auditor 放进可创建集合），
下游一个字没改：``auth.py`` 与 ``sso.py`` 都是从真源派生的，本来就该跟着放行。

🔴 本文件同时是 R357 那两枚差集钉的**改口落点**（R413 的写域不含
``tests/test_r357_single_role_roster.py``，那枚文件归总控改口）：强断言先在这里立住，免得改口途中
钝化成「auditor 允许出现」这类洗白。新现实是**三本账同集**——``CREATABLE_ROLES``、``ROLE_CLEARANCE``、
``ROLE_PERMISSIONS`` 两两差集必须**恰好**是空集，多一枚少一枚都红。

零副作用：不打容器、不连库、不发真 HTTP。建号走 ``app/common/auth.py`` 自带的受控内存表（
``APP_ENV=development`` + ``_using_memory_store`` 替身）；检索口径只判 ``DocumentRetrievalScope`` 本体。
"""
from pathlib import Path

import pytest

from app.agents.contracts import Principal
from app.common import auth, sso
from app.common.permissions import (
    ACTION_ANALYZE,
    ACTION_AUDIT,
    ACTION_DELETE,
    ACTION_DOWNLOAD,
    ACTION_EXPORT,
    ACTION_MANAGE_ALERTS,
    ACTION_MANAGE_USERS,
    ACTION_UPLOAD,
    ACTION_VIEW,
    CREATABLE_ROLES,
    ROLE_PERMISSIONS,
    permissions_for_role,
)
from app.common.policy import authorization_decision
from app.common.rbac import ROLE_CLEARANCE, allowed_levels, clearance_for

REPO = Path(__file__).resolve().parents[1]
PERMISSIONS_REL = "app/common/permissions.py"
RBAC_REL = "app/common/rbac.py"

#: 裁定原文那一格（H13 结案，09-28 第二十三格·总控线）：判据要的是这件事问得出来，不是一个数飘着。
AUDITOR_TIER = 3
ALL_ROLES = {"staff", "manager", "admin", "auditor"}


def _principal(role: str, department: str = "finance") -> Principal:
    return Principal.from_user({"id": "u-" + role, "username": "r413-" + role, "role": role, "department": department})


# ---------------------------------------------------------------- 裁定面：档位


def test_auditor_now_has_a_clearance_tier_and_it_is_the_admin_tier():
    """H13 连带裁定的正面钉：auditor = 3 档，与 admin 同档。摘掉 ``rbac.py:31`` 那一格，本条先红。"""
    assert ROLE_CLEARANCE["auditor"] == AUDITOR_TIER
    assert clearance_for("auditor") == AUDITOR_TIER
    assert ROLE_CLEARANCE["auditor"] == ROLE_CLEARANCE["admin"]


def test_allowed_levels_for_auditor_reach_the_top_of_the_model():
    """3 档就是 1/2/3 三档全开：机密件（3 级）在密级维度上必须读得到，否则就是假审计。"""
    assert allowed_levels("auditor") == [1, 2, 3]
    assert max(allowed_levels("auditor")) == max(ROLE_CLEARANCE.values())


def test_the_new_tier_was_added_without_repricing_the_three_roles_that_had_one():
    """只补一枚，不许顺手抬别人：staff / manager / admin 三档逐枚点名等于开工那天的读数。"""
    assert ROLE_CLEARANCE["staff"] == 1
    assert ROLE_CLEARANCE["manager"] == 2
    assert ROLE_CLEARANCE["admin"] == 3
    assert {ROLE_CLEARANCE[role] for role in ("staff", "manager", "admin")} == {1, 2, 3}


def test_auditor_no_longer_lands_on_the_silent_staff_fallback():
    """R357 那枚取证钉的对面：今天 auditor 走的不再是的的确的 ``.get`` 兜底。

    ``clearance_for`` 的实现形状一个字没动（仍是 ``ROLE_CLEARANCE.get(role or "staff", 1)``）：
    兜底还在，只是 auditor 已经有名在册，不再需要它替自己说话。
    """
    assert "auditor" in ROLE_CLEARANCE
    assert clearance_for("auditor") != clearance_for("staff")
    assert clearance_for("ghost-role") == 1, "没在册的角色仍走兜底——本单没把它改成 raise，也没加日志"


# ---------------------------------------------------------------- 准入面：三本账同集


def test_auditor_is_creatable_and_assignable():
    assert "auditor" in CREATABLE_ROLES
    assert "auditor" in sso.ALLOWED_ROLES
    assert sso.ALLOWED_ROLES is CREATABLE_ROLES, "R357 的同源钉：再抄一份名单就算相等也不许"


def test_the_three_role_ledgers_hold_the_same_key_set():
    """判据⑧的同一性今天更强：权限面 = 密级面 = 准入面，四枚逐枚点名。"""
    assert CREATABLE_ROLES == frozenset(ROLE_CLEARANCE) == frozenset(ROLE_PERMISSIONS)
    assert set(CREATABLE_ROLES) == ALL_ROLES


@pytest.mark.parametrize(
    "wider,narrower,wider_name,narrower_name",
    [
        (ROLE_PERMISSIONS, CREATABLE_ROLES, "ROLE_PERMISSIONS", "CREATABLE_ROLES"),
        (ROLE_PERMISSIONS, ROLE_CLEARANCE, "ROLE_PERMISSIONS", "ROLE_CLEARANCE"),
        (CREATABLE_ROLES, ROLE_PERMISSIONS, "CREATABLE_ROLES", "ROLE_PERMISSIONS"),
        (CREATABLE_ROLES, ROLE_CLEARANCE, "CREATABLE_ROLES", "ROLE_CLEARANCE"),
        (ROLE_CLEARANCE, ROLE_PERMISSIONS, "ROLE_CLEARANCE", "ROLE_PERMISSIONS"),
        (ROLE_CLEARANCE, CREATABLE_ROLES, "ROLE_CLEARANCE", "CREATABLE_ROLES"),
    ],
)
def test_every_pairwise_difference_is_exactly_empty(wider, narrower, wider_name, narrower_name):
    """R357 两枚差集钉的改口形状：从「恰好 {auditor}」换成「恰好空集」，两边都判。

    🔴 强度不许降。这里判的是**恰好等于空集**，不是「auditor 可以出现」也不是「差不许超过一枚」：
    谁往任何一本账里多塞一枚角色、或者从任何一本里漏掉一枚，六个方向里至少一个当场红。反证刀 K1/K2
    （摘掉 auditor 的档位 / 从准入集合里删掉它）各自打红本条的两个方向。
    """
    gap = set(wider) - set(narrower)
    assert gap == set(), f"{wider_name} 比 {narrower_name} 宽出 {sorted(gap)}：三本账今天必须同集"


def test_the_true_source_is_still_a_literal_of_four_names():
    """真源仍是字面量（派生式与开关都不许）：这条从 R357 借来，因为 R413 动的正是它的内容。"""
    text = (REPO / PERMISSIONS_REL).read_text(encoding="utf-8")
    line = next(item for item in text.splitlines() if item.startswith("CREATABLE_ROLES"))
    assert line.count("\"") == 8, line
    for role in sorted(ALL_ROLES):
        assert '"%s"' % role in line, line
    assert "getenv" not in text, "准入集合不许从环境读（R357 判据⑫，本单没给它开门）"


# ---------------------------------------------------------------- 权限面没被放宽


def test_the_auditor_permission_set_is_unchanged_by_this_ticket():
    """裁定只补密级档，没碰权限集：审计员仍然只有 view / download / audit 三项。"""
    assert ROLE_PERMISSIONS["auditor"] == frozenset({ACTION_VIEW, ACTION_DOWNLOAD, ACTION_AUDIT})
    assert permissions_for_role("auditor") == ROLE_PERMISSIONS["auditor"]


@pytest.mark.parametrize(
    "action",
    [ACTION_MANAGE_USERS, ACTION_DELETE, ACTION_UPLOAD, ACTION_ANALYZE, ACTION_EXPORT, ACTION_MANAGE_ALERTS],
)
def test_a_higher_clearance_did_not_buy_the_auditor_any_new_write_permission(action):
    """「读得到但改不动」的机器形状：3 档换不来任何一项写权限，判定仍出自 permission 缺失。"""
    decision = authorization_decision(_principal("auditor"), None, action)

    assert decision.allowed is False
    assert decision.reason_code == "permission_denied"


def test_an_admin_still_outranks_an_auditor_on_the_write_side():
    """同一条 action 换个角色就过：证明上面那格的拒绝是权限集的事，不是密级档的事。"""
    for action in (ACTION_MANAGE_USERS, ACTION_DELETE):
        assert authorization_decision(_principal("admin"), None, action).allowed is True
        assert authorization_decision(_principal("auditor"), None, action).allowed is False


# ---------------------------------------------------------------- 读路：档位买的是密级，不是部门


def test_the_auditor_scope_reads_confidential_documents_in_its_own_department():
    """裁定的实效面：3 档让 auditor 真读得到 3 级件，谓词与管理员那道 department-free 通行证无关。"""
    from app.rag import filters

    scope = filters.resolve_document_retrieval_scope(_principal("auditor"))

    assert scope.classification_levels == frozenset({1, 2, 3})
    assert scope.reason_code == "department_scope"
    assert scope.departments == frozenset({"finance"})
    assert scope.allows({"classification": 3, "department": "finance"}) is True
    assert scope.allows({"classification": 3, "department": "hr"}) is False, "档位买密级，买不到跨部门"


def test_a_staff_still_cannot_read_what_an_auditor_can():
    """密级维度没有全员拉平：staff 还是 1 档，3 级件对它仍然当场不可见。"""
    from app.rag import filters

    staff = filters.resolve_document_retrieval_scope(_principal("staff"))
    auditor = filters.resolve_document_retrieval_scope(_principal("auditor"))

    assert staff.allows({"classification": 3, "department": "finance"}) is False
    assert auditor.allows({"classification": 3, "department": "finance"}) is True
    assert staff.refusal_code({"classification": 3, "department": "finance"}) == "clearance_insufficient"


def test_an_auditor_without_a_department_is_still_refused_fail_closed(monkeypatch):
    """fail-closed 那一格没因为多了个角色而开门：auditor 没有部门时与 staff 同一个码。"""
    from app.rag import filters

    monkeypatch.setattr(filters, "_record_refusal", lambda *args, **kwargs: None)

    with pytest.raises(filters.RetrievalScopeError) as caught:
        filters.resolve_document_retrieval_scope(_principal("auditor", department=""))

    assert caught.value.code == "authorization_unavailable"


# ---------------------------------------------------------------- 真路：账号真建得出来


@pytest.fixture()
def memory_store(monkeypatch):
    """受控内存表：开发态 + ``_using_memory_store`` 替身，一 socket 一 SQL 都不开。"""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(auth, "_MEM_USERS", {})
    monkeypatch.setattr(auth, "_using_memory_store", lambda: True)
    return auth


def test_an_auditor_account_is_really_created(memory_store):
    """R413 的交付面（判据要求的那条真路）：建号回话从「非法角色」变成成功，名册里读得到这一枚。"""
    created = auth.create_user("r413-auditor-real", "pass1234", role="auditor", department="finance")

    assert created == (True, "创建成功"), created
    row = auth.get_user("r413-auditor-real")
    assert row["role"] == "auditor"
    assert clearance_for(row["role"]) == AUDITOR_TIER
    listed = [item for item in auth.list_users() if item["username"] == "r413-auditor-real"]
    assert len(listed) == 1 and listed[0]["role"] == "auditor"


def test_the_sso_handover_keeps_the_auditor_role_instead_of_downgrading_it(memory_store):
    """SSO 递进来的 auditor 身份不再被降成 staff：``normalize_role`` 与 ``upsert_sso_user`` 两格都放行。"""
    assert sso.normalize_role("auditor") == "auditor"
    identity = sso.extract_sso_identity(
        {"X-SSO-User": "r413-sso-auditor", "X-SSO-Role": "auditor", "X-SSO-Department": "finance"}
    )

    assert identity["role"] == "auditor", identity
    ok, message = auth.upsert_sso_user(identity["username"], identity["role"], identity["department"])
    assert ok is True, message
    assert auth.get_user("r413-sso-auditor")["role"] == "auditor"


def test_a_role_that_is_still_not_in_the_roster_is_refused_with_the_same_message(memory_store):
    """白名单没钝化：放的是 auditor，不是「谁都能建」。这句原文与拒答本身都不许漂。"""
    refused = auth.create_user("r413-ghost", "pass1234", role="developer")

    assert refused == (False, "非法角色: developer"), refused
    assert auth.get_user("r413-ghost") is None


# ---------------------------------------------------------------- 旧账不许留着当现状


def test_the_true_source_states_the_new_reason_in_human_language():
    """理由写在读得到真源的那一格里（口径同 R357，但那句人话今天得换成裁定后的）。"""
    text = (REPO / PERMISSIONS_REL).read_text(encoding="utf-8")

    assert "H13" in text
    assert "密级档位" in text
    assert "ROLE_CLEARANCE" in text
    assert "结案" in text, "真源要写明 H13 已经裁了，不许留一条未决的旧话当现状"


def test_rbac_no_longer_reports_the_clearance_line_as_undecided():
    """``rbac.py`` 的模块自述里那句「属 H13，等业主定口径」今天成了假话，必须跟着改口。"""
    head = (REPO / RBAC_REL).read_text(encoding="utf-8").split("def clearance_for")[0]

    assert "H13" in head
    assert "2026-09-28" in head, "改口要带上裁定的日子，读的人才知道这不是又一枚默认值"
    assert "等业主定口径" not in head


# ---------------------------------------------------------------- R357 尺子上的一枚新盲区

#: R413 把真源涨到四枚，顺手改窄了 R357 那把尺子的形状账：它的形状由真源现推
#: （``frozenset(ROLE_PERMISSIONS)`` 与 ``CREATABLE_ROLES``），真源一涨，谁把手抄的三元组
#: ``('staff', 'manager', 'admin')`` 抄回生产代码就不再被那把尺子咬 —— 那枚名单今天已经是假话。
#: 这一格由 R413 自己钉回来（``tests/test_r357_single_role_roster.py`` 不在本单写域，改它归总控）。
RETIRED_ROSTER = frozenset({"staff", "manager", "admin"})
SCAN_ROOTS = ("app", "scripts", "deploy")


def _retired_roster_lines(source: str) -> list[int]:
    """源码里「一整枚常量容器恰好就是那三枚旧角色名」的行号（纯字符串元素才算）。"""
    import ast

    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in {"set", "frozenset"} and node.args:
            node = node.args[0]
        if not isinstance(node, (ast.Set, ast.List, ast.Tuple)):
            continue
        names = [elt.value for elt in node.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
        if len(names) == len(node.elts) and frozenset(names) == RETIRED_ROSTER:
            hits.append(node.lineno)
    # frozenset({...}) 走一遍 ast.walk 会被数两次（Call 与它包着的 Set）：同一行只记一次
    return sorted(set(hits))


def test_the_retired_three_role_roster_ruler_is_not_blind():
    """反空转（同 R357 的对照组纪律）：尺子先要证明它咬得动，零命中才算数。"""
    assert _retired_roster_lines("GUESSED = ('staff', 'manager', 'admin')\n") == [1]
    assert _retired_roster_lines("GUESSED = frozenset({'admin', 'staff', 'manager'})\n") == [1]
    assert _retired_roster_lines('X = frozenset({"staff", "manager", "admin", "auditor"})\n') == [], "真源那四枚不是旧账，不许误伤"
    assert _retired_roster_lines('X = ["staff"]\n') == []


def test_no_production_module_replants_the_retired_three_role_roster():
    """生产代码里一枚手抄的旧三元组都不许有：它现在是假话，不叫另一本名单。"""
    found = []
    for name in SCAN_ROOTS:
        root = REPO / name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            lines = _retired_roster_lines(path.read_text(encoding="utf-8"))
            if lines:
                found.append((path.relative_to(REPO).as_posix(), lines))

    assert found == [], f"R413 之后又被手抄回来的旧三元组：{found}"
