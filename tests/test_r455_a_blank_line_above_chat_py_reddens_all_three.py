# -*- coding: utf-8 -*-
"""R455 · 反证钉第一把（判据②a）：给 `chat.py` 顶部插一枚空行 ⇒ 那三枚坐标当场红。

这一把刀就是这一族病灶的显影液：R404 并树给 `chat.py` 的 import 块净 +1，缺口单那三枚手抄坐标
当场打漂，而**没有任何一枚门喊过**。今天它必须喊，而且只许喊一句话 —— 跑 emit 重落地：
红句点名 `python scripts/r455_gapdoc_coordinates.py --emit-doc-cells`，不给人留"拿旧数加减一行"
那条错路（R404 那一笔的教训：净 +1 与净 +17 落在区间内外，加减算术会在第二枚锚上算错）。

🔴 插行落在 tmp 影子树上，盘上那枚被跟踪的 `app/api/v1/chat.py` 一个字节都不动 ——
   这形在册由 `tests/test_r253_no_test_rewrites_a_tracked_file.py` 盯着，本件最后那枚用例
   自己再取一次 sha256 对账（进门一趟、出门一趟，盘上必须同一枚）。

同时钉住"重落地是纯机械"这一格：把影子树现读的那三枚坐标写回缺口单，红的清单就空了 ——
下一班不需要任何行号算术，也不需要读源码数行。
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import test_r455_gapdoc_coordinates_are_derived as ledger

REPO = ledger.REPO
TOOL = ledger.TOOL
CHAT = ledger.CHAT
GAPDOC_REL = ledger.GAPDOC_REL


def shadow_doc(root: Path) -> str:
    return (root / GAPDOC_REL).read_bytes().decode("utf-8")


def cells_from(root: Path) -> dict:
    return ledger.derived(root)


def number(cell: str) -> int:
    return int(cell[len(TOOL.CELL_HEAD):])


def test_a_single_blank_line_above_chat_py_reddens_every_live_coordinate(tmp_path: Path) -> None:
    """🔴 刀①：影子树里给 `chat.py` 顶上加一枚空行 ⇒ 五枚行内引用逐枚红。"""
    shadow = ledger.shadow_root(tmp_path, pad_lines=1)
    report = TOOL.compare(root=shadow, text=shadow_doc(shadow))
    drift = [item for item in report["red"] if "重落地" in item]
    assert len(drift) == len(TOOL.LIVE_CITES) == 5, "红清单：" + str(report["red"])
    assert len(report["red"]) == 5, "除坐标这一族之外还红了别的：" + str(report["red"])
    for label in ("T2", "G04", "G06", "G08", "§遗留 2"):
        assert any(label in item for item in drift), label + " 没被这把刀咬住：" + str(drift)


def test_the_red_sentence_names_the_emit_command_and_not_hand_arithmetic(tmp_path: Path) -> None:
    """🔴 判据②a 那半句「红句点名跑 emit 重落地」：红句只指一条路，且明令不许手改。"""
    shadow = ledger.shadow_root(tmp_path, pad_lines=1)
    report = TOOL.compare(root=shadow, text=shadow_doc(shadow))
    first = report["red"][0]
    assert TOOL.EMIT_COMMAND in first, "红句没点名那枚量具：" + first
    assert "重落地" in first and "不许手改数字" in first, "红句给的不是唯一那条路：" + first
    assert "那一格印" in first and "按符号现读" in first, "红句没把两头都端出来：" + first
    for item in report["red"]:
        assert TOOL.EMIT_COMMAND in item, str(report["red"])


def test_the_three_readings_move_by_exactly_the_inserted_line(tmp_path: Path) -> None:
    """插一行 ⇒ 三枚现读整体 +1：派生账吃得住"并树把文件撑长"这一族，不需要人做算术。"""
    shadow = ledger.shadow_root(tmp_path, pad_lines=1)
    here, there = cells_from(REPO), cells_from(shadow)
    assert set(here) == set(there)
    for key in here:
        assert number(there[key]) == number(here[key]) + 1, key + "：" + here[key] + " -> " + there[key]
    assert here != there, "影子树插了行而读数一模一样：这把刀砍在空气上"


def test_relanding_the_emitted_cells_makes_the_padded_tree_green(tmp_path: Path) -> None:
    """重落地之后红清单为空 —— 证明修这一族是机械动作，不是考古。"""
    shadow = ledger.shadow_root(tmp_path, pad_lines=1)
    landed = TOOL.land_cells(shadow_doc(shadow), cells_from(shadow))
    report = TOOL.compare(root=shadow, text=landed)
    assert report["red"] == [], "写了现读还红：" + str(report["red"])
    assert len(report["matched"]) == 5, str(report["matched"])


def test_landing_moves_no_byte_but_the_coordinate_characters(tmp_path: Path) -> None:
    """🔴 写域那半句「散文一个字不许动」的量具版：落地前后把坐标挖掉，两版必须逐字节相同。"""
    shadow = ledger.shadow_root(tmp_path, pad_lines=1)
    original = shadow_doc(shadow)
    landed = TOOL.land_cells(original, cells_from(shadow))
    assert landed != original, "影子树插了行、落地却没改动任何字节"
    mask = re.compile(re.escape(TOOL.CELL_HEAD) + r"\d+")
    assert mask.sub(TOOL.CELL_HEAD + "NNNN", original) == mask.sub(TOOL.CELL_HEAD + "NNNN", landed), \
        "落地动的不止坐标那一串字"
    assert len(original.splitlines()) == len(landed.splitlines()), "落地把行数也动了：那不止是坐标"


def test_the_teeth_leave_the_tracked_files_byte_for_byte(tmp_path: Path) -> None:
    """🔴 零污染：这把握刀全程只在 tmp 里落笔，盘上那两枚文件进门出门同一枚 sha256。"""
    digests = {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest() for rel in (CHAT, GAPDOC_REL)}
    shadow = ledger.shadow_root(tmp_path, pad_lines=3)
    TOOL.compare(root=shadow, text=shadow_doc(shadow))
    TOOL.land_cells(shadow_doc(shadow), cells_from(shadow))
    for rel, before in digests.items():
        assert hashlib.sha256((REPO / rel).read_bytes()).hexdigest() == before, rel + " 被人就地改写过"
