# -*- coding: utf-8 -*-
"""R662 判据①②③④ · 批准跑道那一侧：屏上只挂着挂起说明时，续跑那一发必须逐字上屏。

在册病形（凭据纸 ``docs/testing/r662-a2-single-frame-rows-2026-10-05.md``，代次 ``9556513``）：
run22 ``chart-01``／``tool-04`` 两行 ``kind=approved_ok``（**不是没答**），帧账却是
``text_frames=2``／``max_stream_frames=1``／``per_stream=[1, 1]`` —— 挂起轮交一枚 37 字的
挂起说明，批准轮交一枚整段终答。批准腿那一发的逐片帧**确实生成出来了**（出口真响），
但被 ``app/api/v1/chat.py::_ApprovedAnswerStream.decide`` 的规则 2 整批拦在闸门外：
那道闸把「与屏上那份不同源的非收尾整段」当第二枚终答流 held 下来。屏上此刻站着的如果只是
那句挂起说明，本轮就还没有任何终答上过屏，这一发是**第一枚**终答流，不是第二枚。

本件钉的是那一格（``_ApprovedAnswerStream.decide`` 的 ``opening`` 分支），四枚判据逐条点名：

- **①** 成形答复的 ``text`` 事件数 >1；
- **②** 逐片递增且不重叠（片区间 + 在册尺抄下的 ``arrival_at`` 一列非减）；
- **③** 拼接逐字等于终答全文（``missing_chars == 0`` 且 ``extra_chars == 0``）；
- **④** 末帧覆盖终答末尾（``last_frame_covers_answer``）—— ``chart-04`` 那一形红的就是它。

🔴 两枚反证牙在本件：摘掉 ``opening`` 那一格必须红并点名题号（刀 C）；把真帧的末帧少一个字
喂进在册尺必须红（刀 D）。
🔴 一枚方向钉在本件：屏上挂着**真答复**（R464 病历的常态、run22 那 19 枚 ``approved_ok``
的共同形状）时，逐片帧照旧一枚都不许上屏，也不许把闸门灌满误报。这一格护住的是「不许为了
翻绿把 17 枚绿题打成红」。

判分只用一把尺：``scripts/eval_transport_ask_v2.py`` 的 ``_frame_readings``／``_frame_verdict``
（经 ``tests/test_r662_formed_answer_streams_progressively.py::_round_readings``，与在册
``_record_frames`` 同一组合）。本件不改夹具、不改判分器、不自造分母。
"""

import ast
import asyncio
import inspect
import logging
import textwrap

import pytest
from langchain_core.messages import HumanMessage

from app.agents import nodes, orchestrator
from app.api.v1 import chat

from tests.test_r464_one_terminal_answer_stream_per_round import (  # noqa: F401
    PARK_TEXT,
    PENDING_CHART,
    SESSION_ID,
    _drive_approve,
    _drive_ask,
    _parked_leg,
    _parked_leg_without_body,
    _state,
    finance_principal,
)
from tests.test_r210_break_replaces_the_screen import _correction_steps, _text_contents, _wire
from tests.test_r662_formed_answer_streams_progressively import (  # noqa: F401
    REGISTERED_CHARS,
    SHADOW_KIND,
    SHADOW_WIRE_ENV,
    _record_shadow_wire,
    TOKEN_CHARS,
    _assert_seven_green,
    _formed_body,
    _resilient,
    _round_readings,
    _streaming_handler,
    ruler,
)


# ==================== 真挂起轮 + 真批准腿（假只假在编排那一层） ====================


def _resume_leg(answer, seen, *, worker="chart"):
    """替 ``run_interrupt_stream``：生成腿与收端全真，出口用调用方交来的那一枚。

    打帧按 ``TOKEN_CHARS`` 逐 token（真 provider 的形状），不按 R524 那 18 字一枚：
    31 字那一形按 18 字切只够撞响一枚尺寸闸，那是 R524 自己的病历形状。
    """

    def stream(*_args, **kwargs):
        sink = kwargs.get("stream_piece_sink")

        def spy(piece):
            seen.append(piece)
            if callable(sink):
                sink(piece)

        configurable = {"worker": worker, "request_id": "request-r662",
                        "trace_id": "trace-r662"}
        if callable(sink):
            configurable[nodes.STREAM_PIECE_SINK_KEY] = spy
        message = _resilient(_streaming_handler(answer)).invoke(
            [HumanMessage(content="把上次统计的口径说明一下")],
            config={"configurable": configurable})
        handed = str(getattr(message, "content", "") or "")
        yield {"messages": [], "worker_results": {worker: handed}, "final_answer": handed}

    return stream


@pytest.fixture
def parked(monkeypatch, tmp_path):
    """挂起轮**真**把那一行写进会话历史：``_round_screen_answer`` 读的就是它。

    与 ``tests/test_r464_one_terminal_answer_stream_per_round.py::offline`` 同一分工，
    只多加两处：模型额度（一枚槽、trace 落 tmp）与上下文窗口（按部署在配值给，
    见 ``tests/test_r662_formed_answer_streams_progressively.py`` 里那处注释）。
    """
    from app.common import model_budget
    from app.storage import pending_approvals as approval_store
    from app.storage.sessions import SessionRegistry
    from app.trace import spans
    from app.trace.store import TraceStore

    flag = {"pending": PENDING_CHART}
    monkeypatch.delenv("REPORT_LANE_VIA_QUEUE", raising=False)
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "16384")
    model_budget.reset_default_budget()
    monkeypatch.setattr(approval_store, "_MEM_ROWS", {})
    monkeypatch.setattr(approval_store, "_database_available", lambda: False)
    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "_MEM_SESSIONS", {})
    monkeypatch.setattr(chat, "_MEM_SESSION_MESSAGES", {})
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator, "check_interrupt", lambda _tid: flag["pending"])
    monkeypatch.setattr(spans, "default_trace_store",
                        lambda: TraceStore(tmp_path / "r662-approve.jsonl"))

    registry = SessionRegistry(tmp_path / "sessions.json")
    principal = finance_principal()
    registry.bind(SESSION_ID, principal)
    monkeypatch.setattr(chat, "session_registry", registry)

    ctx = {"monkeypatch": monkeypatch, "flag": flag, "principal": principal,
           "rows": chat._MEM_SESSION_MESSAGES}
    yield ctx
    model_budget.reset_default_budget()


def _round(parked, *, answer, park_answer=None, worker="chart"):
    """跑一整轮：挂起轮（屏上留挂起说明，或留一份真答复）⇒ 批准轮（真生成腿逐片）。"""
    seen: list = []
    ask_stream = (_parked_leg(park_answer, worker=worker) if park_answer is not None
                  else _parked_leg_without_body())
    parked["monkeypatch"].setattr(orchestrator, "run_with_stream", ask_stream)
    parked["monkeypatch"].setattr(orchestrator, "run_interrupt_stream",
                                  _resume_leg(answer, seen, worker=worker))
    ask_body = _drive_ask(parked["principal"])
    parked["flag"]["pending"] = None
    approve_body = _drive_approve(parked["principal"])
    written = [str(row.get("content") or "") for row in parked["rows"][SESSION_ID]
               if str(row.get("role") or "") == "assistant"]
    assert len(written) == 2, written
    return {"ask": ask_body, "approve": approve_body, "pieces": seen,
            "on_screen": written[0], "delivered": written[-1]}

# ==================== 判据①②③④：屏上只挂着挂起说明 ⇒ 逐片上屏 ====================


@pytest.mark.parametrize("question_id", ["chart-01", "tool-04"])
def test_the_approve_leg_reaches_the_screen_piece_by_piece(parked, question_id):
    """改后读数：两条流各交自己那一份，批准流里逐片帧一帧一帧上屏。

    改前在册读数（run22 这两行）：``kind=approved_ok``、``text_frames=2``、
    ``per_stream=[1, 1]``、``max_stream_frames=1``、缺字多字同为 0、末帧覆盖终答
    ⇒ 六枚合取里只有 ``max_stream_frames > 1`` 一枚不成立，红的就是判据①「不许一坨」。
    """
    answer = _formed_body(REGISTERED_CHARS[question_id])
    turn = _round(parked, answer=answer)
    assert turn["on_screen"] == PARK_TEXT, turn["on_screen"]
    assert len(PARK_TEXT) == 37, len(PARK_TEXT)  # run22 这两行的 stream 0 帧长现读
    assert turn["delivered"] == answer, turn["delivered"]

    seen = turn["pieces"]
    assert len(seen) > 1, f"生成腿一枚片都没交到出口：{seen}"
    assert "".join(piece.text for piece in seen) == answer
    ordered = sorted(seen, key=lambda piece: piece.start_at)
    for earlier, later in zip(ordered, ordered[1:]):
        assert later.start_at >= earlier.end_at, (earlier, later)
    assert {piece.worker for piece in seen} == {"chart"}
    assert len({piece.call_id for piece in seen}) == 1

    frames = _text_contents(turn["approve"])
    assert len(frames) > 1, [len(frame) for frame in frames]
    for earlier, later in zip(frames, frames[1:]):
        assert later.startswith(earlier), (earlier, later)
    assert frames[-1] == answer, frames[-1]

    readings, arrivals = _round_readings(
        [_wire(turn["ask"]), _wire(turn["approve"])], answer)
    _assert_seven_green(readings, question_id)
    assert bool(ruler._frame_verdict(readings)) is True, readings
    assert readings["answer_chars"] == REGISTERED_CHARS[question_id]
    assert readings["streams"] == 2, readings
    assert readings["per_stream"][1]["frames"] > 1, readings["per_stream"]
    assert [item.get("arrival_at") for item in arrivals] == sorted(
        item.get("arrival_at") for item in arrivals), arrivals


@pytest.mark.parametrize("question_id", ["chart-01", "tool-04"])
def test_the_round_arms_exactly_one_replacement(parked, question_id):
    """一轮至多换源一次：挂起说明不是答复，换掉它的那一枚 step 只许配对出现一次。"""
    answer = _formed_body(REGISTERED_CHARS[question_id])
    turn = _round(parked, answer=answer)
    steps = _correction_steps(turn["approve"])
    assert len(steps) == 2, steps
    assert [step.get("status") for step in steps] == ["running", "done"], steps
    assert _correction_steps(turn["ask"]) == [], _correction_steps(turn["ask"])


def test_the_notice_never_counts_as_a_second_delivery(parked):
    """R471 那一格不许被这次放宽碰响：挂起说明与答复逐帧指纹重合数必须恒 0。"""
    answer = _formed_body(REGISTERED_CHARS["tool-04"])
    turn = _round(parked, answer=answer)
    readings, _arrivals = _round_readings(
        [_wire(turn["ask"]), _wire(turn["approve"])], answer)
    assert readings["cross_stream_repeat_frames"] == 0, readings
    assert PARK_TEXT not in _text_contents(turn["approve"]), _text_contents(turn["approve"])


def test_the_delivered_body_is_byte_identical_to_the_leg_answer(parked):
    """闸门只改「发几枚帧」，不改交付：会话历史那一行与腿交回的那句逐字相同。"""
    answer = _formed_body(REGISTERED_CHARS["chart-01"])
    turn = _round(parked, answer=answer)
    assert turn["delivered"] == answer
    assert _text_contents(turn["approve"])[-1] == answer
    assert len(_text_contents(turn["approve"])) == len(turn["pieces"])


# ==================== 方向钉：屏上挂着真答复时，本单一格都不许多发 ====================


def test_the_piece_branch_stays_shut_when_the_screen_already_holds_the_answer(parked, caplog):
    """R464 病历的常态（run22 那 19 枚 ``approved_ok`` 的共同形状）不许被这次放宽碰红。

    屏上此刻站着的是**真答复**：续跑重放同一份字 ⇒ 逐片帧一枚都不许上屏，也不许把闸门
    灌满误报（``[R464] 批准腿拦下``）。放宽如果写成无条件，这一格立刻红。
    """
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    answer = _formed_body(REGISTERED_CHARS["tool-04"])
    turn = _round(parked, answer=answer, park_answer=answer)
    assert turn["on_screen"] == answer, turn["on_screen"]
    assert len(turn["pieces"]) > 1, turn["pieces"]
    assert _text_contents(turn["approve"]) == [], _text_contents(turn["approve"])
    alarms = [record.getMessage() for record in caplog.records
              if "批准腿拦下" in record.getMessage()]
    assert alarms == [], alarms
    readings, _arrivals = _round_readings(
        [_wire(turn["ask"]), _wire(turn["approve"])], answer)
    assert readings["max_stream_frames"] > 1, readings
    assert bool(ruler._frame_verdict(readings)) is True, readings


# ==================== 反证牙 C：摘掉 opening 那一格必须红，并点名题号 ====================


def _forbid_opening(monkeypatch):
    """把 R662 那一格摘掉：``opening`` 恒假 ⇒ 逐片帧重新被规则 2 整批 held（改前形状）。"""
    decide = chat._ApprovedAnswerStream.decide

    def mutant(self, body, *, terminal, opening=False):
        return decide(self, body, terminal=terminal)

    monkeypatch.setattr(chat._ApprovedAnswerStream, "decide", mutant)


@pytest.mark.parametrize("question_id", ["chart-01", "tool-04"])
def test_knife_c_dropping_the_opening_cell_goes_red_naming_the_rows(monkeypatch, parked,
                                                                    question_id, caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    _forbid_opening(monkeypatch)
    answer = _formed_body(REGISTERED_CHARS[question_id])
    turn = _round(parked, answer=answer)
    assert len(turn["pieces"]) > 1, "生成腿没交片：这枚反证没咬住东西"
    assert _text_contents(turn["approve"]) == [answer], _text_contents(turn["approve"])
    # 改前那一枚收尾帧本来就要换源（规则 3），所以纠正 step 仍旧配对：红的不是这一格。
    assert len(_correction_steps(turn["approve"])) == 2, _correction_steps(turn["approve"])
    alarms = [record.getMessage() for record in caplog.records if "批准腿拦下" in record.getMessage()]
    assert len(alarms) == 1, alarms
    readings, _arrivals = _round_readings(
        [_wire(turn["ask"]), _wire(turn["approve"])], answer)
    assert readings["text_frames"] == 2, readings
    assert readings["max_stream_frames"] == 1, readings
    assert readings["per_stream"] == [{"frames": 1, "breaks": 0, "first_break_at": 0},
                                      {"frames": 1, "breaks": 0, "first_break_at": 0}], readings
    assert (readings["missing_chars"], readings["extra_chars"]) == (0, 0), readings
    assert readings["last_frame_covers_answer"] is True, readings
    assert bool(ruler._frame_verdict(readings)) is False, readings
# ==================== 反证牙 D：末帧少一个字必须红（chart-04 那一形） ====================


def _shorten_last_frame(events, chars):
    """把一条流里**末帧**截短 ``chars`` 字，别的一格不动（真帧改一格，不重造形状）。"""
    indexes = [index for index, (name, _payload) in enumerate(events) if name == "text"]
    assert indexes, events
    last = indexes[-1]
    name, payload = events[last]
    mutated = dict(payload)
    mutated["content"] = str(payload.get("content") or "")[:-chars]
    return events[:last] + [(name, mutated)] + events[last + 1:]


@pytest.mark.parametrize("chars", [1, 5, 40])
def test_knife_d_a_last_frame_that_misses_the_tail_goes_red_on_the_tail(chars, parked):
    """``chart-04`` 的病形就是「末帧不覆盖终答」：少一个字也必须读成红。

    在册尺的读法（``scripts/eval_transport_ask_v2.py::_frame_readings``）：末帧比终答少
    ``chars`` 字 ⇒ ``extra_chars == chars``、``last_frame_covers_answer`` 翻假 ⇒
    ``criterion_two_holds`` 假。🔴 本件不为此改尺，也不为此改判分器。
    """
    answer = _formed_body(REGISTERED_CHARS["chart-01"])
    turn = _round(parked, answer=answer)
    streams = [_wire(turn["ask"]), _wire(turn["approve"])]
    base, _base_frames = _round_readings(streams, answer)
    assert bool(ruler._frame_verdict(base)) is True, base
    readings, _arrivals = _round_readings(
        [streams[0], _shorten_last_frame(streams[1], chars)], answer)
    assert readings["extra_chars"] == min(chars, len(answer)), readings
    assert readings["last_frame_covers_answer"] is False, readings
    assert bool(ruler._frame_verdict(readings)) is False, readings
    assert readings["text_frames"] == base["text_frames"], (readings, base)
    assert readings["max_stream_frames"] == base["max_stream_frames"], readings


# ==================== 漂移钉：那一格的来历只许是「现构造的挂起说明」 ====================


def _approve_source() -> str:
    from tests.test_r524_sink_reaches_both_runways import _function_source

    return _function_source(chat, "approve")


def test_the_opening_flag_is_derived_from_the_notice_at_open():
    """``opening`` 的因只许是 ``is_hitl_park_notice(屏上此刻那份正文)``，一次都不许多。

    写成无条件 True 会把上面那枚方向钉立刻打红；抄字面文案会漂（挂起文案的在册裁定是
    「按 ``hitl_park_text`` 现构造再逐字比」）。
    """
    source = _approve_source()
    assert "screen_holds_notice = is_hitl_park_notice(screen_at_open)" in source
    assert source.count("opening=screen_holds_notice") == 1
    assert source.count("screen_holds_notice") == 2, source.count("screen_holds_notice")


def test_the_piece_branch_is_the_only_caller_that_passes_the_opening_flag():
    """``terminal`` 那三处调用点形状不许漂：收尾那一枚仍旧恒真。

    批准腿的 ``_emit_answer`` 调用点一共三枚（piece / hitl / done），``terminal=True``
    只许出现在收尾那一枚上 —— 放宽如果漏到收尾那一格，就把「一轮一份」那枚裁定泡掉了。
    """
    tree = ast.parse(textwrap.dedent(_approve_source()))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.AsyncFor) and isinstance(node.iter, ast.Call)
             and getattr(node.iter.func, "id", None) == "_emit_answer"]
    calls = sorted(calls, key=lambda node: node.iter.lineno)
    assert len(calls) == 3, len(calls)
    terminals, flags = [], []
    for call in calls:
        keywords = {keyword.arg: keyword.value for keyword in call.iter.keywords}
        terminals.append(bool(keywords["terminal"].value))
        flags.append("opening" in keywords)
    assert terminals.count(True) == 1, terminals
    assert flags.count(True) == 1, flags
    assert flags[terminals.index(True)] is False, (terminals, flags)

# ==================== 复演件：批准腿两形过真发射件后的字节（按 env 开关） ====================


@pytest.mark.parametrize("question_id", ["chart-01", "tool-04"])
def test_record_the_shadow_wire_of_the_parked_approval_round(parked, question_id):
    """与 ``tests/test_r662_formed_answer_streams_progressively.py`` 同一枚复演件口径。"""
    answer = _formed_body(REGISTERED_CHARS[question_id])
    turn = _round(parked, answer=answer)
    assert len(_text_contents(turn["approve"])) > 1, "复演件不许交回一枚帧：先修好再落证据"
    _record_shadow_wire(question_id, [turn["ask"], turn["approve"]],
                        turn["delivered"], turn["pieces"])
