"""R227 ① —— 报告档那 311 s 到底踩了哪一支，以及租约怎么跟着运行时长走。

根因形状：历轮用例从来表达不出"跑到一半租约自己到期"这件事 ——
`tests/test_reliable_queue.py` 里那枚 FakeRedis 把 `set(..., ex=)` 直接吞了（它连
`expire` 都没有），所以"租约过期"从前只能靠手工 `redis.delete(lease_key)` 模拟"已经被
回收"，而"任务还在正常跑、租约到点了"这一格压根没有量具。本文件带一枚会真的让键到期的
时钟 Redis，把那一格量出来。

现场读数（总控 09-25 亲测，原文时序）：09:26:57 入队 → 09:32:12 `[doc] 完成
status=success 结果 1519 字` → 09:32:14 丢弃 → 队列交回
`{"status":"done","result":null,"failure":{"attempts":1,"last_error":null,"max_attempts":3}}`，
且 `enterprise-brain:tasks:result:3d37af0e…` 的 TTL=-2。
"""
from __future__ import annotations

import inspect
import math
import pathlib
import re
import threading
import time

import pytest

from app.common import reliable_queue as queue_module
from app.common.reliable_queue import (
    LEASE_HEARTBEAT_DIVISOR,
    LEASE_HEARTBEAT_MIN_INTERVAL_SECONDS,
    LEASE_MAX_RENEW_SECONDS_DEFAULT,
    LeaseHeartbeat,
    ReliableQueue,
    connect_reliable_queue,
    lease_renew_budget,
)

#: 现场那几枚数，本文件按抄本使用，出处是总控 09-25 的日志时序。
FIELD_RUN_SECONDS = 311
FIELD_LEASE_SECONDS = 300
FIELD_ANSWER_CHARS = 1519
FIELD_READOUT = {
    "status": "done",
    "result": None,
    "failure": {"attempts": 1, "last_error": None, "max_attempts": 3},
}
PRODUCTION_QUEUE_NAME = "enterprise-brain:tasks"


class FakeClock:
    """一枚能被测试推着走的单调钟。"""

    def __init__(self, start: float = 1_000.0):
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += float(seconds)
        return self.now


class TickingRedis:
    """Redis 里带过期语义的那一小撮命令，全部按注入的钟判定到期。

    `ttl` 与真 Redis 同口径：-2 = 键不存在，-1 = 在但没设过期。`expire` 对不存在的键
    返回 0 —— 这一枚返回值就是"续租不许复活已被回收的租约"的全部依据。
    """

    def __init__(self, clock: FakeClock | None = None):
        self.clock = clock or FakeClock()
        self.values: dict[str, str] = {}
        self.deadline: dict[str, float] = {}
        self.lists: dict[str, list[str]] = {}
        self.expire_calls = 0

    # ---- keys ---------------------------------------------------------------
    def _purge(self, key: str) -> None:
        at = self.deadline.get(key)
        if at is not None and at <= self.clock():
            self.values.pop(key, None)
            self.deadline.pop(key, None)

    def ping(self) -> bool:
        return True

    def get(self, key: str):
        self._purge(key)
        return self.values.get(key)

    def set(self, key: str, value, ex=None):
        self.values[key] = str(value)
        if ex is None:
            self.deadline.pop(key, None)
        else:
            self.deadline[key] = self.clock() + float(ex)
        return True

    def delete(self, key: str):
        self.deadline.pop(key, None)
        return int(self.values.pop(key, None) is not None)

    def exists(self, key: str):
        self._purge(key)
        return int(key in self.values)

    def expire(self, key: str, seconds):
        self.expire_calls += 1
        self._purge(key)
        if key not in self.values:
            return 0
        self.deadline[key] = self.clock() + float(seconds)
        return 1

    def ttl(self, key: str) -> int:
        self._purge(key)
        if key not in self.values:
            return -2
        at = self.deadline.get(key)
        if at is None:
            return -1
        return int(math.ceil(at - self.clock()))

    # ---- lists --------------------------------------------------------------
    def rpush(self, key: str, value):
        self.lists.setdefault(key, []).append(str(value))
        return len(self.lists[key])

    def rpoplpush(self, source: str, destination: str):
        items = self.lists.get(source, [])
        if not items:
            return None
        value = items.pop()
        self.lists.setdefault(destination, []).insert(0, value)
        return value

    def brpoplpush(self, source: str, destination: str, timeout: int = 0):
        return self.rpoplpush(source, destination)

    def lrem(self, key: str, count: int, value: str):
        items = self.lists.get(key, [])
        removed = 0
        remaining = []
        for item in items:
            if item == value and (count == 0 or removed < count):
                removed += 1
                continue
            remaining.append(item)
        self.lists[key] = remaining
        return removed

    def lrange(self, key: str, start: int, end: int):
        items = self.lists.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]

    def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))


def _queue(*, lease_seconds: int = FIELD_LEASE_SECONDS, max_attempts: int = 3) -> tuple:
    clock = FakeClock()
    store = TickingRedis(clock)
    queue = ReliableQueue(
        store, name="r227:tasks", lease_seconds=lease_seconds, max_attempts=max_attempts
    )
    return queue, store, clock


def _reserved(*, lease_seconds: int = FIELD_LEASE_SECONDS) -> tuple:
    queue, store, clock = _queue(lease_seconds=lease_seconds)
    message = queue.enqueue({"message": "生成本月差旅费用分析周报"}, "r227-idem")
    reserved = queue.reserve()
    assert reserved is not None and reserved.request_id == message.request_id
    return queue, store, clock, message.request_id


def _legacy_complete(queue: ReliableQueue, request_id: str, result: str) -> bool:
    """R227 之前那枚 `complete()` 的逐字抄本，只用来复现当年的谎报。"""
    if queue.is_cancelled(request_id) or queue._lease_lost(request_id):
        queue.redis.delete(queue._result_key(request_id))
        queue.ack(request_id)
        return False
    queue.redis.set(queue._result_key(request_id), result, ex=queue.result_ttl)
    return queue.ack(request_id)


def _readout(queue: ReliableQueue, request_id: str) -> dict:
    """`/api/v1/queue/status` 在这一格会交回的三枚读数（不含 request_id）。"""
    return {
        "status": queue.status(request_id),
        "result": queue.result(request_id),
        "failure": queue.failure(request_id),
    }


def _run_the_311_second_turn(queue, store, clock, request_id, *, heartbeat=None) -> dict:
    """把现场那一轮（311 s、1519 字）在假时钟上走完，交回发布前后的读数。

    心跳默认不起线程、由这一秒一秒推着走：311 秒的真等在全量门里跑不动，而跑不动的
    判据等于没有判据。
    """
    beat = heartbeat or queue.lease_heartbeat(request_id, clock=clock)
    for _ in range(FIELD_RUN_SECONDS):
        clock.advance(1)
        beat.beat()
    #: `lease_ttl` 必须取在发布之前——ack() 会把租约键删掉，那是所有权释放，不是过期。
    lease_ttl = store.ttl(queue._lease_key(request_id))
    published = queue.complete(request_id, "报" * FIELD_ANSWER_CHARS)
    return {
        "heartbeat": beat,
        "published": published,
        "lease_ttl": lease_ttl,
        "lease_released": store.ttl(queue._lease_key(request_id)) == -2,
        "still_listed": request_id in queue.redis.lrange(queue.processing_key, 0, -1),
        "answer_chars": len(queue.result(request_id) or ""),
        "readout": _readout(queue, request_id),
    }


# ==================== 现值：租约多长、谁在续、多久续一次 ====================


def test_the_production_lease_is_300_seconds_and_the_factory_passes_no_override():
    default = inspect.signature(ReliableQueue.__init__).parameters["lease_seconds"].default
    assert default == FIELD_LEASE_SECONDS

    store = TickingRedis()
    queue = connect_reliable_queue("redis://127.0.0.1:6379/0", redis_factory=lambda _url: store)
    assert queue.lease_seconds == FIELD_LEASE_SECONDS

    message = queue.enqueue({"message": "周报"}, "r227-factory")
    queue.reserve()
    #: 键名与现场同一层：总控直查 TTL=-2 的那一枚就是 `...:result:<request_id>`。
    assert queue.name == PRODUCTION_QUEUE_NAME
    assert queue._lease_key(message.request_id) == (
        PRODUCTION_QUEUE_NAME + ":lease:" + message.request_id
    )
    assert queue._result_key(message.request_id) == (
        PRODUCTION_QUEUE_NAME + ":result:" + message.request_id
    )
    assert store.ttl(queue._lease_key(message.request_id)) == FIELD_LEASE_SECONDS


def test_the_lease_is_written_once_and_extended_only_by_the_beat():
    """①第三问"运行途中有没有人续租"的静态答案：改前一个都没有，改后只有心跳这一处。"""
    source = pathlib.Path(queue_module.__file__).read_text(encoding="utf-8")

    lease_writes = re.findall(
        r"self\.redis\.set\(self\._lease_key\(request_id\)[^\n]*", source
    )
    lease_extends = re.findall(
        r"self\.redis\.expire\(self\._lease_key\(request_id\)[^\n]*", source
    )
    assert lease_writes == [
        "self.redis.set(self._lease_key(request_id), \"1\", ex=self.lease_seconds)"
    ], "reserve 之外再写租约 = 又一处无人认领的所有权"
    assert len(lease_extends) == 1
    assert source.count("def renew_lease(") == 1
    assert source.count("self.queue.renew_lease(") == 1, "续租只有心跳这一个调用点"

    worker_source = pathlib.Path(
        pathlib.Path(queue_module.__file__).resolve().parents[2] / "deploy" / "queue_worker.py"
    ).read_text(encoding="utf-8")
    body = re.search(r"def process_one\(\):.*?\n\n\ndef ", worker_source, re.S).group(0)
    assert worker_source.count('getattr(queue, "lease_heartbeat", None)') == 1
    assert body.index("_lease_beat(queue, message.request_id)") < body.index(
        "_process_reserved(queue, message)"
    ), "心跳必须在领走之后、跑图之前起"
    assert "with heartbeat:" in body and "_report_lease(heartbeat" in body


def test_the_beat_cadence_is_one_third_of_the_lease_with_a_one_second_floor():
    queue, _store, _clock = _queue()
    heartbeat = queue.lease_heartbeat("r227-cadence")
    assert heartbeat.interval_seconds == pytest.approx(
        FIELD_LEASE_SECONDS / LEASE_HEARTBEAT_DIVISOR
    )
    assert heartbeat.budget_seconds == float(LEASE_MAX_RENEW_SECONDS_DEFAULT)

    short = ReliableQueue(TickingRedis(), name="r227:short", lease_seconds=2)
    assert short.lease_heartbeat("r227-floor").interval_seconds == pytest.approx(
        LEASE_HEARTBEAT_MIN_INTERVAL_SECONDS
    )


def test_the_renew_fuse_cannot_be_configured_off(monkeypatch):
    monkeypatch.delenv("QUEUE_LEASE_MAX_RENEW_SECONDS", raising=False)
    assert lease_renew_budget() == float(LEASE_MAX_RENEW_SECONDS_DEFAULT)
    for garbage in ("", "0", "-5", "not-a-number", "1e9", "nan", "inf"):
        monkeypatch.setenv("QUEUE_LEASE_MAX_RENEW_SECONDS", garbage)
        assert lease_renew_budget() == float(LEASE_MAX_RENEW_SECONDS_DEFAULT), garbage
    monkeypatch.setenv("QUEUE_LEASE_MAX_RENEW_SECONDS", "600")
    assert lease_renew_budget() == 600.0


def test_a_beat_does_not_touch_redis_before_it_is_due():
    queue, store, clock, request_id = _reserved(lease_seconds=30)
    heartbeat = queue.lease_heartbeat(request_id, interval_seconds=10, clock=clock)

    for _ in range(9):
        clock.advance(1)
        assert heartbeat.beat() is True
    assert store.expire_calls == 0

    clock.advance(1)
    assert heartbeat.beat() is True
    assert store.expire_calls == 1
    assert store.ttl(queue._lease_key(request_id)) == 30


# ==================== ① 到底是哪一支触发的 ====================


def test_a_311_second_run_reads_as_lease_loss_and_not_cancellation():
    queue, store, clock, request_id = _reserved()

    assert queue.is_cancelled(request_id) is False
    clock.advance(FIELD_RUN_SECONDS)

    assert queue.is_cancelled(request_id) is False
    assert queue._lease_lost(request_id) is True
    assert store.ttl(queue._lease_key(request_id)) == -2


def test_only_the_lease_branch_reproduces_the_field_readout():
    """现场那枚 `status=done` + `result=null` 只可能出自租约那一支。"""
    queue, store, clock, request_id = _reserved()
    clock.advance(FIELD_RUN_SECONDS)
    assert _legacy_complete(queue, request_id, "报" * FIELD_ANSWER_CHARS) is False
    assert _readout(queue, request_id) == FIELD_READOUT
    assert store.ttl(queue._result_key(request_id)) == -2

    armed = ReliableQueue(TickingRedis(), name="r227:cancel", lease_seconds=300)
    cancelled = armed.enqueue({"message": "周报"}, "r227-cancel")
    armed.reserve()
    armed.cancel(cancelled.request_id)
    assert _legacy_complete(armed, cancelled.request_id, "报" * FIELD_ANSWER_CHARS) is False
    assert armed.status(cancelled.request_id) == "cancelled"
    assert armed.status(cancelled.request_id) != FIELD_READOUT["status"], (
        "取消那一支交不回现场那枚 done —— 当年触发它的就不是取消"
    )


# ==================== ① 的修法：租约跟着运行时长走 ====================


def test_the_beat_keeps_the_311_second_turn_publishable():
    queue, store, clock, request_id = _reserved()

    readings = _run_the_311_second_turn(queue, store, clock, request_id)
    beat = readings["heartbeat"]

    assert beat.renewals == 3, "311 s 里应当落三拍（100/200/300 s）"
    assert beat.refusals == 0
    assert beat.stopped_reason is None
    #: 最后一拍在 +300 s 把 TTL 重置成 300，走到 +311 s 还剩 289 —— 关键读数是它没归零。
    assert readings["lease_ttl"] == 289
    assert readings["lease_released"] is True, "发布之后租约应当随 ack 释放"
    assert readings["published"] is True
    assert readings["still_listed"] is False, "发布成功就该从处理表上摘下来"
    assert readings["answer_chars"] == FIELD_ANSWER_CHARS
    assert readings["readout"]["status"] == "done"


def test_the_beat_refuses_to_resurrect_a_requeued_lease():
    queue, store, clock, request_id = _reserved(lease_seconds=30)
    heartbeat = queue.lease_heartbeat(request_id, clock=clock)

    clock.advance(31)
    assert queue.requeue_expired() == 1
    assert queue.status(request_id) == "queued"

    assert heartbeat.beat() is False
    assert heartbeat.renewals == 0
    assert heartbeat.refusals == 1
    assert heartbeat.stopped_reason == LeaseHeartbeat.STOP_LEASE_LOST
    assert store.expire_calls == 1, "EXPIRE 真的打出去了，是 Redis 说不行"
    assert store.ttl(queue._lease_key(request_id)) == -2


def test_a_stopped_beat_lets_the_lease_lapse_within_one_ttl():
    """崩溃/停表之后的检测速度：仍旧是一个 lease_seconds，心跳没把它拖慢。"""
    queue, store, clock, request_id = _reserved()
    heartbeat = queue.lease_heartbeat(request_id, clock=clock)

    for _ in range(150):
        clock.advance(1)
        heartbeat.beat()
    assert heartbeat.renewals == 1
    heartbeat.stop()
    assert heartbeat.stopped_reason == LeaseHeartbeat.STOP_MANUAL

    #: 最后一拍落在 +100 s，把 TTL 重置成 300 ⇒ 检测点 = +400 s，即停表后不到一枚 lease_seconds。
    clock.advance(249)
    assert queue._lease_lost(request_id) is False, "停表 249 s（最后一拍后 299 s）租约还在"
    clock.advance(2)
    assert queue._lease_lost(request_id) is True
    assert store.ttl(queue._lease_key(request_id)) == -2
    assert queue.requeue_expired() == 1
    assert queue.status(request_id) == "queued"


def test_the_renew_fuse_releases_a_wedged_but_alive_worker():
    queue, store, clock, request_id = _reserved(lease_seconds=30)
    heartbeat = queue.lease_heartbeat(
        request_id, interval_seconds=10, budget_seconds=25, clock=clock
    )

    for _ in range(31):
        clock.advance(1)
        heartbeat.beat()

    assert heartbeat.renewals == 2
    assert heartbeat.stopped_reason == LeaseHeartbeat.STOP_BUDGET
    clock.advance(30)
    assert store.ttl(queue._lease_key(request_id)) == -2
    assert queue.requeue_expired() == 1
    assert queue.status(request_id) == "queued"


def test_a_beat_survives_a_client_that_cannot_extend_leases():
    """不会 `expire` 的客户端（用例里那只 FakeRedis 就是）只许让心跳停表，不许掀翻进程。"""

    class _NoExpire(TickingRedis):
        def expire(self, key, seconds):
            raise AttributeError("this vintage of redis client has no EXPIRE")

    clock = FakeClock()
    store = _NoExpire(clock)
    queue = ReliableQueue(store, name="r227:noexpire", lease_seconds=30)
    request_id = queue.enqueue({"message": "周报"}, "r227-noexpire").request_id
    queue.reserve()
    heartbeat = queue.lease_heartbeat(request_id, interval_seconds=5, clock=clock)

    clock.advance(5)
    assert heartbeat.beat() is False
    assert heartbeat.stopped_reason == LeaseHeartbeat.STOP_RENEW_ERROR
    assert heartbeat.renewals == 0
    with pytest.raises(AttributeError):
        queue.renew_lease(request_id)


def test_the_real_thread_renews_without_being_told_to():
    """线程那一支也亲自跑一次：假时钟证不了 `Event.wait` 真会把拍子送到。"""
    queue, store, _clock, request_id = _reserved(lease_seconds=60)
    heartbeat = queue.lease_heartbeat(request_id, interval_seconds=0.05)

    with heartbeat:
        deadline = time.monotonic() + 2.0
        while heartbeat.renewals < 3 and time.monotonic() < deadline:
            time.sleep(0.01)

    assert heartbeat.renewals >= 3
    assert heartbeat.running is False
    assert store.ttl(queue._lease_key(request_id)) == 60


def test_the_heartbeat_thread_is_never_left_running_after_the_with_block():
    queue, _store, _clock, request_id = _reserved(lease_seconds=60)
    before = threading.active_count()

    with queue.lease_heartbeat(request_id, interval_seconds=0.05):
        assert threading.active_count() == before + 1
    assert threading.active_count() == before


# ==================== 反证钉：摘掉续租，症状必须当场回来 ====================


def test_counter_evidence_a_renewal_that_does_not_extend_the_key_loses_the_answer(monkeypatch):
    """"续租"写成"看一眼键还在就报活"（不写 EXPIRE）——311 s 那一格必须重新变红。"""

    def _look_but_do_not_extend(self, request_id: str) -> bool:
        return bool(self.redis.exists(self._lease_key(request_id)))

    monkeypatch.setattr(ReliableQueue, "renew_lease", _look_but_do_not_extend)
    queue, store, clock, request_id = _reserved()

    readings = _run_the_311_second_turn(queue, store, clock, request_id)
    beat = readings["heartbeat"]

    assert beat.renewals == 2, "假续租应当骗过前两拍，否则这枚钉是空的"
    assert beat.stopped_reason == LeaseHeartbeat.STOP_LEASE_LOST
    assert readings["published"] is False
    assert readings["answer_chars"] == 0
    assert readings["readout"]["status"] != "done"
    assert readings["readout"]["failure"]["last_error"] == "result_discarded:lease_lost"


def test_counter_evidence_deleting_the_beat_call_site_turns_the_cadence_pin_red():
    """把 `LeaseHeartbeat.beat` 换成"什么都不做"，同一套读数必须回到丢答案那一侧。"""
    queue, store, clock, request_id = _reserved()
    heartbeat = queue.lease_heartbeat(request_id, clock=clock)
    heartbeat.beat = lambda now=None: True  # 拆掉守卫：拍子还在打，租约不再续

    readings = _run_the_311_second_turn(queue, store, clock, request_id, heartbeat=heartbeat)

    assert readings["published"] is False
    assert readings["lease_ttl"] == -2
    assert readings["answer_chars"] == 0
    assert readings["still_listed"] is True, "丢弃的那一任不许替回收器把消息摘掉"
