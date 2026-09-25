"""R227 ② —— 丢弃不许读成 `done`，也不许读成"跑完了、正文空"。

现场那一格交回的是 `{"status":"done","result":null,"failure":{"attempts":1,
"last_error":null,"max_attempts":3}}`，而 `complete()` 自己的 docstring 早就写着
"既不得发布答案也不得谎报 done"。本文件把那句话变成读数：答案键不在、状态不是 done、
`failure.last_error` 写着稳定码 `result_discarded:<reason>`，且这一轮仍会被重投。

②选的是派工单给的第二条路（把失败写进 failure 且状态不许是 done），不是新造一枚终态字面：
新增一枚 `queue/status` 状态词等于给前端 `QUEUE_SETTLED`（`scripts/r218_switch_rehearsal.py`
按 `FINAL_QUEUE_STATUSES` 逐枚核对过停表名单）留一枚永远停不干净的轮子，而 `frontend/**`
不是本单写域。
"""
from __future__ import annotations

import json
import pathlib
import re
import time
from contextlib import nullcontext

import pytest

from app.common import reliable_queue as queue_module
from app.common.reliable_queue import (
    DISCARD_REASON_CANCELLED,
    DISCARD_REASON_LEASE_LOST,
    ReliableQueue,
    RESULT_DISCARDED,
)
from tests.test_r227_lease_heartbeat import FakeClock, TickingRedis

ANSWER = "本周差旅费用环比下降 4.2%，主要来源为华东区机票集中出票。" * 40
RUN_SECONDS = 311
LEASE_SECONDS = 300


def _reserved(*, lease_seconds: int = LEASE_SECONDS, max_attempts: int = 3):
    clock = FakeClock()
    store = TickingRedis(clock)
    queue = ReliableQueue(
        store, name="r227:honest", lease_seconds=lease_seconds, max_attempts=max_attempts
    )
    request_id = queue.enqueue(
        {"message": "生成本月差旅费用分析周报", "session_id": "s-r227"}, "r227-honest"
    ).request_id
    queue.reserve()
    return queue, store, clock, request_id


def _lost_lease(queue, store, clock, request_id) -> None:
    """把"任务还在正常跑、租约自己到点"这一格走到：跑满 lease_seconds + 11 s。"""
    clock.advance(RUN_SECONDS)
    assert store.ttl(queue._lease_key(request_id)) == -2
    assert queue.is_cancelled(request_id) is False


def _legacy_complete(queue: ReliableQueue, request_id: str, result: str) -> bool:
    """R227 之前那枚 `complete()` 的逐字抄本，只给反证钉当对照物。"""
    if queue.is_cancelled(request_id) or queue._lease_lost(request_id):
        queue.redis.delete(queue._result_key(request_id))
        queue.ack(request_id)
        return False
    queue.redis.set(queue._result_key(request_id), result, ex=queue.result_ttl)
    return queue.ack(request_id)


def _honest_discard_readings(queue, request_id) -> dict:
    """契约三问：正文在不在、状态是不是 done、成因读不读得出。"""
    return {
        "answer": queue.result(request_id),
        "status": queue.status(request_id),
        "reason": queue.failure(request_id)["last_error"],
        "attempts": queue.failure(request_id)["attempts"],
    }


def _assert_honest_discard(queue, request_id) -> dict:
    readings = _honest_discard_readings(queue, request_id)
    assert readings["answer"] is None, "丢弃之后不许有正文可读"
    assert readings["status"] != "done", "丢弃之后状态不许是 done"
    assert str(readings["reason"]).startswith(RESULT_DISCARDED), "丢弃必须留下稳定码"
    assert readings["reason"], "成因不许是空串"
    return readings


# ==================== ②：两条丢弃分支都读得出成因，都不是 done ====================


def test_a_lease_discard_is_readable_and_never_reports_done():
    queue, store, clock, request_id = _reserved()
    _lost_lease(queue, store, clock, request_id)

    assert queue.complete(request_id, ANSWER) is False

    readings = _assert_honest_discard(queue, request_id)
    assert readings["reason"] == f"{RESULT_DISCARDED}:{DISCARD_REASON_LEASE_LOST}"
    assert readings["status"] == "processing", "还在处理表上等重投，不是终局"
    assert readings["attempts"] == 1, "丢弃不许吃掉重试名额"
    assert request_id in queue.redis.lrange(queue.processing_key, 0, -1)
    assert store.ttl(queue._result_key(request_id)) == -2


def test_a_cancel_discard_keeps_its_terminal_status_and_gains_a_reason():
    queue, _store, _clock, request_id = _reserved(lease_seconds=30)
    queue.cancel(request_id)

    assert queue.complete(request_id, ANSWER) is False

    readings = _assert_honest_discard(queue, request_id)
    assert readings["reason"] == f"{RESULT_DISCARDED}:{DISCARD_REASON_CANCELLED}"
    assert readings["status"] == "cancelled", "取消仍旧是终态，本单一个字没改"
    assert request_id not in queue.redis.lrange(queue.processing_key, 0, -1)


def test_the_reason_is_a_stable_code_and_carries_no_prose():
    queue, store, clock, request_id = _reserved()
    _lost_lease(queue, store, clock, request_id)
    queue.complete(request_id, ANSWER)

    reason = queue.failure(request_id)["last_error"]
    assert re.fullmatch(r"result_discarded:(cancelled|lease_lost)", reason), reason
    assert all(char.isascii() for char in reason), "稳定码不许夹中文（R16 同口径）"


def test_the_published_answer_still_reads_done_with_a_body():
    queue, _store, _clock, request_id = _reserved(lease_seconds=30)

    assert queue.complete(request_id, ANSWER) is True

    readings = _honest_discard_readings(queue, request_id)
    assert readings["status"] == "done"
    assert readings["answer"] == ANSWER
    assert readings["reason"] is None, "正常发布不许留下丢弃码"


def test_a_discarded_turn_is_requeued_and_its_second_attempt_publishes_the_answer():
    queue, store, clock, request_id = _reserved()
    _lost_lease(queue, store, clock, request_id)
    assert queue.complete(request_id, ANSWER) is False

    assert queue.requeue_expired() == 1
    assert queue.status(request_id) == "queued"
    assert queue.failure(request_id)["attempts"] == 1

    retry = queue.reserve()
    assert retry is not None and retry.request_id == request_id
    assert retry.attempts == 2
    assert queue.complete(request_id, ANSWER) is True

    assert queue.status(request_id) == "done"
    assert queue.result(request_id) == ANSWER
    #: 回收器那句 `lease_expired` 盖在上一任的丢弃码之上，两笔账都是真的：这一轮确实被
    #: 丢过一次，也确实是被重投之后才发布出来的。
    assert queue.failure(request_id)["last_error"] == "lease_expired"


def test_a_discard_on_an_unknown_request_writes_no_ledger():
    queue = ReliableQueue(TickingRedis(), name="r227:ghost")

    assert queue.complete("never-enqueued", ANSWER) is False

    assert queue.status("never-enqueued") is None
    assert queue.failure("never-enqueued") == {
        "attempts": 0,
        "last_error": None,
        "max_attempts": 3,
    }
    assert queue.redis.get(queue._message_key("never-enqueued")) is None


def test_a_corrupt_ledger_is_not_overwritten_with_a_forged_body():
    queue, store, clock, request_id = _reserved()
    _lost_lease(queue, store, clock, request_id)
    queue.redis.set(queue._message_key(request_id), "{not json")

    assert queue.complete(request_id, ANSWER) is False

    assert queue.redis.get(queue._message_key(request_id)) == "{not json"
    assert queue.status(request_id) != "done"


# ==================== 客户端那一侧真正读到了什么 ====================


def _client(monkeypatch, queue):
    from fastapi.testclient import TestClient

    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.main import app

    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)
    monkeypatch.setattr(
        auth, "get_user", lambda username: {"id": username, "username": username, "role": "admin"}
    )
    return TestClient(app), create_token("admin")


def _get(client, token, request_id):
    response = client.get(
        f"/api/v1/queue/status/{request_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return response.json()


def test_the_route_never_answers_done_with_an_empty_body(monkeypatch):
    queue, store, clock, request_id = _reserved()
    queue.redis.set(
        queue._message_key(request_id),
        json.dumps(
            {
                "request_id": request_id,
                "payload": {
                    "message": "周报",
                    "principal": {"user_id": "admin", "username": "admin"},
                },
                "attempts": 1,
            },
            ensure_ascii=False,
        ),
    )
    queue.redis.set(queue._status_key(request_id), "processing")
    queue.redis.set(queue._lease_key(request_id), "1", ex=LEASE_SECONDS)
    _lost_lease(queue, store, clock, request_id)
    client, token = _client(monkeypatch, queue)

    assert queue.complete(request_id, ANSWER) is False
    payload = _get(client, token, request_id)

    assert payload["status"] == "processing"
    assert "result" not in payload, "非 done 不许带 result 键"
    assert payload["failure"] == {
        "attempts": 1,
        "last_error": "result_discarded:lease_lost",
        "max_attempts": 3,
    }


def test_the_route_still_answers_done_with_the_body_of_the_retry(monkeypatch):
    queue, store, clock, request_id = _reserved()
    queue.redis.set(
        queue._message_key(request_id),
        json.dumps(
            {
                "request_id": request_id,
                "payload": {
                    "message": "周报",
                    "principal": {"user_id": "admin", "username": "admin"},
                },
                "attempts": 1,
            },
            ensure_ascii=False,
        ),
    )
    queue.redis.set(queue._lease_key(request_id), "1", ex=LEASE_SECONDS)
    _lost_lease(queue, store, clock, request_id)
    assert queue.complete(request_id, ANSWER) is False
    queue.requeue_expired()
    queue.reserve()
    assert queue.complete(request_id, ANSWER) is True
    client, token = _client(monkeypatch, queue)

    payload = _get(client, token, request_id)

    assert payload["status"] == "done"
    assert payload["result"] == ANSWER


# ==================== worker 侧：接线与取证 ====================


def _worker_payload(**overrides):
    payload = {
        "message": "生成本月差旅费用分析周报",
        "session_id": "s-worker",
        "principal": {"user_id": "u-worker", "username": "worker-user", "roles": ["staff"]},
    }
    payload.update(overrides)
    return payload


def _contract_result(answer: str):
    from app.agents.contracts import AgentResult

    return AgentResult(
        worker="orchestrator",
        status="success",
        answer=answer,
        request_id="req-r227",
        trace_id="trace-r227",
        task_id="task-r227",
    )


class _WatchingQueue(ReliableQueue):
    """记下 `complete()` 那一刻心跳还在不在活着——续租的作用域必须盖住发布。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.beats = []
        self.alive_at_complete = None

    def lease_heartbeat(self, request_id, **kwargs):
        heartbeat = super().lease_heartbeat(request_id, **kwargs)
        self.beats.append(heartbeat)
        return heartbeat

    def complete(self, request_id, result):
        current = self.beats[-1] if self.beats else None
        self.alive_at_complete = bool(current and current.running)
        return super().complete(request_id, result)


def _install_worker(monkeypatch, queue, *, seconds: float):
    import deploy.queue_worker as worker

    monkeypatch.setattr(worker, "_queue", queue)
    monkeypatch.setattr(worker, "record_agent_result", lambda record, **kwargs: {})

    def slow_run(*_args, **_kwargs):
        time.sleep(seconds)
        return _contract_result(ANSWER)

    monkeypatch.setattr("app.agents.orchestrator.run_orchestrator_result", slow_run)
    return worker


def test_a_turn_longer_than_the_lease_publishes_when_the_worker_is_wired(monkeypatch):
    """微缩现场：跑 3.6 s > lease 3 s，就是 311 s > 300 s 的等比抄本，走的是真线程。

    这里必须用**真钟**的 Redis 替身：假时钟只认 `advance()`，真 sleep 不让它走一步，
    那一轮就跑不出"租约先到期"的形状，判据会变成一枚空钉。
    """
    queue = _WatchingQueue(
        TickingRedis(clock=time.monotonic), name="r227:worker", lease_seconds=3
    )
    request_id = queue.enqueue(_worker_payload(), "r227-worker-ok").request_id
    worker = _install_worker(monkeypatch, queue, seconds=3.6)

    assert worker.process_one() is True

    beat = queue.beats[-1]
    assert queue.alive_at_complete is True, "complete() 必须落在心跳作用域里面"
    assert beat.renewals >= 2, f"3.6 s 的跑程至少该落两拍，实测 {beat.renewals}"
    assert beat.stopped_reason == "manual"
    assert queue.status(request_id) == "done"
    assert queue.result(request_id) == ANSWER


def test_counter_evidence_unwiring_the_beat_from_the_worker_loses_a_long_turn(monkeypatch):
    """把 worker 那一行接线拆掉（`_lease_beat` 交回空作用域）——同一轮必须重新丢答案。"""
    queue = _WatchingQueue(
        TickingRedis(clock=time.monotonic), name="r227:worker-red", lease_seconds=3
    )
    request_id = queue.enqueue(_worker_payload(), "r227-worker-red").request_id
    worker = _install_worker(monkeypatch, queue, seconds=3.6)
    monkeypatch.setattr(worker, "_lease_beat", lambda _queue, _request_id: nullcontext())

    assert worker.process_one() is True

    assert queue.beats == [], "拆了线就不该再有心跳被起来"
    assert queue.result(request_id) is None
    assert queue.status(request_id) == "processing", "谎报 done 已经不可能，但答案确实没了"
    assert queue.failure(request_id)["last_error"] == "result_discarded:lease_lost"


def test_the_worker_falls_back_when_the_queue_cannot_renew(monkeypatch):
    import deploy.queue_worker as worker

    class _LegacyStub:
        def __init__(self):
            self.completed = []

        def reserve(self, timeout=0):
            return type("M", (), {"request_id": "req-stub", "payload": _worker_payload()})()

        def complete(self, request_id, result):
            self.completed.append((request_id, result))
            return True

    stub = _LegacyStub()
    monkeypatch.setattr(worker, "_queue", stub)
    monkeypatch.setattr(worker, "record_agent_result", lambda record, **kwargs: {})
    monkeypatch.setattr(
        "app.agents.orchestrator.run_orchestrator_result",
        lambda *_args, **_kwargs: _contract_result(ANSWER),
    )

    assert worker.process_one() is True
    assert stub.completed == [("req-stub", ANSWER)]
    assert worker._lease_beat(object(), "req-stub").__enter__() is None


def test_the_discard_line_and_the_cause_line_are_logged_together(monkeypatch, caplog):
    import logging

    import deploy.queue_worker as worker

    queue = ReliableQueue(TickingRedis(), name="r227:log", lease_seconds=30)
    request_id = queue.enqueue(_worker_payload(), "r227-log").request_id
    monkeypatch.setattr(worker, "_queue", queue)
    monkeypatch.setattr(worker, "record_agent_result", lambda record, **kwargs: {})
    monkeypatch.setattr(
        "app.agents.orchestrator.run_orchestrator_result",
        lambda *_args, **_kwargs: (
            queue.cancel(request_id),  # 运行途中被取消：reserve 之后才落下那一枚取消标记
            _contract_result(ANSWER),
        )[1],
    )
    with caplog.at_level(logging.INFO):
        assert worker.process_one() is True

    messages = [record.getMessage() for record in caplog.records]
    assert (
        f"request_id={request_id} 结果已丢弃：运行途中被取消或租约已丢失 terminal_status=cancelled"
        in messages
    ), "R81 钉住的那句逐字文案一个字没动"
    assert (
        f"[QueueWorker] request_id={request_id} 丢弃成因 reason=result_discarded:cancelled"
        in messages
    )
    assert queue.result(request_id) is None


def test_an_early_lease_stop_is_warned_with_its_readings(monkeypatch, caplog):
    import logging

    from app.common.reliable_queue import LeaseHeartbeat
    from deploy import queue_worker

    warn_queue = ReliableQueue(TickingRedis(), name="r227:warn", lease_seconds=30)
    heartbeat = queue_worker._lease_beat(warn_queue, "req-warn")
    heartbeat.renewals = 2
    heartbeat.stopped_reason = LeaseHeartbeat.STOP_LEASE_LOST
    with caplog.at_level(logging.WARNING):
        queue_worker._report_lease(heartbeat, "req-warn")

    written = " ".join(record.getMessage() for record in caplog.records)
    assert "租约心跳提前停表" in written
    assert "reason=lease_lost" in written and "renewals=2" in written
    assert "refusals=0" in written

    caplog.clear()
    quiet = ReliableQueue(TickingRedis(), name="r227:quiet", lease_seconds=30)
    with queue_worker._lease_beat(quiet, "req-quiet"):
        pass
    with caplog.at_level(logging.WARNING):
        queue_worker._report_lease(quiet.lease_heartbeat("req-quiet"), "req-quiet")
    assert caplog.records == [], "正常跑完的一轮不许在告警面上留一行噪音"


# ==================== 反证钉 ====================


def test_counter_evidence_the_old_guard_reproduces_the_field_lie(monkeypatch):
    queue, store, clock, request_id = _reserved()
    _lost_lease(queue, store, clock, request_id)

    assert _legacy_complete(queue, request_id, ANSWER) is False

    assert queue.status(request_id) == "done", "对照物必须是当年那枚谎报"
    assert queue.result(request_id) is None
    assert queue.failure(request_id) == {
        "attempts": 1,
        "last_error": None,
        "max_attempts": 3,
    }
    with pytest.raises(AssertionError):
        _assert_honest_discard(queue, request_id)


def test_counter_evidence_silencing_the_reason_write_blinds_only_the_cause():
    queue, store, clock, request_id = _reserved()
    _lost_lease(queue, store, clock, request_id)
    queue._record_discard = lambda request_id, reason: None  # 摘掉写账这一格

    assert queue.complete(request_id, ANSWER) is False

    assert queue.status(request_id) == "processing", "状态那一格仍旧是诚实的"
    assert queue.result(request_id) is None
    assert queue.failure(request_id)["last_error"] is None, "这一枚钉红的就是成因"


def test_counter_evidence_a_lost_lease_discard_that_still_acks_lies_about_done():
    """所有权已丢的那一支要是还去 `ack()`，谎报立刻回来——这一枚钉红的就是本格。"""
    queue, _store, _clock, request_id = _reserved()
    queue.redis.set(queue._lease_key(request_id), "1", ex=LEASE_SECONDS)

    def _discard_then_ack(rid, result):
        queue.redis.delete(queue._result_key(rid))
        queue.ack(rid)
        return False

    queue.complete = _discard_then_ack  # type: ignore[method-assign]
    assert queue.complete(request_id, ANSWER) is False
    assert queue.result(request_id) is None
    assert queue.status(request_id) == "done", "摘掉所有权守卫，谎报 done 就回来了"
    with pytest.raises(AssertionError):
        _assert_honest_discard(queue, request_id)


def test_the_contract_sentence_lives_where_the_code_does():
    """契约句子的可执行版本就写在 `complete()` 的 docstring 里，漂了就红。"""
    doc = pathlib.Path(queue_module.__file__).read_text(encoding="utf-8")
    block = re.search(r"def complete\(self.*?\n    def ", doc, re.S).group(0)

    assert "既不得发布答案也不得谎报 done" in block
    assert "result_discarded" in block
    assert "状态**不是** `done`" in block
    assert "requeue_expired" in block


def test_the_status_vocabulary_gained_no_new_terminal_word():
    """②走的是"写进 failure"那条路：状态词表一个新字都没加，停表名单不必跟着改。"""
    written = set(
        re.findall(
            r'self\.redis\.set\(self\._status_key\(request_id\),\s*"([a-z_]+)"\)',
            pathlib.Path(queue_module.__file__).read_text(encoding="utf-8"),
        )
    )
    assert written == {
        "cancelled",
        "cancel_requested",
        "dead",
        "done",
        "failed",
        "processing",
        "queued",
    }
    assert "result_discarded" not in written
    assert "discarded" not in written
