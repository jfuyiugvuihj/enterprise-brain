# -*- coding: utf-8 -*-
"""R210 判据 2/5：断流轮的「离线话术」必须作为一次**纠正替换**上屏，不许接在半截真话后面。

形状的来历（R203 交底、总控 §93.13 立案）：doc/data/chart 三条生成腿改走流式之后，provider
死在半路、而此前已经交出 >=1 片，那一轮的终答会换成一句预制话术。那句话不是刚才那半截字
的延伸，所以旧形状下收尾帧会落进 ``frontend/src/lib/sessions.js:491`` 的**追加**分支，用户
读到「半截真话 + 离线话术」拼成的一句。改前 pieces 恒 0，这一格结构上到不了。

本件不抄 R203 的断言，只借它的办法：**帧是真的从真 /ask 上流出来的**（真 _ResilientModel +
真 _AnswerPieceTap + 真收端折帧），假的只有 orchestrator 那一层与那台半路断流的 provider；
屏上读数是把流里真到的帧按 sessions.js 的分支**逐帧复算**出来的，不是照抄后端字段。

判据对应：2 = ``_fold_like_the_browser`` 之后屏上正文恰等于离线话术、不含半截真话、
``doubled == 0`` 且 ``started == 1``；5 = 正常轮（不断流）整条流的字面与摘掉守卫时逐字节相同。

🔴 判据 1（帧账 ``prefix_breaks`` 回到 0）本件做不到，理由与实测读数钉在
``tests/test_r210_frame_ledger_of_a_broken_round.py``，不在这里含糊带过。
"""

import asyncio
import json

import httpx
import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.agents import nodes
from app.agents.contracts import ModelTier
from app.api.v1 import chat
from app.common import model_budget
from app.common.model_budget import model_tier_budget

from tests.test_r203_sse_progressive_frames import (  # noqa: F401  -- 同一条链，不造第二份
    QUESTION,
    _answer_frames,
    _http_request,
    ruler,
)

#: provider 死在半路之前，这一题的正文至少要写出这么多字，才谈得上「已发 >=1 片」。
STREAMED_ANSWER = (
    "一线城市住宿费为每晚 500 元，凭发票按实际发生额报销；"
    "二三线城市住宿费为每晚 350 元，超标部分需要部门负责人签字确认之后才可以入账。"
    "交通费用按高铁二等座实名票据据实报销，市内打车一个月封顶三百元，超出部分由本人承担。"
    "餐饮补助按出差自然日计算，每天一百元，不需要发票，也不需要事前申请，直接随差旅单一并递交。"
)
#: 留这么多枚流帧再断：实测（本文件 ``test_the_break_shape_actually_streams_at_least_one_frame``）
#: 这个断点上一片已经交出去并折成帧，而正文远没写完 —— 正是「半截真话」那一格。
DIE_AFTER_FRAMES = 10


# ==================== 真 /ask + 真生成腿 + 半路断流的 provider ====================


def _broken_leg(text, die_after, sink, worker):
    """真 :class:`nodes._ResilientModel` 打上一台会中途断流的 provider。

    死后由 ``_OfflineModel`` 顶上一句预制话术 —— 这条回退道是今天的真码，本单一个字没改。
    """

    def handler(request: httpx.Request) -> httpx.Response:
        keep = _answer_frames(text)[:die_after]
        payload = "".join("data: " + json.dumps(f, ensure_ascii=False) + "\n\n" for f in keep)
        # 断法与 R203 answer_leg_streams 同一枚：结尾是一枚被截断的残帧，客户端当场抛
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(payload + 'data: {"broken\n\n').encode("utf-8"),
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
    model = nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="fake",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.ANALYSIS),
    )
    configurable = {
        "worker": worker,
        "request_id": "request-r210",
        "trace_id": "trace-r210",
    }
    if sink is not None:
        configurable[nodes.STREAM_PIECE_SINK_KEY] = sink
    return model.invoke([HumanMessage(content=QUESTION)], config={"configurable": configurable})


def _round(monkeypatch, tmp_path, legs, *, die_after=DIE_AFTER_FRAMES):
    """跑一轮真 /ask，返回 ``(整条 SSE 字面, 腿交回的答案)``。

    ``legs`` 是 ``[(worker, answer_or_None)]``：answer 给 ``None`` 表示这一发会中途断流并
    由离线话术顶上，否则它一路流到底。除 orchestrator 之外全链真码（与 R203 同一分工）。
    """
    from app.common import cache
    from app.storage.sessions import SessionRegistry

    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())

    handed_back = {}

    def fake_stream(*_args, **kwargs):
        sink = kwargs.get("stream_piece_sink")
        results = {}
        for worker, answer in legs:
            if answer is None:
                message = _broken_leg(STREAMED_ANSWER, die_after, sink, worker)
            else:
                message = _clean_leg(answer, sink, worker)
            # 落进 worker_results 的必须是**腿真交回的那句**：断流轮它就是离线话术，
            # 不是任何人在收端重新拼出来的东西。
            results[worker] = str(getattr(message, "content", "") or "")
            handed_back[worker] = results[worker]
            yield {
                "messages": [],
                "worker_results": dict(results),
                "final_answer": "\n\n".join(results.values()),
            }

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    saves = []
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: saves.append(_a))
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _s, m: m)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(
        chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)})
    )
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    def ask(message=QUESTION, session_id="sess-r210"):
        response = asyncio.run(
            chat.ask(
                chat.AskRequest(message=message, session_id=session_id),
                http_request=_http_request(),
            )
        )

        async def consume():
            chunks = [c async for c in response.body_iterator]
            return "".join(c.decode("utf-8") if isinstance(c, bytes) else c for c in chunks)

        return asyncio.run(consume())

    ask.saves = saves
    ask.handed_back = handed_back
    return ask


def _clean_leg(text, sink, worker):
    def handler(request: httpx.Request) -> httpx.Response:
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
    model = nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="fake",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.ANALYSIS),
    )
    configurable = {
        "worker": worker,
        "request_id": "request-r210",
        "trace_id": "trace-r210",
    }
    if sink is not None:
        configurable[nodes.STREAM_PIECE_SINK_KEY] = sink
    return model.invoke([HumanMessage(content=QUESTION)], config={"configurable": configurable})


# ==================== 线上字面 -> (name, payload) 序列 ====================


def _wire(body):
    """按到达顺序吐出 ``(事件名, data 载荷)``。屏上复算吃的就是这份，不做任何加工。"""
    frames = []
    for frame in body.split("\n\n"):
        if not frame:
            continue
        name = frame.split("\n", 1)[0].removeprefix("event: ")
        try:
            payload = json.loads(frame.split("data: ", 1)[1])
        except (IndexError, ValueError):
            payload = {}
        frames.append((name, payload))
    return frames


def _text_contents(body):
    return [str(payload.get("content") or "") for name, payload in _wire(body) if name == "text"]


# ==================== 屏上复算：逐帧走 sessions.js 的分支 ====================


def _fold_like_the_browser(frames):
    """把真到达的帧按 ``frontend/src/lib/sessions.js`` 的分支逐帧复算一遍。

    与 R203 那枚 ``_fold_like_the_browser`` 的分工：它只折 ``text`` 的三条给字分支，因为
    今天没有任何一轮会走到 ``_correcting``；本单动的**就是**那一格，所以这里必须把
    ``step`` 也喂进去 —— ``step(status=running)`` 在 ``msg.content`` 非空时置
    ``_correcting``（:513），紧跟着的那枚 text 帧整段替换屏上正文（:482）。分支条件与
    赋值逐字对齐源码，不自创语义：``doubled`` = 有正文时又走了一次追加，``started`` =
    屏上还没有正文时走了追加，``replaced`` = 走了 ``_correcting`` 整段替换，
    ``covered`` = 走了 covering 整段替换，``ignored`` = 重复帧被丢掉，
    ``open_steps`` = 收帧时还在转圈的步骤数。
    """
    content = ""
    segments: list[str] = []
    correcting = False
    steps: list[dict] = []
    doubled = started = replaced = covered = ignored = 0
    for name, payload in frames:
        if name == "text":
            chunk = payload.get("content")
            chunk = "" if chunk is None else str(chunk)
            if not chunk:
                ignored += 1
                continue
            if correcting:
                content = chunk
                correcting = False
                segments = [chunk]
                replaced += 1
            elif chunk in segments:
                ignored += 1
            else:
                covering = next((seg for seg in segments if seg in chunk and chunk != seg), None)
                if covering is not None:
                    content = chunk
                    segments = [chunk]
                    covered += 1
                else:
                    if content:
                        doubled += 1
                    else:
                        started += 1
                    content = f"{content}{chunk}"
                    segments = [*segments, chunk]
        elif name == "step":
            running = payload.get("status") == "running"
            existing = next(
                (s for s in steps if s["tool"] == payload.get("tool") and s["status"] == "running"),
                None,
            )
            if existing is not None and not running:
                existing["status"] = "done"
                existing["elapsed"] = payload.get("elapsed")
            elif running:
                if content:
                    correcting = True
                steps.append(
                    {"tool": payload.get("tool"), "label": payload.get("label"),
                     "status": "running", "elapsed": None}
                )
            elif payload.get("tool"):
                steps.append(
                    {"tool": payload.get("tool"), "label": payload.get("label"),
                     "status": payload.get("status") or "done", "elapsed": None}
                )
    return {
        "content": content,
        "segments": segments,
        "doubled": doubled,
        "started": started,
        "replaced": replaced,
        "covered": covered,
        "ignored": ignored,
        "open_steps": sum(1 for s in steps if s["status"] == "running"),
    }


@pytest.fixture()
def broken_round(monkeypatch, tmp_path):
    """一真轮：doc 腿流到半路 provider 死掉，终答换成离线话术。"""
    ask = _round(monkeypatch, tmp_path, [("doc", None)])
    body = ask()
    return body, _text_contents(body), ask


def test_the_break_shape_actually_streams_at_least_one_frame(broken_round):
    """先钉形状：这一轮真的流出了 >=1 枚半截帧，且收尾帧是离线话术。

    这一枚不是判据，是判据的地基 —— 形状没构造成功，后面所有断言都是在给自己壮胆。
    """
    _body, contents, _ask = broken_round

    assert len(contents) >= 2, f"这一轮没流起来（帧数={len(contents)}），断流形状无从谈起"
    assert nodes.is_offline_reply_text(contents[-1]), "收尾那帧不是离线话术：形状不对"
    # 半截帧是模型写的真话，既不是离线话术的开头，也不该被当成答案留在屏上。
    assert not contents[-1].startswith(contents[0])
    # 首帧是模型真写出去的半截正文，不是预制话术：这一格的「半截」是真的半截。
    assert not nodes.is_offline_reply_text(contents[0]), "首帧不是模型真写的正文，形状换了"
    assert contents[0] in STREAMED_ANSWER, "首帧不是那条真正文的开头若干字"


def test_the_screen_shows_the_offline_reply_alone_not_joined_to_the_half_truth(broken_round):
    """判据 2：屏上正文**等于**离线话术本身，不含半截真话的残留。"""
    body, contents, _ask = broken_round

    rendered = _fold_like_the_browser(_wire(body))
    assert rendered["content"] == contents[-1], rendered
    assert rendered["content"] == _ask.handed_back["doc"]
    assert contents[0] not in rendered["content"], "半截真话还挂在屏上"
    assert rendered["doubled"] == 0, f"屏上被追加成了两份：{rendered}"
    assert rendered["started"] == 1, f"第一枚片帧没按应有那条路上屏：{rendered}"
    assert rendered["replaced"] == 1, f"收尾那一帧没走整段替换：{rendered}"


def test_the_correction_is_carried_by_the_existing_step_semantics_only(broken_round):
    """守卫只借既有 step 语义：不新增帧键、不改 text 帧形状、不动 legacy 事件名。"""
    body, _contents, _ask = broken_round

    wire = _wire(body)
    names = [name for name, _payload in wire]
    assert "answer_correction" not in names, "纠正不许长出一枚新事件名，它走的是既有 step"
    # text 帧的键集合仍然是 R149 钉的那一份：type/content（命中道另带缓存三枚，这里没命中）。
    for name, payload in wire:
        if name == "text":
            assert set(payload) == {"type", "content"}, payload
    # 纠正那两枚 step 用的仍是 step 词汇表里的既有四键，且 running 紧贴在收尾帧之前。
    steps = [payload for name, payload in wire if name == "step" and payload.get("tool") == "answer_correction"]
    assert [s.get("status") for s in steps] == ["running", "done"], steps
    for step in steps:
        assert set(step) <= {"type", "tool", "label", "status", "elapsed"}, step
    index_of_final_text = max(i for i, (name, _p) in enumerate(wire) if name == "text")
    assert wire[index_of_final_text - 1][0] == "step", "收尾帧前面那枚不是武装替换的 step"
    assert wire[index_of_final_text - 1][1].get("status") == "running"


def test_the_correction_leaves_no_step_spinning_on_the_panel(broken_round):
    """那两枚 step 自己收口：界面不许留一枚永远转圈的步骤。"""
    body, _contents, _ask = broken_round

    assert _fold_like_the_browser(_wire(body))["open_steps"] == 0


def test_the_history_row_is_still_the_offline_reply_written_once(broken_round):
    """账上不变：会话历史仍然只有一行 assistant，内容仍是终答本身。"""
    _body, contents, ask = broken_round

    assistant_rows = [call for call in ask.saves if len(call) >= 2 and call[1] == "assistant"]
    assert len(assistant_rows) == 1, [call[1:3] for call in assistant_rows]
    assert assistant_rows[0][2] == contents[-1]


def _readings(body):
    """把这条流的 text 帧喂进评分器那把尺，取回这一题的帧账读数。"""
    out = ruler._blank_observation("sess-r210")
    for content in _text_contents(body):
        ruler._count_text_frame(out, content)
        if content:
            out["answer"] = content
    ledger = ruler._fold_frames(ruler._new_frame_ledger(), out)
    return ruler._frame_readings(ledger, out["answer"])


def _correction_steps(body):
    return [
        payload
        for name, payload in _wire(body)
        if name == "step" and payload.get("tool") == "answer_correction"
    ]


def test_a_normal_round_does_not_grow_a_single_frame(monkeypatch, tmp_path):
    """判据 5：provider 一路流到底的那一轮，多发零枚帧、收尾帧字面逐字节等于今天。

    这里不比两次运行的整条字面 —— ``request_id``/``trace_id``/``timestamp`` 每轮都换，
    比出来只会红在无关格上。要比的是三件能落地的：纠正帧一枚都不许多、收尾那枚帧的
    字节面就是 ``text_sse_frame(终答)`` 本身、帧账两枚读数仍然恒 0。
    """
    ask = _round(monkeypatch, tmp_path, [("doc", STREAMED_ANSWER)])
    body = ask()

    assert _correction_steps(body) == [], "正常轮多发了一枚纠正帧"
    names = [name for name, _payload in _wire(body)]
    assert names.count("step") == 0, f"正常轮不该出现任何 step 帧：{names}"
    # 逐字节：收尾那枚帧的字面 == 构造器给今天那一份的字面，一个字节都没多。
    assert chat.text_sse_frame(STREAMED_ANSWER, None) in body
    assert _text_contents(body)[-1] == STREAMED_ANSWER

    readings = _readings(body)
    assert readings["prefix_breaks"] == 0, readings
    assert readings["extra_chars"] == 0, readings
    assert readings["answer_sha"] == ruler._sha12(STREAMED_ANSWER), readings


def test_the_guard_is_inert_unless_the_round_actually_breaks():
    """静态钉：那道守卫只挂在「不同源」那一格里，两处多发帧都受同一枚标记门控。

    判据 5 的另一半不能只靠一条用例跑到的形状来保证 —— 得钉住码本身：全仓 ``= True``
    只此一处，且它左边就是那条前缀判据；两处 ``step`` 出口都写在 ``if answer_needs_correction``
    底下。谁把守卫挪到别处（比如无条件发），本枚当场红。
    """
    import inspect
    import re

    source = inspect.getsource(chat.ask)
    arms = re.findall(r"answer_needs_correction = True", source)
    assert len(arms) == 1, f"守卫置真的地方应当只有一处，实到 {len(arms)}"

    lines = source.splitlines()
    guard_at = next(
        index for index, line in enumerate(lines)
        if "if cumulative_text and not full_text.startswith(cumulative_text):" in line
    )
    indent = len(lines[guard_at]) - len(lines[guard_at].lstrip())
    body = []
    for line in lines[guard_at + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    assert any("answer_needs_correction = True" in line for line in body), (
        "置真那一行不在「不同源」判据的函数体里：守卫被挪到别处了"
    )

    lines = source.splitlines()
    # 纠正帧那两枚载荷都从同一份 correction 字典长出来：tool 只此一处定义。
    assert sum(1 for line in lines if "CORRECTION_STEP_TOOL" in line) == 1, (
        "纠正帧的 tool 只许在一处定义，两枚出口共用同一份载荷"
    )
    gates = [index for index, line in enumerate(lines) if line.strip() == "if answer_needs_correction:"]
    assert len(gates) == 2, f"两枚出口各自受一道门，实到 {len(gates)} 道"
    emits = [index for index, line in enumerate(lines) if 'sse_event("step"' in line]
    assert len(emits) == 2, f"受门控的纠正帧出口应当两枚，实到 {len(emits)}"
    for emit in emits:
        previous = next(
            lines[back].strip() for back in range(emit - 1, -1, -1) if lines[back].strip()
        )
        assert previous == "if answer_needs_correction:", (
            f"有一枚纠正帧出口没受门：它上面是 {previous!r}"
        )


def test_the_frontend_branches_this_fix_rests_on_are_still_on_disk():
    """承重的那三条前端分支还在原处：它们一动，本文件的屏上复算就该重审。"""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib" / "sessions.js"
    ).read_text(encoding="utf-8")
    backtick = chr(96)

    # _correcting 整段替换（:482 那一格），以及 step(running) 武装它的那一行（:513）。
    assert "if (msg._correcting) {" in source, "整段替换那格不见了"
    assert "msg.content = chunk" in source, "整段替换不再直取帧正文"
    assert "if (msg.content) msg._correcting = true" in source, "step 不再武装替换：守卫落空"
    assert (
        "msg.content = " + backtick + "${msg.content || ''}${chunk}" + backtick
    ) in source, "追加分支还在：那就必须保证这一轮走不到它"
