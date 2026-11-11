# -*- coding: utf-8 -*-
r"""R690 · ``/chat`` 流式那一发的 usage opt-in（计划书 R38 判据③ 缺的就是这一格）。

工单：``docs/tickets/R690-stream-usage-optin.md``。现取病形：R670 已经让 ``/chat`` 落
``model_calls`` 行，``app/api/v1/chat.py::chat`` 的在册循环也已经在读末片的 ``chunk.usage``，
``app/trace/spans.py::stream_usage_counts`` 把它折成 summary，``app/trace/projections.py`` 再把它
搬进两枚列 —— 缺的是**请求里从没向服务端要过数**：
``app/common/model_handler.py::ModelHandler.chat`` 不带 ``stream_options.include_usage``，
而同仓另一条腿 ``app/agents/orchestrator.py`` 早带了它。base 上的 wire body 键名集合是
``['keep_alive', 'max_tokens', 'messages', 'model', 'reasoning_effort', 'stream', 'thinking']``，
现取读数记在凭据纸 ``docs/testing/r690-2026-10-06.md``。

钉死的几件事，每件单独可失败：

1. 流式那一发的 **wire body** 带 ``{"include_usage": True}``（判据① 前半）；
2. 调用方自己写过 ``stream_options`` 就原样放行，不越俎代庖 —— 口径逐字照
   ``app/agents/nodes.py::_answer_leg_tap``（caller 写过就不动它），本单不另造规则（判据① 后半）；
3. 非流式的 body 一个字不受影响（同一条在册裁定：只有真走流式才把它放进请求）；
4. 真打一次 ``/chat``：``model_calls.input_tokens``／``output_tokens`` 逐枚等于夹具自报的那两枚
   （判据②）。**改前这枚必须红**，红在服务端没被要求报数 ⇒ 末片不带 usage；
5. 反证钉（判据③）：拿不到 usage 的那一形留 **NULL** 而不是 0（``app/common/model_handler.py``
   的在册规矩「绝不默认成 0」）；影子把那格折成 0 ⇒ 同一枚谓词当场为假，另配一枚未变源码的正控；
6. 观测不改正文：只带计量的末片一个字都不上屏，交出去的字与本单之前逐字相同；
7. 三枚格子各有自己的读数（判据⑤）：opt-in 没带／末帧没解析／解析了没落库，逐枚点名；
8. 🔴 本件**不**宣布 R38③ 翻绿 —— 真机那一格欠一扇安静窗（工单判据⑥：run32 之后抽查一问）。

夹具是一台**会说不**的假 Ollama 兼容腿：``/v1/chat/completions`` 只有在请求带了
``stream_options.include_usage`` 时才在末片报一次数（R31 现读，
``docs/perf/latency-budget-2026-09-16.md``）。请求里没那一格 ⇒ 流里就没有末片。所以本件判的是
「请求到底有没有要过数」，不是「夹具愿不愿意给」。

全程离线：``httpx.MockTransport`` 顶掉传输层，base_url 指向不存在的机器名，一次真 HTTP 都不发生；
真 SDK 解析、真路由、真 span 链，账落 ``tmp_path``，不连库、不起服务、不动容器、不打模型。
"""

import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from openai import OpenAI
from openai.types.completion_usage import CompletionUsage

from app.common import model_budget
from app.common.model_handler import TRANSPORT_COMPAT, ModelHandler
from app.trace.spans import stream_usage_counts
from test_r503_artifact_lineage_keys import load_shadow
from test_r670_legacy_chat_model_calls_row import (
    ANSWER_PIECES,
    COMPAT_USAGE,
    MODEL_NAME,
    _Retriever,
    _headers,
    _offline_store,
    _rows,
)

#: 一个不存在的机器名：万一有缝没堵住，它也只能 DNS 失败，碰不到宿主 Ollama 的端口。
SAFE_BASE_URL = "http://model.internal:11434/v1"
STREAM_OPTIONS_FIELD = "stream_options"
INCLUDE_USAGE = {"include_usage": True}
REWRITE_REPLY = json.dumps(
    {"rewrites": ["住宿费报销上限是多少"], "sub_questions": []}, ensure_ascii=False
)
#: ``usage_keys`` 记的是那块东西自己的键名（``app/trace/spans.py::stream_usage_counts`` 的在册口径）。
#: 真 SDK 把末片反序列化成 ``CompletionUsage``，它比夹具多两枚 ``*_tokens_details`` —— 那是拼写，
#: 不是数。名单由 SDK 自己的模型字段现取，本件不手抄。
EXPECTED_USAGE_KEYS = sorted(CompletionUsage.model_fields)
SPANS = Path(__file__).resolve().parents[1] / "app" / "trace" / "spans.py"
#: 牙的靶（唯一命中，否则 load_shadow 当场报「这把刀会空转」）。
ABSENT_READING = '        return {"input_tokens": None, "output_tokens": None, "usage_keys": []}'
FOLDED_INTO_ZERO = '        return {"input_tokens": 0, "output_tokens": 0, "usage_keys": []}'


class _HonestOllamaCompat:
    """假兼容腿：按请求里那一格决定末片报不报数，并把真发出去的 wire body 原样记账。

    记账的是**序列化之后**的 body —— ``stream_options`` 要是不被 ``openai`` 的 SDK 接受，
    这一腿就当场炸，而不是等到生产。``honor_opt_in=False`` 那一形是给反证钉用的：
    一台不认这个选项的服务端（vLLM 之类），本单不许替它编数。
    """

    def __init__(self, *, usage=COMPAT_USAGE, honor_opt_in=True):
        self.usage = usage
        self.honor_opt_in = honor_opt_in
        self.bodies = []

    @property
    def client(self) -> OpenAI:
        return OpenAI(
            base_url=SAFE_BASE_URL,
            api_key="r690-offline",
            http_client=httpx.Client(
                transport=httpx.MockTransport(self._handle), trust_env=False
            ),
            max_retries=0,
        )

    def _frame(self, *, content=None, usage=None, finish_reason=None):
        frame = {
            "id": "chatcmpl-r690",
            "object": "chat.completion.chunk",
            "created": 1759000000,
            "model": MODEL_NAME,
            "choices": []
            if usage is not None
            else [{"index": 0, "delta": {"content": content or ""}, "finish_reason": finish_reason}],
        }
        if usage is not None:
            frame["usage"] = usage
        return frame

    def _sse(self, reports_usage: bool) -> bytes:
        frames = [self._frame(content=piece) for piece in ANSWER_PIECES]
        if reports_usage:
            frames.append(self._frame(usage=self.usage))
        frames.append(self._frame(finish_reason="stop"))
        return (
            "".join("data: %s\n\n" % json.dumps(frame) for frame in frames) + "data: [DONE]\n\n"
        ).encode("utf-8")

    def _completion(self) -> dict:
        return {
            "id": "chatcmpl-r690",
            "object": "chat.completion",
            "created": 1759000000,
            "model": MODEL_NAME,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": REWRITE_REPLY},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 116, "completion_tokens": 7, "total_tokens": 123},
        }

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if not body.get("stream"):
            return httpx.Response(200, json=self._completion())
        asked = bool((body.get(STREAM_OPTIONS_FIELD) or {}).get("include_usage"))
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=self._sse(asked and self.honor_opt_in),
        )


def _handler(monkeypatch, wire: _HonestOllamaCompat) -> ModelHandler:
    """真 handler 装假传输：客户端构造不开 socket，与 ``tests/test_r34_keep_alive_residency.py`` 同法。"""
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", SAFE_BASE_URL)
    monkeypatch.setenv("LOCAL_MODEL_NAME", MODEL_NAME)
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    monkeypatch.delenv("LOCAL_MODEL_KEEP_ALIVE", raising=False)
    model_budget.reset_default_budget()
    handler = ModelHandler()
    handler.local_client = wire.client
    handler.ollama_client = handler.local_client
    return handler


def _collect(stream):
    """逐字照 ``app/api/v1/chat.py::chat`` 的在册循环消费一条流：交回（正文, usage 帧列表）。"""
    pieces, usage_frames = [], []
    for chunk in stream:
        reported = getattr(chunk, "usage", None)
        if reported is not None:
            usage_frames.append(reported)
        for choice in getattr(chunk, "choices", None) or []:
            content = choice.delta.content
            if content:
                pieces.append(content)
    return "".join(pieces), usage_frames


def _absent_is_recorded_as_null(record) -> bool:
    """唯一的谓词：「服务端没报」在两枚列上必须是 NULL。P5 与那枚牙共用它，牙才咬得到钉。"""
    return record.get("input_tokens") is None and record.get("output_tokens") is None


def _drive_route(monkeypatch, tmp_path, handler):
    from app.api.v1 import chat
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": username,
            "username": username,
            "role": "staff",
            "department": "dept-a",
        },
    )
    monkeypatch.setattr(chat, "retriever", _Retriever())
    monkeypatch.setattr(chat, "model_handler", handler)
    store = _offline_store(tmp_path, monkeypatch)
    response = TestClient(app).post(
        "/api/v1/chat",
        json={"message": "残值率是多少"},
        headers=_headers("staff-r690"),
    )
    return response, store


# ==================== 判据① · opt-in 上得上不了请求 ====================


def test_the_streaming_request_asks_the_server_for_a_usage_tail_frame(monkeypatch):
    """判据① 前半：流式那一发的 wire body 必须带 ``{"include_usage": True}``。"""
    wire = _HonestOllamaCompat()
    handler = _handler(monkeypatch, wire)

    text, usage_frames = _collect(
        handler.chat([{"role": "user", "content": "残值率是多少"}], stream=True)
    )
    body = wire.bodies[-1]

    assert body["stream"] is True
    assert body.get(STREAM_OPTIONS_FIELD) == INCLUDE_USAGE, (
        "服务端没被要求报数，末片就不会带 usage —— 这正是 model_calls 两枚列为 NULL 的那一格"
    )
    assert len(usage_frames) == 1
    assert text == "".join(ANSWER_PIECES)


def test_a_caller_that_already_wrote_stream_options_keeps_its_own_values(monkeypatch):
    """判据① 后半：调用方写过 ``stream_options`` 就原样放行（口径照 ``app/agents/nodes.py::_answer_leg_tap``）。"""
    caller = {"include_usage": False}
    wire = _HonestOllamaCompat()
    handler = _handler(monkeypatch, wire)

    text, usage_frames = _collect(
        handler.chat(
            [{"role": "user", "content": "残值率是多少"}],
            stream=True,
            stream_options=caller,
        )
    )

    assert wire.bodies[-1][STREAM_OPTIONS_FIELD] == caller, "越俎代庖就是把调用方的声明吃掉"
    assert usage_frames == [], "服务端照请求回答：没被要数就没有末片，本件不许替它编"
    assert text == "".join(ANSWER_PIECES)


def test_the_non_streaming_body_is_not_touched(monkeypatch):
    """判据① 的边界：非流式的 body 一个字不受影响（只有真走流式才把它放进请求）。"""
    wire = _HonestOllamaCompat()
    handler = _handler(monkeypatch, wire)
    #: 原生腿已被判定不存在（R147 的在册状态），改写这一发落到兼容腿，请求才量得到。
    handler._native_supported = False

    reply = handler.chat([{"role": "user", "content": "住宿费上限"}], stream=False)
    body = wire.bodies[-1]

    assert body["stream"] is False
    assert STREAM_OPTIONS_FIELD not in body
    assert str(reply) == REWRITE_REPLY
    assert reply.transport == TRANSPORT_COMPAT


# ==================== 判据② · 末帧 usage 进得了那两枚列 ====================


def test_one_round_of_chat_lands_the_servers_own_counts_in_the_row(monkeypatch, tmp_path):
    """判据②：走一次真 ``/chat``，两枚列逐枚等于夹具自报 —— 🔴 改前这枚必须红。"""
    wire = _HonestOllamaCompat()
    response, store = _drive_route(monkeypatch, tmp_path, _handler(monkeypatch, wire))
    rows = _rows(store, "model_calls")

    assert len(rows) == 1, "行门是 R670 的货，本单不许让它复发"
    row = rows[0]
    assert (row["input_tokens"], row["output_tokens"]) == (
        COMPAT_USAGE["prompt_tokens"],
        COMPAT_USAGE["completion_tokens"],
    ), "两枚列等的就是服务端自报的那两枚数：一个都不许折算"
    assert row["input_tokens"] > 0 and row["output_tokens"] > 0
    assert row["cached_tokens"] == COMPAT_USAGE["prompt_tokens_details"]["cached_tokens"]
    assert row["metadata"]["usage_keys"] == EXPECTED_USAGE_KEYS
    assert row["status"] == "completed"
    #: 数从哪一格来的：请求里那一格 opt-in（判据① 的那一枚），不是本件替它编的。
    assert wire.bodies[-1].get(STREAM_OPTIONS_FIELD) == INCLUDE_USAGE
    assert response.text == "".join(ANSWER_PIECES), "只带计量的末片一个字都不许上屏"


# ==================== 判据⑤ · 三枚格子各有读数 ====================


def test_the_three_cells_are_named_by_three_readings_not_by_adjectives(monkeypatch):
    """取证三选一：opt-in 没带／末帧没解析／解析了没落库 —— 每格各自的现取读数。"""
    wire = _HonestOllamaCompat()
    handler = _handler(monkeypatch, wire)

    text, usage_frames = _collect(
        handler.chat([{"role": "user", "content": "残值率是多少"}], stream=True)
    )

    #: 格 A（请求要没要数）：只有这一格本单动了码。
    assert wire.bodies[-1].get(STREAM_OPTIONS_FIELD) == INCLUDE_USAGE
    #: 格 B（末帧解析）：真 SDK 交回的 usage 帧在不在流上 —— 在册循环 ``app/api/v1/chat.py::chat`` 读的就是它。
    assert len(usage_frames) == 1 and text == "".join(ANSWER_PIECES)
    #: 格 C（解析了落不落库）：summary 的两枚键名就是 ``app/trace/projections.py`` 搬进列的那两枚。
    counts = stream_usage_counts(usage_frames[-1])
    assert not _absent_is_recorded_as_null(counts)
    assert (counts["input_tokens"], counts["output_tokens"]) == (
        COMPAT_USAGE["prompt_tokens"],
        COMPAT_USAGE["completion_tokens"],
    )
    assert counts["cached_tokens"] == COMPAT_USAGE["prompt_tokens_details"]["cached_tokens"]


# ==================== 判据③ · 反证钉：没报就是 NULL，不是 0 ====================


def test_counter_evidence_a_server_that_never_reports_usage_leaves_the_counters_null(
    monkeypatch, tmp_path
):
    """服务端不认这个选项的那一形：行照样落，两枚列留 NULL，键名集合为空。"""
    wire = _HonestOllamaCompat(honor_opt_in=False)
    response, store = _drive_route(monkeypatch, tmp_path, _handler(monkeypatch, wire))
    rows = _rows(store, "model_calls")

    assert len(rows) == 1, "报不出数与没这一行是两件事，本单不许把前者写成后者"
    row = rows[0]
    assert _absent_is_recorded_as_null(row), "把「没报」折成 0 就是造数"
    assert row["input_tokens"] != 0 and row["output_tokens"] != 0
    assert row["cached_tokens"] is None
    assert row["metadata"]["usage_keys"] == []
    assert wire.bodies[-1].get(STREAM_OPTIONS_FIELD) == INCLUDE_USAGE, "请求要过了，是没报，不是没要"
    assert response.text == "".join(ANSWER_PIECES)


def test_counter_evidence_folding_the_absent_reading_into_zero_turns_the_null_pin_red():
    """同一枚谓词的刀：影子把「没报」偷折成 0 ⇒ 判据③ 那枚谓词当场为假；未变源码必须判真（正控）。"""
    shadow = load_shadow(SPANS, "spans_shadow_r690", patches=[(ABSENT_READING, FOLDED_INTO_ZERO)])

    folded = shadow.stream_usage_counts(None)
    assert folded == {"input_tokens": 0, "output_tokens": 0, "usage_keys": []}
    assert not _absent_is_recorded_as_null(folded), (
        "影子折成 0 而谓词仍为真 ⇒ 判据③ 那枚 NULL 钉是死牙，本件不算通过"
    )
    assert _absent_is_recorded_as_null(stream_usage_counts(None)), (
        "正控：未变的源码必须判真，否则这枚牙量的是它自己"
    )


# ==================== 判据⑥/⑦ · 观测不改正文，也不改并发纪律 ====================


def test_the_extra_tail_frame_does_not_hold_the_concurrency_slot(monkeypatch):
    """末片多一枚帧不许改变槽位归还：并发 1 时连着两发都要打得出来。"""
    wire = _HonestOllamaCompat()
    handler = _handler(monkeypatch, wire)

    first, _ = _collect(handler.chat([{"role": "user", "content": "第一问"}], stream=True))
    second, _ = _collect(handler.chat([{"role": "user", "content": "第二问"}], stream=True))

    assert first == second == "".join(ANSWER_PIECES)
    assert "rate_limited" not in second
    assert len(wire.bodies) == 2
