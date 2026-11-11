"""R203 判据①②④ 的生产者半边：图路径上的生成腿真走流式，交回来的还是同一发答案。

全程离线：真 ChatOpenAI + httpx.MockTransport，base_url 指向 127.0.0.1:9（那里不可能有
监听），所以「走没走流式」判的是**请求体字节**，而网线上一枚包都不发。

一枚假 provider 同时会两种答复：请求体里 stream 为真就回 SSE 帧，为假就回整段 JSON。
这个分流不是偷懒——它就是取证：改前线上发出去的 body 里躺着 "stream": false（本机实测，
见 test_a_leg_that_is_not_on_the_list_sends_todays_bytes），本单改的只有那一格的值与
stream_options 这一格新键，其余字段逐字节相同（test_the_wire_body_differs_only_in_...）。

判据对应（跟进单 §93 R203）：

- 判据①「哪一腿要改成流式」：test_every_listed_answer_leg_is_tapped 与
  test_a_leg_that_is_not_on_the_list_sends_todays_bytes 两枚对着钉——doc/data/chart 进，
  export、approval、supervisor、没注册 sink 的那一发，一个字节都不许多。
- 判据②「让那枚 sink 真响」：test_a_registered_answer_leg_streams_pieces_into_the_sink。
- 判据④「答案字节与今天逐位相同」：test_the_tapped_invoke_hands_back_the_untapped_message
  与 test_the_wire_body_differs_only_in_the_two_transport_fields。
- R149b 两条硬前置：片必须带调用身份（同一枚用例逐片断言 call_id / worker），计量不许回
  NULL（test_the_streamed_round_still_meters_its_tokens）。
"""

import json

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.agents import nodes
from app.agents.contracts import ModelTier, Principal
from app.common import model_budget
from app.common.model_budget import model_tier_budget

ANSWER = (
    "一线城市住宿费为每晚 500 元，凭发票按实际发生额报销；"
    "二三线城市住宿费为每晚 350 元，超标部分需要部门负责人签字确认之后才可以入账。"
)
USAGE = {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33}
#: 每一帧带 18 字：两帧就跨过 R31 的尺寸闸（20 字），四帧足够分出多片。
CHUNK_SIZE = 18
GREETING = [HumanMessage(content="住宿费标准")]
OFFLINE_REPLY = "本地模型暂不可用，已按离线口径回复。"


@pytest.fixture(autouse=True)
def _offline_ledger(tmp_path, monkeypatch):
    """一发额度 + trace 落 tmp：这一发的读数不进仓库，也不占真模型的槽。"""
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace import spans
    from app.trace.store import TraceStore

    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    store = TraceStore(
        tmp_path / "r203-spans.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / "r203-spans.json"),
    )
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    yield store
    model_budget.reset_default_budget()


# ==================== 假 provider：与本机兼容腿同形的 SSE / JSON 两头 ====================


def _chunk(delta, finish=None, usage=None):
    body = {
        "id": "cmpl-1",
        "model": "fake",
        "object": "chat.completion.chunk",
        "created": 1,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    if usage is not None:
        body["usage"] = usage
        body["choices"] = []
    return body


def _text_frames(text=ANSWER, usage=None, frames=None):
    count = frames if frames is not None else -(-len(text) // CHUNK_SIZE)
    built = [_chunk({"role": "assistant", "content": ""})]
    for index in range(count):
        piece = text[index * CHUNK_SIZE:(index + 1) * CHUNK_SIZE]
        built.append(_chunk({"content": piece}))
    if usage is not None:
        built.append(_chunk({}, usage=usage))
    return built


def _tool_call_frames():
    return [
        _chunk({"role": "assistant", "content": ""}),
        _chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "search_docs", "arguments": '{"query": "差旅"}'},
                    }
                ]
            }
        ),
        _chunk({}, finish="tool_calls"),
    ]


def _sse(frames):
    return "".join("data: " + json.dumps(f, ensure_ascii=False) + "\n\n" for f in frames)


def _provider_handler(bodies, frames, die_after=None):
    """按请求体分流：stream 为真回 SSE，为假回整段 JSON——两边都是真字节。

    die_after 不是「第 N 帧之后不发了」，而是「第 N 帧之后网线上的字节坏了」：那枚坏帧在
    SSE 解码器里抛错，正是 provider 死在半路的样子。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        bodies.append(body)
        if not body.get("stream"):
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={
                    "id": "cmpl-1",
                    "model": "fake",
                    "object": "chat.completion",
                    "created": 1,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": ANSWER},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": USAGE,
                },
            )
        payload = _sse(frames) if die_after is None else _sse(frames[:die_after]) + 'data: {"broken\n\n'
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(payload + "data: [DONE]\n\n").encode("utf-8"),
        )

    return handler


class _OfflineReply:
    """provider 死掉之后顶上的那句预制话术——与 _OfflineModel 同形，不再调模型。"""

    def invoke(self, messages, config=None, **kwargs):
        return AIMessage(content=OFFLINE_REPLY)

    def bind_tools(self, tools):
        return self


def _client(handler):
    transport = httpx.MockTransport(handler)
    return ChatOpenAI(
        base_url="http://127.0.0.1:9/v1",
        api_key="x",
        model="fake",
        temperature=0,
        max_retries=0,
        http_socket_options=(),
        http_client=httpx.Client(transport=transport),
        http_async_client=httpx.AsyncClient(transport=transport),
    )


def _resilient(handler):
    return nodes._ResilientModel(
        _client(handler),
        _OfflineReply(),
        provider="local-openai-compatible",
        model_name="fake",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.ANALYSIS),
    )


def _config(sink=None, worker="doc"):
    configurable = {
        "request_id": "request-r203",
        "trace_id": "trace-r203",
        "principal": Principal(user_id="u-r203", username="staff-r203", roles=["staff"]),
        "worker": worker,
    }
    if sink is not None:
        configurable[nodes.STREAM_PIECE_SINK_KEY] = sink
    return {"configurable": configurable}


# ==================== 判据② ：那枚 sink 真的响了，而且响的是合格的片 ====================


def test_a_registered_answer_leg_streams_pieces_into_the_sink():
    bodies, pieces = [], []
    model = _resilient(_provider_handler(bodies, _text_frames(ANSWER, usage=USAGE)))

    response = model.invoke(GREETING, config=_config(pieces.append))

    assert bodies[0].get("stream") is True, "生成腿没改走流式：本单一个字都没落地"
    assert bodies[0].get("stream_options") == {"include_usage": True}, (
        "R149b 第二条硬前置：兼容腿的流帧默认不带 usage，不主动开就是计量回 NULL"
    )
    assert len(pieces) >= 2, f"pieces={len(pieces)}：判据② 要的是多发，一片都不发就是没接上"
    assert "".join(piece.text for piece in pieces) == ANSWER, "G1 无损：拼回去逐字等于正文"
    assert {piece.call_id for piece in pieces} == {pieces[0].call_id}, "同一发要认得出是同一发"
    for piece in pieces:
        assert piece.call_id, "R149b 第一条硬前置：片必须带调用身份"
        assert piece.worker == "doc"
    assert type(response).__name__ == "AIMessage"
    assert response.content == ANSWER


def test_the_tapped_invoke_hands_back_the_untapped_message():
    """判据④ 的生产者半边：换传输道不许换一个答案。"""
    tapped_bodies, untapped_bodies = [], []
    frames = _text_frames(ANSWER, usage=USAGE)
    tapped = _resilient(_provider_handler(tapped_bodies, frames))
    untapped = _resilient(_provider_handler(untapped_bodies, frames))

    seen = []
    left = tapped.invoke(GREETING, config=_config(seen.append))
    right = untapped.invoke(GREETING, config=_config())

    assert type(left).__name__ == type(right).__name__ == "AIMessage"
    assert left.content == right.content == ANSWER
    assert left.tool_calls == right.tool_calls == []
    assert left.usage_metadata == right.usage_metadata, (
        "R38/R146 那把尺读的就是 usage_metadata：聚合把它丢了，D 行整排 NULL"
    )


def test_the_wire_body_differs_only_in_the_two_transport_fields():
    """同一发请求，除了 stream 的值与 stream_options 这一格之外不许多带一个字。

    预算仍按非流式那一档量（authorize(stream=False)），所以 max_tokens、时钟、思考开关、
    keep_alive 全都不许因为改走流式而移动——那些一动，答案就可能换一个。
    """
    streamed_bodies, plain_bodies = [], []
    frames = _text_frames(ANSWER, usage=USAGE)
    streamed = _resilient(_provider_handler(streamed_bodies, frames))
    plain = _resilient(_provider_handler(plain_bodies, frames))

    seen = []
    streamed.invoke(GREETING, config=_config(seen.append))
    plain.invoke(GREETING, config=_config())

    left, right = streamed_bodies[0], plain_bodies[0]
    assert left["stream"] is True and right["stream"] is False, (left, right)
    assert left["stream_options"] == {"include_usage": True}
    assert "stream_options" not in right
    without_transport = lambda payload: {k: v for k, v in payload.items() if k not in {"stream", "stream_options"}}
    assert without_transport(left) == without_transport(right)
    assert seen, "对照组没流起来，上面的比较就是空的"


def test_the_streamed_round_still_meters_its_tokens(_offline_ledger):
    """R149b 第二半：这一发的 tokens 必须照样进 model_calls。"""
    bodies, seen = [], []
    model = _resilient(_provider_handler(bodies, _text_frames(ANSWER, usage=USAGE)))

    model.invoke(GREETING, config=_config(seen.append))

    rows = _offline_ledger.persistence.list("model_calls")
    assert rows, "model_calls 一条都没记下"
    latest = rows[-1]
    assert latest["input_tokens"] == 11, latest
    assert latest["output_tokens"] == 22, latest


# ==================== 判据① ：准入名单 ====================


@pytest.mark.parametrize("worker", sorted(nodes.ANSWER_LEG_STREAM_WORKERS))
def test_every_listed_answer_leg_is_tapped(worker):
    bodies, seen = [], []
    model = _resilient(_provider_handler(bodies, _text_frames(ANSWER, usage=USAGE)))

    model.invoke(GREETING, config=_config(seen.append, worker=worker))

    assert bodies[0].get("stream") is True
    assert {piece.worker for piece in seen} == {worker}


@pytest.mark.parametrize(
    "worker,label",
    [
        ("", "supervisor 派发与 plan/respond 那一发"),
        ("approval", "approval 腿"),
        ("export", "export 腿"),
        ("synthesize", "非生成腿"),
    ],
)
def test_a_leg_that_is_not_on_the_list_sends_todays_bytes(worker, label):
    """不在名单上的腿：stream 仍然为假（今天就是假），出口一个字节都不发。"""
    bodies, seen = [], []
    model = _resilient(_provider_handler(bodies, _text_frames(ANSWER, usage=USAGE)))

    model.invoke(GREETING, config=_config(seen.append, worker=worker))

    assert bodies[0].get("stream") is False, f"{label} 被改走流式了：准入条件失效"
    assert "stream_options" not in bodies[0]
    assert seen == [], f"{label} 往出口里放了字"


def test_an_unregistered_round_sends_exactly_todays_request():
    """没注册 sink 的道（队列、审批续跑、离线直调）：与今天逐字节相同。"""
    bodies, seen = [], []
    model = _resilient(_provider_handler(bodies, _text_frames(ANSWER, usage=USAGE)))

    model.invoke(GREETING, config=_config())

    assert bodies[0].get("stream") is False
    assert seen == []


# ==================== 三道闸门：T1 工具轮、T3 死在半路 ====================


def test_a_tool_call_round_publishes_no_pieces():
    """T1：工具轮那一发不是终答，它的字一个都不许进累计串。"""
    bodies, seen = [], []
    model = _resilient(_provider_handler(bodies, _tool_call_frames()))

    response = model.invoke(GREETING, config=_config(seen.append))

    assert seen == [], [piece.text for piece in seen]
    assert bodies[0].get("stream") is True, "准入只看腿，放弃发生在闸门那一层"
    assert response.tool_calls, "假 provider 的这一发本来就该是工具调用"


def test_a_provider_that_dies_mid_stream_stops_publishing_at_once():
    """T3：provider 死在半路时，之后的片一片不许发。

    四帧 72 字之后坏帧：尺寸闸 20 字 + 滚动留一，所以只可能交出第一片（36 字）——第二片
    已经在手里，是坏帧让它永远到不了出口。半截字不许冒充答案的最后一块，与 R31 那枚
    "同流断掉不许发末片"的钉子同一条裁定。
    """
    bodies, seen = [], []
    frames = _text_frames(ANSWER, frames=4)
    model = _resilient(_provider_handler(bodies, frames, die_after=5))

    response = model.invoke(GREETING, config=_config(seen.append))

    assert [piece.text for piece in seen] == [ANSWER[:36]], [piece.text for piece in seen]
    assert response.content == OFFLINE_REPLY, "这一发没走离线回退，用例前提就变了"


def test_the_two_new_fields_cannot_change_the_shape_of_a_piece():
    """StreamPiece 长两格新字段：老字段一位不动，默认空串，不盖章时交出去的是同一枚对象。"""
    assert nodes.StreamPiece._fields == (
        "text",
        "start_at",
        "end_at",
        "source_fragments",
        "emitted_at",
        "call_id",
        "worker",
    )
    legacy = nodes.StreamPiece("正文", 1.0, 2.0, 3)
    assert tuple(legacy) == ("正文", 1.0, 2.0, 3, 0.0, "", "")

    seen = []
    nodes.publish_stream_pieces(_config(seen.append), [legacy])
    assert seen and seen[0] is legacy, "两格留空时不许重新造对象"

    stamped = []
    nodes.publish_stream_pieces(_config(stamped.append), [legacy], call_id="c1", worker="doc")
    assert stamped[0].call_id == "c1" and stamped[0].worker == "doc"
    assert stamped[0][:5] == legacy[:5], "盖章只加两格，老读数一位不动"
