# -*- coding: utf-8 -*-
"""R460 · 反证钉第二、三把（判据③b／③c）：手改数字凑绿要红，符号写错层也要红。

(b) **手改表里任一数字凑绿**：把某一枚行内引用的坐标按「净 +1」的算术挪一下、把另一枚锚的现读
    抄过来顶替、或把本单改掉之前的那枚旧抄数原样贴回去 —— 三种都是「看着像今天」的数，
    本件必须红在那一格的名字上。旧抄数不在本件里手打：逐枚从并树那一版的读数本现取
    （`ledger.printed_at_head`），下一班把这单重跑一遍，这组数会跟着历史走，不会烂在纸上。

(c) **把符号写错层**：这一把专治本单病灶本身。
    · 「分母恒=105」那句的正解是 `evaluate_evaluation_set` docstring 里的判据 4；本单发现时那一格
      指的是 `app/quality/eval.py:401-402` —— 今天躺在那两行的是**第二把尺越出 [0,1] 的 raise 校验**，
      它的报错文案里恰好写着「分子踩在了全部题数上」，手抄的人就是被这几个字骗到的。
    · 「C2 unsupported_claim_rate 算法」的正解是报告 dict 里那枚率的七行；补令发现那一格指的是
      今天躺着 `LATENCY_LEDGER_RATIO_TOLERANCE`／`LATENCY_LEDGER_SLACK_MS` 的位置 —— 两枚**时延容忍带
      常量**，名字里也带「率」与「容差」的味道，同一族诱饵。
    · 「`total=len(rows)`、`answer_correctness=ratio(correct)`」的正解是报告 dict 那两行；而
      `pre_approval_ruler` 里另有一枚 `total = len(results)` 与一把 `answer_correctness` —— 它是**旧口径
      那把尺的分母**，不在主分母上：数看着对、层是错的，正是补令点名那一形。
    · 采集器里另有两枚诱饵：`/approve 之后出现缓存命中`（另一道闸）与队列轮询的 blip 记账（本单
      发现时 :105 那一格就指着它）。
    每一种错层都要量具的层判据咬住：起点固定串、块内必含的措辞、下一行的 raise、往上读到的那枚函数。
    🔴 同一份数据喂给「摘掉层判据」的量具必须绿：否则不能断定红来自那把牙。
    🔴 四把层判据各点名自己那条措辞 —— 摘掉任何一把，红会换个名字甚至不红，本件逐枚分得开。

🔴 全程只在内存字符串与进程内锚表上叠变异，被跟踪文件一枚字节都不动（R253 在册那一形）；
   本件最后一枚用例自己再取一次 sha256 对账。
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
#: 在册那几格的名字（红清单要逐枚点名，本件一枚都不该漏）。
LIVE_LABELS = ledger.LIVE_LABELS
#: 本单与补令病灶那些「看着像」的错层锚：全部按符号写，一枚行号都不写进断言。
WRONG_LAYER_DENOMINATOR = {
    "start": (0, ["if not math.isfinite(number) or not 0.0 <= number <= 1.0:",
                  "raise ScorabilityDerivationError("]),
    "end": (0, ['f"第二把尺 {number} 越出 [0, 1] ⇒ 分子踩在了全部题数上")']),
}
WRONG_LAYER_LATENCY = {
    "start": (0, ["LATENCY_LEDGER_RATIO_TOLERANCE = 1.25", "LATENCY_LEDGER_SLACK_MS = 2000.0"]),
    "end": None,
}
WRONG_LAYER_PRE_APPROVAL = {
    "start": (0, ["total = len(results)"]),
    "end": (0, ['"answer_correctness": round(correct / total, 4) if total else 0.0,']),
}
#: 「抄了一行没抄块」：起点那行确实是分母，块尾那行才是这句话的另一半。
WRONG_LAYER_ONE_LINE_ONLY = {
    "start": (0, ['"total": len(rows),']),
    "end": None,
}
WRONG_LAYER_CACHE_APPROVE = {
    "start": (0, ['if out["cached"]:',
                  "raise RuntimeError(",
                  'row_id + ": /approve 之后出现缓存命中 ⇒ 开窗纪律破了（P-18），停下重跑，不许估算")']),
    "end": None,
}
WRONG_LAYER_CACHE_BLIP = {
    "start": (0, ['book["last_blip"] = type(exc).__name__']),
    "end": (0, ['book["polls"] += 1']),
}


def live_text() -> str:
    return ledger.readout_text()


def cite(label: str) -> dict:
    return ledger.cite(label)


def with_anchor(key: str, anchors: dict) -> dict:
    """把在册锚表里某一枚的起点／终点换成另一层的符号，其余照抄（换的是锚，不是数）。"""
    sites = {name: dict(spec) for name, spec in TOOL.RUN9_SITES.items()}
    sites[key].update(anchors)
    return sites


def with_claim(key: str, claim: dict) -> dict:
    """锚照抄、只改「这一格该长什么样」那句层判据：用来逐枚验四把判据各自的措辞。"""
    sites = {name: dict(spec) for name, spec in TOOL.RUN9_SITES.items()}
    sites[key].update(claim)
    return sites


def strip_layer_gate(sites: dict) -> dict:
    """摘守卫：把层判据从锚表里拿掉（进程内字典，盘上那枚量具一个字不动）。"""
    stripped = {}
    for key, spec in sites.items():
        clone = dict(spec)
        for gate in ("must_start", "must_contain", "next_start", "inside_def"):
            clone.pop(gate, None)
        stripped[key] = clone
    return stripped


def naked_cell(key: str, anchors: dict) -> str:
    """摘掉层判据之后，那枚错层锚读出来的坐标 —— 就是「手抄的人以为的数」。"""
    cells, failures = TOOL.derived_cells(REPO, strip_layer_gate(with_anchor(key, anchors)))
    assert failures == [], str(failures)
    return cells[key]


# ------------------------------------------------------------------ (b) 手改数字凑绿


@pytest.mark.parametrize("item", TOOL.READOUT_CITES, ids=lambda item: item["label"])
def test_bumping_any_live_cell_by_one_the_offset_math_trick_goes_red(item: dict) -> None:
    """🔴 刀②b-1：拿「净 +1」把任何一枚在册格算术凑绿 —— 只红这一枚，且红句把两头与唯一出路都端出来。"""
    truth = ledger.derived()[item["key"]]
    fudged = ledger.mutate_cell(live_text(), item["label"], ledger.shift(truth, 1))
    report = TOOL.compare(root=REPO, text=fudged)
    assert len(report["red"]) == 1, "凑绿只该红这一格：" + str(report["red"])
    red = report["red"][0]
    assert item["label"] in red and TOOL.EMIT_COMMAND in red, red
    assert "那一格印 " + ledger.shift(truth, 1) in red and "按符号现读 " + truth in red, red
    assert "不许手改数字" in red and "不许拿旧数加减行号" in red, red


def test_copying_the_sibling_coordinate_into_the_wrong_cell_goes_red() -> None:
    """🔴 刀②b-2：把缓存那一枚的现读抄进分母那一格 —— 数是真的、格是错的，照样红，且不连坐。"""
    cells = ledger.derived()
    donor = next(item for item in TOOL.READOUT_CITES if TOOL.RUN9_SITES[item["key"]]["file"] == TRANSPORT)
    victim = next(item for item in TOOL.READOUT_CITES if TOOL.RUN9_SITES[item["key"]]["file"] == EVAL)
    report = TOOL.compare(root=REPO, text=ledger.mutate_cell(live_text(), victim["label"], cells[donor["key"]]))
    assert [item for item in report["red"] if victim["label"] in item], str(report["red"])
    assert not [item for item in report["red"] if donor["label"] in item], str(report["red"])


@pytest.mark.parametrize("item", TOOL.READOUT_CITES, ids=lambda item: item["label"])
def test_the_pre_r460_hand_copied_number_reddens_again(item: dict) -> None:
    """🔴 刀②b-3：把本单（含补令）改掉之前的那枚手抄数原样贴回去 —— 这一形就是病灶，不许复活。"""
    stale = ledger.printed_at_head(item["label"])
    assert ledger.derived()[item["key"]] != stale, "现读已经等于旧抄数：这一刀没砍在数上"
    report = TOOL.compare(root=REPO, text=ledger.mutate_cell(live_text(), item["label"], stale))
    red = [entry for entry in report["red"] if item["label"] in entry]
    assert len(red) == 1, str(report["red"])
    assert "那一格印 " + stale in red[0], red[0]
    assert "按符号现读 " + ledger.derived()[item["key"]] in red[0], red[0]


def test_a_single_digit_tweak_in_any_live_cell_goes_red() -> None:
    """🔴 刀②b-4：只挪末位一枚数（最像「手滑」的那一形）—— 逐枚等值那把尺必须立刻点名。"""
    cells = ledger.derived()
    for item in TOOL.READOUT_CITES:
        truth = cells[item["key"]]
        fudged = ledger.mutate_cell(live_text(), item["label"], ledger.shift(truth, -1))
        report = TOOL.compare(root=REPO, text=fudged)
        assert len(report["red"]) == 1 and item["label"] in report["red"][0], (item["label"], report["red"])


# ------------------------------------------------------------------ (c) 符号写错层


@pytest.mark.parametrize("key,anchors,claim", [
    ("eval_denominator", WRONG_LAYER_DENOMINATOR, "恒按全部题数算"),
    ("unsupported_claim_rate", WRONG_LAYER_LATENCY, '"unsupported_claim_rate": round('),
    ("report_denominator_code", WRONG_LAYER_PRE_APPROVAL, '"total": len(rows),'),
    ("report_denominator_code", WRONG_LAYER_ONE_LINE_ONLY, "answer_correctness"),
    ("cache_guard", WRONG_LAYER_CACHE_APPROVE, "命中答案缓存"),
    ("cache_guard", WRONG_LAYER_CACHE_BLIP, 'if out["cached"]:'),
])
def test_a_wrong_layer_anchor_is_refused_by_name(key: str, anchors: dict, claim: str) -> None:
    """🔴 刀②c：六枚错层锚各配一次拒绝 —— 量具点名「写错层／引的不是那道闸」，一枚数都不端。

    诱饵与正解之间差的不是数字大小，是**那一格站在哪一层**：报错文案里写着「分子踩在了全部题数上」
    的两行不是分母读点，名字带「率」的两枚常量不是那把率，旧口径那把尺的分母不是主分母。
    """
    with pytest.raises(TOOL.CoordinateUnavailable) as err:
        TOOL.resolve_site(key, REPO, with_anchor(key, anchors))
    message = str(err.value)
    assert claim in message, message
    assert ("写错层" in message) or ("引的不是那道闸" in message), message


def test_the_layer_gates_trip_one_by_one_and_name_their_own_wording() -> None:
    """🔴 四把层判据分得开：每摘一把，对应那一形的诱饵就不再有名字（本件用改判据来验，不靠数行号）。"""
    trips = [
        ({"must_start": "LATENCY_LEDGER_RATIO_TOLERANCE"}, "起头"),
        ({"must_contain": "LATENCY_LEDGER"}, "读不出"),
        ({"next_start": "raise ScorabilityDerivationError("}, "引的不是那道闸"),
        ({"inside_def": "def pre_approval_ruler("}, "引错了层"),
    ]
    for claim, wording in trips:
        with pytest.raises(TOOL.CoordinateUnavailable) as err:
            TOOL.resolve_site("unsupported_claim_rate", REPO, with_claim("unsupported_claim_rate", claim))
        assert wording in str(err.value), (wording, str(err.value))
    for claim, _wording in trips:
        naked = strip_layer_gate(with_claim("unsupported_claim_rate", claim))
        cells, failures = TOOL.derived_cells(REPO, naked)
        assert failures == [], str(failures)
        assert cells["unsupported_claim_rate"] == ledger.derived()["unsupported_claim_rate"], str(claim)


@pytest.mark.parametrize("key,label,anchors", [
    ("eval_denominator", "hitl 分母恒=105", WRONG_LAYER_DENOMINATOR),
    ("unsupported_claim_rate", "C2 算法", WRONG_LAYER_LATENCY),
    ("report_denominator_code", "分母口径·代码腿", WRONG_LAYER_PRE_APPROVAL),
])
def test_a_wrong_layer_cite_stays_red_even_when_the_number_matches(key: str, label: str, anchors: dict) -> None:
    """🔴 刀②c 最硬那一形：把错层那枚「摘掉层判据之后的现读」原样写回那一格（文档与读数自洽），
    在册量具仍然红 —— 因为格子里那句话说的是另一层。摘了牙的量具对此必须绿，否则红不来自那把牙。

    同一枚锚在 :115 与 :182 上挂着两枚格时（`eval_denominator`），两枚一起换：只换一枚的话，
    另一枚的红会混进「摘牙必绿」那条断言里，这枚对照就废了。
    """
    wrong = naked_cell(key, anchors)
    assert wrong != ledger.derived()[key], "错层与正解读到同一行：这刀没砍在层上"
    landed = live_text()
    for item in TOOL.READOUT_CITES:
        if item["key"] == key:
            landed = ledger.mutate_cell(landed, item["label"], wrong)
    toothless = TOOL.compare(root=REPO, sites=strip_layer_gate(with_anchor(key, anchors)), text=landed)
    assert toothless["red"] == [], "摘了层判据还红：本件证不了红来自那把牙 —— " + str(toothless["red"])

    guarded = TOOL.compare(root=REPO, sites=with_anchor(key, anchors), text=landed)
    assert any("写错层" in entry for entry in guarded["red"]), str(guarded["red"])
    assert any(label in entry for entry in guarded["red"]), str(guarded["red"])


def test_the_readout_itself_names_the_layer_it_claims() -> None:
    """文档那一格自己写着「命中即 raise 停窗」「分母恒=105」「unsupported_claim_rate 键；算法」
    「`total=len(rows)`、`answer_correctness=ratio(correct)`」：层判据引的就是它这句话，不是本件编的。"""
    rows = live_text().splitlines()
    by_row = {item["row"]: next(row for row in rows if item["row"] in row) for item in TOOL.READOUT_CITES}
    assert "命中即 raise 停窗" in by_row[cite("C1 缓存命中")["row"]]
    assert "分母恒=105" in by_row[cite("hitl 分母恒=105")["row"]]
    assert "unsupported_claim_rate 键；算法" in by_row[cite("C2 算法")["row"]]
    mouth = by_row[cite("分母口径·代码腿")["row"]]
    assert "的 `total=len(rows)`、`answer_correctness=ratio(correct)` 分母恒为全部 105 题" in mouth, mouth
    for key, phrase in (("eval_denominator", "恒按全部题数算"),
                        ("report_denominator_code", '"total": len(rows),'),
                        ("unsupported_claim_rate", "/ len(results),"),
                        ("cache_guard", "raise RuntimeError(")):
        assert phrase in ledger.block_of(key), key + " 的落点读不出文档那一格说的那句话"


def test_the_teeth_leave_the_tracked_book_byte_for_byte() -> None:
    """🔴 零污染：本件全部变异在内存与进程内锚表上，盘上那三枚文件进门出门同一枚 sha256。"""
    digests = {rel: hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
               for rel in (EVAL, TRANSPORT, READOUT_REL)}
    text = ledger.mutate_cell(live_text(), "hitl 分母恒=105", ledger.shift(ledger.derived()["eval_denominator"], 280))
    TOOL.compare(root=REPO, text=text)
    TOOL.frozen_missing(text)
    TOOL.registered_conflicts(text, ledger.derived())
    for anchors in (WRONG_LAYER_DENOMINATOR, WRONG_LAYER_LATENCY, WRONG_LAYER_PRE_APPROVAL):
        TOOL.derived_cells(REPO, strip_layer_gate(with_anchor("eval_denominator", anchors)))
    for rel, before in digests.items():
        assert hashlib.sha256((REPO / rel).read_bytes()).hexdigest() == before, rel + " 被人就地改写过"
