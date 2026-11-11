# -*- coding: utf-8 -*-
"""R693 的牙：§9.3 那枚机械写回口自己得咬得住（全离线，不 import app，不连库，不起服务）。

为什么单独钉这把写回口（AGENTS.md 病根处置①②同一条纪律）：那一列的值只许由派生器现场给，
而「派生器现场给」这件事本身要有牙——否则下一次重落地就是一只没人验过的手，抄进去的数字
照样是手抄账。八把反证各咬一格，全在内存的行列表里变异，盘上一枚字节都不写：

* 漂的那一格被改回现读，且改完幂等（第二遍一枚都不必动）；
* 锚 key 与坐标枚数不等 ⇒ 整本拒写（拒绝半落地，不是改一半交回去）；
* 文件归属对不上 ⇒ 点名拒写；没锚那一行长出坐标 ⇒ 拒写；那一节找不到 ⇒ 直接拒，不猜；
* 行尾成对还原：CRLF 进 CRLF 出，LF 进 LF 出（混行尾会让逐字节钉天天误红）；
* 只动数字那一段：把数字抹掉之后两版正文必须逐字节相等；
* 写回口与本件自己的源码都不许长字面坐标（照在册棘轮那把尺的口径自咬）。

形状照 tests/test_r132_contract_followup_sync.py 抄：只用 ast／re／pathlib，离线，秒级。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "scripts" / "r693_land_s93_column.py"
LINT = REPO / "scripts" / "lint_hand_copied_coordinates.py"

#: 合成坐标的字面形状靠拼接，本件源码里一枚「文件:数字」都不写（在册反证钉同一手法）。
EXT = "." + "py"
COLON = ":"
TICK = "`"
FILE = "app" + "/" + "demo" + EXT
OTHER = "app" + "/" + "other" + EXT
SEP = "|" + "---|" * 4


def _load(name: str, path: Path):
    module = sys.modules.get(name)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lander = _load("r693_land_s93_column", TOOL)


def cite(path: str, first: int, last=None) -> str:
    return path + COLON + (str(first) if last is None else "%d-%d" % (first, last))


def cell(*pieces) -> str:
    return " ".join(TICK + piece + TICK for piece in pieces)


def data_row(keys, cell_text: str) -> str:
    left = " ".join(TICK + key + TICK for key in keys) if keys else "🔴 无锚"
    return "| 病那一格 | " + left + " | 锚首行 token | " + cell_text + " |"


def doc_text(rows, newline: str = "\n", mark: str = "### " + "9.3") -> str:
    lines = [mark, "",
             "| 病 | 锚（key） | 锚首行 token | 本班现读＝resolve_site 现场派生 |", SEP]
    lines += rows
    lines += ["", "### 9.4 下一节"]
    return newline.join(lines)


def resolver(mapping):
    def resolve(key, _root):
        return mapping[key]
    return resolve


# ---------------------------------------------------------------- 漂移→落地→幂等


def test_a_stale_cell_is_rewritten_to_the_live_reading() -> None:
    text = doc_text([data_row(["hop1"], cell(cite(FILE, 100)))])
    landed, changed, refusals = lander.land(text, resolver({"hop1": (FILE, 250, 250)}), REPO)
    assert refusals == [], refusals
    assert changed == 1, changed
    assert cite(FILE, 100) not in landed
    assert cite(FILE, 250) in landed


def test_landing_the_landed_text_changes_nothing() -> None:
    text = doc_text([data_row(["hop1"], cell(cite(FILE, 100)))])
    mapping = {"hop1": (FILE, 250, 250), "hop2": (FILE, 300, 320)}
    once, changed, _ = lander.land(text, resolver(mapping), REPO)
    assert changed == 1
    twice, changed_again, refusals = lander.land(once, resolver(mapping), REPO)
    assert changed_again == 0 and twice == once and refusals == []


def test_ranges_and_single_lines_both_re_render() -> None:
    """单行变区间、区间变单行：数字段整段换掉，不许留下半枚旧区间。"""
    rows = [data_row(["hop1"], cell(cite(FILE, 10))),
            data_row(["hop2"], cell(cite(FILE, 20, 30)))]
    mapping = {"hop1": (FILE, 40, 44), "hop2": (FILE, 50, 50)}
    landed, changed, refusals = lander.land(doc_text(rows), resolver(mapping), REPO)
    assert refusals == [] and changed == 2, (refusals, changed)
    assert cite(FILE, 40, 44) in landed and cite(FILE, 50) in landed
    assert cite(FILE, 20, 30) not in landed and cite(FILE, 10) not in landed


def stripped(body: str) -> str:
    return "".join(ch for ch in body if not ch.isdigit())


def test_only_the_digits_move_every_other_byte_stays() -> None:
    """箭头、括号、反引号、对齐空格一枚不重排：抹掉数字之后两版必须逐字节相等。

    这一把只用「单行换单行」的映射——区间那一带的字节形状由上一把钉管，混在一起就
    量不出「只动数字」这件事了。
    """
    rows = [data_row(["hop5f", "hop5g"], cell(cite(FILE, 10)) + " → " + cell(cite(FILE, 20))),
            data_row(["hop6", "hop6b", "hop6c"],
                     cell(cite(FILE, 30)) + " → " + cell(cite(FILE, 40))
                     + "（" + cell(cite(FILE, 50)) + "）")]
    mapping = {"hop5f": (FILE, 11, 11), "hop5g": (FILE, 22, 22), "hop6": (FILE, 33, 33),
               "hop6b": (FILE, 40, 40), "hop6c": (FILE, 50, 50)}
    text = doc_text(rows)
    landed, changed, refusals = lander.land(text, resolver(mapping), REPO)
    assert refusals == [] and changed == 3, (refusals, changed)
    assert stripped(landed) == stripped(text), "数字之外的字节被动过"


# ------------------------------------------------------------------- 拒写那一族


def test_key_and_claim_counts_mismatch_refuses_half_landing() -> None:
    text = doc_text([data_row(["hop1", "hop2"], cell(cite(FILE, 100)))])
    _landed, _changed, refusals = lander.land(text, resolver({"hop1": (FILE, 200, 200)}), REPO)
    assert refusals and "拒绝半落地" in refusals[0], refusals


def test_a_coordinate_without_an_anchor_refuses() -> None:
    rows = [data_row([], cell(cite(FILE, 100))), data_row(["hop1"], "—")]
    _landed, _changed, refusals = lander.land(doc_text(rows), resolver({}), REPO)
    assert any("无处派生" in row for row in refusals), refusals


def test_wrong_file_attribution_is_named_and_refused() -> None:
    text = doc_text([data_row(["hop1"], cell(cite(FILE, 100)))])
    _landed, changed, refusals = lander.land(text, resolver({"hop1": (OTHER, 200, 200)}), REPO)
    assert changed == 0, "文件归属不对却已经改了格"
    assert any("文件归属不对" in row for row in refusals), refusals


def test_a_missing_section_refuses_instead_of_guessing() -> None:
    text = "| 病 | 锚 | token | 现读 |" + "\n" + SEP + "\n"
    with pytest.raises(RuntimeError, match="拒绝落地"):
        lander.land(text, resolver({}), REPO)


# ------------------------------------------------------------------ 行尾与自咬


def test_the_line_ending_of_the_book_is_returned_unchanged() -> None:
    mapping = {"hop1": (FILE, 250, 250)}
    rows = [data_row(["hop1"], cell(cite(FILE, 100)))]
    crlf = doc_text(rows, newline="\r\n")
    landed, changed, refusals = lander.land(crlf, resolver(mapping), REPO)
    assert refusals == [] and changed == 1
    assert landed.count("\r\n") == crlf.count("\r\n")
    assert landed.count("\n") == landed.count("\r"), "落地把成对行尾劈开了"
    lf = doc_text(rows, newline="\n")
    landed_lf, changed_lf, _ = lander.land(lf, resolver(mapping), REPO)
    assert changed_lf == 1 and "\r" not in landed_lf


def test_the_lander_and_this_pin_carry_no_hand_copied_coordinate() -> None:
    """写回口自己不许带账：它一旦含字面坐标，下一次重落地就又有人抄它的数。"""
    lint = _load("chase_lint_for_r693", LINT)
    for path in (TOOL, Path(__file__).resolve()):
        hits = lint.hits_in_file(path)
        assert hits == [], str(path) + " 里长出字面坐标：" + str(hits[:3])
