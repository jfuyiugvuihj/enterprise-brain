# -*- coding: utf-8 -*-
"""R459 判据①③④ 的生产者半边：主 Agent 直答那一发接上了既有片段出口。

病灶（``docs/perf/a2-single-frame-attribution-2026-09-28.md`` §2.1 与 §10 锚点 1）：员工问一枚
不需要派活的问题，supervisor 自己回答，而那一发 ``main_model.invoke([sys_msg, current_user_msg])``
**不带 config** ⇒ 本轮注册的 ``stream_piece_sink`` 摘不到 ⇒ 一个片都不进出口 ⇒ 收端整轮只有一枚
``event: text``（写在收尾那一发），屏幕上是「转圈转到最后一次性砸出全文」。

本文件只量生产者这一侧，全程离线：真 ``ChatOpenAI`` + ``httpx.MockTransport``（base_url 指向
127.0.0.1:9，那里不可能有监听，网线上一枚包都不发），SSE 帧由一枚**带真实到达间隔**的生成器
逐枚交回，所以「片是在正文写完之前出去的」这句是可量的，不是注释。

判据对应（跟进单 §130 二 → 本单交回单）：

- 判据① 接上出口：``test_the_direct_answer_round_publishes_pieces_into_the_registered_sink``
  与 ``test_the_answer_bytes_and_message_shape_survive_the_coupling``（末帧覆盖全文的生产者前提＝
  片拼回去逐字等于终答；答案字节与不换传输道时逐位相同）。
- 判据③ 不放宽在册口径：``test_the_wire_body_differs_only_in_the_two_transport_fields``
  （R203 同一条裁定：除 ``stream``／``stream_options`` 两格外不许多带一个字）与
  ``test_the_coupling_does_not_widen_the_admission_list``（不借 worker 名进归因名单）。
- 判据④ 首片读数：``test_the_first_piece_leaves_the_model_before_the_answer_is_finished``。
- ①那三格前置各有一枚承重钉：``test_each_prerequisite_is_load_bearing``（影子副本只改内存、
  不动盘；仓里 ``tests/test_r253_no_test_rewrites_a_tracked_file.py`` 治的就是原地改被跟踪文件）。
- 反证钉：``test_a_bypass_of_the_r31_merger_breaks_the_piece_caliber``（绕过合并闸 ⇒ 同一套断言红）。

``(None, None)`` 那一路退回**单参数** invoke 这一格由
``test_a_round_without_a_sink_falls_back_to_todays_single_argument_call`` 钉着（判据要的「不许只靠注释」）。
"""
import hashlib
import inspect
import json
import shutil
import tempfile
import time
from pathlib import Path

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.agents import nodes, orchestrator
from app.agents.contracts import ModelTier, Principal
from app.common import model_budget
from app.common.model_budget import model_tier_budget

ANSWER = (
    "根据历史对话记录，这个问题已经为您解答过：\n\n"
    "## 回款确认时点\n\n"
    "回款以到账日确认，验收单日期不作为确认时点。"
)
USAGE = {"prompt_tokens": 11, "completion_tokens": 22, "total_tokens": 33}
#: 每一帧 18 字：跨过 R31 尺寸闸（20 字）就成一片，所以多帧是量出来的，不是凑的。
CHUNK_SIZE = 18
GAP_SECONDS = 0.03
QUESTION = "回款什么时候算确认了？"
#: 在册的离线话术之一（``app/agents/nodes.py`` 的 ``OFFLINE_REPLY_TEXTS``）。
OFFLINE_SENTENCE = "离线模式已启用"

GUARD_SINK = "    if not callable(sink):\n        return None, None\n"
GUARD_LEDGER = "    if state.get(\"worker_results\"):\n        return None, None\n"
GUARD_DISPATCH = (
    "    if _prior_dispatch_decision(turn_messages) is not None:\n"
    "        return None, None\n"
)
#: 摘接驳那一刀的字面：把「该不该接」整格短路成「永不接」。收端那半边拿它做负对照，
#: 钉的是「接驳一摘，在册量具当场读回 run9 的单片形状」。
TAP_HEAD = '    configurable = (config or {}).get("configurable") or {}\n'
UNPLUG = '    return None, None  # r459 knife：摘掉接驳，这一腿退回一次性成文\n'


@pytest.fixture(autouse=True)
def _offline_ledger(tmp_path, monkeypatch):
    """一发额度 + trace 落 tmp：这一发的读数不进仓库，也不占真模型的槽。"""
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace import spans
    from app.trace.store import TraceStore

    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    store = TraceStore(
        tmp_path / "r459-spans.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / "r459-spans.json"),
    )
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    yield store
    model_budget.reset_default_budget()


# ==================== 假 provider：SSE 帧逐枚到达，网线一枚不发 ====================


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


def _text_frames(text=ANSWER, usage=None, gap_frames=None):
    count = -(-len(text) // CHUNK_SIZE) if gap_frames is None else gap_frames
    built = [_chunk({"role": "assistant", "content": ""})]
    for index in range(count):
        built.append(_chunk({"content": text[index * CHUNK_SIZE:(index + 1) * CHUNK_SIZE]}))
    if usage is not None:
        built.append(_chunk({}, usage=usage))
    return built


def _chatter_then_tool_call_frames(chatter=ANSWER):
    built = [_chunk({"role": "assistant", "content": ""})]
    for index in range(-(-len(chatter) // CHUNK_SIZE)):
        built.append(_chunk({"content": chatter[index * CHUNK_SIZE:(index + 1) * CHUNK_SIZE]}))
    built.append(
        _chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "dispatch", "arguments": '{"workers": ["doc"]}'},
                    }
                ]
            }
        )
    )
    built.append(_chunk({}, finish="tool_calls"))
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
                        "function": {"name": "dispatch", "arguments": '{"workers": ["doc"]}'},
                    }
                ]
            }
        ),
        _chunk({}, finish="tool_calls"),
    ]


def _json_reply(text=ANSWER):
    return {
        "id": "cmpl-1",
        "model": "fake",
        "object": "chat.completion",
        "created": 1,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
        "usage": USAGE,
    }


def _provider_handler(bodies, frames, die_after=None):
    """stream 为真就逐枚吐 SSE（每枚之间真睡一次），为假就回整段 JSON。

    ``die_after`` 是「第 N 枚之后网线坏了」：那枚坏帧在 SSE 解码器里抛错，正是 provider 死在
    半路的样子，与 R203 那枚同形。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        bodies.append(body)
        if not body.get("stream"):
            return httpx.Response(
                200, headers={"content-type": "application/json"}, json=_json_reply()
            )

        def streamed():
            payload = frames if die_after is None else frames[:die_after]
            for index, frame in enumerate(payload):
                if index:
                    time.sleep(GAP_SECONDS)
                yield ("data: " + json.dumps(frame, ensure_ascii=False) + "\n\n").encode("utf-8")
            if die_after is not None:
                yield b'data: {"broken\n\n'
            else:
                yield b"data: [DONE]\n\n"

        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=streamed(),
        )

    return handler


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


class _OfflineReply:
    """provider 死掉之后顶上的那一发——与 ``_OfflineModel.bind_tools([dispatch])`` 同形。

    生产上 supervisor 的 fallback 带着 ``dispatch``，交回的是**空正文 + 一枚 dispatch**，不是
    那句预制的话：``is_offline_reply_text("")`` 对它无效，所以 T3 的结清判据两半都得查。
    """

    def __init__(self, shape="dispatch"):
        self.shape = shape

    def invoke(self, messages, config=None, **kwargs):
        if self.shape == "sentence":
            return AIMessage(content=OFFLINE_SENTENCE)
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "dispatch",
                    "args": {"workers": ["doc"]},
                    "id": "offline-dispatch",
                    "type": "tool_call",
                }
            ],
        )

    def bind_tools(self, tools):
        return self


class _SpyModel:
    """记录 supervisor 那一发**到底怎么被调用**的替身：位置参数与关键字参数分开存。

    ①那一路「不接就退回单参数 invoke」必须能在字节之外还被看见一次：这一枚存的就是调用形状，
    ``kwargs == {}`` 才是今天那一发。
    """

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    def invoke(self, messages, **kwargs):
        self.calls.append((list(messages), dict(kwargs)))
        return self.inner.invoke(messages, **kwargs)

    @property
    def roundtrips(self):
        return len(self.calls)

    def bind_tools(self, tools):
        return self


# ==================== 一轮直答：真 main_agent_node + 真 tap + 假 provider ====================


def _round_config(sink=None, **extra):
    configurable = {
        "thread_id": "session-r459",
        "request_id": "request-r459",
        "trace_id": "trace-r459",
        "principal": Principal(user_id="u-r459", username="staff-r459", roles=["staff"]),
    }
    configurable.update(extra)
    if sink is not None:
        configurable[nodes.STREAM_PIECE_SINK_KEY] = sink
    return {"configurable": configurable}


def _direct_answer_state(**extra):
    """员工问一枚不需要派活的问题：本轮消息里只有那一条 HumanMessage。"""
    state = {"messages": [HumanMessage(content=QUESTION)], "plan": [], "memory": {}}
    state.update(extra)
    return state


def _dispatched_state():
    """本轮已经做出 dispatch 决策的那一发（guard② 的形状：账本还没落定也得挡住）。"""
    dispatch = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "dispatch",
                "args": {"workers": ["data"]},
                "id": "supervisor-dispatch",
                "type": "tool_call",
            }
        ],
    )
    return {
        "messages": [
            HumanMessage(content="各部门回款合计多少？"),
            dispatch,
            ToolMessage(content="已派发 1 个子Agent", tool_call_id="supervisor-dispatch", name="dispatch"),
            AIMessage(content=f"【data Agent 返回】\n{ANSWER}"),
        ],
        "plan": [],
        "memory": {},
    }


def _run_round(monkeypatch, frames, sink=None, state=None, config=None, die_after=None,
               fallback="dispatch"):
    """跑一发 supervisor：交回（假 provider 记下的请求体，出口收到的片与到达时刻，节点返回值）。"""
    bodies = []
    arrivals = []

    def recording_sink(piece):
        arrivals.append((time.monotonic(), piece))
        if sink is not None:
            sink(piece)

    handler = _provider_handler(bodies, frames, die_after=die_after)
    model = _SpyModel(
        nodes._ResilientModel(
            _client(handler),
            _OfflineReply(fallback),
            provider="local-openai-compatible",
            model_name="fake",
            capacity_wait_seconds=0,
            budget=model_tier_budget(ModelTier.ANALYSIS),
        )
    )
    monkeypatch.setattr(orchestrator, "main_model", model)
    started = time.monotonic()
    update = orchestrator.main_agent_node(
        state if state is not None else _direct_answer_state(),
        config if config is not None else _round_config(recording_sink),
    )
    finished = time.monotonic()
    return {
        "bodies": bodies,
        "arrivals": arrivals,
        "pieces": [piece for _at, piece in arrivals],
        "returned_at": finished,
        "started_at": started,
        "model": model,
        "update": update,
    }

# ==================== 影子根：摘守卫只改内存，不动盘 ====================

DISABLE = "    if _r459_disabled:\n        return None, None\n"
TAIL_GUARD_BODY = (
    '    return not getattr(resp, "tool_calls", None) and not is_offline_reply_text(\n'
    '        getattr(resp, "content", "")\n'
    '    )\n'
)


class _RawTokenTap(nodes.BaseCallbackHandler):
    """刀专用：每收到一枚 token 增量就直交出口，**绕过 R31 的合并闸**。

    这不是候选实现，是反证钉的靶子——用来证明「片必须过那两把尺」这句是本单真正咬住的东西。
    """

    def tap_output_iter(self, run_id, output):
        return output

    def tap_output_aiter(self, run_id, output):
        return output

    def __init__(self, config, sink, *, worker, call_id):
        self.config = config
        self.sink = sink
        self.worker = worker
        self.call_id = call_id

    def on_llm_new_token(self, token, **kwargs):
        message = getattr(kwargs.get("chunk"), "message", None)
        text = nodes.visible_chunk_text(message) if message is not None else ""
        if not text:
            return
        now = time.monotonic()
        piece = nodes.StreamPiece(
            text=text, start_at=now, end_at=now, source_fragments=1, emitted_at=now
        )
        nodes.publish_stream_pieces(self.config, [piece], call_id=self.call_id, worker=self.worker)

    def close(self):
        return 0

    def abandon(self, reason):
        return None


_SHADOW_DIRS: list = []


@pytest.fixture(autouse=True)
def _sweep_shadow_dirs():
    """影子副本用完整回就扫掉：临时目录不留在盘上当二手垃圾。"""
    yield
    while _SHADOW_DIRS:
        shutil.rmtree(_SHADOW_DIRS.pop(), ignore_errors=True)


def _shadow(monkeypatch, name, edits):
    """按字面摘掉真源码里的某一格，改出的源码落进**临时影子副本**，再从那里 exec 回挂。

    🔴 仓里一字节都不改：摘刀之前先记被跟踪那枚文件的 sha256，回挂之后再记一次，两次数不
    相等就当场红（事故 #71 那一形——为了看钉红不红而原地改被跟踪文件——由
    ``tests/test_r253_no_test_rewrites_a_tracked_file.py`` 在全仓静态扫，本函数自己再证一遍）。
    漂移造在 ``tempfile.mkdtemp()`` 的影子副本里：exec 的编译源就是那枚临时文件，所以
    ``inspect.getsource`` 之后取到的是影子自己，不会回头读仓里那份。
    每枚 needle 必须**恰好命中一次**，命中不上就是刀磨钝了：当场红，不许静默走空。
    """
    tracked = Path(inspect.getsourcefile(orchestrator)).resolve()
    digest_before = hashlib.sha256(tracked.read_bytes()).hexdigest()

    source = inspect.getsource(getattr(orchestrator, name))
    for needle, replacement in edits:
        assert source.count(needle) == 1, (name, needle[:40], source.count(needle))
        source = source.replace(needle, replacement)

    shadow_dir = Path(tempfile.mkdtemp(prefix="r459-shadow-"))
    _SHADOW_DIRS.append(shadow_dir)
    assert shadow_dir not in tracked.parents, "影子副本落在仓里：这一刀不许开"
    shadow_file = shadow_dir / "orchestrator_answer_leg_tap.py"
    shadow_file.write_text(source, encoding="utf-8")

    namespace = dict(vars(orchestrator))
    namespace["_r459_disabled"] = False
    namespace["_RawTokenTap"] = _RawTokenTap
    exec(compile(shadow_file.read_text(encoding="utf-8"), str(shadow_file), "exec"), namespace)
    shadow = namespace[name]
    assert shadow is not getattr(orchestrator, name), f"影子与原件同一枚对象：{name}"
    monkeypatch.setattr(orchestrator, name, shadow)

    assert hashlib.sha256(tracked.read_bytes()).hexdigest() == digest_before, (
        RED + " 摘刀在被跟踪文件上留下了写口：反证钉不许动盘"
    )
    return shadow


def _check_piece_caliber(pieces, floor=nodes.STREAM_PIECE_MIN_CHARS):
    """R31 那两把尺在本单这一腿上仍然说了算（判据③：不放宽，只新增）。"""
    assert len(pieces) >= 2, f"片数={len(pieces)}：出口没多片就是没接上"
    for piece in pieces[:-1]:
        assert len(piece.text) >= floor, (
            f"尺寸闸被绕过了：一片只有 {len(piece.text)} 字（口径 {floor} 字）"
            f"——{piece.text!r}"
        )
    assert "".join(piece.text for piece in pieces) == ANSWER, "G1 无损：拼回去逐字等于终答"
    for previous, current in zip(pieces, pieces[1:]):
        # 在册口径是「不相交」（G2），不是「严格大于」：本机 monotonic 有毫秒级量化，
        # 把尺子拧得比在册的那一枚更紧，量到的会是时钟而不是产码。
        assert previous.end_at <= current.start_at, "G2 不重叠被破坏：两片共用了字"


# ==================== 判据①：直答那一发真的把片交进了出口 ====================


def test_the_direct_answer_round_publishes_pieces_into_the_registered_sink(monkeypatch):
    """接上出口之后：多片、片拼回去逐字等于终答、身份两格齐、腿名不借 worker 的名。"""
    round_ = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE))

    _check_piece_caliber(round_["pieces"])
    assert {piece.worker for piece in round_["pieces"]} == {orchestrator.SUPERVISOR_ANSWER_LEG}
    assert round_["pieces"][0].call_id, "R149b 第一条硬前置：片必须带调用身份"
    assert {piece.call_id for piece in round_["pieces"]} == {round_["pieces"][0].call_id}
    assert round_["update"].keys() == {"messages"}, "节点返回值多了一格：终答可能被交回两遍"
    assert round_["update"]["messages"][0].content == ANSWER


def test_the_answer_bytes_and_message_shape_survive_the_coupling(monkeypatch):
    """判据① 末帧覆盖全文的生产者前提：换传输道不许换一个答案，也不许丢计量。"""
    coupled = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE))
    plain = _run_round(
        monkeypatch, _text_frames(ANSWER, usage=USAGE), config=_round_config()
    )

    left = coupled["update"]["messages"][0]
    right = plain["update"]["messages"][0]
    assert type(left).__name__ == type(right).__name__ == "AIMessage"
    assert left.content == right.content == ANSWER
    assert left.tool_calls == right.tool_calls == []
    assert left.usage_metadata == right.usage_metadata, (
        "R38/R146 那把尺读的就是 usage_metadata：流式把计量洗成 NULL 就不许收工"
    )


def test_the_wire_body_differs_only_in_the_two_transport_fields(monkeypatch):
    """R203 同一条裁定落到这一腿上：除了 stream 与 stream_options，body 一个字都不许多。"""
    coupled = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE))
    plain = _run_round(
        monkeypatch, _text_frames(ANSWER, usage=USAGE), config=_round_config()
    )

    left, right = coupled["bodies"][0], plain["bodies"][0]
    assert left["stream"] is True and right["stream"] is False, (left["stream"], right["stream"])
    assert left["stream_options"] == {"include_usage": True}
    assert "stream_options" not in right
    without = lambda payload: {
        key: value for key, value in payload.items() if key not in {"stream", "stream_options"}
    }
    assert without(left) == without(right)
    assert plain["pieces"] == [] and plain["arrivals"] == []


def test_a_round_without_a_sink_falls_back_to_todays_single_argument_call(monkeypatch):
    """①的第一格：没注册出口的道（审批续跑、离线直调，以及入队那一支本身）退回**单参数** invoke。

    这条不靠注释：`_SpyModel` 存的就是调用形状，`kwargs == {}` 才是今天那一发；请求体里
    ``stream`` 仍为假、``stream_options`` 一个都不许多带。

    09-30 改口（R548 `f312eeb`）：`deploy/queue_worker.py` 今天已在 worker 进程注册一枚
    收端，那是报告档后台那一道，不在本枚钉射程内；本钉量的仍是 `/ask` 道里摘不到出口的那一发。
    """
    plain = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE), config=_round_config())

    messages, kwargs = plain["model"].calls[0]
    assert kwargs == {}, f"摘不到出口的那一发多带了关键字参数：{sorted(kwargs)}"
    assert len(messages) == 2, "supervisor 的 prompt 仍是 [sys, user] 那一发（R33 的既成事实）"
    assert plain["bodies"][0]["stream"] is False
    assert "stream_options" not in plain["bodies"][0]
    assert plain["pieces"] == []


def test_the_coupling_adds_no_second_copy_of_the_answer_to_the_state(monkeypatch):
    """正文不许重复出两遍（生产者半边）：节点只追加模型那一发本身，不另写终答。"""
    round_ = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE))

    assert list(round_["update"]) == ["messages"], list(round_["update"])
    assert len(round_["update"]["messages"]) == 1
    assert "final_answer" not in round_["update"], "编排层多写一份终答＝收端可能读两遍"

# ==================== 判据④：首片的读数（量的层＝本轮出口的收口处） ====================


def test_the_first_piece_leaves_the_model_before_the_answer_is_finished(monkeypatch):
    """「憋到最后一把砸出」在这一格上装不出来：首片交出去时，正文还没写完。

    量的层说清楚：``arrivals`` 是本单在 ``_run_round`` 里包的那枚**记录型 sink** 记下的
    ``time.monotonic()``——它就是 ``chat._piece_sink`` 收到这片的那一刻（本文件不开 SSE，
    收端那半边的读数在 ``tests/test_r459_ask_direct_answer_frames.py``）。三格合起来才是
    「一边生成一边出字」：片数 ≥2、首片与次片之间隔得出时间、末片早于 invoke 返回。
    """
    round_ = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE))
    arrivals = [at for at, _piece in round_["arrivals"]]

    assert len(arrivals) >= 2, f"出口只收到 {len(arrivals)} 片：单片形状没被治好"
    assert arrivals[1] - arrivals[0] > 0, "首片与次片之间隔不出时间：这不是逐字，是一把砸"
    assert round_["returned_at"] - arrivals[0] >= GAP_SECONDS, (
        "首片距整发结束隔不出一个到达间隔：一把砸到收尾再发，读起来就是这个样子"
    )
    assert arrivals[-1] <= round_["returned_at"], "有片是在 invoke 返回之后才交出去的"


# ==================== 判据③：三格前置各是一枚承重墙 ====================


def _direct_without_sink(monkeypatch):
    """队列道／审批续跑那一形：本轮根本没注册片段出口。"""
    return _run_round(
        monkeypatch, _text_frames(ANSWER, usage=USAGE), config=_round_config()
    )


def _ledger_only_state():
    """reflect → redo 那一圈的真实形状：账本已经非空，本轮消息尾部还没有 dispatch 决策。"""
    return {
        "messages": [HumanMessage(content="各部门回款合计多少？")],
        "plan": [],
        "memory": {},
        "worker_results": {"data": ANSWER},
        "redo": True,
    }


@pytest.mark.parametrize(
    "guard,needle",
    [
        ("sink", GUARD_SINK),
        ("dispatch", GUARD_DISPATCH),
        ("ledger", GUARD_LEDGER),
    ],
)
def test_each_prerequisite_is_load_bearing(monkeypatch, guard, needle):
    """摘掉三格前置里的**任意一格**，那一格挡住的东西就立刻出门——每格都有可指名的后果。

    原件一侧钉今天的形状，影子一侧钉「刀真的咬到了」：哪一天这格前置变成装饰，影子与原件
    不再有任何差别，这枚钉自己先红——反证钉不许空转。
    """
    if guard == "sink":
        shipped = _direct_without_sink(monkeypatch)
        assert shipped["model"].calls[0][1] == {}, "没注册出口的那一发不再是单参数 invoke"
        assert shipped["bodies"][0]["stream"] is False, "队列道的请求体被改走流式了"
        _shadow(monkeypatch, "_supervisor_answer_tap", [(needle, DISABLE)])
        damaged = _direct_without_sink(monkeypatch)
        assert damaged["bodies"][0]["stream"] is True, "摘掉①之后队列道仍然不发流式：这格前置是空的"
        assert damaged["pieces"] == [], "摘掉①却不见后果：影子没咬到"
        return

    state = _dispatched_state() if guard == "dispatch" else _ledger_only_state()
    shipped = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE), state=state)
    assert shipped["pieces"] == [], (
        f"{guard} 那一形今天就在出口外，摘它做什么：先查前置是不是已经漏了"
    )
    assert shipped["model"].calls[0][1] == {}, "已派发的汇总那一发不该带 config"
    _shadow(monkeypatch, "_supervisor_answer_tap", [(needle, DISABLE)])
    damaged = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE), state=state)
    assert len(damaged["pieces"]) >= 2, f"摘掉{guard}那一格没有任何后果：这格前置不承重"
    leaked = "".join(piece.text for piece in damaged["pieces"])
    assert leaked == ANSWER, leaked[:24]
    if guard == "ledger":
        settled = [str(value).strip() for value in (state.get("worker_results") or {}).values()]
        assert leaked in settled, (
            f"摘掉③没量到「正文重复出两遍」：流出去的是 {leaked[:20]!r}，"
            f"而账本里落定的是 {settled}"
        )
    else:
        # 摘掉②的后果是「每一枚帧都是终答的前缀」被破坏：那一轮的终答由 synthesize 从
        # worker_results 折出来，与 supervisor 汇总那一发的字不同源。收端那一侧的读数在
        # tests/test_r459_ask_direct_answer_frames.py 的两腿用例里量。
        assert state.get("worker_results") or {} == {}, "影子用例的前提变了：账本已经非空"


def test_the_admission_list_is_not_widened_to_smuggle_the_supervisor(monkeypatch):
    """不借 worker 的名字进归因名单：主 Agent 那一发的 config 形状仍然被名单挡在外面。

    这一枚钉的是「接法」的底线。把 ``worker`` 填成 ``doc``／``data``／``chart`` 里任意一枚就能
    走通 ``nodes.answer_leg_stream_target`` 的正门，代价是往日志的 ``leg=`` 与
    ``StreamPiece.worker`` 里塞一枚假腿名，还要在 ``worker_results`` 真的落定那条腿时把两笔账
    混成一本。本单选的是复用同一枚 tap、另立一枚 honest 腿名。
    """
    assert nodes.ANSWER_LEG_STREAM_WORKERS == frozenset({"doc", "data", "chart"})
    assert orchestrator.SUPERVISOR_ANSWER_LEG not in nodes.ANSWER_LEG_STREAM_WORKERS
    assert orchestrator.SUPERVISOR_ANSWER_LEG not in {
        "doc", "data", "chart", "export", "approval",
    }, "腿名撞上了 worker_results 的键：收端那条「未落定就关门」的规则会失真"

    sink_called = []
    assert nodes.answer_leg_stream_target(_round_config(sink_called.append)) == (None, "")
    assert sink_called == []


def test_the_registered_r31_merge_caliber_is_untouched():
    """判据③ 的字面：两把尺与那块地板一个数都没动（允许新增，不许放宽）。"""
    assert nodes.STREAM_PIECE_MIN_CHARS == 20
    assert nodes.STREAM_PIECE_MERGE_SECONDS == 0.1
    assert nodes.STREAM_PIECE_STALL_FLOOR_CHARS == 4
    merger_source = inspect.getsource(nodes.StreamPieceMerger)
    assert "clock=time.monotonic" in merger_source, "空档闸换了时间源：R31 的 100 ms 就不是那把尺了"

# ==================== 三道闸门落在这条新腿上：T1 工具轮 / T3 半截字 ====================


def test_a_dispatch_turn_publishes_no_pieces_behind_t1(monkeypatch):
    """T1：那一发转去派活时，它的字一片都不许进出口（判据① 的「tool_calls 为空那一支」）。"""
    round_ = _run_round(monkeypatch, _tool_call_frames())

    assert round_["pieces"] == [], [piece.text for piece in round_["pieces"]]
    assert round_["update"]["messages"][0].tool_calls, "假 provider 的这一发本来就该是派发"


def test_pre_dispatch_chatter_leaks_at_most_the_pieces_a_later_arrival_already_proved(monkeypatch):
    """T2 的滚动留一把「口播之后转去派活」那一形的泄漏封在一枚片之内。

    run9 那九枚的兄弟形状是「先说一句再派活」：这类轮次里 supervisor 的字**不是**终答的前缀，
    多流一枚就是坏形。这里不假装它是零——本机实测这一形漏出至多一枚（已经由后一片证明过的那枚），
    残余风险的记账与处置（收端关门 + R210 纠正替换）钉在
    ``tests/test_r459_ask_direct_answer_frames.py``。
    """
    round_ = _run_round(monkeypatch, _chatter_then_tool_call_frames(ANSWER))
    pieces = round_["pieces"]

    assert len(pieces) <= 1, [piece.text for piece in pieces]
    assert round_["update"]["messages"][0].tool_calls
    if pieces:
        assert ANSWER.startswith(pieces[0].text), pieces[0].text
        assert pieces[0].text != ANSWER, "整段正文都流出去了还说闸门在挡：这一形必须是漏半截"


@pytest.mark.parametrize("fallback", ["dispatch", "sentence"])
def test_a_provider_that_dies_mid_stream_does_not_publish_the_tail(monkeypatch, fallback):
    """T3：provider 死在半路时，残余缓冲整片丢弃——半截字不许冒充答案的最后一块。

    两形都钉：supervisor 的 fallback 带着 ``dispatch``，交回的是一发空正文的派发；离线话术
    是另一形（手工造的模型腿、``_OfflineModel`` 没绑工具时）。两形都只许交出「已经被后一枚
    到达证明过」的那一片。
    """
    round_ = _run_round(
        monkeypatch, _text_frames(ANSWER, usage=USAGE), die_after=5, fallback=fallback
    )
    message = round_["update"]["messages"][0]

    assert round_["bodies"][0]["stream"] is True, "这一发准入过，才有半路可死"
    assert [piece.text for piece in round_["pieces"]] == [ANSWER[:36]], [
        piece.text for piece in round_["pieces"]
    ]
    if fallback == "dispatch":
        assert message.content == "" and message.tool_calls
    else:
        assert message.content == OFFLINE_SENTENCE


def test_a_bypassed_t3_would_publish_the_tail_as_a_final_piece(monkeypatch):
    """反证：摘掉 T3 的结清判据（把半路死掉那一发也当正常交回 close），尾巴冒充末片出门。

    摘了它，收端拿到的末帧是一段死在半路的真话前缀，而终答不是它的延伸——正是 ``[R149]``
    那行日志点名、R210 要用「纠正替换」收拾的形状。本单不制造它，也不放过它。
    """
    shipped = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE), die_after=5)
    assert [piece.text for piece in shipped["pieces"]] == [ANSWER[:36]]

    _shadow(monkeypatch, "_answer_leg_publishes_tail", [(TAIL_GUARD_BODY, "    return True\n")])
    bypassed = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE), die_after=5)
    assert len(bypassed["pieces"]) > 1, "摘掉 T3 没有任何后果：结清点不承重"
    assert "".join(piece.text for piece in bypassed["pieces"]).startswith(ANSWER[:36])
    assert "".join(piece.text for piece in bypassed["pieces"]) != ANSWER[:36]


def test_a_refused_call_publishes_nothing(monkeypatch):
    """预算拒发那一形（run9 的 metric-02／scope-02 上游）：出口一片都不许多。

    invoke 当场抛 ⇒ 节点既不 close 也不 abandon，pending 永不落地。这一枚钉的是「本单没把
    空读伪装成流式」：那两枚今天仍是 ``text_frames=0``，治它的是窗口预算，不是这条腿。
    """
    from app.common.model_budget import ModelContextLimitExceeded

    def refuse(self, prompt_tokens, stream=False):
        raise ModelContextLimitExceeded(self.budget, prompt_tokens)

    monkeypatch.setattr(nodes._ResilientModel, "_budget_kwargs", refuse)
    with pytest.raises(ModelContextLimitExceeded):
        _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE))


# ==================== 反证钉：绕过 R31 的合并闸就当场红 ====================


def test_a_bypass_of_the_r31_merger_breaks_the_piece_caliber(monkeypatch):
    """把 tap 换成「每枚 token 直交出口」：同一套口径断言当场红，片数还涨出一截。

    判据③ 要的是「合并发片那条规则不动」。这条钉把「不动」量成可指名的东西：除末片以外每一片
    都过 20 字尺寸闸；绕过合并闸之后这两把尺立刻失效——所以绿的是闸，不是运气。
    """
    assert "_RawTokenTap" not in inspect.getsource(orchestrator), "靶子被抄进产码了"
    shipped = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE))
    _check_piece_caliber(shipped["pieces"])

    _shadow(monkeypatch, "_supervisor_answer_tap", [("_AnswerPieceTap(", "_RawTokenTap(")])
    bypassed = _run_round(monkeypatch, _text_frames(ANSWER, usage=USAGE))
    assert len(bypassed["pieces"]) > len(shipped["pieces"]), "绕过合并闸没有任何后果：刀磨钝了"
    with pytest.raises(AssertionError, match="尺寸闸"):
        _check_piece_caliber(bypassed["pieces"])