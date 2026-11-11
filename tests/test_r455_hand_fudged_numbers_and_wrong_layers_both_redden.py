# -*- coding: utf-8 -*-
"""R455 · 反证钉第二、三把（判据②b／②c）：手改数字凑绿要红，符号写错层也要红。

(b) **手改表里任一数字凑绿**：把某一枚行内引用的坐标按"净 +1"的算术挪一下，或把另一枚锚的现读
    抄过来顶替 —— 两种都是"看着像今天"的数，本件必须红在那一格的名字上。
    再加一刀：把文末历史表里的旧数追改成今天的数（判据③明令不许）。这一形 `compare()` 看不见
    （历史区不比等值，只比有没有被追改），只有 `history_frozen_diff` 咬得住 —— 两头都取回，
    才证得明那把牙不是装饰。

(c) **把符号写错层**：`GET /sessions` 那一格点的是路由本体，锚块若去引 `_ensure_session` 那枚
    helper（`4037868` 那一笔当年就抄错在这一层），单看数字它可以凑得一模一样 —— 量具的层判据
    （落点必须以 `@router.` 起头、下一行读得出端点定义）必须仍然红。
    🔴 同一份数据喂给「摘掉层判据」的量具必须绿：否则不能断定红来自那把牙。

外加一把：锚被人改名（`@router.get("/sessions")` 读不出来）时，量具必须点名锚腐、把那一格的读数
拒发出去，不许"取第一次命中"，也不许把旧数留在表里 —— 静默跳过＝假绿，比红更坏。

🔴 全程只在内存字符串与 tmp 影子树上叠变异，被跟踪文件一枚字节都不动（R253 在册那一形）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

import test_r455_gapdoc_coordinates_are_derived as ledger

REPO = ledger.REPO
TOOL = ledger.TOOL
CHAT = ledger.CHAT
GAPDOC_REL = ledger.GAPDOC_REL
#: 当年抄错的那一层：本件只按符号引它，一枚行号都不写。
WRONG_LAYER_ANCHOR = (0, ['def _ensure_session(session_id: str, user_id: str = "") -> dict:'])


def live_text() -> str:
    return ledger.gapdoc_text()


def cite(label: str) -> dict:
    return next(item for item in TOOL.LIVE_CITES if item["label"] == label)


def mutate_cell(text: str, label: str, cell: str) -> str:
    """在内存里把某一枚行内引用的坐标换成另一串数：盘上那本文一个字不动。"""
    item = cite(label)
    index, row = TOOL._row_of(text, item["row"], label)
    at = row.find(item["before"])
    assert at >= 0, label + " 的坐标左锚读不到了"
    cut = at + len(item["before"])
    token = TOOL._coordinate_token(row[cut:])
    assert token, label + " 那一格读不出坐标"
    lines = text.split("\r\n")
    lines[index] = lines[index][:cut] + cell + lines[index][cut + len(token):]
    return "\r\n".join(lines)


def shifted(cell: str, step: int = 1) -> str:
    return TOOL.CELL_HEAD + str(int(cell[len(TOOL.CELL_HEAD):]) + step)


def with_anchor(key: str, anchor: tuple) -> dict:
    """把在册锚表里某一枚的起点换成另一层的一个符号，其余照抄（换的是锚，不是数）。"""
    sites = {name: dict(spec) for name, spec in TOOL.GAPDOC_SITES.items()}
    sites[key]["start"] = anchor
    return sites


def strip_layer_gate(sites: dict) -> dict:
    """摘守卫：把层判据从锚表里拿掉（进程内字典，盘上那枚量具一个字不动）。"""
    stripped = {}
    for key, spec in sites.items():
        clone = dict(spec)
        clone.pop("must_start", None)
        clone.pop("handler_start", None)
        stripped[key] = clone
    return stripped

# ------------------------------------------------------------------ (b) 手改数字凑绿


def test_bumping_a_cell_by_one_the_offset_math_trick_goes_red() -> None:
    """🔴 刀②b-1：拿"净 +1"把 G06 那一格算术凑绿 —— 红，且红句把两头与那条唯一的出路都端出来。"""
    truth = ledger.derived()["queue_cancel"]
    fudged = mutate_cell(live_text(), "G06", shifted(truth, 1))
    report = TOOL.compare(root=REPO, text=fudged)
    assert len(report["red"]) == 1, "凑绿只该红这一格：" + str(report["red"])
    assert "G06" in report["red"][0] and TOOL.EMIT_COMMAND in report["red"][0], report["red"][0]
    assert "那一格印 " + shifted(truth, 1) in report["red"][0], report["red"][0]
    assert "不许手改数字" in report["red"][0], report["red"][0]


def test_copying_a_sibling_coordinate_into_the_wrong_cell_goes_red() -> None:
    """🔴 刀②b-2：把 sessions 的现读抄进 G06 那一格 —— 数是真的、格是错的，照样红。

    这一刀专治「只看数看不格」的假尺：抄来的数若恰好也是今天某枚锚的现读，集合级检查会放它过关，
    只有逐枚等值那一格咬得住（所以这里同时钉 `stray == []`：红来自逐枚等值，不来自多一枚手抄）。
    """
    cells = ledger.derived()
    fudged = mutate_cell(live_text(), "G06", cells["sessions_route"])
    report = TOOL.compare(root=REPO, text=fudged)
    assert [item for item in report["red"] if "G06" in item], str(report["red"])
    assert report["stray"] == [], str(report["stray"])


def test_one_more_hand_copied_cell_anywhere_outside_the_history_goes_red() -> None:
    """🔴 结构性关掉这一族的落点：正文里再冒出一枚没在册的手抄坐标，当场红。"""
    text = live_text()
    index, _row = TOOL._row_of(text, "| T3 | 查自己报的数据", "T3")
    lines = text.split("\r\n")
    lines[index] = lines[index] + "（新抄的一枚 `app/api/v1/chat.py:4100`）"
    report = TOOL.compare(root=REPO, text="\r\n".join(lines))
    assert any("多出来手抄" in item and "4100" in item for item in report["red"]), str(report["red"])


def test_retouching_a_historical_table_is_red_and_only_the_freeze_tooth_sees_it() -> None:
    """判据③：把历史表里的旧数追改成今天的数 —— `compare()` 一路绿，`history_frozen_diff` 红。

    两头都取回：如果只留逐枚等值那一把牙，改口历史就没人管；这一格同时说明本单为什么两张历史表
    原样不追改、而正文那五枚行内引用要跟着现读走 —— 它们根本不是同一类断言。
    """
    text = live_text()
    retouched = text.replace("| :4213 | ", "| :4214 | ")
    assert retouched != text, "上一笔那枚读数不在历史表里，本刀白磨"
    assert TOOL.compare(root=REPO, text=retouched)["red"] == [], "这一形不该混进坐标等值那把牙"
    red = TOOL.history_frozen_diff(retouched, text)
    assert red and "被追改" in red[0], str(red)


# ------------------------------------------------------------------ (c) 符号写错层


def test_a_sessions_anchor_pointed_at_the_helper_is_refused_by_name() -> None:
    """🔴 刀②c-1：把 sessions 锚改成 `_ensure_session` —— 量具点名「写错层」，一枚数都不端。"""
    with pytest.raises(TOOL.CoordinateUnavailable) as err:
        TOOL.resolve_site("sessions_route", REPO, with_anchor("sessions_route", WRONG_LAYER_ANCHOR))
    message = str(err.value)
    assert "写错层" in message, message
    assert "_ensure_session" in message, message
    assert "GET /sessions 路由本体" in message, message


def test_a_wrong_layer_cite_stays_red_even_when_the_number_matches() -> None:
    """🔴 刀②c-2：数凑得一模一样也红 —— 这一把才是 §126「写下时就查错了层」的解药。

    先用摘了层判据的量具算出错层那一枚的现读，照它写回缺口单那一格（文档与读数此刻完全自洽），
    再拿**在册**的量具去对：数相等、层不等 ⇒ 红。同一份数据喂给摘了牙的量具必须绿，
    否则本件不能断定红来自那把牙而不是别处。
    """
    naked_wrong = strip_layer_gate(with_anchor("sessions_route", WRONG_LAYER_ANCHOR))
    wrong_cells, failures = TOOL.derived_cells(REPO, naked_wrong)
    assert failures == [], str(failures)
    assert wrong_cells["sessions_route"] != ledger.derived()["sessions_route"], "错层与路由读到同一行：这刀没砍在层上"

    landed = mutate_cell(live_text(), "G04", wrong_cells["sessions_route"])
    toothless = TOOL.compare(root=REPO, sites=naked_wrong, text=landed)
    assert toothless["red"] == [], "摘了层判据还红：本件证不了红来自那把牙 —— " + str(toothless["red"])

    guarded = TOOL.compare(root=REPO, sites=with_anchor("sessions_route", WRONG_LAYER_ANCHOR), text=landed)
    assert any("写错层" in item for item in guarded["red"]), str(guarded["red"])
    assert any("G04" in item for item in guarded["red"]), str(guarded["red"])


def test_the_gap_doc_names_the_layer_it_claims() -> None:
    """文档那一格自己写着「`GET /sessions` 路由本体」：层判据引的就是它这句话，不是本件编的。"""
    _index, row = TOOL._row_of(live_text(), cite("G04")["row"], "G04")
    assert "路由本体" in row, row
    assert "GET /sessions" in row, row


# ------------------------------------------------------------------ 锚腐不许静默


def test_a_renamed_route_decorator_is_announced_not_guessed(tmp_path: Path) -> None:
    """🔴 锚被改名（0 命中）时不许悄悄取第一次命中，也不许把旧数留在表里：静默＝假绿。"""
    shadow = ledger.shadow_root(tmp_path, pad_lines=0)
    path = shadow / CHAT
    body = path.read_bytes().decode("utf-8")
    decorator = TOOL.GAPDOC_SITES["sessions_route"]["start"][1][0]
    assert body.count(decorator) == 1, "影子树里那枚装饰器不唯一，本刀白磨"
    path.write_bytes(body.replace(decorator, '@router.get("/sessions-legacy")').encode("utf-8"))

    cells, failures = TOOL.derived_cells(shadow)
    assert failures and any("sessions_route" in item and "命中 0 枚" in item for item in failures), str(failures)
    assert "sessions_route" not in cells, "锚腐了还把数端出来：" + str(cells)
    report = TOOL.compare(root=shadow, text=(shadow / GAPDOC_REL).read_bytes().decode("utf-8"))
    assert any("先修锚" in item and "G04" in item for item in report["red"]), str(report["red"])
