"""R155：把「队列已满」变成一枚能被读到的状态。

钉的是 `app/common/reliable_queue.py` 的容量/深度读数面：`parse_queue_capacity`、
`pending_depth` / `processing_depth` / `dead_letter_depth`、`ReliableQueue.stats`，
以及 `connect_reliable_queue` 那枚从环境里读上限的通道。判据出处：跟进单 §79 三 R155。

本单只交读数，不交策略：满了之后拒收、排队上限还是降级，是业主裁定。所以这里同时
钉死「入队语义一个字都没变」——超出上限的第 N 条消息照样收进队列。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.common.reliable_queue import (
    CAPACITY_SOURCE_ENV,
    CAPACITY_SOURCE_INVALID,
    CAPACITY_SOURCE_NOT_CONFIGURED,
    DEPTH_SOURCE_REDIS_LLEN,
    QUEUE_CAPACITY_ENV,
    QueueConnectionError,
    ReliableQueue,
    connect_reliable_queue,
    parse_queue_capacity,
)
from tests.test_reliable_queue import FakeRedis

WRITES = {"set", "delete", "rpush", "lrem", "rpoplpush", "brpoplpush"}


class ReadableRedis(FakeRedis):
    """给共享存储补上 LLEN，并逐条记账。

    记账的用意有两处：证明深度是服务端 LLEN 数出来的（不是把整条列表拉回进程里
    len 一遍），证明 stats() 是一个字都不写的被动观测面。
    """

    def __init__(self):
        super().__init__()
        self.command_log: list[str] = []
        self.depth_reads: list[str] = []

    def _log(self, name: str) -> None:
        self.command_log.append(name)

    def llen(self, key: str) -> int:
        self._log("llen")
        self.depth_reads.append(key)
        return len(self.lists.get(key, []))

    def get(self, key: str):
        self._log("get")
        return super().get(key)

    def set(self, key: str, value, ex=None):
        self._log("set")
        return super().set(key, value, ex=ex)

    def delete(self, key: str):
        self._log("delete")
        return super().delete(key)

    def rpush(self, key: str, value):
        self._log("rpush")
        return super().rpush(key, value)

    def lrem(self, key: str, count: int, value: str):
        self._log("lrem")
        return super().lrem(key, count, value)

    def rpoplpush(self, source: str, destination: str):
        self._log("rpoplpush")
        return super().rpoplpush(source, destination)

    def lrange(self, key: str, start: int, end: int):
        self._log("lrange")
        return super().lrange(key, start, end)

    def ping(self):
        self._log("ping")
        return True

    def writes_since_start(self) -> list[str]:
        return [name for name in self.command_log if name in WRITES]


def _authed(monkeypatch):
    """/api/v1/queue/stats 走全局 AuthMiddleware：借用既有测试的登录接缝，不新造一套。"""
    from app.common import auth
    from app.common.auth import create_token

    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {"id": username, "username": username, "role": "admin"},
    )
    return {"Authorization": f"Bearer {create_token('admin')}"}


def _queue(store: ReadableRedis, **options) -> ReliableQueue:
    return ReliableQueue(store, name="r155:tasks", lease_seconds=30, **options)


def _enqueue(queue: ReliableQueue, count: int, tag: str) -> list[str]:
    return [queue.enqueue({"message": f"{tag}-{n}"}, f"{tag}-{n}").request_id for n in range(count)]


def test_stats_reports_declared_capacity_and_live_depth():
    store = ReadableRedis()
    queue = _queue(store, capacity=3)
    _enqueue(queue, 2, "cap3")

    reading = queue.stats()

    assert reading["queue_length"] == 2
    assert reading["processing"] == 0
    assert reading["capacity"] == 3
    assert reading["remaining"] == 1
    assert reading["saturated"] is False
    assert reading["depth_source"] == DEPTH_SOURCE_REDIS_LLEN
    assert reading["capacity_source"] == "constructor"


def test_the_reading_is_shared_state_not_a_per_process_counter():
    """两枚队列对象共用一份 Redis = 两个 API 副本 / 一个副本加一个 worker。

    任何"本进程记一笔账"的实现都会在这里当场红：A 入队、B 读数，B 必须看得见。
    """
    store = ReadableRedis()
    api = _queue(store, capacity=2)
    worker = _queue(store, capacity=2)

    _enqueue(api, 2, "shared")

    assert worker.stats()["queue_length"] == 2
    assert worker.stats()["saturated"] is True
    assert api.stats()["saturated"] is True

    assert worker.reserve() is not None

    assert api.stats() == worker.stats()
    assert api.stats()["queue_length"] == 1
    assert api.stats()["processing"] == 1
    assert api.stats()["saturated"] is False


def test_saturated_turns_true_at_capacity_while_enqueue_still_accepts_more():
    """判据③：满是一种状态，不是一种行为。超限那条消息照样得排进去。"""
    store = ReadableRedis()
    queue = _queue(store, capacity=2)
    _enqueue(queue, 2, "policy")

    assert queue.stats()["saturated"] is True
    third = queue.enqueue({"message": "policy-2"}, "policy-2")

    assert third.request_id
    assert queue.status(third.request_id) == "queued"
    assert queue.stats()["queue_length"] == 3
    assert queue.stats()["remaining"] == 0
    assert queue.stats()["saturated"] is True


def test_capacity_unset_reads_as_unknown_not_zero_and_not_full():
    store = ReadableRedis()
    queue = _queue(store)
    _enqueue(queue, 1, "unset")

    reading = queue.stats()

    assert reading["queue_length"] == 1
    assert reading["capacity"] is None
    assert reading["remaining"] is None
    #: 「读不到」与「还没满」是两句话；这里一旦写成 false，前端就会把没配置画成没满。
    assert reading["saturated"] is None
    assert reading["capacity_source"] == CAPACITY_SOURCE_NOT_CONFIGURED


@pytest.mark.parametrize(
    ("raw", "want_capacity", "want_source"),
    [
        ("50", 50, CAPACITY_SOURCE_ENV),
        ("  50  ", 50, CAPACITY_SOURCE_ENV),
        ("", None, CAPACITY_SOURCE_NOT_CONFIGURED),
        ("   ", None, CAPACITY_SOURCE_NOT_CONFIGURED),
        (None, None, CAPACITY_SOURCE_NOT_CONFIGURED),
        ("abc", None, CAPACITY_SOURCE_INVALID),
        ("0", None, CAPACITY_SOURCE_INVALID),
        ("-3", None, CAPACITY_SOURCE_INVALID),
        ("true", None, CAPACITY_SOURCE_INVALID),
        ("2.5", None, CAPACITY_SOURCE_INVALID),
    ],
)
def test_declared_capacity_is_parsed_or_reported_as_unreadable(raw, want_capacity, want_source):
    assert parse_queue_capacity(raw) == (want_capacity, want_source)


def test_an_unreadable_capacity_config_never_breaks_the_queue(monkeypatch):
    """配置写坏了也只该让读数变 null，不该让入队 500——那是把观测事故升级成生产事故。"""
    monkeypatch.setenv(QUEUE_CAPACITY_ENV, "not-a-number")
    store = ReadableRedis()
    queue = connect_reliable_queue("redis://offline.invalid:0/9", redis_factory=lambda url: store)

    assert queue.capacity is None
    assert queue.stats()["capacity_source"] == CAPACITY_SOURCE_INVALID
    assert queue.enqueue({"message": "still-accepted"}, "bad-config") is not None


def test_connect_reliable_queue_passes_the_declared_capacity_through(monkeypatch):
    monkeypatch.setenv(QUEUE_CAPACITY_ENV, "7")
    store = ReadableRedis()

    queue = connect_reliable_queue("redis://offline.invalid:0/9", redis_factory=lambda url: store)

    assert queue.capacity == 7
    assert queue.capacity_source == CAPACITY_SOURCE_ENV
    assert queue.stats()["capacity"] == 7
    assert queue.stats()["remaining"] == 7


def test_connect_reports_unknown_capacity_when_the_environment_is_silent(monkeypatch):
    monkeypatch.delenv(QUEUE_CAPACITY_ENV, raising=False)
    store = ReadableRedis()

    queue = connect_reliable_queue("redis://offline.invalid:0/9", redis_factory=lambda url: store)

    assert queue.stats()["capacity"] is None
    assert queue.stats()["saturated"] is None
    assert queue.stats()["capacity_source"] == CAPACITY_SOURCE_NOT_CONFIGURED


def test_depth_is_read_with_llen_instead_of_fetching_the_whole_list():
    store = ReadableRedis()
    queue = _queue(store, capacity=10)
    _enqueue(queue, 4, "llen")
    store.command_log.clear()

    reading = queue.stats()

    assert reading["queue_length"] == 4
    assert "lrange" not in store.command_log
    assert store.command_log.count("llen") == 2
    #: 只数排队区与处理中这两条表，读的是被观测的那份共享状态，不是本地缓存。
    assert store.depth_reads == [queue.pending_key, queue.processing_key]


def test_the_readout_is_passive_it_writes_not_a_single_byte():
    store = ReadableRedis()
    queue = _queue(store, capacity=1)
    _enqueue(queue, 1, "passive")
    store.command_log.clear()

    queue.stats()
    queue.pending_depth()
    queue.processing_depth()
    queue.dead_letter_depth()

    assert store.writes_since_start() == []


def test_dead_letter_depth_moves_with_the_retry_budget():
    store = ReadableRedis()
    queue = _queue(store, capacity=5, max_attempts=1)
    message = queue.enqueue({"message": "dead"}, "dead-1")
    queue.reserve()

    assert queue.fail_or_retry(message.request_id, "boom", retryable=False) == "dead"

    assert queue.dead_letter_depth() == 1
    assert queue.pending_depth() == 0


def test_stats_stays_a_superset_of_the_two_numbers_the_route_already_publishes():
    """路由换成直接返回 stats() 时，今天那两枚键必须同名同值——这是给接表人的护栏。"""
    store = ReadableRedis()
    queue = _queue(store, capacity=2)
    _enqueue(queue, 1, "compat")
    queue.reserve()
    queue.enqueue({"message": "compat-1"}, "compat-1")

    reading = queue.stats()

    assert {"queue_length", "processing"} <= set(reading)
    assert reading["queue_length"] == len(store.lrange(queue.pending_key, 0, -1))
    assert reading["processing"] == len(store.lrange(queue.processing_key, 0, -1))
    assert reading["queue_length"] == 1
    assert reading["processing"] == 1


def test_an_explicit_nonsense_capacity_is_refused_at_construction():
    store = ReadableRedis()
    with pytest.raises(ValueError, match="invalid queue configuration"):
        ReliableQueue(store, name="r155:bad", capacity=0)
    with pytest.raises(ValueError, match="invalid queue configuration"):
        ReliableQueue(store, name="r155:bad", capacity=-1)
    with pytest.raises(ValueError, match="invalid queue configuration"):
        ReliableQueue(store, name="r155:bad", capacity="10")
    with pytest.raises(ValueError, match="invalid queue configuration"):
        ReliableQueue(store, name="r155:bad", capacity=True)


def test_queue_stats_route_agrees_with_the_reading_it_could_return(monkeypatch):
    """HTTP 面今天只交两枚数；凡是它交的每一枚，都必须与读数逐枚相等。

    接表（把路由换成 `return queue.stats()`）落在 `app/api/v1/chat.py`，那是 R155
    的禁改写域，所以这里钉的是"接上以后不许对不上"，而不是"现在就有"。
    """
    from app.api.v1 import chat
    from app.main import app

    store = ReadableRedis()
    queue = _queue(store, capacity=2)
    _enqueue(queue, 2, "http")
    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)

    response = TestClient(app).get("/api/v1/queue/stats", headers=_authed(monkeypatch))

    assert response.status_code == 200
    payload = response.json()
    reading = queue.stats()
    assert set(payload) <= set(reading), sorted(set(payload) - set(reading))
    assert payload["queue_length"] == reading["queue_length"] == 2
    assert payload["processing"] == reading["processing"] == 0
    for key, value in payload.items():
        assert value == reading[key], key


def test_queue_unavailable_still_answers_503_with_the_same_code(monkeypatch):
    """判据③：REDIS 连不通这条路径一个字不许动——先建连接，再谈读数。"""
    from app.api.v1 import chat
    from app.main import app

    def _boom():
        raise QueueConnectionError("Redis queue is unavailable: refused")

    monkeypatch.setattr(chat, "_get_reliable_queue", _boom)

    response = TestClient(app).get("/api/v1/queue/stats", headers=_authed(monkeypatch))

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "queue_unavailable",
        "message": "Redis queue is unavailable: refused",
    }


def test_the_503_path_is_reached_before_any_capacity_parsing(monkeypatch):
    """容量配错也不许把 503 变成 500：健康探针在前，读数解析在后。"""
    monkeypatch.setenv(QUEUE_CAPACITY_ENV, "garbage")

    with pytest.raises(QueueConnectionError) as exc_info:
        connect_reliable_queue("")

    assert exc_info.value.code == "queue_unavailable"


def test_a_failing_health_probe_still_raises_the_connection_error(monkeypatch):
    monkeypatch.setenv(QUEUE_CAPACITY_ENV, "5")

    class DeadRedis:
        def ping(self):
            raise OSError("connection refused")

    with pytest.raises(QueueConnectionError) as exc_info:
        connect_reliable_queue("redis://offline.invalid:0/9", redis_factory=lambda url: DeadRedis())

    assert exc_info.value.code == "queue_unavailable"
    assert "connection refused" in str(exc_info.value)

def test_llen_is_a_real_command_on_the_client_the_app_actually_uses():
    """别让它变成「在自己的 fake 上自证」。

    深度读数是 LLEN，那 LLEN 就必须是应用真会用的那枚服务端命令。`redis` 在
    `pyproject.toml` 里是硬依赖（redis>=5,<6）；这里只翻客户端的方法表，一个
    socket 都不开——真连 Redis 要起服务，越过本单红线。
    """
    import redis

    for command in ("llen", "lrange", "rpush", "rpoplpush", "brpoplpush", "lrem"):
        assert callable(getattr(redis.Redis, command, None)), command
    #: LLEN 属于 ListCommands mixin：与 ReliableQueue 用的其它列表命令同源。哪天换成
    #: 另一套 Redis 客户端实现，这条先响，而不是让读数静默失真。
    assert callable(redis.commands.core.ListCommands.llen)
