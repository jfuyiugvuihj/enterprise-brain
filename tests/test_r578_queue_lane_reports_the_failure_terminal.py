# -*- coding: utf-8 -*-
"""R578 —— 队列道报告腿：`_drain_report_stream` 的两枚可注册点各交一次凭据。

R548（并树 ``5830422`` 之后）已经在 ``deploy/queue_worker.py`` 交出**片段汇那一枚**注册点，
本单在它旁边补第二枚 —— ``report_failure_sink``：报告道那一步真落到 ``stream_error`` 时，
把 ``report_failure_record(stream_error)`` 的原样记录（终态词 ``failed`` ＋ ``ErrorEnvelope.code``
里**已在册**的一枚原因码）交给它。缺省不建、一次也不叫：全部既有直调（含 `_process_report_lane_turn`
在成功分支与挂起分支上的三处调用，以及 R548 端到端跑的那几轮）走的是同一段 return，一个键都不多。

🔴 本单不做投递面、不做真机读数、不改 R524 交工纸里 ``queue_lane=not_applicable`` 那一格——
「注册点在」与「客户端读得到字」是两件事，V2 §6 R545 那一行明令不许洗绿。判据⑤ 的边界原文
在凭据纸 `docs/testing/r578-queue-lane-piece-sink-2026-10-03.md` §4。

全程离线：不打模型、不起服务、不动容器、不碰真 Redis（沿用 R37 的 FakeRedis 夹具）。
"""

from pathlib import Path

from app.agents import nodes, orchestrator
from app.agents.contracts import ErrorEnvelope
from deploy import queue_worker

# 借在册件里的夹具：R548 已经把「跑一轮 + 装图内假流 + 真 producer 盖章」这三手做成
# 具名函数；R37 交回 worker 与 state 的桩；R81 交回 ENUM_CODES 这把尺。
# 借而不改，是判据②「同名集同数」的前提——两把尺在树里只有唯一一处定义。
import test_r548_queue_lane_registers_the_piece_sink as nail
from tests.test_r37_report_lane_worker import (
    MESSAGE,
    _install_worker,
    _request_id,
    _state,
)
from tests.test_r81_queue_terminal_retry import ENUM_CODES


REPO = Path(__file__).resolve().parents[1]
WORKER_PATH = REPO / "deploy" / "queue_worker.py"

#: 报告腿那一步的**在册**终态词——只有 ``failed`` 才是"这轮没跑出来"。
#: ``succeeded`` / ``refused`` 都是队列账本自己的状态词，与 ``ErrorEnvelope`` 无关，
#: 借过来当判据就是把契约里的两码事揉成一团。
TERMINAL_FAILED = "failed"

#: 一枚装得下 STREAM_PIECE_MIN_CHARS 至少两次的正文；用在册那把尺去切，切得出多片。
PREFIX_ANSWER = nail.ANSWER

#: 编排出 error 事件时那一句里必须带的**在册片段**——`app/common/model_budget.py::CONTEXT_ERROR_FRAGMENTS`
#: 里点名的一条；带着它，`report_failure_record` 就会认回 ``CONTEXT_LIMIT_CODE``，
#: 不带它就退回 ``internal_error``，两枚都在 `ErrorEnvelope.code` 里。
CONTEXT_LIMIT_MESSAGE = "prompt is too long: prompt tokens 2695 > available 4096"
UNKNOWN_MESSAGE = "worker crashed with an unrecognised stack trace"


# ==================== 判据①：注册点收到逐字片段，且与终答前缀可对齐 ====================


def test_the_piece_sink_receives_pieces_that_line_up_with_the_final_answer_prefix(monkeypatch, tmp_path):
    """sink 收到的**逐字序列**=终答的前缀，切分由在册那把 `STREAM_PIECE_MIN_CHARS` 决定。

    本单**不新加常数**：片的最小宽度直接读 `nodes.STREAM_PIECE_MIN_CHARS`；`_publish` 走
    `nodes.StreamPieceMerger` 原件，所以切得出多少片、每片几字，全由在册那把尺说。
    """
    box = nail._install_graph_stream(
        monkeypatch, {}, answer=PREFIX_ANSWER, publish=True
    )
    ctx = _install_worker(monkeypatch, tmp_path, name="r578-prefix-align")
    assert ctx.worker.process_one() is True

    ledger = box["sinks"][0]
    assert isinstance(ledger, queue_worker.ReportLanePieceLedger), ledger
    # ① 多片：一次投喂一整篇是"一坨"，逐字流式才是"一串"
    assert ledger.count > 1, ledger.count
    # ② 每片非最末那一枚，字数不小于在册那把尺
    for piece in ledger.pieces[:-1]:
        assert len(piece.text) >= nodes.STREAM_PIECE_MIN_CHARS, (
            len(piece.text), nodes.STREAM_PIECE_MIN_CHARS, piece
        )
    # ③ 逐字前缀对齐：joined_text 是终答的前缀（本例流到尾 = 全等）
    joined = ledger.joined_text()
    assert PREFIX_ANSWER.startswith(joined), (PREFIX_ANSWER[:20], joined[:20])
    assert joined == PREFIX_ANSWER


def test_a_partial_run_still_aligns_as_a_strict_prefix(monkeypatch, tmp_path):
    """只汇出前几枚 ⇒ joined_text 严格短于终答，但仍是它的字面前缀（对齐不许漂）。"""
    merger = nodes.StreamPieceMerger()
    pieces = merger.feed(PREFIX_ANSWER[:80])  # 只喂前 80 字，模拟流被截在中间
    ledger = queue_worker.ReportLanePieceLedger("r578-partial")
    for piece in pieces:
        nodes.publish_stream_pieces(
            nail._sink_config(ledger), [piece], call_id=nail.CALL_ID, worker=nail.LEG
        )
    joined = ledger.joined_text()
    assert ledger.count >= 1
    assert PREFIX_ANSWER.startswith(joined) and joined != PREFIX_ANSWER, joined


# ==================== 判据②：默认 None 时行为与今天逐字节同 ====================


def _direct_drain(monkeypatch, tmp_path, *, stream_body, **kwargs):
    """绕开 worker 那一层，直接把 `_drain_report_stream` 叫一发，返回值原样交回。

    `stream_body` 是本单自己那枚 `run_with_stream` 替身：它只负责按顺序吐事件，
    不做取消、不重连、不打模型，因此判据① / ③ 都能拿到精确的事件序列而不引入别的变量。
    """
    monkeypatch.setattr(orchestrator, "run_with_stream", stream_body)
    return queue_worker._drain_report_stream(
        MESSAGE,
        thread_id="r578-direct",
        principal={},
        provenance="direct",
        request_id="req-r578-direct",
        trace_id="trace-r578-direct",
        task_id="task-r578-direct",
        **kwargs,
    )


def test_the_failure_sink_default_none_returns_the_same_three_tuple(monkeypatch, tmp_path):
    """不设 `report_failure_sink` ⇒ 返回值 arity 与内容一格没动（本单不许改终态那层的接口）。"""

    def _just_states(*a, **kw):
        yield (("",), _state(answer="hello", agent_results={}))

    results = _direct_drain(monkeypatch, tmp_path, stream_body=_just_states)
    assert len(results) == 3, results
    final_answer, agent_results, stream_error = results
    assert final_answer == "hello"
    assert agent_results == {}
    assert stream_error == ""


def test_the_failure_sink_default_none_still_hands_the_error_string_back(monkeypatch, tmp_path):
    """不设 sink 但真落到 stream_error ⇒ 仍旧与改前逐字节同：三值里的第三值就是那句话。"""

    def _boom(*a, **kw):
        yield {"error": CONTEXT_LIMIT_MESSAGE}

    final_answer, agent_results, stream_error = _direct_drain(
        monkeypatch, tmp_path, stream_body=_boom
    )
    assert stream_error == CONTEXT_LIMIT_MESSAGE
    assert final_answer == "" and agent_results == {}


def test_the_success_path_never_calls_the_failure_sink(monkeypatch, tmp_path):
    """报告道成功那一发 ⇒ sink 一次也不叫：本单不在成功分支上多留一笔。"""
    calls: list = []

    def _just_states(*a, **kw):
        yield (("",), _state(answer="ok"))

    _direct_drain(
        monkeypatch, tmp_path,
        stream_body=_just_states,
        report_failure_sink=calls.append,
    )
    assert calls == []


# ==================== 判据③：失败有终态与具名原因码（ErrorEnvelope 里的在册码） ====================


def test_the_failure_sink_receives_the_record_when_the_lane_falls_over(monkeypatch, tmp_path):
    """注册点收到 `report_failure_record(stream_error)` 的原样记录：终态词 + 具名原因码。"""
    received: list = []

    def _boom(*a, **kw):
        yield {"error": CONTEXT_LIMIT_MESSAGE}

    final_answer, agent_results, stream_error = _direct_drain(
        monkeypatch, tmp_path,
        stream_body=_boom,
        report_failure_sink=received.append,
    )
    # 三值返回值一格没动
    assert stream_error == CONTEXT_LIMIT_MESSAGE
    # sink 恰好收到一发
    assert len(received) == 1, received
    record = received[0]
    # ① 终态词是 `failed`（这是 worker 与契约对账的那一枚；不是队列 status 那一格）
    assert record["status"] == TERMINAL_FAILED, record
    # ② 具名原因码在 ErrorEnvelope.code 的封闭枚举里
    code = record["error"]["code"]
    assert code in ENUM_CODES, (code, sorted(ENUM_CODES))
    # ③ 那条在册尺子（context_error_code + CONTEXT_ERROR_FRAGMENTS）把 CONTEXT_LIMIT_MESSAGE
    #   认回成 CONTEXT_LIMIT_CODE——不是随便落一枚 internal_error 交差。
    assert code == "context_limit_exceeded", record
    # ④ message 原样带着 stream_error，不重抄不改写
    assert record["error"]["message"] == CONTEXT_LIMIT_MESSAGE
    # ⑤ 记录可以直接喂进 ErrorEnvelope 那枚 pydantic 校验器，构造不出就说明码是野的
    envelope = ErrorEnvelope(code=code, message=record["error"]["message"])
    assert envelope.code == code


def test_the_failure_sink_falls_back_to_internal_error_when_nothing_matches(monkeypatch, tmp_path):
    """认不出原码那一发仍旧交回兜底的 `internal_error`：兜底码也在册，本单不发明新码。"""
    received: list = []

    def _boom(*a, **kw):
        yield {"error": UNKNOWN_MESSAGE}

    _direct_drain(
        monkeypatch, tmp_path,
        stream_body=_boom,
        report_failure_sink=received.append,
    )
    assert len(received) == 1, received
    record = received[0]
    assert record["status"] == TERMINAL_FAILED
    assert record["error"]["code"] == "internal_error", record
    assert record["error"]["code"] in ENUM_CODES


def test_the_deterministic_refusal_still_marks_the_record_non_retryable(monkeypatch, tmp_path):
    """R448 那一族：认回白名单里的确定性拒绝 ⇒ 记录里补一枚 `retryable: False`，注册点照收。"""
    received: list = []

    def _boom(*a, **kw):
        yield {"error": CONTEXT_LIMIT_MESSAGE}

    _direct_drain(
        monkeypatch, tmp_path,
        stream_body=_boom,
        report_failure_sink=received.append,
    )
    record = received[0]
    assert record["error"].get("retryable") is False, record
    # 与在册那把尺同源：is_non_retryable_error 是 R81 那枚闸门认的记录形状
    assert queue_worker.is_non_retryable_error(record) is True


def test_the_drain_hands_one_record_per_failing_round_not_two(monkeypatch, tmp_path):
    """一轮里编排只会 yield 一枚 error 事件 ⇒ 注册点也只该被叫一次；叫两次就是第二套口径。"""
    calls: list = []

    def _boom(*a, **kw):
        yield {"error": CONTEXT_LIMIT_MESSAGE}
        yield {"error": "second error should never fire the sink again"}

    _direct_drain(
        monkeypatch, tmp_path,
        stream_body=_boom,
        report_failure_sink=calls.append,
    )
    # 两条 error 都会覆盖 stream_error（这是既有语义，本单不改），但 sink 只在最末一发被叫
    assert len(calls) == 1, calls
    assert calls[0]["error"]["message"] == "second error should never fire the sink again"


# ==================== 判据②：worker 里的稳定码字面量集合与改前逐字节同 ====================


def test_the_worker_still_hands_over_no_new_stable_code_literal():
    """判据②：本单往 worker 里加的只是新关键字与两行 if 判断，一枚稳定码字面量都没多。

    尺子在册：`ENUM_CODES` 借自 `tests/test_r81_queue_terminal_retry.py`，
    与 `tests/test_r548_queue_lane_registers_the_piece_sink.py::test_the_worker_still_hands_over_no_new_stable_code`
    同一枚表达式、同一枚交集判 —— 本件不新造第二把尺。
    """
    import re

    codes_in_worker = set(re.findall(r'"([a-z][a-z_]+)"', WORKER_PATH.read_text(encoding="utf-8"))) & ENUM_CODES
    assert codes_in_worker == {"internal_error"}, codes_in_worker


# ==================== 借 R548 的夹具再证：报告腿那一步注册点两枚同时到位 ====================


def test_the_round_hands_both_sinks_down_without_leaking_into_the_published_readings(monkeypatch, tmp_path):
    """端到端一跑：片段汇与失败汇都在 worker 手里；发布面的读数不因本单第二枚注册点漂一格。

    `process_one()` 走真报告腿，`_install_graph_stream(publish=True)` 只汇片不叫错；
    失败汇因此一次也不该被叫，`_run_round` 交回的 `status / result / terminal` 三格
    与 R548 判据③ 那两枚在册钉（`test_the_published_readings_do_not_move_when_pieces_flow`）
    同读数 ⇒ 本单的第二枚注册点在成功分支上零行为外溢。
    """
    round_ = nail._run_round(monkeypatch, tmp_path, name="r578-both-sinks-quiet", publish=True)
    assert round_["finished"] is True
    ledger = round_["ledger"]
    assert ledger.count > 1 and ledger.joined_text() == PREFIX_ANSWER
    # 成功分支上失败汇一次也不叫：ctx.queue 的 status 走 done、不是 dead/failed
    request_id = round_["request_id"]
    status = round_["ctx"].queue.status(request_id)
    assert status == "done", status
