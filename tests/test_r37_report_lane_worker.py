"""R37 —— report 档进可靠队列（worker 侧）。

判据 ③ 关页面不丢：worker 把这一轮跑完，结果查得回，会话历史里一问一答都落得回去。
判据 ④ 队列失败有终态与原因码，并与 R81 的收口对齐（不可重试终态不占名额）。
判据 ⑤ HITL 语义一条不许丢：报告档的 export 必须仍旧停在批准之前，
   绝不许因为“后台没人看”就自动批准，也绝不许悄悄跳过导出。

先红后绿：改前这些用例红在同一个地方——载荷里的 lane 根本没人读，于是队列走的是
不带 interrupt 的 queue_graph（deploy/queue_worker.py:109 的 run_orchestrator_result），
export 会被自动执行；而失败与挂起都不回写会话历史，留下一句没人回答的问话。
"""

import inspect
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import orchestrator
from app.agents.contracts import AgentResult
from app.agents.state import AgentState
from app.common.reliable_queue import ReliableQueue
from app.storage import pending_approvals
from app.trace.store import TraceStore
from deploy import queue_worker
from tests.test_reliable_queue import FakeRedis

SESSION = "r37-worker-session"
USERNAME = "r37-worker"
USER_ID = "u-r37-worker"
MESSAGE = "把上季度的经营情况整理成一页纸报告"
BACKGROUND_ANSWER = "后台跑完的报告结论"
# 这一句抄自同步路径 app/api/v1/chat.py 挂起时写给用户的那句话：两条道必须同话。
PARK_EXPORT = "本轮在「📋 导出报告」前等待你确认，确认后才会执行，目前尚未产出回答内容。"


# ==================== 夹具（全程离线：FakeRedis 加假图） ====================


def _payload(**overrides):
    payload = {
        "task_type": "ask",
        "message": MESSAGE,
        "session_id": SESSION,
        "username": USERNAME,
        "principal": {"user_id": USER_ID, "username": USERNAME, "roles": ["staff"]},
        "lane": "report",
        "write_back_session": True,
    }
    payload.update(overrides)
    return payload


class _FakeStream:
    """顶替带 interrupt 的在场流：按脚本产出快照。

    真流的快照事件是 (namespace, state) 元组，而编排自己吐的失败事件是一枚裸 dict，
    这里刻意保留两种形状，免得 worker 只认得其中一种。
    """

    def __init__(self, events, *, on_call=None):
        self.events = events
        self.calls = []
        self.on_call = on_call

    def __call__(self, user_message, thread_id="default", user=None, **kwargs):
        self.calls.append({"user_message": user_message, "thread_id": thread_id, "user": user})
        if self.on_call is not None:
            self.on_call()
        for event in self.events:
            yield event if "error" in event else (("",), event)


def _state(answer="", agent_results=None):
    return {
        "messages": [],
        "worker_results": {"export": answer} if answer else {},
        "final_answer": answer,
        "agent_results": agent_results or {},
    }


def _denied_results():
    """一条真契约记录：row_scope_denied 的 retryable 由 ErrorEnvelope 出厂值决定。"""
    denied = AgentResult.model_validate(
        {
            "worker": "export",
            "status": "rejected",
            "answer": "",
            "request_id": "req-r37-denied",
            "trace_id": "trace-r37-denied",
            "task_id": "task-r37-denied",
            "error": {"code": "row_scope_denied", "message": "这些行不在你的可见范围内"},
        }
    )
    return {"export": denied.model_dump(mode="json")}


def _parked_graph(worker):
    """真 StateGraph：START 到 export 到 END，编译期带 interrupt_before。"""
    builder = StateGraph(AgentState)
    builder.add_node("export", orchestrator._make_worker_wrapper(worker, "export"))
    builder.add_edge("export", END)
    builder.add_edge(START, "export")
    return builder.compile(checkpointer=MemorySaver(), interrupt_before=["export"])


class _SinkWorker:
    """child graph 的替身：invoke 就是“把产物落盘”这个副作用本身。"""

    def __init__(self, sink: Path):
        self.sink = sink
        self.calls = 0

    def invoke(self, _state, config=None):
        self.calls += 1
        self.sink.write_text("artifact body", encoding="utf-8")
        return {"messages": [AIMessage(content="产物已生成 /api/v1/artifacts/r37.pdf")]}


def _install_worker(
    monkeypatch, tmp_path, *, payload=None, max_attempts=3, name="r37-worker", stream=None, graph=None
):
    from app.api.v1 import chat

    queue = ReliableQueue(FakeRedis(), name=name, lease_seconds=30, max_attempts=max_attempts)
    message = queue.enqueue(_payload(**(payload or {})), "idem-" + name)
    ctx = SimpleNamespace(
        queue=queue, message=message, worker=queue_worker, chat=chat, history=[], recorded=[]
    )

    monkeypatch.setattr(queue_worker, "_queue", queue)
    monkeypatch.setattr(
        queue_worker, "record_agent_result", lambda rec, **kwargs: ctx.recorded.append(rec)
    )
    # 只有 PG 就绪的部署里，跨进程回写历史才是真的写得回去；这里按那条前提钉。
    monkeypatch.setattr(chat, "_session_database_available", lambda: True)
    monkeypatch.setattr(
        chat, "_save_message", lambda *args, **kwargs: ctx.history.append(tuple(args))
    )
    monkeypatch.setattr(orchestrator, "_trace_store", TraceStore(tmp_path / "traces.jsonl"))
    if stream is not None:
        monkeypatch.setattr(orchestrator, "run_with_stream", stream)
    if graph is not None:
        monkeypatch.setattr(orchestrator, "multi_agent_graph", graph)
    return ctx


def _request_id(ctx):
    return ctx.message.request_id


# ==================== 判据⑤：HITL 一条不许丢 ====================


def test_a_report_lane_turn_runs_on_the_graph_that_can_park(monkeypatch, tmp_path):
    """判据⑤：报告档在队列里必须走带 interrupt 的图，不许再走无确认的 queue_graph。"""
    sink = tmp_path / "export-should-not-exist"
    graph = _parked_graph(_SinkWorker(sink))

    def refuse(*_args, **_kwargs):
        raise AssertionError("报告档不许再走不带 interrupt 的队列图入口")

    monkeypatch.setattr(orchestrator, "run_orchestrator_result", refuse)
    ctx = _install_worker(monkeypatch, tmp_path, name="r37-park", graph=graph)

    assert ctx.worker.process_one() is True

    assert sink.exists() is False, "挂起没保住就等于自动批准"
    assert ctx.queue.status(_request_id(ctx)) == "done"


def test_a_parked_report_turn_never_executes_the_export_node(monkeypatch, tmp_path):
    """判据⑤：查回来的结果要说“等你确认”，而且不许假装导出已完成。"""
    sink = tmp_path / "export-should-not-exist-b"
    ctx = _install_worker(
        monkeypatch, tmp_path, name="r37-park-text", graph=_parked_graph(_SinkWorker(sink))
    )

    assert ctx.worker.process_one() is True

    assert ctx.queue.result(_request_id(ctx)) == PARK_EXPORT
    assert sink.exists() is False


def test_a_parked_report_turn_opens_one_awaiting_row_for_the_right_owner(monkeypatch, tmp_path):
    """判据⑤：挂起必须写成一行待办，否则审批面板看不见后台挂起的这一轮。"""
    session = "r37-park-row-session"
    sink = tmp_path / "export-should-not-exist-c"
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name="r37-park-row",
        payload={"session_id": session},
        graph=_parked_graph(_SinkWorker(sink)),
    )

    assert ctx.worker.process_one() is True

    row = pending_approvals.get_row(session)
    assert row is not None, "队列路径下的挂起没落账，审批面板就是空的"
    assert row.status == pending_approvals.AWAITING
    assert row.parked_steps == ["export"]
    assert row.owner_user_id == USER_ID
    assert row.session_id == session


def test_the_parked_wording_written_into_history_matches_the_sync_path(monkeypatch, tmp_path):
    """判据③加⑤：挂起这一轮也要回写会话历史，而且文案与同步路径同话。"""
    sink = tmp_path / "export-should-not-exist-d"
    ctx = _install_worker(
        monkeypatch, tmp_path, name="r37-park-history", graph=_parked_graph(_SinkWorker(sink))
    )

    assert ctx.worker.process_one() is True

    assert len(ctx.history) == 1, ctx.history
    session_id, role, content = ctx.history[0]
    assert session_id == SESSION
    assert role == "assistant"
    assert content == PARK_EXPORT


# ==================== 判据③：结果查得回、历史落得回去 ====================


def test_a_finished_report_turn_writes_the_answer_back_into_the_session(monkeypatch, tmp_path):
    """判据③：后台跑完的一轮，结果要查得回，也要落回会话历史。"""
    ctx = _install_worker(
        monkeypatch, tmp_path, name="r37-done", stream=_FakeStream([_state(BACKGROUND_ANSWER)])
    )

    assert ctx.worker.process_one() is True

    assert ctx.queue.status(_request_id(ctx)) == "done"
    assert ctx.queue.result(_request_id(ctx)) == BACKGROUND_ANSWER
    assert [entry[1:] for entry in ctx.history] == [("assistant", BACKGROUND_ANSWER)]


def test_a_dead_report_turn_still_leaves_a_line_in_the_conversation(monkeypatch, tmp_path):
    """判据③加④：重试耗尽落 dead，历史里也不许只剩一句没人回答的问话。"""
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name="r37-dead",
        max_attempts=1,
        stream=_FakeStream([{"error": "模型暂时不可用"}]),
    )

    assert ctx.worker.process_one() is True

    request_id = _request_id(ctx)
    assert ctx.queue.status(request_id) == "dead"
    assert ctx.queue.failure(request_id)["last_error"], "终态必须留下原因"
    assert len(ctx.history) == 1, ctx.history
    written = ctx.history[0][2]
    for code in ("internal_error", "model_unavailable", "row_scope_denied", "no_answer_produced"):
        assert code not in written, "写给用户看的那一行不许夹稳定码"


def test_a_turn_that_will_be_retried_writes_nothing_yet(monkeypatch, tmp_path):
    """判据③：还要重试的这一轮不是终态，不许先写一行失败了糊弄历史。"""
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name="r37-retry",
        max_attempts=3,
        stream=_FakeStream([{"error": "模型暂时不可用"}]),
    )

    assert ctx.worker.process_one() is True

    assert ctx.queue.status(_request_id(ctx)) == "queued"
    assert ctx.history == []


def test_a_final_denial_does_not_burn_a_retry_slot_and_still_writes_history(monkeypatch, tmp_path):
    """判据④：与 R81 对齐——契约判定不可重试的终态直接 dead，一个名额不占。"""
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name="r37-final",
        stream=_FakeStream([_state("", _denied_results())]),
    )

    assert ctx.worker.process_one() is True
    assert ctx.worker.process_one() is False, "被拒的这一轮不该再回到 pending 等取"

    request_id = _request_id(ctx)
    assert ctx.queue.status(request_id) == "dead"
    assert ctx.queue.failure(request_id) == {
        "attempts": 1,
        "last_error": "row_scope_denied",
        "max_attempts": 3,
    }
    assert len(ctx.history) == 1
    assert "row_scope_denied" not in ctx.history[0][2]


def test_a_cancelled_report_turn_publishes_nothing_and_writes_nothing(monkeypatch, tmp_path):
    """运行途中被取消：既不发布答案，也不往历史里写半成品。"""
    ctx = _install_worker(monkeypatch, tmp_path, name="r37-cancel")
    request_id = _request_id(ctx)

    monkeypatch.setattr(
        orchestrator,
        "run_with_stream",
        _FakeStream([_state(BACKGROUND_ANSWER)], on_call=lambda: ctx.queue.cancel(request_id)),
    )

    assert ctx.worker.process_one() is True

    assert ctx.queue.status(request_id) == "cancelled"
    assert ctx.queue.result(request_id) is None
    assert ctx.history == []


# ==================== 判据②：纯规则，不新增模型往返 ====================


def test_the_lane_predicate_is_a_pure_read_of_the_payload():
    """判据②：worker 侧定档也只读载荷字段，一个参数的纯函数。"""
    predicate = queue_worker._report_lane_requested

    assert list(inspect.signature(predicate).parameters) == ["payload"]
    assert predicate(_payload()) is True
    assert predicate(_payload(lane="REPORT")) is False
    assert predicate(_payload(lane="")) is False
    assert predicate({}) is False
    for junk in (None, [], "", 0, object()):
        assert predicate(junk) is False, junk


def test_the_lane_name_has_one_source_of_truth():
    """判据②：档位名在两处各自声明，靠这条钉住不许漂移，而不是互抓私有名。"""
    from app.api.v1 import chat

    assert queue_worker.REPORT_LANE == "report"
    assert queue_worker.REPORT_LANE == chat.LANE_REPORT


# ==================== 判据①：爆炸半径 ====================


def test_a_payload_without_a_lane_keeps_the_old_graph_entry_point(monkeypatch, tmp_path):
    """判据①：没声明档位的存量任务仍旧走 run_orchestrator_result，一字未动。"""
    calls = []

    def fake_run(user_message, thread_id="default", user=None):
        calls.append({"user_message": user_message, "thread_id": thread_id})
        return AgentResult.model_validate(
            {
                "worker": "orchestrator",
                "status": "success",
                "answer": "存量结论",
                "request_id": "req-r37-legacy",
                "trace_id": "trace-r37-legacy",
                "task_id": "task-r37-legacy",
            }
        )

    def never_stream(*_args, **_kwargs):
        raise AssertionError("没声明档位就不许碰带 interrupt 的在场流")

    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name="r37-legacy",
        payload={"lane": "", "write_back_session": False},
        stream=never_stream,
    )
    monkeypatch.setattr(orchestrator, "run_orchestrator_result", fake_run)

    assert ctx.worker.process_one() is True

    assert calls and calls[0]["user_message"] == MESSAGE
    assert ctx.queue.result(_request_id(ctx)) == "存量结论"
    assert ctx.history == []


def test_a_task_that_never_asked_for_write_back_leaves_history_alone(monkeypatch, tmp_path):
    """判据①：回写历史只对声明了这一点的那一轮生效，存量载荷不受影响。"""
    ctx = _install_worker(
        monkeypatch,
        tmp_path,
        name="r37-no-write-back",
        payload={"write_back_session": False},
        stream=_FakeStream([_state(BACKGROUND_ANSWER)]),
    )

    assert ctx.worker.process_one() is True

    assert ctx.queue.result(_request_id(ctx)) == BACKGROUND_ANSWER
    assert ctx.history == []


def test_the_background_turn_answers_the_owner_end_to_end(monkeypatch, tmp_path):
    """判据③端到端：/ask 入队、worker 跑完、GET /queue/status 查回、历史落回。"""
    from fastapi.testclient import TestClient

    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.main import app
    from tests.test_r37_report_lane_enqueue import _ask, _data_objects, _install as _install_api, _switch

    queue = ReliableQueue(FakeRedis(), name="r37-e2e", lease_seconds=30)
    api = _install_api(monkeypatch, tmp_path, queue=queue)
    _switch(monkeypatch, "1")
    monkeypatch.setattr(chat, "_session_database_available", lambda: True)

    body = _data_objects(_ask(lane="report"))
    request_id = body[0]["request_id"]

    monkeypatch.setattr(queue_worker, "_queue", queue)
    monkeypatch.setattr(queue_worker, "record_agent_result", lambda rec, **kwargs: None)
    monkeypatch.setattr(orchestrator, "run_with_stream", _FakeStream([_state(BACKGROUND_ANSWER)]))
    assert queue_worker.process_one() is True

    def known_user(username):
        if username == USERNAME:
            return {"id": USER_ID, "username": USERNAME, "role": "admin"}
        return {"id": "u-" + username, "username": username, "role": "admin"}

    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)
    monkeypatch.setattr(auth, "get_user", known_user)
    client = TestClient(app)

    mine = client.get(
        "/api/v1/queue/status/" + request_id,
        headers={"Authorization": "Bearer " + create_token(USERNAME)},
    )
    intruder = client.get(
        "/api/v1/queue/status/" + request_id,
        headers={"Authorization": "Bearer " + create_token("intruder")},
    )

    assert mine.status_code == 200
    assert mine.json()["status"] == "done"
    assert mine.json()["result"] == BACKGROUND_ANSWER
    assert intruder.status_code == 403
    assert [entry[0][1] for entry in api.saved] == ["user", "assistant"]
    assert api.saved[-1][0][2] == BACKGROUND_ANSWER
