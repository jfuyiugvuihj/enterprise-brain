"""R37 —— report 档进可靠队列（入队侧）。

判据 ① 入队只由**显式**信号触发：请求自己声明档位，并且环境变量开关打开。
   两者缺一个，/ask 就走原来的同步路径，一个字节都不许变。
判据 ② 档位判别是纯规则：只读请求字段，判别路径上不碰模型、不碰图，
   也不去 app/agents/nodes.py 抓私有名（那是别的 Agent  的写域）。
判据 ③ 关页面不丢：queued 事件发完客户端就走人，单子仍旧留在队列里等 worker 取。

先红后绿：本文件在改前实测红（AskRequest 没有 lane 字段、chat 里没有开关常量，
声明档位的请求仍旧进同步流），红的原文抄在交工回执第 5 项。
"""

import asyncio
import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.common.identity import Principal

REPOSITORY = Path(__file__).resolve().parents[1]
SESSION = "r37-enqueue-session"
USERNAME = "r37-enqueue"
USER_ID = "u-r37-enqueue"
QUEUE_REQUEST_ID = "r37-reliable-request"
ANSWER = "在场跑完的答案"
MESSAGE = "把上季度的经营情况整理成一页纸报告"
IDEM = "r37-idempotency-key"


# ==================== 夹具（全程离线：假队列加假模型出口） ====================


class _FakeQueue:
    """只记录入队调用：判据①的正题是“该不该进队列”，这里不需要真 Redis。"""

    def __init__(self):
        self.calls = []

    def enqueue(self, payload, idempotency_key):
        self.calls.append({"payload": payload, "idempotency_key": idempotency_key})
        return SimpleNamespace(request_id=QUEUE_REQUEST_ID)


class _StreamSpy:
    """顶替 run_with_stream：它被调用就说明这一轮进了同步的在场执行。"""

    def __init__(self):
        self.calls = []

    def __call__(self, user_message, thread_id="default", user=None, **kwargs):
        self.calls.append({"user_message": user_message, "thread_id": thread_id})
        yield {"messages": [], "worker_results": {}, "final_answer": ANSWER}


class _ModelFactorySpy:
    """判据②的计数器：判别与入队这一段只要碰模型，这里就会涨。"""

    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("档位判别不许造模型")


def _install(monkeypatch, tmp_path, *, queue=None, connect=None, allowed=True):
    from app.agents import nodes, orchestrator
    from app.api.v1 import chat
    from app.common import reliable_queue
    from app.storage.sessions import SessionRegistry

    ctx = SimpleNamespace(
        chat=chat,
        queue=queue if queue is not None else _FakeQueue(),
        saved=[],
        cache_reads=[],
        stream=_StreamSpy(),
        models=_ModelFactorySpy(),
    )

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(
        chat, "_save_message", lambda *args, **kwargs: ctx.saved.append((args, kwargs))
    )
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(
        chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)})
    )
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_a, **_k: (allowed, 9))
    monkeypatch.setattr(
        "app.common.cache.get_cached_answer",
        lambda _question, scope="": ctx.cache_reads.append(scope) or None,
    )
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_a, **_k: None)
    monkeypatch.setattr(
        reliable_queue,
        "connect_reliable_queue",
        connect if connect is not None else (lambda: ctx.queue),
    )
    monkeypatch.setattr(orchestrator, "run_with_stream", ctx.stream)
    monkeypatch.setattr(nodes, "_make_model", ctx.models)
    if hasattr(orchestrator, "_make_model"):
        monkeypatch.setattr(orchestrator, "_make_model", ctx.models)
    return ctx


def _switch_name():
    from app.api.v1 import chat

    return str(getattr(chat, "REPORT_LANE_QUEUE_ENV", "<<chat 还没有开关常量>>"))


def _switch(monkeypatch, value):
    name = _switch_name()
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)


def _http_request():
    principal = Principal.from_user(
        {"id": USER_ID, "username": USERNAME, "role": "staff", "department": "R&D"}
    )
    return SimpleNamespace(
        state=SimpleNamespace(username=USERNAME, principal=principal), headers={}
    )


def _ask(*, lane=None, idempotency=IDEM):
    from app.api.v1 import chat

    fields = {"message": MESSAGE, "session_id": SESSION}
    if lane is not None:
        fields["lane"] = lane
    if idempotency is not None:
        fields["idempotency_key"] = idempotency
    return asyncio.run(chat.ask(chat.AskRequest(**fields), http_request=_http_request()))


def _response_body(response):
    async def collect():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    return asyncio.run(collect())


def _data_objects(response):
    payloads = []
    for line in _response_body(response).splitlines():
        if line.startswith("data: "):
            payloads.append(json.loads(line[6:]))
    return payloads


# ==================== 判据①：显式信号加默认关 ====================


def test_the_request_contract_gained_one_optional_lane_field():
    """判据①：档位是请求里的显式字段，默认空 ⇒ 老调用方一个字都不用改。"""
    from app.api.v1 import chat

    assert chat.LANE_REPORT == "report"
    assert chat.AskRequest(message=MESSAGE).lane == ""
    assert chat.AskRequest(message=MESSAGE, lane="report").lane == "report"


def test_the_queue_switch_is_off_by_default(monkeypatch):
    """判据①：默认关——没配环境变量的现网不会因为本单多走一条道。"""
    from app.api.v1 import chat

    _switch(monkeypatch, None)
    assert chat._report_lane_via_queue_enabled() is False
    for value in ("", "0", "off", "no", "false", "anything-else"):
        _switch(monkeypatch, value)
        assert chat._report_lane_via_queue_enabled() is False, value
    for value in ("1", "true", "TRUE", "yes", "on"):
        _switch(monkeypatch, value)
        assert chat._report_lane_via_queue_enabled() is True, value


def test_an_undeclared_request_never_reaches_the_queue(monkeypatch, tmp_path):
    """判据①：开关打开也不许改变没声明档位的请求——它仍旧在场跑完。"""
    ctx = _install(monkeypatch, tmp_path)
    _switch(monkeypatch, "1")

    body = _data_objects(_ask(lane=None))

    assert ctx.queue.calls == []
    assert ctx.stream.calls and ctx.stream.calls[0]["user_message"] == MESSAGE
    assert any(item.get("type") == "text" and item.get("content") == ANSWER for item in body)
    assert ctx.cache_reads, "没声明档位的请求必须照旧经过答案缓存这道门"


def test_a_declared_report_lane_stays_synchronous_while_the_switch_is_off(monkeypatch, tmp_path):
    """判据①：只有请求声明档位、开关没开，也仍旧是同步路径。"""
    ctx = _install(monkeypatch, tmp_path)
    _switch(monkeypatch, "0")

    body = _data_objects(_ask(lane="report"))

    assert ctx.queue.calls == []
    assert ctx.stream.calls
    assert any(item.get("type") == "text" and item.get("content") == ANSWER for item in body), "开关关着的时候这一轮必须在场跑完"


def test_a_declared_report_lane_is_enqueued_when_the_switch_is_on(monkeypatch, tmp_path):
    """判据①正题：显式档位加开关打开 ⇒ 进可靠队列，载荷带得出档位。"""
    ctx = _install(monkeypatch, tmp_path)
    _switch(monkeypatch, "1")

    _ask(lane="report")

    assert len(ctx.queue.calls) == 1, ctx.queue.calls
    call = ctx.queue.calls[0]
    assert call["idempotency_key"] == IDEM
    payload = call["payload"]
    assert payload["task_type"] == "ask"
    assert payload["message"] == MESSAGE
    assert payload["session_id"] == SESSION
    assert payload["username"] == USERNAME
    assert payload["lane"] == "report"
    # 队列路径下历史不许留空洞：载荷里要带上“这一轮要回写会话”的明确交代。
    assert payload["write_back_session"] is True
    assert payload["principal"]["user_id"] == USER_ID


def test_a_background_report_turn_is_not_short_circuited_by_the_answer_cache(monkeypatch, tmp_path):
    """显式要求后台跑的一轮，不许被答案缓存就地短路成在场回答。"""
    ctx = _install(monkeypatch, tmp_path)
    _switch(monkeypatch, "1")

    _ask(lane="report")

    assert ctx.cache_reads == []
    assert ctx.stream.calls == []


def test_the_queued_event_says_why_the_turn_went_background(monkeypatch, tmp_path):
    """queued 事件要能自证是“报告档走队列”，不是限流，也不是缓存命中。"""
    ctx = _install(monkeypatch, tmp_path)
    _switch(monkeypatch, "1")

    body = _data_objects(_ask(lane="report"))

    assert body[0] == {
        "type": "queued",
        "request_id": QUEUE_REQUEST_ID,
        "status": "queued",
        "lane": "report",
        "reason": "report_lane",
    }
    assert body[-1] == {"type": "done"}


def test_the_over_limit_payload_is_untouched_for_callers_that_declare_no_lane(monkeypatch, tmp_path):
    """判据①护栏：现存的超限入队路径，对没声明档位的调用方一字不变。"""
    ctx = _install(monkeypatch, tmp_path, allowed=False)
    _switch(monkeypatch, "1")

    body = _data_objects(_ask(lane=None))

    assert len(ctx.queue.calls) == 1
    assert set(ctx.queue.calls[0]["payload"]) == {
        "task_type",
        "message",
        "session_id",
        "username",
        "principal",
    }
    assert body[0] == {
        "type": "queued",
        "request_id": QUEUE_REQUEST_ID,
        "status": "queued",
    }


def test_a_report_lane_turn_without_an_idempotency_key_is_refused(monkeypatch, tmp_path):
    """入队必须可幂等：没有幂等键就不许悄悄收下单子。"""
    ctx = _install(monkeypatch, tmp_path)
    _switch(monkeypatch, "1")

    with pytest.raises(HTTPException) as caught:
        _ask(lane="report", idempotency=None)

    assert caught.value.status_code == 400
    assert caught.value.detail == "idempotency_key_required"
    assert ctx.queue.calls == []


def test_a_report_lane_turn_fails_closed_when_redis_is_unavailable(monkeypatch, tmp_path):
    """没有 Redis 就没有队列：这一轮要被拒，不许退化成“进程里先记着”。"""
    from app.common.reliable_queue import QueueConnectionError

    def refuse():
        raise QueueConnectionError("REDIS_URL is required for the reliable queue")

    ctx = _install(monkeypatch, tmp_path, connect=refuse)
    _switch(monkeypatch, "1")

    with pytest.raises(HTTPException) as caught:
        _ask(lane="report")

    assert caught.value.status_code == 503
    assert caught.value.detail["code"] == QueueConnectionError.code
    assert ctx.stream.calls == []


# ==================== 判据②：纯规则，零模型往返 ====================


def test_the_lane_predicate_only_reads_the_request():
    """判据②：定档只看请求字段——一个参数的纯函数，不做大小写模糊匹配。"""
    from app.api.v1 import chat

    assert list(inspect.signature(chat._queue_lane).parameters) == ["request"]
    assert chat._queue_lane(SimpleNamespace(lane="report")) == "report"
    assert chat._queue_lane(SimpleNamespace(lane="  report  ")) == "report"
    for junk in ("", None, "REPORT", "report lane", "qa", "analysis", 0, object()):
        assert chat._queue_lane(SimpleNamespace(lane=junk)) == "", junk


def test_the_lane_decision_spends_no_model_round_trip(monkeypatch, tmp_path):
    """判据②：判别加入队全程零模型往返；对照组自己证明计数器有牙。"""
    from app.agents import nodes

    ctx = _install(monkeypatch, tmp_path)
    _switch(monkeypatch, "1")

    _ask(lane="report")

    assert ctx.models.calls == []
    assert ctx.queue.calls
    # 对照组：spy 一被调用就抛，证明它不是空转的计数器。
    with pytest.raises(AssertionError, match="不许造模型"):
        nodes._make_model()
    assert len(ctx.models.calls) == 1, "计数器不涨就说明这条用例是空转"


def test_chat_py_never_grabs_a_private_name_from_the_lane_owner():
    """判据②：档位真相在 app/agents/nodes.py，本单一律不抓它的私有名。"""
    source = (REPOSITORY / "app" / "api" / "v1" / "chat.py").read_text(encoding="utf-8")

    offenders = [
        (node.lineno, node.module, alias.name)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("app.agents")
        for alias in node.names
        if alias.name.startswith("_")
    ]

    assert offenders == [], offenders


# ==================== 判据③：关页面不丢 ====================


def test_closing_the_page_right_after_queued_leaves_the_task_in_the_queue(monkeypatch, tmp_path):
    """真队列加 FakeRedis：客户端拿到 queued 就走，单子必须还在，worker 还取得到。"""
    from app.common.reliable_queue import ReliableQueue
    from tests.test_reliable_queue import FakeRedis

    queue = ReliableQueue(FakeRedis(), name="r37:enqueue", lease_seconds=30)
    ctx = _install(monkeypatch, tmp_path, queue=queue)
    _switch(monkeypatch, "1")

    response = _ask(lane="report")

    async def take_the_receipt_and_walk_away():
        first = await response.body_iterator.__anext__()
        await response.body_iterator.aclose()
        return first

    first = asyncio.run(take_the_receipt_and_walk_away())
    request_id = json.loads(first.splitlines()[1][6:])["request_id"]

    assert queue.status(request_id) == "queued"
    assert request_id in queue.redis.lists.get(queue.pending_key, [])
    assert queue.is_cancelled(request_id) is False
    assert ctx.stream.calls == [], "客户端走人不该把这一轮变成在场执行"

    reserved = queue.reserve()
    assert reserved.request_id == request_id
    assert reserved.payload["lane"] == "report"
