# -*- coding: utf-8 -*-
"""R215 判据②③④：让量具认得「受控末帧纠正」，但不给它留任何撒谎空间。

分工：``tests/test_r215_recomputing_run6_frames.py`` 钉「原始账不许漂」，本件钉「新格子
凭什么才有资格亮起来」。全程离线：喂的是合成 SSE 字节，走的是量具**真收端**那几件函数
（``_consume`` / ``_count_text_frame`` / ``_fold_frames`` / ``_corrective_readings`` /
``_frame_readings`` / ``_frame_verdict``），外加 R210 那枚真 /ask 断流轮。

豁免四条（与 ``_corrective_readings`` 的码同名）：
  ① 坏形那一枚是**这一条流的末帧**；② 本轮至多一枚；③ 它前面**紧邻**一枚
  ``step(tool=answer_correction, status=running)``；④ 末帧正文与最终交付的 ``answer`` 逐字相等。
四类反例各一枚（③ 还带三个变体），每一条都当场读「不豁免」。

🔴 一把尺：本件不写第二份帧账，也不折叠屏上的字（那是 R210 那件的活）；这里只把线上真到达的
事件喂进收端。``_wire_readings`` 是唯一一枚跨件出口，R210 那枚原本 skip 的用例复用它。
"""

import ast
import importlib.util
import json
from pathlib import Path

import pytest

from app.api.v1 import chat

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r215_correction_ruler", REPO_ROOT / "scripts" / "eval_transport_ask_v2.py")
ruler = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ruler)

from tests.test_r210_break_replaces_the_screen import (  # noqa: E402  -- 同一条链，不造第二份
    DIE_AFTER_FRAMES,
    _readings,
    _round,
    _text_contents,
    _wire,
)

#: 判据① 点名不许漂的那几格（``first_break_at`` 活在 ``per_stream`` 里）。
RAW_CELLS = ("text_frames", "prefix_breaks", "missing_chars", "extra_chars", "answer_sha",
             "last_frame_covers_answer", "last_frame_chars", "answer_chars",
             "streams", "max_stream_frames", "per_stream")

HALF_A = "一线城市住宿费为每晚 500 元"
HALF_B = "一线城市住宿费为每晚 500 元，凭发票按实际发生额报销"
REPLY = "本轮模型未能完成，已改用离线口径回答：请补充制度文件之后再试一次。"
OTHER_SOURCE = "另一条来源给出的整段答案，和刚才那半截真话没有一个字相同。"


# ==================== 合成流：喂进量具真收端 ====================


def _lines(events):
    """把 ``(事件名, 载荷)`` 序列编成 SSE 字节行 —— 服务端就是这么写的。"""
    lines = []
    for name, payload in events:
        lines.append(("event: " + name).encode("utf-8") + b"\n")
        lines.append(("data: " + json.dumps(payload, ensure_ascii=False)).encode("utf-8") + b"\n")
        lines.append(b"\n")
    return lines


def _text(content):
    return ("text", {"type": "text", "content": content})


def _step(tool, status):
    return ("step", {"type": "step", "tool": tool, "label": tool, "status": status})


def _arm():
    """R210 守卫在收尾那枚帧**前面紧邻**发的那一枚：前端就是被它武装成整段替换的。"""
    return _step(chat.CORRECTION_STEP_TOOL, "running")


def _wedge():
    """夹在 step 与帧之间的一枚无关事件 —— 用来打掉「紧邻」。"""
    return ("status", {"type": "status", "content": "🔍 正在分析您的问题..."})


def _stream(*events):
    out = ruler._blank_observation("sess-r215")
    ruler._consume(_lines(list(events)), out)
    return out


def _readings_of(streams, answer=None):
    """几条流折成一题的账 —— 与 ``transport`` / ``_resolve_hitl`` 走同一组函数。

    ``answer`` 不给就是「交付的正文 = 最后那枚非空帧」；给了就是采集器真正交回评分器的那份字
    （含哨兵替换）：判据④ 要比的正是这个。
    """
    ledger = ruler._new_frame_ledger()
    delivered = ""
    for events in streams:
        out = _stream(*events)
        if out["answer"]:
            delivered = out["answer"]
        ruler._fold_frames(ledger, out)
    return ruler._frame_readings(ledger, delivered if answer is None else str(answer))


def _frame_only_readings(contents, answer):
    """R203 / R210 那两枚 ``_readings`` 的办法：只喂 text 帧正文，step 在半路丢掉。

    留着它不是为了另一把尺，而是为了钉住**方向**：掉了 step 的那条路拿不到证词，永远豁免不了
    —— 豁免只可能来自线上真到达的那枚武装帧。
    """
    out = ruler._blank_observation("sess-r215")
    for content in contents:
        ruler._count_text_frame(out, content)
        if content:
            out["answer"] = content
    return ruler._frame_readings(ruler._fold_frames(ruler._new_frame_ledger(), out), answer)


def _wire_readings(body, answer=None):
    """把一真轮的整条 SSE 字面喂进真收端（跨件出口：R210 那枚用例复用这一枚）。"""
    return _readings_of([_wire(body)], answer)


# ==================== 认得：受控纠正不再冒充断流 ====================


def test_a_controlled_correction_reads_as_one_replacement_not_a_break():
    """①②③④ 全中：坏形恰一枚、恰在末帧、恰被那枚 step 武装、恰等于交付的那份字。"""
    readings = _readings_of([[
        _text(HALF_A), _text(HALF_B), _arm(), _text(REPLY),
        _step(chat.CORRECTION_STEP_TOOL, "done"),
    ]])

    assert readings["prefix_breaks"] == 1, readings           # 原始账照记不误
    assert readings["per_stream"][0]["first_break_at"] == readings["text_frames"], readings
    assert readings["corrective_replacements"] == 1, readings
    assert readings["uncorrected_breaks"] == 0, readings
    assert readings["text_frames"] == 3 and readings["max_stream_frames"] == 3, readings
    assert ruler._frame_verdict(readings) is True, readings


def test_the_raw_ledger_is_identical_with_and_without_the_wire_testimony():
    """豁免不等于撒谎：同一批帧，摘掉 step 之后原始账逐格不变，只是豁免拿不到。"""
    frames_only = _frame_only_readings([HALF_A, HALF_B, REPLY], REPLY)
    from_wire = _readings_of([[_text(HALF_A), _text(HALF_B), _arm(), _text(REPLY)]])

    for cell in RAW_CELLS:
        assert frames_only[cell] == from_wire[cell], cell
    assert frames_only["prefix_breaks"] == from_wire["prefix_breaks"] == 1
    # 差别只许落在新增的两格上，而且方向唯一：有线上证词才可能豁免。
    assert frames_only["corrective_replacements"] == 0, frames_only
    assert frames_only["uncorrected_breaks"] == 1, frames_only
    assert from_wire["corrective_replacements"] == 1, from_wire
    assert from_wire["uncorrected_breaks"] == 0, from_wire
    assert ruler._frame_verdict(frames_only) is False, frames_only
    assert ruler._frame_verdict(from_wire) is True, from_wire


def test_a_real_broken_round_from_the_route_grants_exactly_one_replacement(monkeypatch, tmp_path):
    """真 /ask 断流轮（R210 那台半路死的 provider）：量具现在读得出「这是一次纠正」。"""
    ask = _round(monkeypatch, tmp_path, [("doc", None)], die_after=DIE_AFTER_FRAMES)
    body = ask()
    contents = _text_contents(body)
    delivered = str(ask.handed_back["doc"])

    assert contents[-1] == delivered, "末帧不是交付的那份字，判据④ 的前提先破了"
    readings = _wire_readings(body)
    assert readings["text_frames"] == len(contents), readings
    assert readings["prefix_breaks"] == 1, readings
    assert readings["corrective_replacements"] == 1, readings
    assert readings["uncorrected_breaks"] == 0, readings
    assert ruler._frame_verdict(readings) is True, readings
    # 同一条流、同一批帧，只把 step 摘掉 —— 立刻读回那枚红。
    assert _readings(body)["corrective_replacements"] == 0, _readings(body)
    assert _readings(body)["uncorrected_breaks"] == 1, _readings(body)


# ==================== 反例① 中途坏形：不是末帧就不许豁免 ====================


@pytest.mark.parametrize("shape, events, delivered", [
    # 只有 ① 拦得住这一格：坏形前面站着武装 step（③ 过），坏形那一枚正文恰等于交付的终答
    # （④ 过），本轮也只有它一枚候选（② 过）—— 唯一的理由是它**不是末帧**，后面流还在往前走。
    ("换源之后流又往前长了一截",
     [_text(HALF_A), _text(HALF_B), _arm(), _text(REPLY), _text(REPLY + "的后半")], REPLY),
    # 同一枚形状的最朴素版本：末帧与坏形同一份字，交付的也是它 —— 仍然只有 ① 拦得住。
    ("换源之后又重复发了同一枚帧",
     [_text(HALF_A), _text(HALF_B), _arm(), _text(REPLY), _text(REPLY)], None),
], ids=["grew-after-replacement", "repeated-frame"])
def test_a_break_in_the_middle_is_never_exempt_even_when_it_is_armed(shape, events, delivered):
    """①：中途坏形**只**因为「不是末帧」这一条不豁免 —— 摘掉 ① 这枚当场红。

    反证 a 的施加方式：把 ``_corrective_readings`` 里 ``at != stream_frames`` 那一格改成恒假，
    这一枚读到 ``corrective_replacements == 1`` 立刻红（其余三条它在构造上就满足）。
    """
    readings = _readings_of([events], delivered)

    assert readings["text_frames"] == 4, readings
    assert readings["prefix_breaks"] == 1, (shape, readings)
    assert readings["per_stream"][0]["first_break_at"] == 3, (shape, readings)  # 坏在中间
    assert readings["max_stream_frames"] == 4, readings
    assert readings["corrective_replacements"] == 0, (shape, readings)
    assert readings["uncorrected_breaks"] == 1, (shape, readings)
    assert ruler._frame_verdict(readings) is False, (shape, readings)


# ==================== 反例② 一轮两枚：第二枚不许豁免 ====================


def test_a_second_correction_in_the_same_round_is_not_exempt():
    """两条流各末帧换源一次：本轮至多一枚，第二枚仍然是断流。"""
    first = [_text(HALF_A), _arm(), _text(REPLY)]
    second = [_text("恢复轮写出来的半截真话"), _arm(), _text(REPLY)]
    readings = _readings_of([first, second], answer=REPLY)

    assert readings["streams"] == 2, readings
    assert readings["text_frames"] == 4, readings
    assert readings["prefix_breaks"] == 2, readings
    assert readings["corrective_replacements"] == 1, readings
    assert readings["uncorrected_breaks"] == 1, readings
    assert ruler._frame_verdict(readings) is False, readings


# ==================== 反例③ 没有那枚 step：字节流形状蒙不过去 ====================


@pytest.mark.parametrize("shape, events", [
    ("根本没有那枚 step", [_text(HALF_A), _text(REPLY)]),
    ("step 是 done 不是 running", [_text(HALF_A), _step(chat.CORRECTION_STEP_TOOL, "done"),
                                   _text(REPLY)]),
    ("running 但是别的 tool", [_text(HALF_A), _step("doc", "running"), _text(REPLY)]),
    ("step 与帧之间还夹了一枚事件", [_text(HALF_A), _arm(), _wedge(), _text(REPLY)]),
], ids=["no-step", "step-done", "step-other-tool", "step-not-adjacent"])
def test_a_source_switch_without_the_arming_step_is_not_exempt(shape, events):
    """③：只靠「短一截、换个头、又变长」这套字节形状，一枚都豁免不了。"""
    readings = _readings_of([events])

    assert readings["prefix_breaks"] == 1, shape
    assert readings["per_stream"][0]["first_break_at"] == readings["text_frames"], shape
    assert readings["corrective_replacements"] == 0, (shape, readings)
    assert readings["uncorrected_breaks"] == 1, (shape, readings)
    assert ruler._frame_verdict(readings) is False, (shape, readings)


# ==================== 反例④ 屏上没真替换：换源没换成交付的那份字 ====================


def test_a_source_switch_that_never_reached_the_screen_is_not_exempt():
    """④：末帧换了源、step 也在，可交付的终答不是那枚帧 ⇒ 屏上没整段替换，不豁免。"""
    events = [[_text(HALF_A), _arm(), _text(REPLY)]]

    on_screen = _readings_of(events)                       # 交付 = 末帧：这才是真纠正
    substituted = _readings_of(events, answer="<approval-failed-no-terminal-answer>")

    assert on_screen["corrective_replacements"] == 1, on_screen
    assert substituted["corrective_replacements"] == 0, substituted
    assert substituted["uncorrected_breaks"] == 1, substituted
    assert substituted["prefix_breaks"] == 1, substituted   # 原始账一格不动
    assert substituted["extra_chars"] > 0, substituted      # 终答里有一截没上屏的字
    assert ruler._frame_verdict(substituted) is False, substituted


# ==================== 判据④ 的既有条件：一枚不许松 ====================


def test_the_verdict_still_refuses_a_round_where_the_last_frame_outruns_the_answer():
    """``missing_chars`` 这一格今天真的咬人：末帧比交付的终答多一截 ⇒ 判据② 读 False。"""
    readings = _readings_of(
        [[_text(HALF_A), _text(HALF_B), _text(HALF_B + "多余的一截")]], answer=HALF_B)

    assert readings["prefix_breaks"] == 0, readings
    assert readings["extra_chars"] == 0, readings              # covering：末帧盖住了终答
    assert readings["last_frame_covers_answer"] is True, readings
    assert readings["missing_chars"] == len("多余的一截"), readings
    assert ruler._frame_verdict(readings) is False, readings


def test_the_verdict_still_refuses_rounds_that_never_streamed():
    """一帧到底、两条单帧流：判据② 要的「同一条流里累计」不成立，零坏形也不算绿。"""
    one_frame = _readings_of([[_text(REPLY)]])
    two_single = _readings_of([[_text(HALF_A)], [_text(REPLY)]], answer=REPLY)

    assert one_frame["prefix_breaks"] == 0 and one_frame["uncorrected_breaks"] == 0
    assert ruler._frame_verdict(one_frame) is False, one_frame
    assert two_single["text_frames"] == 2, two_single
    assert two_single["max_stream_frames"] == 1, two_single
    assert ruler._frame_verdict(two_single) is False, two_single


def test_the_new_cells_observed_only_and_never_touched_the_scoring_paths():
    """只观测不改评分：交付正文的取法、step 计数、哨兵替换这三条老路一个字没动。"""
    source = (REPO_ROOT / "scripts" / "eval_transport_ask_v2.py").read_text(encoding="utf-8")

    assert 'answer = out["answer"]' in source          # 末帧覆盖前帧：answer 口径没动
    assert 'out["steps"] += 1' in source               # step 仍然只留给 R38 用量审计
    assert 'row["criterion_two_holds"] = _frame_verdict(readings)' in source
    assert source.count("def _record_frames") == 1     # 落盘动作仍然只有一处
    assert "APPROVAL_FAILED_SENTINEL, " in source      # 批准失败的哨兵照旧


# ==================== 焊条：量具认的那枚 tool 与产品发的必须是同一枚 ====================


def test_the_ruler_mirrors_the_guard_tool_name_byte_for_byte():
    """上游改名 ⇒ 豁免当场失效（宁可少豁免）；这枚焊条保证「改名」不会被静默吞掉。"""
    assert ruler.CORRECTION_STEP_TOOL == chat.CORRECTION_STEP_TOOL
    assert chat.CORRECTION_STEP_TOOL == "answer_correction"
    # 量具仍然不许 import app：它得能被 importlib 单独加载（R181 / R203 都靠这一点）。
    # 只认真 import 语句（AST），别拿「注释里出现了 app 两个字」当证据。
    source = (REPO_ROOT / "scripts" / "eval_transport_ask_v2.py").read_text(encoding="utf-8")
    imported = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported += [one.name for one in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not [n for n in imported if n == "app" or n.startswith("app.")], imported