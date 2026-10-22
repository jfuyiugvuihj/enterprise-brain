# -*- coding: utf-8 -*-
"""R533 判据①② —— SLO 口径骨架里那句桥话必须是名册的读数，不是散文里的数字。

对判据的哪一条（派工词 R533）：
  ① ``bridge_note`` 不再携带任何手写枚数/成员名：那句句子由 ``members`` 与
     ``bridge_from_product_lane``（＝``nodes.LANE_TIERS`` 的值面）现场派生，派生函数落在
     observability.py 内部；零新路由、零新对外字段，``slo_slot_caliber()`` 的形状一字未动。
  ② 名册一动、话就跟着动：往 ``ModelTier`` 影子注入一档（lane 对属不动）之后句子必须改口；
     把一条 lane 改配到另一档之后共用那一支必须跟着改口。两枚影子都只活在 monkeypatch 的替换里，
     退出即原样（R466 的姿势：不许漏在活模块上）。
  ③ 契约那一格本件不读它的枚数也不改它（在途单 R523 写域）；交回的是成段原文，见
     ``docs/testing/r533-slo-bridge-note-2026-09-30.md``。
  ④ 本件不碰 R526 那两枚在册件，只保证自己没把它们的输入改脏（指纹台账在反证件里）。

🔴 本件一枚名册枚数都不写死：所有期望值都从 ``contracts.ModelTier`` 与 ``nodes.LANE_TIERS`` 现取，
所以「把句子硬编成今天这副样子」在这件上过不了关（反证刀 K1/K1b 点的就是这一格）。

形状沿用 R526：判据写成「纯函数 + 读数」，反证刀把同一批纯函数喂 mutated 源文，刀口与牙共用一枚
代码，不留「刀有牙、钉没牙」的缝。
"""

import ast
import enum
import inspect
import json
import re
from pathlib import Path

from app.agents import contracts, nodes
from app.api.v1 import observability

REPO = Path(__file__).resolve().parents[1]
OBSERVABILITY = REPO / "app" / "api" / "v1" / "observability.py"
BUDGET_UNIT = "model_budget_tier"

#: 影子注入用的那一档：只存在于 monkeypatch 的替换里，永不进名册、永不进纸。
SHADOW_TIER = "shadow_extra"

#: 基点那句手写散文的死名。本单之后观测面再出现它，就是派生被退回硬编。
STALE_NOTE = (
    "not one-to-one: analysis and report share ModelTier.ANALYSIS, and six of the "
    "seven budget tiers belong to no lane at all"
)

#: 枚数不许再拿英文词写进散文（``one`` 放行：one-to-one 与 shared across lanes 是结构性说法）。
SPELL_NUMBERS = ("two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                 "eleven", "twelve")

#: 「数词紧跟在名册名词中间」就是走私：这一把尺同时量源文字面量与交回的句子。
COUNT_IN_PROSE = re.compile(
    r"\b(?:\d+|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"\s+(?:budget\s+)?(?:tiers?|product\s+lanes?|lanes?)\b",
    re.IGNORECASE,
)

#: 形状锁（判据① 的「零新对外字段」）：这三组键名是本单不许动的契约面。
UNIT_KEYS = ("product_lane", "model_budget_tier", "ledger_stage")
BUDGET_CELL_KEYS = {
    "owns_the_name",
    "decided_by",
    "members",
    "this_is_the_unit_of_the_slo",
    "bridge_from_product_lane",
    "bridge_note",
}
CALIBER_KEYS = {
    "schema", "document", "section", "sample_floor", "percentile_source", "evidence_dirs",
    "spine", "reference_window", "quantiles", "families", "slots", "uncalibrated", "orphan",
}


# ==================== 两名册现取（独立于观测面，否则判据② 是同义反复）====================


def budget_roster() -> list[str]:
    """``ModelTier`` 的值面，现读模块属性（monkeypatch 注了档就必须看得见）。"""
    return [tier.value for tier in contracts.ModelTier]


def lane_bridge() -> dict[str, str]:
    """``nodes.LANE_TIERS`` 的值面，现读模块属性（同上）。"""
    return {
        lane: nodes.LANE_TIERS[lane].value
        for lane in (nodes.LANE_QA, nodes.LANE_ANALYSIS, nodes.LANE_REPORT)
    }


def unlaned_tiers() -> list[str]:
    used = set(lane_bridge().values())
    return [tier for tier in budget_roster() if tier not in used]


def shared_tiers() -> dict[str, list[str]]:
    lanes_by_tier: dict[str, list[str]] = {}
    for lane, tier in lane_bridge().items():
        lanes_by_tier.setdefault(tier, []).append(lane)
    return {tier: lanes for tier, lanes in lanes_by_tier.items() if len(lanes) > 1}


def bridge_note() -> str:
    return observability.slo_units()[BUDGET_UNIT]["bridge_note"]


# ==================== 源文侧的纯函数（反证刀共用这两枚把手）====================


def source_text() -> str:
    return OBSERVABILITY.read_text(encoding="utf-8")


def top_level(text: str, name: str) -> ast.FunctionDef:
    found = [
        node
        for node in ast.parse(text).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(found) == 1, "%s：顶层定义 %d 枚，本件的取段前提变了" % (name, len(found))
    return found[0]


def string_literals(node: ast.AST) -> list[str]:
    """含 f-string：把一枚 JoinedStr 的常量片拼成一串（占位符落空），好让尺子只量散文。"""
    out: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.JoinedStr):
            out.append(
                "".join(
                    part.value
                    for part in sub.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                )
            )
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def prose_counts(text: str) -> list[str]:
    """观测面这两枚函数里，枚数紧跟名册名词的字面量（正读为空，硬编必不空）。"""
    hits: list[str] = []
    for name in ("slo_units", "_slo_bridge_note"):
        for literal in string_literals(top_level(text, name)):
            hits.extend(
                "%s: %r" % (name, match.group(0)) for match in COUNT_IN_PROSE.finditer(literal)
            )
    return hits


def bridge_note_value_node(text: str) -> ast.expr:
    """``slo_units`` 里 ``bridge_note`` 那一格的取值节点：派生＝Call，硬编＝Constant。"""
    units = top_level(text, "slo_units")
    found = [
        value
        for node in ast.walk(units)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values)
        if isinstance(key, ast.Constant) and key.value == "bridge_note"
    ]
    assert len(found) == 1, found
    return found[0]


def grown_model_tier(extra_value: str):
    """一枚影子名册：真 ``ModelTier`` 原样 + 多一档，只活在 monkeypatch 的替换里。"""
    members = {tier.name: tier.value for tier in contracts.ModelTier}
    members[extra_value.upper()] = extra_value
    return enum.Enum("ModelTier", members, type=str)


# ==================== 判据①：句子是派生的，不是抄的 ====================


def test_bridge_note_is_a_call_into_the_rosters_not_a_literal() -> None:
    """那一格的取值必须是 ``_slo_bridge_note(名册, 桥)`` 这一枚调用，不是一串字面。"""
    value = bridge_note_value_node(source_text())
    assert isinstance(value, ast.Call), ast.dump(value)
    assert getattr(value.func, "id", "") == "_slo_bridge_note", ast.dump(value.func)
    args = [node.id for node in value.args if isinstance(node, ast.Name)]
    assert args == ["budget_members", "lane_bridge"], args


def test_the_derivation_lives_inside_observability_and_adds_no_surface() -> None:
    """派生函数落在 observability.py 内部（判据① 写域），且没给自己开新路由。"""
    origin = Path(inspect.getsourcefile(observability._slo_bridge_note)).resolve()
    assert origin == OBSERVABILITY.resolve(), origin
    handler_names = {
        getattr(route.endpoint, "__name__", "") for route in observability.router.routes
    }
    assert "_slo_bridge_note" not in handler_names, sorted(handler_names)


def test_neither_function_smuggles_a_count_into_prose() -> None:
    """反证刀共用这把尺：观测面那两枚函数里，枚数紧跟名册名词的字面量必须一枚都没有。"""
    assert prose_counts(source_text()) == []


def test_the_stale_hand_typed_sentence_is_dead_on_the_page() -> None:
    """旧那句（写 six 的那句）在观测面源文里彻底死了：整句、半句都不留。"""
    text = source_text()
    assert STALE_NOTE not in text
    assert "belong to no lane at all" not in text
    assert bridge_note() != STALE_NOTE


def test_the_note_agrees_with_the_rosters_it_is_derived_from() -> None:
    """句子报的数就是两名册现取的数；句子里不许再出现英文枚数。"""
    note = bridge_note()
    roster, unlaned, shared, bridge = (
        budget_roster(), unlaned_tiers(), shared_tiers(), lane_bridge(),
    )
    digits = set(re.findall(r"\d+", note))
    allowed = {
        str(len(roster)), str(len(unlaned)), str(len(shared)), str(len(bridge)),
    }
    assert digits, note
    assert digits <= allowed, (sorted(digits), sorted(allowed))
    assert str(len(roster)) in digits and str(len(unlaned)) in digits, note
    for word in SPELL_NUMBERS:
        assert not re.search(r"\b%s\b" % word, note, re.IGNORECASE), (word, note)


def test_the_shared_half_names_the_lanes_that_share() -> None:
    """共用那一支：哪几条例外同档、共几档，全由 LANE_TIERS 现算（反证刀 K3 咬这一格）。"""
    shared = shared_tiers()
    assert shared, "本钉守的形状是「确有道共档」；名册要是真变成一一对应，改这枚钉要走取证+总控裁"
    note = bridge_note()
    clause = [part for part in note.split("; ") if "shared across lanes" in part]
    assert len(clause) == 1, note
    for tier, lanes in shared.items():
        for lane in lanes:
            assert re.search(r"lanes [^:]*%s" % re.escape("`%s`" % lane), clause[0]), (lane, clause)
        assert "on tier `%s`" % tier in clause[0], (tier, clause[0])


def test_the_unlaned_half_names_every_tier_no_lane_owns() -> None:
    """无对属那一支：成员名一枚不多一枚不少，顺序就是名册顺序（反证刀 K4 咬这一格）。"""
    note = bridge_note()
    halves = [part for part in note.split("; ") if "named by no lane" in part]
    assert len(halves) == 1, note
    named = re.findall(r"`([^`]+)`", halves[0])
    assert named == unlaned_tiers(), (named, unlaned_tiers())
    laned = set(lane_bridge().values())
    assert not laned & set(named), (laned & set(named), named)


def test_the_published_shape_did_not_change() -> None:
    """判据① 的「零新对外字段」：units 三格、预算格、口径回执顶格集一律原样。"""
    units = observability.slo_units()
    assert tuple(units) == UNIT_KEYS, tuple(units)
    assert set(units[BUDGET_UNIT]) == BUDGET_CELL_KEYS, sorted(units[BUDGET_UNIT])
    assert isinstance(units[BUDGET_UNIT]["bridge_note"], str)
    assert set(observability.slo_slot_caliber()) == CALIBER_KEYS
    readout_units = observability.slo_readout()["units"]
    assert tuple(readout_units) == UNIT_KEYS, tuple(readout_units)
    assert json.dumps(units[BUDGET_UNIT], ensure_ascii=False, default=str)


# ==================== 判据②：名册一动，话就跟着动 ====================


def test_growing_modeltier_with_a_shadow_member_moves_the_sentence(monkeypatch) -> None:
    """往 ModelTier 注一档、lane 对属一字不动 ⇒ 句子必须改口（读数＝「句子随名册变」）。"""
    before = bridge_note()
    roster_before, unlaned_before = len(budget_roster()), len(unlaned_tiers())
    with monkeypatch.context() as box:
        box.setattr(contracts, "ModelTier", grown_model_tier(SHADOW_TIER))
        assert len(budget_roster()) == roster_before + 1
        assert len(unlaned_tiers()) == unlaned_before + 1
        moved = bridge_note()
    assert moved != before, "注一档进名册而句子一个字都没动：那句还是手抄的"
    assert "`%s`" % SHADOW_TIER in moved, moved
    assert "of the %d" % (roster_before + 1) in moved, moved
    assert str(unlaned_before + 1) in moved, moved
    assert bridge_note() == before, "影子退出后名册/句子必须回到原样：变异漏在活模块上了"


def test_repointing_one_lane_moves_the_shared_half(monkeypatch) -> None:
    """给一档补一条 lane 对属（把报告档改配到 plan）⇒ 共用那一支必须自己消失、枚数自己少一枚。"""
    before = bridge_note()
    roster_size = len(budget_roster())
    unlaned_before = unlaned_tiers()
    repointed = dict(nodes.LANE_TIERS)
    repointed[nodes.LANE_REPORT] = contracts.ModelTier.PLAN
    with monkeypatch.context() as box:
        box.setattr(nodes, "LANE_TIERS", repointed)
        assert not shared_tiers(), "本例前提：改配之后不该再有共档"
        unlaned_after = unlaned_tiers()
        moved = bridge_note()
    assert moved != before, "改了一条 lane 的对属而句子一个字都没动：那句还是手抄的"
    assert "shared across lanes" not in moved, moved
    assert "`plan`" not in moved, moved
    assert len(unlaned_after) == len(unlaned_before) - 1, (unlaned_before, unlaned_after)
    assert str(len(unlaned_after)) in moved, moved
    assert "of the %d" % roster_size in moved, moved
    assert bridge_note() == before, "改配的影子漏在活模块上了"


def test_the_sentence_is_a_function_of_the_rosters_alone() -> None:
    """纯函数面：同一副名册同一句话；名册换成别的形状，话就换成别的形状。"""
    derive = observability._slo_bridge_note
    assert derive(["a", "b"], {"one": "a", "two": "b"}).startswith("one-to-one:")
    assert "not one-to-one" not in derive(["a", "b"], {"one": "a", "two": "b"})

    empty = derive(budget_roster(), {})
    assert "named by no lane" in empty, empty
    assert all("`%s`" % tier in empty for tier in budget_roster()), empty

    ghost = derive(budget_roster(), {"qa": "ghostly"})
    assert "which the budget roster does not have" in ghost, ghost

    two_groups = derive(["a", "b", "c", "d"], {"one": "a", "two": "a", "three": "b", "four": "b"})
    assert "2 budget tiers of the 4 are shared across lanes" in two_groups, two_groups


def test_the_note_is_the_same_object_the_surface_publishes() -> None:
    """`/slo` 回执里那格就是派生出来的那句话，不是另一份抄本。"""
    published = observability.slo_readout()["units"][BUDGET_UNIT]["bridge_note"]
    assert published == bridge_note()
    assert observability.slo_units()[BUDGET_UNIT]["bridge_from_product_lane"] == lane_bridge()
