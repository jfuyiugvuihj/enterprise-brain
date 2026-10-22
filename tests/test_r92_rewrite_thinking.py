"""R92：思考型模型下的查询改写必须真的拿到正文，两类失败要分得开。

现网缺陷（总控 09-18 22:1x-22:3x 亲测，本单在容器里又复跑了一次对照）：非流式改写打的是
Ollama 的 OpenAI 兼容腿 ``/v1``，隐藏思维链照样计入 ``max_tokens=256``，于是每次都返回
200 + ``content=""`` + ``finish_reason=length``，``json.loads("")`` 当场炸，日志里只剩一句
"查询改写失败，返回原始问题"——每题白烧十几秒 GPU，而改写等于从来没生效过。

本文件钉四件事：
① 非流式这条边界改走原生 ``/api/chat`` + ``think:false``（判据②：机制断在根上，不是把
   REWRITE 的预算调大——``test_the_native_request_carries_the_untouched_rewrite_cap`` 把
   256 原地钉死）；
② 空正文/被长度截断 与 有正文但读不懂，两条路径的日志文案与 ``error_code`` 互不相同，
   ``length`` 那一条不许静默回退（判据③）；
③ ``stream=True`` 那条遗留答案口一字不变（判据②后半）；
④ 改写失败仍然回退成原始问题，检索不许被拖崩（判据③后半）。

全程离线：模型地址只出现 ``http://model.internal:11434`` 这种不存在的主机，真正的 HTTP 由
``_native_chat_request`` 这一个缝注入，一条真 socket 都不开；R56 闸门在收尾处再判一次。
"""
import json
import logging
from types import SimpleNamespace

import httpx
import pytest

from app.agents.contracts import ModelTier
from app.common import model_budget
from app.common.model_budget import ModelContextLimitExceeded, OUTPUT_TRUNCATED_CODE
from app.common.model_handler import (
    MODEL_UNAVAILABLE_CODE,
    RATE_LIMITED_CODE,
    RESPONSE_EMPTY_CODE,
    TRANSPORT_COMPAT,
    TRANSPORT_NATIVE,
    ModelHandler,
    ModelReply,
    ModelSource,
    _NativeChatUnsupported,
    answer_error_code,
    compat_reply,
)
from app.rag import retrieval_pipeline

QUESTION = "住宿费标准是多少？"
REWRITE_JSON = json.dumps(
    {
        "rewrites": ["住宿费报销上限是多少", "差旅住宿费标准规定", "酒店住宿费限额标准"],
        "sub_questions": ["住宿费标准按职级区分吗", "超标部分如何审批"],
    },
    ensure_ascii=False,
)
#: 一个不存在的机器名：万一有缝没堵住，它也只能 DNS 失败，绝不会碰到宿主 Ollama 的端口。
SAFE_BASE_URL = "http://model.internal:11434/v1"


def _handler(monkeypatch, *, base_url=SAFE_BASE_URL, model_name="qwen3.5:9b"):
    """一个装着真 OpenAI 客户端的 handler：建客户端不开 socket，真 HTTP 由用例注入。"""
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", base_url)
    monkeypatch.setenv("LOCAL_MODEL_NAME", model_name)
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    return ModelHandler()


def _native_body(content=REWRITE_JSON, done_reason="stop", eval_count=102, thinking=""):
    """Ollama 原生 /api/chat 的响应形状：正文在 ``message.content``，不在顶层。"""
    message = {"role": "assistant", "content": content}
    if thinking:
        message["thinking"] = thinking
    return {
        "model": "qwen3.5:9b",
        "message": message,
        "done_reason": done_reason,
        "done": True,
        "eval_count": eval_count,
    }


def _compat_on(handler, **kwargs):
    """给真客户端装一个会记账的 ``completions``。

    只有 ``stream`` 这一个开关有权决定走哪条腿，所以这些用例必须留着真 ``OpenAI`` 客户端
    （否则"没走原生腿"是被 transport 挡掉的，证明不了流式那条判据），只把最里层的
    ``completions`` 换成记账替身，一次真 HTTP 都不发。
    """
    completions = _CompatCompletions(**kwargs)
    handler.ollama_client.chat.completions = completions
    return completions


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


class _CompatCompletions:
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


class _CompatClient:
    """只实现 ``chat.completions`` 的替身：它不属于本 handler，所以不该被换腿。"""

    def __init__(self, **kwargs):
        self.completions = _CompatCompletions(**kwargs)
        self.chat = SimpleNamespace(completions=self.completions)

    @property
    def calls(self):
        return self.completions.calls


def _stream_chunk(content):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content))])


def _stub_chat(monkeypatch, reply):
    """把改写这一步的模型出口钉成一条预定应答，其余链路全用真的。"""

    class _Stub:
        def __init__(self, value):
            self.value = value
            self.calls = []

        def chat(self, *, messages, source, stream, **kwargs):
            self.calls.append({"messages": messages, "source": source, "stream": stream})
            return self.value

    stub = _Stub(reply)
    monkeypatch.setattr(retrieval_pipeline, "model", stub)
    return stub


class _RecordingSemantic:
    def __init__(self):
        self.queries = []

    def search(self, query, k=10, where=None):
        self.queries.append(query)
        return []


class _RecordingBM25:
    def __init__(self):
        self.queries = []

    def search(self, query, k=10, pred=None):
        self.queries.append(query)
        return []


def _bare_pipeline():
    """绕开 ``__init__``（它会连 Chroma），保住真·QueryRewriter 与真·search 组装。"""
    pipeline = retrieval_pipeline.RetrievalPipeline.__new__(retrieval_pipeline.RetrievalPipeline)
    pipeline.semantic = _RecordingSemantic()
    pipeline.bm25 = _RecordingBM25()
    pipeline.reranker = SimpleNamespace(rerank=lambda query, docs, top_k=5: [])
    pipeline.rewriter = retrieval_pipeline.QueryRewriter()
    return pipeline


@pytest.fixture
def rewriter_logs(caplog):
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    return caplog


def _rewrite_lines(caplog):
    return [record.getMessage() for record in caplog.records if "查询改写" in record.getMessage()]


# ==================== 判据②：非流式这条边界走原生腿 + think:false ====================


def test_rewrite_call_goes_to_the_native_api_with_thinking_off(monkeypatch):
    handler = _handler(monkeypatch)
    native = _NativeRecorder()
    monkeypatch.setattr(handler, "_native_chat_request", native)

    reply = handler.chat(
        messages=[{"role": "user", "content": "改写这个问题"}],
        source=ModelSource.LOCAL,
        stream=False,
    )

    assert isinstance(reply, str) and str(reply) == REWRITE_JSON
    assert len(native.calls) == 1, "一次改写只许付一次推理"
    call = native.calls[0]
    assert call["url"] == "http://model.internal:11434/api/chat"
    assert call["payload"]["think"] is False
    assert call["payload"]["stream"] is False
    assert call["payload"]["model"] == "qwen3.5:9b"
    assert call["payload"]["messages"] == [{"role": "user", "content": "改写这个问题"}]
    assert reply.transport == TRANSPORT_NATIVE
    assert reply.finish_reason == "stop"
    assert reply.output_tokens == 102
    assert reply.error_code == ""


def test_the_native_request_carries_the_untouched_rewrite_cap(monkeypatch):
    """「只调大 max_tokens 不算修好」：256 必须原地不动，并原样进原生请求。"""
    handler = _handler(monkeypatch)
    native = _NativeRecorder()
    monkeypatch.setattr(handler, "_native_chat_request", native)

    handler.chat(
        messages=[{"role": "user", "content": "改写这个问题"}],
        source=ModelSource.LOCAL,
        stream=False,
    )

    budget = ModelHandler._call_budget(stream=False)
    assert budget.tier is ModelTier.REWRITE
    assert model_budget.TIER_MAX_TOKEN_DEFAULTS[ModelTier.REWRITE] == 256
    assert budget.max_tokens == 256
    assert native.calls[0]["payload"]["options"]["num_predict"] == 256
    assert isinstance(native.calls[0]["timeout"], httpx.Timeout)


def test_streaming_call_never_touches_the_native_leg(monkeypatch):
    """遗留答案口逐字节不变：流式既不换腿，也不许被换腿逻辑碰一下。"""
    handler = _handler(monkeypatch)
    fake = _compat_on(handler, stream_chunks=[_stream_chunk("住宿"), _stream_chunk("费标准")])
    native = _NativeRecorder()
    monkeypatch.setattr(handler, "_native_chat_request", native)
    # 同一台服务器、同一个 handler：只有 stream 这一个字能决定走哪条腿。
    assert handler._native_chat_url(handler.ollama_client).endswith("/api/chat")

    stream = handler.chat(
        [{"role": "user", "content": "讲讲住宿费标准"}],
        source=ModelSource.LOCAL,
        stream=True,
    )

    assert [chunk.choices[0].delta.content for chunk in stream] == ["住宿", "费标准"]
    assert native.calls == [], "stream=True 不许尝试原生腿"
    assert fake.calls[0]["stream"] is True
    assert fake.calls[0]["max_tokens"] == ModelHandler._call_budget(stream=True).max_tokens
    # 流式收尾要把槽位还回来：还不回来，紧随其后的改写就会被限流挡在门口。
    reply = handler.chat(
        [{"role": "user", "content": "改写"}], source=ModelSource.LOCAL, stream=False
    )
    assert str(reply) == REWRITE_JSON
    assert reply.transport == TRANSPORT_NATIVE
    assert len(native.calls) == 1
    assert len(fake.calls) == 1, "非流式改写在原生腿成功时不该再打兼容腿"


def test_an_injected_transport_keeps_the_compatible_leg(monkeypatch):
    """换进来的 transport 只实现了 chat.completions，就不许给它凭空造第二条腿。"""
    handler = _handler(monkeypatch)
    fake = _CompatClient(content=REWRITE_JSON)
    handler.ollama_client = fake
    attempts = []

    def _spy(*args, **kwargs):
        attempts.append(args)
        raise AssertionError("替身客户端不该走原生腿")

    monkeypatch.setattr(handler, "_native_chat_request", _spy)

    reply = handler.chat(
        [{"role": "user", "content": "改写"}], source=ModelSource.LOCAL, stream=False
    )

    assert attempts == []
    assert str(reply) == REWRITE_JSON
    assert reply.transport == TRANSPORT_COMPAT
    assert handler._native_chat_url(fake) == ""


def test_the_offline_client_keeps_the_compatible_leg(monkeypatch):
    from app.common.model_handler import _OfflineChatClient

    handler = _handler(monkeypatch)
    handler.ollama_client = _OfflineChatClient()
    monkeypatch.setattr(
        handler, "_native_chat_request", lambda *a, **k: pytest.fail("离线客户端不该开腿")
    )

    reply = handler.chat(
        [{"role": "user", "content": "改写"}], source=ModelSource.LOCAL, stream=False
    )

    assert "离线模式" in reply
    assert reply.error_code == MODEL_UNAVAILABLE_CODE


def test_a_server_without_a_native_api_falls_back_once(monkeypatch, caplog):
    """只有 /v1 的端点（vLLM 那类）：探测一次、退回兼容腿，之后的改写不再重复付费。"""
    handler = _handler(monkeypatch)
    native = _NativeRecorder(raises=_NativeChatUnsupported("HTTP 404: not found"))
    monkeypatch.setattr(handler, "_native_chat_request", native)
    fake = _compat_on(handler, content=REWRITE_JSON)
    caplog.set_level(logging.WARNING, logger="enterprise_brain")

    first = handler.chat(
        [{"role": "user", "content": "改写"}], source=ModelSource.LOCAL, stream=False
    )
    second = handler.chat(
        [{"role": "user", "content": "改写"}], source=ModelSource.LOCAL, stream=False
    )

    assert len(native.calls) == 1, "原生腿不可用只许探一次"
    assert len(fake.calls) == 2
    assert str(first) == str(second) == REWRITE_JSON
    assert any("不支持原生" in record.getMessage() for record in caplog.records), caplog.text
    assert handler._native_supported is False


def test_native_transport_failure_keeps_the_offline_verdict(monkeypatch, caplog):
    handler = _handler(monkeypatch)
    monkeypatch.setattr(
        handler,
        "_native_chat_request",
        _NativeRecorder(raises=httpx.ConnectError("connection refused")),
    )
    fake = _compat_on(handler)
    caplog.set_level(logging.WARNING, logger="enterprise_brain")

    reply = handler.chat(
        [{"role": "user", "content": "改写"}], source=ModelSource.LOCAL, stream=False
    )

    assert "离线模式" in reply
    assert reply.error_code == MODEL_UNAVAILABLE_CODE
    assert reply.transport == TRANSPORT_NATIVE
    assert fake.calls == [], "服务端已经连不上，不该再打第二腿"
    assert any("provider unavailable" in r.getMessage() for r in caplog.records)
    assert handler._native_supported is True, "连不上是暂时的，不该永久退役这条腿"


def test_a_context_refusal_on_the_native_leg_is_still_typed_and_returns_its_slot(monkeypatch):
    handler = _handler(monkeypatch)
    monkeypatch.setattr(
        handler,
        "_native_chat_request",
        _NativeRecorder(raises=RuntimeError("n_ctx too small for this prompt")),
    )
    fake = _compat_on(handler, content=REWRITE_JSON)

    with pytest.raises(ModelContextLimitExceeded):
        handler.chat(
            [{"role": "user", "content": "改写"}], source=ModelSource.LOCAL, stream=False
        )

    assert handler._native_supported is True
    # 槽位必须还回来：漏一次，这台单卡机器之后每题都会被自己判成限流。
    monkeypatch.setattr(handler, "_native_chat_request", _NativeRecorder())
    reply = handler.chat(
        [{"role": "user", "content": "改写"}], source=ModelSource.LOCAL, stream=False
    )
    assert str(reply) == REWRITE_JSON
    assert fake.calls == []


# ==================== 判据③：空/截断 与 不可解析 必须分得开 ====================


def test_answer_error_code_separates_truncated_empty_and_usable():
    assert answer_error_code("", "length") == OUTPUT_TRUNCATED_CODE
    assert answer_error_code("半截 JSON", "length") == OUTPUT_TRUNCATED_CODE
    assert answer_error_code("", "stop") == RESPONSE_EMPTY_CODE
    assert answer_error_code("   ", "stop") == RESPONSE_EMPTY_CODE
    assert answer_error_code(REWRITE_JSON, "stop") == ""
    assert answer_error_code("", "") == RESPONSE_EMPTY_CODE


def test_compat_reply_keeps_the_truncation_evidence():
    """改前这条腿把 content 之外的东西全丢了：finish_reason 本来就在响应上。"""
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=""), finish_reason="length")],
        usage=SimpleNamespace(completion_tokens=256),
    )

    reply = compat_reply(response)

    assert reply.error_code == OUTPUT_TRUNCATED_CODE
    assert reply.finish_reason == "length"
    assert reply.output_tokens == 256
    assert reply.transport == TRANSPORT_COMPAT


def test_truncated_answer_is_announced_and_not_called_a_parse_failure(monkeypatch, rewriter_logs):
    _stub_chat(
        monkeypatch,
        ModelReply(
            "",
            finish_reason="length",
            output_tokens=256,
            error_code=OUTPUT_TRUNCATED_CODE,
        ),
    )

    result = retrieval_pipeline.QueryRewriter.rewrite(QUESTION)

    assert result == {"rewrites": [QUESTION], "sub_questions": []}
    loud = [r for r in rewriter_logs.records if OUTPUT_TRUNCATED_CODE in r.getMessage()]
    assert [r.levelname for r in loud] == ["ERROR"], loud
    assert _rewrite_lines(rewriter_logs) == [loud[0].getMessage()], _rewrite_lines(rewriter_logs)
    assert "rewrite_payload_unparseable" not in "\n".join(_rewrite_lines(rewriter_logs))
    assert not any(
        "查询改写失败，返回原始问题" in text for text in _rewrite_lines(rewriter_logs)
    )


def test_empty_answer_gets_a_different_code_and_wording(monkeypatch, rewriter_logs):
    _stub_chat(
        monkeypatch,
        ModelReply("", finish_reason="stop", error_code=RESPONSE_EMPTY_CODE),
    )

    retrieval_pipeline.QueryRewriter.rewrite(QUESTION)

    lines = _rewrite_lines(rewriter_logs)
    assert len(lines) == 1, lines
    assert RESPONSE_EMPTY_CODE in lines[0]
    assert lines[0].startswith("查询改写没有可用正文"), lines[0]
    assert OUTPUT_TRUNCATED_CODE not in lines[0]
    assert "rewrite_payload_unparseable" not in lines[0]


def test_unparseable_answer_gets_its_own_code(monkeypatch, rewriter_logs):
    _stub_chat(monkeypatch, "抱歉，这个问题我不需要改写。")

    result = retrieval_pipeline.QueryRewriter.rewrite(QUESTION)

    lines = _rewrite_lines(rewriter_logs)
    assert result == {"rewrites": [QUESTION], "sub_questions": []}
    assert len(lines) == 1, lines
    assert lines[0].startswith("查询改写正文解析失败"), lines[0]
    assert "error_code=rewrite_payload_unparseable" in lines[0]
    assert "正文字数=" in lines[0]
    assert OUTPUT_TRUNCATED_CODE not in lines[0]
    assert RESPONSE_EMPTY_CODE not in lines[0]


def test_a_bare_empty_string_from_a_stub_is_not_reported_as_unparseable(monkeypatch, rewriter_logs):
    """出口只承诺 str：桩回空串时也必须落在「没有正文」那一类，而不是伪装成解析失败。"""
    _stub_chat(monkeypatch, "")

    retrieval_pipeline.QueryRewriter.rewrite(QUESTION)

    lines = _rewrite_lines(rewriter_logs)
    assert len(lines) == 1, lines
    assert RESPONSE_EMPTY_CODE in lines[0]
    assert "rewrite_payload_unparseable" not in lines[0]


def test_an_unavailable_model_is_not_reported_as_a_rewrite_bug(monkeypatch, rewriter_logs):
    """模型根本没起来：上游已经警告过，这里只许以 WARNING 记一次自己的码。"""
    _stub_chat(
        monkeypatch,
        ModelReply(
            "离线模式：模型不可用（error_code=model_unavailable），未生成业务结论",
            error_code=MODEL_UNAVAILABLE_CODE,
        ),
    )

    result = retrieval_pipeline.QueryRewriter.rewrite(QUESTION)

    lines = _rewrite_lines(rewriter_logs)
    assert result == {"rewrites": [QUESTION], "sub_questions": []}
    assert len(lines) == 1, lines
    assert MODEL_UNAVAILABLE_CODE in lines[0]
    assert "rewrite_payload_unparseable" not in lines[0]


def test_rate_limited_rewrite_falls_back_without_looking_broken(monkeypatch, rewriter_logs):
    handler = _handler(monkeypatch)
    held = handler._budget.acquire(wait_seconds=0)
    monkeypatch.setattr(retrieval_pipeline, "model", handler)
    try:
        result = retrieval_pipeline.QueryRewriter.rewrite(QUESTION)
    finally:
        held.release()
        model_budget.reset_default_budget()

    lines = _rewrite_lines(rewriter_logs)
    assert result == {"rewrites": [QUESTION], "sub_questions": []}
    assert len(lines) == 1, lines
    assert RATE_LIMITED_CODE in lines[0]
    assert "rewrite_payload_unparseable" not in lines[0]


# ==================== 判据②后半 + 契约：解析助手与成功路径 ====================


@pytest.mark.parametrize(
    "text",
    [
        REWRITE_JSON,
        "```json\n" + REWRITE_JSON + "\n```",
        "```\n" + REWRITE_JSON + "\n```",
        "好的：\n" + REWRITE_JSON + "\n以上。",
        "```json\n" + REWRITE_JSON + "```",
    ],
)
def test_every_payload_shape_still_parses(monkeypatch, text):
    _stub_chat(monkeypatch, text)

    result = retrieval_pipeline.QueryRewriter.rewrite(QUESTION)

    assert len(result["rewrites"]) == 3
    assert len(result["sub_questions"]) == 2


def test_the_success_line_counts_versions_and_sub_questions(monkeypatch, rewriter_logs):
    _stub_chat(monkeypatch, REWRITE_JSON)

    result = retrieval_pipeline.QueryRewriter.rewrite(QUESTION)

    assert _rewrite_lines(rewriter_logs) == ["查询改写: 3 个版本, 2 个子问题"]
    assert result["rewrites"][0] == "住宿费报销上限是多少"
    assert result["sub_questions"] == ["住宿费标准按职级区分吗", "超标部分如何审批"]


def test_a_scalar_rewrites_field_cannot_take_the_retrieval_down(monkeypatch):
    """模型把 rewrites 回成一个字符串时，老写法会把它原样递进 ``[query] + rewrites``。"""
    _stub_chat(monkeypatch, json.dumps({"rewrites": "住宿费限额", "sub_questions": None}))
    monkeypatch.setenv(retrieval_pipeline.TIER_ENV, "full")
    pipeline = _bare_pipeline()

    docs, rewrites = pipeline.search(QUESTION, top_k=3)

    assert rewrites == ["住宿费限额"]
    assert docs == []
    assert pipeline.semantic.queries[0] == QUESTION
    assert "住宿费限额" in pipeline.semantic.queries


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"rewrites": ["甲", " ", "乙"], "sub_questions": []}, (["甲", "乙"], [])),
        ({"rewrites": "单个字符串", "sub_questions": None}, (["单个字符串"], [])),
        (
            {"rewrites": [{"q": "形状不对"}, 7, "留下"], "sub_questions": ("元组里的一项",)},
            (["留下"], ["元组里的一项"]),
        ),
        ({}, ([], [])),
    ],
)
def test_payload_fields_are_coerced_into_usable_lists(monkeypatch, payload, expected):
    """约定的两个字段永远是「非空字符串列表」：检索拿到的是能直接拼接的东西。"""
    _stub_chat(monkeypatch, json.dumps(payload, ensure_ascii=False))

    result = retrieval_pipeline.QueryRewriter.rewrite(QUESTION)

    assert (result["rewrites"], result["sub_questions"]) == expected


def test_a_valid_payload_with_extra_keys_still_serves_the_contract(monkeypatch):
    """多带一个字段不算失败：检索只读约定的那两个键。"""
    _stub_chat(
        monkeypatch,
        json.dumps(
            {"rewrites": ["住宿费上限"], "sub_questions": [], "notes": "好的"}, ensure_ascii=False
        ),
    )

    result = retrieval_pipeline.QueryRewriter.rewrite(QUESTION)

    assert result == {"rewrites": ["住宿费上限"], "sub_questions": []}


# ==================== 判据①的离线镜像 + 判据⑥：整条路不开真 socket ====================


def test_rewrite_end_to_end_over_the_native_leg(monkeypatch, rewriter_logs):
    """容器里真机跑过的那一腿，在离线下的等价复现：原生腿正文直接进 json.loads。"""
    handler = _handler(monkeypatch)
    monkeypatch.setattr(handler, "_native_chat_request", _NativeRecorder())
    monkeypatch.setattr(retrieval_pipeline, "model", handler)
    monkeypatch.setenv(retrieval_pipeline.TIER_ENV, "full")

    result = retrieval_pipeline.QueryRewriter.rewrite(QUESTION)

    messages = [record.getMessage() for record in rewriter_logs.records]
    assert len(result["rewrites"]) == 3 and len(result["sub_questions"]) == 2, result
    assert not any("查询改写失败" in text for text in messages), messages
    assert not any("没有可用正文" in text for text in messages), messages
    assert any(TRANSPORT_NATIVE in text for text in messages), messages


def test_the_native_path_opens_no_socket(model_endpoint_guard):
    """判据⑥：这一文件的用例一条真 socket 都不许开（R56 的账本必须还是空的）。"""
    assert model_endpoint_guard.blocked_attempts == []
    assert model_endpoint_guard.sentinel == "__eb_test_disabled__"
