# -*- coding: utf-8 -*-
r"""R653 · 剩下六枚「契约逐字节前缀」钉接到 R645 那一本具名差异账上（尺不新造，只接）。

病（总控 10-04 23:1x 现跑，不是转述）：`497ac38`（并树 R630）把契约 blockers 表里
`first_token_not_a_stage_sample` 那一行的两枚手抄行号换成了运行时派生锚。那一格改得对 —— 对外契约里
烤死过期坐标正是本仓这两天在治的病；错的是六枚常驻钉各抄一把自己的基点、又不许有人把那一格登记在册，
于是「文末之前的每一个字都不许动」从今天起不可能绿（28d1ea4 上亲跑＝6 failed / 315 passed / 1 xfailed）。
R645 已经把 r354 那两枚换成薄壳，尺与账一起住在 `tests/test_r645_contract_difference_ledger.py`；
本单把剩下六枚接到**同一本账**上，不新造第二把尺。

治法（只这一条，三条绕路一律不走）：
  ① 六枚钉摘掉自家的基点、契约路径、`git show` 把手、对文本变量做的 `startswith`，只走共用入口
     `assert_history_matches_ledger()`；每件留一枚本地薄壳，可达面一律由 AST 现查（判据②）。
  ② 每枚钉保住自己那两条与位置无关的判据：本单那一节在追加段里恰一枚、`## ` 节数只增不减。
  ③ 账的**形状尺**一字不动：仍只收「手抄坐标 → `文件::符号` 派生锚」；六枚读到的是**同一格**
     （R630 那一行），所以走同一枚登记，`EXPECTED_DIFFERENCES_TODAY` 仍是等号 1，没有第二枚、没有豁免。
  不走的路：不把钉改成结构级判据（`tests/test_r397_read_legs_refuse_a_missing_table.py` 09-28 被那样
     改口过一次，强度降了）；不前移尺的基点、不清账、不把枚数门写成阈值或区间、不 skip／xfail；
     契约一字节不动；`tests/test_r397_*` 与 `tests/test_r523_cached_count_lands.py` 那两枚今天绿的形状不同，不收进来。

四把刀（一律只拿 `tmp_path` 影子端判，**不开 overlay 窗**，盘上契约进出各取一次 sha256 断言相等）：
刀① 账外动一个标点 ⇒ 六枚同时红，且红句**逐枚一字不差**（判据③：同一笔账只许给同一句话），
   红句里点名现派生的字符位与行号；
刀② 逐枚一把自己的刀（判据⑤）：改动点逐枚不同，每枚都得为那一改红；
刀③ 把今天派生出来的位置抄回字面量 ⇒ 反手抄扫描当场点名（拿改过的源码文本现证它咬得动，不写盘）；
刀④ 谁偷偷再造一把尺（自家基点／自家枚数门／自己攒一格登记）⇒ 点名红。
"""
from __future__ import annotations

import ast
import importlib
import inspect
import re
import sys
from pathlib import Path

import pytest

from tests import test_r645_contract_difference_ledger as contract_ledger

REPO = Path(__file__).resolve().parents[1]
#: 六枚钉逐枚点名：件（仓内相对路径）:: 钉的名。基点一律不再抄在这里 —— 尺只有一把。
NAILS: tuple = (
    ("tests/test_r340_replayable_alerts_open.py", "test_the_contract_appends_one_section_and_deletes_nothing"),
    ("tests/test_r366_inbox_keeps_its_legs_when_the_alert_store_refuses.py",
     "test_the_contract_appends_one_section_and_deletes_nothing"),
    ("tests/test_r367_gate_shape_pins.py", "test_the_contract_appends_one_section_and_deletes_nothing"),
    ("tests/test_r373_the_two_remaining_legs_answer_absence.py",
     "test_the_contract_appends_one_section_and_deletes_nothing"),
    ("tests/test_r388_read_leg_answers_absence.py", "test_the_contract_appends_one_section_and_deletes_nothing"),
    ("tests/test_r414_b_terminal_data_filename.py", "test_the_registration_is_a_tail_append_over_the_base"),
)
NAIL_IDS = ("r340", "r366", "r367", "r373", "r388", "r414_b")

#: 薄壳的名字、它必须落到的共用入口、以及各件拿账本的那一枚把手（与 R645 给 r354 定的同一套名字）。
SHARED_RULER = "_contract_history_account"
SHARED_ENTRY_POINT = "assert_history_matches_ledger"
LEDGER_HANDLE = "contract_ledger"

#: 各件里「第二把尺」的把手：六枚钉的可达面一枚都不许沾（判据② 的硬话）。
FORBIDDEN_HANDLES = frozenset({
    "BASE", "CONTRACT", "_git_show", "_base_file", "_git", "_as_blob_text", "_source", "_contract",
    "_own_contract_section", "_normalize_eol", "_first_difference", "subprocess",
})

#: 账外那一改只在标点里挑：动一个标点，既不改语义也不碰登记过的每一格。
EDITABLE_PUNCTUATION = ";:,.()[]{}|<>#*_-~!?"
#: 手抄偏移量长得什么样：五位以上的裸数字（与 R645 同一把尺，不放宽）。
BARE_NUMBER = re.compile(r"(?<![\w.])\d{5,}(?![\w.])")


# ---------------------------------------------------------------------- 现跑与现读


def _module_of(relative: str):
    """取那枚钉所在的模块本身：pytest 已按顶层名导过就复用那一份，否则按 `tests.` 点名导。"""
    stem = Path(relative).name[: -len(".py")]
    for name in (stem, "tests." + stem):
        module = sys.modules.get(name)
        if module is not None:
            return module
    return importlib.import_module("tests." + stem)


def _run_nail(relative: str, nail: str) -> str:
    """现跑一枚钉：绿回空串，红回那句红话；别的异常不吞，当场炸给总控看。"""
    try:
        getattr(_module_of(relative), nail)()
    except AssertionError as error:
        return str(error) or "<红句为空：这枚断言没带话>"
    return ""


def _run_six() -> dict:
    return {
        "%s::%s" % (Path(relative).name, nail): _run_nail(relative, nail) for relative, nail in NAILS
    }


def _red(outcome: dict) -> dict:
    return {name: message for name, message in outcome.items() if message}


def _today_positions() -> set:
    """今天从账上派生出来的每一个数字：字符位、行号、两侧长度。它们只许现派生，不许被抄进钉。"""
    account = contract_ledger.assert_history_matches_ledger()
    numbers: set = {len(account.base_text), len(account.current_text), len(account.expected_prefix)}
    for record in account.records:
        numbers |= {
            record.base_start, record.base_end, record.current_start, record.current_end,
            record.base_line, record.current_line,
        }
    return numbers


def _off_ledger_limit() -> int:
    """第一格登记在现盘上的起点：它之前铁定在差异账之外（刀① ② 的落点尺）。"""
    account = contract_ledger.assert_history_matches_ledger()
    assert account.records, "账上一枚登记都没有：那就没有「账外」这一说，刀无从落点"
    return account.records[0].current_start


def _punctuation_positions() -> list:
    """现派生「账外那一段里可改的标点」落在哪几枚字符位：一把尺子，六把刀共用，本件不抄任何数字。"""
    limit = _off_ledger_limit()
    text = contract_ledger.current_contract_text()
    return [index for index, char in enumerate(text[:limit]) if char in EDITABLE_PUNCTUATION]


def _off_ledger_punctuation_edit(order: int):
    """派生「账外动第 order 枚标点」的改写：把那一枚标点重写两枚（长度只加一个字符）。

    🔴 改动点取自「第一格登记之前」那一段 ⇒ 铁定在差异账之外；长度只增不减 ⇒ 这一刀只可能咬
    「账外被动过」那一格，撞不到「契约没长东西」，更撞不到枚数门与形状尺。
    """
    def mutate(text: str) -> str:
        hits = _punctuation_positions()
        assert len(hits) > order, "历史区里可改的标点不够分给这几把刀：%d 枚" % len(hits)
        at = hits[order]
        return text[:at + 1] + text[at] + text[at + 1:]

    return mutate


# ---------------------------------------------------------------------- 反手抄扫描


def _reach_defs(tree: ast.Module, entry: str) -> list:
    """这枚钉的可达面（本文件内的顶层函数定义），逐枚点名用。"""
    defs = contract_ledger._function_defs(tree)
    reach = contract_ledger._reachable(tree, entry)
    return [defs[name] for name in sorted(reach["local"]) if name in defs]


def _hand_copy_problems(nodes: list, numbers: set) -> list:
    """可达面上有没有活着的手抄位置：数值常量与字符串里的数字两路都扫。"""
    problems: list[str] = []
    for node in nodes:
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Constant):
                continue
            value = sub.value
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)) and abs(value) >= 10000:
                problems.append("可达面上出现一枚五位以上的数值常量 %r：位置只许现派生" % value)
            if not isinstance(value, str):
                continue
            bare = BARE_NUMBER.findall(value)
            if bare:
                problems.append("可达面上的字里出现 %d 枚五位以上裸数字：%s" % (len(bare), sorted(set(bare))))
            copied = sorted(number for number in numbers if str(number) in value)
            if copied:
                problems.append("可达面把今天派生出来的位置抄成了字面量：%s" % copied)
    return problems


def _second_ruler_problems(source_text: str) -> list:
    """这一件里有没有第二把尺：自家基点／自家枚数门／自己攒一格登记。"""
    problems: list[str] = []
    tree = ast.parse(source_text)
    for constant in ("FROZEN_BASE", "EXPECTED_DIFFERENCES_TODAY", "CONTRACT_DIFFERENCES"):
        got = contract_ledger._literal_assignments(tree, constant)
        if got:
            problems.append(
                "%s 在本件里被赋值 %d 次：这本账与它的基点、枚数门只许住在 R645 那一件里" % (constant, len(got))
            )
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Difference":
            problems.append("本件自己攒了一格 Difference 登记：六枚读到的是同一格，登记归 R645 那一本账")
    return problems


def _injected_source(relative: str, nail: str, literal: str) -> str:
    """把一枚字面量塞进那枚钉的第一行（只在内存里，不写盘）：用来现证扫描器咬得动。"""
    source = (REPO / relative).read_text(encoding="utf-8")
    start = source.index("def %s():" % nail)
    body = source.index("\n", start) + 1
    return source[:body] + "    probe = %s\n" % literal + source[body:]


# ---------------------------------------------------------------------- 常驻牙：一本账、六枚钉


def test_the_book_still_holds_exactly_one_named_difference():
    """正控：六枚读到的是**同一格**（R630 那一行），走同一枚登记，枚数门仍是等号 1。

    🔴 这一枚就是「不许把门改成 6、不许改成区间」那一格的牙：六枚钉登记的如果本来就是同一格，
    账上的枚数不会因为把六枚接进来而变；真变成两枚，这一枚当场红。
    """
    account = contract_ledger.assert_history_matches_ledger()

    assert len(account.records) == len(contract_ledger.CONTRACT_DIFFERENCES) == 1
    assert contract_ledger.EXPECTED_DIFFERENCES_TODAY == 1, "枚数门被挪过了：那不是我这一单的口径"
    assert len(account.records) == contract_ledger.EXPECTED_DIFFERENCES_TODAY
    assert [record.ticket for record in account.records] == ["R630"], account.records
    assert [entry.ticket for entry in contract_ledger.CONTRACT_DIFFERENCES] == ["R630"]
    assert contract_ledger._literal_pin_problems(contract_ledger._own_source()) == []


def test_the_six_nails_are_green_on_the_disk_today():
    """判据① 的正控：六枚钉同名转绿，且是现跑现盘（不是引用谁的旧账）。"""
    red = _red(_run_six())

    assert red == {}, sorted(red)


def test_the_six_nails_read_this_same_book():
    """判据②：六枚钉的可达面逐枚 AST 现查 —— 只走共用入口，自家的把手一枚不许留。"""
    for relative, nail in NAILS:
        tree = contract_ledger._parse(relative)
        defs = contract_ledger._function_defs(tree)
        shellers = contract_ledger._shells_out(tree)

        assert nail in defs, "%s 里那枚钉不见了：%s" % (relative, nail)
        reach = contract_ledger._reachable(tree, nail)
        assert SHARED_RULER in reach["local"], (relative, sorted(reach["local"]))
        assert SHARED_ENTRY_POINT in reach["called"], (relative, sorted(reach["called"]))
        hijacked = sorted((reach["local"] | reach["loads"]) & FORBIDDEN_HANDLES)
        assert not hijacked, "%s 还留着自家的把手：%s" % (relative, hijacked)
        assert not (reach["local"] & shellers), (relative, sorted(reach["local"] & shellers))
        assert "show" not in reach["strings"], relative
        assert not [text for text in reach["strings"] if contract_ledger.CONTRACT_REL in text], relative
        assert not [text for text in reach["strings"] if text == contract_ledger.FROZEN_BASE], relative
        private_prefix = sorted(reach["prefix_receivers"] & contract_ledger.TEXT_NAMES)
        assert not private_prefix, "%s 还在自己做前缀等式：%s" % (relative, private_prefix)
        assert list(inspect.signature(getattr(_module_of(relative), nail)).parameters) == [], (relative, nail)


def test_the_ledger_handle_is_one_object_in_all_six_files():
    """同名两副面孔就是假绿的入口：刀架在这一份上、钉读那一副看不见（R645 同一条病，六枚一起防）。"""
    for relative, _nail in NAILS:
        assert getattr(_module_of(relative), LEDGER_HANDLE, None) is contract_ledger, relative


def test_the_six_files_ship_no_second_ruler():
    """判据③ 的封口：六枚件里不许出现自家基点、自家枚数门、自家登记 —— 尺与账只有 R645 那一份。"""
    for relative, _nail in NAILS:
        source = (REPO / relative).read_text(encoding="utf-8")
        problems = _second_ruler_problems(source)
        assert problems == [], (relative, problems)


def test_the_six_nails_ship_no_escape_hatch():
    """判据⑤ 的下限：不许 skip／xfail／逃生口，也不许把枚数那一格从等号松成阈值。"""
    for relative, nail in NAILS:
        tree = contract_ledger._parse(relative)
        for node in _reach_defs(tree, nail):
            body = ast.Module(body=[node], type_ignores=[])
            assert contract_ledger._escape_calls(body) == [], (relative, node.name)
            assert contract_ledger._loose_count_assertions(body) == [], (relative, node.name)
        trapped = sorted(contract_ledger._reachable(tree, nail)["called"] & contract_ledger.NO_ESCAPE_CALLS)
        assert not trapped, (relative, trapped)


def test_the_six_nails_keep_their_own_non_position_teeth():
    """接线不等于摘牙：每枚钉改完仍得留住自己那两条与位置无关的判据（节名恰一枚、节数只增不减）。"""
    for relative, nail in NAILS:
        tree = contract_ledger._parse(relative)
        body = ast.Module(body=_reach_defs(tree, nail), type_ignores=[])
        asserts = [node for node in ast.walk(body) if isinstance(node, ast.Assert)]
        rendered = [ast.unparse(node) for node in asserts]

        assert len(asserts) >= 4, (relative, len(asserts))
        assert any("EXPECTED_DIFFERENCES_TODAY" in text for text in rendered), relative
        assert any(".count(" in text for text in rendered), "%s 的节名／节数判据不见了" % relative


def test_no_nail_copies_a_derived_position():
    """判据④：手抄位置一枚不许活着的两条扫描。

    · 全文扫「今天派生出来的那些数字」（字符位与行号、两侧长度）：六枚件与本件都不许把它们写成字面量。
    · 可达面扫「五位以上裸数字」：这一条只按钉的可达面判 —— 六枚件里 `999999` 是假告警号、
      `4382443` 是立案的 sha，两者都不是位置；把它们剔出去就成了豁免名单，所以判「位置真正可能被
      用起来的那一格」，而不是把全文数字一律当罪证。
    """
    numbers = _today_positions()

    for relative, nail in NAILS:
        tree = contract_ledger._parse(relative)
        problems = _hand_copy_problems(_reach_defs(tree, nail), numbers)
        assert problems == [], (relative, problems)
        text = (REPO / relative).read_text(encoding="utf-8")
        copied = sorted(number for number in numbers if str(number) in text)
        assert copied == [], "%s 把派生出来的位置写成了字面量：%s" % (relative, copied)

    own = Path(__file__).resolve().read_text(encoding="utf-8")
    assert sorted(number for number in numbers if str(number) in own) == [], "本件自己也不许抄位置"


def test_the_six_knives_edit_six_different_bytes():
    """六把刀各改各的那一枚字节：不许一枚刀复用别人的落点（那六枚就只剩一把刀）。"""
    limit = _off_ledger_limit()
    positions = _punctuation_positions()
    chosen = [positions[order] for order in range(len(NAILS))]

    assert len(positions) >= len(NAILS), positions
    assert len(set(chosen)) == len(chosen), chosen
    assert all(0 <= position < limit for position in chosen), (chosen, limit)


# ---------------------------------------------------------------------- 四把反证刀


def test_counter_evidence_1_one_off_ledger_punctuation_edit_gives_one_sentence(tmp_path, monkeypatch):
    """刀①（判据③）：账外动一个标点 ⇒ 六枚同时红，红句逐枚一字不差，且点名派生出来的位置。

    六枚钉读的必须是同一句话：不许一枚说「账外被动过」、另一枚说「枚数不对」。
    """
    before = contract_ledger._disk_sha()
    shadow = contract_ledger._shadow_copy(tmp_path, _off_ledger_punctuation_edit(0))
    monkeypatch.setattr(contract_ledger, "CONTRACT_PATH", shadow)

    red = _red(_run_six())
    assert len(red) == len(NAILS), red
    sentences = set(red.values())
    assert len(sentences) == 1, sorted(sentences)
    only = sentences.pop()
    assert "在差异账之外被动过" in only, only
    assert "现盘第" in only and "对应基点第" in only, only
    assert "枚数不对" not in only, only
    assert _red(_run_six()) == red, "同一枚影子端跑两遍得给同一份红：读数不许带现场状态"
    assert contract_ledger._disk_sha() == before, "刀动到了盘上那枚禁区文件"


@pytest.mark.parametrize("order", range(len(NAILS)), ids=list(NAIL_IDS))
def test_counter_evidence_2_every_nail_has_its_own_knife(order, tmp_path, monkeypatch):
    """刀②（判据⑤）：每枚钉至少一把自己的刀 —— 落点逐枚不同的那一改，它必须红。"""
    relative, nail = NAILS[order]
    key = "%s::%s" % (Path(relative).name, nail)
    before = contract_ledger._disk_sha()
    shadow = contract_ledger._shadow_copy(tmp_path, _off_ledger_punctuation_edit(order))
    monkeypatch.setattr(contract_ledger, "CONTRACT_PATH", shadow)

    red = _red(_run_six())
    assert key in red, "%s 对这一改不红：它没在读这本账：%s" % (key, sorted(red))
    assert "在差异账之外被动过" in red[key] and "现盘第" in red[key], red[key]
    assert len(red) == len(NAILS), red
    assert contract_ledger._disk_sha() == before, "刀动到了盘上那枚禁区文件"


def test_counter_evidence_3_a_copied_position_bites_the_scanner():
    """刀③（判据④ 的反证）：把今天派生出来的位置抄回钉里，扫描当场点名（只在内存里改，不写盘）。"""
    numbers = _today_positions()
    relative, nail = NAILS[0]
    tree = contract_ledger._parse(relative)
    assert _hand_copy_problems(_reach_defs(tree, nail), numbers) == [], relative

    sample = max(numbers)
    assert sample >= 10000, sample
    for forge in (str(sample), repr(str(sample)), "100000"):
        mutated = ast.parse(_injected_source(relative, nail, forge))
        problems = _hand_copy_problems(_reach_defs(mutated, nail), numbers)
        assert problems, (forge, problems)
        assert any(("位置" in line) or ("裸数字" in line) for line in problems), (forge, problems)

    untouched = (REPO / relative).read_text(encoding="utf-8")
    assert _second_ruler_problems(untouched) == [], relative


def test_counter_evidence_4_a_second_ruler_bites_the_scanner():
    """刀④（判据③ 的反证）：谁偷偷再造一把尺 —— 自家基点、自家枚数门、自家登记，三形都点名。"""
    relative, _nail = NAILS[0]
    source = (REPO / relative).read_text(encoding="utf-8")

    for forge in (
        'FROZEN_BASE = "deadbeef"',
        "EXPECTED_DIFFERENCES_TODAY = 6",
        "EXPECTED_DIFFERENCES_TODAY = range(3)",
        "CONTRACT_DIFFERENCES = ()",
        "probe = Difference(ticket='x', old='y', new='z', reason='w')",
    ):
        problems = _second_ruler_problems(source + "\n\n" + forge + "\n")
        assert problems, forge
    assert _second_ruler_problems(source) == [], relative
