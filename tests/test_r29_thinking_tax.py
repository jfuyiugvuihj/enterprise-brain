"""R29 思考税：生成轮搬到原生 `/api/chat` 腿值不值——把裁定变成可重放的账。

工单判据（跟进单 §21 表 L501）要求四件事，本案的实测结论是「**不迁**」，所以本文件钉的不是
"迁好了"，而是"为什么不能这么迁"，一条真 socket 都不开（宿主真机数据在下面 D/E/F/G 四段以**逐字
帧与逐题表**的形式钉住，捕获脚本与时间写在每段自己的注释里）：

* 判据①（`thinking` 实测 0 字）——达成，但**达成的是个空壳**：原生腿 `think:false` 之后
  `thinking` 确实 0 字，同一串思考原文却整段落进 `content`（D 段逐字帧），所以"字段为 0"
  不等于"思考已关"。判据⑤「不许在无线上端点证据前宣布关掉了思考」正是为此而设。
* 判据②（30.6 s → ≤22 s）——**未达成**：同题同模型 n=8 生产形状 A/B（F 段），原生腿/兼容腿
  中位墙钟比 **0.9981**，把 30.6 s 按实测比例外推是 **30.5 s**。税没省，正文反而从 0 字变成
  667 字的思考口播。
* 判据③（证据链与逐类分数）——本单**未动** messages 装箱、`[来源: …]` 与权限过滤，逐类分数
  需要在跑分窗口里证明，按工单要求写「受阻」交回总控，不偷跑评测。
* 判据④（`tool_calls` 语义）——两腿报文形状**互斥**（E 段）：原生腿只收 `arguments` 对象，
  兼容腿只收 `arguments` 字符串，两边都是当场 400。这不是理论，是 C 段那枚离线重放钉住的
  产品行为：形状不对时原生腿被**整个进程退役**，改写腿跟着一起没。
* 判据⑥（退路）——B 段把 `keep_alive` 真正接进答题腿（跟进单 L1519 记在 R29 名下的那半笔），
  这是本单在"不迁腿"的前提下唯一能量化的省钱动作；真正的思考税出路是换模型，实测在 F 段末尾。

写域：`app/common/model_handler.py`、`app/agents/nodes.py`、`app/common/model_budget.py`、
`app/common/model_config.py` 与本文件。`tests/test_r100_thinking_switch.py:250` 那枚字节级钉子
不在写域内，B 段第 4 枚用例把"为什么只能条件化下发"钉在这里，反证 F3 把它变成有主的事实；G 段再钉一条：这台服务器今天对 /v1 侧的 keep_alive 根本不理，所以补齐的是请求面，不是常驻本身。
"""

import json
import logging
import statistics
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from app.agents import nodes
from app.agents.contracts import ModelTier
from app.common import model_budget
from app.common.model_budget import (
    MODEL_THINKING_ENV,
    OUTPUT_TRUNCATED_CODE,
    answer_text,
    model_tier_budget,
    produced_a_tool_call,
)
from app.common.model_config import (
    DEFAULT_KEEP_ALIVE_SECONDS,
    KEEP_ALIVE_CEILING_SECONDS,
    KEEP_ALIVE_ENV,
    resolve_keep_alive,
)
from app.common.model_handler import (
    KEEP_ALIVE_FIELD,
    RESPONSE_EMPTY_CODE,
    NATIVE_CHAT_SUFFIX,
    NATIVE_MAX_TOKENS_FIELD,
    NATIVE_THINK_FIELD,
    TRANSPORT_COMPAT,
    ModelHandler,
    ModelReply,
    ModelSource,
    _NativeChatUnsupported,
    answer_error_code,
)
from app.trace.spans import model_token_counts

GREETING = [HumanMessage(content="你好")]
#: 一个不存在的机器名：万一有缝没堵住，它也只能 DNS 失败，绝不会碰到宿主 Ollama 的端口。
SAFE_BASE_URL = "http://model.internal:11434/v1"
SAFE_MODEL = "qwen3.5:9b"
#: 宿主实测的错误原文（%TEMP%\r29_probe9.py 七格矩阵，2026-09-21）：把 OpenAI 形状的
#: ``tool_calls.arguments``（字符串）打上原生腿，服务端当场回的就是这一串。
NATIVE_400_ON_STRING_ARGS = "HTTP 400: {\"error\":\"Value looks like object, but can't find closing '}' symbol\"}"
#: The canned native body for the payload nails: content only, nothing else claimed.
NATIVE_OK_BODY = {
    "model": SAFE_MODEL,
    "message": {"role": "assistant", "content": "ok"},
    "done": True,
    "done_reason": "stop",
}


@pytest.fixture(autouse=True)
def _clean_model_env(monkeypatch):
    """每个用例自己拥有常驻与思考开关，不继承宿主 shell 里恰好导出的那一个。"""
    monkeypatch.delenv(KEEP_ALIVE_ENV, raising=False)
    monkeypatch.delenv(MODEL_THINKING_ENV, raising=False)
    #: 流式用例若漏还许可位，后面的用例会整片掉到离线腿，失败看起来像"字段没带"。
    model_budget.reset_default_budget()
    yield
    model_budget.reset_default_budget()


class _RecordingModel:
    """Stand-in provider: records the wire arguments, opens no socket."""

    def __init__(self, chunks=None):
        self.calls: list[dict] = []
        self.chunks = chunks if chunks is not None else [AIMessageChunk(content="一段答案")]

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append(kwargs)
        return AIMessage(content="一段答案", response_metadata={"finish_reason": "stop"})

    def stream(self, *args, **kwargs):
        self.calls.append(kwargs)
        yield from self.chunks

    def bind_tools(self, tools):
        return self

    @property
    def last_body(self):
        return self.calls[-1].get("extra_body") or {}


def _resilient(primary, tier: ModelTier = ModelTier.CHAT, *, budget="default"):
    """A model built the way `_make_model` builds one: this tier budget, on the compat leg."""
    return nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(tier) if budget == "default" else budget,
    )


class _NativeRecorder:
    """The native leg's seam: record the payload, replay a canned body, send nothing."""

    def __init__(self, body=None, raises=None):
        self.calls: list[dict] = []
        self.body = NATIVE_OK_BODY if body is None else body
        self.raises = raises

    def __call__(self, url, payload, *, timeout):
        self.calls.append({"url": url, "payload": payload, "timeout": timeout})
        if self.raises is not None:
            raise self.raises
        return self.body


def _handler(monkeypatch, *, base_url=SAFE_BASE_URL, model_name=SAFE_MODEL):
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", base_url)
    monkeypatch.setenv("LOCAL_MODEL_NAME", model_name)
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    return ModelHandler()


# ==================== B：常驻窗口进了答题腿（跟进单 L1519 记在 R29 名下的那半笔） ====================


@pytest.mark.parametrize("send", ["invoke", "stream"])
def test_the_answer_leg_asks_for_the_configured_residency_on_both_paths(monkeypatch, send):
    """`LOCAL_MODEL_KEEP_ALIVE=15m` used to reach the rewrite leg only; now both paths of this one."""
    monkeypatch.setenv(KEEP_ALIVE_ENV, "15m")
    primary = _RecordingModel()
    model = _resilient(primary)
    result = getattr(model, send)(GREETING)
    if send == "stream":
        list(result)

    assert primary.last_body[KEEP_ALIVE_FIELD] == "900s"


def test_a_window_above_the_ceiling_arrives_clamped_and_never_as_asked(monkeypatch):
    monkeypatch.setenv(KEEP_ALIVE_ENV, "2h")
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING)

    assert primary.last_body[KEEP_ALIVE_FIELD] == f"{KEEP_ALIVE_CEILING_SECONDS}s"
    assert primary.last_body[KEEP_ALIVE_FIELD] != "7200s"


@pytest.mark.parametrize("raw", ["-1", "infinite", "forever", "never", "1d"])
def test_never_unload_never_reaches_the_wire_from_this_leg(monkeypatch, raw):
    """The customer owns this RAM; the answer leg must not be able to pin it either."""
    monkeypatch.setenv(KEEP_ALIVE_ENV, raw)
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING)

    body = primary.last_body
    assert body[KEEP_ALIVE_FIELD] == f"{KEEP_ALIVE_CEILING_SECONDS}s"
    assert "-1" not in json.dumps(body)


def test_an_unset_variable_sends_no_field_at_all_which_is_the_r100_byte_claim(monkeypatch):
    """Why the field is asked for *conditionally*, and who owns that constraint.

    ``tests/test_r100_thinking_switch.py:250`` holds this leg's body to ``set(body) ==
    {"max_tokens"}`` in an ``enabled`` process: "switch thinking back on must be a no-op on
    the wire". That file is outside this ticket's write domain, so the only way to add a field
    here without breaking a claim this product already ratified is to add it when this
    deployment actually moved the window. A shipped ``15m`` does move it.
    """
    monkeypatch.setenv(MODEL_THINKING_ENV, "enabled")
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING)

    body = primary.last_body
    assert KEEP_ALIVE_FIELD not in body
    assert set(body) == {"max_tokens"}


def test_a_caller_that_brings_its_own_extra_body_cannot_delete_the_field(monkeypatch):
    """langchain merges call-time kwargs over client defaults; the boundary re-asserts its own."""
    monkeypatch.setenv(KEEP_ALIVE_ENV, "15m")
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING, extra_body={"max_tokens": 64})

    assert primary.last_body[KEEP_ALIVE_FIELD] == "900s"
    assert primary.last_body["max_tokens"] == 64


def test_a_caller_that_names_residency_itself_is_obeyed_not_overridden(monkeypatch):
    """An explicit value is a decision, not an accident -- same rule R100 set for `thinking`."""
    monkeypatch.setenv(KEEP_ALIVE_ENV, "15m")
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING, extra_body={KEEP_ALIVE_FIELD: "30s"})

    assert primary.last_body[KEEP_ALIVE_FIELD] == "30s"


def test_the_tool_bound_leg_carries_the_same_residency(monkeypatch):
    """`bind_tools` rebuilds the wrapper; a field added in one constructor only would be lost."""
    monkeypatch.setenv(KEEP_ALIVE_ENV, "20m")
    primary = _RecordingModel()
    _resilient(primary).bind_tools([SimpleNamespace(name="search_docs")]).invoke(GREETING)

    assert primary.last_body[KEEP_ALIVE_FIELD] == "1200s"


def test_the_window_is_resolved_per_call_not_frozen_when_the_model_was_built(monkeypatch):
    """An operator who edits the variable between two questions must not have to restart."""
    primary = _RecordingModel()
    model = _resilient(primary)
    monkeypatch.setenv(KEEP_ALIVE_ENV, "6m")
    model.invoke(GREETING)
    first = primary.last_body[KEEP_ALIVE_FIELD]
    monkeypatch.setenv(KEEP_ALIVE_ENV, "12m")
    model.invoke(GREETING)

    assert first == "360s"
    assert primary.last_body[KEEP_ALIVE_FIELD] == "720s"


def test_both_legs_ask_the_same_window_from_the_same_resolver(monkeypatch):
    """One variable, two transports: the caller must not need to know which leg answered."""
    monkeypatch.setenv(KEEP_ALIVE_ENV, "15m")
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING)
    native = _NativeRecorder()
    handler = _handler(monkeypatch)
    monkeypatch.setattr(handler, "_native_chat_request", native)
    handler.chat(messages=[{"role": "user", "content": "改写这个问题"}], source=ModelSource.LOCAL, stream=False)

    assert resolve_keep_alive().wire == ModelHandler._keep_alive().wire == "900s"
    assert primary.last_body[KEEP_ALIVE_FIELD] == resolve_keep_alive().wire
    assert native.calls[0]["payload"][KEEP_ALIVE_FIELD] == resolve_keep_alive().wire


def test_the_process_announces_residency_once_and_the_seam_arms_it_again(caplog):
    nodes.reset_keep_alive_mode_log()
    with caplog.at_level(logging.INFO):
        nodes._log_keep_alive_mode(SAFE_BASE_URL)
        nodes._log_keep_alive_mode(SAFE_BASE_URL)
    said = [rec.message for rec in caplog.records if "keep_alive=" in rec.message]

    assert len(said) == 1, said
    assert f"未下发，即用服务端默认 {DEFAULT_KEEP_ALIVE_SECONDS}s" in said[0]

    nodes.reset_keep_alive_mode_log()
    with caplog.at_level(logging.INFO):
        nodes._log_keep_alive_mode(SAFE_BASE_URL)

    assert len([rec for rec in caplog.records if "keep_alive=" in rec.message]) == 2


def test_a_configured_window_is_announced_with_its_wire_value(monkeypatch, caplog):
    monkeypatch.setenv(KEEP_ALIVE_ENV, "15m")
    nodes.reset_keep_alive_mode_log()
    with caplog.at_level(logging.INFO):
        nodes._log_keep_alive_mode(SAFE_BASE_URL)
    said = [rec.message for rec in caplog.records if "keep_alive=" in rec.message]

    assert len(said) == 1, said
    assert "兼容腿 keep_alive=900s" in said[0]
    assert "未下发" not in said[0]


# ==================== C：think 字段仍在原生腿上，且形状冲突不许把答案吃掉 ====================


def test_the_native_leg_still_says_think_false(monkeypatch):
    """反证①的靶子：摘掉这一行，D 段与这枚一起红——工单点名的那把。"""
    native = _NativeRecorder()
    handler = _handler(monkeypatch)
    monkeypatch.setattr(handler, "_native_chat_request", native)

    handler.chat(messages=[{"role": "user", "content": "改写这个问题"}], source=ModelSource.LOCAL, stream=False)

    payload = native.calls[0]["payload"]
    assert NATIVE_THINK_FIELD == "think"
    assert payload[NATIVE_THINK_FIELD] is False
    assert payload["stream"] is False
    assert native.calls[0]["url"].endswith(NATIVE_CHAT_SUFFIX)


def test_the_native_leg_still_carries_the_tier_cap_untouched(monkeypatch):
    native = _NativeRecorder()
    handler = _handler(monkeypatch)
    monkeypatch.setattr(handler, "_native_chat_request", native)

    handler.chat(messages=[{"role": "user", "content": "改写这个问题"}], source=ModelSource.LOCAL, stream=False)

    assert native.calls[0]["payload"]["options"][NATIVE_MAX_TOKENS_FIELD] == 256


def test_a_shape_refused_by_the_native_leg_downgrades_without_losing_the_answer(monkeypatch):
    """判据④的产品侧后果，按真机报文重放（E 段给出那枚 400 的原文）。

    原生腿把 400 归类为「这台服务器没有原生 API」，于是它**整个进程退役**，改写腿跟着一起
    退回兼容腿。这是既有分类（``NATIVE_REFUSED_STATUSES``），本单不改它，只把它钉住：
    形状冲突必须"少一条腿"，绝不能"少一个答案"。
    """
    native = _NativeRecorder(raises=_NativeChatUnsupported(NATIVE_400_ON_STRING_ARGS))
    handler = _handler(monkeypatch)
    completions = SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"rewrites": []}'), finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
    ))
    handler.ollama_client.chat.completions = completions
    monkeypatch.setattr(handler, "_native_chat_request", native)

    reply = handler.chat(messages=[{"role": "user", "content": "改写这个问题"}], source=ModelSource.LOCAL, stream=False)

    assert len(native.calls) == 1
    assert reply.transport == TRANSPORT_COMPAT
    assert str(reply) == '{"rewrites": []}'
    assert reply.error_code == ""
    assert handler._native_supported is False


def test_that_retirement_is_sticky_for_the_rest_of_the_process(monkeypatch):
    """The same fact from the other side: one client-side shape error costs both legs, forever.

    Deliberately a pin on current behaviour, not an endorsement. If a later ticket decides a
    400 caused by *our* message shape must not retire the leg, this is the test to change --
    and the one that proves the exposure is real today.
    """
    native = _NativeRecorder(raises=_NativeChatUnsupported(NATIVE_400_ON_STRING_ARGS))
    handler = _handler(monkeypatch)
    monkeypatch.setattr(handler, "_native_chat_request", native)
    rewrite = model_tier_budget(ModelTier.REWRITE)
    first = handler._native_chat(handler.ollama_client, handler.local_model, [], rewrite, 1)
    second = handler._native_chat(handler.ollama_client, handler.local_model, [], rewrite, 1)

    assert first is None and second is None
    assert len(native.calls) == 1, "退役之后不该再为原生腿花第二次钱"


# ==================== D：真机逐帧契约（2026-09-21，宿主 127.0.0.1:11434，qwen3:4b） ====================
# 捕获脚本 %TEMP%\r29_capture_frames.py，产物 %TEMP%\r29_frames.txt，帧文本由脚本原样落盘、
# 再由生成器逐字注入本文件末尾的 DATA_FRAMES —— 不手抄一个字符。
#: --- generated data below ---
# ==================== E：tool_calls 报文形状互斥（判据④） ====================
# ==================== F：n=8 生产形状 A/B 与"省税的唯一出路"（判据②） ====================

DATA_SIMPLE_NATIVE = (
    '{"model":"qwen3:4b","created_at":"2026-09-21T03:14:34.4696153Z","message":{"role":"assistant","content":"嗯"},"done":false}',
    '{"model":"qwen3:4b","created_at":"2026-09-21T03:14:35.2662791Z","message":{"role":"assistant","content":""},"done":true,"done_reason":"length","total_duration":827928200,"load_duration":7826400,"prompt_eval_count":19,"prompt_eval_cached_count":1,"prompt_eval_duration":18320000,"eval_count":64,"eval_duration":795725000}',
)
DATA_SIMPLE_COMPAT = (
    'data: {"id":"chatcmpl-296","object":"chat.completion.chunk","created":1789960475,"model":"qwen3:4b","system_fingerprint":"fp_ollama","choices":[{"index":0,"delta":{"role":"assistant","content":"","reasoning":"嗯"},"finish_reason":null}]}',
    'data: {"id":"chatcmpl-296","object":"chat.completion.chunk","created":1789960475,"model":"qwen3:4b","system_fingerprint":"fp_ollama","choices":[{"index":0,"delta":{},"finish_reason":"length"}]}',
)
DATA_TOOL200_NATIVE = (
    '{"model":"qwen3:4b","created_at":"2026-09-21T03:14:29.1916266Z","message":{"role":"assistant","content":"好的"},"done":false}',
    '{"model":"qwen3:4b","created_at":"2026-09-21T03:14:31.7706469Z","message":{"role":"assistant","content":""},"done":true,"done_reason":"length","total_duration":2932963300,"load_duration":7563800,"prompt_eval_count":149,"prompt_eval_cached_count":148,"prompt_eval_duration":237939000,"eval_count":200,"eval_duration":2578620000}',
)
DATA_TOOL200_COMPAT = (
    'data: {"id":"chatcmpl-495","object":"chat.completion.chunk","created":1789960471,"model":"qwen3:4b","system_fingerprint":"fp_ollama","choices":[{"index":0,"delta":{"role":"assistant","content":"","reasoning":"好的"},"finish_reason":null}]}',
    'data: {"id":"chatcmpl-495","object":"chat.completion.chunk","created":1789960471,"model":"qwen3:4b","system_fingerprint":"fp_ollama","choices":[{"index":0,"delta":{},"finish_reason":"length"}]}',
)
DATA_NATIVE_TOOL = (
    '{"model":"qwen3:4b","created_at":"2026-09-21T03:31:12.2801081Z","message":{"role":"assistant","content":"","tool_calls":[{"id":"call_pf1m0bmd","function":{"index":0,"name":"search_docs","arguments":{"query":"公司住宿费报销上限"}}}]},"done":false}',
    '{"model":"qwen3:4b","created_at":"2026-09-21T03:31:12.3069121Z","message":{"role":"assistant","content":""},"done":true,"done_reason":"stop","total_duration":5834797200,"load_duration":13101900,"prompt_eval_count":184,"prompt_eval_cached_count":3,"prompt_eval_duration":301261000,"eval_count":415,"eval_duration":5432819000}',
)
DATA_COMPAT_TOOL = (
    'data: {"id":"chatcmpl-222","object":"chat.completion.chunk","created":1789961472,"model":"qwen3:4b","system_fingerprint":"fp_ollama","choices":[{"index":0,"delta":{"content":"","tool_calls":[{"id":"call_xp9th20b","index":0,"type":"function","function":{"name":"search_docs","arguments":"{\\"query\\":\\"公司住宿费报销上限\\"}"}}]},"finish_reason":null}]}',
)
DATA_COMPAT_FINISH = (
    'data: {"id":"chatcmpl-346","object":"chat.completion.chunk","created":1789961502,"model":"qwen3:4b","system_fingerprint":"fp_ollama","choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}',
)

DATA_AB8_ROWS = [
    {
        "q": "我们经销商的标准回款周期是多少天？超期多久会停发新货？",
        "compat": {
            "wall_s": 5.562,
            "prompt_tokens": 374,
            "completion_tokens": 400,
            "cached_tokens": 8,
            "hidden_chars": 575,
            "content_chars": 0,
            "finish": "length"
        },
        "native": {
            "wall_s": 5.328,
            "prompt_tokens": 374,
            "completion_tokens": 400,
            "cached_tokens": 373,
            "hidden_chars": 0,
            "content_chars": 671,
            "finish": "length"
        }
    },
    {
        "q": "经销商回款周期超过 47 天会有什么后果？",
        "compat": {
            "wall_s": 5.266,
            "prompt_tokens": 371,
            "completion_tokens": 400,
            "cached_tokens": 370,
            "hidden_chars": 576,
            "content_chars": 0,
            "finish": "length"
        },
        "native": {
            "wall_s": 5.375,
            "prompt_tokens": 371,
            "completion_tokens": 400,
            "cached_tokens": 8,
            "hidden_chars": 0,
            "content_chars": 575,
            "finish": "length"
        }
    },
    {
        "q": "2026 年华东区经销商的回款周期和停发新货的口径分别是什么？",
        "compat": {
            "wall_s": 5.469,
            "prompt_tokens": 378,
            "completion_tokens": 400,
            "cached_tokens": 8,
            "hidden_chars": 601,
            "content_chars": 0,
            "finish": "length"
        },
        "native": {
            "wall_s": 5.281,
            "prompt_tokens": 378,
            "completion_tokens": 400,
            "cached_tokens": 377,
            "hidden_chars": 0,
            "content_chars": 615,
            "finish": "length"
        }
    },
    {
        "q": "单笔订单的折扣上限是多少？超出要怎么审批？",
        "compat": {
            "wall_s": 4.89,
            "prompt_tokens": 368,
            "completion_tokens": 370,
            "cached_tokens": 367,
            "hidden_chars": 565,
            "content_chars": 117,
            "finish": "stop"
        },
        "native": {
            "wall_s": 5.078,
            "prompt_tokens": 368,
            "completion_tokens": 370,
            "cached_tokens": 9,
            "hidden_chars": 0,
            "content_chars": 691,
            "finish": "stop"
        }
    },
    {
        "q": "回款周期和折扣上限这两条分别是怎么规定的？",
        "compat": {
            "wall_s": 5.297,
            "prompt_tokens": 368,
            "completion_tokens": 400,
            "cached_tokens": 8,
            "hidden_chars": 684,
            "content_chars": 0,
            "finish": "length"
        },
        "native": {
            "wall_s": 5.265,
            "prompt_tokens": 368,
            "completion_tokens": 400,
            "cached_tokens": 367,
            "hidden_chars": 0,
            "content_chars": 699,
            "finish": "length"
        }
    },
    {
        "q": "渠道政策里关于停发新货和折扣审批是怎么写的？",
        "compat": {
            "wall_s": 5.312,
            "prompt_tokens": 370,
            "completion_tokens": 400,
            "cached_tokens": 369,
            "hidden_chars": 641,
            "content_chars": 42,
            "finish": "length"
        },
        "native": {
            "wall_s": 5.359,
            "prompt_tokens": 370,
            "completion_tokens": 400,
            "cached_tokens": 10,
            "hidden_chars": 0,
            "content_chars": 664,
            "finish": "length"
        }
    },
    {
        "q": "经销商超期 15 天以上、折扣超过 12% 各自触发什么流程？",
        "compat": {
            "wall_s": 5.391,
            "prompt_tokens": 380,
            "completion_tokens": 400,
            "cached_tokens": 9,
            "hidden_chars": 482,
            "content_chars": 161,
            "finish": "length"
        },
        "native": {
            "wall_s": 5.391,
            "prompt_tokens": 380,
            "completion_tokens": 400,
            "cached_tokens": 379,
            "hidden_chars": 0,
            "content_chars": 657,
            "finish": "length"
        }
    },
    {
        "q": "华东区 2026 渠道政策的两条硬指标是什么，依据哪份文件？",
        "compat": {
            "wall_s": 5.39,
            "prompt_tokens": 379,
            "completion_tokens": 400,
            "cached_tokens": 378,
            "hidden_chars": 664,
            "content_chars": 0,
            "finish": "length"
        },
        "native": {
            "wall_s": 5.453,
            "prompt_tokens": 379,
            "completion_tokens": 400,
            "cached_tokens": 9,
            "hidden_chars": 0,
            "content_chars": 682,
            "finish": "length"
        }
    }
]
DATA_AB8_CAP = 400
DATA_AB8_MODEL = 'qwen3:4b'
DATA_AB8_SUMMARY = {
    "compat": {
        "wall_median": 5.35,
        "wall_p95": 5.562,
        "content_median": 0.0,
        "hidden_median": 588.5,
        "eval_median": 400.0,
        "cached_median": 188.0,
        "prompt_median": 372.5
    },
    "native": {
        "wall_median": 5.34,
        "wall_p95": 5.453,
        "content_median": 667.5,
        "hidden_median": 0.0,
        "eval_median": 400.0,
        "cached_median": 188.5,
        "prompt_median": 372.5
    }
}
DATA_AB8_RATIO = 0.9981
DATA_SWAP = {
    "qwen3:4b": [
        {
            "wall_s": 5.375,
            "eval": 400,
            "prompt_eval": 221,
            "cached": 9,
            "reason": "length",
            "content_chars": 0,
            "thinking_chars": 660,
            "head": ""
        },
        {
            "wall_s": 5.359,
            "eval": 400,
            "prompt_eval": 216,
            "cached": 9,
            "reason": "length",
            "content_chars": 0,
            "thinking_chars": 709,
            "head": ""
        },
        {
            "wall_s": 5.312,
            "eval": 400,
            "prompt_eval": 217,
            "cached": 9,
            "reason": "length",
            "content_chars": 0,
            "thinking_chars": 709,
            "head": ""
        },
        {
            "wall_s": 5.453,
            "eval": 400,
            "prompt_eval": 215,
            "cached": 9,
            "reason": "length",
            "content_chars": 0,
            "thinking_chars": 671,
            "head": ""
        },
        {
            "wall_s": 5.375,
            "eval": 400,
            "prompt_eval": 228,
            "cached": 9,
            "reason": "length",
            "content_chars": 0,
            "thinking_chars": 664,
            "head": ""
        },
        {
            "wall_s": 5.39,
            "eval": 400,
            "prompt_eval": 226,
            "cached": 9,
            "reason": "length",
            "content_chars": 78,
            "thinking_chars": 583,
            "head": "根据知识库搜索结果，华东区2026年渠道政策的两条硬指标及依据文件如下：\\n\\n1. **回款周期**  \\n   2026年"
        },
        {
            "wall_s": 5.36,
            "eval": 400,
            "prompt_eval": 218,
            "cached": 8,
            "reason": "length",
            "content_chars": 0,
            "thinking_chars": 589,
            "head": ""
        },
        {
            "wall_s": 5.39,
            "eval": 400,
            "prompt_eval": 227,
            "cached": 8,
            "reason": "length",
            "content_chars": 0,
            "thinking_chars": 573,
            "head": ""
        }
    ],
    "qwen2.5:3b-instruct": [
        {
            "wall_s": 3.531,
            "eval": 53,
            "prompt_eval": 226,
            "cached": 0,
            "reason": "stop",
            "content_chars": 83,
            "thinking_chars": 0,
            "head": "根据提供的政策文档，2026年华东区经销商的标准回款周期为47天。如果经销商超期15天未完成回款，将从第47天开始停发新"
        },
        {
            "wall_s": 0.625,
            "eval": 56,
            "prompt_eval": 221,
            "cached": 9,
            "reason": "stop",
            "content_chars": 98,
            "thinking_chars": 0,
            "head": "根据提供的文档内容，单笔订单的折扣上限是成交价的12%，超出此上限需要渠道总监书面审批。相关文件来源为 \"demo-po"
        },
        {
            "wall_s": 1.187,
            "eval": 110,
            "prompt_eval": 219,
            "cached": 9,
            "reason": "stop",
            "content_chars": 174,
            "thinking_chars": 0,
            "head": "根据提供的政策文档内容，关于回款周期和折扣上限的规定如下：\\n\\n### 回款周期\\n2026 年华东区经销商的标准回款周期为"
        },
        {
            "wall_s": 1.406,
            "eval": 136,
            "prompt_eval": 221,
            "cached": 9,
            "reason": "stop",
            "content_chars": 219,
            "thinking_chars": 0,
            "head": "根据提供的文档内容，关于停发新货和折扣审批的政策如下：\\n\\n### 停发新货\\n- **回款周期**：2026年华东区经销商"
        },
        {
            "wall_s": 0.969,
            "eval": 91,
            "prompt_eval": 230,
            "cached": 9,
            "reason": "stop",
            "content_chars": 147,
            "thinking_chars": 0,
            "head": "根据文档内容，经销商超期 15 天以上触发的流程是停发新货，而折扣超过 12% 则需要渠道总监书面审批。\\n\\n- **经销"
        },
        {
            "wall_s": 0.906,
            "eval": 85,
            "prompt_eval": 228,
            "cached": 8,
            "reason": "stop",
            "content_chars": 129,
            "thinking_chars": 0,
            "head": "华东区 2026 年的渠道政策中，关于回款周期的两条硬指标是：\\n\\n1. 标准回款周期为 47 天。\\n2. 超期 15 天"
        },
        {
            "wall_s": 0.812,
            "eval": 76,
            "prompt_eval": 221,
            "cached": 8,
            "reason": "stop",
            "content_chars": 120,
            "thinking_chars": 0,
            "head": "根据文档内容，如果经销商的回款周期超过47天，将会从第47天开始，每超期15天就会暂停发放新的货物。具体来说，如果经销商"
        },
        {
            "wall_s": 1.344,
            "eval": 129,
            "prompt_eval": 231,
            "cached": 9,
            "reason": "stop",
            "content_chars": 187,
            "thinking_chars": 0,
            "head": "根据提供的文档内容，2026年华东区经销商的回款周期为47天，如果经销商的回款周期超过47天，将从第47天开始，每超期1"
        }
    ]
}
DATA_SWAP_SUMMARY = {
    "qwen3:4b": {
        "wall_median": 5.375,
        "eval_median": 400.0,
        "content_median": 0.0,
        "thinking_median": 662.0,
        "reasons": [
            "length"
        ]
    },
    "qwen2.5:3b-instruct": {
        "wall_median": 1.078,
        "eval_median": 88.0,
        "content_median": 138.0,
        "thinking_median": 0.0,
        "reasons": [
            "stop"
        ]
    }
}
DATA_PS_MODEL = "qwen3:4b"
DATA_PS_ROWS = [
    {
        "step": "version",
        "ollama": "0.34.2"
    },
    {
        "step": "native keep_alive=20m",
        "seconds_left": 1200
    },
    {
        "step": "compat keep_alive=20m",
        "seconds_left": 1200
    },
    {
        "step": "compat no field",
        "seconds_left": 1200
    },
    {
        "step": "native keep_alive=6m",
        "seconds_left": 360
    },
    {
        "step": "compat keep_alive=1800s",
        "seconds_left": 360
    }
]


# ==================== D：契约钉 —— "thinking 0 字" 与 "思考已关" 是两件事（判据①⑤） ====================


def _payload(line: str) -> dict:
    """One captured wire frame -> dict, whether it came from SSE or the native stream."""
    return json.loads(line[5:].strip() if line.startswith("data:") else line)


def test_the_same_thinking_token_lands_in_another_field_on_the_other_leg():
    """判据①达成、判据⑤否决：两枚逐字帧只差字段名，不差内容。

    同一发请求（无工具、cap 64、宿主 qwen3:4b、2026-09-21 03:14），原生腿把第一个思考字写进
    ``message.content``，兼容腿把**同一个字**写进 ``delta.reasoning``。把生成轮搬过去，
    ``thinking`` 确实变 0 字——因为思考换了地址。
    """
    native_first = _payload(DATA_SIMPLE_NATIVE[0])
    compat_first = _payload(DATA_SIMPLE_COMPAT[0])

    assert native_first["message"]["content"] == "嗯"
    assert "thinking" not in native_first["message"]
    assert compat_first["choices"][0]["delta"] == {"role": "assistant", "content": "", "reasoning": "嗯"}


def test_think_false_does_not_buy_back_a_single_token():
    """两臂的预算账一模一样：cap 64 全部花在思考上，谁也没答完。"""
    native_done = _payload(DATA_SIMPLE_NATIVE[1])
    compat_finish = _payload(DATA_SIMPLE_COMPAT[1])

    assert native_done["eval_count"] == 64, "cap 64 全部花在思考上，一个 token 也没省回来"
    assert compat_finish["choices"][0]["finish_reason"] == "length"
    assert answer_error_code(native_done["message"]["content"], native_done["done_reason"]) == OUTPUT_TRUNCATED_CODE
    assert answer_error_code("", compat_finish["choices"][0]["finish_reason"]) == OUTPUT_TRUNCATED_CODE


def test_the_relabelled_chain_of_thought_would_ship_as_a_perfect_answer():
    """为什么"字段为 0"不能当验收：口播既不为空、也没被截断，评分器只会说这轮成功了。"""
    narration = "好的，我现在需要回答用户的问题。首先，用户问的是回款周期是多少天。"

    assert answer_error_code(narration, "stop") == ""
    assert answer_text(SimpleNamespace(content=narration)) == narration.strip()

    native_done = _payload(DATA_NATIVE_TOOL[1])
    assert native_done["done_reason"] == "stop"
    assert native_done["message"]["content"] == ""
    assert DATA_AB8_SUMMARY["native"]["content_median"] > 500, "八题的口播中位数就在 F 段的表里"


def test_the_compat_stream_reports_no_usage_so_the_ledger_has_to_stay_null():
    """两臂逐字帧里没有任何 usage：流式生成轮的 token 计量本来就没有来源。

    这条不是待修项，是判据②那笔账的读数前提：改前/改后只能拿墙钟比，拿不到 token 差。
    """
    for line in DATA_SIMPLE_COMPAT + DATA_TOOL200_COMPAT + DATA_COMPAT_TOOL + DATA_COMPAT_FINISH:
        assert "usage" not in _payload(line), line

    counts = model_token_counts(AIMessageChunk(content="嗯"))
    assert counts == {"input_tokens": None, "output_tokens": None}
    assert model_token_counts(AIMessage(content="")) == {"input_tokens": None, "output_tokens": None}


def test_the_native_done_frame_reports_a_cached_count_the_ledger_has_no_place_for():
    """真机复测推翻 §21/`spans.py` 的一句话，并把证据钉在这里（R38 已结案，本单只具名上报）。

    原生 ``/api/chat`` 的 done 帧带 ``prompt_eval_cached_count``（本文件 4 枚 done 帧里分别是
    148/1/3/…），所以"本机 Ollama 不报 cached_tokens"不成立；`app/trace/spans.py` 不在本单
    写域，故这里只钉两件事：帧里有这个键，台账里没有这个字段。
    """
    done = _payload(DATA_SIMPLE_NATIVE[1])
    reply = ModelReply(
        "ok",
        finish_reason="stop",
        input_tokens=done["prompt_eval_count"],
        output_tokens=done["eval_count"],
    )

    assert "prompt_eval_cached_count" in done
    assert isinstance(done["prompt_eval_cached_count"], int)
    assert set(model_token_counts(reply)) == {"input_tokens", "output_tokens"}
    assert "prompt_eval_cached_count" not in json.dumps(model_token_counts(reply))


# ==================== E：tool_calls 报文形状互斥（判据④） ====================


def test_a_tool_call_arrives_as_an_object_on_one_leg_and_a_string_on_the_other():
    """同一枚工具调用、同一个 query、两种类型：这就是"报文重做"四个字的实价。"""
    native = _payload(DATA_NATIVE_TOOL[0])["message"]["tool_calls"][0]["function"]
    compat = _payload(DATA_COMPAT_TOOL[0])["choices"][0]["delta"]["tool_calls"][0]["function"]

    assert native["name"] == compat["name"] == "search_docs"
    assert isinstance(native["arguments"], dict)
    assert isinstance(compat["arguments"], str)
    assert json.loads(compat["arguments"]) == native["arguments"]


def test_the_history_langchain_builds_today_is_exactly_what_the_native_leg_refuses():
    """判据⑤的落地形态：不是"加个参数"，是要拦 LangChain 的序列化器。

    ``_convert_message_to_dict`` 把 ``args`` 字典 ``json.dumps`` 成字符串（OpenAI 形状），
    宿主原生腿对这种历史当场 400：``Value looks like object, but can't find closing '}' symbol``
    （%TEMP%\\r29_probe9.py 七格矩阵，2026-09-21：字符串 arguments 3/3 全 400，对象 4/4 全 200；
    反方向同样互斥，/v1 对对象 arguments 回 ``cannot unmarshal object ... of type string``）。
    只要这条序列化不变，生成轮就没有"只换端点"的迁法。
    """
    from langchain_openai.chat_models.base import _convert_message_to_dict

    converted = _convert_message_to_dict(
        AIMessage(content="", tool_calls=[{"name": "search_docs", "args": {"query": "住宿费"}, "id": "call_x"}])
    )

    assert isinstance(converted["tool_calls"][0]["function"]["arguments"], str)
    assert _payload(DATA_NATIVE_TOOL[0])["message"]["tool_calls"][0]["function"]["arguments"] == {"query": "公司住宿费报销上限"}


def test_the_two_legs_end_a_tool_round_with_different_words():
    """`done_reason` 与 `finish_reason` 不是同一族枚举，权限/超时判定不许照抄。"""
    native_finish = _payload(DATA_NATIVE_TOOL[1])["done_reason"]
    compat_finish = _payload(DATA_COMPAT_FINISH[0])["choices"][0]["finish_reason"]

    assert (native_finish, compat_finish) == ("stop", "tool_calls")
    assert answer_error_code("", native_finish) == RESPONSE_EMPTY_CODE
    assert answer_error_code("", compat_finish) == RESPONSE_EMPTY_CODE
    assert answer_error_code("正文", "length") == OUTPUT_TRUNCATED_CODE


def test_the_emptiness_guard_reads_both_tool_shapes_without_crying_wolf():
    """工具轮在两条腿上都不许被当成"没答"：这是判据④里"语义不丢"的那一半。"""
    call = {"name": "search_docs", "args": {"query": "住宿费"}, "id": "call_x"}
    native_shaped = AIMessage(content="", tool_calls=[call])
    compat_shaped = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": "search_docs", "args": '{"query": "', "id": "call_x", "index": 0}],
    )
    compat_done = AIMessageChunk(
        content="",
        tool_call_chunks=[{"name": None, "args": '住宿费"}', "id": None, "index": 0}],
    )

    assert produced_a_tool_call(native_shaped) is True
    assert produced_a_tool_call(compat_shaped) is True
    assert produced_a_tool_call(compat_done) is True
    assert answer_text(native_shaped) == ""
    assert model_budget.detect_empty_answer(native_shaped) is None
    assert model_budget.detect_empty_answer(compat_shaped) is None
    assert model_budget.detect_empty_answer(AIMessage(content="")) == model_budget.NO_ANSWER_CODE


# ==================== F：n=8 生产形状 A/B（判据②） ====================
# 请求体、工具与 cap=400 全部取自 scripts/perf_probe_think.py:gen_messages —— 那枚 30.6 s
# 台账行（docs/perf/raw/think_off.jsonl, case repeat0_as_product_no_option）用的就是它。
# 脚本 %TEMP%\r29_probe8.py，ABBA 交替，两臂同带 keep_alive=10m，宿主 qwen3:4b。


def _median(values):
    return round(statistics.median(values), 2)


def _p95(values):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def test_the_eight_questions_are_all_here_and_all_answered_by_both_arms():
    assert len(DATA_AB8_ROWS) == 8
    for row in DATA_AB8_ROWS:
        assert row["compat"]["wall_s"] > 0 and row["native"]["wall_s"] > 0
        assert row["compat"]["prompt_tokens"] == row["native"]["prompt_tokens"] or abs(
            row["compat"]["prompt_tokens"] - row["native"]["prompt_tokens"]
        ) <= 12, "同一枚请求体，两臂读进去的量必须对得上"


@pytest.mark.parametrize("arm", ["compat", "native"])
def test_the_measured_table_matches_the_medians_and_p95_printed_in_the_log(arm):
    """汇总数不许和逐题数各说一套。"""
    walls = [row[arm]["wall_s"] for row in DATA_AB8_ROWS]

    assert _median(walls) == DATA_AB8_SUMMARY[arm]["wall_median"]
    assert _p95(walls) == pytest.approx(DATA_AB8_SUMMARY[arm]["wall_p95"], abs=0.001)


def test_moving_the_generation_turn_buys_no_time():
    """判据②：**未达成**。逐题墙钟中位数之比贴着 1，token 一模一样。"""
    assert DATA_AB8_MODEL == "qwen3:4b"
    assert abs(DATA_AB8_RATIO - 1.0) <= 0.03, DATA_AB8_RATIO
    assert DATA_AB8_SUMMARY["native"]["eval_median"] == DATA_AB8_SUMMARY["compat"]["eval_median"] == float(DATA_AB8_CAP)
    assert DATA_AB8_SUMMARY["compat"]["hidden_median"] > 0
    assert DATA_AB8_SUMMARY["native"]["hidden_median"] == 0.0


def test_the_native_leg_would_replace_every_answer_with_a_monologue():
    """省不了时间还是坏的：八题的口播中位数 667 字，兼容臂的中位数是 0 字正文。"""
    assert DATA_AB8_SUMMARY["native"]["content_median"] > 500
    assert DATA_AB8_SUMMARY["compat"]["content_median"] == 0.0
    for row in DATA_AB8_ROWS:
        assert row["native"]["content_chars"] > 400
        assert row["native"]["hidden_chars"] == 0
        assert row["native"]["completion_tokens"] >= 370
        assert row["native"]["finish"] in {"length", "stop"}


def test_the_30_6_second_baseline_still_misses_22_seconds_after_the_move():
    """把实测比例外推到台账基线：30.6 s × 0.998 ≈ 30.5 s，离 ≤22 s 差着一整个思考链。

    基线数在本仓 `docs/perf/raw/think_off.jsonl` 里现读，不抄常数；那条记录用的模型
    （qwen3.5:9b）今天已不在宿主 `api/tags` 里，所以外推标注 `[算术]`。
    """
    ledger = Path(__file__).resolve().parents[1] / "docs" / "perf" / "raw" / "think_off.jsonl"
    baseline = None
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.startswith("JSONL "):
            continue
        row = json.loads(line[len("JSONL ") :])
        if row.get("case") == "repeat0_as_product_no_option":
            baseline = row
    assert baseline is not None, ledger
    projected = round(baseline["wall_s"] * DATA_AB8_RATIO, 1)

    assert baseline["wall_s"] > 25.0
    assert projected > 22.0, projected

def test_the_only_measured_lever_is_a_model_without_a_thinking_capability():
    """判据⑥该往哪走：同一个请求体、同一条原生腿，换掉思考能力才是数量级的差。

    %TEMP%\\r29_probe10.py，8 题，宿主 `/api/chat`，cap=400。qwen3:4b 每题都撞上 cap 且
    正文 0 字（thinking 662 字），qwen2.5:3b-instruct 每题 `done_reason=stop`、正文中位 138 字。
    30.6 s × (1.078 / 5.375) ≈ 6.1 s `[算术]`——**换模型属业主侧**，且质量必须回跑分窗口定价。
    """
    thinking = DATA_SWAP_SUMMARY["qwen3:4b"]
    plain = DATA_SWAP_SUMMARY["qwen2.5:3b-instruct"]

    assert thinking["reasons"] == ["length"] and plain["reasons"] == ["stop"]
    assert thinking["thinking_median"] > 500 and plain["thinking_median"] == 0.0
    assert plain["wall_median"] * 4 < thinking["wall_median"]
    assert round(30.6 * plain["wall_median"] / thinking["wall_median"], 1) <= 22.0

# ==================== G：常驻字段在服务端到底值不值（判据⑥的实测前提） ====================
# %TEMP%\r29_probe11c.py，宿主 Ollama /api/ps 的 expires_at 读数，2026-09-21，逐字注入。


def _window(step):
    for row in DATA_PS_ROWS:
        if row["step"] == step:
            return row["seconds_left"]
    raise AssertionError(step)


def test_the_native_leg_obeys_the_residency_field_and_the_compat_leg_ignores_it():
    """跟进单 L1519 那半笔的真实形状：客户端已经开口，`/v1` 那侧不认。

    读法：先把窗口拉到 20 分钟，再用三次兼容腿调用去试（要 20m / 什么都不带 / 要 1800 秒），
    `/api/ps` 的剩余窗口全程不动；只有回到原生腿填 6m，窗口才真的落到 360 秒。
    ⇒ 本单给答题腿补上的 `keep_alive` 是**请求面**的补齐，今天在这台机器上换不来常驻；
    同时也解释了为什么 R34 在 09-19 量到的「答案腿把窗口压回 5 分钟」在 0.34.2 上复现不了：
    兼容腿既不套用也不重置。
    """
    assert DATA_PS_ROWS[0]["ollama"] == "0.34.2", DATA_PS_ROWS[0]
    assert DATA_PS_MODEL == "qwen3:4b"
    assert _window("native keep_alive=20m") == 1200
    assert _window("compat keep_alive=20m") == 1200
    assert _window("compat no field") == 1200
    assert _window("native keep_alive=6m") == 360
    assert _window("compat keep_alive=1800s") == 360


def test_the_wiring_still_asks_so_a_server_that_listens_is_not_a_code_change(monkeypatch):
    """为什么明知被忽略还要发：把"要不要问"和"服务端理不理"分开钉，后者是服务器事实。"""
    monkeypatch.setenv(KEEP_ALIVE_ENV, "15m")
    primary = _RecordingModel()
    _resilient(primary).invoke(GREETING)
    native = _NativeRecorder()
    handler = _handler(monkeypatch)
    monkeypatch.setattr(handler, "_native_chat_request", native)
    handler.chat(messages=[{"role": "user", "content": "改写这个问题"}], source=ModelSource.LOCAL, stream=False)

    assert primary.last_body[KEEP_ALIVE_FIELD] == "900s", "兼容腿：问了，今天被忽略"
    assert native.calls[0]["payload"][KEEP_ALIVE_FIELD] == "900s", "原生腿：问了，今天有效"
