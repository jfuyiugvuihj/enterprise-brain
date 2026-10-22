"""P1-2 —— 在途取消与租约丢失后的结果所有权。

队列层的历史缺陷：任务在运行途中被取消，worker 仍会把答案写回 Redis 并把
状态覆盖成 done；租约过期被回收后，迟到的 worker 同样能发布结果。
本文件锁死“取消优先、所有权优先”的收敛语义。
"""
from __future__ import annotations

from app.common.reliable_queue import ReliableQueue
from tests.test_reliable_queue import FakeRedis


def _queue() -> ReliableQueue:
    return ReliableQueue(FakeRedis(), name="inflight:test", lease_seconds=30, max_attempts=2)


def _processing(queue: ReliableQueue, request_id: str) -> bool:
    return request_id in queue.redis.lrange(queue.processing_key, 0, -1)


def test_inflight_cancel_drops_the_answer_and_never_reports_done():
    queue = _queue()
    message = queue.enqueue({"task": "long"}, "idem-1")
    queue.reserve()

    assert queue.cancel(message.request_id) is True
    assert queue.status(message.request_id) == "cancel_requested"

    assert queue.complete(message.request_id, "不该被看到的答案") is False

    assert queue.result(message.request_id) is None
    assert queue.status(message.request_id) == "cancelled"
    assert _processing(queue, message.request_id) is False
    assert queue.redis.exists(queue._lease_key(message.request_id)) == 0


def test_inflight_cancel_wins_even_when_the_worker_acks_without_a_result():
    queue = _queue()
    message = queue.enqueue({"task": "long"}, "idem-1")
    queue.reserve()
    queue.cancel(message.request_id)

    assert queue.ack(message.request_id) is False
    assert queue.status(message.request_id) == "cancelled"
    assert queue.result(message.request_id) is None


def test_a_previously_published_result_is_erased_by_cancellation():
    queue = _queue()
    message = queue.enqueue({"task": "long"}, "idem-1")
    queue.reserve()
    queue.redis.set(queue._result_key(message.request_id), "上一轮残留")
    queue.cancel(message.request_id)

    assert queue.ack(message.request_id) is False
    assert queue.result(message.request_id) is None


def test_uncancelled_task_still_publishes_a_readable_result():
    queue = _queue()
    message = queue.enqueue({"task": "long"}, "idem-1")
    queue.reserve()

    assert queue.complete(message.request_id, "正常答案") is True

    assert queue.status(message.request_id) == "done"
    assert queue.result(message.request_id) == "正常答案"
    assert _processing(queue, message.request_id) is False


def test_stale_worker_cannot_publish_after_its_lease_is_requeued():
    queue = _queue()
    message = queue.enqueue({"task": "long"}, "idem-1")
    queue.reserve()
    queue.redis.delete(queue._lease_key(message.request_id))

    assert queue.requeue_expired() == 1
    assert queue.status(message.request_id) == "queued"

    assert queue.complete(message.request_id, "上一任 worker 的迟到结果") is False

    assert queue.result(message.request_id) is None
    assert queue.status(message.request_id) == "queued"


def test_retry_after_lease_loss_completes_normally():
    queue = _queue()
    message = queue.enqueue({"task": "long"}, "idem-1")
    queue.reserve()
    queue.redis.delete(queue._lease_key(message.request_id))
    queue.requeue_expired()

    retry = queue.reserve()

    assert retry is not None
    assert retry.request_id == message.request_id
    assert retry.attempts == 2
    assert queue.complete(retry.request_id, "重试后的结果") is True
    assert queue.result(retry.request_id) == "重试后的结果"
    assert queue.status(retry.request_id) == "done"


def test_stale_ack_does_not_touch_a_lease_held_by_the_next_attempt():
    queue = _queue()
    message = queue.enqueue({"task": "long"}, "idem-1")
    queue.reserve()
    queue.redis.delete(queue._lease_key(message.request_id))
    queue.requeue_expired()

    assert queue.ack(message.request_id) is False

    fresh = queue.reserve()
    assert fresh is not None
    assert queue.redis.exists(queue._lease_key(message.request_id)) == 1
    assert queue.status(message.request_id) == "processing"
    assert queue.complete(message.request_id, "重试答案") is True