# -*- coding: utf-8 -*-
"""R460 · 反证钉第一把（判据③a）：往被测后端文件顶部插一行 ⇒ 在册那几格坐标当场红并点名「跑派生件重落地」。

这一把刀就是这一族病灶的显影液：run9 收窗那一笔（`2154318`）之后，并树给 `app/quality/eval.py`
净 +280／+289／+290 行（按格不同）、给采集器净 +99 行，读数本里那几枚手抄坐标一枚枚打漂，
而**没有任何一枚门喊过**。今天它必须喊，而且只许喊一句话 —— 红句点名
`python scripts/r460_run9_coordinates.py --emit-doc-cells`，不给人留「拿旧数加减一行」那条错路
（R455 §129 三那一族的两笔教训都在这一句上）。

🔴 枚数从表里取，不从纸上抄：本件所有「红几枚」的期望都由 `READOUT_CITES` 与被引文件的对应关系
   现算 —— 在册那几格今天变成几枚，这把刀就该当场咬几枚，刀上不写死数字（补令把两格纳进派生道时，
   本件一字没改，红数从 2 枚自己长到 5 枚）。

同时钉住「重落地是纯机械」这一格：把影子树现读的那几枚坐标写回读数本，红的清单就空了 ——
下一班不需要任何行号算术，也不需要读源码数行。

🔴 插行落在 tmp 影子树上，盘上那两枚被跟踪的后端文件与那本读数各一个字节都不动 ——
   这形在册由 `tests/test_r253_no_test_rewrites_a_tracked_file.py` 盯着，本件最后那枚用例
   自己再取一次 sha256 对账（进门一趟、出门一趟，盘上必须同一枚）。
🔴 历史不追改（判据④）另有一枚用例：影子树插行之后，当年现取的其他格子一枚都不许跟着红。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import test_r460_run9_coordinates_are_derived as ledger

REPO = ledger.REPO
TOOL = ledger.TOOL
EVAL = ledger.EVAL
TRANSPORT = ledger.TRANSPORT
READOUT_REL = ledger.READOUT_REL
#: 在册行内引用（红清单要逐枚点名，缺一枚都算这把刀砍空）。
LIVE_LABELS = ledger.LIVE_LABELS
#: 每一枚被引文件今天背着哪几枚在册格 —— 枚数由表算出，不在本件里写死。
CITES_BY_FILE = {
    rel: tuple(item for item in TOOL.READOUT_CITES if TOOL.RUN9_SITES[item["key"]]["file"] == rel)
    for rel in (EVAL, TRANSPORT)
}
#: 插行实验的两枚被引文件（影子树里只有这两枚会被撑长）。
PADDED_KEYS = tuple(item["key"] for rel in (EVAL, TRANSPORT) for item in CITES_BY_FILE[rel])


def shadow_doc(root: Path) -> str:
    return (root / READOUT_REL).read_bytes().decode("utf-8")


def cells_from(root: Path) -> dict:
    return ledger.derived(root)


def drift_reds(report: dict) -> list:
    return [item for item in report["red"] if "重落地" in item]


@pytest.mark.parametrize("rel", [EVAL, TRANSPORT])
def test_a_blank_line_above_a_backed_file_reddens_every_cell_it_carries(tmp_path: Path, rel: str) -> None:
    """🔴 刀①：影子树里给被引文件各插一枚空行 ⇒ 它背着的那几枚在册格逐枚红，别文件的格一枚不许陪红。"""
    shadow = ledger.shadow_root(tmp_path,
                                pad_eval=1 if rel == EVAL else 0,
                                pad_transport=1 if rel == TRANSPORT else 0)
    report = TOOL.compare(root=shadow, text=shadow_doc(shadow))
    drift = drift_reds(report)
    expect = CITES_BY_FILE[rel]
    assert len(expect) >= 1 and rel in CITES_BY_FILE, "这张表空了：这把刀没有下口处"
    assert len(drift) == len(expect) == len(report["red"]), "红清单：" + str(report["red"])
    for item in expect:
        assert any(item["label"] in entry for entry in drift), item["label"] + " 没被这把刀咬住：" + str(drift)
    others = {entry["label"] for entry in TOOL.READOUT_CITES if entry not in expect}
    assert not [entry for entry in report["red"] if any(label in entry for label in others)], str(report["red"])


def test_a_blank_line_above_both_backed_files_reddens_every_live_coordinate(tmp_path: Path) -> None:
    """两枚文件同时撑长 ⇒ 在册每一枚都红：一枚不许漏（漏一枚就是那格没在派生道上）。"""
    shadow = ledger.shadow_root(tmp_path, pad_eval=1, pad_transport=1)
    report = TOOL.compare(root=shadow, text=shadow_doc(shadow))
    drift = drift_reds(report)
    assert len(drift) == len(TOOL.READOUT_CITES), "红清单：" + str(report["red"])
    assert len(report["red"]) == len(LIVE_LABELS), "除坐标这一族之外还红了别的：" + str(report["red"])
    for label in LIVE_LABELS:
        assert any(label in item for item in drift), label + " 没被这把刀咬住：" + str(drift)


def test_the_red_sentence_names_the_emit_command_and_not_hand_arithmetic(tmp_path: Path) -> None:
    """🔴 判据③a 那半句「红句点名跑派生件重落地」：每枚红都只指一条路，且明令不许手改。"""
    shadow = ledger.shadow_root(tmp_path, pad_eval=1, pad_transport=1)
    report = TOOL.compare(root=shadow, text=shadow_doc(shadow))
    assert len(report["red"]) == len(LIVE_LABELS), str(report["red"])
    for item in report["red"]:
        assert TOOL.EMIT_COMMAND in item, item
        assert "重落地" in item and "不许手改数字" in item and "不许拿旧数加减行号" in item, item
        assert "那一格印" in item and "按符号现读" in item, item


@pytest.mark.parametrize("key", PADDED_KEYS)
def test_readings_move_by_exactly_the_inserted_lines(tmp_path: Path, key: str) -> None:
    """插 N 行 ⇒ 那一枚现读整体 +N：派生账吃得住「并树把文件撑长」这一族，不需要人做算术。"""
    rel = TOOL.RUN9_SITES[key]["file"]
    pad = 3 if rel == EVAL else 2
    shadow = ledger.shadow_root(tmp_path,
                                pad_eval=pad if rel == EVAL else 0,
                                pad_transport=pad if rel == TRANSPORT else 0)
    here, there = cells_from(REPO)[key], cells_from(shadow)[key]
    assert ledger.numbers(there) == tuple(value + pad for value in ledger.numbers(here)), str((here, there))
    assert here != there, "影子树插了行而读数一模一样：这把刀砍在空气上"


def test_relanding_the_emitted_cells_makes_the_padded_tree_green(tmp_path: Path) -> None:
    """重落地之后红清单为空 —— 证明修这一族是机械动作，不是考古。"""
    shadow = ledger.shadow_root(tmp_path, pad_eval=1, pad_transport=1)
    landed = TOOL.land_cells(shadow_doc(shadow), cells_from(shadow))
    report = TOOL.compare(root=shadow, text=landed)
    assert report["red"] == [], "写了现读还红：" + str(report["red"])
    assert len(report["matched"]) == len(LIVE_LABELS), str(report["matched"])


def test_landing_moves_no_byte_but_the_coordinate_characters(tmp_path: Path) -> None:
    """🔴 判据⑤的具像：落地前后把坐标挖掉，两版必须逐字节相同；行数一枚不许变。"""
    shadow = ledger.shadow_root(tmp_path, pad_eval=1, pad_transport=1)
    original = shadow_doc(shadow)
    landed = TOOL.land_cells(original, cells_from(shadow))
    assert landed != original, "影子树插了行、落地却没改动任何字节"
    assert ledger.masked(original) == ledger.masked(landed), "落地动的不止坐标那一串字"
    assert len(original.splitlines()) == len(landed.splitlines()), "落地把行数也动了：那不止是坐标"


def test_the_pad_leaves_every_historical_cell_alone(tmp_path: Path) -> None:
    """判据④的另一面：撑长后端文件只该红在册那几枚，历史格子一枚都不许跟着喊。"""
    shadow = ledger.shadow_root(tmp_path, pad_eval=1, pad_transport=1)
    body = shadow_doc(shadow)
    report = TOOL.compare(root=shadow, text=body)
    assert report["failures"] == [], str(report["failures"])
    assert not [item for item in report["red"] if "追改" in item or "历史格子" in item], str(report["red"])
    assert TOOL.frozen_missing(body) == []
    assert TOOL.registered_conflicts(body, cells_from(shadow)) == [], "撑长一行不该碰互斥那条路"


def test_the_teeth_leave_the_tracked_files_byte_for_byte(tmp_path: Path) -> None:
    """🔴 零污染：这把握刀全程只在 tmp 里落笔，盘上那三枚文件进门出门同一枚 sha256。"""
    digests = {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
               for rel in (EVAL, TRANSPORT, READOUT_REL)}
    shadow = ledger.shadow_root(tmp_path, pad_eval=2, pad_transport=2)
    TOOL.compare(root=shadow, text=shadow_doc(shadow))
    TOOL.land_cells(shadow_doc(shadow), cells_from(shadow))
    for rel, before in digests.items():
        assert hashlib.sha256((REPO / rel).read_bytes()).hexdigest() == before, rel + " 被人就地改写过"
