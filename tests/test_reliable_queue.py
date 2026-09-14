from __future__ import annotations

import pytest

from app.common.reliable_queue import QueueConnectionError, ReliableQueue, connect_reliable_queue


class FakeRedis:
    """Minimal in-memory Redis subset for deterministic offline queue tests."""

    def __init__(self):
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    def get(self, key: str):
        return self.values.get(key)

    def set(self, key: str, value, ex=None):
        self.values[key] = str(value)
        return True

    def delete(self, key: str):
        removed = key in self.values
        self.values.pop(key, None)
        return int(removed)

    def exists(self, key: str):
        return int(key in self.values)

    def rpush(self, key: str, value):
        self.lists.setdefault(key, []).append(str(value))
        return len(self.lists[key])

    def brpoplpush(self, source: str, destination: str, timeout=0):
        return self.rpoplpush(source, destination)

    def rpoplpush(self, source: str, destination: str):
        items = self.lists.get(source, [])
        if not items:
            return None
        value = items.pop()
        self.lists.setdefault(destination, []).insert(0, value)
        return value

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
        if end == -1:
            return items[start:]
        return items[start : end + 1]


def test_reliable_queue_is_idempotent_and_acknowledgeable():
    queue = ReliableQueue(FakeRedis(), name="test:q", lease_seconds=30, max_attempts=2)
    first = queue.enqueue({"task": "one"}, "idem-1")
    same = queue.enqueue({"task": "changed"}, "idem-1")

    assert same.request_id == first.request_id
    reserved = queue.reserve()
    assert reserved.request_id == first.request_id
    assert reserved.attempts == 1
    assert queue.status(first.request_id) == "processing"
    assert queue.ack(first.request_id) is True
    assert queue.status(first.request_id) == "done"


def test_reliable_queue_retries_then_dead_letters():
    queue = ReliableQueue(FakeRedis(), name="test:q", lease_seconds=30, max_attempts=2)
    message = queue.enqueue({"task": "one"}, "idem-1")

    queue.reserve()
    assert queue.fail_or_retry(message.request_id, "temporary") == "queued"
    queue.reserve()
    assert queue.fail_or_retry(message.request_id, "permanent") == "dead"
    assert queue.status(message.request_id) == "dead"


def test_reliable_queue_requeues_an_expired_uncancelled_lease():
    queue = ReliableQueue(FakeRedis(), name="test:q", lease_seconds=30, max_attempts=2)
    message = queue.enqueue({"task": "one"}, "idem-1")
    queue.reserve()
    queue.redis.delete(queue._lease_key(message.request_id))
    assert queue.requeue_expired() == 1
    assert queue.status(message.request_id) == "queued"


def test_reliable_queue_does_not_ack_unknown_message():
    queue = ReliableQueue(FakeRedis(), name="test:q", lease_seconds=30, max_attempts=2)

    assert queue.ack("missing") is False
    assert queue.status("missing") is None


def test_reliable_queue_does_not_reserve_a_task_cancelled_while_queued():
    queue = ReliableQueue(FakeRedis(), name="test:q", lease_seconds=30, max_attempts=2)
    message = queue.enqueue({"task": "one"}, "idem-1")

    assert queue.cancel(message.request_id) is True
    assert queue.reserve() is None
    assert queue.status(message.request_id) == "cancelled"


def test_reliable_queue_does_not_retry_a_task_cancelled_while_processing():
    queue = ReliableQueue(FakeRedis(), name="test:q", lease_seconds=30, max_attempts=2)
    message = queue.enqueue({"task": "one"}, "idem-1")
    queue.reserve()

    assert queue.cancel(message.request_id) is True
    assert queue.fail_or_retry(message.request_id, "worker_stopped") == "cancelled"
    assert queue.status(message.request_id) == "cancelled"
    assert queue.reserve() is None


def test_connect_reliable_queue_requires_an_explicit_redis_url():
    with pytest.raises(QueueConnectionError, match="REDIS_URL") as exc_info:
        connect_reliable_queue("")

    assert exc_info.value.code == "queue_unavailable"


def test_connect_reliable_queue_pings_the_injected_client_before_returning():
    class PingableRedis(FakeRedis):
        def __init__(self):
            super().__init__()
            self.pinged = False

        def ping(self):
            self.pinged = True
            return True

    client = PingableRedis()
    queue = connect_reliable_queue(
        "redis://127.0.0.1:6379/15",
        redis_factory=lambda _: client,
        name="test:connected",
    )

    assert client.pinged is True
    assert queue.name == "test:connected"


def test_connect_reliable_queue_surfaces_authentication_or_network_failure():
    class BrokenRedis:
        def ping(self):
            raise RuntimeError("authentication failed")

    with pytest.raises(QueueConnectionError, match="authentication failed") as exc_info:
        connect_reliable_queue(
            "redis://127.0.0.1:6379/15",
            redis_factory=lambda _: BrokenRedis(),
        )

    assert exc_info.value.code == "queue_unavailable"
