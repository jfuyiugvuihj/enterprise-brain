r"""R591 · 兼容腿必须带上端点真正读取的那一枚关闭思考字段，而且换腿与拒收都必须具名。

病（总控一手实测，run16 ``report-04`` / run17 ``report-04`` 同形）：worker 日志
``budget_verdict=fits max_tokens=1536 error_code=model_output_truncated`` 同一行第二枚
``error_code=no_answer_produced``，最终回答 0 字；ollama 侧同一发 ``eval time=38469ms /
1536 tokens`` 且 ``truncated=0`` —— 预算**正好吐满**，可见正文为零。

决定性测量（2026-10-03，同一台交付机、容器里 Ollama 0.34.0、qwen3.5:9b，凭据
``%TEMP%\r591-probe.txt`` 与 ``%TEMP%\evalrun\r591-compat-lever.txt``，六臂）：

  compat  thinking:{"type":"disabled"}        content   0  reasoning 5554  finish=length
  compat  不带任何字段                          content   0  reasoning 6041  finish=length
  compat  thinking + reasoning_effort:"none"  content 572  reasoning    0  finish=stop (8.48 s)
  native  think:false                          content 804  reasoning    0  finish=stop (12.35 s)

⇒ ``thinking`` 在 ``/v1`` 上是**惰性字段**（带与不带同形），``reasoning_effort`` 才是这条腿读取
的那一枚。本文件是这些数字的**离线镜像**：一条真 socket 都不开（R56 闸门在位），钉的是
「请求体里到底有哪几枚字段」「落到真线上时字段在顶层还是被 langchain 吃了」「换腿必须具名」
「服务端拒收这枚字段时必须有自己的错误码与计数，且不许用兜底文案掩盖空正文」。
真打模型那一腿在 ``tests/test_r591_live_thinking_off.py``，默认 skip，``EB_OLLAMA_ACCEPTANCE=1``
才跑（照 ``tests/_live_model.py`` 的在册门，与 ``tests/test_r540_*`` 同一先例）。

反证（摘刀必红，逐把见 docs/handoff/r591-*.md）：
 K1 摘掉 wire 里的 ``reasoning_effort`` → 本文件 ``..._carries_the_field_...`` 与真线顶层那枚同红。
 K2 把兼容腿的换腿退回成"只打日志不计数" → ``native_body_rejected`` 那枚计数钉红。
 K3 把字段拼成原生那枚 ``think:false``（§42 表 #7 已证 0 字）→ 逐字段点名的钉红。
 K4 用兜底文案掩盖空正文 → ``no_answer_produced`` 那两枚钉红。
"""

import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from app.agents import nodes
from app.agents.contracts import ModelTier
from app.common import model_budget
from app.common.model_budget import (
    LEVER_REJECTED_CODE,
    NO_ANSWER_CODE,
    NO_THINK_REQUEST_FIELDS,
    REASONING_EFFORT_DISABLED_VALUE,
    REASONING_EFFORT_REQUEST_FIELD,
    THINKING_REQUEST_FIELD,
    budget_event_counts,
    context_error_code,
    lever_rejection_code,
    model_budget_readout,
    model_tier_budget,
    no_think_request_fields,
    resolve_model_thinking,
    reset_budget_events,
    thinking_extra_body,
)
from app.common.model_handler import (
    TRANSPORT_COMPAT,
    TRANSPORT_NATIVE,
    ModelHandler,
    _NativeChatRequestRejected,
)

GREETING = [HumanMessage(content="住宿费标准是多少？")]
MODEL = "test-model"
#: A base_url on a host that is not this machine: the R56 gate only owns loopback model
#: ports, and a pin that needs a client object must not be one step away from a real call.
SAFE_BASE_URL = "http://model.internal:11434/v1"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every case owns MODEL_THINKING, the concurrency slots, and the counters."""
    monkeypatch.delenv(model_budget.MODEL_THINKING_ENV, raising=False)
    model_budget.reset_thinking_warning()
    model_budget.reset_default_budget()
    reset_budget_events()
    yield
    model_budget.reset_thinking_warning()
    model_budget.reset_default_budget()
    reset_budget_events()


class _RecordingModel:
    """Stand-in provider: records the wire arguments, opens no socket."""

    def __init__(self, content="一段答案", finish_reason="stop", chunks=None):
        self.calls = []
        self.content = content
        self.finish_reason = finish_reason
        self.chunks = chunks if chunks is not None else [AIMessageChunk(content="一段答案")]

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append(kwargs)
        return AIMessage(
            content=self.content,
            response_metadata={"finish_reason": self.finish_reason},
        )

    def stream(self, *args, **kwargs):
        self.calls.append(kwargs)
        yield from self.chunks

    def bind_tools(self, tools):
        return self

    @property
    def last_body(self):
        return self.calls[-1].get("extra_body") or {}


def _resilient(primary, tier: ModelTier = ModelTier.ANALYSIS):
    """A model built the way ``_make_model`` builds one: this tier's budget, on the compat leg."""
    return nodes._ResilientModel(
        primary,
        provider="ollama",
        model_name=MODEL,
        capacity_wait_seconds=0,
        budget=model_tier_budget(tier),
    )


class _CompatRecorder:
    """The handler boundary's compat mouth: records what the SDK was handed."""

    def __init__(self, content="{}", raises=None):
        self.calls = []
        self.content = content
        self.raises = raises

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        message = SimpleNamespace(content=self.content)
        choice = SimpleNamespace(message=message, finish_reason="stop")
        usage = SimpleNamespace(prompt_tokens=20, completion_tokens=7)
        return SimpleNamespace(choices=[choice], usage=usage)


class _RefusingNative:
    """A native leg that answers 400 for this body and nothing else (R147's finding)."""

    def __init__(self, message="HTTP 400: tool_calls.arguments must be an object"):
        self.calls = []
        self.message = message

    def __call__(self, url, payload, *, timeout):
        self.calls.append({"url": url, "payload": payload})
        raise _NativeChatRequestRejected(self.message)


def _handler(monkeypatch, native_request=None):
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", SAFE_BASE_URL)
    monkeypatch.setenv("LOCAL_MODEL_NAME", MODEL)
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    monkeypatch.delenv("LOCAL_MODEL_KEEP_ALIVE", raising=False)
    handler = ModelHandler()
    if native_request is not None:
        handler._native_chat_request = native_request
    return handler


# ==================== 判据③④ · 请求体形状 ====================


def test_the_compat_body_carries_the_field_the_endpoint_reads():
    """正文非空的前提是这一枚字段在体里：``thinking`` 单独存在时它测的是 0 字。"""
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING)

    body = primary.last_body
    assert body[REASONING_EFFORT_REQUEST_FIELD] == REASONING_EFFORT_DISABLED_VALUE
    assert body[THINKING_REQUEST_FIELD] == {"type": "disabled"}
    assert body["max_tokens"] == model_tier_budget(ModelTier.ANALYSIS).max_tokens


def test_the_streamed_answer_leg_carries_it_too():
    """run16/run17 空正文的是流式那一发，所以恢复腿与生成腿都必须在同一枚体内带上它。"""
    primary = _RecordingModel(chunks=[AIMessageChunk(content="住宿费")])
    list(_resilient(primary).stream(GREETING))

    assert primary.last_body[REASONING_EFFORT_REQUEST_FIELD] == REASONING_EFFORT_DISABLED_VALUE


def test_the_field_reaches_the_real_wire_and_not_just_langchain_kwargs():
    """🔴 反稻草人：``extra_body`` 会被 langchain 深合并吗？这枚钉读 SDK 真发出去的 JSON。

    前两枚钉的是" kwargs 里有这枚字段"，而 kwargs 不等于报文：``langchain_openai`` 把
    ``extra_body`` 交给 openai SDK，由它并进**顶层** JSON body。这一枚用 ``httpx.MockTransport``
    把真 ``ChatOpenAI`` 的请求截在内存里，逐字节看那个 body——字段若被吞、被嵌进
    ``extra_body`` 子对象、或被改名，本钉当场红。
    """
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 1,
                "model": MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "回款以银行实际到账日期为准。"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40},
            },
        )

    primary = nodes.ChatOpenAI(
        base_url=SAFE_BASE_URL,
        api_key="test-key",
        model=MODEL,
        http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url=SAFE_BASE_URL),
        max_retries=0,
    )
    reply = _resilient(primary).invoke(GREETING)

    assert captured["url"].endswith("/v1/chat/completions"), captured["url"]
    body = captured["body"]
    assert body[REASONING_EFFORT_REQUEST_FIELD] == REASONING_EFFORT_DISABLED_VALUE, body
    assert body[THINKING_REQUEST_FIELD] == {"type": "disabled"}, body
    assert "extra_body" not in body, "字段必须在顶层，嵌一层就是另一枚没人读的键"
    assert str(reply.content) == "回款以银行实际到账日期为准。"


def test_the_near_miss_spellings_stay_out_of_both_bodies(monkeypatch):
    """K3 的正面：把兼容字段换成原生那枚 ``think:false``（§42 表 #7 实测 0 字）不许发生。"""
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING)

    assert "think" not in primary.last_body
    compat_handler = _handler(monkeypatch)
    compat = _CompatRecorder()
    compat_handler.ollama_client.chat.completions = compat
    compat_handler._native_chat_request = _RefusingNative()
    compat_handler.chat([{"role": "user", "content": "改写"}], stream=False)

    assert "think" not in compat.calls[0]["extra_body"]
    assert compat.calls[0]["extra_body"][REASONING_EFFORT_REQUEST_FIELD] == "none"


def test_an_enabled_process_sends_neither_spelling(monkeypatch):
    """运维旋钮的另一半：``MODEL_THINKING=enabled`` 必须把两枚字段一起撤掉，不是换成第三种写法。"""
    monkeypatch.setenv(model_budget.MODEL_THINKING_ENV, "enabled")
    assert thinking_extra_body() == {}
    assert no_think_request_fields() == ()
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING)
    assert THINKING_REQUEST_FIELD not in primary.last_body
    assert REASONING_EFFORT_REQUEST_FIELD not in primary.last_body


def test_a_caller_that_spells_the_lever_itself_is_obeyed():
    """R30 的 "caller wins" 跟着这枚字段一起成立：边界只在调用方没提时补它。"""
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING, extra_body={REASONING_EFFORT_REQUEST_FIELD: "low"})

    assert primary.last_body[REASONING_EFFORT_REQUEST_FIELD] == "low"


# ==================== 判据①③ · 换腿必须具名 ====================


def test_a_native_400_downgrade_is_counted_not_only_logged(monkeypatch):
    """静默退回Compat是本案要治的第二半：腿不退役是对的，"没人知道退了"不是。"""
    handler = _handler(monkeypatch)
    handler._native_chat_request = _RefusingNative()
    compat = _CompatRecorder()
    handler.ollama_client.chat.completions = compat
    before = budget_event_counts()["native_body_rejected"]

    reply = handler.chat([{"role": "user", "content": "改写"}], stream=False)

    assert budget_event_counts()["native_body_rejected"] == before + 1
    assert handler.native_leg_readout()["request_rejections"] == 1
    assert handler.native_leg_readout()["verdict"] == "request_rejected"
    assert handler._native_supported is True, "400 说的是我的报文，不是这台机没有原生 API"
    assert str(reply) == "{}"
    assert reply.transport == TRANSPORT_COMPAT
    assert compat.calls[0]["extra_body"][REASONING_EFFORT_REQUEST_FIELD] == "none"


def test_the_published_readout_counts_both_named_outcomes():
    """判据③ 要"可观测"：两枚新计数必须在 health 快照读得到的那张账里。"""
    readout = model_budget_readout()

    assert {"native_body_rejected", "lever_rejected"} <= set(readout["events"])
    assert readout["thinking"]["request_fields"] == list(NO_THINK_REQUEST_FIELDS)
    assert readout["thinking"]["compat_lever"] == {
        "field": REASONING_EFFORT_REQUEST_FIELD,
        "value": REASONING_EFFORT_DISABLED_VALUE,
    }


def test_an_empty_answer_line_names_the_leg_and_the_fields_it_sent(caplog):
    """run16/run17 事后问"这一发走的哪条腿、带了哪枚字段"，日志一个字都答不出来。现在必须答。"""
    primary = _RecordingModel(content="", finish_reason="length")

    with caplog.at_level(logging.ERROR):
        _resilient(primary).invoke(GREETING)

    line = next(rec.message for rec in caplog.records if NO_ANSWER_CODE in rec.message)
    assert f"transport={TRANSPORT_COMPAT}" in line, line
    assert "no_think_fields=thinking|reasoning_effort" in line, line
    assert "error_code=no_answer_produced" in line, line


def test_the_streamed_empty_verdict_names_the_leg_too(caplog):
    primary = _RecordingModel(chunks=[AIMessageChunk(content="")])

    with caplog.at_level(logging.ERROR):
        list(_resilient(primary).stream(GREETING))

    line = next(rec.message for rec in caplog.records if NO_ANSWER_CODE in rec.message)
    assert "stream=yes" in line and f"transport={TRANSPORT_COMPAT}" in line, line


def test_an_empty_body_is_never_repaired_with_a_friendly_sentence(caplog):
    """🔴 本案的禁区：兜底文案会把空正文变成客户看得见的一句客套话。"""
    primary = _RecordingModel(content="", finish_reason="length")

    with caplog.at_level(logging.ERROR):
        reply = _resilient(primary).invoke(GREETING)

    assert nodes.answer_text(reply) == "", "空正文必须原样交回，不许被换成任何成品句"
    assert NO_ANSWER_CODE in "".join(rec.message for rec in caplog.records)


# ==================== 判据③ · 字段被服务端拒收时的具名失败 ====================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('Error code: 400 - {"error":"this model does not support thinking"}', LEVER_REJECTED_CODE),
        ('Error code: 400 - Input not valid: {"reasoning_effort":"none"}', LEVER_REJECTED_CODE),
        ("HTTP 400: unsupported thinking parameter", LEVER_REJECTED_CODE),
        ("HTTP 400: messages too long, thinking is fine but the window is not", None),
        ("Error code: 500 - upstream reset", None),
    ],
)
def test_the_lever_rejection_is_read_from_the_servers_own_sentence(text, expected):
    assert lever_rejection_code(RuntimeError(text)) == expected


def test_a_length_refusal_still_outranks_the_lever_reading():
    """两句话都在同一条错误里时，窗口那一枚先赢——它有类型化的 raise 和自己的码。"""
    exc = RuntimeError("request (9000 tokens) exceeds the available context size (4096 tokens)")

    assert context_error_code(exc) is not None
    assert lever_rejection_code(exc) is None


def test_a_server_that_refuses_the_lever_counts_it_and_still_refuses_to_mask(monkeypatch, caplog):
    handler = _handler(monkeypatch)
    handler._native_chat_request = _RefusingNative()
    handler.ollama_client.chat.completions = _CompatRecorder(
        raises=RuntimeError('Error code: 400 - {"error":"this model does not support thinking"}')
    )

    with caplog.at_level(logging.ERROR):
        reply = handler.chat([{"role": "user", "content": "改写"}], stream=False)

    assert budget_event_counts()["lever_rejected"] == 1
    line = next(rec.message for rec in caplog.records if LEVER_REJECTED_CODE in rec.message)
    assert "no_think_fields=thinking|reasoning_effort" in line, line
    assert f"transport={TRANSPORT_COMPAT}" in line, line
    assert reply.error_code == "model_unavailable", "具名不改变裁定，只给它一个名字"


def test_the_answer_leg_reports_a_refused_lever_on_its_span(monkeypatch, caplog):
    """同一个码必须在生成腿那一侧也在场：批准恢复后重跑的就是这一侧。"""

    class _Boom:
        def invoke(self, messages, config=None, **kwargs):
            raise RuntimeError("HTTP 400: unsupported thinking parameter")

        def bind_tools(self, tools):
            return self

    finished = []
    monkeypatch.setattr(
        "app.trace.spans.start_model_call",
        lambda *a, **k: _FakeSpan(finished),
        raising=True,
    )
    with caplog.at_level(logging.ERROR):
        _resilient(_Boom()).invoke(GREETING)

    assert budget_event_counts()["lever_rejected"] == 1
    assert any(LEVER_REJECTED_CODE in rec.message for rec in caplog.records), caplog.text
    assert finished[0]["summary"] == {"lever_rejection_code": LEVER_REJECTED_CODE}
    assert finished[0]["status"] == "failed", "具名不许把这一发改判成别的东西"


class _FakeSpan:
    def __init__(self, sink):
        self.sink = sink
        self.finished = False

    def mark_first_token(self):
        return None

    def finish(self, status, *, error_code="", summary=None, record_evidence=True):
        self.finished = True
        self.sink.append({"status": status, "error_code": error_code, "summary": summary})
        return {}


def test_the_native_leg_still_asks_think_false_and_nothing_else(monkeypatch):
    """改判不许顺手把兼容字段搬到原生体上：那枚体已由 R29/R92 实测，多一个键就是新的未测改动。"""
    recorder = _NativeRecorder()
    handler = _handler(monkeypatch)
    handler._native_chat_request = recorder

    reply = handler._native_chat(
        handler.local_client,
        MODEL,
        [{"role": "user", "content": "改写"}],
        model_tier_budget(ModelTier.REWRITE),
        30,
    )

    payload = recorder.calls[0]["payload"]
    assert payload["think"] is False
    assert REASONING_EFFORT_REQUEST_FIELD not in payload
    assert THINKING_REQUEST_FIELD not in payload
    assert str(reply) == "{}"
    assert reply.transport == TRANSPORT_NATIVE


class _NativeRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, url, payload, *, timeout):
        self.calls.append({"url": url, "payload": payload, "timeout": timeout})
        return {"message": {"content": "{}"}, "done_reason": "stop", "eval_count": 7}


def test_a_model_that_is_thinking_anyway_still_costs_the_same_verdict():
    """字段带上了不等于模型一定不思考：判据不许变成"看起来关掉了就当成功"。"""
    policy = resolve_model_thinking()
    primary = _RecordingModel(content="", finish_reason="length")

    assert set(policy.wire) == set(NO_THINK_REQUEST_FIELDS)
    assert model_budget.detect_empty_answer(primary.invoke(GREETING)) == NO_ANSWER_CODE


# ==================== 判据④ · 三格 AND 的读法本身 ====================


def _live_reader():
    """Load the live file's reader without running its (model-gated) cases.

    The live pin is the only place the three facts can be read off a real frame, and a pin that
    skips by default must not be the only place its own assertion logic exists -- otherwise the
    day somebody relaxes it to ``content`` alone, nothing in the resident门 notices.
    """
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent / "test_r591_live_thinking_off.py"
    spec = importlib.util.spec_from_file_location("r591_live_reader", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Two frames as the server actually answered them today, readings verbatim from
#: ``%TEMP%\evalrun\r591-compat-lever.txt`（lever on, ``[实测]``）and
#: ``%TEMP%\r591-probe.txt`（总控 arm 1, lever off, ``[实测]``）. These are recorded numbers,
#: not a live call: this pin proves the *reader* can tell the two apart.
_LEVER_ON_FRAME = {
    "choices": [{"message": {"role": "assistant", "content": "据" * 286}, "finish_reason": "stop"}],
    "usage": {"completion_tokens": 338},
}
_LEVER_OFF_FRAME = {
    "choices": [
        {
            "message": {"role": "assistant", "content": "", "reasoning": "思" * 5554},
            "finish_reason": "length",
        }
    ],
    "usage": {"completion_tokens": 1536},
}


def test_the_three_fact_verdict_passes_only_on_a_frame_with_all_three():
    reader = _live_reader()

    assert reader.thinking_off_verdicts(reader.read_compat_frame(_LEVER_ON_FRAME)) == []


def test_the_inert_field_fails_the_same_verdict_on_all_three_counts():
    r"""K4 的靶子：谁想把这枚 AND 放宽成一格，这一钉先红，而且红得说出是哪三格。

    两枚 frame 是今天服务端真答出来的形状，读数逐字取自 ``%TEMP%\r591-probe.txt``（控制臂，
    ``[实测]``）与 ``%TEMP%\evalrun\r591-compat-lever.txt``（带字段臂，``[实测]``）。本钉不重跑
    模型，它证的是**读法**分得开这两枚——也就是证那枚惰性字段真的三格全丢。
    """
    reader = _live_reader()
    readings = reader.read_compat_frame(_LEVER_OFF_FRAME)

    assert readings["content"] == "" and readings["completion_tokens"] == 1536
    assert reader.thinking_off_verdicts(readings) == [
        "empty_content",
        "reasoning_not_empty",
        "finish_not_stop(length)",
    ]


def test_reasoning_is_unreadable_through_the_product_object(monkeypatch):
    """判据④ 的第二格只能读服务端原始帧：LangChain 把 ``message.reasoning`` 整通道丢掉。

    这一枚是"为什么不拿 ``_make_model`` 的对象去证思考为空"的凭据，用 ``MockTransport`` 在内存里
    跑，不开 socket。它同时也是一条产品事实：客户永远看不见思考链，所以空正文在 UI 上就是空正文。
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "c",
                "object": "chat.completion",
                "created": 1,
                "model": MODEL,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "住宿费按发票实报。",
                            "reasoning": "让我想想这个问题的背景……",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 20, "total_tokens": 32},
            },
        )

    primary = nodes.ChatOpenAI(
        base_url=SAFE_BASE_URL,
        api_key="test-key",
        model=MODEL,
        http_client=httpx.Client(transport=httpx.MockTransport(handler), base_url=SAFE_BASE_URL),
        max_retries=0,
    )
    reply = _resilient(primary).invoke(GREETING)

    assert nodes.answer_text(reply) == "住宿费按发票实报。"
    assert "让我想想" not in json.dumps(reply.additional_kwargs, ensure_ascii=False), (
        "思考链若进了 additional_kwargs，判据④ 的第二格就该改在这儿钉，本钉的说明就成了假话"
    )
