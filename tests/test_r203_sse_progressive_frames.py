"""R203 判据② 的收端半边：一题的 text_frames 真的 >= 2，而且每枚帧都是终答的单调前缀。

与 R149 那枚文件的分工：R149 钉"片到了就多发"，生产者换成手搓的假片；本文件钉的是**整条链**
——生产者是**真的生成腿**（真 ChatOpenAI + httpx.MockTransport 走 _ResilientModel.invoke），
片由 nodes.py 里那枚 tap 现场产出，经 chat.py 本轮注册的 _piece_sink 进同一条 result_queue，
收端折帧发出去。假的只有 orchestrator 那一层（它要读文档、跑工具，离线跑不动）：腿、出口、
收端、SSE 帧字面全是真码。

🔴 读数只用一把尺：判据② 用的就是评分器自己那套解析（scripts/eval_transport_ask_v2.py 的
blank_observation / _count_text_frame / _fold_frames / _frame_readings / _frame_verdict）。
判据⑥ 说"不许改量具"——本文件不改它一个字，只是 import 进来现算，run6 判红的那四枚读数与
这里判绿的是同一枚。

判据对应：② 多发且每枚帧单调前缀；③ 收尾那枚帧不许消失、形状不许变；④ 答案字节与今天逐位
相同（test_the_answer_bytes_are_the_same_as_todays_untapped_round）；⑤ legacy 事件名一个不许
下线（test_legacy_event_names_survive_the_streamed_round）。
"""

import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.agents import nodes
from app.agents.contracts import ModelTier, Principal
from app.api.v1 import chat
from app.common import model_budget
from app.common.model_budget import model_tier_budget

_SPEC = importlib.util.spec_from_file_location(
    "r203_frame_ruler",
    Path(__file__).resolve().parents[1] / "scripts" / "eval_transport_ask_v2.py",
)
ruler = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ruler)

QUESTION = "差旅费报销的住宿费标准是多少？"
DOC_ANSWER = (
    "一线城市住宿费为每晚 500 元，凭发票按实际发生额报销；"
    "二三线城市住宿费为每晚 350 元，超标部分需要部门负责人签字确认之后才可以入账。"
)
CHART_ANSWER = (
    "把上面的标准画成柱状图：一线城市 500 元、二三线城市 350 元，两者相差一百五十元，"
    "差额部分按制度需要部门负责人签字才可入账，图表已生成在报告目录里可以直接下载查看。"
)
USAGE = {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33}
CHUNK_SIZE = 18


@pytest.fixture(autouse=True)
def _one_slot(monkeypatch):
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    yield
    model_budget.reset_default_budget()


# ==================== 真腿：MockTransport 上的兼容腿 SSE，与本机同形 ====================


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


def _answer_frames(text):
    frames = [_chunk({"role": "assistant", "content": ""})]
    starts = list(range(0, len(text), CHUNK_SIZE))
    for position, start in enumerate(starts):
        last = position == len(starts) - 1
        piece = text[start:start + CHUNK_SIZE]
        frames.append(_chunk({"content": piece}, finish="stop" if last else None))
    frames.append(_chunk({}, usage=USAGE))
    return frames


def _leg(text, worker_seen):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        worker_seen.append(bool(body.get("stream")))
        payload = "".join(
            "data: " + json.dumps(f, ensure_ascii=False) + "\n\n" for f in _answer_frames(text)
        )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(payload + "data: [DONE]\n\n").encode("utf-8"),
        )

    transport = httpx.MockTransport(handler)
    primary = ChatOpenAI(
        base_url="http://127.0.0.1:9/v1",
        api_key="x",
        model="fake",
        temperature=0,
        max_retries=0,
        http_socket_options=(),
        http_client=httpx.Client(transport=transport),
        http_async_client=httpx.AsyncClient(transport=transport),
    )
    return nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="fake",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.ANALYSIS),
    )


def _run_leg(sink, text, worker, streams, *, register=True):
    """这一发走的是生产同一条准入路径：本轮注册的 sink + 腿名，都在 configurable 里。

    register=False 复刻的是**今天**的生产形状：出口照样注册、腿照样跑，只是那一发没接上
    sink（R149 之后线上一字不发就是这个样子）——用它当对照组，比较才不是拿两段不同的代码比。
    """
    model = _leg(text, streams)
    configurable = {
        "worker": worker,
        "request_id": "request-r203-sse",
        "trace_id": "trace-r203-sse",
    }
    if register:
        configurable[nodes.STREAM_PIECE_SINK_KEY] = sink
    return model.invoke([HumanMessage(content=QUESTION)], config={"configurable": configurable})


# ==================== /ask 挂到真腿上（只有 orchestrator 那一层是假的） ====================


def _principal():
    return Principal(
        user_id="u-r203",
        username="staff-r203",
        roles=["staff"],
        permissions=["document:read"],
        department="finance",
        department_ids=[],
        clearance=2,
        clearance_label="L2",
        status="active",
    )


def _http_request():
    return type(
        "Request",
        (),
        {
            "state": type(
                "State", (), {"principal": _principal(), "username": "staff-r203"}
            )()
        },
    )()


def _harness(monkeypatch, tmp_path, legs, *, tapped=True):
    """legs 是 [(worker, answer)]：一条腿就是今天的单腿形状，两条腿测跨腿折帧。

    返回值：ask() 吐出整条 SSE 的字面；streams 记每一发请求体里 stream 的真假。
    """
    from app.common import cache
    from app.storage.sessions import SessionRegistry

    monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())

    seen = {}
    streams = []

    def fake_stream(*_args, **kwargs):
        sink = kwargs.get("stream_piece_sink")
        seen["sink"] = sink
        seen["kwargs"] = sorted(kwargs)
        results = {}
        for worker, answer in legs:
            if sink is not None:
                _run_leg(sink, answer, worker, streams, register=tapped)
            results[worker] = answer
            yield {
                "messages": [],
                "worker_results": dict(results),
                "final_answer": "\n\n".join(results.values()),
            }

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(
        chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)})
    )
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_args, **_kwargs: (True, 9))
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    def ask(message=QUESTION, session_id="sess-r203"):
        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message=message, session_id=session_id),
                http_request=_http_request(),
            )
        )

        async def consume():
            chunks = [chunk async for chunk in response.body_iterator]
            return "".join(
                chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in chunks
            )

        return asyncio.run(consume())

    return ask, seen, streams


# ==================== 解析：帧字面 → 评分器那把尺 ====================


def _as_lines(body):
    return iter([chunk.encode("utf-8") for chunk in body.splitlines(keepends=True)])


def _observation(body):
    out = ruler._blank_observation("sess-r203")
    for name, data, arrival in ruler.iter_events(_as_lines(body)):
        if name == "text":
            content = data.get("content")
            ruler._count_text_frame(out, "" if content is None else str(content))
            if content:
                if out["first_token_at"] is None:
                    out["first_token_at"] = arrival
                out["answer"] = str(content)
    return out


def _readings(body):
    out = _observation(body)
    ledger = ruler._fold_frames(ruler._new_frame_ledger(), out)
    return ruler._frame_readings(ledger, out["answer"])


def _text_payloads(body):
    return [
        json.loads(frame.split("data: ", 1)[1])
        for frame in body.split("\n\n")
        if frame.startswith("event: text")
    ]


def _event_names(body):
    return [
        frame.split("\n", 1)[0].removeprefix("event: ")
        for frame in body.split("\n\n")
        if frame
    ]


# ==================== 判据② ====================


def test_the_route_registers_a_sink_and_the_leg_actually_uses_it(monkeypatch, tmp_path):
    ask, seen, streams = _harness(monkeypatch, tmp_path, [("doc", DOC_ANSWER)])
    ask()

    assert callable(seen["sink"]), "SSE 出口没把片段出口传下去"
    assert "stream_piece_sink" in seen["kwargs"]
    assert streams == [True], "注册了 sink 的这一发没改走流式"


def test_a_streamed_round_clears_the_frame_verdict_of_criterion_two(monkeypatch, tmp_path):
    """判据②：同一把尺（评分器的 _frame_verdict）在这一题上判绿。"""
    ask, _seen, _streams = _harness(monkeypatch, tmp_path, [("doc", DOC_ANSWER)])
    body = ask()
    readings = _readings(body)

    assert readings["text_frames"] >= 2, readings
    assert readings["max_stream_frames"] >= 2, readings
    assert readings["prefix_breaks"] == 0, readings
    assert readings["extra_chars"] == 0, readings
    assert readings["missing_chars"] == 0, readings
    assert readings["last_frame_covers_answer"] is True, readings
    assert ruler._frame_verdict(readings) is True, readings


def test_every_frame_is_a_monotone_prefix_of_the_final_answer(monkeypatch, tmp_path):
    ask, _seen, _streams = _harness(monkeypatch, tmp_path, [("doc", DOC_ANSWER)])
    contents = [payload["content"] for payload in _text_payloads(ask())]

    assert len(contents) >= 2
    assert contents[-1] == DOC_ANSWER, "收尾那枚帧（判据③）不许消失也不许换字"
    for previous, current in zip(contents, contents[1:]):
        assert current.startswith(previous), (previous[-16:], current[-16:])
        assert len(current) >= len(previous)
    increments = [contents[0]] + [c[len(p):] for p, c in zip(contents, contents[1:])]
    assert "".join(increments) == DOC_ANSWER, "无损：帧间差拼回去逐字等于终答"


def test_a_multi_leg_round_keeps_every_frame_a_prefix_of_the_joined_answer(monkeypatch, tmp_path):
    """两条腿：第二腿的第一枚帧必须带着第一腿的全文当底座，否则跨腿那一帧就不是前缀。"""
    ask, _seen, _streams = _harness(
        monkeypatch, tmp_path, [("doc", DOC_ANSWER), ("chart", CHART_ANSWER)]
    )
    body = ask()
    final = DOC_ANSWER + "\n\n" + CHART_ANSWER
    contents = [payload["content"] for payload in _text_payloads(body)]

    assert len(contents) >= 4, contents
    assert contents[-1] == final
    for previous, current in zip(contents, contents[1:]):
        assert current.startswith(previous), (previous[-20:], current[-20:])
    assert _readings(body)["prefix_breaks"] == 0
    assert _readings(body)["extra_chars"] == 0


# ==================== 判据④：答案字节与今天逐位相同 ====================


def test_the_answer_bytes_are_the_same_as_todays_untapped_round(monkeypatch, tmp_path):
    """同一道题：接上流式之前与之后，落到会话里、发在收尾帧里的是同一份字节。

    "今天的形状"用同一条 harness 复刻，只把腿那一发摘掉（sink 仍然注册，正是 R149 之后
    生产上的样子：出口在、腿不响）。两轮回来的收尾帧必须逐字节相同。
    """
    today, _seen_today, streams_today = _harness(
        monkeypatch, tmp_path, [("doc", DOC_ANSWER)], tapped=False
    )
    body_today = today()

    streamed, _seen_streamed, streams_streamed = _harness(
        monkeypatch, tmp_path, [("doc", DOC_ANSWER)]
    )
    body_streamed = streamed()
    assert streams_today == [False] and streams_streamed == [True]

    today_contents = [payload["content"] for payload in _text_payloads(body_today)]
    streamed_contents = [payload["content"] for payload in _text_payloads(body_streamed)]
    assert len(today_contents) == 1, "今天的形状就是一枚整段帧，这枚前提塌了用例就没尺了"
    assert today_contents[0] == streamed_contents[-1] == DOC_ANSWER
    assert _readings(body_streamed)["answer_sha"] == _readings(body_today)["answer_sha"]


def test_the_streamed_frames_are_cumulative_never_deltas(monkeypatch, tmp_path):
    """判据② 的字面口径：每一枚帧都是"截至这一片的累计全文"，不是增量。"""
    ask, _seen, _streams = _harness(monkeypatch, tmp_path, [("doc", DOC_ANSWER)])
    contents = [payload["content"] for payload in _text_payloads(ask())]

    assert all(len(c) >= 20 for c in contents), contents
    assert DOC_ANSWER.startswith(contents[0]), "首帧就得是终答的开头"
    for index, current in enumerate(contents[1:], start=1):
        assert current.startswith(contents[index - 1])


# ==================== 判据⑤：legacy 事件名一个不许下线 ====================


def test_legacy_event_names_survive_the_streamed_round(monkeypatch, tmp_path):
    today, _s1, _w1 = _harness(monkeypatch, tmp_path, [("doc", DOC_ANSWER)], tapped=False)
    names_today = _event_names(today())

    streamed, _s2, _w2 = _harness(monkeypatch, tmp_path, [("doc", DOC_ANSWER)])
    names_streamed = _event_names(streamed())

    assert set(names_today) <= set(names_streamed), set(names_today) - set(names_streamed)
    # 摘掉多出来的 text 帧，两条流的事件名序列必须逐位相同：本单只许多发 text，不许换别的。
    extra = len(names_streamed) - len(names_today)
    assert extra >= 1
    stripped = list(names_streamed)
    removed = 0
    for index in range(len(stripped) - 1, -1, -1):
        if stripped[index] == "text" and removed < extra:
            del stripped[index]
            removed += 1
    assert stripped == names_today, (names_today, stripped)



@pytest.mark.parametrize("chunk_size", [18, 6, 3], ids=["chunk18", "chunk6", "chunk3"])
@pytest.mark.parametrize(
    "answer", [DOC_ANSWER, CHART_ANSWER], ids=["70å­ç­æ¡", "86å­ç­æ¡"]
)
def test_the_measured_piece_and_frame_counts_are_pinned(
    monkeypatch, tmp_path, answer, chunk_size
):
    """判据① 的读数本体：接线之前 pieces 恒 0，接线之后这一题到底出几片、几帧。

    接线之前 run6 的帧账是逐题 pieces=0 / text_frames=1（整段一次性到达）；接线之后同一条链
    上的离线读数（本用例的 print，chunk＝provider 每次吐多少字）：

      chars=70  chunk=18 → pieces=2 text_frames=3   sizes=[36, 34]
      chars=70  chunk=6  → pieces=3 text_frames=4   sizes=[24, 24, 22]
      chars=70  chunk=3  → pieces=4 text_frames=5   sizes=[21, 21, 21, 7]
      chars=86  chunk=18 → pieces=3 text_frames=4   sizes=[36, 36, 14]
      chars=86  chunk=6  → pieces=4 text_frames=5   sizes=[24, 24, 24, 14]
      chars=86  chunk=3  → pieces=5 text_frames=6   sizes=[21, 21, 21, 21, 2]

    所以"变成几"没有单一答案，它由三把尺共同定：答案字数、provider 每次吐多少字、R31 那枚
    尺寸闸 ``STREAM_PIECE_MIN_CHARS=20``（再加 tap 的滚动留一，末片由 close 兜底）。本用例
    钉的是这条曲线的形状与下限（pieces ≥ 2 ⇒ text_frames ≥ 3），不是钉某一个数：改了尺寸闸
    或分帧几何，这里先红，交回单上那句话就得跟着重算。真机（本机 Ollama）读数**没做到**，
    理由与复测口令见交回单，不在这里外推。
    """
    pieces: list = []
    streams: list = []
    # setitem(globals()) 而不是 setattr(模块名, ...)：本文件会以两个模块名各被加载一次
    # （pytest 收一份、test_r203_no_double_delivery 从 tests. 路径 import 另一份），
    # 只有 globals() 这一份是正在跑的这枚用例真正看得见的那本。
    monkeypatch.setitem(globals(), "CHUNK_SIZE", chunk_size)
    _run_leg(pieces.append, answer, "doc", streams)
    assert streams == [True], streams
    assert "".join(piece.text for piece in pieces) == answer

    ask, _seen, _streams = _harness(monkeypatch, tmp_path, [("doc", answer)])
    readings = _readings(ask())

    # 一帧一片，收尾那帧另算：text_frames 恒等于 pieces + 1
    assert readings["text_frames"] == len(pieces) + 1, (len(pieces), readings)
    assert readings["max_stream_frames"] == readings["text_frames"], readings
    assert readings["prefix_breaks"] == 0 and readings["extra_chars"] == 0, readings
    assert len(pieces) >= 2, "判据② 的下限：一题至少两片才谈得上逐字"
    sizes = [len(piece.text) for piece in pieces]
    print(
        "R203-MEASURE chars=%d chunk=%d pieces=%d text_frames=%d sizes=%s"
        % (len(answer), chunk_size, len(pieces), readings["text_frames"], sizes),
    )

# ==================== 收端规则 1：没落定的第二发必须关门 ====================


def _piece(text, call_id, worker):
    return nodes.StreamPiece(
        text=text,
        start_at=0.0,
        end_at=1.0,
        source_fragments=1,
        call_id=call_id,
        worker=worker,
    )


def test_a_second_call_that_has_not_settled_closes_the_frame_stream():
    """换发的前提是前一发那条腿**已经落进 worker_results**；没落定就关门，一个字也不再发。

    这枚守卫是判据④ 里 ``prefix_breaks`` 恒 0 的最后一道：两发同时在写的时候，谁也说不清
    终答会以哪一段收尾，硬把第二发的字接在累计串后面就会长出一枚不是前缀的帧。本单的裁定
    是宁少不错——这一题退回今天"一次性到达"的形状，而不是赌一把。
    """
    stream = chat._AnswerPieceStream()

    assert stream.frame_for(_piece(DOC_ANSWER[:21], "c1", "doc"), {}) == DOC_ANSWER[:21]
    assert stream.frame_for(_piece(DOC_ANSWER[21:], "c1", "doc"), {}) == DOC_ANSWER
    # doc 那一发还没落进 worker_results 就冒出第二发：判定为两发同时在写 ⇒ 关门
    assert stream.frame_for(_piece("第二段", "c2", "data"), {}) is None
    assert stream.closed is True and stream.dropped == 1
    # 关门之后即便前一发落定了也不许反悔重开：坏过一次就整轮静音
    assert stream.frame_for(_piece("再多一字", "c2", "data"), {"doc": DOC_ANSWER}) is None
    assert stream.last_frame == DOC_ANSWER


def test_a_settled_leg_handing_over_to_the_next_keeps_every_frame_a_prefix():
    """healthy path 的另一半：前一发落定之后换发，新帧必须带着已落定的底座继续长。

    与上一枚是同一处守卫的两条出路，摘掉守卫这两枚里必有一枚红；只看上一枚则只能证明
    "会关门"，证明不了"该换发的时候没被误关"。
    """
    stream = chat._AnswerPieceStream()
    settled = {"doc": DOC_ANSWER}
    final = DOC_ANSWER + "\n\n" + CHART_ANSWER

    first = stream.frame_for(_piece(CHART_ANSWER[:21], "c2", "chart"), settled)
    second = stream.frame_for(_piece(CHART_ANSWER[21:], "c2", "chart"), settled)

    # 帧正文两侧都 strip 过（规则 2），期望值取同一口径：以半角空格结尾的那一截会被削掉
    assert first == DOC_ANSWER + "\n\n" + CHART_ANSWER[:21].strip()
    assert second == final
    assert final.startswith(first), "strip 之后仍必须是终答的前缀，否则 prefix_breaks 就起来了"
    assert stream.closed is False and stream.dropped == 0


def test_the_two_new_fields_never_ride_the_wire(monkeypatch, tmp_path):
    """待证① 的正面回答：盖过 ``call_id``/``worker`` 的片，落到 SSE 上仍是两键帧。

    帧形状与 ``StreamPiece`` 长几格新字段无关——收端只取 ``piece.text`` 折帧，那两格是
    收端内部用来认腿认发的，从不外抄。R149 那枚 ``test_live_frames_never_carry_a_cache_mark``
    钉的是手搓的无身份片，本枚钉的是真盖了身份的一片，两枚合起来才叫"新字段改不了帧形状"。
    """
    ask, _seen, _streams = _harness(monkeypatch, tmp_path, [("doc", DOC_ANSWER)])
    payloads = _text_payloads(ask())
    assert len(payloads) >= 3, "帧数不够，等于没测到片道"
    assert {tuple(sorted(payload)) for payload in payloads} == {("content", "type")}

    wire = json.dumps(payloads, ensure_ascii=False)
    assert "call_id" not in wire and "worker" not in wire, "身份字段漏进了线上载荷"

