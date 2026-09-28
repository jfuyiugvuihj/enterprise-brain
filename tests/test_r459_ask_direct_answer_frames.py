# -*- coding: utf-8 -*-
"""R459 判据①②④ 的收端半边：直答那一轮在在册量具上读成多帧，且末帧覆盖全文。

复现的是 run9 里那八枚「主 Agent 自己回答、一次算完整段再交出来」的题号
（``doc-07 chat-03 chat-06 chat-09 chat-10 metric-16 approval-06 scope-01``，正文逐字取自在册
产物 ``docs/testing/answers-run9.jsonl``，只读不改），打的仍是真 ``/api/v1/ask`` 路由
（``TestClient``，进程内 ASGI，不开端口），量的是**在册量具自己那把尺**
（``scripts/eval_transport_ask_v2.py`` 的 ``_blank_observation``／``_consume``／``_fold_frames``／
``_frame_readings``／``_frame_verdict``，importlib 现场加载，一个字不改）。

判据按收端 :meth:`app.api.v1.chat._AnswerPieceStream.frame_for` 那三条规则写成断言（本单一行
都不裁，也不改它的字面）：

1. **同一发调用才累计**（``call_id`` 换腿必须等前一腿落进 ``worker_results``）——本单的直答
   轮只有一条 ``supervisor`` 腿 ⇒ 钉 ``streams == 1``、``prefix_breaks == 0``。
2. **帧正文 = 已落定的答案 + 本发已经写出的字** ⇒ 每一枚帧天然还是终答的前缀；直答轮的终答
   就是 supervisor 那一发的正文，且它永远不进 ``worker_results`` ⇒ 钉帧是单调前缀链、
   ``last_frame_covers_answer is True``、``missing_chars == extra_chars == 0``。
3. **只在新帧真的变长时才发** ⇒ 片与帧一一对应，一枚都不许多、一枚都不许少；钉
   ``text_frames == 片数 + 1``（那枚 1 是收尾帧），收尾帧与末帧逐字同文 ⇒ 正文不会出两遍。

与 R456 那三枚在册钉的分工：那一单钉「单片形状必须判不过」，本单钉「接上片段出口之后同一枚
形状读成过」，两单共用一把尺 ⇒ 谁放宽口径都会在对方身上露馅。

全程离线：假 provider（``httpx.MockTransport``，base_url 指向 127.0.0.1:9）、假编排线程、零模型、
零服务、零容器。🔴 反证钉的「漂移」一律造在内存影子副本（``_shadow``）里，被跟踪文件一字节不改。
"""
import contextlib
import importlib.util
import json
import time
from collections import Counter
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage

from app.agents import nodes, orchestrator
from app.agents.contracts import ModelTier, Principal
from app.common.model_budget import model_tier_budget
from app.storage.sessions import SessionRegistry
from tests.test_approve_canonical_events import _patch_offline
from tests.test_r459_supervisor_answer_leg_streams import (  # noqa: F401  复用同一套假 provider
    DISABLE,
    GAP_SECONDS,
    GUARD_DISPATCH,
    GUARD_LEDGER,
    GUARD_SINK,
    QUESTION,
    TAP_HEAD,
    UNPLUG,
    _client,
    _dispatched_state,
    _ledger_only_state,
    _OfflineReply,
    _offline_ledger,
    _provider_handler,
    _round_config,
    _shadow,
    _text_frames,
)

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "r459_frame_ruler", _ROOT / "scripts" / "eval_transport_ask_v2.py"
)
ruler = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ruler)

SESSION_ID = "r459-direct-answer"

#: run9 里那八枚「主 Agent 自己写完整段再交出来」的题号。``data-09`` 不在此列——那一枚卡的是
#: 工具之后的汇总那一发，本单的前置②③明写不接那一发（取证单 §10 锚点 1 只算八枚）。
ONE_SHOT_IDS = (
    "doc-07",
    "chat-03",
    "chat-06",
    "chat-09",
    "chat-10",
    "metric-16",
    "approval-06",
    "scope-01",
)


def run9_answer(question_id: str) -> str:
    """从在册产物里取那一枚题号当天交回的正文（只读，一字不改）。"""
    rows = [
        json.loads(line)
        for line in (_ROOT / "docs" / "testing" / "answers-run9.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    by_id = {row.get("id"): row for row in rows}
    assert question_id in by_id, f"{question_id} 不在 answers-run9 里：夹具前提变了"
    answer = str(by_id[question_id]["answer"])
    assert len(answer) >= 2 * nodes.STREAM_PIECE_MIN_CHARS, (question_id, len(answer))
    return answer


# ==================== 假编排线程：走的是真 main_agent_node ====================


def direct_answer_driver(answer: str, *, record=None):
    """替掉 ``run_with_stream``：本轮注册出口，然后**真跑** supervisor 那一发，再交终答。

    复刻取证单 §2.1 那条链的 4→8 环：直答那一发不带 dispatch ⇒ ``route_main`` 交回 reflect
    （派发集合为空）⇒ 一个 worker 都没跑 ⇒ ``worker_results`` 为空、``final_answer`` 就是
    supervisor 写的那整段。差别只有一件：那一现在有挂着 tap，字是一边生成一边进出口的。
    """

    def stream(*_args, **kwargs):
        downstream = kwargs["stream_piece_sink"]
        sink = downstream
        arrivals = []
        piece_texts = []
        if record is not None:
            def timed(piece, _downstream=downstream):
                """在收端出口收到这一片的那一刻记一笔时间。

                🔴 ``_downstream`` 必须用默认参数绑死：写成闭包里的 ``sink(piece)`` 就是一枚
                自递归（下一行才把 ``sink`` 改名成 ``timed``），量到的不是片到达次数而是
                递归深度——本单栽过一次，读出 15696 次，正是 ``[R31] 出口抛错已忽略`` 那一形。
                """
                arrivals.append(time.monotonic())
                piece_texts.append(str(getattr(piece, "text", "")))
                _downstream(piece)

            sink = timed
        bodies = []
        model = nodes._ResilientModel(
            _client(_provider_handler(bodies, _text_frames(answer, usage=None))),
            _OfflineReply(),
            provider="local-openai-compatible",
            model_name="fake",
            capacity_wait_seconds=0,
            budget=model_tier_budget(ModelTier.ANALYSIS),
        )
        with _patched_main_model(model):
            update = orchestrator.main_agent_node(
                {"messages": [_human(QUESTION)], "plan": [], "memory": {}},
                _round_config(sink),
            )
        message = update["messages"][0]
        if record is not None:
            record["bodies"] = bodies
            record["arrivals"] = list(arrivals)
            record["piece_texts"] = list(piece_texts)
            record["terminal_yielded_at"] = time.monotonic()
        yield {
            "messages": [message],
            "worker_results": {},
            "final_answer": message.content,
        }

    return stream


@contextlib.contextmanager
def _patched_main_model(model):
    original = orchestrator.main_model
    orchestrator.main_model = model
    try:
        yield
    finally:
        orchestrator.main_model = original


def _increments(text, size=26):
    return [text[start:start + size] for start in range(0, len(text), size)]


def _stamped_piece(text, *, call_id, worker, seconds_ago=0.0):
    now = time.monotonic() - seconds_ago
    return nodes.StreamPiece(
        text=text,
        start_at=now - 0.01,
        end_at=now,
        source_fragments=len(text),
        emitted_at=now,
        call_id=call_id,
        worker=worker,
    )


def _human(text):
    return HumanMessage(content=text)


def ask_body(monkeypatch, tmp_path, stream, *, session_id: str = SESSION_ID,
             message: str = QUESTION) -> str:
    """把 /api/v1/ask 挂到假编排上，经 TestClient 取整条 SSE 字面（与 R456 同一条路）。"""
    from fastapi.testclient import TestClient

    from app.common.auth import create_token, get_user
    from app.api.v1 import chat
    from app.main import app

    _patch_offline(monkeypatch, tmp_path, stream, None)
    assert get_user("admin"), "夹具要用的 admin 必须能离线解析出来"
    registry = SessionRegistry(tmp_path / "r459-sessions.json")
    registry.bind(session_id, Principal.from_user(get_user("admin")))
    chat.session_registry = registry

    client = TestClient(app)
    response = client.post(
        "/api/v1/ask",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
        json={"message": message, "session_id": session_id},
    )
    assert response.status_code == 200, response.text
    return response.text


def _event_names(body: str) -> list:
    return [
        frame.split("\n", 1)[0].removeprefix("event: ")
        for frame in body.split("\n\n")
        if frame
    ]


def _text_payloads(body: str) -> list:
    return [
        json.loads(frame.split("data: ", 1)[1])
        for frame in body.split("\n\n")
        if frame.startswith("event: text")
    ]


def read_with_registered_ruler(body: str, session_id: str = SESSION_ID):
    out = ruler._blank_observation(session_id)
    lines = iter([chunk.encode("utf-8") for chunk in body.splitlines(keepends=True)])
    ruler._consume(lines, out)
    ledger = ruler._fold_frames(ruler._new_frame_ledger(), out)
    return out, ruler._frame_readings(ledger, out["answer"])


def _install_frame_accounting(monkeypatch, record):
    """在三层各拦一手读数：片进没进出口、片喂没喂进折帧、帧写没写进 SSE。

    🔴 三层全部包在 ``app/api/v1/chat.py`` 的**模块对象**上（``monkeypatch`` 用完即退，
    盘上一字节不改）。这一层就是"屏幕"跟前的一层：片在这里进队，帧在这里成形。
    """
    from app.api.v1 import chat

    original_stream = chat._AnswerPieceStream
    original_text_frame = chat.text_sse_frame
    record.setdefault("frame_calls", [])       # 收侧：(片文字, 折出来的帧或 None)
    record.setdefault("frames_written", [])    # 屏前：真写进 SSE 的 text 帧正文
    record.setdefault("streams", [])           # 本轮折帧器实例（closed/dropped 在它身上）

    class _AccountingStream(original_stream):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            record["streams"].append(self)

        def frame_for(self, piece, worker_results):
            frame = super().frame_for(piece, worker_results)
            record["frame_calls"].append((str(getattr(piece, "text", "")), frame))
            return frame

    def counting_text_frame(content, cache_fields=None):
        record["frames_written"].append(content)
        return original_text_frame(content, cache_fields)

    monkeypatch.setattr(chat, "_AnswerPieceStream", _AccountingStream)
    monkeypatch.setattr(chat, "text_sse_frame", counting_text_frame)


# ==================== 判据①：同一枚尺上，八枚夹具全部读成多帧 ====================


@pytest.mark.parametrize("question_id", ONE_SHOT_IDS)
def test_the_direct_answer_round_reads_more_than_one_text_frame(monkeypatch, tmp_path,
                                                                question_id):
    """判据①②：``text_frames > 1``、末帧覆盖全文、不缺字、不多字、不断流。

    这一枚就是「摘掉接驳当场红」的主钉：接驳一拆，``text_frames`` 立刻回到 1（那枚负对照
    的读数是 ``test_unplugging_the_coupling_reads_back_as_the_registered_single_frame_shape``），
    尺上的说法就是 R456 钉在册上的那种"单片形状"。
    """
    answer = run9_answer(question_id)
    body = ask_body(
        monkeypatch, tmp_path, direct_answer_driver(answer),
        session_id=f"{SESSION_ID}-{question_id}",
    )
    _out, readings = read_with_registered_ruler(body, session_id=f"{SESSION_ID}-{question_id}")

    assert readings["text_frames"] > 1, readings
    assert readings["max_stream_frames"] > 1, readings
    assert readings["streams"] == 1, readings
    assert readings["missing_chars"] == 0, readings
    assert readings["extra_chars"] == 0, readings
    assert readings["prefix_breaks"] == 0, readings
    assert readings["uncorrected_breaks"] == 0, readings
    assert readings["last_frame_covers_answer"] is True, readings
    assert ruler._frame_verdict(readings) is True, readings
    assert _out["answer"] == answer, _out["answer"][:40]


@pytest.mark.parametrize("question_id", ONE_SHOT_IDS[:3])
def test_the_frames_are_a_monotone_prefix_chain_and_the_close_repeats_nothing(
    monkeypatch, tmp_path, question_id
):
    """判据①② 的「正文不许重复出两遍」：帧是单调前缀链，收尾那一枚与末帧逐字同文。

    同文帧落进前端 ``sessions.js`` 的第一条分支（``segments.includes(chunk)`` 直接 ignored），
    所以屏上始终只有一份正文；``extra_chars == 0`` 是那件事在尺上的影子。
    """
    answer = run9_answer(question_id)
    body = ask_body(
        monkeypatch, tmp_path, direct_answer_driver(answer),
        session_id=f"{SESSION_ID}-chain-{question_id}",
    )
    frames = [payload["content"] for payload in _text_payloads(body)]

    assert len(frames) >= 2, frames
    assert all(later.startswith(earlier) for earlier, later in zip(frames, frames[1:])), frames
    assert frames[-1] == answer, frames[-1][:40]
    assert frames[-2] == frames[-1], (
        "末帧与收尾帧不同文：屏上会追加出第二份正文，本单不收这一形"
    )
    assert all(frame.count(answer) <= 1 for frame in frames), (
        "有一枚帧里同一段正文出现了两遍"
    )
    # 累计前缀链的「新增字数」合起来必须逐字等于正文一次：收尾那一枚新增 0 字。
    grown = frames[0] + "".join(
        later[len(earlier):] for earlier, later in zip(frames, frames[1:])
    )
    assert grown == answer, (len(grown), len(answer))


# ==================== 判据④：首片的读数（这一层量的是真路由） ====================


def test_the_first_frame_lands_well_before_the_round_closes(monkeypatch, tmp_path):
    """判据④：「转圈转到最后一次性砸出」在这一格上装不出来——片数、间隔、帧账三样都要读数。

    🔴 说清在哪一层量的、怎么拦的（三层都包在 ``app/api/v1/chat.py`` 的模块对象上，
    ``monkeypatch`` 用完即退，盘上一字节不改）：

    * ``arrivals``／``piece_texts``：**生产侧**。驱动器把 ``run_with_stream`` 收到的那枚
      ``stream_piece_sink``（它就是 ``chat._piece_sink``）包一层计时，记的是出口收到这一片
      的那一刻、以及交出去的是哪一段字。
    * ``frame_calls``：**收侧**。包 ``chat._AnswerPieceStream.frame_for``，记的是这片有没有
      喂进折帧、折出来是一枚帧还是 ``None``（``None`` 就是收端把这片刻掉了）。
    * ``frames_written``：**屏前**。包 ``chat.text_sse_frame``，记的是真写进 SSE 的 text 帧。

    ``terminal_yielded_at`` 是同一枚假编排线程交出终答 state 的那一刻。收端脚本里的
    ``first_visible_ms`` 在这一枚夹具上不可用——``TestClient`` 把整条响应先缓存完，尺读到的
    是它自己消费的时钟，不是服务器的时钟，所以本单不拿它当证据。
    """
    answer = run9_answer("chat-09")
    record = {}
    _install_frame_accounting(monkeypatch, record)
    body = ask_body(
        monkeypatch, tmp_path, direct_answer_driver(answer, record=record),
        session_id=f"{SESSION_ID}-timing",
    )
    names = _event_names(body)
    arrivals = record["arrivals"]
    frame_calls = record["frame_calls"]
    frames_written = record["frames_written"]

    # ① 片数：出口至少两片，而且一片不落地全部喂进了折帧这一层。
    assert len(arrivals) >= 2, f"出口只收到 {len(arrivals)} 片：那一腿根本没接上"
    assert len(frame_calls) == len(arrivals), (len(frame_calls), len(arrivals))
    assert [text for text, _frame in frame_calls] == record["piece_texts"], (
        "收端喂进折帧的片与生产侧交出的片不是同一批"
    )

    # ② 间隔：首片与次片之间隔得出时间，并且至少一段是真正的生成间隔。
    gaps = [later - earlier for earlier, later in zip(arrivals, arrivals[1:])]
    assert gaps and gaps[0] > 0, f"首片与次片之间隔不出时间：{[round(g, 4) for g in gaps[:6]]}"
    assert max(gaps) >= GAP_SECONDS, (round(max(gaps), 4), GAP_SECONDS)

    # ③ 首片早于收窗一整段生成，末片也早于收窗：那一发不是收尾补发。
    assert record["terminal_yielded_at"] - arrivals[0] >= GAP_SECONDS, (
        f"首片距收窗只隔了 {record['terminal_yielded_at'] - arrivals[0]:.3f}s：那是收尾补发"
    )
    assert arrivals[-1] <= record["terminal_yielded_at"] + GAP_SECONDS, arrivals[-1]

    # ④ 帧账对齐：收端一枚都没丢（closed/dropped 都是零），写进流的帧与折出来的帧同一批。
    piece_stream = record["streams"][0]
    assert piece_stream.dropped == 0 and piece_stream.closed is False, (
        piece_stream.dropped, piece_stream.closed
    )
    assert [frame for _text, frame in frame_calls] == frames_written[:-1], (
        len(frame_calls), len(frames_written)
    )
    assert len(frames_written) == len(arrivals) + 1 == names.count("text"), (
        len(arrivals), len(frames_written), names.count("text")
    )
    assert frames_written[0] != answer and answer.startswith(frames_written[0]), (
        "第一枚帧不是正文的严格前缀：那不是流式，那是收尾砸全文"
    )
    assert frames_written[-1] == answer, frames_written[-1][:40]

    # ⑤ 字面顺序：text 帧整段排在收窗之前，收窗只有一枚，且这一轮没有 error。
    assert max(index for index, name in enumerate(names) if name == "text") < names.index(
        "request.completed"
    ), "有一枚 text 帧排到了收窗之后"
    assert names.count("request.completed") == 1 and "error" not in names, Counter(names)


# ==================== 反证钉：②③ 两格前置在帧形上的后果 ====================


def two_leg_driver(answer, gate_state, record=None):
    """worker 腿先把它那份正文逐片交出去并落进账本，然后**真跑** supervisor 的汇总那一发。

    这一形是 run9 ``data-09`` 的邻居：那一发的正文不是终答的前缀（终答由 synthesize 从
    ``worker_results`` 折出来），所以本单的前置②③必须把它挡在出口外。挡住了 ⇒ 一条腿一枚链；
    摘掉 ⇒ 同一段正文在屏上出现两遍，而收尾那一帧与末帧不同源。
    """

    def stream(*_args, **kwargs):
        sink = kwargs["stream_piece_sink"]
        published = []
        for chunk in _increments(answer):
            piece = _stamped_piece(chunk, call_id="worker-call", worker="data")
            published.append(chunk)
            sink(piece)
        # 账本落定（真图里这是 worker 节点那一次 values 事件）
        yield {"messages": [], "worker_results": {"data": answer}, "final_answer": ""}
        bodies = []
        model = nodes._ResilientModel(
            _client(_provider_handler(bodies, _text_frames(answer, usage=None))),
            _OfflineReply(),
            provider="local-openai-compatible",
            model_name="fake",
            capacity_wait_seconds=0,
            budget=model_tier_budget(ModelTier.ANALYSIS),
        )
        with _patched_main_model(model):
            update = orchestrator.main_agent_node(gate_state(), _round_config(sink))
        if record is not None:
            record["summary_pieces"] = len(published)
            record["bodies"] = bodies
        yield {
            "messages": [update["messages"][0]],
            "worker_results": {"data": answer},
            "final_answer": answer,
        }

    return stream


def _frame_texts(body):
    return [payload["content"] for payload in _text_payloads(body)]


@pytest.mark.parametrize(
    "guard,needle,gate_state",
    [
        ("dispatch", GUARD_DISPATCH, _dispatched_state),
        ("ledger", GUARD_LEDGER, _ledger_only_state),
    ],
)
def test_the_two_gates_keep_the_answer_from_appearing_twice(
    monkeypatch, tmp_path, guard, needle, gate_state
):
    """原件：一条腿一条链、末帧覆盖全文。摘掉②或③：同一段正文在屏上出现两遍。

    影子只改内存里的函数对象（``_shadow``），被跟踪文件一字节不动。
    """
    answer = run9_answer("metric-16")
    session = f"{SESSION_ID}-{guard}"
    body = ask_body(monkeypatch, tmp_path, two_leg_driver(answer, gate_state), session_id=session)
    _out, readings = read_with_registered_ruler(body, session_id=session)
    frames = _frame_texts(body)

    assert readings["prefix_breaks"] == 0, readings
    assert readings["last_frame_covers_answer"] is True, readings
    assert readings["streams"] == 1, readings
    assert all(frame.count(answer) <= 1 for frame in frames), frames

    _shadow(monkeypatch, "_supervisor_answer_tap", [(needle, DISABLE)])
    damaged_session = f"{session}-shadow"
    damaged = ask_body(
        monkeypatch, tmp_path, two_leg_driver(answer, gate_state), session_id=damaged_session
    )
    _out2, damaged_readings = read_with_registered_ruler(damaged, session_id=damaged_session)
    damaged_frames = _frame_texts(damaged)

    assert any(frame.count(answer) >= 2 for frame in damaged_frames), (
        f"摘掉{guard}这一格没有任何后果：这一格前置不承重。读数={damaged_readings}"
    )
    assert damaged_readings["prefix_breaks"] > 0 or (
        damaged_readings["last_frame_covers_answer"] is False
    ), damaged_readings


# ==================== 空读那一形不许被这一改洗成流式 ====================


def test_a_budget_refusal_still_produces_no_text_frame(monkeypatch, tmp_path):
    """run9 的 ``metric-02``／``scope-02`` 那一形：出口一片不响，收端一帧 text 都数不到。

    治它的是窗口预算（``MODEL_CONTEXT_TOKENS`` 与 Ollama ``num_ctx`` 配套，业主要裁的那格），
    不是这条腿。本单不把它伪装成已经流式。
    """
    from app.common.model_budget import ModelContextLimitExceeded

    def refuse(self, prompt_tokens, stream=False):
        raise ModelContextLimitExceeded(self.budget, prompt_tokens)

    monkeypatch.setattr(nodes._ResilientModel, "_budget_kwargs", refuse)

    def raising_stream(*_args, **kwargs):
        orchestrator.main_agent_node(
            {"messages": [_human(QUESTION)], "plan": [], "memory": {}},
            _round_config(kwargs["stream_piece_sink"]),
        )
        yield {}

    body = ask_body(monkeypatch, tmp_path, raising_stream, session_id=f"{SESSION_ID}-refused")
    names = Counter(_event_names(body))
    _out, readings = read_with_registered_ruler(body, session_id=f"{SESSION_ID}-refused")

    assert names["text"] == 0, dict(names)
    assert readings["text_frames"] == 0, readings
    assert names["request.failed"] == 1 and "request.completed" not in names, dict(names)


def test_the_registered_single_frame_verdict_is_not_relaxed(monkeypatch, tmp_path):
    """在册口径一字不放宽：不接出口的那一轮在同一把尺上仍然读成不过。

    负对照直接借 R456 自己的驱动器（``one_shot_supervisor_stream``），本单不复算第二套尺。
    """
    from tests.test_r456_single_frame_shape_is_not_a_pass import one_shot_supervisor_stream

    body = ask_body(
        monkeypatch, tmp_path, one_shot_supervisor_stream, session_id=f"{SESSION_ID}-negative"
    )
    _out, readings = read_with_registered_ruler(body, session_id=f"{SESSION_ID}-negative")

    assert readings["text_frames"] == 1, readings
    assert ruler._frame_verdict(readings) is False, readings
    assert readings["last_frame_covers_answer"] is True, readings


# ==================== 反证钉：摘掉接驳 ⇒ 在册量具当场读回那一族单片形状 ====================


def test_unplugging_the_coupling_reads_back_as_the_registered_single_frame_shape(
    monkeypatch, tmp_path
):
    """判据②：接驳一摘，同一枚尺当场把这一轮读回 run9 的「单片形状」。

    刀只在内存里改函数对象（``_shadow``，被跟踪文件一字节不动）：把「该不该接」整格短路成
    「永不接」。摘掉之后出口一片不响、请求体退回非流式，``doc-07`` 重新读成 ``text_frames == 1``
    ——与本单主钉 ``test_the_direct_answer_round_reads_more_than_one_text_frame`` 的失败形状
    逐字相同。所以哪天有人把接驳拆了，主钉自己就先红，不需要这枚负对照替它说话。
    """
    answer = run9_answer("doc-07")
    session = f"{SESSION_ID}-unplugged"
    record = {}
    _shadow(monkeypatch, "_supervisor_answer_tap", [(TAP_HEAD, UNPLUG + TAP_HEAD)])

    body = ask_body(
        monkeypatch, tmp_path, direct_answer_driver(answer, record=record), session_id=session
    )
    _out, readings = read_with_registered_ruler(body, session_id=session)

    assert readings["text_frames"] == 1, readings
    assert readings["max_stream_frames"] == 1, readings
    assert readings["per_stream"] == [{"frames": 1, "breaks": 0, "first_break_at": 0}], (
        readings["per_stream"]
    )
    assert ruler._frame_verdict(readings) is False, readings
    assert readings["last_frame_covers_answer"] is True, readings
    assert record["arrivals"] == [], record["arrivals"]
    # 传输道也一并退回今天那一发：单参数 invoke ⇒ 请求体 stream 为假，一枚 stream_options 不多带。
    assert record["bodies"][0]["stream"] is False, sorted(record["bodies"][0])
    assert "stream_options" not in record["bodies"][0]


# ==================== 反证钉：三格前置摘光 ⇒ 正文在屏上出现两遍 ====================


def test_removing_all_three_prerequisites_publishes_the_answer_twice(monkeypatch, tmp_path):
    """判据② 最后一把刀：①②③ 一起摘 ⇒ 同一段正文出现两遍，末帧不再覆盖终答。

    摘单格另有两枚钉（``test_the_two_gates_keep_the_answer_from_appearing_twice`` 与
    ``tests/test_r459_supervisor_answer_leg_streams.py::test_each_prerequisite_is_load_bearing``）。
    这一枚要的是「三格全摘也不许只留下一种后果」：已经落进账本的那条腿先把正文逐片交出去，
    supervisor 汇总那一发再接上同一枚出口，收端按规则① 换发、按规则② 把已落定的答案垫成底座
    ⇒ 帧正文变成「正文 + 正文」。R215 的受控纠正那一格救不了它：坏形不在这一流的最后一枚帧上。
    """
    answer = run9_answer("approval-06")
    session = f"{SESSION_ID}-all-three"
    body = ask_body(
        monkeypatch, tmp_path, two_leg_driver(answer, _dispatched_state), session_id=session
    )
    _out, readings = read_with_registered_ruler(body, session_id=session)

    assert all(frame.count(answer) <= 1 for frame in _frame_texts(body)), readings
    assert readings["prefix_breaks"] == 0, readings

    _shadow(monkeypatch, "_supervisor_answer_tap", [
        (GUARD_SINK, DISABLE),
        (GUARD_DISPATCH, DISABLE),
        (GUARD_LEDGER, DISABLE),
    ])
    damaged_session = f"{session}-shadow"
    damaged = ask_body(
        monkeypatch, tmp_path, two_leg_driver(answer, _dispatched_state),
        session_id=damaged_session,
    )
    _out2, damaged_readings = read_with_registered_ruler(damaged, session_id=damaged_session)
    damaged_frames = _frame_texts(damaged)

    assert any(frame.count(answer) >= 2 for frame in damaged_frames), (
        f"三格前置全摘也不见后果：这一改不承重。读数={damaged_readings}"
    )
    assert damaged_frames[-1] != damaged_frames[-2], damaged_frames[-1][:40]
    assert damaged_readings["prefix_breaks"] > 0, damaged_readings
    # 🔴 这一形的 verdict 被 R215 的受控纠正替换救回来（下面两格是它的证词）
    # ⇒ 摘接驱的后果不许只拿 verdict 当证据，必须拿「帧内重复计数 + 原始断流账」。
    assert damaged_readings["corrective_replacements"] == 1, damaged_readings
    assert damaged_readings["uncorrected_breaks"] == 0, damaged_readings
    assert ruler._frame_verdict(damaged_readings) is True, (
        "口径变了：这一形今天读成过——钉要重写，不许顺手改断言"
    )
