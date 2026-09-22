# -*- coding: utf-8 -*-
"""R43a 判据①④ · 原生腿把 cached-token 计数接出来。

跟进单 §81 三第 1 条：原生 ``/api/chat`` 的 ``done`` 帧一直带着
``prompt_eval_cached_count``，而 ``app/common/model_handler.py`` 的取数段只抄两枚计数，
再往上一层 ``ModelReply.__new__`` 的形参里根本没有 ``cached_tokens`` 这一格——所以
``app/trace/spans.py`` 里那句 ``getattr(response, "cached_tokens", None)`` 是**结构性**
永远拿不到值，不是"等施工接上"。本件钉的就是这枚洞被补上、且补法不夹带估算。

读数（1 / 148 / 3）一律不抄字面量：逐字帧引用 ``tests/test_r29_thinking_tax.py`` D 段
那一份已并树的真机产物（R146 判据⑤：禁止复制第二份帧）。

全程离线：不开 socket、不起服务、不碰数据库。本机宿主模型此刻正被三枚在途 Agent
抢，任何时延数都不可比，所以本件一个时间都不测——"真省下多少"留给跑分窗。
"""
import inspect
import json
import logging
from types import SimpleNamespace

import pytest

from app.common import model_budget
from app.common.model_handler import (
    TRANSPORT_NATIVE,
    ModelHandler,
    ModelReply,
    ModelSource,
    compat_reply,
)
from app.trace.spans import model_token_counts
from tests.test_r29_thinking_tax import (
    DATA_NATIVE_TOOL,
    DATA_SIMPLE_NATIVE,
    DATA_TOOL200_NATIVE,
)

#: 一个不存在的机器名：万一有缝没堵住，它也只能 DNS 失败，碰不到宿主模型端口。
SAFE_BASE_URL = "http://model.internal:11434/v1"
FRAME_LINES = DATA_SIMPLE_NATIVE + DATA_TOOL200_NATIVE + DATA_NATIVE_TOOL
MESSAGES = [{"role": "user", "content": "改写这个问题"}]
#: 区分「这一格不存在」与「这一格的值是 None」：桩要能造出前者。
UNSET = object()


@pytest.fixture(autouse=True)
def _reset_budget():
    yield
    model_budget.reset_default_budget()


def _frame(line: str) -> dict:
    return json.loads(line)


def _native_done_frames() -> list[dict]:
    """真机 done 帧：本件唯一的 cached 读数来源。"""
    frames = [_frame(line) for line in FRAME_LINES]
    return [frame for frame in frames if frame.get("done") is True]


def _body(*, cached=UNSET, prompt=500, output=20) -> dict:
    """Ollama 原生 ``/api/chat`` 的应答形状：正文在 ``message.content``，计数在顶层。

    三枚 duration 故意留着：想反推 cached 的实现有得偷，才钉得住"不许估算"。
    """
    body = {
        "model": "qwen3.5:9b",
        "message": {"role": "assistant", "content": json.dumps({"rewrites": ["a", "b", "c"]})},
        "done_reason": "stop",
        "done": True,
        "load_duration": 6_100_000_000,
        "prompt_eval_duration": 3_733_000_000,
        "eval_duration": 45_883_000_000,
        "total_duration": 55_716_000_000,
    }
    if prompt is not UNSET:
        body["prompt_eval_count"] = prompt
    if output is not UNSET:
        body["eval_count"] = output
    if cached is not UNSET:
        body["prompt_eval_cached_count"] = cached
    return body


class _NativeRecorder:
    """原生腿的缝：记账请求并回放预置响应，一次真实 HTTP 都不发生。"""

    def __init__(self, body):
        self.calls = []
        self.body = body

    def __call__(self, url, payload, *, timeout):
        self.calls.append({"url": url, "payload": payload, "timeout": timeout})
        return self.body


def _native_reply(monkeypatch, body) -> ModelReply:
    """只经过真 ``ModelHandler.chat`` 这一道出口，拿到服务端应答的落地对象。"""
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", SAFE_BASE_URL)
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3.5:9b")
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    handler = ModelHandler()
    native = _NativeRecorder(body)
    monkeypatch.setattr(handler, "_native_chat_request", native)
    reply = handler.chat(messages=MESSAGES, source=ModelSource.LOCAL, stream=False)
    assert len(native.calls) == 1, "一次调用只许付一次推理"
    assert reply.transport == TRANSPORT_NATIVE
    return reply


# ==================== 判据①：接的地方这次真的有洞了 ====================


def test_modelreply_signature_now_has_a_cached_slot_defaulting_to_none():
    """改动前这一枚必红：形参里根本没有 ``cached_tokens``，``getattr`` 拿的是空气。"""
    parameters = inspect.signature(ModelReply.__new__).parameters
    assert "cached_tokens" in parameters, "接的地方没有洞就谈不上接上：形参必须存在"
    slot = parameters["cached_tokens"]
    assert slot.kind is inspect.Parameter.KEYWORD_ONLY, "计数槽不许挤占位置参数顺序"
    assert slot.default is None, "默认必须是 None（＝没有读数），不许默认成 0"


def test_the_native_frame_cached_count_comes_out_through_the_reply(monkeypatch):
    frame = _native_done_frames()[1]
    reported = frame["prompt_eval_cached_count"]

    reply = _native_reply(monkeypatch, _body(cached=reported))

    assert reply.cached_tokens == reported, "服务端报了就必须带出来，不许再被丢掉"
    assert isinstance(reply.cached_tokens, int)


def test_the_metering_boundary_sees_three_keys_on_a_native_round(monkeypatch):
    """本单不碰 ``app/trace/spans.py``：那侧早就备好了，接上即生效。"""
    frame = _native_done_frames()[0]
    reply = _native_reply(
        monkeypatch,
        _body(
            cached=frame["prompt_eval_cached_count"],
            prompt=frame["prompt_eval_count"],
            output=frame["eval_count"],
        ),
    )

    assert model_token_counts(reply) == {
        "input_tokens": frame["prompt_eval_count"],
        "output_tokens": frame["eval_count"],
        "cached_tokens": frame["prompt_eval_cached_count"],
    }, "三枚必须同源同形：本单是加法，不是换尺子"


# ==================== 判据①的口径：没报就是没有，报 0 才是 0 ====================


def test_a_frame_that_says_nothing_grows_no_reading(monkeypatch):
    """🔴 缺 ``prompt_eval_cached_count`` 就是缺：不许长成一枚 None，更不许长成 0。

    这一枚同时钉住本单的取舍：``ModelReply`` 的这个属性在"服务端没说"时**不存在**而非
    ``None``——``tests/test_r38_cached_tokens_honesty.py`` 钉着"没报的帧不许长出 cached
    字段"，而记账侧要区分的正是"没报"与"报了 0"。读它请一律用
    ``getattr(reply, "cached_tokens", None)``。
    """
    reply = _native_reply(monkeypatch, _body())

    assert not hasattr(reply, "cached_tokens"), "没报就是没报：不许凭空长出一格"
    counts = model_token_counts(reply)
    assert "cached_tokens" not in counts, counts
    assert counts == {"input_tokens": 500, "output_tokens": 20}, "前两枚照旧，本单不动那把尺"


def test_a_reported_zero_stays_a_measured_zero(monkeypatch):
    """报了 0 与没报必须分得开：0 是实测命中数，不是缺读数的遮羞布。"""
    reply = _native_reply(monkeypatch, _body(cached=0))

    assert reply.cached_tokens == 0
    counts = model_token_counts(reply)
    assert counts["cached_tokens"] == 0, counts


def test_the_cached_count_is_never_back_filled_by_subtraction(monkeypatch):
    """🔴 反估算：``prompt_eval_count - cached``、时长换算、正文长度顶包，一条都不许进账。"""
    reply = _native_reply(monkeypatch, _body(cached=UNSET, prompt=500, output=20))
    counts = model_token_counts(reply)

    assert "cached_tokens" not in counts, counts
    assert counts["input_tokens"] == 500, "缺第三枚不许回头污染前两枚"
    assert getattr(reply, "cached_tokens", None) is None


def test_this_wiring_opens_no_socket(model_endpoint_guard, monkeypatch):
    """接线的路本身离线：R56 那本账（blocked connect attempts）必须仍然是空的。"""
    _native_reply(monkeypatch, _body(cached=148))

    assert model_endpoint_guard.blocked_attempts == []


# ==================== 判据④：一枚具名读数（现成真机帧，不测时延） ====================


def test_the_verbatim_host_frames_each_carry_their_own_cached_reading(monkeypatch):
    """每一枚真机 done 帧过一遍这道出口：帧报多少，对象就带多少，一枚不差。"""
    frames = _native_done_frames()
    assert frames, "前提：R29 注入的逐字帧还在"

    readings = []
    for frame in frames:
        assert "prompt_eval_cached_count" in frame, frame
        assert isinstance(frame["prompt_eval_cached_count"], int), frame
        reply = _native_reply(
            monkeypatch,
            _body(
                cached=frame["prompt_eval_cached_count"],
                prompt=frame["prompt_eval_count"],
                output=frame["eval_count"],
            ),
        )
        assert reply.cached_tokens == frame["prompt_eval_cached_count"]
        readings.append(reply.cached_tokens)

    #: 读数只从帧里取，不抄字面量；这一枚要求"三枚各不相同且都非 None"，
    #: 替桩实现（永远回同一枚数、或干脆回 None）蒙不过去。
    assert len(set(readings)) == len(readings), readings
    assert all(value >= 0 for value in readings), readings
    assert any(value > 0 for value in readings), readings


def test_the_native_log_line_names_the_cached_counter_for_the_run_window(monkeypatch, caplog):
    """跑分窗核对用的那一张脸：日志里必须能直接读到服务端自报的第三枚计数。"""
    caplog.set_level(logging.INFO, logger="enterprise_brain")

    _native_reply(monkeypatch, _body(cached=148))

    line = [record.getMessage() for record in caplog.records if "prompt_eval_cached_count" in record.getMessage()]
    assert line, [record.getMessage() for record in caplog.records]
    assert "prompt_eval_cached_count=148" in line[0], line[0]


def test_the_compatible_leg_reply_still_carries_no_cached_field():
    """本单的范围：只接原生腿。兼容腿的 cached 走 ``usage`` 形状，由 spans 那侧读。"""
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=500, completion_tokens=20),
    )

    reply = compat_reply(response)

    assert not hasattr(reply, "cached_tokens"), "没给兼容腿造读数，本单不越界"
    assert model_token_counts(reply) == {"input_tokens": 500, "output_tokens": 20}