# -*- coding: utf-8 -*-
"""R551 —— ``POST /approve`` 续跑轮的**顺序不变量**：``request.started`` 必须先于任何 ``completed`` 形事件。

症状（不是记账错，是真伤害）：``app/api/v1/chat.py`` 的 ``_approve_stream`` 里，
``agent_future = loop.run_in_executor(_executor, _run)`` 在前、``_record_resumed_lane_trace(...)``
在后，中间没有任何同步点——``run_in_executor`` 一交出去，工作线程立刻就动，它不等事件循环。
后果链：``app/trace/lifecycle.py:101`` 那句 ``if terminal_event or not current:`` 让一枚 trace 的
**第一条事件就把 ``agent_runs`` 行种出来**，而工作线程第一条会是检索留痕（``status=completed``）；
抢跑之后 ``lifecycle.py:96`` 以 ``terminal_run_regression`` 拒掉那枚 ``running`` 的 ``request.started``。
🔴 而这一支此后**再不往 trace 记任何 ``request.*`` 终态事件**（``request.failed``/``request.completed``
只发帧，``run_interrupt_stream`` 自己一枚都不记）⇒ 那一轮后来真失败，账面也永远停在 ``completed``。
对照物：``/ask`` 走 ``app/agents/orchestrator.py`` 的 ``run_with_stream``，``request.started`` 记在图起跑**之前**。

判据落点：
  ① 两形都测——「预发」（工作线程抢在协程之前把活干完，用同线程 eager executor 做成**确定性**形状）
     与「服务端回来之后」（真线程池、留痕晚到）各一形，都断言 ``request.started`` 的序号严格在前；
  ② 正控核心——造一轮**中途失败**的审批续跑（编排抛错 ⇒ 收端 ``kind == "error"`` 那一支），
     用真 ``TraceStore`` + 真投影读回 ``agent_runs`` 那一行，断言它的 status **不是** ``completed``；
     并同枚测试里证明这一轮**真的失败了**（body 里有 ``request.failed`` 与 ``internal_error``），否则判据是空的。

另有一格缺口在本单**不越界补**，只点名：这一支没有终态记账 ⇒ 修好顺序之后 run 行停在**开放态**
``running``（不是 ``completed``，也不是"已失败"）。补它要动 ``run_interrupt_stream`` 的 canonical 归属，
会撞 ``tests/test_approve_canonical_events.py`` 一族与前端 ``lastSequence`` 闸门——业主未裁，交回总控。

全程离线：不建 PersistentClient、不打模型、不起服务、不动 docker、不连库。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
from concurrent.futures import Future
from pathlib import Path

import pytest

#: 结构钉要用的两个符号名（在 ``_approve_stream`` 函数体里比行号，不猜绝对行号）。
RECORD_CALL = "_record_resumed_lane_trace"
EXECUTOR_CALL = "run_in_executor"


# ------------------------------------------------------------------ 最坏情形设备
class EagerExecutor:
    """``submit`` 当场把活干完 —— 等价于"工作线程抢在协程之前跑完整轮"这一最坏交错。

    抢窗口用真线程测是**量不出来**的：主协程在 ``run_in_executor`` 之后还要走十几行没有 await 的
    代码，赢面天然在它那边。这一枚设备把最坏情形变成确定性：谁的出口排在提交之后，谁就一定输。
    """

    def __init__(self) -> None:
        self.submits = 0

    def submit(self, fn, *args, **kwargs):  # noqa: ANN001 - asyncio 的调用形状
        self.submits += 1
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # pragma: no cover - _run 自己吞异常，这里只兜形状
            future.set_exception(exc)
        return future


class RecordingStore:
    """只记账的 TraceStore 替身：``record_event`` 的入参按到达顺序原样落进 ``events``。"""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def record_event(self, **kwargs):
        self.events.append({"sequence": len(self.events) + 1, **kwargs})
        return self.events[-1]


# ------------------------------------------------------------------ 离线夹具
SESSION_ID = "r551-turn"


def _principal():
    from app.agents.contracts import Principal

    return Principal.from_user(
        {"id": "alice", "username": "alice", "role": "manager", "department": "finance"}
    )


def _http_request(who):
    return type("Request", (), {"state": type("State", (), {
        "principal": who, "username": who.username
    })()})()


async def _consume(response) -> str:
    parts = []
    async for chunk in response.body_iterator:
        parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
    return "".join(parts)


def _offline(monkeypatch, tmp_path, chat, stream, store=None):
    """与 ``tests/test_r536_retrieval_completed_on_product_lane.py`` 同一套摘法（假编排、临时会话、假账本）。"""
    from app.agents import orchestrator as orchestrator_module
    from app.rag import retrieval_pipeline
    from app.storage import pending_approvals as approval_store
    from app.storage.sessions import SessionRegistry

    store = RecordingStore() if store is None else store
    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_a, **_k: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_a, **_k: None)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _sid, message: message)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda *_a, **_k: None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr(orchestrator_module, "run_with_stream", stream)
    monkeypatch.setattr(orchestrator_module, "run_interrupt_stream", stream)
    monkeypatch.setattr(orchestrator_module, "check_interrupt", lambda _sid: None)
    monkeypatch.setattr(approval_store, "_MEM_ROWS", {})
    monkeypatch.setattr(approval_store, "_database_available", lambda: False)
    registry = SessionRegistry(tmp_path / "sessions.json")
    registry.bind(SESSION_ID, _principal())
    monkeypatch.setattr(chat, "session_registry", registry)
    # 两本 trace 出口都改道到同一枚替身：chat 的第三处出口 + 检索留痕。
    monkeypatch.setattr("app.trace.store.default_trace_store", lambda: store)
    monkeypatch.setattr(retrieval_pipeline, "_product_trace_store", lambda: store)
    return store


def _leaving_a_retrieval_trail(*, fail: bool):
    """造一枚假的续跑图：第一枚动作就是**真**检索留痕（走产品发射器），随后成功收尾或抛错。"""
    from app.rag.retrieval_pipeline import record_retrieval_completed

    def stream(_session_id, **_kwargs):
        record_retrieval_completed(query="差旅报销上限是多少？", hits=[], scope=None)
        if fail:
            raise RuntimeError("编排在工作线程里挂了")
        yield {"messages": [], "worker_results": {"doc": "已批准。"}, "final_answer": "已批准。"}

    return stream


def _drive(chat, store, monkeypatch, *, fail: bool, executor=None):
    if executor is not None:
        monkeypatch.setattr(chat, "_executor", executor)
    # 与在册那件同一驱动法：先 await 端点拿到响应，再单独跑一遍流（两枚事件循环）。
    response = asyncio.run(chat.approve(
        chat.ApproveRequest(session_id=SESSION_ID, approved=True),
        _http_request(_principal()),
    ))
    return asyncio.run(_consume(response))


# ------------------------------------------------------------------ 结构钉（判据① 的第一道形状）
def _approve_stream_span(chat_module):
    source = Path(chat_module.__file__).read_text(encoding="utf-8")
    tree = __import__("ast").parse(source)
    for node in __import__("ast").walk(tree):
        if isinstance(node, __import__("ast").AsyncFunctionDef) and node.name == "_approve_stream":
            return source[:node.lineno].count("\n") + 1, node
    raise AssertionError("读不到 _approve_stream")


def _call_lines(node):
    out = {}
    ast_module = __import__("ast")
    for sub in ast_module.walk(node):
        if isinstance(sub, ast_module.Call):
            func = sub.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name in (RECORD_CALL, EXECUTOR_CALL):
                out.setdefault(name, []).append(sub.lineno)
    return out


def test_the_record_call_site_is_textually_before_the_executor_handoff():
    """顺序不变量的静态那一面：把出口挪回提交之后，这枚钉先红（不靠运行时抢窗口）。"""
    from app.api.v1 import chat

    _start, node = _approve_stream_span(chat)
    lines = _call_lines(node)
    assert lines.get(RECORD_CALL), "续跑轮的第三处出口整个没了 —— 那正是本单要防的哑火"
    assert lines.get(EXECUTOR_CALL), "读不到 run_in_executor 的提交点"
    assert max(lines[RECORD_CALL]) < min(lines[EXECUTOR_CALL]), (
        f"{RECORD_CALL}@{lines[RECORD_CALL]} 必须整体早于 {EXECUTOR_CALL}@{lines[EXECUTOR_CALL]}"
    )


# ------------------------------------------------------------------ 判据①：两形都测
def test_shape_preemptive_worker_still_sees_request_started_first(monkeypatch, tmp_path):
    """形一「预发」：工作线程抢在协程之前跑完整轮，``request.started`` 仍旧是第一枚事件。"""
    from app.api.v1 import chat

    store = _offline(monkeypatch, tmp_path, chat, _leaving_a_retrieval_trail(fail=False))
    executor = EagerExecutor()
    _drive(chat, store, monkeypatch, fail=False, executor=executor)

    kinds = [item["event_type"] for item in store.events]
    assert executor.submits == 1, store.events
    assert "request.started" in kinds and "retrieval.completed" in kinds, kinds
    assert kinds.index("request.started") < kinds.index("retrieval.completed"), kinds
    started = next(item for item in store.events if item["event_type"] == "request.started")
    assert started["status"] == "running", "started 必须带开放态；带终态就是自己把自己种死"
    assert started["trace_id"] == next(
        item["trace_id"] for item in store.events if item["event_type"] == "retrieval.completed"
    ), "两枚事件不在同一枚 trace 上，顺序断言就是空的"


def test_shape_after_server_return_keeps_the_same_order(monkeypatch, tmp_path):
    """形二「服务端回来之后」：不摘 executor（真线程池），留痕晚到，顺序断言仍旧成立。"""
    from app.api.v1 import chat

    store = _offline(monkeypatch, tmp_path, chat, _leaving_a_retrieval_trail(fail=False))
    body = _drive(chat, store, monkeypatch, fail=False)  # 用真 _executor：这一形测的是晚到

    kinds = [item["event_type"] for item in store.events]
    assert "request.started" in kinds, (kinds, body[:400])
    assert kinds[0] == "request.started", kinds
    assert kinds.index("request.started") < kinds.index("retrieval.completed"), kinds
    assert "request.completed" in body, "本轮确实交付了终答帧（这一形不是空跑）"


# ------------------------------------------------------------------ 判据②：正控核心
def test_a_failing_continuation_round_does_not_report_completed(monkeypatch, tmp_path):
    """中途失败的审批续跑：``agent_runs.status`` 不许是 ``completed``，且这一轮**真的失败过**。

    这一枚是正控核心：读的是**真** ``TraceStore`` + 真投影落下的 ``agent_runs`` 行，不是替身账面。
    工作线程用同线程 eager executor 提交（最坏抢跑形状），假图在第一枚动作就发**真**检索留痕
    再抛错 ⇒ 收端走 ``kind == "error"`` 那一支关门。
    """
    from app.api.v1 import chat
    from app.rag import retrieval_pipeline
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace.lifecycle import terminal_verdict
    from app.trace.projections import run_id_for
    from app.trace.store import TraceStore

    store = TraceStore(tmp_path / "traces.jsonl",
                       persistence=JsonPersistenceAdapter(tmp_path / "records.json"))

    def failing_stream(_session_id, **_kwargs):
        from app.rag.retrieval_pipeline import record_retrieval_completed

        record_retrieval_completed(query="差旅报销上限是多少？", hits=[], scope=None)
        raise RuntimeError("编排在工作线程里挂了")

    _offline(monkeypatch, tmp_path, chat, failing_stream, store=store)
    monkeypatch.setattr("app.trace.store.default_trace_store", lambda: store)
    monkeypatch.setattr(retrieval_pipeline, "_product_trace_store", lambda: store)

    body = _drive(chat, store, monkeypatch, fail=True, executor=EagerExecutor())

    trace_id = _trace_id_from(body)
    row = store.persistence.get("agent_runs", run_id_for(trace_id))
    assert row is not None, "跑完一轮连 run 行都没有，判据② 无从谈起"
    assert row["status"] != "completed", (
        "抢跑回来了：run 行被检索留痕种成 completed，失败轮再也改不动 —— "
        f"{ {k: row.get(k) for k in ('status', 'completed_at', 'error_code')} }"
    )
    # 这一轮必须真的失败过，否则"不是 completed"是句空话。
    assert "request.failed" in body and "internal_error" in body, body[:600]
    verdict = terminal_verdict(row)
    assert verdict["status_is_terminal"] is False, verdict
    assert verdict["completed_at_is_set"] is False, verdict
    kinds = [item["event_type"] for item in store.replay(trace_id)]
    assert kinds[0] == "request.started", kinds
    assert "retrieval.completed" in kinds, kinds


def _trace_id_from(body: str) -> str:
    """从响应体里取本轮 trace 编号：只认产品自己发出去的那一枚，不自造。"""
    import re

    hits = re.findall(r"trace-[0-9a-f]{8,}", body)
    assert hits, "整条流里读不到 trace_id，驱动没跑通"
    return hits[0]
# ------------------------------------------------------------------ 缺口点名（不越界补）
def test_this_lane_still_records_no_terminal_request_event(monkeypatch, tmp_path):
    """🔴 本单只修顺序：这一支**至今不往 trace 记 request.* 终态事件**，改前改后都一样。

    承认它而不是顺手补它：补它要动 ``run_interrupt_stream`` 的 canonical 归属，会撞
    ``tests/test_approve_canonical_events.py`` 一族与前端 ``lastSequence`` 闸门（业主未裁）。
    """
    from app.api.v1 import chat

    store = _offline(monkeypatch, tmp_path, chat, _leaving_a_retrieval_trail(fail=True))
    body = _drive(chat, store, monkeypatch, fail=True, executor=EagerExecutor())

    kinds = {item["event_type"] for item in store.events}
    assert "request.failed" not in kinds, "顺序修好了不等于账面会关门：这一支没有终态记账，别把它偷偷补上"
    assert "request.failed" in body, "帧是发了的（客户端看得见），缺的只是 trace 那一本账"
    assert "request.started" in kinds, kinds