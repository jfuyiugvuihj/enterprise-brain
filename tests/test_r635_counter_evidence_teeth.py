# -*- coding: utf-8 -*-
"""R635 判据④ —— 反证刀：把「整本观测面的坐标治理」钝掉，看那把放宽的尺认不认得出。

## 口径（沿用 R524 / R526 / R533 / R630 那一套，不另立规矩）

- 🔴 仓里一字节都不改。摘刀全在**内存影子**里做：源文在 import 那一刻抄进内存，锚点那枚目标的
  源文件按 overrides 递影子，再交给**在册那把尺本身**（``r630.surface_shape_violations`` /
  ``r630.surface_roster_offenders``），刀口与牙共用一枚代码，不留「刀有牙、钉没牙」的缝。
  每把刀进刀前后各核一次被跟踪文件的 sha256，末了总清点。
- 每把刀都带**正控**：同一套机械不摘刀先跑一遍，读数必须先「零违规」。
- 本件不写任何字面坐标：伪造的坐标全部在运行时由 AST 现取的行号拼出来，所以弹药也进不了
  源文自扫——形状尺照样咬得住，而纸面自己一枚坐标都没抄。

## 刀的清单

| 刀 | 摘掉的那一格 | 预期咬住它的牙 |
|----|--------------|----------------|
| K1 | 一枚锚点退回行号坐标，且**漂一行** | 源文整本那支：不许抄坐标 |
| K2 | 一枚锚点退回行号坐标，且**抄对了行号** | 同一支：按形状失败，不按准确性失败 |
| K3 | 一枚锚点的目标符号从它自己的文件里被删走 | 锚点必须真解析得到那支 |
| K4 | 一枚锚点的目标符号被改名 | 同一支（牙认的是符号名，不是文件名） |
| K5 | 一枚锚点把文件换成另一枚真文件（符号不在那儿） | 同一支（跨文件张冠李戴） |
| K6 | 派生的桥话读数改成手写常量（错数字／英文词两形） | 放宽到整本名册那把枚数尺 |
| K7 | 手写枚数躲进一本不随回执对外的名册格子 | 名册整本那支——在册旧输入（只看回执）扫不到 |
| K8 | 一枚坐标只出现在注释里（散文全干净） | 源文整本那支——R630 只量那一格时的盲区 |
| K9 | 派生读数换成「今天抄对了」的手写常量，再让名册长一档 | 枚数尺的派生同判那支（不是文本出现即可） |
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import test_r526_slot_caliber_closure as r526
import test_r630_first_token_pointer_is_derived as r630
from app.api.v1 import observability

REPO = r630.REPO
OBSERVABILITY = r630.OBSERVABILITY
BOOK = "SLO_BLOCKERS"
CELL = "export_leg_has_no_stage"
CELL_REL = "app/common/stage_timing.py"
CELL_SYMBOL = "TOOL_TO_STAGE"
#: 桥话那枚派生读数的把手：手写常量伪装的就是它交回的句子。
NOTE_KEY = "model_budget_tier"

#: 派工词判据① 那枚坐标形状，本件自扫时同样拿它量自己（伪装的坐标只在运行时拼出来）。
TICKET_SHAPE = re.compile(r"[A-Za-z_/]+\.py:[0-9]+")

#: 手写枚数的两种伪装（英文词 / 对不上派生的数字），运行时才喂进影子，不落纸面形状。
HAND_WRITTEN_WORD = "not one-to-one: six budget tiers are named by no lane"
HAND_WRITTEN_DIGIT = "not one-to-one: %s budget tiers of the roster are named by no lane"

#: 影子注入用的那一格：名册里有、回执里没有，专门用来量「只扫对外那半把尺」的盲区。
SHADOW_CELL = "shadow_cell_that_never_reaches_the_receipt"

_RUN: set[str] = set()
_BITTEN: set[str] = set()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


TRACKED = (
    OBSERVABILITY,
    REPO / "tests" / "test_r630_first_token_pointer_is_derived.py",
    REPO / "tests" / "test_r630_counter_evidence_teeth.py",
    REPO / "tests" / "test_r635_surface_pointers_are_derived.py",
    REPO / "tests" / "test_r533_bridge_note_is_derived.py",
    REPO / "tests" / "test_r526_slot_caliber_closure.py",
    REPO / "tests" / "test_r105_slo_contract.py",
    REPO / "docs" / "api" / "contract-v1.md",
    REPO / "app" / "common" / "stage_timing.py",
    REPO / "app" / "common" / "performance.py",
    REPO / "app" / "common" / "model_budget.py",
    REPO / "app" / "agents" / "contracts.py",
    REPO / "app" / "agents" / "nodes.py",
    REPO / "app" / "agents" / "orchestrator.py",
    REPO / "app" / "api" / "v1" / "chat.py",
    REPO / "app" / "trace" / "spans.py",
    REPO / "app" / "storage" / "persistence.py",
)
FINGERPRINT_AT_IMPORT = {path: _sha(path) for path in TRACKED}
TEXT_AT_IMPORT = OBSERVABILITY.read_text(encoding="utf-8")


# ==================== 机械：行号一律 AST 现取，本件不写任何字面坐标 ====================


def definition_node(rel: str, dotted: str) -> ast.stmt:
    """锚点目标符号在源文件里的那枚定义节点（行号由它现取，不抄第二份）。"""
    tree = ast.parse(r630.module_source(rel))
    head, rest = dotted.split(".")[0], dotted.split(".")[1:]
    for node in r630._children(tree):
        if head in r630._defined_names(node):
            if not rest:
                return node
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                for inner in r630._children(node):
                    if rest[0] in r630._defined_names(inner):
                        return inner
    raise AssertionError("定义节点取不到：%s::%s" % (rel, dotted))


def coordinate(rel: str, dotted: str, drift: int = 0) -> str:
    """现场拼出一枚「文件冒号行号」：drift 用来把那枚真行号改漂。"""
    node = definition_node(rel, dotted)
    return "%s%s%s" % (rel, chr(58), node.lineno + drift)


def blockers_from(text: str) -> dict[str, str]:
    """从（影子）源文里现取名册整本：刀改的是这段，牙读的也是这段。"""
    for node in ast.parse(text).body:
        targets = (
            [node.target]
            if isinstance(node, ast.AnnAssign)
            else list(node.targets)
            if isinstance(node, ast.Assign)
            else []
        )
        if not any(isinstance(t, ast.Name) and t.id == BOOK for t in targets):
            continue
        return {
            str(ast.literal_eval(key)): str(ast.literal_eval(value))
            for key, value in zip(node.value.keys, node.value.values)
        }
    raise AssertionError("源文里取不到名册整本，本件的取段前提变了")


def edited(text: str, needle: str, replacement: str) -> str:
    """锚点唯一才许改：命中零次或多次都当场拒（不唯一的刀等于没动东西）。"""
    hits = text.count(needle)
    assert hits == 1, "锚点命中 %d 次 ⇒ 这枚反证是空的或危险的" % hits
    return text.replace(needle, replacement, 1)


def source_of(edit) -> str:
    """把一枚摘刀作用在内存影子上；盘上一个字节不动，模块也不 reload。"""
    shadow = edit(TEXT_AT_IMPORT)
    ast.parse(shadow)
    assert shadow != TEXT_AT_IMPORT, "摘刀没作用到东西上"
    return shadow


def verdicts(source: str | None = None, overrides=None, book=None, payload=None) -> list[str]:
    """一把抓：在册那把放宽的尺原样上，违规清单交回（正控必须是空表）。"""
    return r630.surface_shape_violations(
        source=source if source is not None else TEXT_AT_IMPORT,
        book=book,
        payload=payload,
        overrides=overrides,
    )


def bite(name: str, bad: list[str]) -> list[str]:
    _RUN.add(name)
    if bad:
        _BITTEN.add(name)
    return bad


# ==================== 正控 ====================


def test_the_same_machinery_with_no_edit_reports_nothing() -> None:
    """正控前置：真源文、真名册、真回执在放宽的尺上必须零违规，否则后面的红什么都量不出。"""
    assert verdicts() == []
    assert r630.surface_roster_offenders() == []
    assert blockers_from(TEXT_AT_IMPORT)[CELL] == getattr(observability, BOOK)[CELL]
    moved = [p.name for p, digest in FINGERPRINT_AT_IMPORT.items() if _sha(p) != digest]
    assert moved == [], moved


# ==================== 判据④ 的三把主刀 ====================


def test_k1_a_coordinate_drifted_by_one_line_reds_the_ruler() -> None:
    """K1：把一枚锚点退回行号坐标并改漂一行，源文整本与名册那一格同时红。"""
    anchor = "%s::%s" % (CELL_REL, CELL_SYMBOL)
    shadow = source_of(lambda text: edited(text, anchor, coordinate(CELL_REL, CELL_SYMBOL, drift=1)))
    bad = bite("K1_coordinate_drifted_by_one", verdicts(source=shadow, book=blockers_from(shadow)))
    assert any("抄了行号坐标" in row for row in bad), bad


def test_k2_a_correct_line_number_is_still_a_coordinate() -> None:
    """K2：行号抄对了也红——这把尺按形状失败，不按准确性失败，所以没人能靠对齐行号蒙过去。"""
    anchor = "%s::%s" % (CELL_REL, CELL_SYMBOL)
    exact = coordinate(CELL_REL, CELL_SYMBOL, drift=0)
    assert exact.split(chr(58))[-1].isdigit()
    shadow = source_of(lambda text: edited(text, anchor, exact))
    bad = bite("K2_correct_coordinate_still_red", verdicts(source=shadow, book=blockers_from(shadow)))
    assert any("抄了行号坐标" in row for row in bad), bad
    assert not any("解析不到" in row for row in bad), bad


def test_k3_deleting_the_target_symbol_reds_the_anchor_leg() -> None:
    """K3：锚点的目标符号被从它自己的文件里删走（内存影子），锚点腿必须红。"""
    node = definition_node(CELL_REL, CELL_SYMBOL)
    lines = r630.module_source(CELL_REL).splitlines(keepends=True)
    del lines[node.lineno - 1 : node.end_lineno]
    bad = bite(
        "K3_target_symbol_deleted",
        verdicts(overrides={CELL_REL: "".join(lines)}),
    )
    assert any("解析不到" in row for row in bad), bad
    assert _sha(REPO / CELL_REL) == FINGERPRINT_AT_IMPORT[REPO / CELL_REL]


def test_k4_renaming_the_target_symbol_reds_the_anchor_leg() -> None:
    """K4：同一枚符号被改名（文件还在、行还在），牙认的是符号名，照样红。"""
    node = definition_node(CELL_REL, CELL_SYMBOL)
    lines = r630.module_source(CELL_REL).splitlines(keepends=True)
    lines[node.lineno - 1] = lines[node.lineno - 1].replace(CELL_SYMBOL, CELL_SYMBOL + "_moved", 1)
    shadow_target = "".join(lines)
    assert "%s_moved" % CELL_SYMBOL in shadow_target
    bad = bite("K4_target_symbol_renamed", verdicts(overrides={CELL_REL: shadow_target}))
    assert any("解析不到" in row for row in bad), bad


def test_k5_an_anchor_naming_the_wrong_file_reds_the_anchor_leg() -> None:
    """K5：把锚点的文件换成另一枚真文件（符号不在那儿）：跨文件张冠李戴必须红。"""
    anchor = "%s::%s" % (CELL_REL, CELL_SYMBOL)
    shadow = source_of(lambda text: edited(text, anchor, "app/trace/spans.py::%s" % CELL_SYMBOL))
    bad = bite("K5_anchor_names_the_wrong_file", verdicts(source=shadow, book=blockers_from(shadow)))
    assert any("解析不到" in row and "spans.py" in row for row in bad), bad


def test_k6_a_hand_typed_constant_for_the_derived_note_reds_the_book(monkeypatch) -> None:
    """K6：派生出来的桥话改成手写常量，两种伪装（错数字／英文词）都得被整本那把枚数尺咬住。"""
    offenders: list[str] = []
    for note in (HAND_WRITTEN_WORD, HAND_WRITTEN_DIGIT % "6"):
        monkeypatch.setattr(observability, "_slo_bridge_note", lambda *_a, **_k: note)
        offenders += r630.surface_roster_offenders()
    bite("K6_derived_note_becomes_constant", offenders)
    assert offenders, "手写常量躲过了放宽后的枚数尺"
    assert _sha(OBSERVABILITY) == FINGERPRINT_AT_IMPORT[OBSERVABILITY]


def test_k7_a_hand_typed_count_hiding_in_a_cell_that_never_ships(monkeypatch) -> None:
    """K7：手写枚数躲进一本没对外的名册格子 —— 只喂回执那半把尺扫不到，放宽后才咬得住。"""
    assert SHADOW_CELL not in getattr(observability, BOOK), "影子那一格的名字撞上了真名册"
    monkeypatch.setitem(getattr(observability, BOOK), SHADOW_CELL, HAND_WRITTEN_WORD)
    published = {str(node.get("code")) for node in _blocker_nodes(observability.slo_readout())}
    assert SHADOW_CELL not in published, "这一格其实对外了：那本盲区并不存在，本刀的前提变了"
    narrow = r630.roster_count_offenders(observability.slo_readout())
    assert narrow == [], narrow
    offenders = bite("K7_hand_count_in_unpublished_cell", r630.surface_roster_offenders())
    assert offenders, "躲进未对外格子的手写枚数没人管：那把尺白放宽了"


def _blocker_nodes(node) -> list[dict]:
    found: list[dict] = []
    if isinstance(node, dict):
        if "code" in node and "detail" in node:
            found.append(node)
        for value in node.values():
            found += _blocker_nodes(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            found += _blocker_nodes(value)
    return found


def test_k8_a_coordinate_that_only_lives_in_a_comment() -> None:
    """K8：坐标只出现在注释里（每一格散文都干净），源文整本那一支必须仍然红。"""
    forged = coordinate(CELL_REL, CELL_SYMBOL, drift=1)
    shadow = TEXT_AT_IMPORT + "\n# 手抄的一枚旧坐标：%s\n" % forged
    ast.parse(shadow)
    assert blockers_from(shadow) == getattr(observability, BOOK), "摘刀把散文也动了，这支不再是注释刀"
    bad = bite("K8_coordinate_only_in_a_comment", verdicts(source=shadow))
    assert bad and all(row.startswith("source ") for row in bad), bad
    assert any("抄了行号坐标" in row for row in bad), bad


def test_k9_a_right_valued_constant_dies_when_the_roster_grows(monkeypatch) -> None:
    """K9：派生读数换成「今天恰好抄对」的手写常量，形状尺量不到，但名册一长它必须当场死。

    这一支才是「不许用文本里出现即可蒙过去」的硬面：常量与真源同值时谁都看不出来，
    名册一动，抄来的那句就对不上现取的派生读数了。
    """
    derived_now = observability.slo_units()[NOTE_KEY]["bridge_note"]
    monkeypatch.setattr(observability, "_slo_bridge_note", lambda *_a, **_k: derived_now)
    assert r630.surface_roster_offenders() == [], "正控：抄得对的时候这一句本来就是干净的"
    assert r630.derived_reading_offenders() == [], "正控：重建那一条腿在没动名册时必须先绿"
    with monkeypatch.context() as box:
        box.setattr(r630.r533.contracts, "ModelTier", r630.r533.grown_model_tier(r630.r533.SHADOW_TIER))
        grown = observability.slo_readout()
        legacy = r630.roster_count_offenders(grown)
        rebuild = r630.derived_reading_offenders(grown)
        offenders = bite("K9_constant_note_vs_a_grown_roster", r630.surface_roster_offenders(payload=grown))
    assert offenders, "名册长了这一句还一样：说明它压根没被读，牙是空的"
    assert legacy == [], ("在册那把旧尺今天也咬住了这一形：本刀的红就不是新腿的贡献，读数=%s" % legacy)
    assert rebuild, "红不来自重建同判那一条腿：本刀的前提变了"


# ==================== 总清点 ====================


def test_every_knife_ran_and_bit_and_nothing_on_disk_moved() -> None:
    """没真摘过的刀、没真咬红的钉，当场拒；跟踪里的原件一枚字节都没动。"""
    expected = {
        "K1_coordinate_drifted_by_one",
        "K2_correct_coordinate_still_red",
        "K3_target_symbol_deleted",
        "K4_target_symbol_renamed",
        "K5_anchor_names_the_wrong_file",
        "K6_derived_note_becomes_constant",
        "K7_hand_count_in_unpublished_cell",
        "K8_coordinate_only_in_a_comment",
        "K9_constant_note_vs_a_grown_roster",
    }
    assert _RUN == expected, sorted(_RUN ^ expected)
    assert _BITTEN == expected, sorted(expected - _BITTEN)
    moved = [path.name for path, digest in FINGERPRINT_AT_IMPORT.items() if _sha(path) != digest]
    assert moved == [], "摘刀动到了盘上：%s" % moved


def test_the_write_domain_files_match_their_import_time_digests() -> None:
    """判据④ 的越域核对：本单被允许改的四类文件，摘刀前后同判（其余一字节都不该动）。"""
    allowed = (
        OBSERVABILITY,
        REPO / "tests" / "test_r630_first_token_pointer_is_derived.py",
    )
    for path in allowed:
        assert path in TRACKED, "%s 不在跟踪台账里" % path.name
        assert _sha(path) == FINGERPRINT_AT_IMPORT[path], path.name


def test_this_file_itself_copies_no_coordinate() -> None:
    """本件自扫：一枚坐标形状都没有（伪造的坐标全部运行时拼），也不藏量级与手写枚数。"""
    source = Path(__file__).resolve().read_text(encoding="utf-8")
    assert r630.LINE_ANCHOR.findall(source) == []
    assert TICKET_SHAPE.findall(source) == []
    assert r526.find_magnitudes(source) == []
    for rel, dotted in r630.WIDE_ANCHOR.findall(source):
        assert r630.anchor_resolves(rel, dotted), "%s::%s" % (rel, dotted)
