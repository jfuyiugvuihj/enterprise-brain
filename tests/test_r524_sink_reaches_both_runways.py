# -*- coding: utf-8 -*-
"""R524 差格 a：stream piece sink 从此接在「审批续跑道」上，判据④ 一格都不倒退。

判据逐条对应（派工词 ``.tmpfix/r524_dispatch.txt`` 判据 1/3/4/5/6）：

- **判据①**「接上之后 ``git grep -n stream_piece_sink -- app/agents/orchestrator.py`` >=2 处（两跑道
  各一）」：本件不止数枚数——**改前现取就是 5 处命中，全部住在 ``run_with_stream`` 里**（执行层自报：
  ``git grep -c stream_piece_sink -- app/agents/orchestrator.py`` 改前 =5、改后 =9），所以只数枚数那把
  尺今天量不到本单，反而会把它冒充成"已经绿了"。真正咬得住的是按**函数**点名：两跑道各收一枚同名
  形参、各写一枚 ``config["configurable"][STREAM_PIECE_SINK_KEY]``，缺一枚即红。摘刀读数在
  ``tests/test_r524_counter_evidence_teeth.py``（刀 K1）。
- **判据②** 队列道端到端 → 不在本件：见 ``tests/test_r524_queue_lane_sends_no_second_character.py``
  （``not_applicable``，带凭据；那一支今天结构上发不出第二枚字）。
- **判据③** 三把尺一字未动 → ``test_the_three_rulers_of_criterion_three_are_untouched``。
- **判据④/⑤** 不注册时连键都不加、无人注册时 ``publish_stream_pieces`` 仍直接 return →
  ``test_an_unregistered_resume_round_adds_not_a_single_key`` + ``test_an_unregistered_round_publishes_nothing``。
- **判据⑥** 开窗后读哪一行 → ``test_the_resume_runway_reports_the_round_in_the_registered_log_keys``
  与 ``test_the_window_reading_uses_only_registered_log_keys``：后端日志里
  ``[R149] ... 批准续跑轮收到流式片段`` 那一行，键名沿用 /ask 那行的在册词汇
  （``pieces=`` / ``cumulative=`` / ``leg=`` / ``call=`` / ``dropped=``），本单不新造没人消费的键。

🔴 为什么续跑道接上出口**不是**装饰（现取自本树，不抄纸）：挂起**之前**那一轮里审批腿没有字可流
——正文由 ``build_precheck()`` / ``extract_standard()`` 确定性拼出，总控 09-29 已记 ``not_applicable``
（计划书 L486），本单不为「接上」伪造逐片。但批准**之后**续跑的这一轮会真去跑被挂起的那条腿：
``orchestrator._HITL_PARKED`` 现读是 ``chart`` / ``export``，其中 ``chart`` 就坐在
``nodes.ANSWER_LEG_STREAM_WORKERS`` 名单里 ⇒ 那一发的字确实进得来出口。名单本单一个字未放宽。

两族形状各钉一枚（都打真 ``/api/v1/approve`` 路由，假 provider 逐 chunk 流字，零端口零模型零容器）：

- 屏上**没有**正文（挂起轮一枚字没交，run9 ``chart-01`` 那一族）⇒ 逐片帧真上屏：``text`` 事件 >1、
  帧与帧首尾相接是单调前缀、逐字拼回等于本轮交付的正文、片段时间戳两两不重叠；
- 屏上**已有**同一份正文（R464 病历的常态：批准后图把同一条腿重跑一遍）⇒ 一枚逐片帧都不许上屏，
  ``text`` 帧序列与改前逐字相同，片只进账不进屏。
"""

import ast
import asyncio
import inspect
import json
import logging
import re
from pathlib import Path

import httpx
import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.agents import nodes, orchestrator
from app.agents.contracts import ModelTier
from app.api.v1 import chat
from app.common import model_budget
from app.common.model_budget import model_tier_budget
from app.storage import pending_approvals as approval_store
from app.storage.sessions import SessionRegistry
from tests.test_approve_canonical_events import _http_request, finance_principal
from tests.test_r203_sse_progressive_frames import _answer_frames  # noqa: F401  同一条链，不造第二份

REPO = Path(__file__).resolve().parents[1]
ORCHESTRATOR_PATH = REPO / "app" / "agents" / "orchestrator.py"
CHAT_PATH = REPO / "app" / "api" / "v1" / "chat.py"
NODES_PATH = REPO / "app" / "agents" / "nodes.py"

SESSION_ID = "r524-resume-runway"
QUESTION = "把这笔差旅按制度批下来，并说明住宿标准"
#: 157 字的正文（现取 len(ANSWER)=157）按 18 字一 chunk 打出去，尺寸闸（20 字）至少切出 3 枚满片再加一枚末片，
#: 所以下面「text 事件 >1」不是本件构造出来的假形状，是判据③ 那把尺自己算出来的枚数。
ANSWER = (
    "一线城市住宿费为每晚 500 元，凭发票按实际发生额报销；"
    "二三线城市住宿费为每晚 350 元，超标部分需要部门负责人签字确认之后才可以入账。"
    "交通费用按高铁二等座实名票据据实报销，市内打车一个月封顶三百元，超出部分由本人承担。"
    "餐饮补助按出差自然日计算，每天一百元，不需要发票，也不需要事前申请，直接随差旅单一并递交。"
)
REGISTER_STATEMENT = 'config["configurable"][STREAM_PIECE_SINK_KEY] = stream_piece_sink'
#: 判据③ 的三把尺：本单不许动，动了就是退回。字面抄在钉里，红了报的是现读数。
RULERS = {
    "STREAM_PIECE_MIN_CHARS": "20",
    "STREAM_PIECE_MERGE_SECONDS": "0.1",
    "STREAM_PIECE_STALL_FLOOR_CHARS": "4",
}
#: 判据⑥：/ask 那行在册读数的键名（``app/api/v1/chat.py`` 里 ``[R149] ... 流式片段与终答不同源``）。
#: 续跑道的日志键只许用这一族——R518 交回的「腿名只能读后端日志」那一格认的就是它。
REGISTERED_LOG_KEYS = {"session", "pieces", "cumulative", "leg", "call", "dropped"}
RESUME_LOG_MARKER = "批准续跑轮收到流式片段"


# ==================== 源文侧的取证助手（判据①③⑥ 全走这里） ====================


def _function_source(module, name: str) -> str:
    """按名字取模块里某枚函数的源码，**嵌套定义也算**（``_approve_stream`` 藏在路由里面）。"""
    text = Path(inspect.getsourcefile(module)).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(f"{module.__name__} 里找不到 {name}，这条钉的前提变了")


def _grep_lines(path: Path, needle: str) -> list:
    """等价于 ``git grep -n <needle> -- <path>``：逐行命中，交回 ``(行号, 原文)``。"""
    return [
        (number, line)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if needle in line
    ]


def _runway_body(text: str, name: str) -> str:
    """取 orchestrator 源文里某枚顶层函数的整段源码（含 docstring 与形参行）。"""
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(f"orchestrator 源文里找不到 {name}")


def _runway_is_wired(source: str) -> bool:
    """一枚跑道算"接上了"要同时满足两格：收得到形参、并且真把它写进 ``configurable``。"""
    return "stream_piece_sink=None," in source and REGISTER_STATEMENT in source


# ==================== 真 /approve + 真生成腿（假 provider 逐 chunk 流字） ====================


def _streaming_model(answer: str, calls: list):
    """真 :class:`nodes._ResilientModel`：注册了出口 ⇒ 这一发必须改走流式（R203 那套准入）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        calls.append(bool(body.get("stream")))
        payload = "".join(
            "data: " + json.dumps(f, ensure_ascii=False) + "\n\n" for f in _answer_frames(answer)
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


def _resume_leg(answer, seen, calls, worker):
    """替 ``run_interrupt_stream`` 那一层：**只替编排**，生成腿与收端全真。

    出口用**调用方交来的那一枚**：调用方没注册就拿不到 sink，一个字都进不了出口。这正是判据①
    要的因果——摘掉注册点，下面的端到端断言必须红，而不是摘了还绿。
    """

    def stream(*_args, **kwargs):
        sink = kwargs.get("stream_piece_sink")

        def spy(piece):
            seen.append(piece)
            sink(piece)

        configurable = {
            "worker": worker,
            "request_id": "request-r524",
            "trace_id": "trace-r524",
        }
        if callable(sink):
            configurable[nodes.STREAM_PIECE_SINK_KEY] = spy
        message = _streaming_model(answer, calls).invoke(
            [HumanMessage(content=QUESTION)], config={"configurable": configurable}
        )
        handed = str(getattr(message, "content", "") or "")
        yield {"messages": [], "worker_results": {worker: handed}, "final_answer": handed}

    return stream


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """两条腿摘成离线件：假编排 + **真**内存会话历史 + 假缓存；零模型、零端口、零容器。

    与 ``tests/test_r464_one_terminal_answer_stream_per_round.py::offline`` 同一分工：会话历史
    必须**真**写得进也读得出，``_round_screen_answer`` 读的就是那一行——"客户端真见过什么"只有
    这一处事实源。
    """
    monkeypatch.delenv("REPORT_LANE_VIA_QUEUE", raising=False)
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    monkeypatch.setattr(approval_store, "_MEM_ROWS", {})
    monkeypatch.setattr(approval_store, "_database_available", lambda: False)
    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "_MEM_SESSIONS", {})
    monkeypatch.setattr(chat, "_MEM_SESSION_MESSAGES", {})
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator, "check_interrupt", lambda _tid: None)
    from app.trace import spans
    from app.trace.store import TraceStore

    monkeypatch.setattr(spans, "default_trace_store", lambda: TraceStore(tmp_path / "r524.jsonl"))

    registry = SessionRegistry(tmp_path / "sessions.json")
    principal = finance_principal()
    registry.bind(SESSION_ID, principal)
    monkeypatch.setattr(chat, "session_registry", registry)

    ctx = {"monkeypatch": monkeypatch, "principal": principal, "rows": chat._MEM_SESSION_MESSAGES}
    yield ctx
    model_budget.reset_default_budget()


def _stub_resume(offline, *, answer=ANSWER, seen=None, calls=None, worker="chart"):
    seen = [] if seen is None else seen
    calls = [] if calls is None else calls
    offline["monkeypatch"].setattr(
        orchestrator, "run_interrupt_stream", _resume_leg(answer, seen, calls, worker)
    )
    return seen, calls


def _drain(response) -> str:
    async def _read():
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return "".join(parts)

    return asyncio.run(_read())


def _approve(*, approved: bool = True) -> str:
    return _drain(asyncio.run(chat.approve(
        chat.ApproveRequest(session_id=SESSION_ID, approved=approved),
        http_request=_http_request(finance_principal()),
    )))


def _text_bodies(body: str) -> list:
    """按到达顺序取出这条流上每一枚 ``text`` 帧的正文（不加工，帧里是什么就是什么）。"""
    out = []
    for frame in body.split("\n\n"):
        if not frame.strip():
            continue
        name, data = None, None
        for line in frame.split("\n"):
            if line.startswith("event: "):
                name = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if name == "text":
            out.append(str((data or {}).get("content") or ""))
    return out


def _seed_screen(text: str) -> None:
    """把"屏上此刻的那一份正文"写成会话历史里最后一条 assistant 行（挂起轮交回的那一行）。"""
    chat._MEM_SESSION_MESSAGES.setdefault(SESSION_ID, []).append(
        {"role": "assistant", "content": text}
    )


# ==================== 判据①：两跑道各一枚形参 + 各一枚注册语句 ====================


def test_criterion_one_names_both_runways_not_just_a_hit_count():
    """字面尺（``>=2 处``）改前就绿（5 处全在 ``run_with_stream`` 里），所以本钉按函数点名。"""
    text = ORCHESTRATOR_PATH.read_text(encoding="utf-8")
    for name in ("run_with_stream", "run_interrupt_stream"):
        body = _runway_body(text, name)
        assert _runway_is_wired(body), f"{name} 这一跑道没接上：形参或注册语句缺格"
    hits = _grep_lines(ORCHESTRATOR_PATH, "stream_piece_sink")
    assert len(hits) >= 2, hits


def test_the_registered_key_is_the_one_the_nodes_admission_reads():
    """两跑道写进去的键名就是 ``nodes.answer_leg_stream_target`` 认的那一枚，不是第二套。"""
    assert nodes.STREAM_PIECE_SINK_KEY == "stream_piece_sink"
    text = ORCHESTRATOR_PATH.read_text(encoding="utf-8")
    assert text.count(REGISTER_STATEMENT) == 2, "两跑道各一枚注册语句，多一枚就是第二套口径"


def test_the_approve_endpoint_hands_its_own_sink_to_the_resume_runway():
    """``/approve`` 的调用点真把自己那枚出口交下去（摘掉那一行 = 刀 K2：端到端与这枚钉一起红）。

    ``_run`` 在 ``_ask_stream`` 与 ``_approve_stream`` 里各有一枚同名嵌套定义，所以本钉按
    **外层**函数取源码：``ast.get_source_segment`` 交回的是整段，嵌套定义也算在里面。
    """
    resume = _function_source(chat, "_approve_stream")
    assert "stream_piece_sink=_piece_sink," in resume, "审批道的注册点没了"
    assert 'result_queue.put(("piece", piece))' in resume, "审批道没有把片送进同一条队列的入口"
    assert sorted(set(re.findall(r'result_queue\.put\(\("(\w+)"', resume))) == [
        "done", "error", "event", "piece"
    ], "审批道的队列词汇表与这条钉的前提不符，重审"


# ==================== 判据④/⑤：不注册时一个键都不加、一个字都不发 ====================


def _captured_config(monkeypatch, *, approved: bool, **kwargs) -> dict:
    """真跑 ``run_interrupt_stream``，把交给图的那本 config 抓回来（图本身摘成一枚空流）。"""
    captured = {}

    def fake_stream(graph, payload, config, *, cancel_event=None):
        captured.update(config)
        return iter(())

    monkeypatch.setattr(orchestrator, "_cancellable_stream", fake_stream)
    monkeypatch.setattr(orchestrator, "check_interrupt", lambda _tid: None)
    monkeypatch.setattr(
        orchestrator.multi_agent_graph, "update_state", lambda *_a, **_k: None, raising=False
    )
    list(orchestrator.run_interrupt_stream("thread-r524", approved, {"username": "tester"}, **kwargs))
    return captured.get("configurable") or {}


def test_an_unregistered_resume_round_adds_not_a_single_key(monkeypatch):
    """判据④：不传出口时这本 config 的键集与改前逐字相同——连键都不加，图的形状一个字没动。"""
    configurable = _captured_config(monkeypatch, approved=True)
    assert nodes.STREAM_PIECE_SINK_KEY not in configurable, sorted(configurable)
    assert {"thread_id", "username", "request_id", "trace_id", "task_id"} <= set(configurable)


def test_the_resume_runway_registers_the_very_sink_the_caller_handed_in(monkeypatch):
    sink = object()
    approved = _captured_config(monkeypatch, approved=True, stream_piece_sink=sink)
    assert approved[nodes.STREAM_PIECE_SINK_KEY] is sink
    # 拒绝那条收尾流（Command(goto="supervisor")）用的是同一本 config：不能只有批准才带出口。
    declined = _captured_config(monkeypatch, approved=False, stream_piece_sink=sink)
    assert declined[nodes.STREAM_PIECE_SINK_KEY] is sink


def test_an_unregistered_round_publishes_nothing():
    """判据⑤：``nodes.py:518-526`` 那一支的形状还在——无人注册就 return，不建列表、不发事件。"""
    warnings = []
    original = nodes.logger.warning
    nodes.logger.warning = lambda *_a, **_k: warnings.append(_a)
    try:
        config = {"configurable": {"thread_id": "t", "worker": "chart"}}
        assert nodes.publish_stream_pieces(config, ["任何一片"]) is None
        assert nodes.answer_leg_stream_target(config) == (None, "")
        assert warnings == []
    finally:
        nodes.logger.warning = original


# ==================== 判据③：三把尺一字未动（为了过门改数＝退回） ====================


def test_the_three_rulers_of_criterion_three_are_untouched():
    text = NODES_PATH.read_text(encoding="utf-8")
    for name, literal in RULERS.items():
        assert re.search(rf"^{name} = {re.escape(literal)}$", text, re.M), name
    assert nodes.STREAM_PIECE_MIN_CHARS == 20
    assert nodes.STREAM_PIECE_MERGE_SECONDS == 0.1
    assert nodes.STREAM_PIECE_STALL_FLOOR_CHARS == 4
    # 取证裁定：名单不放宽。审批腿接不接得到出口与名单无关（挂起腿压根没有模型调用可流），
    # 把 approval 写进名单只会往日志的 leg= 与 StreamPiece.worker 里塞一枚假腿名（归因造假）。
    assert nodes.ANSWER_LEG_STREAM_WORKERS == frozenset({"doc", "data", "chart"})


# ==================== 两族形状的定罪格（判据②③ 与 R464 各读各的，绿色件与反证刀共用） =====


def assert_progressive_delivery(seen, frames, delivered):
    """判据② 的三条 + 判据③ 的尺寸闸：续跑道把逐片字真交到了屏上。"""
    assert len(frames) > 1, f"续跑道一枚逐片帧都没上屏（text 事件 >1 不成立）：{frames}"
    ordered = sorted(seen, key=lambda piece: piece.start_at)
    for earlier, later in zip(ordered, ordered[1:]):
        assert later.start_at >= earlier.end_at, (earlier, later)
    assert "".join(piece.text for piece in seen) == ANSWER, "逐字拼回缺字"
    assert frames[-1].strip() == ANSWER.strip(), frames[-1]
    for earlier, later in zip(frames, frames[1:]):
        assert later.startswith(earlier), (earlier, later)
    for piece in seen[:-1]:
        assert len(piece.text) >= nodes.STREAM_PIECE_MIN_CHARS, piece
    assert {piece.worker for piece in seen} == {"chart"}
    assert len({piece.call_id for piece in seen}) == 1
    assert delivered == ANSWER, delivered
    return {"pieces": len(seen), "frames": len(frames)}


def assert_no_replay_on_screen(seen, frames, alarms):
    """R464 那一侧：屏上已站着同一份正文 ⇒ 一枚逐片帧都不许再上屏，也不许把闸门灌满误报。"""
    assert frames == [], f"逐片帧把屏上已有的正文又发了一遍（R464 病历）：{frames}"
    assert len(seen) > 1, seen
    assert "".join(piece.text for piece in seen) == ANSWER
    assert alarms == [], f"重放被记成了「第二枚流」的罪证，R464 的账被逐片帧灌满：{alarms}"


# ==================== 端到端 · 屏上无正文 ⇒ 逐片帧真上屏（判据②的三条都在这一支） ==========


def test_the_resume_runway_streams_progressive_frames_when_the_screen_holds_nothing(offline):
    seen, _calls = _stub_resume(offline)
    frames = _text_bodies(_approve())
    delivered = [r["content"] for r in offline["rows"][SESSION_ID] if r["role"] == "assistant"][-1]
    assert_progressive_delivery(seen, frames, delivered)


# ==================== 判据⑥：窗内读数 = 在册键，不新造没人消费的键 ====================


def test_the_resume_runway_reports_the_round_in_the_registered_log_keys(offline, caplog):
    seen, _calls = _stub_resume(offline)
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    _approve()
    lines = [r.getMessage() for r in caplog.records if RESUME_LOG_MARKER in r.getMessage()]
    assert len(lines) == 1, lines
    reading = lines[0]
    assert "[R149]" in reading, reading
    for key in ("pieces=", "cumulative=", "call=", "dropped="):
        assert key in reading, (key, reading)
    assert f"pieces={len(seen)}" in reading, reading
    assert "leg=chart" in reading, reading


def test_those_key_names_are_actually_registered_on_the_ask_reading_line():
    """判据⑥ 的"在册"二字不许是空话：本单沿用的每一枚键名，/ask 那行读数今天就在用。

    出处：``app/api/v1/chat.py`` 里 ``[R149] ... 流式片段与终答不同源`` 那一行；消费者见
    ``docs/testing/r506-a2-reading-2026-09-29.md`` §2.A 第 8 条与
    ``docs/testing/r518-a2-lane-attribution-2026-09-29.md`` 的"腿名"那一行——它们写的读法就是
    读后端这行日志，而不是给帧账加键（帧账那七格受 ``tests/test_r181_text_frame_ruler.py``
    的 ``FRAME_READING_KEYS`` 甲案钉约束，加一格当场红，本单没碰它）。
    """
    text = CHAT_PATH.read_text(encoding="utf-8")
    at = text.index("流式片段与终答不同源")
    ask_line = text[max(0, at - 200):at + 500]
    for key in sorted(REGISTERED_LOG_KEYS):
        assert f"{key}=" in ask_line, (key, ask_line)


def test_the_window_reading_adds_no_key_nobody_consumes(offline, caplog):
    """把真到手的读数行拆成字段：键集与在册词汇**对判**（不是子集），多一枚就是没人消费。"""
    _stub_resume(offline)
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    _approve()
    lines = [r.getMessage() for r in caplog.records if RESUME_LOG_MARKER in r.getMessage()]
    assert len(lines) == 1, lines
    assert set(re.findall(r"(\w+)=", lines[0])) == REGISTERED_LOG_KEYS, lines[0]


# ==================== R464 那一侧：屏上已有同一份正文 ⇒ 一枚都不许再上屏 ====================


def test_the_resume_runway_does_not_re_deliver_text_already_on_screen(offline, caplog):
    seen, _calls = _stub_resume(offline)
    _seed_screen(ANSWER)  # 挂起轮交付的那一行 = 此刻屏上站着的那份字
    caplog.set_level(logging.INFO, logger="enterprise_brain")
    frames = _text_bodies(_approve())
    alarms = [r.getMessage() for r in caplog.records if "批准腿拦下" in r.getMessage()]
    delivered = [r["content"] for r in offline["rows"][SESSION_ID] if r["role"] == "assistant"]

    assert_no_replay_on_screen(seen, frames, alarms)
    assert delivered[-1] == ANSWER, delivered
    assert delivered[0] == ANSWER, "挂起轮那一行被改写：屏上此刻的字不是本单交的那一份"