"""R12：「停止」必须真的停得下来。

用户按停止只表示"这一轮我不看了"（裁定 ④甲）。它既不是拒绝（不许记 refused），也不
能让图继续跑完并落下新产物。本文件钉住四件事：

1. 取消标记从调用方一路穿透到 worker 节点的 configurable —— 历史上这一环是断的：全仓
   只有读端（orchestrator.py:342/:406）而没有任何写入点，两个检查点恒等于
   ``_raise_if_cancelled(None)``，即死代码；
2. 取消之后不再产生新副作用（图表/报告不落盘）；
3. 停止 != 拒绝，而拒绝仍然必须记 refused（84af113「拒绝必须真的拒绝」不许回退）；
4. executor 工作线程里逃出的异常不会无声消失。

图是真的 ``StateGraph`` 而不是手拼 config 喂进节点自证，并且刻意用降级在用的
MemorySaver：真机上 PG 与 Memory 只在 orchestrator.py 编译期换一个 checkpointer 对象，
取消语义按构造共享。
"""

import asyncio
import threading
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import orchestrator
from app.agents.state import AgentState
from app.trace.store import TraceStore


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    store = TraceStore(tmp_path / "traces.jsonl")
    monkeypatch.setattr(orchestrator, "_trace_store", store)
    return store


class FakeWorkerGraph:
    """顶替 worker 子图：``invoke`` 就是"落盘"这个副作用本身。"""

    def __init__(self, sink: Path, *, arm_on_invoke=None):
        self.sink = sink
        self.arm_on_invoke = arm_on_invoke
        self.child_configurables: list[dict] = []

    def invoke(self, _state, config=None):
        self.child_configurables.append(dict((config or {}).get("configurable", {})))
        if self.arm_on_invoke is not None:
            # 模拟"节点已经跑在半路上，用户这时按了停止"
            self.arm_on_invoke.set()
        self.sink.write_text("artifact body", encoding="utf-8")
        return {"messages": [AIMessage(content="产物已生成")]}


def _parked_graph(chart_worker, export_worker=None, *, interrupt=("chart",)):
    """真图：START -> chart -> export -> END，编译期带 interrupt_before。"""
    builder = StateGraph(AgentState)
    builder.add_node("chart", orchestrator._make_worker_wrapper(chart_worker, "chart"))
    if export_worker is not None:
        builder.add_node("export", orchestrator._make_worker_wrapper(export_worker, "export"))
        builder.add_edge("chart", "export")
        builder.add_edge("export", END)
    else:
        builder.add_edge("chart", END)
    builder.add_edge(START, "chart")
    return builder.compile(
        checkpointer=MemorySaver(), interrupt_before=list(interrupt)
    )


def _event_types(store: TraceStore, trace_id: str) -> list[str]:
    return [event["event_type"] for event in store.replay(trace_id)]


# ---------------------------------------------------------------- 穿透


def test_the_marker_reaches_both_the_worker_node_and_its_child_config(trace_store, monkeypatch, tmp_path):
    """真调用链：run_with_stream -> 真图 -> worker 节点 -> 子图 config。

    这一条专打"断链"：标记必须由 run_with_stream 写进 configurable，langgraph 才能把它
    交给节点；节点再经 child_conf 白名单传给子图。两处都断言同一个 Event 对象。
    """
    sink = tmp_path / "chart-should-exist.png"
    worker = FakeWorkerGraph(sink)
    monkeypatch.setattr(orchestrator, "multi_agent_graph", _parked_graph(worker, interrupt=()))
    marker = threading.Event()

    list(
        orchestrator.run_with_stream(
            "把销量画成图",
            thread_id="r12-passthrough",
            user={"username": "tester"},
            trace_id="trace-passthrough",
            trace_store=trace_store,
            cancel_event=marker,
        )
    )

    assert worker.child_configurables, "worker 子图没有被真正调用，这条测试就没有意义"
    assert worker.child_configurables[0]["cancel_event"] is marker
    assert sink.exists()


def test_ask_passes_the_same_marker_the_cancel_endpoint_arms(monkeypatch, tmp_path):
    """服务层闭环：/ask 交给编排的 Event 必须就是 /cancel 会置位的那一个。

    少了这一条，编排内部接得再对也没用——调用方手里的标记和运行中的标记是两个对象。
    """
    from app.api.v1 import chat
    from app.common.identity import Principal
    from app.storage.sessions import SessionRegistry

    captured = {}

    def fake_stream(*_args, **kwargs):
        captured["cancel_event"] = kwargs.get("cancel_event")
        # 在飞窗口里就地取证：R18 之后一代标记随运行结束就弹出，出流之后再查表只能查到
        # "没有在飞运行"，那时再断言"是不是同一个对象"已经没有对象可比。
        captured["in_flight_marker"] = chat.current_marker(session_id)
        captured["cancel_reports"] = chat.cancel_request(session_id)
        captured["set_after_cancel"] = kwargs["cancel_event"].is_set()
        yield {"messages": [], "worker_results": {"doc": "答案"}, "final_answer": "答案"}

    principal = Principal.from_user(
        {"id": "staff1", "username": "staff1", "role": "staff", "department": "R&D"}
    )
    http_request = type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": "staff1"})()},
    )()

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(
        chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)})
    )
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda _q, scope="": None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator, "run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    session_id = "r12-marker-identity"
    response = asyncio.run(
        chat.ask(
            chat.AskRequest(message="差旅标准是多少", session_id=session_id),
            http_request=http_request,
        )
    )

    async def consume():
        chunks = []
        async for item in response.body_iterator:
            chunks.append(item.decode("utf-8") if isinstance(item, bytes) else item)
        return "".join(chunks)

    body = asyncio.run(consume())

    marker = captured["cancel_event"]
    assert isinstance(marker, threading.Event), "/ask 没有把取消标记交给编排"
    # /cancel 走的就是这个函数：置位后编排看到的必须是同一个对象
    assert captured["in_flight_marker"] is marker, "/ask 交给编排的标记不是 /cancel 会置位的那一代"
    assert captured["cancel_reports"] is True
    assert captured["set_after_cancel"] is True
    assert chat.current_marker(session_id) is None, "R18 ②：一轮结束后本代条目必须从登记表弹出"


def test_a_stop_during_the_stream_ends_the_stream_without_done(monkeypatch, tmp_path):
    """图还在跑的时候按停止：流必须收在 cancelled，不能把后续事件继续推给客户端。

    置位走的是 ``POST /cancel`` 用的同一个函数，不是测试自己造的标记。
    """
    from app.api.v1 import chat
    from app.common.identity import Principal
    from app.storage.sessions import SessionRegistry

    session_id = "r12-stop-mid-stream"
    streamed = []

    def fake_stream(*_args, **kwargs):
        yield {"messages": [], "worker_results": {"doc": "第一段"}, "final_answer": "第一段"}
        # 用户这时点了停止：/cancel 端点调的就是这个函数
        assert chat.cancel_request(session_id) is True
        for index in range(3):
            marker = kwargs["cancel_event"]
            if marker.is_set():
                # 真编排在检查点抛出后就直接收尾，绝不再往下产事件
                return
            streamed.append(index)
            yield {"messages": [], "worker_results": {"doc": f"第{index}段"}, "final_answer": "x"}

    def exploding_fallback(*_args, **_kwargs):
        raise AssertionError("停止之后不得再产报告这类新副作用")

    principal = Principal.from_user(
        {"id": "staff1", "username": "staff1", "role": "staff", "department": "R&D"}
    )
    http_request = type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": "staff1"})()},
    )()

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(
        chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)})
    )
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda _q, scope="": None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator, "run_with_stream", fake_stream)
    monkeypatch.setattr(orchestrator, "_fallback_export_result", exploding_fallback)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    response = asyncio.run(
        chat.ask(
            chat.AskRequest(message="差旅标准是多少", session_id=session_id),
            http_request=http_request,
        )
    )

    async def consume():
        chunks = []
        async for item in response.body_iterator:
            chunks.append(item.decode("utf-8") if isinstance(item, bytes) else item)
        return "".join(chunks)

    body = asyncio.run(consume())

    assert "event: cancelled" in body
    assert "event: done" not in body
    assert streamed == [], "取消之后工作线程还在往下跑"
    # 停止不是拒绝：不许出现 refused/已取消，未执行 那套文案
    assert "refused" not in body


def test_approve_cancellation_emits_the_canonical_event_too(monkeypatch, tmp_path):
    """/approve 的取消必须和 /ask 一样先发 canonical request.cancelled，再发 legacy。

    形状对齐 /ask 的 chat.py:958-972：同一个事件名、同样带 request_id/trace_id/task_id
    与 sequence，legacy ``cancelled`` 保留不删。状态码不变（仍是 200 的 SSE）。
    """
    import json as _json

    from app.api.v1 import chat
    from app.common.identity import Principal
    from app.storage.sessions import SessionRegistry

    session_id = "r13-approve-cancel"
    registry = SessionRegistry(tmp_path / "session-registry.json")
    principal = Principal.from_user(
        {"id": "staff1", "username": "staff1", "role": "staff", "department": "R&D"}
    )
    registry.bind(session_id, principal)

    def fake_stream(*_args, **kwargs):
        yield {"messages": [], "worker_results": {}}
        assert chat.cancel_request(session_id) is True
        while True:
            if kwargs["cancel_event"].is_set():
                return
            yield {"messages": [], "worker_results": {"chart": "不该送达"}}

    monkeypatch.setattr(chat, "session_registry", registry)
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(orchestrator, "run_interrupt_stream", fake_stream)

    http_request = type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": "staff1"})()},
    )()
    response = asyncio.run(
        chat.approve(
            chat.ApproveRequest(session_id=session_id, approved=True),
            http_request=http_request,
        )
    )

    async def consume():
        chunks = []
        async for item in response.body_iterator:
            chunks.append(item.decode("utf-8") if isinstance(item, bytes) else item)
        return "".join(chunks)

    body = asyncio.run(consume())

    assert "event: request.cancelled" in body, "/approve 只发 legacy cancelled"
    assert "event: cancelled" in body
    assert "event: done" not in body
    assert "不该送达" not in body

    canonical = [
        block.splitlines()[1].removeprefix("data: ")
        for block in body.split("\n\n")
        if block.startswith("event: request.cancelled")
    ]
    assert len(canonical) == 1, "同一次取消只应发一对事件"
    payload = _json.loads(canonical[0])
    assert payload["status"] == "cancelled"
    assert payload["data"] == {"session_id": session_id}
    assert payload["request_id"].startswith("req-")
    assert payload["trace_id"].startswith("trace-")
    assert payload["task_id"].startswith("task-")
    assert isinstance(payload["sequence"], int)


# ---------------------------------------------------------------- 停止不落盘


def test_a_stop_before_the_worker_runs_produces_no_artifact(trace_store, monkeypatch, tmp_path):
    """取消已置位 -> 节点根本不开工 -> 产物不存在，且 trace 是 cancelled。"""
    sink = tmp_path / "chart-must-not-exist.png"
    worker = FakeWorkerGraph(sink)
    monkeypatch.setattr(orchestrator, "multi_agent_graph", _parked_graph(worker, interrupt=()))
    marker = threading.Event()
    marker.set()

    events = list(
        orchestrator.run_with_stream(
            "把销量画成图",
            thread_id="r12-stop-before",
            user={"username": "tester"},
            trace_id="trace-stop-before",
            trace_store=trace_store,
            cancel_event=marker,
        )
    )

    assert worker.child_configurables == [], "被停止的请求仍然开工跑了 worker 节点"
    assert not sink.exists(), "取消后仍有产物落盘"
    assert [event for event in events if "error" in event] == []
    types = _event_types(trace_store, "trace-stop-before")
    assert "request.cancelled" in types
    assert "request.failed" not in types
    assert "request.completed" not in types


def test_mid_node_stop_stops_the_export_fallback_from_writing(monkeypatch, tmp_path):
    """检查点 3 是活代码：节点跑到一半被停止时，export 兜底不得再写报告。"""
    sink = tmp_path / "in-flight.png"
    marker = threading.Event()
    worker = FakeWorkerGraph(sink, arm_on_invoke=marker)
    calls = []

    def exploding_fallback(*_args, **_kwargs):
        calls.append("called")
        return "不该被调用"

    monkeypatch.setattr(orchestrator, "_fallback_export_result", exploding_fallback)
    node = orchestrator._make_worker_wrapper(worker, "export")

    with pytest.raises(orchestrator.RequestCancelled):
        node(
            {"messages": [AIMessage(content="x")], "worker_results": {}, "agent_results": {}},
            {"configurable": {"thread_id": "t", "username": "tester", "cancel_event": marker}},
        )

    assert calls == [], "停止之后 export 兜底还是写了报告"


# ---------------------------------------------------------------- 停止 != 拒绝


def test_a_stop_leaves_the_session_parked_and_never_says_refused(trace_store, monkeypatch, tmp_path):
    """parked 会话被停止后仍是挂起态，等 R13 的待办端点来列它。"""
    sink = tmp_path / "resume-must-not-run.png"
    worker = FakeWorkerGraph(sink)
    graph = _parked_graph(worker)
    monkeypatch.setattr(orchestrator, "multi_agent_graph", graph)

    list(
        orchestrator.run_with_stream(
            "导出报告",
            thread_id="r12-parked",
            user={"username": "tester"},
            trace_id="trace-parked",
            trace_store=trace_store,
        )
    )
    assert orchestrator.check_interrupt("r12-parked") == {"pending": ["chart"], "labels": [orchestrator._HITL_LABELS["chart"]]}

    marker = threading.Event()
    marker.set()
    list(
        orchestrator.run_interrupt_stream(
            "r12-parked",
            True,
            {"username": "tester"},
            cancel_event=marker,
        )
    )

    assert worker.child_configurables == [], "被停止的 resume 还是把批准的节点跑完了"
    assert not sink.exists()
    assert orchestrator.check_interrupt("r12-parked"), "停止把挂起态清掉了，R13 就再也列不到它"
    values = graph.get_state({"configurable": {"thread_id": "r12-parked"}}).values
    results = values.get("worker_results") or {}
    assert "chart" not in results, "停止被记成了拒绝"
    assert "已取消，未执行" not in str(values.get("messages") or "")


def test_a_declined_action_is_still_recorded_as_declined(monkeypatch):
    """回守 84af113：拒绝必须真的拒绝，refused 落账不能被取消语义冲掉。"""
    captured = {}

    class FakeGraph:
        def update_state(self, config, values):
            captured["update"] = values

        def stream(self, payload, config, **kwargs):
            captured["payload"] = payload
            captured["configurable"] = config["configurable"]
            yield {"messages": []}

    monkeypatch.setattr(orchestrator, "multi_agent_graph", FakeGraph())
    monkeypatch.setattr(
        orchestrator,
        "check_interrupt",
        lambda thread_id: {"pending": ["chart"], "labels": [orchestrator._HITL_LABELS["chart"]]},
    )

    list(orchestrator.run_interrupt_stream("thread-decline", False, {"username": "tester"}))

    update = captured["update"]
    assert "chart" in update["worker_results"]
    assert update["worker_results"]["chart"].startswith("已取消，未执行")
    assert captured["payload"].goto == "supervisor"


def test_a_resume_config_always_carries_the_marker_slot(monkeypatch):
    """没传标记时不得凭空多出键，传了才注入——保证既有调用点逐字节不变。"""

    class FakeGraph:
        def __init__(self):
            self.configurables = []

        def stream(self, payload, config, **kwargs):
            self.configurables.append(config["configurable"])
            yield {"messages": []}

    graph = FakeGraph()
    monkeypatch.setattr(orchestrator, "multi_agent_graph", graph)

    list(orchestrator.run_interrupt_stream("t-a", True, {"username": "tester"}))
    assert "cancel_event" not in graph.configurables[0]

    marker = threading.Event()
    list(
        orchestrator.run_interrupt_stream(
            "t-b", True, {"username": "tester"}, cancel_event=marker
        )
    )
    assert graph.configurables[1]["cancel_event"] is marker


# ---------------------------------------------------------------- future 可见性


def test_an_exception_escaping_the_worker_thread_is_logged(caplog):
    from app.api.v1.chat import _reap_agent_worker

    class DoneFuture:
        def __init__(self, error):
            self._error = error

        def exception(self):
            return self._error

        def add_done_callback(self, fn):
            fn(self)

    with caplog.at_level("ERROR"):
        _reap_agent_worker(
            DoneFuture(RuntimeError("model exploded")),
            session_id="s-1",
            stage="ask",
        )
    assert "model exploded" in caplog.text
    assert "s-1" in caplog.text


def test_a_cancelled_future_does_not_raise_inside_the_done_callback(caplog):
    """asyncio Future 被取消后 exception() 抛 CancelledError，回调不得把它顶回循环。"""
    from app.api.v1.chat import _reap_agent_worker

    class CancelledFuture:
        def exception(self):
            raise asyncio.CancelledError()

        def add_done_callback(self, fn):
            fn(self)

    with caplog.at_level("ERROR"):
        _reap_agent_worker(CancelledFuture(), session_id="s-2", stage="approve")
    assert "s-2" not in caplog.text


def test_a_clean_worker_run_logs_nothing(caplog):
    from app.api.v1.chat import _reap_agent_worker

    class OkFuture:
        def exception(self):
            return None

        def add_done_callback(self, fn):
            fn(self)

    with caplog.at_level("ERROR"):
        _reap_agent_worker(OkFuture(), session_id="s-3", stage="ask")
    assert "s-3" not in caplog.text