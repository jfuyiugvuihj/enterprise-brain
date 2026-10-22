# -*- coding: utf-8 -*-
"""R630 判据③ —— 反证刀：把「那句落点话派生化」这一格钝掉，看牙认不认得出。

## 口径（沿用 R524 / R526 / R533 那一套，不另立规矩）

- 🔴 仓里一字节都不改。摘刀全部在**内存影子**里做：observability.py 的源文在 import 那一刻抄进
  内存，按现取的那一格的行区间换掉，再交给**在册那把尺本身**（``r630.prose_shape_violations`` /
  ``r630.chain_violations`` / ``r630.roster_count_offenders``），刀口与牙共用一枚代码，不留
  「刀有牙、钉没牙」的缝。每把刀进刀前后各核一次被跟踪文件的 sha256，末了总清点。
- 每把刀都带**正控**：同一套机械不摘刀先跑一遍，读数必须先「零违规」，不然「红」只是它本来就红。
- 判据③ 要的「按形状失败」在这儿是可量的：把 `first_token_at` 的落点从名册里摘走（K5）、往名册
  影子注一档（正件那一枚用例），句子不改就红；**只把一枚数字换成另一枚数字**也照样红（K1/K6/K7），
  所以这不是枚数钉。

## 刀的清单

| 刀 | 摘掉的那一格 | 预期咬住它的牙 |
|----|--------------|----------------|
| K0 | 整格退回基点那句硬编（把落点说给 store，还带着三枚行号） | 形状尺：抄坐标一支 + 被冤枉的锚点 + 断链 |
| K1 | 写 INSERT 那一腿改指 store 的真符号（符号解析得到，文件却不带这一格） | 形状尺的「锚点必须真带这一格」一支 + 断链 |
| K2 | 句尾再补一枚行号坐标 | 形状尺的「不许抄坐标」一支 |
| K3 | 把「账本不经手」那一支改口成「账本经手」 | 形状尺的「只点名必须配否定词」一支 |
| K4 | 整条落盘那一腿被删掉 | 链路钉：真链路的文件没被点名 |
| K5 | 名册里把这枚列摘走（派生源搬家，文案一字不动） | 形状尺的 CLAIMS 一支（现读与声称对不上） |
| K6 | 桥话退回手写枚数（英文词与错数字两种写法） | 放宽到整本回执那把尺 |
| K7 | 手写枚数躲进另一格散文（在册那把旧尺扫不到的那一类） | 同一把放宽的尺——本单补的正是这一格盲区 |
"""
from __future__ import annotations

import ast
import copy
import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

import test_r630_first_token_pointer_is_derived as r630
from app.api.v1 import observability
from app.storage import persistence

REPO = r630.REPO
OBSERVABILITY = r630.OBSERVABILITY
FIELD = r630.FIELD
CELL = r630.CELL

#: 🔴 两枚记号在源文里被劈开写：常量本身不能等于记号，否则「弹药区」会被算成这两行定义自己。
FORGERY_START = "# --- 伪造弹药" + "（只喂内存里的影子副本，永不落盘，也排除在本件自扫之外）---"
FORGERY_END = "# --- 弹药" + "结束 ---"

# --- 伪造弹药（只喂内存里的影子副本，永不落盘，也排除在本件自扫之外）---
#: 基点那三行原文：抄了三枚行号，还把落点说给一枚压根不带这一格的文件。
STALE_ENTRY = (
    '    "%s": (\n' % CELL
    + '        "first_token_at is recorded on a model span (app/trace/spans.py:174) and persisted "\n'
    + '        "(app/trace/store.py:259), but app/common/stage_timing.py:330-345 never reads it into "\n'
    + '        "a sample, so 首屏 is computable per trace and not from the in-process ledger."\n'
)
CREDIT_THE_STORE = (
    "``app/storage/persistence.py::PostgresPersistenceAdapter.upsert`` writes it",
    "``app/trace/store.py::TraceStore.record_event`` writes it",
)
ADD_A_COORDINATE = ("in-process ledger.", "in-process ledger (app/storage/persistence.py:407).")
FLIP_THE_LEDGER = (
    "ledger samples yet its ``samples_from_span_payload`` builds a ``StageSample`` with no field "
    "for it",
    "ledger samples and its ``samples_from_span_payload`` builds a ``StageSample`` that carries "
    "the stamp",
)
DROP_THE_WRITE_LEG = (
    "; ``app/trace/projections.py::project_span`` folds it into the model_calls row, whose "
    "columns are the roster in ``app/trace/schema.py::TRACE_TABLE_COLUMNS``, and "
    "``app/storage/persistence.py::PostgresPersistenceAdapter.upsert`` writes it, taking the "
    "column set from ``app/storage/persistence.py::_TABLES``",
    "; ``app/trace/projections.py::project_span`` folds it into the model_calls row",
)
HAND_TYPED_BRIDGE = (
    "not one-to-one: six of the seven budget tiers belong to no lane at all",
    "not one-to-one: 6 budget tiers of the 7 are named by no lane",
)
HAND_TYPED_COUNT_IN_A_BLOCKER = (
    "first_token_at is not a stage sample: six of the seven budget tiers never reach the ledger."
)
# --- 弹药结束 ---

PROSE_KNIVES = {
    "K1_credited_the_blamed_store": (CREDIT_THE_STORE,),
    "K2_coordinate_sneaks_back": (ADD_A_COORDINATE,),
    "K3_ledger_flipped_to_credited": (FLIP_THE_LEDGER,),
    "K4_write_leg_dropped": (DROP_THE_WRITE_LEG,),
}

ALL_KNIVES = (
    "K0_stale_entry_retyped",
    "K1_credited_the_blamed_store",
    "K2_coordinate_sneaks_back",
    "K3_ledger_flipped_to_credited",
    "K4_write_leg_dropped",
    "K5_roster_loses_the_column",
    "K6_hand_typed_bridge_note",
    "K7_hand_typed_count_hides_elsewhere",
)

#: 总清点台账：每一把刀都必须真跑过、并且真咬红过。
_RUN: set[str] = set()
_BITTEN: set[str] = set()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


TRACKED = (
    OBSERVABILITY,
    REPO / "tests" / "test_r630_first_token_pointer_is_derived.py",
    REPO / "tests" / "test_r533_bridge_note_is_derived.py",
    REPO / "tests" / "test_r526_slot_caliber_closure.py",
    REPO / "tests" / "test_r105_slo_contract.py",
    REPO / "docs" / "api" / "contract-v1.md",
    REPO / "app" / "trace" / "store.py",
    REPO / "app" / "trace" / "schema.py",
    REPO / "app" / "trace" / "projections.py",
    REPO / "app" / "storage" / "persistence.py",
    REPO / "app" / "common" / "stage_timing.py",
)
FINGERPRINT_AT_IMPORT = {path: _sha(path) for path in TRACKED}
#: 摘刀只作用在内存副本上，所以「原件长什么样」必须在 import 那一刻抄下来，不许回头再读盘。
TEXT_AT_IMPORT = OBSERVABILITY.read_text(encoding="utf-8")


# ==================== 机械：现取行区间 + 内存摘刀 ====================


def cell_line_span(text: str) -> tuple[int, int]:
    """那一格在源文里的行区间（现取，本件不写任何行号）：直接拿去切 ``splitlines`` 的下标。"""
    for node in ast.parse(text).body:
        targets = (
            [node.target]
            if isinstance(node, ast.AnnAssign)
            else list(node.targets)
            if isinstance(node, ast.Assign)
            else []
        )
        if not any(
            isinstance(target, ast.Name) and target.id == "SLO_BLOCKERS" for target in targets
        ):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(key, ast.Constant) and key.value == CELL:
                start, stop = key.lineno - 1, value.end_lineno
                lines = text.splitlines(keepends=True)
                assert lines[stop].strip() == "),", "那一格的收口形状变了：%r" % lines[stop]
                return start, stop
    raise AssertionError("源文里找不到那一格，本件的取段前提变了")


def mutated_source() -> str:
    """K0：整格退回基点那句。只在内存里动，盘上一个字节不改。"""
    lines = TEXT_AT_IMPORT.splitlines(keepends=True)
    start, stop = cell_line_span(TEXT_AT_IMPORT)
    rebuilt = "".join(lines[:start]) + STALE_ENTRY + "".join(lines[stop:])
    ast.parse(rebuilt)
    assert rebuilt != TEXT_AT_IMPORT, "摘刀没作用到东西上"
    return rebuilt


def prose_with(edits) -> str:
    """按锚点摘出那一格的影子文案；锚点不唯一当场拒（不唯一的刀等于没动东西）。"""
    prose = r630.cell_prose()
    for needle, replacement in edits:
        hits = prose.count(needle)
        assert hits == 1, "锚点命中 %d 次 ⇒ 这枚反证是空的" % hits
        prose = prose.replace(needle, replacement, 1)
    if edits:
        assert prose != r630.cell_prose(), "摘刀没作用到东西上"
    return prose


def verdicts(prose: str) -> list[str]:
    """一把抓：在册那两把尺同时上，违规清单交回（正控必须是空表）。"""
    return r630.prose_shape_violations(prose) + r630.chain_violations(prose)


def bite(name: str, bad: list[str]) -> list[str]:
    """记账：跑过哪把刀、咬红没咬红，全部留给总清点那一枚用例验收。"""
    _RUN.add(name)
    if bad:
        _BITTEN.add(name)
    return bad


def ammunition_window(source: str) -> tuple[int, int]:
    start = source.index(FORGERY_START)
    return start, source.index(FORGERY_END, start)


# ==================== 正控 ====================


def test_the_same_machinery_with_no_edit_reports_nothing() -> None:
    """正控前置：真句子与真源文在两把尺上都得零违规，否则后面的红什么都量不出。"""
    assert verdicts(prose_with(())) == []
    assert r630.prose_shape_violations(r630.cell_from_source(TEXT_AT_IMPORT)) == []
    assert r630.roster_count_offenders(observability.slo_readout()) == []
    assert _sha(OBSERVABILITY) == FINGERPRINT_AT_IMPORT[OBSERVABILITY]


def test_the_ammunition_really_carries_the_shapes_it_claims_to() -> None:
    """弹药得真会被咬：区内形状先量得出，区外一枚坐标都没有。"""
    source = Path(__file__).resolve().read_text(encoding="utf-8")
    start, stop = ammunition_window(source)
    assert r630.LINE_ANCHOR.findall(source[:start] + source[stop:]) == []
    assert r630.LINE_ANCHOR.findall(source[start:stop]), "弹药区里一枚坐标都没有 ⇒ 这区是空的"
    assert r630.roster_count_offenders({"ammunition": HAND_TYPED_BRIDGE[0]}) != []


# ==================== 刀 ====================


def test_k0_the_stale_entry_retyped_reds_the_ruler() -> None:
    """K0：基点那句（抄坐标 + 把落点说给 store）放回同一格，三形一起红。"""
    stale = r630.cell_from_source(mutated_source())
    assert stale != r630.cell_prose(), "摘出来的句子与在册那句一模一样：刀没动到"
    bad = bite("K0_stale_entry_retyped", verdicts(stale))
    assert any("抄了行号坐标" in row for row in bad), bad
    assert any("app/trace/store.py" in row for row in bad), bad
    assert any("没点名它" in row for row in bad), bad


@pytest.mark.parametrize("name", sorted(PROSE_KNIVES))
def test_prose_knives_red_the_shape_ruler(name) -> None:
    """K1—K4：每把刀只动一形，动的那一形必须被在册那把尺抓出来。"""
    bad = bite(name, verdicts(prose_with(PROSE_KNIVES[name])))
    assert bad, "%s：摘了这一形而尺子没反应" % name


def test_k1_bites_the_carrier_leg_and_not_the_symbol_leg() -> None:
    """K1 的红得来自「那枚文件压根没这一格」，不是来自符号解析不到——否则牙咬错了地方。"""
    assert r630.resolve_symbol("app/trace/store.py", "TraceStore.record_event")
    bad = verdicts(prose_with(PROSE_KNIVES["K1_credited_the_blamed_store"]))
    assert any("经手这一格" in row for row in bad), bad
    assert not any("解析不到" in row for row in bad), bad


def test_k5_moving_the_column_out_of_the_roster_reds_the_prose(monkeypatch) -> None:
    """K5：派生源搬家（名册里摘走这枚列）而文案一字不动 ⇒ 按形状红。"""
    entry = persistence._TABLES["model_calls"]
    cut = replace(entry, columns=tuple(col for col in entry.columns if col != FIELD))
    monkeypatch.setitem(persistence._TABLES, "model_calls", cut)
    assert FIELD not in persistence._TABLES["model_calls"].columns
    bad = bite("K5_roster_loses_the_column", verdicts(r630.cell_prose()))
    assert any("_TABLES" in row for row in bad), bad


def test_k6_a_hand_typed_bridge_note_reds_the_surface_ruler() -> None:
    """K6：桥话退回手写枚数，两种写法（英文词 / 对不上派生的数字）都得被那把放宽的尺咬住。"""
    offenders: list[str] = []
    for note in HAND_TYPED_BRIDGE:
        clone = copy.deepcopy(observability.slo_units())
        clone[r630.r533.BUDGET_UNIT]["bridge_note"] = note
        offenders += r630.roster_count_offenders(clone)
    bite("K6_hand_typed_bridge_note", offenders)
    assert offenders, "手写枚数躲过了整本回执那把尺"


def test_k7_a_hand_typed_count_hiding_in_another_cell(monkeypatch) -> None:
    """K7：手写枚数躲进在册旧尺扫不到的另一格散文 —— 本单补的正是这一格盲区。"""
    assert r630.roster_count_offenders(observability.slo_readout()) == [], "正控：真盘面必须干净"
    monkeypatch.setitem(observability.SLO_BLOCKERS, CELL, HAND_TYPED_COUNT_IN_A_BLOCKER)
    offenders = bite("K7_hand_typed_count_hides_elsewhere",
                     r630.roster_count_offenders(observability.slo_readout()))
    assert offenders, "躲在 blocker 里的手写枚数没人管：那把尺白放宽了"


# ==================== 总清点 ====================


def test_every_knife_ran_and_bit_and_nothing_on_disk_moved() -> None:
    """没真摘过的刀、没真咬红的钉，当场拒；跟踪里的原件一枚字节都没动。"""
    missing = sorted(set(ALL_KNIVES) - _RUN)
    extra = sorted(_RUN - set(ALL_KNIVES))
    assert not missing and not extra, (missing, extra)
    assert _BITTEN == set(ALL_KNIVES), sorted(set(ALL_KNIVES) - _BITTEN)
    moved = [path.name for path, digest in FINGERPRINT_AT_IMPORT.items() if _sha(path) != digest]
    assert moved == [], "摘刀动到了盘上：%s" % moved


def test_this_file_itself_copies_no_coordinate_outside_the_ammunition() -> None:
    """本件自扫：弹药区之外一枚行号坐标都不许有（钉自己先守住自己立的规矩）。"""
    source = Path(__file__).resolve().read_text(encoding="utf-8")
    start, stop = ammunition_window(source)
    assert r630.LINE_ANCHOR.findall(source[:start] + source[stop:]) == []
