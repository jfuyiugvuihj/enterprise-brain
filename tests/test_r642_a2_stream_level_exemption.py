# -*- coding: utf-8 -*-
"""R642 判据②：A② 甲案（豁免第④条从轮级比源改成流级比源），两把刀都当场跑。

``_corrective_readings`` 的 ① ② ③ 一字未动，今天只把第④条的**比对对象**从「本轮交回评分器的
那份字」换成「它所在那一条流自己交付的那份字」—— 同一条流内不许换源，跨流不许互相比源。
归因不在本件里复述，凭据是 ``docs/perf/r614-uncorrected-break-attribution-2026-10-03.md``
（两窗 19/19 挂起轮的终答都比挂起轮那份字长 ⇒ 轮级那一条对这一族恒假）。本件只干三件事：

1. 正控（判据② 左半）：一枚 ``approved_ok`` 形状的同轮双流 trace —— 换源发生在挂起轮
   （stream 0）、交付来自批准腿（stream 1）、终答以挂起轮那份字为前缀。同一份 trace 喂两棵树：
   退回轮级比源的影子端必须红（``uncorrected_breaks == 1``），改后的活体端必须绿（== 0）。
2. 反证刀（判据② 右半，🔴 本单主刀）：真断流 —— 屏上换成了**另一份**答案，不是接着往下写。
   改后仍必须判红并点名。这一把自己也咬一次：摘掉 (c) 前缀闸的影子端会把它洗成绿 ⇒ 证明闸真的
   站着，不是一句装饰。「宁可少豁免一次，不可多豁免一次」在账上的形状就是这个。
3. 不变量：原始账不漂（``prefix_breaks`` 等逐格与影子端同数）、R215 那枚恒等式两边都成立、
   单流轮逐格一字不变、帧账一行的键集一格不多（🔴 判定用的「每条流交付的文本」只活在内存里，
   与 ``break_frames`` 同一格纪律），``_frame_verdict`` 这一腿依旧不读 ``prefix_breaks``。

全部离线：只按文件名单独加载量具（不 import app.**，零容器零连库零模型）；变异一律落 tmp_path
影子副本（R253 纪律），跑完现读被跟踪原件的指纹，必须与 import 那一刻逐字节相同。
"""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from tests import _r259_queue_ruler as Q

REPO = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO / "scripts" / "eval_transport_ask_v2.py"
#: 被跟踪原件在 import 那一刻的指纹：所有影子道跑完必须还它一个字不动。
IMPORT_SHA = hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest()

HALF_A = "据统计，Q3 营收 1200"
HALF_B = "据统计，Q3 营收 1200 万元，环比"
PARK = "挂起轮交付的那份正文，先停在闸前等确认。"
FINAL = PARK + "批准后接着往下写的那一截，把同一段补完。"
OTHER = "批准腿另起炉灶交回的另一份答案，与挂起轮那份字没有一个字重合。"
SENTINEL_TEXT = "<approval-failed-no-terminal-answer>"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load(SCRIPT_PATH, "r642_a2_live")

#: 影子端的四把刀：每把都按唯一锚点摘掉一处判定。锚点不唯一当场红 —— 空响的刀不算刀。
ROUND_LEVEL = (
    '        if not _stream_level_correction(str(record.get("text") or ""), answer_text,\n'
    '                                        frames.get("stream_deliveries"),\n'
    '                                        int(record.get("stream") or 0)):\n'
    '            continue  # ④ 轮级/流级两条比源都不成立：屏上没真替换成交付的那份字\n',
    '        if str(record.get("text") or "") != answer_text:\n'
    '            continue  # 影子端：把第④条退回 R642 之前的轮级比源\n',
)
DROP_PREFIX_GATE = (
    '    return bool(frame_text) and answer_text.startswith(frame_text)  # (c) 终答以它为前缀\n',
    '    return bool(frame_text)  # 影子端：摘掉 (c) 前缀闸\n',
)
DROP_DELIVERY_GATE = (
    '    if frame_text != deliveries[stream]:\n'
    '        return False  # (b) 同一条流内换了源\n',
    '    if False:  # 影子端：摘掉 (b) 流内交付比对\n'
    '        return False  # 影子端：(b) 不再拦阻\n',
)
DROP_EMPTY_GUARD = (
    '    return bool(frame_text) and answer_text.startswith(frame_text)  # (c) 终答以它为前缀\n',
    '    return answer_text.startswith(frame_text)  # 影子端：连空帧那一道 guard 一起摘\n',
)


def _shadow(tmp_path, name, *knives):
    """把量具复制进 tmp_path、只按锚点动刀，再加载那份副本。🔴 原件一枚字节都不许动。"""
    before = SCRIPT_PATH.read_bytes()
    text = before.decode("utf-8").replace("\r\n", "\n")
    for anchor, replacement in knives:
        assert text.count(anchor) == 1, "锚点在原件里不唯一，这枚反证是空的：" + anchor[:60]
        text = text.replace(anchor, replacement, 1)
    assert text != before.decode("utf-8").replace("\r\n", "\n"), "反证没作用到东西上"
    target = tmp_path / ("shadow-" + name) / "scripts" / "eval_transport_ask_v2.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    module = _load(target, "r642_shadow_" + name)
    assert hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest() == IMPORT_SHA, "影子道动了原件"
    return module


def _lines(events):
    out = []
    for name, payload in events:
        out.append(("event: " + name + "\n").encode("utf-8"))
        out.append(("data: " + json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        out.append(b"\n")
    return out


def _text(content):
    return ("text", {"type": "text", "content": content})


def _arm():
    return ("step", {"type": "step", "tool": adapter.CORRECTION_STEP_TOOL,
                     "label": "answer_correction", "status": "running"})


def _readings(module, streams, answer=None):
    """几条流折成一题的账（与 transport / _resolve_hitl 走同一组函数），交回判定层读数。"""
    ledger = module._new_frame_ledger()
    delivered = ""
    for events in streams:
        out = module._blank_observation("sess-r642")
        module._consume(_lines(events), out)
        if out["answer"]:
            delivered = out["answer"]
        module._fold_frames(ledger, out)
    return module._frame_readings(ledger, delivered if answer is None else str(answer))


PARK_ROUND = [[_text(HALF_A), _text(HALF_B), _arm(), _text(PARK)], [_text(FINAL)]]
SWITCHED = [[_text(HALF_A), _text(HALF_B), _arm(), _text(PARK)], [_text(OTHER)]]
LAST_STREAM_BREAK = [[_text(HALF_B)], [_text(HALF_A), _arm(), _text(PARK)]]
EMPTY_TAIL = [[_text(HALF_B), _arm(), _text("")], [_text(HALF_B + "接着写的一截")]]
TWO_BREAKS = [[_text(HALF_A), _arm(), _text(PARK)], [_text(HALF_B), _arm(), _text(PARK)]]
SINGLE_CONTROLLED = [[_text(HALF_A), _text(HALF_B), _arm(), _text(FINAL)]]
SINGLE_NO_ARM = [[_text(HALF_A), _text(HALF_B), _text(FINAL)]]
SINGLE_MIDBREAK = [[_text(HALF_A), _arm(), _text(FINAL), _text(FINAL + "又长一截")]]

#: 逐格对照用的原始账（R215 判据① 点名的那几格）。
RAW_CELLS = ("text_frames", "prefix_breaks", "missing_chars", "extra_chars",
             "last_frame_covers_answer", "last_frame_chars", "last_frame_sha",
             "answer_chars", "answer_sha", "streams", "max_stream_frames", "per_stream")


def _assert_identity(readings):
    """R215 那枚恒等式：豁免只把坏形分家，原始账一格不漂。"""
    assert readings["prefix_breaks"] == (readings["corrective_replacements"]
                                        + readings["uncorrected_breaks"]), readings


# ==================== 一、正控：挂起轮内那一次换源，改前红／改后绿 ====================


def test_the_park_round_switch_is_red_before_the_fix_and_green_after(tmp_path):
    """同一份 trace 两棵树各跑一遍：影子端（轮级比源）红，活体端（流级比源）绿。"""
    old = _shadow(tmp_path, "round-level", ROUND_LEVEL)
    readings_old = _readings(old, PARK_ROUND)
    readings_new = _readings(adapter, PARK_ROUND)

    assert readings_old["prefix_breaks"] == readings_new["prefix_breaks"] == 1, (
        readings_old, readings_new)
    assert readings_old["corrective_replacements"] == 0, readings_old
    assert readings_old["uncorrected_breaks"] == 1, readings_old
    assert old._frame_verdict(readings_old) is False, readings_old
    assert readings_new["corrective_replacements"] == 1, readings_new
    assert readings_new["uncorrected_breaks"] == 0, readings_new
    assert adapter._frame_verdict(readings_new) is True, readings_new
    _assert_identity(readings_old)
    _assert_identity(readings_new)


def test_the_stream_level_branch_only_applies_to_a_non_last_stream():
    """(a)：末流那一族的坏形只认轮级那一条 —— 单流轮（同步道全部形状）口径一字不动。"""
    readings = _readings(adapter, LAST_STREAM_BREAK, answer=SENTINEL_TEXT)
    assert readings["prefix_breaks"] == 1, readings
    assert readings["corrective_replacements"] == 0, readings
    assert readings["uncorrected_breaks"] == 1, readings
    assert adapter._frame_verdict(readings) is False, readings
    _assert_identity(readings)


# ==================== 二、反证刀：真断流改后仍判红，闸自己会咬 ====================


def test_a_round_that_switched_to_another_answer_still_reads_red(tmp_path):
    """主刀（判据② 右半）：屏上换成**另一份**答案，不是接着往下写 ⇒ 一枚都不许豁免。

    同一把刀再割一次：摘掉 (c) 前缀闸的影子端会把这一形洗成绿 ⇒ (c) 真的站着，本枚刀不空响。
    """
    readings = _readings(adapter, SWITCHED)
    assert readings["corrective_replacements"] == 0, readings
    assert readings["uncorrected_breaks"] == 1, readings
    assert adapter._frame_verdict(readings) is False, readings
    loose = _shadow(tmp_path, "no-prefix-gate", DROP_PREFIX_GATE)
    washed = _readings(loose, SWITCHED)
    assert washed["corrective_replacements"] == 1 and washed["uncorrected_breaks"] == 0, washed
    assert loose._frame_verdict(washed) is True, washed


def test_an_empty_tail_frame_is_not_launched_as_a_correction(tmp_path):
    """末帧是一枚空帧那一形：(b) 与空帧 guard 互为双保险，单独摘一枚另一枚还站着。"""
    readings = _readings(adapter, EMPTY_TAIL)
    assert readings["prefix_breaks"] == 1, readings
    assert readings["corrective_replacements"] == 0, readings
    assert adapter._frame_verdict(readings) is False, readings
    only_b = _shadow(tmp_path, "no-delivery-gate", DROP_DELIVERY_GATE)
    assert _readings(only_b, EMPTY_TAIL)["corrective_replacements"] == 0, (
        "摘掉 (b) 就放行 ⇒ guard 那一枚是空的")
    only_guard = _shadow(tmp_path, "no-empty-guard", DROP_EMPTY_GUARD)
    assert _readings(only_guard, EMPTY_TAIL)["corrective_replacements"] == 0, (
        "摘掉 guard 就放行 ⇒ (b) 那一枚是空的")
    both = _shadow(tmp_path, "both-gates", DROP_DELIVERY_GATE, DROP_EMPTY_GUARD)
    assert _readings(both, EMPTY_TAIL)["corrective_replacements"] == 1, (
        "两枚一起摘还拦得住 ⇒ 这两把刀都是空的")


def test_two_breaks_in_one_round_still_grant_at_most_one():
    """② 本轮至多一枚：两条流各换源一次，第二枚仍然是断流（在册口径不变）。"""
    readings = _readings(adapter, TWO_BREAKS, answer=PARK)
    assert readings["prefix_breaks"] == 2, readings
    assert readings["corrective_replacements"] == 1, readings
    assert readings["uncorrected_breaks"] == 1, readings
    assert adapter._frame_verdict(readings) is False, readings
    _assert_identity(readings)


# ==================== 三、不变量：原始账不漂、单流轮不动、键集一格不多 ====================


@pytest.mark.parametrize("shape,streams", [
    ("正控双流", PARK_ROUND),
    ("换成另一份答案", SWITCHED),
    ("末流坏形", LAST_STREAM_BREAK),
    ("空尾帧", EMPTY_TAIL),
    ("一轮两枚", TWO_BREAKS),
    ("单流受控纠正", SINGLE_CONTROLLED),
    ("单流无武装 step", SINGLE_NO_ARM),
    ("单流中途坏形", SINGLE_MIDBREAK),
])
def test_the_raw_ledger_is_identical_on_both_trees(shape, streams, tmp_path):
    """改前改后只差在「豁免分家」那两格：原始账逐格同数，恒等式两边都成立。"""
    old = _shadow(tmp_path, "round-level-" + str(abs(hash(shape))), ROUND_LEVEL)
    before = _readings(old, streams)
    after = _readings(adapter, streams)
    for cell in RAW_CELLS:
        assert before[cell] == after[cell], (shape, cell, before[cell], after[cell])
    _assert_identity(before)
    _assert_identity(after)


@pytest.mark.parametrize("answer", [None, FINAL, SENTINEL_TEXT, ""])
def test_single_stream_rounds_are_untouched_on_every_answer(answer, tmp_path):
    """同步流道那一族（单条流）在两套读法下逐格相同 ⇒ 历轮可比性不许被打断。"""
    old = _shadow(tmp_path, "round-level-single", ROUND_LEVEL)
    live = _readings(adapter, SINGLE_CONTROLLED, answer)
    base = _readings(old, SINGLE_CONTROLLED, answer)
    assert live == base, (answer, live, base)


def test_the_verdict_leg_still_does_not_read_prefix_breaks():
    """🔴 本腿不吃 prefix_breaks：那条恒等式不许被顺手统一（AST 现读用集，不搜散文）。"""
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    verdict = next(node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == "_frame_verdict")
    read = set()
    for node in ast.walk(verdict):
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                and node.value.id == "readings" and isinstance(node.slice, ast.Constant)):
            read.add(str(node.slice.value))
    assert "prefix_breaks" not in read, read
    assert "uncorrected_breaks" in read, read


def test_the_frame_row_key_set_did_not_move_and_the_gate_still_flips(tmp_path):
    """键集闸可翻面（判据③）：本单没往帧账顶层加一列，而那枚闸确实会红，不是摆设。"""
    module = _load(SCRIPT_PATH, "r642_a2_transport")
    Q.configure(module, tmp_path, name="r642-a2")
    module._open = Q.Transport(
        ask_events=[_text(HALF_A), _text(HALF_B), _arm(), _text(PARK),
                    ("hitl", {"type": "hitl", "pending": ["export"]}),
                    ("done", {"type": "done"})],
        statuses=[],
        approvals=[[_text(FINAL), ("done", {"type": "done"})]])
    module.transport({"id": "report-99", "question": "给一题"})

    rows = Q.read_jsonl(module.frame_ledger_path())
    assert len(rows) == 1, rows
    row = rows[0]
    assert set(row) == Q.FRAME_ROW_KEYS, set(row) ^ Q.FRAME_ROW_KEYS
    assert row["kind"] == "approved_ok" and row["streams"] == 2, row
    assert row["prefix_breaks"] == 1 and row["corrective_replacements"] == 1, row
    assert row["uncorrected_breaks"] == 0 and row["criterion_two_holds"] is True, row
    assert "stream_deliveries" not in row, "内存态那一格漏进账上了（原始账不许漂）"
    # 翻面：把任何一格冒充成顶层列 promote 进账，同一枚对判必须红；收回去立刻绿。
    promoted = dict(row)
    promoted["stream_deliveries"] = [PARK]
    assert set(promoted) != Q.FRAME_ROW_KEYS, "键集闸是摆设：多一列它都不响"
    demoted = dict(promoted)
    demoted.pop("stream_deliveries")
    assert set(demoted) == Q.FRAME_ROW_KEYS
    # 少一列同样响：把在册那一格摘掉 ⇒ 证明它是**对判**，不是子集。
    missing = dict(row)
    missing.pop("prefix_breaks")
    assert set(missing) != Q.FRAME_ROW_KEYS, "键集闸松成了子集"


def test_the_tracked_ruler_is_byte_identical_after_every_shadow_proof():
    """影子道跑完，被跟踪原件必须与 import 那一刻逐字节相同（R253 纪律）。"""
    assert hashlib.sha256(SCRIPT_PATH.read_bytes()).hexdigest() == IMPORT_SHA