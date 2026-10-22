"""R149 生成轮流式透传（收端半）：SSE 出口逐片发**累计** text 帧。

判据对应（跟进单 §76 第一条）：

- 判据①「一次真实生成的 SSE 里 text 事件数 > 1」：本件钉的是**收端**那一半——片到了就多发。
  线上那一半今天发不出来，因为生产图路径上的生成腿只被 ``invoke``（R31 已具名上报，本单在
  案发现场复现），改它属 ``nodes.py``/``orchestrator.py``，本单禁碰。见交付说明的判决实验。
- 判据②「每枚片携带截至该片的累计全文」：``test_every_frame_carries_the_cumulative_prefix_```；
  ``test_a_whole_answer_with_no_pieces_still_issues_exactly_one_text_frame`` 是"不许硬切凑多发"
  的反证靶子：整段答案、零片时仍然只有一枚帧。
- 判据③「done 那枚帧不许消失、不许改形状」：``test_the_done_frame_is_byte_for_byte_```，
  外加旧钉 ``tests/test_answer_cache_scope.py`` / ``tests/test_routing_intent_and_terminal_state.py``
  / ``tests/test_sse_sources.py`` 一枚都不许红。
- 判据④「R35 三枚缓存字段在每一枚片上语义一致」：``test_live_frames_never_carry_a_cache_mark```
  与 ``test_cache_fields_are_the_same_on_every_frame_within_a_turn``。
- 判据⑤「逐片不引入 sleep/节流、first_text_at 显著早于 wall」：
  ``test_the_piece_branch_contains_no_sleep_or_throttle``（AST 面闸）＋
  ``test_piece_frames_reach_the_wire_while_the_run_is_still_open``（因果时序）。

全程离线：假 orchestrator、缓存层的内存回退、tmp 里的会话表。不开 socket、不打模型端口、
不起服务——直接吃 ``chat.ask`` 返回体的 ``body_iterator``，与既有旧钉同一招。
"""

import asyncio
import ast
import inspect
import json
import logging
import time

from app.agents import nodes, orchestrator
from app.agents.contracts import Principal
from app.api.v1 import chat

QUESTION = "差旅费报销的住宿费标准是多少？"
ANSWER = (
    "一线城市住宿费为每晚 500 元，凭发票按实际发生额报销；"
    "二三线城市住宿费为每晚 350 元，超标部分需要部门负责人签字确认之后才可以入账。"
)
#: 三枚增量，拼起来逐字等于 ANSWER。判据② 要的正是"帧=累计、片=增量"这一对关系。
INCREMENTS = [ANSWER[:26], ANSWER[26:52], ANSWER[52:]]
CACHE_FIELDS = ("cached", "cache_generated_at", "cache_note")
RUN_KWARGS = [
    "cancel_event",
    "request_id",
    "stream_piece_sink",
    "task_id",
    "thread_id",
    "trace_id",
    "user",
]


def _principal():
    return Principal(
        user_id="u-r149",
        username="staff-r149",
        roles=["staff"],
        permissions=["document:read"],
        department="finance",
        department_ids=[],
        clearance=2,
        clearance_label="L2",
        status="active",
    )


def _memory_cache(monkeypatch):
    """缓存层换成内存回退：REDIS_URL 未设时生产上跑的就是这一套（与 R35 旧钉同一招）。"""
    from app.common import cache

    backend = cache._MemoryRedis()
    monkeypatch.setattr(cache, "_redis", backend)
    return backend


def _http_request(principal):
    return type(
        "Request",
        (),
        {
            "state": type(
                "State", (), {"principal": principal, "username": principal.username}
            )()
        },
    )()


def _harness(monkeypatch, tmp_path, answers, publish=None):
    """把 /ask 挂到一枚假 orchestrator 上。

    ``publish(sink, answer)`` 决定这一轮往注册进来的片段出口里放什么：不放就是今天的线上
    形状（零片），放就是在终答出来之前先把模型侧的增量交出去。假的是**生产者**，收端跑的
    是真实代码，所以这条证据不是"字段达标"。
    """
    from app.storage.sessions import SessionRegistry

    # 每枚用例换一具全新的内存缓存：app.common.cache 的模块级后端跨用例是粘着的，
    # 不复位就会出现"第二枚用例命中了第一枚写进去的答案"这种假象。
    _memory_cache(monkeypatch)
    remaining = list(answers)
    seen = {}

    def fake_stream(*_args, **kwargs):
        seen["sink"] = kwargs.get("stream_piece_sink")
        seen["kwargs"] = sorted(kwargs)
        answer = remaining.pop(0)
        if seen["sink"] is not None and publish is not None:
            publish(seen["sink"], answer)
        yield {
            "messages": [],
            "worker_results": {"doc": answer},
            "final_answer": answer,
        }

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(
        chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)})
    )
    monkeypatch.setattr(
        "app.common.cache.check_rate_limit", lambda *_args, **_kwargs: (True, 9)
    )
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    def ask(principal=None, message=QUESTION, session_id="sess-r149"):
        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message=message, session_id=session_id),
                http_request=_http_request(principal or _principal()),
            )
        )

        async def consume():
            chunks = [chunk async for chunk in response.body_iterator]
            return "".join(
                chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in chunks
            )

        return asyncio.run(consume())

    def ask_timed(principal=None, message=QUESTION, session_id="sess-r149-timed"):
        """逐帧记录到达时刻：判据⑤ 要的是"片早于终答"，这只能靠时间戳证。"""

        async def consume():
            started = time.monotonic()
            rows = []
            async for chunk in response.body_iterator:
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8")
                rows.append((time.monotonic() - started, chunk))
            return {"frames": rows, "wall": time.monotonic() - started}

        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message=message, session_id=session_id),
                http_request=_http_request(principal or _principal()),
            )
        )
        return asyncio.run(consume())

    return ask, ask_timed, remaining, seen


def _piece(text):
    """造一枚真 ``StreamPiece``：收端认的就是它，不用假形状糊过去。"""
    now = time.monotonic()
    return nodes.StreamPiece(
        text=text, start_at=now - 0.01, end_at=now, source_fragments=3, emitted_at=now
    )


def _publish_all(sink, answer):
    for part in INCREMENTS:
        sink(_piece(part))


def _text_frames(body):
    """按出现顺序取出每一枚 ``event: text`` 的**原始帧字面**（判据③ 要逐字节比）。"""
    return [frame + "\n\n" for frame in body.split("\n\n") if frame.startswith("event: text")]


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

# ==================== 判据① 收端半：片到了就多发 ====================


def test_the_route_registers_a_piece_sink_with_the_run(monkeypatch, tmp_path):
    """收端必须真的把出口注册进本轮——判据⑥ 说的"注册即需流式"就是这一行注册出来的。"""
    ask, _ask_timed, _remaining, seen = _harness(monkeypatch, tmp_path, [ANSWER])
    ask()
    assert seen["kwargs"] == RUN_KWARGS, f"注册参数漂移：{seen['kwargs']}"
    assert callable(seen["sink"]), "SSE 出口没把片段出口传下去"


def test_the_receiver_and_the_producer_agree_on_the_sink_parameter():
    """两枚文件靠参数名对接：生产者改名而收端不报错，特性就静默失效，所以钉死。"""
    assert "stream_piece_sink" in inspect.signature(orchestrator.run_with_stream).parameters
    assert nodes.STREAM_PIECE_SINK_KEY == "stream_piece_sink"


def test_each_piece_becomes_its_own_text_frame(monkeypatch, tmp_path):
    ask, _ask_timed, remaining, _seen = _harness(
        monkeypatch, tmp_path, [ANSWER], publish=_publish_all
    )
    body = ask()
    payloads = _text_payloads(body)
    assert remaining == []
    assert len(payloads) == len(INCREMENTS) + 1, "判据①：三枚片 ⇒ 三枚片帧，外加收尾那枚不许消失的帧"
    names = _event_names(body)
    assert names.count("text") == len(INCREMENTS) + 1
    assert names.index("text") < names.index("request.completed"), "片不许迟到收尾之后才补发"


# ==================== 判据② 帧=累计、片=增量，逐字无损 ====================


def test_every_frame_carries_the_cumulative_prefix_of_the_answer(monkeypatch, tmp_path):
    ask, _ask_timed, _remaining, _seen = _harness(
        monkeypatch, tmp_path, [ANSWER], publish=_publish_all
    )
    contents = [payload["content"] for payload in _text_payloads(ask())]
    assert contents[-1] == ANSWER
    for previous, current in zip(contents, contents[1:]):
        assert current.startswith(previous), (
            f"每枚片必须携带截至该片的累计全文：{previous[-12:]!r} -> {current[:12]!r}"
        )
        assert len(current) >= len(previous)
    recombined = [contents[0]] + [c[len(p):] for p, c in zip(contents, contents[1:])]
    assert recombined == INCREMENTS + [""], "收端只做累加：帧间差必须逐字等于上游交来的片"
    assert "".join(recombined) == ANSWER, "无损：拼回去一个字不多一个字不少"


def test_the_last_piece_frame_and_the_done_frame_carry_the_same_text(monkeypatch, tmp_path):
    """判据③ 的共存面：收尾那枚不许消失 ⇒ 末片帧与它必然同文。前端 ``sessions.js`` 的
    ``state.segments.includes(chunk)`` 分支会把这枚重复帧静默丢掉，所以"多一枚"不会多一个字。"""
    ask, _ask_timed, _remaining, _seen = _harness(
        monkeypatch, tmp_path, [ANSWER], publish=_publish_all
    )
    contents = [payload["content"] for payload in _text_payloads(ask())]
    assert contents[-2] == contents[-1] == ANSWER
    assert len(contents) == len(set(contents)) + 1, "整条流里只许出现一次这种重复"


def test_a_whole_answer_with_no_pieces_still_issues_exactly_one_text_frame(monkeypatch, tmp_path):
    """反"硬切凑多发"的靶子：零片时多发一帧都是假的，多发十帧就是按标点切出来的。"""
    assert ANSWER.count("，") + ANSWER.count("；") >= 2, "题面得真带分隔符，否则这条钉在空转"
    ask, _ask_timed, _remaining, _seen = _harness(monkeypatch, tmp_path, [ANSWER])
    payloads = _text_payloads(ask())
    assert len(payloads) == 1, "整段答案、没有片，收端一个字都不许自己切"
    assert payloads[0]["content"] == ANSWER


def test_the_legacy_frame_sequence_survives_a_zero_piece_run(monkeypatch, tmp_path):
    """没有片时，帧名序列与改动前逐项相同（一枚不多、一枚不少）。"""
    ask, _ask_timed, _remaining, _seen = _harness(monkeypatch, tmp_path, [ANSWER])
    assert _event_names(ask()) == [
        "status",
        "request.started",
        "text",
        "request.completed",
        "sources",
        "done",
    ]


def test_one_oversized_piece_is_never_split_by_the_receiver(monkeypatch, tmp_path):
    """判据③ 的两把尺在上游 merger 里，收端不许再切一遍——切了就凭空造出短碎片。"""
    ask, _ask_timed, _remaining, _seen = _harness(
        monkeypatch, tmp_path, [ANSWER], publish=lambda sink, answer: sink(_piece(ANSWER))
    )
    contents = [payload["content"] for payload in _text_payloads(ask())]
    assert contents == [ANSWER, ANSWER]


# ==================== 判据③ done 那枚帧逐字节不变 ====================


def test_the_done_frame_is_byte_for_byte_the_frame_issued_before_r149(monkeypatch, tmp_path):
    """收尾帧的字面按 R35 之后的形状硬编码在这里，不经过被测代码构造，改形状必红。"""
    expected = (
        'event: text\ndata: {"type": "text", "content": '
        + json.dumps(ANSWER, ensure_ascii=False)
        + "}\n\n"
    )
    plain, _ask_timed, _remaining, _seen = _harness(monkeypatch, tmp_path, [ANSWER])
    assert _text_frames(plain())[-1] == expected, "零片那一道的收尾帧被改了"

    streamed, _ask_timed2, _remaining2, _seen2 = _harness(
        monkeypatch, tmp_path, [ANSWER], publish=_publish_all
    )
    assert _text_frames(streamed())[-1] == expected, "有片那一道的收尾帧被改了"


# ==================== 判据④ R35 三枚缓存字段：一轮之内每帧一致 ====================


def test_live_frames_never_carry_a_cache_mark(monkeypatch, tmp_path):
    ask, _ask_timed, _remaining, _seen = _harness(
        monkeypatch, tmp_path, [ANSWER], publish=_publish_all
    )
    payloads = _text_payloads(ask())
    assert len(payloads) > 1, "这条钉的前提是有片"
    key_sets = {tuple(sorted(payload)) for payload in payloads}
    assert key_sets == {("content", "type")}, (
        "实时那一轮按 R35 的既有裁定不许出现缓存键，片帧与收尾帧必须同一个键集合"
    )


def test_cache_fields_are_the_same_on_every_frame_within_a_turn(monkeypatch, tmp_path):
    """同一轮里"有的帧带、有的帧不带"就是 R150 画不出缓存那张脸的成因。"""
    ask, _ask_timed, remaining, _seen = _harness(monkeypatch, tmp_path, [ANSWER])

    live = _text_payloads(ask())
    assert remaining == [], "第一回合应当真的生成一次"
    assert all(field not in payload for payload in live for field in CACHE_FIELDS)

    hit = _text_payloads(ask())
    assert remaining == [], "第二回合应当命中缓存，一次都不生成"
    assert len(hit) == 1, "命中道是整段回读，不许被拆成片（拆它就是按标点硬切）"
    assert hit[0]["content"] == ANSWER
    assert hit[0]["cached"] is True
    assert hit[0]["cache_note"].startswith("缓存结果 · 生成于")
    assert "T" in hit[0]["cache_generated_at"]
    assert tuple(sorted(hit[0])) == (
        "cache_generated_at",
        "cache_note",
        "cached",
        "content",
        "type",
    )


# ==================== 判据⑤ 不引入节流：AST 面闸 + 因果时序 ====================


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _function_node(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到 {name}：出口被改名或内联就等于拔掉判据⑤ 的钉子")


def _piece_branch():
    tree = ast.parse(inspect.getsource(chat))
    ask_stream = _function_node(tree, "_ask_stream")
    branches = [
        node
        for node in ast.walk(ask_stream)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and _dotted(node.test.left) == "kind"
        and isinstance(node.test.comparators[0], ast.Constant)
        and node.test.comparators[0].value == "piece"
    ]
    assert len(branches) == 1, f"收端应当恰有一枚片分支，实到 {len(branches)} 枚"
    return branches[0]


def test_the_piece_branch_contains_no_sleep_or_throttle():
    """AST 面闸：片分支里只许出现 ``sleep(0)``（零延时让出）。任何非零延时、任何定时器、
    任何阻塞式 ``queue.get()`` 都是节流，判据⑤ 直接判负。"""
    branch = _piece_branch()
    delays = []
    for node in ast.walk(branch):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func)
        if name.endswith("sleep") or name.endswith("Timer") or name.endswith(".get"):
            argument = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
            delays.append((name, argument))
    assert all(delay == 0 for delay in [value for _name, value in delays]), (
        f"逐片发出这一支长出了节流：{delays}"
    )


def test_piece_frames_reach_the_wire_while_the_run_is_still_open(monkeypatch, tmp_path):
    """上游每片之间停 0.5 s：收端要是把片攒到收尾一起发，帧间距会全成 0；要是自己加了
    节流，帧间距会明显大于 0.5 s。两头都钉住才是"逐片直发"。"""
    hold = 0.5

    def publish(sink, answer):
        for part in INCREMENTS:
            sink(_piece(part))
            time.sleep(hold)

    ask, ask_timed, _remaining, _seen = _harness(
        monkeypatch, tmp_path, [ANSWER], publish=publish
    )
    out = ask_timed()
    text_times = [t for t, frame in out["frames"] if frame.startswith("event: text")]
    assert len(text_times) == len(INCREMENTS) + 1
    first_text_at = text_times[0]
    wall_seconds = out["wall"]
    assert first_text_at < wall_seconds - 0.5, (
        f"判据⑤：first_text_at={first_text_at:.2f} 必须显著早于 wall={wall_seconds:.2f}"
    )
    gaps = [later - earlier for earlier, later in zip(text_times, text_times[1:])]
    assert min(gaps) >= 0.4, f"片被攒成一坨同时发出：{[round(gap, 3) for gap in gaps]}"
    assert max(gaps) <= hold + 1.0, f"逐片之间长出了额外节流：{[round(gap, 3) for gap in gaps]}"


def test_the_piece_sink_stops_feeding_a_stream_nobody_reads(monkeypatch, tmp_path):
    """停止之后不再塞片：与 ("event", ...) 那一条同一裁定，收端自己也得守。

    只能盯队列：收尾循环每轮先查取消再取件，所以被丢掉的那枚片本来就永远到不了客户端，
    从帧面上看"少一帧"既可能是守卫起作用、也可能是取消检查抢先——那种断言不咬人。
    """
    import queue as queue_module

    fed = []

    class _SpyQueue(queue_module.Queue):
        def put(self, item, *_args, **_kwargs):
            fed.append(item)
            return super().put(item, *_args, **_kwargs)

    shim = type(
        "QueueShim",
        (),
        {"Queue": _SpyQueue, "Empty": queue_module.Empty},
    )()
    monkeypatch.setattr(chat, "qmod", shim)

    session = "sess-r149-stop"

    def publish(sink, answer):
        sink(_piece(INCREMENTS[0]))
        marker = chat.current_marker(session)
        assert marker is not None, "本轮没登记在飞运行，取消语义无从谈起"
        marker.set()
        sink(_piece(INCREMENTS[1]))

    ask, _ask_timed, _remaining, _seen = _harness(
        monkeypatch, tmp_path, [ANSWER], publish=publish
    )
    body = ask(session_id=session)
    assert "cancelled" in _event_names(body), "停止这一轮的收尾形状没走既有那条道"
    fed_pieces = [piece.text for kind, piece in fed if kind == "piece"]
    assert fed_pieces == [INCREMENTS[0]], (
        f"停止之后还在往没人读的流里塞片：{fed_pieces}"
    )


def test_the_identity_guard_still_emits_the_untouched_done_frame_and_logs(
    monkeypatch, tmp_path, caplog
):
    """片与终答不同源时的裁定：收尾帧一个字都不改（前端整段替换，终态永远对），但必须大声记账。

    R31 那枚 ``StreamPiece`` 只带文字与时间戳、**不带调用身份**，所以一旦生成腿改走流式，
    一轮里 planner/worker 的字都可能混进同一条累计串。收端救不了病因（那是腿改造单的硬
    前置），但绝不能让它静默。
    """
    noise = "这一句是规划器的口播，不是给客户看的答案，它绝不该出现在终答里。"
    ask, _ask_timed, _remaining, _seen = _harness(
        monkeypatch,
        tmp_path,
        [ANSWER],
        publish=lambda sink, answer: (sink(_piece(noise)), sink(_piece(INCREMENTS[0]))),
    )
    expected = (
        'event: text\ndata: {"type": "text", "content": '
        + json.dumps(ANSWER, ensure_ascii=False)
        + "}\n\n"
    )
    with caplog.at_level(logging.ERROR, logger="enterprise_brain"):
        body = ask()
    payloads = _text_payloads(body)
    assert payloads[0]["content"] == noise, "已经交出去的片收不回来，这一点不装"
    assert _text_frames(body)[-1] == expected, "守卫不许顺手改那枚不许变形状的收尾帧"
    logged = [record.message for record in caplog.records if "[R149]" in record.message]
    assert logged, "累计片与终答不同源必须留下一行 error，静默是最坏的选项"
    assert "pieces=2" in logged[0] and "cumulative=" in logged[0], logged[0]


# ==================== 判据③ 上游口径贯通：真 merger 的片穿过收端不变形 ====================


def test_the_idle_gate_from_r31_survives_the_sse_exit(monkeypatch, tmp_path):
    """用**真** ``StreamPieceMerger``（注入时钟，逐字到达）产出片，再让它们过一遍 SSE 出口：
    判据③ 的"非末片 ≥20 字、单字碎片 0"必须在帧间差上原样成立——收端一变形就红。"""
    tick = {"n": 0}

    def clock():
        tick["n"] += 1
        return tick["n"] * 0.011  # ≈91 字/s，与 R31 真机实测的解码速度同量级

    merger = nodes.StreamPieceMerger(clock=clock)
    pieces = []
    for character in ANSWER:
        pieces.extend(merger.feed(character))
    pieces.extend(merger.finish())

    assert pieces, "merger 没出片说明前提塌了"
    increments = [piece.text for piece in pieces]
    assert "".join(increments) == ANSWER, "G1 无损"
    for piece in pieces[:-1]:
        assert len(piece.text) >= nodes.STREAM_PIECE_MIN_CHARS, (
            f"非末片 {len(piece.text)} 字，没过尺寸闸"
        )
    assert all(len(piece.text) != 1 for piece in pieces), "单字碎片"
    for earlier, later in zip(pieces, pieces[1:]):
        assert earlier.end_at <= later.start_at, "G2 时间戳重叠"

    def publish(sink, answer):
        for piece in pieces:
            sink(piece)

    ask, _ask_timed, _remaining, _seen = _harness(
        monkeypatch, tmp_path, [ANSWER], publish=publish
    )
    contents = [payload["content"] for payload in _text_payloads(ask())]
    deltas = [contents[0]] + [c[len(p):] for p, c in zip(contents, contents[1:])]
    assert deltas == increments + [""], "收端把上游的片切开或合并了"
    assert len(contents) == len(pieces) + 1