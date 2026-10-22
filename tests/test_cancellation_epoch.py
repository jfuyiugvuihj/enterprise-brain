"""R18：取消标记必须按「代」生效，不许跨请求泄漏，也不许留死字段。

判据来自 ``docs/handoff/2026-09-15-backend-followup-requests.md`` §14，四件事逐条对号：

- **① 覆盖即丢取消**（事实 1）：``cancel_request`` 先到、``register_request`` 后到时，
  旧实现换一个干净的 Event，那次取消就消失了。本文件从单元与整轮问答两个高度钉它。
- **② 表只涨不消**（事实 3）：一轮运行结束（正常 / 异常 / 取消 / 客户端半路走人）之后，
  ``_REQUESTS`` 里不许留下本代条目——它只反映在飞的运行。
- **③ 跨代泄漏**（事实 2）：上一轮被取消过的会话，新一轮不许开局即已取消；反过来，
  绑在已结束那一代上的取消也不许顺延到下一代之后第二次生效。
- **死字段**（事实 4）：``cancellation_token`` 不许停在既不读也不写的中间态。

契约口径（与 ``docs/api/contract-v1.md`` 的 cancel 一节一致）：不带 epoch 的
``POST /api/v1/ask/{session_id}/cancel`` 取消的是**该会话当前这一代**；当没有任何在飞
运行时，它给**下一代**留一次性标记（覆盖"归属校验之后、register 之前"的窗口与
"HITL 挂起时按停止、随后点批准"），被消费一次即消失。
"""

import asyncio
import threading
import time

import pytest

from app.agents import orchestrator
from app.api.v1 import chat


@pytest.fixture(autouse=True)
def isolate_registration_table():
    """登记表是进程级的，用例之间必须各清各的（红底阶段也不许互相污染）。"""
    _clear_cancellation_state()
    yield
    _clear_cancellation_state()


def _clear_cancellation_state() -> None:
    chat._REQUESTS.clear()
    pending = getattr(chat, "_PENDING_CANCELLATIONS", None)
    if pending is not None:
        pending.clear()


def _principal(username: str = "staff1"):
    from app.common.identity import Principal

    return Principal.from_user(
        {"id": username, "username": username, "role": "staff", "department": "R&D"}
    )


def _http_request(username: str = "staff1"):
    principal = _principal(username)
    return type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": username})()},
    )()


def _wire(monkeypatch, tmp_path, stream=None):
    """把 /ask 拆成一个不碰数据库、不碰模型的纯流，只留取消这条主线。"""
    from app.storage.sessions import SessionRegistry

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
    registry = SessionRegistry(tmp_path / "sessions.json")
    monkeypatch.setattr(chat, "session_registry", registry)
    if stream is not None:
        monkeypatch.setattr(orchestrator, "run_with_stream", stream)
    return registry


async def _consume(response) -> str:
    chunks = []
    async for item in response.body_iterator:
        chunks.append(item.decode("utf-8") if isinstance(item, bytes) else item)
    return "".join(chunks)


def _answer_stream(*_args, **_kwargs):
    yield {"messages": [], "worker_results": {"doc": "标准答案"}, "final_answer": "标准答案"}


def _ask(session_id: str, *, message: str = "差旅标准是多少") -> str:
    """完整跑完一轮 /ask（含把流排空），返回 SSE 正文。"""
    response = asyncio.run(
        chat.ask(
            chat.AskRequest(message=message, session_id=session_id),
            http_request=_http_request(),
        )
    )
    return asyncio.run(_consume(response))


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    from app.trace.store import TraceStore

    store = TraceStore(tmp_path / "traces.jsonl")
    monkeypatch.setattr(orchestrator, "_trace_store", store)
    return store


class _FakeChartWorker:
    """顶替 chart 子图：``invoke`` 就是"产物落盘"这个副作用本身。"""

    def __init__(self, sink):
        self.sink = sink
        self.invocations: list[str] = []

    def invoke(self, _state, config=None):
        from langchain_core.messages import AIMessage

        self.invocations.append("chart")
        self.sink.write_text("chart body", encoding="utf-8")
        return {"messages": [AIMessage(content="产物已生成")]}


def _parked_graph(chart_worker):
    """真图：START -> chart -> END，编译期带 interrupt_before，跑一次就停在节点之前。"""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph

    from app.agents.state import AgentState

    builder = StateGraph(AgentState)
    builder.add_node("chart", orchestrator._make_worker_wrapper(chart_worker, "chart"))
    builder.add_edge("chart", END)
    builder.add_edge(START, "chart")
    return builder.compile(checkpointer=MemorySaver(), interrupt_before=["chart"])


def _approve(session_id: str) -> str:
    """完整跑完一轮 /approve（含把流排空），返回 SSE 正文。"""
    response = asyncio.run(
        chat.approve(
            chat.ApproveRequest(session_id=session_id, approved=True),
            http_request=_http_request(),
        )
    )
    return asyncio.run(_consume(response))


# ---------------------------------------------------------------- ① 覆盖即丢取消


def test_a_stop_that_lands_before_registration_is_not_wiped():
    """事实 1：先 cancel 后 register，这次取消必须由那一代观察到，不许被新 Event 抹掉。"""
    session_id = "r18-window-unit"

    # 当时没有在飞运行：/cancel 照旧如实报告 false，但标记必须留下
    assert chat.cancel_request(session_id) is False

    generation = chat.register_request(session_id)

    assert generation.is_set() is True, (
        "先到的取消被 register_request 换上的干净标记抹掉了（R18 事实 1）"
    )
    assert chat.is_request_cancelled(session_id, epoch=generation.epoch) is True
    chat.release_request(generation)


def test_a_stop_before_the_first_sse_byte_cancels_that_round(monkeypatch, tmp_path):
    """整轮高度：取消落在 ask() 返回之后、generate() 首行之前，那一轮仍须停在 cancelled。

    这一条打的是"标记不跟着一次运行走"最要命的后果——用户已经按了停止，
    编排却拿着一个干净的标记照常开工、照常把答案推给已经不看的客户端。
    """
    session_id = "r18-window-round"
    observed = []

    def stream(*_args, **kwargs):
        marker = kwargs["cancel_event"]
        observed.append(marker.is_set())
        if marker.is_set():
            # 与真编排的 R12 检查点同形：标记已置位就不再产出任何事件
            return
        yield {"messages": [], "worker_results": {"doc": "标准答案"}, "final_answer": "标准答案"}

    _wire(monkeypatch, tmp_path, stream)
    assert chat.cancel_request(session_id) is False

    body = _ask(session_id)

    # 要么编排根本没开工（取消的 Future 被 cancel 掉），要么开工时拿到的就是已置位的
    # 本代标记；出现 False 才是缺陷——先到的停止被干净的标记抹掉了。
    assert observed in ([], [True]), f"编排拿到的是干净的取消标记，先到的停止丢了: {observed}"
    assert "event: cancelled" in body
    assert "event: done" not in body
    assert "标准答案" not in body
    assert chat._REQUESTS == {}, "这一轮结束后登记表必须是空的"


def test_an_idle_stop_arms_the_next_generation_and_reports_the_route_shape(monkeypatch, tmp_path):
    """契约口径：没在飞运行时按停止，返回 cancelled=false，但标记为下一代武装着。

    响应形状是 R12 第 4 条冻结过的，这里连形状一起钉住，防止"顺手改成 202/204"。
    """
    import json as _json

    session_id = "r18-idle-arm"
    registry = _wire(monkeypatch, tmp_path)
    registry.bind(session_id, _principal())

    answer = asyncio.run(chat.cancel_ask(session_id, _http_request()))
    assert answer == {"cancelled": False, "session_id": session_id}
    assert chat.is_request_cancelled(session_id) is True, (
        "标记既没在飞运行上生效、也没武装给下一代，那这次停止就是彻底的空操作"
    )

    generation = chat.register_request(session_id)
    try:
        assert generation.is_set() is True
        assert chat.is_request_cancelled(session_id) is True
    finally:
        chat.release_request(generation)
    assert chat.is_request_cancelled(session_id) is False
    assert _json.dumps(answer)  # 响应体始终可序列化

# ---------------------------------------------------------------- ② 表只涨不消


def test_n_complete_rounds_leave_no_registration_behind(monkeypatch, tmp_path):
    """事实 3：跑完 N 个完整问答，``len(_REQUESTS)`` 必须回到 0。"""
    session_id = "r18-leak-rounds"
    _wire(monkeypatch, tmp_path, _answer_stream)

    for round_index in range(3):
        body = _ask(session_id)
        assert "event: done" in body, f"第{round_index + 1}轮没有正常收尾"
        assert len(chat._REQUESTS) == 0, (
            f"第{round_index + 1}轮结束后登记表还剩 {dict(chat._REQUESTS)}（R18 事实 3）"
        )
    assert chat._REQUESTS == {}


def test_a_generation_is_registered_only_while_its_round_is_in_flight(monkeypatch, tmp_path):
    """在飞期间看得见、收尾之后必须看不见——登记表只反映在飞的运行。"""
    session_id = "r18-in-flight-window"
    seen = {}

    def stream(*_args, **kwargs):
        seen["epoch"] = getattr(kwargs["cancel_event"], "epoch", None)
        seen["in_flight"] = chat.current_marker(session_id) is kwargs["cancel_event"]
        yield {"messages": [], "worker_results": {"doc": "标准答案"}, "final_answer": "标准答案"}

    _wire(monkeypatch, tmp_path, stream)
    body = _ask(session_id)

    assert "event: done" in body
    assert seen["in_flight"] is True, "在飞的那一代没被登记表认出来"
    assert chat.current_marker(session_id) is None, "收尾后本代条目还留在表里"


def test_a_round_that_raises_in_the_worker_still_releases_its_generation(monkeypatch, tmp_path):
    """异常出口也要走 finally：半途炸掉的轮次不许把标记留成下一轮的既有事实。"""
    session_id = "r18-raising-round"

    def stream(*_args, **_kwargs):
        raise RuntimeError("模型炸了")

    _wire(monkeypatch, tmp_path, stream)
    body = _ask(session_id)

    assert "event: error" in body
    assert chat._REQUESTS == {}, "异常收尾没有弹出本代条目"


def test_a_client_that_walks_away_mid_stream_releases_its_generation(monkeypatch, tmp_path):
    """断连是最容易被忘的出口：生成器被 aclose() 时同样必须 finally 弹出。"""
    session_id = "r18-abandoned-client"

    def stream(*_args, **_kwargs):
        for index in range(200):
            time.sleep(0.01)
            yield {"messages": [], "worker_results": {"doc": f"第{index}段"}, "final_answer": "x"}

    _wire(monkeypatch, tmp_path, stream)

    async def abandon():
        response = await chat.ask(
            chat.AskRequest(message="慢慢说", session_id=session_id),
            http_request=_http_request(),
        )
        iterator = response.body_iterator.__aiter__()
        await iterator.__anext__()
        await response.body_iterator.aclose()

    asyncio.run(abandon())

    assert chat._REQUESTS == {}, "客户端走人后本代标记永久留在表里（单租户长进程下的慢泄漏）"
    assert chat.current_marker(session_id) is None

# ---------------------------------------------------------------- ③ 跨代泄漏


def test_a_cancelled_round_does_not_start_the_next_round_already_cancelled(monkeypatch, tmp_path):
    """上一轮按了停止，下一轮必须重新拿到干净的标记，并且能正常收尾。"""
    session_id = "r18-across-rounds"

    def stopping_stream(*_args, **kwargs):
        yield {"messages": [], "worker_results": {"doc": "第一段"}, "final_answer": "x"}
        # 用户这时点了停止：/cancel 端点调的就是这个函数
        assert chat.cancel_request(session_id) is True
        while not kwargs["cancel_event"].is_set():
            yield {"messages": [], "worker_results": {}}

    _wire(monkeypatch, tmp_path, stopping_stream)
    first_body = _ask(session_id)
    assert "event: cancelled" in first_body
    assert chat._REQUESTS == {}, (
        "被取消那一代的标记没有被弹出，它随时可能被下一轮读成「已取消」（R18 事实 2）"
    )

    monkeypatch.setattr(orchestrator, "run_with_stream", _answer_stream)
    second_body = _ask(session_id)

    assert "event: cancelled" not in second_body
    assert "event: done" in second_body
    assert "标准答案" in second_body
    assert chat._REQUESTS == {}


def test_a_stop_bound_to_a_finished_generation_never_arms_a_second_one():
    """一次性消费：武装给下一代的标记，被那一代读走之后不许再顺延。"""
    session_id = "r18-one-shot"

    first = chat.register_request(session_id)
    assert chat.cancel_request(session_id) is True
    chat.release_request(first)

    second = chat.register_request(session_id)
    try:
        assert second.is_set() is False, "上一代的取消顺延到了这一代"
        assert chat.is_request_cancelled(session_id) is False
        assert chat.is_request_cancelled(session_id, epoch=second.epoch) is False
    finally:
        chat.release_request(second)

    third = chat.register_request(session_id)
    try:
        assert third.is_set() is False, "同一个停止把后面两代都判成已取消"
    finally:
        chat.release_request(third)


def test_a_cancel_hits_only_the_generation_that_is_current():
    """同会话并存的代里，不带 epoch 的 cancel 只打击最新那一代。"""
    session_id = "r18-two-generations"

    older = chat.register_request(session_id)
    newer = chat.register_request(session_id)
    assert isinstance(older, threading.Event) and isinstance(newer, threading.Event)
    assert older.epoch != newer.epoch, "两代拿到了同一个代标识"

    try:
        assert chat.cancel_request(session_id) is True
        assert newer.is_set() is True, "停止没有打在当前这一代上"
        assert older.is_set() is False, "停止打到了已经结束检查的旧一代上"
        assert chat.is_request_cancelled(session_id, epoch=older.epoch) is False
        assert chat.is_request_cancelled(session_id, epoch=newer.epoch) is True

        chat.release_request(newer)
        assert chat.current_marker(session_id) is older
        assert chat.is_request_cancelled(session_id, epoch=newer.epoch) is False, (
            "已经结束的代还能借到别人的取消状态，epoch 化读取就白做了"
        )
    finally:
        chat.release_request(older)
    assert chat._REQUESTS == {}


def test_releasing_another_generation_cannot_evict_the_one_in_flight():
    """finally 只许弹自己那一代：旧一代的收尾不能把新一代的登记带走。"""
    session_id = "r18-no-cross-evict"

    older = chat.register_request(session_id)
    newer = chat.register_request(session_id)
    chat.release_request(older)

    assert chat.current_marker(session_id) is newer
    chat.release_request(newer)
    assert chat.current_marker(session_id) is None


def test_a_stop_while_parked_prevents_the_approve_from_running_the_action(
    monkeypatch, tmp_path, trace_store
):
    """§14 判据 4（甲裁定的落地）：停在挂起处的停止，随后的批准不得执行被停的动作。

    真机复验仍归总控（本批禁 Docker），这一条把同一个形状搬到服务层：真 ``StateGraph``
    + ``interrupt_before=("chart",)``，图先 park，再用 /cancel 端点调的同一个函数停止，
    最后走完整的 /approve 流。worker 节点的 ``invoke`` 就是"产物落盘"这个副作用本身。
    """
    from app.storage import pending_approvals

    session_id = "r18-parked-stop"
    sink = tmp_path / "chart-must-not-exist.png"
    worker = _FakeChartWorker(sink)
    decided: list[str] = []
    monkeypatch.setattr(orchestrator, "multi_agent_graph", _parked_graph(worker))
    monkeypatch.setattr(
        chat, "_decide_pending_approval", lambda _sid, status: decided.append(status)
    )
    registry = _wire(monkeypatch, tmp_path)
    registry.bind(session_id, _principal())

    # 第一轮跑到 HITL 节点之前 park 住，那一代随流结束已经弹出
    list(
        orchestrator.run_with_stream(
            "导出报告",
            thread_id=session_id,
            user={"username": "staff1"},
            trace_id="trace-r18-parked",
            trace_store=trace_store,
        )
    )
    assert orchestrator.check_interrupt(session_id), "图没有 park 住，这条测试就没有意义"
    assert chat._REQUESTS == {}, "park 那一代收尾后不该留下任何登记"

    # 会话停在挂起处、没有在飞运行：/cancel 如实报 false，但标记武装给下一代
    assert chat.cancel_request(session_id) is False

    body = _approve(session_id)

    assert worker.invocations == [], "被停止的动作还是开工了"
    assert not sink.exists(), "停止之后仍有图表落盘"
    assert "event: cancelled" in body
    assert "event: done" not in body
    assert "已取消，未执行" not in body, "停止被记成了拒绝"
    assert decided == [pending_approvals.ABANDONED], "停止的账面必须是 abandoned"
    assert pending_approvals.REFUSED not in decided
    assert orchestrator.check_interrupt(session_id), "停止把挂起态清掉了，R13 就再也列不到它"

    # 一次性：武装的标记已被上一代消费，再点一次批准应当真的执行
    body = _approve(session_id)

    assert worker.invocations == ["chart"], "一次停止把会话永久锁死了"
    assert sink.exists()
    assert "event: done" in body
    assert decided == [pending_approvals.ABANDONED, pending_approvals.RESUMED]
    assert orchestrator.check_interrupt(session_id) is None


# ---------------------------------------------------------------- 死字段


def test_the_dead_cancellation_token_field_is_not_left_in_the_middle():
    """事实 4：既不读也不写的 ``cancellation_token`` 必须删净，或真的当 epoch 载体用起来。

    本批选的是"删净"：代标识现在由 ``chat`` 层的取消标记对象本身携带（每步比对的就是它），
    跨进程可序列化的 state 里再放一个没人读的同名字段，只会给人"取消已经有代际标识"的错觉。
    """
    from app.agents.contracts import AgentContext
    from app.agents.state import AgentState

    assert "cancellation_token" not in AgentState.__annotations__
    assert "cancellation_token" not in AgentContext.model_fields