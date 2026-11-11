# -*- coding: utf-8 -*-
"""R533 判据②③ —— 反证刀：把「桥话派生」这一格钝掉，看牙认不认得出。

## 口径（沿用 R524 / R526 那一套，不另立规矩）

- 🔴 **仓里一字节都不改**。摘刀一律在**内存影子**里做：observability.py 的源文在 import 那一刻
  抄进内存，按锚点改一格，写进 ``tmp_path`` 的影子副本，再 ``exec`` 回挂到模块上（``monkeypatch``
  负责 teardown 复原原件身份）。每把刀进刀前后各核一次被跟踪文件的 sha256，末了总清点。
- **源文侧的摘刀**交回给**在册那枚钉用的同一表达式**（``D.prose_counts`` / ``D.bridge_note_value_node``
  收的就是源文字符串），所以刀口与牙共用一枚代码，不留「刀有牙、钉没牙」的缝。
- **每把刀都带正控**：同一套机械不摘刀（``edits=()``）先跑一遍，victim 必须先绿。
- **victim 全部点名**，走台账：没真摘过的刀、没真咬红的钉，总清点那一枚用例当场拒。

## 刀的清单

| 刀 | 摘掉的那一格 | victim（在册钉） |
|----|--------------|------------------|
| K1  | ``slo_units`` 的 ``bridge_note`` 退回基点那句硬编（写 six 的那句） | 枚数对判钉 + 源文形状钉 + 散文枚数扫描 |
| K1b | 同一格退回「今天派生出来的那串」的硬编（看着对，但不动） | 形状钉 + 影子注档钉 + 改配钉 |
| K2  | 派生里无对属那一支的总数改读桥（``len(members)`` → ``len(lanes_by_tier)``） | 枚数对判钉 |
| K3  | 共用那一支的门槛钝掉（``len(lanes) > 1`` → ``> 2``） | 共用半句钉（红在共用那一支上） |
| K4  | 无对属那一支的成员名摘掉（只留数） | 名册名对判钉 |

判据② 的牙本身在 ``tests/test_r533_bridge_note_is_derived.py``：本件不重抄一份相似物。
"""

import ast
import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

from app.api.v1 import observability

REPO = Path(__file__).resolve().parents[1]
OBSERVABILITY = REPO / "app" / "api" / "v1" / "observability.py"
PAPER = REPO / "docs" / "testing" / "r533-slo-bridge-note-2026-09-30.md"

#: 在册件 + 禁改清单 + 本单纸：每一把刀进刀前后都核这一串指纹（判据③ 的「一枚字节没碰」也在这儿留痕）。
TRACKED = (
    OBSERVABILITY,
    REPO / "tests" / "test_r533_bridge_note_is_derived.py",
    REPO / "tests" / "test_r526_slot_caliber_closure.py",
    REPO / "tests" / "test_r526_counter_evidence_teeth.py",
    REPO / "tests" / "test_r105_slo_contract.py",
    REPO / "docs" / "api" / "contract-v1.md",
    REPO / "migrations" / "manifest.json",
    PAPER,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


FINGERPRINT_AT_IMPORT = {path: _sha(path) for path in TRACKED}
#: 摘刀只作用在内存副本上，所以「原件长什么样」必须在 import 那一刻抄下来，不许回头再读盘。
TEXT_AT_IMPORT = OBSERVABILITY.read_text(encoding="utf-8")
#: 回挂之前那两枚把手的身份：窗尾必须还是它们（R466 记的那一笔：整片 exec 会把身份全换掉）。
ORIGINAL_BINDINGS = {"slo_units": observability.slo_units, "_slo_bridge_note": observability._slo_bridge_note}


def _load(relative: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D = _load("tests/test_r533_bridge_note_is_derived.py", "r533_derived_for_teeth")

#: 基点那句手写散文（判据② 要消灭的那一类）：只作 K1 的影子弹药，永不落盘。
STALE_NOTE = D.STALE_NOTE
#: K1 的替换形状：整格退回字面量，缩进照抄在册那格的书写位置。
CALL_LINE = '            "bridge_note": _slo_bridge_note(budget_members, lane_bridge),\n'
STALE_LINE = '            "bridge_note": (\n%s\n            ),\n' % (
    "                " + json.dumps(STALE_NOTE[: len(STALE_NOTE) // 2]) + "\n"
    "                " + json.dumps(STALE_NOTE[len(STALE_NOTE) // 2 :])
)
UNLANED_TOTAL = "f\"{tally(len(unlaned), 'budget tier')} of the {len(members)} \""
SHARED_GATE = "if len(lanes) > 1}"
SHARED_GATE_CUT = "if len(lanes) > 2}"
UNLANED_NAMES = "f\"{agrees(len(unlaned), 'is', 'are')} named by no lane: {spelled(unlaned)}\""
UNLANED_NAMES_CUT = "f\"{agrees(len(unlaned), 'is', 'are')} named by no lane\""

_CUT_TAGS: set = set()
_RED_VICTIMS: set = set()
KNIFE_TAGS = ("k1", "k1b", "k2", "k3", "k4")


# ==================== 机械：影子摘刀 + 源文摘刀 + 定罪格调用器 ====================


def _top_level_segment(text: str, name: str) -> str:
    found = [
        ast.get_source_segment(text, node)
        for node in ast.parse(text).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(found) == 1, "%s：顶层定义 %d 枚，本件的取段前提变了" % (name, len(found))
    return found[0] or ""


def _mutate(name: str, edits) -> str:
    r"""源文侧的摘刀：只在内存副本上动，整本文件一字节不改（指纹台账盯着）。

    🔴 交回的是**整本文件的摘后副本**，不是那枚函数的孤段：在册钉那两把尺
    （``D.prose_counts``）要在一本文件里同时取到 ``slo_units`` 与 ``_slo_bridge_note``，
    喂孤段会让它取不到另一枚而报「取段前提变了」——那是机械坏了，不是牙咬到。
    """
    scope = _top_level_segment(TEXT_AT_IMPORT, name)
    mutated = scope
    for needle, replacement in edits:
        hits = mutated.count(needle)
        assert hits == 1, "锚点在 %s 里命中 %d 次 ⇒ 这枚反证是空的" % (name, hits)
        mutated = mutated.replace(needle, replacement, 1)
    if edits:
        assert mutated != scope, "摘刀没作用到东西上"
    ast.parse(mutated)
    whole = TEXT_AT_IMPORT.replace(scope, mutated, 1)
    assert whole != TEXT_AT_IMPORT, "摘后的那枚函数拼不回整本文件：锚点抓错格子"
    ast.parse(whole)
    return whole


def _cut(name: str, edits, monkeypatch, tmp_path, tag: str):
    """把摘过格的那枚函数写进 tmp_path 影子副本，再 exec 回挂到活模块的名字上。

    ``edits=()`` 就是正控：同一套机械不改一格，victim 必须先绿一遍，否则「红」是它本来就红。
    """
    tracked = OBSERVABILITY.resolve()
    assert _sha(tracked) == FINGERPRINT_AT_IMPORT[tracked], "%s：进刀之前就不是原样了" % tag
    source = _top_level_segment(TEXT_AT_IMPORT, name)
    shadow_source = source
    for needle, replacement in edits:
        hits = shadow_source.count(needle)
        assert hits == 1, "%s：锚点在 %s 里命中 %d 次 ⇒ 这枚反证是空的" % (tag, name, hits)
        shadow_source = shadow_source.replace(needle, replacement, 1)
    if edits:
        assert shadow_source != source, "%s：改了个寂寞" % tag

    target = tmp_path / ("r533_shadow_%s.py" % tag)
    assert REPO not in target.resolve().parents, "%s：影子副本落进仓里了" % tag
    target.write_text(shadow_source, encoding="utf-8", newline="\n")

    original = getattr(observability, name)
    monkeypatch.setattr(observability, name, original)  # 先把原件记进 teardown，再 exec 覆盖同名
    exec(compile(shadow_source, str(target), "exec"), observability.__dict__)
    shadow = getattr(observability, name)
    assert shadow is not original, "%s：影子与原件是同一枚对象" % tag
    assert _sha(tracked) == FINGERPRINT_AT_IMPORT[tracked], "%s：摘刀留下了写口" % tag
    _CUT_TAGS.add(tag)
    return shadow


def _bite(fn, *args) -> str:
    """跑在册那枚钉：红了交回「类型: 红话」，没红交回空串。"""
    try:
        fn(*args)
    except Exception as error:  # noqa: BLE001  这里要的就是任何形状的红
        _RED_VICTIMS.add(fn.__name__)
        return "%s: %s" % (type(error).__name__, error)
    return ""


# ==================== K1：整格退回基点那句硬编（写 six 的那句）====================


def test_k1_positive_control_the_surface_and_the_source_both_read_derived() -> None:
    """正控：不摘刀时，源文那一格是 Call、散文扫描为空、句子与名册同数。"""
    assert isinstance(D.bridge_note_value_node(TEXT_AT_IMPORT), ast.Call)
    assert D.prose_counts(TEXT_AT_IMPORT) == []
    D.test_the_note_agrees_with_the_rosters_it_is_derived_from()


def test_k1_retyping_the_stale_sentence_goes_red_on_three_pins(monkeypatch, tmp_path) -> None:
    """**刀 K1**：派生退回基点那句硬编 ⇒ 形状钉、散文枚数扫描、枚数对判钉一起红。

    源文侧摘的是内存副本，喂给在册钉用的同一表达式；运行侧回挂之后叫的是**在册钉本身**。
    """
    mutated = _mutate("slo_units", [(CALL_LINE, STALE_LINE)])
    assert not isinstance(D.bridge_note_value_node(mutated), ast.Call), "K1 之后那一格居然还是调用"
    assert D.prose_counts(mutated), "K1 把 six/seven 塞回散文，枚数扫描却报空：死牙"

    _cut("slo_units", [(CALL_LINE, STALE_LINE)], monkeypatch, tmp_path, "k1")
    red = _bite(D.test_the_note_agrees_with_the_rosters_it_is_derived_from)
    assert red.startswith("AssertionError"), red


# ==================== K1b：退回「今天派生出来的那串」的硬编（看着对，但不动）====================


def _today_literal() -> str:
    """把今天派生出来的那句照抄成字面量：枚数来自现读名册，本件一个字都没手抄。"""
    return '            "bridge_note": %s,\n' % json.dumps(D.bridge_note())


def test_k1b_positive_control_the_unmutated_shadow_still_moves_with_the_roster(monkeypatch, tmp_path) -> None:
    """正控：同一套机械原样回挂 ``slo_units``，影子注档那枚钉必须先绿。"""
    _cut("slo_units", (), monkeypatch, tmp_path, "k1b_control")
    D.test_growing_modeltier_with_a_shadow_member_moves_the_sentence(monkeypatch)


def test_k1b_freezing_todays_derived_sentence_starves_the_roster_teeth(monkeypatch, tmp_path) -> None:
    """**刀 K1b**：硬编的内容与今天逐字相同 ⇒ 所有「对个现读数」的钉全绿，只有「句子随名册变」咬得住。

    这一把就是本单存在的理由：一枚抄对了今天的字符串照样是散文里的数字，名册一动它就成假话。
    """
    mutated = _mutate("slo_units", [(CALL_LINE, _today_literal())])
    assert D.prose_counts(mutated), "K1b 的句子带着名册枚数，扫描却说干净：尺钝了"
    assert _today_literal().strip() != CALL_LINE.strip()

    _cut("slo_units", [(CALL_LINE, _today_literal())], monkeypatch, tmp_path, "k1b")
    red = _bite(D.test_growing_modeltier_with_a_shadow_member_moves_the_sentence, monkeypatch)
    assert "句子" in red or "AssertionError" in red, red
    red2 = _bite(D.test_repointing_one_lane_moves_the_shared_half, monkeypatch)
    assert red2.startswith("AssertionError"), red2


# ==================== K2：无对属那一支的总数改读桥（不看名册）====================


def _totals_in_the_sentence() -> set:
    """句子里每一枚 "of the <n>" 的读数：它们必须全等于预算名册的现取总数。"""
    return set(re.findall(r"of the (\d+)", D.bridge_note()))


def test_k2_positive_control_the_total_comes_from_the_budget_roster() -> None:
    """正控：锚点在场，且句子今天报的总数每一枚都是名册总数（现取，一枚不手抄）。"""
    scope = _top_level_segment(TEXT_AT_IMPORT, "_slo_bridge_note")
    assert scope.count(UNLANED_TOTAL) == 1, "锚点没了：派生那一支的形状被改过，本刀前提变了"
    assert _totals_in_the_sentence() == {str(len(D.budget_roster()))}, _totals_in_the_sentence()


def test_k2_reading_the_total_off_the_bridge_instead_of_the_roster_goes_red(monkeypatch, tmp_path) -> None:
    """**刀 K2**：``len(members)`` 换成 ``len(lanes_by_tier)`` ⇒ 枚数对判钉红（数不再等于名册）。"""
    _cut(
        "_slo_bridge_note",
        [(UNLANED_TOTAL, UNLANED_TOTAL.replace("{len(members)}", "{len(lanes_by_tier)}"))],
        monkeypatch, tmp_path, "k2",
    )
    red = _bite(D.test_the_note_agrees_with_the_rosters_it_is_derived_from)
    assert red.startswith("AssertionError"), red
    roster_total = str(len(D.budget_roster()))
    assert _totals_in_the_sentence() != {roster_total}, "钝刀之后总数还全等于名册：这枚牙是死牙"
    assert roster_total in _totals_in_the_sentence(), "钝刀该只钝掉一支，另一支的总数还得是真名册读数"


# ==================== K3：把「共用那一支」的门槛钝掉（必须红在共用那半句上）====================


def test_k3_positive_control_the_shared_half_is_there(monkeypatch, tmp_path) -> None:
    """正控：不摘刀时共用那一支在场，在册那枚共用钉先绿一遍。"""
    _cut("_slo_bridge_note", (), monkeypatch, tmp_path, "k3_control")
    D.test_the_shared_half_names_the_lanes_that_share()


def test_k3_dulling_the_shared_gate_goes_red_on_the_shared_half(monkeypatch, tmp_path) -> None:
    """**刀 K3**：``len(lanes) > 1`` 钝成 ``> 2`` ⇒ 共用半句整支消失，红在共用那一支上。"""
    _cut("_slo_bridge_note", [(SHARED_GATE, SHARED_GATE_CUT)], monkeypatch, tmp_path, "k3")
    assert "shared across lanes" not in D.bridge_note(), "钝刀之后共用那一支居然还在"
    red = _bite(D.test_the_shared_half_names_the_lanes_that_share)
    assert red.startswith("AssertionError"), red


# ==================== K4：把无对属那一支的成员名摘掉（只留数）====================


def test_k4_positive_control_the_names_are_the_rosters_own_order() -> None:
    """正控：在册那枚名册名钉此刻是绿的，且顺序就是名册顺序。"""
    D.test_the_unlaned_half_names_every_tier_no_lane_owns()


def test_k4_dropping_the_roster_names_goes_red_on_the_name_pin(monkeypatch, tmp_path) -> None:
    """**刀 K4**：那一支只报数不报名 ⇒ 名册名对判钉红（数对而名册丢了也是假话）。"""
    _cut("_slo_bridge_note", [(UNLANED_NAMES, UNLANED_NAMES_CUT)], monkeypatch, tmp_path, "k4")
    red = _bite(D.test_the_unlaned_half_names_every_tier_no_lane_owns)
    assert red.startswith("AssertionError"), red


# ==================== 总清点：刀都真摘过、牙都真咬过、仓里一字节没动 ====================

#: 每把刀必须咬红的那枚在册钉（按钉名点名，不数总数——数总数会把死牙算成活的）。
EXPECTED_RED_VICTIMS = {
    "test_the_note_agrees_with_the_rosters_it_is_derived_from",  # K1 / K2
    "test_growing_modeltier_with_a_shadow_member_moves_the_sentence",  # K1b
    "test_repointing_one_lane_moves_the_shared_half",  # K1b
    "test_the_shared_half_names_the_lanes_that_share",  # K3
    "test_the_unlaned_half_names_every_tier_no_lane_owns",  # K4
}


def test_z9_the_ledger_names_every_knife_and_every_tooth_bit() -> None:
    """五把刀全真摘过，点名在册钉全真咬出红；判据要求的下限是三把，这里一枚都不少。"""
    assert _CUT_TAGS >= set(KNIFE_TAGS), sorted(set(KNIFE_TAGS) - _CUT_TAGS)
    missing = EXPECTED_RED_VICTIMS - _RED_VICTIMS
    assert not missing, "这些在册钉一次都没被摘红：%s" % sorted(missing)
    assert len(_RED_VICTIMS) >= 3, sorted(_RED_VICTIMS)


def test_z9b_the_tracked_files_are_the_ones_we_opened_the_door_with() -> None:
    """五把刀跑完，被跟踪件的指纹必须还是进门那一刻那些：契约纸与 migrations 一字节没动。"""
    for path, digest in FINGERPRINT_AT_IMPORT.items():
        assert _sha(path) == digest, path
    assert TEXT_AT_IMPORT == OBSERVABILITY.read_text(encoding="utf-8")
    strays = list((REPO / "tests").glob("r533_shadow_*.py")) + list(REPO.glob("r533_shadow_*.py"))
    assert not strays, strays


def test_z9c_the_live_bindings_are_the_original_objects() -> None:
    """反证窗退出后活模块那两枚把手身份必须没被换过（R466 记的那一笔）。"""
    for name, original in ORIGINAL_BINDINGS.items():
        assert getattr(observability, name) is original, name
