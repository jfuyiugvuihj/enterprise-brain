# -*- coding: utf-8 -*-
"""R662 判据①③④ · 生产者那一侧：「答案已经成形」的那一发也必须逐片上屏。

在册病形（凭据纸 ``docs/testing/r662-a2-single-frame-rows-2026-10-05.md``，代次 ``9556513``）：
run22 ``data-12`` 的终答 **2858 字一帧发完**（帧账现读 ``text_frames=1``／
``max_stream_frames=1``／``answer_chars=2858``），A② 红在这一格上——**不是没答，是答得太整**。
离线回复到手时已经是一整段写完的字，收端一个字都不切（R149 钉死：
``tests/test_r149_sse_text_pieces.py::test_a_whole_answer_with_no_pieces_still_issues_exactly_one_text_frame``），
于是屏上只落一枚帧。本件钉的是生产者那一侧的新出口
``app/agents/nodes.py::publish_formed_answer_pieces``。

四枚可失败判据里属于生产者那一侧的三枚：

- **①**（不许一坨）：成形答复的 ``text`` 事件数必须 >1；
- **③**（逐字比对）：拼接后的片必须逐字等于终答全文 —— ``missing_chars == 0`` 且
  ``extra_chars == 0``；
- **④**（末帧覆盖）：末帧必须以终答全文开头 —— ``last_frame_covers_answer`` 为真。

判据②（逐片递增且不重叠）住在片的时间戳上：本件按 R524 在册那枚断言逐片钉
``later.start_at >= earlier.end_at``，再用在册尺自己抄下来的 ``frames`` 列核
``arrival_at`` 一列非减。🔴 没有第二把尺。

三条纪律各有一枚钉守着，因为它们是这一单最容易被「修绿」的地方：

- 不许加 sleep／节流：片与片之间的间隔只能由**发射本身**产生（同步一次调用一片）；
- 攒不出第二枚就一枚都不发：尺寸闸说了算，不许硬切凑多发把 ``text_frames`` 洗大；
- 准入一字不放宽：名单外的腿、没注册出口的道、已经流过半截真话的那一发、工具轮，
  每一枚片都不许多。

判分只用一把尺：``scripts/eval_transport_ask_v2.py`` 的 ``_frame_readings``／``_frame_verdict``，
组合方式与在册的 ``_record_frames`` 逐字相同（含 R471 那枚 ``cross_stream_repeat_frames``
从 ``frames`` 列**现场派生**、不落成新列）。本件不改评测夹具、不自造分母。
"""

import ast
import asyncio
import inspect
import json
import os
import textwrap
from uuid import uuid4

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.agents import nodes, orchestrator
from app.agents.contracts import ModelTier
from app.api.v1 import chat
from app.common import model_budget
from app.common.model_budget import model_tier_budget

from tests.test_r203_answer_leg_streams import USAGE, _chunk, _config  # noqa: F401
from tests.test_r203_sse_progressive_frames import QUESTION, _http_request, ruler
from tests.test_r210_break_replaces_the_screen import _text_contents, _wire
from tests.test_r215_recognizing_a_controlled_correction import _lines

#: run22 那三枚红题的字数，**现取**自帧账（``answer_chars`` 一格），不是本件挑的数。
REGISTERED_CHARS = {"data-12": 2858, "chart-01": 31, "tool-04": 170}
SESSION_ID = "sess-r662"
#: 一枚 token 的真实字数：真 provider 逐 token 吐字，中文一枚 token 通常 1—4 字。
#: 🔴 本件不按 R524 那 18 字一枚打帧 —— 31 字那一形按 18 字切只够撞响一枚尺寸闸，
#: 那是 R524 自己的病历形状，不是屏上今天到不到达的形状（凭据纸 §4 末节写了这一格的取舍）。
TOKEN_CHARS = 4


# ==================== 形状：把「已经成形的一整段」造出来 ====================


def _formed_body(chars: int) -> str:
    """造一枚**恰好** ``chars`` 字的成形答复（字数现取自在册帧账）。"""
    seed = "差旅费报销的住宿费标准按城市档位执行，凭发票据实核销，超标部分需签字确认。"
    return (seed * (1 + chars // len(seed)))[:chars]


def _token_frames(text, delta=TOKEN_CHARS):
    """逐 token 的 SSE 帧序列：与真流式同一枚形状（小增量 + 收尾 usage 帧）。"""
    frames = [_chunk({"role": "assistant", "content": ""})]
    for start in range(0, len(text), delta):
        frames.append(_chunk({"content": text[start:start + delta]}))
    frames.append(_chunk({}, usage=USAGE))
    return frames


def _sse(text, delta=TOKEN_CHARS):
    payload = "".join("data: " + json.dumps(f, ensure_ascii=False) + "\n\n"
                      for f in _token_frames(text, delta))
    return (payload + "data: [DONE]\n\n").encode("utf-8")


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


def _resilient(handler, *, fallback=None):
    """真 :class:`nodes._ResilientModel`；``fallback`` 不给就是真 ``_OfflineModel``。"""
    return nodes._ResilientModel(
        _client(handler),
        fallback,
        provider="local-openai-compatible",
        model_name="fake",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.ANALYSIS),
    )


def _dying_handler(text_on_wire=None):
    """一枚字都没流就坏掉的 provider：``data-12`` 那一形的因。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b'data: {"broken\n\n',
        )

    return handler


def _streaming_handler(text):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_sse(text))

    return handler

# ==================== 一把尺：与在册 _record_frames 逐字相同的组合 ====================


def _round_ledger(streams):
    """把几条流（``(事件名, 载荷)`` 序列）折成一题的帧账，走量具**真收端**那几件函数。"""
    ledger = ruler._new_frame_ledger()
    for events in streams:
        out = ruler._blank_observation(SESSION_ID)
        ruler._consume(_lines(list(events)), out)
        ruler._fold_frames(ledger, out)
    return ledger


def _round_readings(streams, answer):
    """``_record_frames`` 的内存版：读数 + R223 到达列 + R471 那枚现场派生的重合数。

    🔴 顺序与在册那枚落盘件一致：``_frame_readings`` 先算，``cross_stream_repeat_frames``
    后派生并**只交给尺子**，不进 ``_frame_readings`` 的返回形状（帧账一行的键集钉在
    ``tests/test_r181_text_frame_ruler.py`` 的 ``FRAME_READING_KEYS``，本单不许开那一格）。
    """
    ledger = _round_ledger(streams)
    readings = ruler._frame_readings(ledger, answer)
    arrivals = ruler._arrival_readings(ledger)
    readings["cross_stream_repeat_frames"] = ruler._cross_stream_repeats(arrivals["frames"])
    return readings, arrivals["frames"]


def _round_verdict(streams, answer):
    """在册七枚合取的判定（``_frame_verdict``），一格都不新加、一枚都不减。"""
    readings, _frames = _round_readings(streams, answer)
    return bool(ruler._frame_verdict(readings)), readings


#: 判据①③④ 各自的格名：红了要报得出是哪一格，不是"verdict 是 False"。
CONJUNCTION_CELLS = ("text_frames", "max_stream_frames", "uncorrected_breaks",
                     "missing_chars", "extra_chars", "last_frame_covers_answer",
                     "cross_stream_repeat_frames")


def _assert_seven_green(readings, question_id):
    assert readings["text_frames"] > 1, (question_id, readings["text_frames"])
    assert readings["max_stream_frames"] > 1, (question_id, readings["max_stream_frames"])
    assert readings["uncorrected_breaks"] == 0, (question_id, readings["prefix_breaks"])
    assert readings["missing_chars"] == 0, (question_id, readings["missing_chars"])
    assert readings["extra_chars"] == 0, (question_id, readings["extra_chars"])
    assert readings["last_frame_covers_answer"] is True, question_id
    assert readings["cross_stream_repeat_frames"] == 0, question_id


# ==================== 离线夹具：假只假在 orchestrator 那一层 ====================


@pytest.fixture(autouse=True)
def _trace_to_tmp(tmp_path, monkeypatch):
    """一发额度 + trace 落 tmp：读数不进仓库，也不占真模型的槽（与 R203 同一分工）。"""
    from app.trace import spans
    from app.trace.store import TraceStore

    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    # 窗口按**部署那一侧的在配值**给（``app/agents/contracts.py::ModelBudget`` 记的在册读数
    # 就是 prompt_tokens=14928 打在 MODEL_CONTEXT_TOKENS=16384 上）：``.env.example`` 那枚 4096
    # 是开发缺省，拿它跑 2858 字的成形答复会先撞上下文闸，量不到本单要量的那一格。
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "16384")
    model_budget.reset_default_budget()
    monkeypatch.setattr(spans, "default_trace_store",
                        lambda: TraceStore(tmp_path / "r662-spans.jsonl"))
    yield
    model_budget.reset_default_budget()


def _drain(response) -> str:
    async def _read():
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return "".join(parts)

    return asyncio.run(_read())


def _offline_ask(monkeypatch, tmp_path):
    """把 /ask 周围那圈依赖摘到内存：会话库、缓存、鉴权、检索留痕，一律零端口零容器。"""
    from app.common import cache
    from app.storage.sessions import SessionRegistry

    monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())
    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _s, m: m)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "auth",
                        type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}))
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator, "check_interrupt", lambda _tid: None)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))


def _ask_round(monkeypatch, tmp_path, *, leg, worker, seen):
    """跑一整轮真 /ask：假只假在编排那一层，生成腿／出口／收端／闸门全真。

    ``leg(sink, worker, seen)`` 必须交回一枚 ``AIMessage``；它交回什么，本轮终答就是什么
    —— ``worker_results`` 里存的必须是**腿真交回的那句**（与 R210 同一裁定，收端不许
    重新拼一份字）。
    """
    _offline_ask(monkeypatch, tmp_path)
    handed = {}

    def fake_stream(*_args, **kwargs):
        sink = kwargs.get("stream_piece_sink")

        def spy(piece):
            seen.append(piece)
            sink(piece)

        message = leg(spy if callable(sink) else None, worker, seen)
        content = str(getattr(message, "content", "") or "")
        handed[worker] = content
        yield {"messages": [], "worker_results": {worker: content}, "final_answer": content}

    monkeypatch.setattr(orchestrator, "run_with_stream", fake_stream)
    body = _drain(asyncio.run(chat.ask(
        chat.AskRequest(message=QUESTION, session_id=SESSION_ID),
        http_request=_http_request())))
    return body, handed[worker]


def _data_12_leg(sink, worker, seen):
    """``data-12`` 那一形：provider 一枚字都没流就坏，离线回复把 ToolMessage 整段回声交回。

    🔴 那 2858 字**不是**本件编的道具：``app/agents/nodes.py::_OfflineModel.invoke`` 今天
    就是这么交回离线回复的（倒着找到的第一枚 ``ToolMessage`` 整段回声），所以这一发的字
    从来没过过出口，收端只能发成一坨。
    """
    long_tool_output = _formed_body(REGISTERED_CHARS["data-12"])
    messages = [HumanMessage(content=QUESTION),
                ToolMessage(content=long_tool_output, tool_call_id="call-r662",
                            name="query_data")]
    return _resilient(_dying_handler()).invoke(
        messages, config=_config(sink=sink, worker=worker))


def _silent_leg_factory(text):
    """交回整段成形字、但一枚 token 回调都没发的那一发（``tap.close()`` 读数 0 那一格）。"""

    class _SilentPrimary:
        model_name = "fake"

        def invoke(self, messages, config=None, **kwargs):
            return AIMessage(content=text)

        def bind_tools(self, tools):
            return self

    def leg(sink, worker, seen):
        model = nodes._ResilientModel(
            _SilentPrimary(), None, provider="local-openai-compatible", model_name="fake",
            capacity_wait_seconds=0, budget=model_tier_budget(ModelTier.ANALYSIS))
        return model.invoke([HumanMessage(content=QUESTION)],
                            config=_config(sink=sink, worker=worker))

    return leg

# ==================== 判据① ：成形答复不许发成一坨（生产者那一侧） ====================


def test_a_formed_answer_publishes_more_than_one_piece():
    """2858 字那一形（run22 ``data-12`` 现读字数）交回来的片数必须远大于 1。"""
    body = _formed_body(REGISTERED_CHARS["data-12"])
    seen = []
    published = nodes.publish_formed_answer_pieces(_config(sink=seen.append, worker="data"), body)
    assert published > 1, published
    assert len(seen) == published, (len(seen), published)


def test_the_pieces_join_back_to_the_formed_answer_verbatim():
    """判据③ 的生产者半边：拼接后的片逐字等于终答全文，一个字符不多也不少。"""
    body = _formed_body(REGISTERED_CHARS["data-12"])
    seen = []
    nodes.publish_formed_answer_pieces(_config(sink=seen.append, worker="data"), body)
    assert "".join(piece.text for piece in seen) == body
    assert len("".join(piece.text for piece in seen)) == REGISTERED_CHARS["data-12"]


def test_the_piece_intervals_are_increasing_and_never_overlap():
    """判据② 的前半句（§21 R31 ②）：逐片时间戳递增且两两不重叠。

    断言字面沿用 R524 在册那枚 ``assert_progressive_delivery`` 的写法：排序比的是
    ``start_at``，判的是 ``later.start_at >= earlier.end_at``（区间可偏窄不可重叠）。
    """
    body = _formed_body(REGISTERED_CHARS["data-12"])
    seen = []
    nodes.publish_formed_answer_pieces(_config(sink=seen.append, worker="data"), body)
    ordered = sorted(seen, key=lambda piece: piece.start_at)
    assert [piece.start_at for piece in ordered] == [piece.start_at for piece in seen]
    for earlier, later in zip(ordered, ordered[1:]):
        assert later.start_at >= earlier.end_at, (earlier, later)
    for earlier, later in zip(seen, seen[1:]):
        assert later.emitted_at >= earlier.emitted_at


def test_every_piece_but_the_last_clears_the_registered_size_gate():
    """本件用的就是 R31 那枚尺寸闸：除末片外，任何一片都不短于 20 字。"""
    body = _formed_body(REGISTERED_CHARS["tool-04"])
    seen = []
    nodes.publish_formed_answer_pieces(_config(sink=seen.append, worker="chart"), body)
    assert len(seen) > 1, seen
    for piece in seen[:-1]:
        assert len(piece.text) >= nodes.STREAM_PIECE_MIN_CHARS, piece
    assert seen[-1].text == body[-len(seen[-1].text):]


def test_the_pieces_carry_one_call_identity_and_the_leg_name():
    """R149b 硬前置：片必须带调用身份；补出来的成形片同一发只许一枚 ``call_id``。"""
    body = _formed_body(REGISTERED_CHARS["tool-04"])
    seen = []
    nodes.publish_formed_answer_pieces(_config(sink=seen.append, worker="data"), body)
    assert len({piece.call_id for piece in seen}) == 1, seen
    assert all(piece.call_id for piece in seen)
    assert {piece.worker for piece in seen} == {"data"}


def test_a_given_call_id_is_reused_not_reforged():
    """调用方给了身份就沿用：同文两发要能分成两条流，靠的就是这一格。"""
    body = _formed_body(REGISTERED_CHARS["tool-04"])
    seen = []
    call_id = uuid4().hex[:12]
    nodes.publish_formed_answer_pieces(_config(sink=seen.append, worker="data"), body,
                                       call_id=call_id)
    assert {piece.call_id for piece in seen} == {call_id}


# ==================== 纪律一：攒不出第二枚就一枚都不发（禁硬切凑多发） ====================


@pytest.mark.parametrize("chars", [1, 7, nodes.STREAM_PIECE_MIN_CHARS - 1,
                                   nodes.STREAM_PIECE_MIN_CHARS])
def test_a_formed_answer_shorter_than_two_gates_publishes_not_a_single_piece(chars):
    """天然短过尺寸闸的那一族：本件一枚都不补，不拿多发同文帧把 ``text_frames`` 洗大。"""
    seen = []
    published = nodes.publish_formed_answer_pieces(
        _config(sink=seen.append, worker="data"), _formed_body(chars))
    assert published == 0, (chars, published)
    assert seen == [], (chars, seen)


def test_a_formed_answer_of_blank_text_publishes_nothing():
    seen = []
    for blank in ("", "   ", "\n\n\t"):
        assert nodes.publish_formed_answer_pieces(
            _config(sink=seen.append, worker="data"), blank) == 0
    assert seen == []


def test_the_first_shape_that_streams_is_one_gate_plus_one_char():
    """边界读数：一枚尺寸闸那么宽只发一坨，多一个字才长出第二枚片。"""
    gate = nodes.STREAM_PIECE_MIN_CHARS
    single, edge, double = [], [], []
    assert nodes.publish_formed_answer_pieces(
        _config(sink=single.append, worker="data"), _formed_body(gate)) == 0
    assert single == []
    assert nodes.publish_formed_answer_pieces(
        _config(sink=edge.append, worker="data"), _formed_body(gate + 1)) == 2
    assert "".join(piece.text for piece in edge) == _formed_body(gate + 1)
    assert nodes.publish_formed_answer_pieces(
        _config(sink=double.append, worker="data"), _formed_body(2 * gate)) == 2
    assert [len(piece.text) for piece in double] == [gate, gate]


# ==================== 纪律二：准入一字不放宽 ====================


@pytest.mark.parametrize("worker", ["export", "approval", "supervisor", "respond", ""])
def test_a_leg_outside_the_registered_list_publishes_no_pieces(worker):
    seen = []
    assert nodes.publish_formed_answer_pieces(_config(sink=seen.append, worker=worker),
                                              _formed_body(REGISTERED_CHARS["data-12"])) == 0
    assert seen == []


def test_a_round_with_no_registered_sink_publishes_no_pieces():
    """队列道、审批道、离线直调：没人注册出口就一个字都不许多（判据④ 的旧形状）。"""
    assert nodes.publish_formed_answer_pieces(_config(sink=None, worker="data"),
                                              _formed_body(REGISTERED_CHARS["data-12"])) == 0
    assert nodes.publish_formed_answer_pieces({"configurable": {"worker": "data"}},
                                              _formed_body(120)) == 0


@pytest.mark.parametrize("listed", sorted(nodes.ANSWER_LEG_STREAM_WORKERS))
def test_the_admission_reads_the_very_list_r203_pinned(listed):
    """名单内那一族确实进得来 —— 名单本身一格未放宽（钉在 R203/R459/R524，本件只复述）。"""
    seen = []
    published = nodes.publish_formed_answer_pieces(
        _config(sink=seen.append, worker=listed), _formed_body(REGISTERED_CHARS["data-12"]))
    assert published > 1, (listed, published)
    assert {piece.worker for piece in seen} == {listed}
# ==================== 纪律三：不许拿 sleep／节流当修复 ====================


def _call_names(func) -> list:
    """一枚函数体里真出现的**调用名**（docstring 里提到 sleep 不算，注释也不算）。"""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target, parts = node.func, []
        while isinstance(target, ast.Attribute):
            parts.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            parts.append(target.id)
        names.append(".".join(reversed(parts)))
    return names


def test_the_producer_contains_no_wait_of_any_kind():
    """分片不许引入新的等待成本：本件里一枚 sleep／定时器／锁都长不出来。

    片与片之间的间隔由**发射本身**产生：一片一次 ``sink(piece)`` 进队列，收端那一枚
    ``await asyncio.sleep(0)`` 是在册的（R149 的 AST 面闸钉着它不许长出节流）。
    """
    banned = {"sleep", "time.sleep", "asyncio.sleep", "Event.wait", "Lock.acquire",
              "Timer", "threading.Timer", "queue.Queue", "put", "join"}
    for func in (nodes.publish_formed_answer_pieces, nodes.publish_formed_reply_for_call):
        names = _call_names(func)
        hits = sorted(name for name in names
                      if name in banned or name.endswith(".sleep") or name.endswith(".wait"))
        assert hits == [], (func.__name__, hits)


def test_the_producer_is_synchronous_so_a_wait_cannot_hide_in_it():
    """同步函数结构上发不出「等一会儿再发下一片」：这一格把上面的读数钉成方向性的。"""
    for func in (nodes.publish_formed_answer_pieces, nodes.publish_formed_reply_for_call):
        assert not asyncio.iscoroutinefunction(func), func.__name__
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
        assert not any(isinstance(node, ast.Await) for node in ast.walk(tree)), func.__name__


# ==================== T1／T3 那两条既有闸门：本件一字不改地尊重 ====================


def _tap(config, sink, worker, *, published=0, abandoned=""):
    tap = nodes._AnswerPieceTap(config, sink, worker=worker, call_id=uuid4().hex[:12])
    tap.published = published
    if abandoned:
        tap.abandon(abandoned)
    return tap


def test_a_round_that_already_put_half_an_answer_on_screen_publishes_nothing():
    """T3（钉在 R149/R203）：已经有一半真话上过屏，离线回复不是它的延伸 ⇒ 一枚都不许多。"""
    seen = []
    config = _config(sink=seen.append, worker="data")
    tap = _tap(config, seen.append, "data", published=2)
    got = nodes.publish_formed_reply_for_call(
        config, AIMessage(content=_formed_body(REGISTERED_CHARS["data-12"])), tap=tap)
    assert got == 0, got
    assert len(seen) == 0, seen


def test_a_tool_call_round_publishes_no_pieces_even_when_it_hands_back_text():
    """T1（钉在 ``tests/test_r203_answer_leg_streams.py::test_a_tool_call_round_publishes_no_pieces``）。"""
    seen = []
    config = _config(sink=seen.append, worker="data")
    tap = _tap(config, seen.append, "data", abandoned="tool_call")
    assert nodes.publish_formed_reply_for_call(
        config, AIMessage(content=_formed_body(120)), tap=tap) == 0
    assert seen == []


def test_the_gate_hands_back_the_pieces_when_nobody_spoke_first():
    """同一条腿、同一段字，闸门空着 ⇒ 补得出片：上面两枚读数的对照组。"""
    seen = []
    config = _config(sink=seen.append, worker="data")
    tap = _tap(config, seen.append, "data")
    got = nodes.publish_formed_reply_for_call(
        config, AIMessage(content=_formed_body(REGISTERED_CHARS["tool-04"])), tap=tap)
    assert got > 1, got
    assert "".join(piece.text for piece in seen) == _formed_body(REGISTERED_CHARS["tool-04"])


# ==================== 端到端：data-12 那一形今天过了在册尺 ====================


def test_the_offline_reply_that_ran_as_one_block_now_streams_pieces(monkeypatch, tmp_path):
    """``data-12`` 病历复现（改后读数）：真 /ask + 真坏 provider + 真离线回声。

    改前在册读数（run22 帧账这一行）：``text_frames=1``／``max_stream_frames=1``／
    ``answer_chars=2858`` ⇒ ``criterion_two_holds=false``，红的正是判据① 那一格
    （不缺字、不多字、末帧覆盖、零坏形，四枚本来就绿）。
    """
    seen: list = []
    body, delivered = _ask_round(monkeypatch, tmp_path, leg=_data_12_leg,
                                 worker="data", seen=seen)
    assert delivered == _formed_body(REGISTERED_CHARS["data-12"])
    assert len(seen) > 1, f"出口只交回 {len(seen)} 片：判据① 没落地"
    frames = _text_contents(body)
    assert len(frames) > 1, f"屏上只落一枚帧：{[len(f) for f in frames]}"
    assert "".join(piece.text for piece in seen) == delivered
    readings, arrivals = _round_readings([_wire(body)], delivered)
    _assert_seven_green(readings, "data-12")
    assert bool(ruler._frame_verdict(readings)) is True, readings
    assert [item.get("arrival_at") for item in arrivals] == sorted(
        item.get("arrival_at") for item in arrivals), "逐帧到达时刻倒着走"


def test_the_terminal_frame_still_covers_the_whole_answer(monkeypatch, tmp_path):
    """判据④ 单独点名：末帧必须以终答全文开头，而且逐字等于它（分片不许吃掉末尾）。"""
    seen: list = []
    body, delivered = _ask_round(monkeypatch, tmp_path, leg=_data_12_leg,
                                 worker="data", seen=seen)
    readings, _arrivals = _round_readings([_wire(body)], delivered)
    assert readings["last_frame_covers_answer"] is True
    assert readings["missing_chars"] == readings["extra_chars"] == 0
    assert readings["last_frame_chars"] == readings["answer_chars"] == len(delivered)
    assert _text_contents(body)[-1] == delivered


def test_an_aggregated_return_that_never_touched_the_sink_still_streams(monkeypatch, tmp_path):
    """``_ResilientModel.invoke`` 的第三处出口：正常返回但一枚片都没交出去 ⇒ 补成逐片。"""
    seen: list = []
    text = _formed_body(REGISTERED_CHARS["tool-04"])
    body, delivered = _ask_round(monkeypatch, tmp_path, leg=_silent_leg_factory(text),
                                 worker="chart", seen=seen)
    assert delivered == text
    assert len(seen) > 1, seen
    assert len(_text_contents(body)) > 1
    readings, _frames = _round_readings([_wire(body)], delivered)
    _assert_seven_green(readings, "chart(tool-04 字数)")
# ==================== 反证牙 A：摘掉分片必须红，并且点得出题号 ====================


@pytest.mark.parametrize("question_id", ["data-12"])
def test_knife_a_dropping_the_formed_piece_producer_goes_red_naming_the_row(monkeypatch, tmp_path,
                                                                           question_id):
    """把 ``publish_formed_reply_for_call`` 摘成恒 0（＝本单的货没落地）⇒ 这一行必须红。

    🔴 红了要红得**只在**判据① 那一格：run22 ``data-12`` 这一行本来就满足其余六枚合取
    （``missing_chars=0``／``extra_chars=0``／末帧覆盖／``uncorrected_breaks=0``／
    ``cross_stream_repeat_frames`` 派生为 0），病历就是「答得整，但没逐字」，读数
    ``text_frames=1``／``max_stream_frames=1``。摘刀复现出来的必须正是这一形。
    """
    monkeypatch.setattr(nodes, "publish_formed_reply_for_call", lambda *_a, **_k: 0)
    seen: list = []
    body, delivered = _ask_round(monkeypatch, tmp_path, leg=_data_12_leg,
                                 worker="data", seen=seen)
    assert seen == [], seen
    frames = _text_contents(body)
    assert len(frames) == 1, [len(frame) for frame in frames]
    readings, _arrivals = _round_readings([_wire(body)], delivered)
    assert readings["text_frames"] == 1, readings
    assert readings["max_stream_frames"] == 1, readings
    assert readings["answer_chars"] == REGISTERED_CHARS[question_id], readings
    assert (readings["missing_chars"], readings["extra_chars"]) == (0, 0)
    assert readings["last_frame_covers_answer"] is True
    assert readings["uncorrected_breaks"] == 0
    assert readings["cross_stream_repeat_frames"] == 0
    assert bool(ruler._frame_verdict(readings)) is False, readings


@pytest.mark.parametrize("worker,expected_frames", [("data", 1), ("export", 1)])
def test_knife_b_the_admission_gate_is_what_makes_the_row_green(worker, expected_frames,
                                                                monkeypatch, tmp_path):
    """反证牙 B：把这一发挪出名单（``export``）⇒ 同一句 2858 字照旧发成一坨。
    绿的因只能落在「名单内的那一发 + 注册过的出口」这一格上。名单本身一格未放宽：
    ``data`` 那一走绿（片 >1），``export`` 那一走回到改前那一形 —— ``publish_formed_answer_pieces``
    今天照样被调用，但 ``answer_leg_stream_target`` 把它挡在门外，屏上仍旧一枚帧。
    """
    seen: list = []
    body, delivered = _ask_round(monkeypatch, tmp_path, leg=_data_12_leg,
                                 worker=worker, seen=seen)
    frames = _text_contents(body)
    if worker in nodes.ANSWER_LEG_STREAM_WORKERS:
        assert len(seen) > 1 and len(frames) > 1, (len(seen), len(frames))
    else:
        assert seen == [], seen
        assert len(frames) == expected_frames, [len(frame) for frame in frames]
        readings, _arrivals = _round_readings([_wire(body)], delivered)
        assert readings["max_stream_frames"] == 1, readings
        assert bool(ruler._frame_verdict(readings)) is False, readings


def test_a_naturally_short_formed_answer_still_issues_exactly_one_frame(monkeypatch, tmp_path):
    """方向钉：天然短过尺寸闸的那一发，本单**不多发**一枚帧（与 R149 同一条裁定）。"""
    seen: list = []
    text = "已按离线口径回复。"
    body, delivered = _ask_round(monkeypatch, tmp_path,
                                 leg=lambda sink, worker, _seen: AIMessage(content=text),
                                 worker="data", seen=seen)
    assert delivered == text
    assert seen == [], seen
    assert len(_text_contents(body)) == 1, _text_contents(body)
def test_a_half_streamed_round_that_delivered_no_pieces_still_publishes_nothing():
    """🔴 闸门认「到过字」，不认「出过片」：T2 压住那一枚时 ``published`` 可以是 0。

    这一形是 R210 在册的「半截真话 + 离线话术」（钉在
    ``tests/test_r210_frame_ledger_of_a_broken_round.py``）：provider 流了两枚字才坏，
    那枚已经成形的片被 T2 压在手里、随 ``abandon()`` 整片丢弃，出口读数 ``published=0``。
    如果补片那一格按 ``published`` 放行，屏上就会多出好几枚「离线话术的逐片累计帧」，
    把一次纠正替换洗成一串片 —— 本件按 ``arrived_chars`` 拦，读数是**一枚片都不许多**。
    """
    seen: list = []
    frames = [_chunk({"role": "assistant", "content": ""}),
              _chunk({"content": "公司报销流程一般包括提交申请"}),
              _chunk({"content": "、部门审批、财务复核和付款归档"})]
    payload = "".join("data: " + json.dumps(f, ensure_ascii=False) + "\n\n" for f in frames)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"},
            content=(payload + 'data: {"broken\n\n').encode("utf-8"))

    class _LongOffline:
        def invoke(self, messages, config=None, **kwargs):
            return AIMessage(content=_formed_body(REGISTERED_CHARS["tool-04"]))

        def bind_tools(self, tools):
            return self

    message = _resilient(handler, fallback=_LongOffline()).invoke(
        [HumanMessage(content=QUESTION)], config=_config(sink=seen.append, worker="doc"))
    assert str(message.content) == _formed_body(REGISTERED_CHARS["tool-04"])
    assert seen == [], [piece.text for piece in seen]
# ==================== 复演件：把真发射件交回的字节落到仓外（按 env 开关） ====================

#: 与 ``tests/test_approve_canonical_events.py`` 的 ``APPROVE_EVENT_INVENTORY_OUT``、
#: ``tests/test_sse_sources.py`` 的 ``SSE_EVENT_INVENTORY_OUT`` 同一分工：缺省 skip，
#: 总控按下开关才落证据，凭据纸里的「改后读数」就是从这一份字节复演出来的。
SHADOW_WIRE_ENV = "R662_SHADOW_WIRE_OUT"
#: run22 这两行的 ``kind`` 现取（写进证据件是为了复演时不必回头猜档位）。
SHADOW_KIND = {"data-12": "ok", "chart-01": "approved_ok", "tool-04": "approved_ok"}


def _record_shadow_wire(question_id, bodies, delivered, pieces):
    target = os.environ.get(SHADOW_WIRE_ENV)
    if not target:
        pytest.skip(f"复演件只在 {SHADOW_WIRE_ENV} 设了仓外路径时才落盘")
    row = {"id": question_id, "kind": SHADOW_KIND[question_id],
           "answer": delivered, "sse": list(bodies),
           "pieces": [{"text": piece.text, "start_at": piece.start_at,
                       "end_at": piece.end_at, "emitted_at": piece.emitted_at,
                       "call_id": piece.call_id, "worker": piece.worker}
                      for piece in pieces]}
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        print(json.dumps(row, ensure_ascii=False), file=handle)


@pytest.mark.parametrize("question_id", ["data-12"])
def test_record_the_shadow_wire_of_the_offline_fallback_round(monkeypatch, tmp_path, question_id):
    """``data-12`` 那一形过真发射件后的字节（单流 /ask，离线回声整段成形）。"""
    seen: list = []
    body, delivered = _ask_round(monkeypatch, tmp_path, leg=_data_12_leg,
                                 worker="data", seen=seen)
    assert len(_text_contents(body)) > 1, "复演件不许交回一枚帧：先修好再落证据"
    _record_shadow_wire(question_id, [body], delivered, seen)