"""R34：`keep_alive` 常驻 —— 消冷加载 6.4–6.9 s，且不许把客户的内存钉死。

跟进单 §21 L504 那一行的判据有三条：① 连续 5 问不再重复付冷加载；② 空闲后的回收策略
落进文档；③ 只在原生端点上有效（`/v1` 传参无效）。①③ 是实机数字，记在
`docs/handoff/2026-09-19-r34-keep-alive-residency.md`：原生腿冷态首问 wall 5.090 s、
服务端自报 `load_duration` 4.951 s，随后四问 0.922 / 0.184 / 3.028 / 2.516 s 而
`load_seconds` 全是 0.001–0.003 s；`ollama ps` 的 `UNTIL` 从"5 minutes from now"变成
15 分钟，窗口到点后模型自己下去了。**本文件是这些事实的离线镜像**：它钉"请求里到底带了
没带这个字段、带的值有没有界、失败与卸载语义有没有被顺手放宽"，一条真 socket 都不开。

钉死的几件事：
- 原生腿 `/api/chat` 与兼容腿 `/v1` 都带 `keep_alive`，且**除这一个字段外两条腿的请求
  形状与 R92 结案时一字不差**（`think:false`、`num_predict=256`、`max_tokens`、`stream`）；
- 未配置时线上走 Ollama 自己的默认 300 s —— 本单不许"新增强制打开的默认值"，常驻窗口是
  运维旋钮，不是这一层替他做的决定；
- 🔴 红线：`-1` / `infinite` / `2h` / 乱码都换不来"永不卸载"，只会被截到上限并在日志里
  说清楚，而答案照常返回；`0` 是合法值（答完立刻把内存还回去）；
- `ModelReply` / `answer_error_code` / `NATIVE_REFUSED_STATUSES` 的判定与 R92 一致。
"""
import json
import logging
from types import SimpleNamespace

import httpx
import pytest

from app.agents.contracts import ModelTier
from app.common.model_budget import OUTPUT_TRUNCATED_CODE, ModelContextLimitExceeded
from app.common import model_budget, model_config
from app.common.model_config import (
    DEFAULT_KEEP_ALIVE_SECONDS,
    KEEP_ALIVE_CEILING_SECONDS,
    KEEP_ALIVE_ENV,
    NEVER_UNLOAD_SPELLINGS,
    parse_keep_alive_seconds,
    resolve_keep_alive,
)
from app.common.model_handler import (
    KEEP_ALIVE_FIELD,
    MODEL_UNAVAILABLE_CODE,
    NATIVE_REFUSED_STATUSES,
    RESPONSE_EMPTY_CODE,
    TRANSPORT_COMPAT,
    TRANSPORT_NATIVE,
    ModelHandler,
    ModelReply,
    _NativeChatUnsupported,
    keep_alive_log,
)

#: 一个不存在的机器名：万一有缝没堵住，它也只能 DNS 失败，碰不到宿主 Ollama 的端口。
SAFE_BASE_URL = "http://model.internal:11434/v1"
#: 实机取证那台交付机上的模型名与常驻体积（`ollama ps` 的 size 字段）。
MODEL = "qwen3.5:9b"
RESIDENT_BYTES = 5_327_342_796
#: 实机原生腿冷态首问自报的 load_duration（4.951 s），日志用例按它断言。
MEASURED_LOAD_NS = 4_951_000_000
REWRITE_JSON = json.dumps(
    {"rewrites": ["住宿费报销上限是多少"], "sub_questions": ["住宿费标准按职级区分吗"]},
    ensure_ascii=False,
)


def _handler(monkeypatch, keep_alive=None):
    """一个装着真 OpenAI 客户端的 handler：建客户端不开 socket，真 HTTP 由用例注入。"""
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", SAFE_BASE_URL)
    monkeypatch.setenv("LOCAL_MODEL_NAME", MODEL)
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    if keep_alive is None:
        monkeypatch.delenv(KEEP_ALIVE_ENV, raising=False)
    else:
        monkeypatch.setenv(KEEP_ALIVE_ENV, keep_alive)
    model_budget.reset_default_budget()
    return ModelHandler()


def _native_body(
    content=REWRITE_JSON, done_reason="stop", eval_count=102, load_ns=MEASURED_LOAD_NS,
):
    """Ollama 原生 `/api/chat` 的响应形状：正文在 `message.content`，冷加载在 `load_duration`。"""
    return {
        "model": MODEL,
        "message": {"role": "assistant", "content": content},
        "done_reason": done_reason,
        "done": True,
        "eval_count": eval_count,
        "load_duration": load_ns,
        "prompt_eval_duration": 100_000_000,
    }


class _NativeRecorder:
    """原生腿的缝：记账请求并回放预置响应，一次真实 HTTP 都不发生。"""

    def __init__(self, body=None, raises=None):
        self.calls = []
        self.body = _native_body() if body is None else body
        self.raises = raises

    def __call__(self, url, payload, *, timeout):
        self.calls.append({"url": url, "payload": payload, "timeout": timeout})
        if self.raises is not None:
            raise self.raises
        return self.body


class _CompatRecorder:
    """兼容腿的缝：把 SDK 真发出去的参数原样记账，包括 `extra_body`。"""

    def __init__(self, content="ok", finish_reason="stop", stream_chunks=None):
        self.calls = []
        self.content = content
        self.finish_reason = finish_reason
        self.stream_chunks = stream_chunks or []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter(self.stream_chunks)
        message = SimpleNamespace(content=self.content)
        choice = SimpleNamespace(message=message, finish_reason=self.finish_reason)
        usage = SimpleNamespace(completion_tokens=13)
        return SimpleNamespace(choices=[choice], usage=usage)


def _compat_on(handler, **kwargs):
    recorder = _CompatRecorder(**kwargs)
    handler.ollama_client.chat.completions = recorder
    return recorder


def _stream_chunk(content):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


def _ask_native(handler, content=REWRITE_JSON, repeats=1):
    """连发几改写档调用：返回 (最后一发的应答, 记账器)。"""
    native = _NativeRecorder(body=_native_body(content=content))
    handler._native_chat_request = native
    reply = None
    for _ in range(repeats):
        reply = handler.chat([{"role": "user", "content": "住宿费标准是多少？"}], stream=False)
    return reply, native


def _residency(payload) -> str:
    return payload[KEEP_ALIVE_FIELD]


@pytest.fixture
def logs(caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    return caplog


# ==================== 判据③：字段确实上了两条腿的请求 ====================


def test_the_native_leg_asks_for_the_window(monkeypatch):
    reply, native = _ask_native(_handler(monkeypatch, "15m"))

    assert len(native.calls) == 1, "一次改写只许付一次推理"
    assert native.calls[0]["url"] == "http://model.internal:11434/api/chat"
    assert _residency(native.calls[0]["payload"]) == "900s"
    assert reply.transport == TRANSPORT_NATIVE
    assert str(reply) == REWRITE_JSON


def test_the_compatible_leg_is_asked_the_same_window(monkeypatch):
    """遗留答案口也要问一次常驻：运维调的是"这台机器留多久"，不该关心哪条腿答的。"""
    handler = _handler(monkeypatch, "15m")
    compat = _compat_on(handler, stream_chunks=[_stream_chunk("住宿"), _stream_chunk("费")])

    chunks = handler.chat([{"role": "user", "content": "讲讲住宿费标准"}], stream=True)

    assert [chunk.choices[0].delta.content for chunk in chunks] == ["住宿", "费"]
    assert compat.calls[0]["extra_body"] == {KEEP_ALIVE_FIELD: "900s"}


def test_residency_is_the_only_thing_either_leg_added(monkeypatch):
    """除常驻这一个字段外，两条腿的请求形状与 R92 结案时一字不差（判据④的反证）。"""
    _, native = _ask_native(_handler(monkeypatch, "15m"))

    assert native.calls[0]["payload"] == {
        "model": MODEL,
        "messages": [{"role": "user", "content": "住宿费标准是多少？"}],
        "stream": False,
        "think": False,
        "options": {"num_predict": 256},
        KEEP_ALIVE_FIELD: "900s",
    }

    handler = _handler(monkeypatch, "15m")
    compat = _compat_on(handler, stream_chunks=[_stream_chunk("x")])
    handler.chat([{"role": "user", "content": "答"}], stream=True)

    call = compat.calls[0]
    assert call["model"] == MODEL
    assert call["stream"] is True
    assert call["max_tokens"] == ModelHandler._call_budget(stream=True).max_tokens
    assert set(call) == {"model", "messages", "stream", "max_tokens", "timeout", "extra_body"}
    assert set(call["extra_body"]) == {KEEP_ALIVE_FIELD}


def test_the_rewrite_cap_is_still_256_on_the_wire(monkeypatch):
    """`max_tokens=256` 是 R92 钉死的 REWRITE 档预算，本单不许借常驻之名放宽它。"""
    _, native = _ask_native(_handler(monkeypatch, "15m"))
    budget = ModelHandler._call_budget(stream=False)

    assert budget.tier is ModelTier.REWRITE
    assert budget.max_tokens == 256
    assert model_budget.TIER_MAX_TOKEN_DEFAULTS[ModelTier.REWRITE] == 256
    assert native.calls[0]["payload"]["options"]["num_predict"] == 256


def test_five_consecutive_questions_all_ask_for_the_same_window(monkeypatch):
    """判据①的离线镜像：连续 5 问，每一发都重新要这个窗口，没有哪一发被漏钉。"""
    _, native = _ask_native(_handler(monkeypatch, "15m"), repeats=5)

    assert len(native.calls) == 5
    assert [_residency(call["payload"]) for call in native.calls] == ["900s"] * 5


# ==================== 判据②：窗口有界，且"永不卸载"拿不到 ====================


def test_an_unconfigured_machine_keeps_the_servers_own_default(monkeypatch):
    """没配就是没配：300 s 正是 Ollama 对"请求什么都没写"的默认，本单不新增强制打开的默认。"""
    _, native = _ask_native(_handler(monkeypatch, None))

    assert resolve_keep_alive().seconds == DEFAULT_KEEP_ALIVE_SECONDS == 5 * 60
    assert _residency(native.calls[0]["payload"]) == "300s"

    handler = _handler(monkeypatch, None)
    compat = _compat_on(handler, stream_chunks=[_stream_chunk("x")])
    handler.chat([{"role": "user", "content": "答"}], stream=True)
    assert compat.calls[0]["extra_body"] == {KEEP_ALIVE_FIELD: "300s"}


@pytest.mark.parametrize(
    ("configured", "expected_seconds", "expect_note"),
    [
        ("90s", 90, False),
        ("15m", 900, False),
        ("300", 300, False),
        ("20m", 1200, False),
        ("1h", KEEP_ALIVE_CEILING_SECONDS, True),
        ("2h", KEEP_ALIVE_CEILING_SECONDS, True),
        ("1h30m", KEEP_ALIVE_CEILING_SECONDS, True),
        ("-1", KEEP_ALIVE_CEILING_SECONDS, True),
        ("infinite", KEEP_ALIVE_CEILING_SECONDS, True),
        ("never", KEEP_ALIVE_CEILING_SECONDS, True),
        ("0", 0, False),
        ("0s", 0, False),
        ("10 minutes", DEFAULT_KEEP_ALIVE_SECONDS, True),
        ("abc", DEFAULT_KEEP_ALIVE_SECONDS, True),
        ("", DEFAULT_KEEP_ALIVE_SECONDS, False),
    ],
)
def test_the_window_is_always_bounded(configured, expected_seconds, expect_note):
    """任何写法都落在 `[0, 上限]` 内；被改过的一定要带 note —— 静默截断等于骗运维。"""
    policy = resolve_keep_alive(configured)

    assert policy.seconds == expected_seconds, configured
    assert policy.wire == f"{expected_seconds}s"
    assert 0 <= policy.seconds <= KEEP_ALIVE_CEILING_SECONDS
    assert bool(policy.note) is expect_note, configured


@pytest.mark.parametrize(
    "value", ["0", "5m", "15m", "30m", "1h", "2h", "-1", "-60s", "infinite", "zzz"]
)
def test_no_input_can_produce_an_unbounded_window(value):
    """红线的机器形态：解析层与策略层合起来，输出永远不可能为负或超上限。"""
    parsed = parse_keep_alive_seconds(value)
    policy = resolve_keep_alive(value)

    assert parsed is None or parsed == -1.0 or parsed >= 0
    assert 0 <= policy.seconds <= KEEP_ALIVE_CEILING_SECONDS


def test_never_unload_is_refused_without_costing_the_answer(monkeypatch):
    """红线是代码拦的而不是文档劝的：`-1` 被截到上限，而这一发的答案照常返回。"""
    reply, native = _ask_native(_handler(monkeypatch, "-1"))

    assert _residency(native.calls[0]["payload"]) == f"{KEEP_ALIVE_CEILING_SECONDS}s"
    assert str(reply) == REWRITE_JSON
    assert reply.error_code == ""


def test_zero_is_a_legitimate_answer_for_a_memory_starved_machine(monkeypatch):
    """运维要让模型每问完就下去，`0` 必须能表达；这是"不得永不卸载"的另一半。"""
    _, native = _ask_native(_handler(monkeypatch, "0"))

    assert _residency(native.calls[0]["payload"]) == "0s"


def test_the_two_numbers_the_document_promise_are_the_numbers_in_code():
    """回收策略文档里写死的默认值与上限必须与代码一致，否则策略就是编的。"""
    assert DEFAULT_KEEP_ALIVE_SECONDS == 300
    assert KEEP_ALIVE_CEILING_SECONDS == 1800
    assert "infinite" in NEVER_UNLOAD_SPELLINGS
    assert "-1" not in NEVER_UNLOAD_SPELLINGS  # 负数由 parse 层按符号拒，不靠枚举
    assert RESIDENT_BYTES == 5_327_342_796  # 实机 `ollama ps` 的 size，文档同数
    assert callable(model_config.resolve_keep_alive)


def test_the_window_is_read_per_call_so_an_operator_need_not_restart(monkeypatch):
    """同一个进程、同一个 handler：改了环境变量，下一发就跟着改，不用重启服务。"""
    handler = _handler(monkeypatch, "15m")

    _, first = _ask_native(handler)
    monkeypatch.setenv(KEEP_ALIVE_ENV, "30m")
    _, second = _ask_native(handler)
    monkeypatch.delenv(KEEP_ALIVE_ENV)
    _, third = _ask_native(handler)

    assert _residency(first.calls[0]["payload"]) == "900s"
    assert _residency(second.calls[0]["payload"]) == "1800s"
    assert _residency(third.calls[0]["payload"]) == "300s"


# ==================== 判据①②的可观测面：日志要说清窗口与冷加载 ====================


def test_the_native_log_line_names_the_window_and_the_cold_load(monkeypatch, logs):
    """实机取证靠的就是 `load_duration`：它必须进日志，否则运维只能掐秒表。"""
    _ask_native(_handler(monkeypatch, "15m"))

    lines = [
        record.getMessage() for record in logs.records if TRANSPORT_NATIVE in record.getMessage()
    ]
    assert len(lines) == 1, lines
    assert "keep_alive=900s" in lines[0]
    assert f"load_seconds={MEASURED_LOAD_NS / 1e9:.2f}" in lines[0]
    assert "done_reason=stop" in lines[0]


def test_a_clamped_window_says_so_in_the_same_line(monkeypatch, logs):
    _ask_native(_handler(monkeypatch, "2h"))

    lines = [
        record.getMessage() for record in logs.records if TRANSPORT_NATIVE in record.getMessage()
    ]
    assert "keep_alive=1800s" in lines[0]
    assert "超过上限" in lines[0]
    assert keep_alive_log(resolve_keep_alive("2h")).startswith("1800s ")


def test_the_compat_log_line_names_the_window_too(monkeypatch, logs):
    handler = _handler(monkeypatch, "15m")
    _compat_on(handler, stream_chunks=[_stream_chunk("x")])

    handler.chat([{"role": "user", "content": "答"}], stream=True)

    messages = [record.getMessage() for record in logs.records]
    assert any("keep_alive=900s" in message for message in messages), messages


# ==================== 判据④：卸载与失败语义一个都不许放宽 ====================


def test_the_refusal_statuses_are_still_the_same_four():
    """`NATIVE_REFUSED_STATUSES` 是 R92 刚结案的产物，本单一字未动。"""
    assert NATIVE_REFUSED_STATUSES == frozenset({400, 404, 405, 410})


def test_a_server_that_refuses_the_native_leg_still_falls_back_the_same_way(monkeypatch):
    handler = _handler(monkeypatch, "15m")
    compat = _compat_on(handler, content=REWRITE_JSON)
    handler._native_chat_request = _NativeRecorder(
        raises=_NativeChatUnsupported("HTTP 404: not found")
    )

    reply = handler.chat([{"role": "user", "content": "改写"}], stream=False)

    assert reply.transport == TRANSPORT_COMPAT
    assert str(reply) == REWRITE_JSON
    assert handler._native_supported is False
    assert compat.calls[0]["extra_body"] == {KEEP_ALIVE_FIELD: "900s"}


def test_a_transport_that_ismerely_unreachable_keeps_the_offline_verdict(monkeypatch):
    handler = _handler(monkeypatch, "15m")
    handler._native_chat_request = _NativeRecorder(raises=httpx.ConnectError("connection refused"))

    reply = handler.chat([{"role": "user", "content": "改写"}], stream=False)

    assert "离线模式" in reply
    assert reply.error_code == MODEL_UNAVAILABLE_CODE
    assert handler._native_supported is True, "连不上是暂时的，不该永久退役这条腿"


@pytest.mark.parametrize(
    ("content", "done_reason", "expected"),
    [
        ("", "stop", RESPONSE_EMPTY_CODE),
        ("   ", "stop", RESPONSE_EMPTY_CODE),
        ("", "length", OUTPUT_TRUNCATED_CODE),
    ],
)
def test_an_unusable_answer_is_still_announced_as_such(monkeypatch, content, done_reason, expected):
    """常驻上了路，空正文与截断的判据不许变得"看起来成功"。"""
    handler = _handler(monkeypatch, "15m")
    handler._native_chat_request = _NativeRecorder(
        body=_native_body(content=content, done_reason=done_reason)
    )

    reply = handler.chat([{"role": "user", "content": "改写"}], stream=False)

    assert reply.error_code == expected


def test_a_context_refusal_still_raises_the_typed_budget_error(monkeypatch):
    """超长请求的处置与常驻无关：照旧抛 `ModelContextLimitExceeded`，不退回第二腿。"""
    handler = _handler(monkeypatch, "15m")
    handler._native_chat_request = _NativeRecorder(
        raises=RuntimeError("n_ctx too small for this prompt")
    )
    compat = _compat_on(handler, content=REWRITE_JSON)

    with pytest.raises(ModelContextLimitExceeded):
        handler.chat([{"role": "user", "content": "改写"}], stream=False)

    assert compat.calls == []
    assert handler._native_supported is True


def test_a_reply_is_still_a_reply(monkeypatch):
    """`ModelReply` 的构造与判定一字未改：它仍然是 str，仍然带那四个属性。"""
    reply, _ = _ask_native(_handler(monkeypatch, "15m"))

    assert isinstance(reply, str) and isinstance(reply, ModelReply)
    assert json.loads(str(reply))["rewrites"]
    assert (reply.finish_reason, reply.output_tokens, reply.transport, reply.error_code) == (
        "stop",
        102,
        TRANSPORT_NATIVE,
        "",
    )
    assert ModelReply("x").transport == TRANSPORT_COMPAT


def test_the_residency_path_opens_no_socket(model_endpoint_guard):
    """判据⑥：本文件一条真 socket 都不许开（R56 的账本必须还是空的）。"""
    assert model_endpoint_guard.blocked_attempts == []
    assert model_endpoint_guard.sentinel == "__eb_test_disabled__"
