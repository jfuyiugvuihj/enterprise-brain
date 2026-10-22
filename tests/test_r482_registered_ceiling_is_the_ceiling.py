# -*- coding: utf-8 -*-
"""R482 常驻闸：注册表里那枚 ``max_clearance`` 从今天起是天花板，不是台账。

病（现读自基点 ``a0ec662``）：开放平台注册表登记了一枚密级档，两枚对外串（
``MAX_CLEARANCE_NOTE`` 逐字进注册回执与应用列表的响应体、``ApplicationRegisterRequest``
那枚 ``description=`` 逐字进 OpenAPI）齐声说「没有任何 Principal 读它」。R478 刚把这层假话
改口成实话（``MAX_CLEARANCE_ENFORCED = False`` / ``registered_only``）；本单是它的前进档：
把这道档真的接上。

执法点唯一：``app/common/open_platform.py::open_audit_principal`` 把 ``clearance`` 一并
``model_copy(update=...)`` 成 ``min(角色档, max(1, 登记档))``。档位的算法仍然只在
``app/rag/filters.py::resolve_document_retrieval_scope`` 那一处——本单不去那里加第二把尺，
只是终于把这枚封顶之后的档位交给它。

断言格：甲 只降不升（角色高于登记档时读到登记档，角色低于登记档时仍是角色档）；乙 封顶之后的
档位喂进真闸门，``classification_levels`` 逐枚等于 ``range(1, capped + 1)``；丙 三种读不出档位的
缺省形状（缺键／0／负）各自一枚、各自红在自己那一条上；丁 两枚对外串与 ``MAX_CLEARANCE_ENFORCED``
三者口径同源，且串里点名的那枚函数真的写着这枚读数（函数名与行区间一律运行时派生，零硬编码行号）。

反证三刀（判据⑤）：刀一 摘掉 ``clearance`` 那一格 update；刀二 把取小换成取大；刀三 执法已开而
常量仍留 ``False``。前两刀走 R253 影子根（变异只落 ``%TEMP%`` 副本，被跟踪文件全程只读），
第三刀只改内存常量。
"""

from __future__ import annotations

import ast
import inspect

import pytest
from fastapi import FastAPI

from app.agents.contracts import Principal
from app.api.v1 import open_platform as open_platform_routes
from app.common import audit, open_platform
from app.common.rbac import clearance_for
from app.rag.filters import resolve_document_retrieval_scope
from tests import _temp_edit_overlay as overlay
from tests import test_r478_no_closed_gate_as_placeholder as r478
from tests import test_r78_unearned_claims as r78

REPO = overlay.REPO
MODULE_REL = "app/common/open_platform.py"
#: 判据里那枚「封顶怎么算」在源码里的长相：一个函数名加一段真写着的表达式，零枚行号。
ENFORCEMENT_FUNCTION = "open_audit_principal"
CEILING_KEY = "max_clearance"


@pytest.fixture(autouse=True)
def _own_the_process_globals(monkeypatch):
    """与 r78 / r478 同一套进程级卫生：注册表与审计都是模块状态，进出都得清。"""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("OPEN_PLATFORM_APP_STORE_PATH", raising=False)
    monkeypatch.setenv("AUDIT_PERSISTENCE", "disabled")
    audit.reset_audit_storage()
    open_platform.configure_app_store("")
    open_platform.clear_app_registry()
    audit.clear_audit_events()
    yield
    open_platform.configure_app_store("")
    open_platform.clear_app_registry()
    audit.clear_audit_events()
    audit.reset_audit_storage()


# ==================== 把手：档位、注册表行、闸门 ====================

class _NoFigure:
    """Sentinel: a registry row written before this field existed carries no such key."""


NO_FIGURE = _NoFigure()


def _subject(*, role: str, department: str = "rnd") -> Principal:
    """A subject whose tier comes from the role map, exactly as the transport builds one."""
    return Principal.from_user(
        {"id": "u-r482", "username": "claimed-by-a-header", "role": role, "department": department}
    )


def _row(figure) -> dict:
    """One registry row in the shape ``verify_open_request`` hands it over: ``asdict`` plus actor."""
    row = {"app_id": "aaaaaaaaaaaaaaaa", "app_name": "r482", "actor": "open-app:aaaaaaaaaaaaaaaa"}
    if figure is not NO_FIGURE:
        row[CEILING_KEY] = figure
    return row


def _capped(*, role: str, figure) -> Principal:
    return open_platform.open_audit_principal(_subject(role=role), _row(figure))


def _levels(principal: Principal):
    """Ask the one real classification algorithm which tiers a subject may read."""
    return resolve_document_retrieval_scope(principal).classification_levels


# ==================== 甲 · 封顶只降不升 ====================

def test_a_registered_tier_below_the_role_tier_is_the_tier_that_reads():
    """判据④(a)：角色 3 档 + 登记 1 档 ⇒ 只能读到 1 档。"""
    role = "admin"
    role_tier = clearance_for(role)
    assert role_tier > open_platform.MINIMUM_CLEARANCE, (
        "this case proves nothing unless the role map still puts " + role + " above the "
        "floor; it reads " + str(role_tier))

    capped = _capped(role=role, figure=open_platform.MINIMUM_CLEARANCE)

    assert capped.clearance == open_platform.MINIMUM_CLEARANCE, capped.clearance
    assert capped.clearance < role_tier, "the registered tier did not cap the subject"


def test_a_higher_registered_tier_never_raises_the_subject_above_its_role():
    """判据④(b)：角色 1 档 + 登记 3 档 ⇒ 仍是 1 档，不许被抬高。"""
    role = "staff"
    role_tier = clearance_for(role)
    granted = role_tier + 2

    capped = _capped(role=role, figure=granted)

    assert capped.clearance == role_tier, (
        "a registered figure lifted the subject above the tier its role grants: "
        + str(capped.clearance) + " > " + str(role_tier))


def test_the_ceiling_is_only_ever_one_of_the_two_tiers_it_compares():
    """The whole domain of the clamp in one sweep: never above either operand, never below the floor."""
    floor = open_platform.MINIMUM_CLEARANCE
    for role in ("staff", "manager", "admin"):
        role_tier = clearance_for(role)
        for figure in (floor, role_tier - 1, role_tier, role_tier + 1, role_tier + 5, 99):
            capped = _capped(role=role, figure=figure).clearance
            assert capped == min(role_tier, max(floor, figure)), (role, figure, capped)
            assert floor <= capped <= role_tier, (role, figure, capped)


# ==================== 乙 · 封顶之后的档位交给真闸门 ====================

def test_the_capped_tier_is_the_levels_the_retrieval_gate_opens():
    """判据④(c)：封顶后的档位喂进 ``resolve_document_retrieval_scope``，``classification_levels``
    逐枚等于 ``range(1, capped + 1)``。这里不复制第二把尺——闸门是 ``app/rag/filters.py`` 那一枚。
    """
    floor = open_platform.MINIMUM_CLEARANCE
    role = "admin"
    assert clearance_for(role) > floor + 1, "this case needs a role two tiers above the floor"

    capped = _capped(role=role, figure=floor + 1)
    scope = resolve_document_retrieval_scope(capped)

    assert capped.clearance == floor + 1, capped.clearance
    assert scope.classification_levels == frozenset(range(1, capped.clearance + 1)), (
        scope.classification_levels)
    assert len(scope.classification_levels) < len(_levels(_subject(role=role))), (
        "the ceiling did not narrow what the gate opens")


def test_the_capped_tier_narrows_a_non_administrators_scope_the_same_way():
    """The clamp is on the subject, not on one branch of the gate: a staff row is capped alike."""
    staff = _capped(role="staff", figure=clearance_for("staff") + 3)
    scope = resolve_document_retrieval_scope(staff)

    assert staff.clearance == clearance_for("staff")
    assert scope.classification_levels == frozenset(range(1, staff.clearance + 1)), (
        scope.classification_levels)
    assert scope.reason_code == "department_scope", scope.reason_code


# ==================== 丙 · 缺省一律 fail-closed 收到最小档 ====================

def test_a_row_with_no_ceiling_key_at_all_falls_to_the_minimum_tier():
    """判据④(d) 之一：缺键（旧行）。这一格只咬「缺键就沿用角色档」那一种退化实现。"""
    role_tier = clearance_for("admin")
    assert CEILING_KEY not in _row(NO_FIGURE), "the fixture stopped being a row without the key"

    capped = _capped(role="admin", figure=NO_FIGURE)

    assert capped.clearance == open_platform.MINIMUM_CLEARANCE, (
        "a registry row which carries no figure at all has to fall to the minimum tier, not "
        "keep the role tier: " + str(capped.clearance) + " vs role " + str(role_tier))


def test_a_zero_ceiling_falls_to_the_minimum_tier_not_to_no_ceiling():
    """判据④(d) 之二：0。这一格只咬「0 被当成没登记，于是照角色档放行」那一种写法。"""
    capped = _capped(role="admin", figure=0)

    assert capped.clearance == open_platform.MINIMUM_CLEARANCE, (
        "a registered 0 must read as the narrowest answer, not as absence: "
        + str(capped.clearance))


def test_a_negative_ceiling_falls_to_the_minimum_tier():
    """判据④(d) 之三：负数。这一格只咬 ``min`` 少了 ``max`` 那一层夹底。"""
    floor = open_platform.MINIMUM_CLEARANCE
    capped = _capped(role="admin", figure=-7)

    assert capped.clearance == floor, (
        "a negative figure must not put a subject at or below zero, where the retrieval "
        "gate refuses the caller outright: " + str(capped.clearance))
    assert _levels(capped) == frozenset({floor})


def test_an_unreadable_ceiling_falls_closed_instead_of_raising():
    """A figure which is not a number is the fourth shape of silence, and answers the same way."""
    for junk in ("", "confidential", None, [], "3 tiers", "2", 2.9, 0.5):
        capped = _capped(role="admin", figure=junk)
        assert capped.clearance == open_platform.MINIMUM_CLEARANCE, (junk, capped.clearance)


# ==================== 丁 · 两枚对外串与常量同源 ====================

def _published_description() -> str:
    built = FastAPI(title="r482-source-of-truth")
    built.include_router(open_platform_routes.apps_router, prefix="/api/v1")
    schema = built.openapi()
    return schema["components"]["schemas"]["ApplicationRegisterRequest"]["properties"][
        CEILING_KEY]["description"]


def _clamp_span() -> tuple:
    """The enforcement function's own lines and text, derived at run time: no line is quoted."""
    lines, start = inspect.getsourcelines(open_platform.open_audit_principal)
    return "".join(lines), start, start + len(lines) - 1


def _figure_readers(rel: str, text: str) -> set:
    tree = ast.parse(text.replace("\r\n", "\n"))
    owners = {}
    for owner in ast.walk(tree):
        if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(owner):
                owners[id(child)] = owner.name
    readers = set()
    for node in ast.walk(tree):
        touched = ((isinstance(node, ast.Attribute) and node.attr == CEILING_KEY)
                   or (isinstance(node, ast.Constant) and node.value == CEILING_KEY))
        if touched:
            readers.add(owners.get(id(node), "<module>"))
    return readers


def test_the_note_and_the_openapi_description_describe_the_function_that_acts():
    """判据④(e)：串里说的必须就是码里做的；note / description / 常量三者同一口径。"""
    note = str(open_platform.MAX_CLEARANCE_NOTE)
    description = _published_description()
    clamp_source, first, last = _clamp_span()

    # ① 常量说的与真行为一致：拿一次封顶量出来，再回头对常量。
    measured = _capped(role="admin", figure=open_platform.MINIMUM_CLEARANCE).clearance
    enforced_by_behaviour = measured < clearance_for("admin")
    assert enforced_by_behaviour is open_platform.MAX_CLEARANCE_ENFORCED is True, (
        "MAX_CLEARANCE_ENFORCED disagrees with the clamp: the clamp says "
        + str(enforced_by_behaviour) + ", the constant says "
        + str(open_platform.MAX_CLEARANCE_ENFORCED))

    # ② effect 这一枚词就在响应体那句话里，且退役的那一句不许回潮。
    assert open_platform.MAX_CLEARANCE_EFFECT.replace("_", " ") in note, (
        "the effect word is not the sentence the body publishes: "
        + open_platform.MAX_CLEARANCE_EFFECT)
    assert "registered_only" not in note and "registered only" not in description.lower(), (
        "R478 那句「只登记不执行」回潮了")

    # ③ 两枚串都点名同一枚函数，而那枚函数自己真的读这枚字段（区间运行时派生）。
    for label, text in (("note", note), ("openapi description", description)):
        assert ENFORCEMENT_FUNCTION in text, label + " does not name the function which acts"
        assert "min(" in text, label + " does not state the arithmetic"
        assert "level 1" in text.lower(), label + " does not state the fail-closed floor"
    assert CEILING_KEY in clamp_source, (
        "the clamp no longer reads the stored figure inside " + ENFORCEMENT_FUNCTION
        + " (lines " + str(first) + "-" + str(last) + " of " + MODULE_REL + ")")
    readers = _figure_readers(MODULE_REL, overlay.authoritative_text(MODULE_REL))
    assert ENFORCEMENT_FUNCTION in readers, (
        "the two published sentences name " + ENFORCEMENT_FUNCTION + ", the code reads the "
        "stored figure in " + str(sorted(readers)))


def test_the_response_body_publishes_the_same_words_as_the_module_constant():
    """The receipt and the list are the two surfaces a client actually reads."""
    issued = r78._register_through_the_api(
        app_name="r482-receipt",
        allowed_actions=["query"],
        allowed_departments=[r78.CALLER_DEPARTMENT],
        max_clearance=4,
    )
    listed = r78._list_through_the_api()["applications"][0]

    for row in (issued, listed):
        # The fact first, then the agreement: comparing the body with the constant alone is
        # a tautology, and a clamp which is live beside a constant still reading False would
        # pass it. That is exactly the split knife three has to catch.
        assert row["max_clearance_enforced"] is True, (
            "the published body no longer says the ceiling is applied, whatever the "
            "constant claims")
        assert row["max_clearance_enforced"] is open_platform.MAX_CLEARANCE_ENFORCED
        assert open_platform.MAX_CLEARANCE_ENFORCED is True
        assert row["max_clearance_effect"] == open_platform.MAX_CLEARANCE_EFFECT
        assert row["max_clearance_note"] == open_platform.MAX_CLEARANCE_NOTE
    assert listed["max_clearance"] == issued["max_clearance"] == 4


# ==================== 反证刀（判据⑤）====================

def _clamp_value_segment(source: str) -> str:
    """The expression assigned to ``update`` inside the enforcement function, read from the tree."""
    tree = ast.parse(source.replace("\r\n", "\n"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == ENFORCEMENT_FUNCTION:
            for statement in node.body:
                if isinstance(statement, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == "update"
                        for target in statement.targets):
                    segment = ast.get_source_segment(source, statement.value)
                    assert segment, "the clamp expression has no source segment"
                    return segment
    raise AssertionError("no `update = ...` assignment inside " + ENFORCEMENT_FUNCTION)


class _ClampEdit(overlay.ShadowEdit):
    """一扇反证窗：变异只落影子根，再 exec 回同一枚模块对象；被跟踪文件全程只读。"""

    tag = "r482"
    execs_module = True

    def __init__(self, rel, replace):
        super().__init__(REPO / rel)
        self.replace = replace

    def mutate(self, text):
        text = text.replace("\r\n", "\n")
        segment = _clamp_value_segment(text)
        if text.count(segment) != 1:
            raise AssertionError("反证刀的锚不唯一：" + segment[:60])
        mutant = text.replace(segment, self.replace(segment))
        try:
            compile(mutant, "<r482-counter-evidence>", "exec")
        except SyntaxError as exc:
            raise AssertionError("反证刀产物编译不过：" + str(exc)) from exc
        assert mutant != text, "这一刀没有改变任何东西"
        return mutant


def _reds(fn, why):
    try:
        fn()
    except AssertionError:
        return
    pytest.fail(why)


def _stays_green(fn, why):
    try:
        fn()
    except AssertionError as exc:
        pytest.fail(why + "（窗外就该绿的，读数：" + str(exc)[:160] + "）")


def test_counter_evidence_dropping_the_clearance_entry_goes_red():
    """刀一：摘掉 ``clearance`` 那一格 update ⇒ 甲、丙、乙、格乙、同源五处同时红。"""
    _stays_green(test_a_registered_tier_below_the_role_tier_is_the_tier_that_reads, "刀一的控制格")
    _stays_green(r478.test_the_stored_figure_is_still_read_only_for_reporting, "刀一的控制格（格乙）")
    with _ClampEdit(MODULE_REL, lambda segment: "{}"):
        _reds(test_a_registered_tier_below_the_role_tier_is_the_tier_that_reads,
              "摘掉执法那一格之后甲钉还绿：它没有咬住封顶")
        _reds(test_a_row_with_no_ceiling_key_at_all_falls_to_the_minimum_tier,
              "摘掉执法那一格之后缺键那枚钉还绿：丙格第一枚不承重")
        _reds(test_the_capped_tier_is_the_levels_the_retrieval_gate_opens,
              "摘掉执法那一格之后闸门那枚钉还绿：乙格不承重")
        _reds(r478.test_the_stored_figure_is_still_read_only_for_reporting,
              "摘掉执法那一格之后格乙还绿：加宽过的尺子是空转的")
        _reds(test_the_note_and_the_openapi_description_describe_the_function_that_acts,
              "摘掉执法那一格之后同源那枚钉还绿：常量与真行为分开了口径没人抓")
    _stays_green(test_a_registered_tier_below_the_role_tier_is_the_tier_that_reads,
                 "刀一退出后字节没还原")


def test_counter_evidence_flipping_the_ceiling_upwards_goes_red():
    """刀二：把取小换成取大 ⇒ 「不许抬高」、全域扫描、格乙判定面三处必须红。"""
    _stays_green(test_a_higher_registered_tier_never_raises_the_subject_above_its_role, "刀二的控制格")
    _stays_green(r478.test_the_stored_figure_is_still_read_only_for_reporting, "刀二的控制格（格乙）")
    with _ClampEdit(MODULE_REL, lambda segment: segment.replace("min(", "max(", 1)):
        _reds(test_a_higher_registered_tier_never_raises_the_subject_above_its_role,
              "取小换成取大之后「不许抬高」那枚钉还绿：它量不出放宽")
        _reds(test_the_ceiling_is_only_ever_one_of_the_two_tiers_it_compares,
              "取小换成取大之后全域扫描那枚钉还绿：这一格是装饰")
        _reds(test_a_negative_ceiling_falls_to_the_minimum_tier,
              "取小换成取大之后负数那枚钉还绿：夹底那一格没被量到")
        _reds(r478.test_the_stored_figure_is_still_read_only_for_reporting,
              "取小换成取大之后格乙还绿：判定面的形状没被量到")
    _stays_green(test_a_higher_registered_tier_never_raises_the_subject_above_its_role,
                 "刀二退出后字节没还原")


def test_counter_evidence_a_live_clamp_with_a_dead_constant_goes_red(monkeypatch):
    """刀三：执法已开而 ``MAX_CLEARANCE_ENFORCED`` 仍留 ``False`` ⇒ 对外那两枚钉必须红。"""
    _stays_green(test_the_note_and_the_openapi_description_describe_the_function_that_acts,
                 "刀三的控制格")
    _stays_green(r78.test_the_registration_response_labels_the_clearance_it_stores,
                 "刀三的控制格（r78 换锚钉）")
    monkeypatch.setattr(open_platform, "MAX_CLEARANCE_ENFORCED", False)
    _reds(test_the_note_and_the_openapi_description_describe_the_function_that_acts,
          "常量改回 False 而同源那枚钉还绿：口径分裂没有被当场抓住")
    _reds(test_the_response_body_publishes_the_same_words_as_the_module_constant,
          "常量改回 False 而响应体那枚钉还绿：对外那一面漏量")
    _reds(r78.test_the_registration_response_labels_the_clearance_it_stores,
          "常量改回 False 而 r78 换锚后的响应体钉还绿：锚没有咬在常量与串的同源上")
    _reds(r78.test_the_api_documentation_says_the_same_thing_to_the_client_that_reads_it,
          "常量改回 False 而 r78 换锚后的 OpenAPI 钉还绿：发布面漏量")
