from app.agents.contracts import AgentResult
from tests.test_reliable_queue import FakeRedis


def _payload(**overrides):
    payload = {
        "message": "hello",
        "session_id": "session-1",
        "username": "worker-user",
        "principal": {"user_id": "u-worker", "username": "worker-user", "roles": ["staff"]},
    }
    payload.update(overrides)
    return payload


def _result(answer="answer", status="success", request_id="req", **overrides):
    data = {
        "worker": "orchestrator",
        "status": status,
        "answer": answer,
        "request_id": request_id,
        "trace_id": "trace-worker",
        "task_id": "task-worker",
    }
    data.update(overrides)
    return AgentResult.model_validate(data)


def test_queue_worker_acknowledges_success_and_stores_result(monkeypatch):
    from app.common.reliable_queue import ReliableQueue
    from deploy import queue_worker

    queue = ReliableQueue(FakeRedis(), name="worker:test", lease_seconds=30, max_attempts=2)
    message = queue.enqueue(_payload(), "idem-worker")
    monkeypatch.setattr(queue_worker, "_queue", queue)
    monkeypatch.setattr(
        "app.agents.orchestrator.run_orchestrator_result",
        lambda user_message, thread_id="default", user=None: _result(
            answer=f"answer:{user_message}:{thread_id}", request_id=message.request_id
        ),
    )

    assert queue_worker.process_one() is True
    assert queue.status(message.request_id) == "done"
    assert queue.result(message.request_id) == "answer:hello:session-1"


def test_queue_worker_records_canonical_result_for_the_run_owner(monkeypatch):
    from app.common.reliable_queue import ReliableQueue
    from deploy import queue_worker

    queue = ReliableQueue(FakeRedis(), name="worker:test", lease_seconds=30, max_attempts=2)
    message = queue.enqueue(_payload(), "idem-worker")
    monkeypatch.setattr(queue_worker, "_queue", queue)
    monkeypatch.setattr(
        "app.agents.orchestrator.run_orchestrator_result",
        lambda *args, **kwargs: _result(answer="500 元/晚", request_id=message.request_id),
    )
    recorded = {}
    monkeypatch.setattr(
        queue_worker,
        "record_agent_result",
        lambda record, **kwargs: recorded.update(record) or {},
    )

    assert queue_worker.process_one() is True
    assert recorded["worker"] == "orchestrator"
    assert recorded["request_id"] == message.request_id
    assert recorded["status"] == "success"


def test_queue_worker_does_not_publish_a_conclusion_when_the_run_failed(monkeypatch):
    from app.common.reliable_queue import ReliableQueue
    from deploy import queue_worker

    queue = ReliableQueue(FakeRedis(), name="worker:test", lease_seconds=30, max_attempts=2)
    message = queue.enqueue(_payload(), "idem-worker")
    monkeypatch.setattr(queue_worker, "_queue", queue)
    monkeypatch.setattr(
        "app.agents.orchestrator.run_orchestrator_result",
        lambda *args, **kwargs: _result(
            answer="离线模式：模型不可用（error_code=model_unavailable）",
            status="model_unavailable",
            request_id=message.request_id,
            error={"code": "model_unavailable", "message": "model down", "retryable": True},
        ),
    )

    assert queue_worker.process_one() is True
    assert queue.status(message.request_id) == "queued"
    assert queue.result(message.request_id) is None


def test_queue_worker_refuses_a_task_without_an_owning_principal(monkeypatch):
    from app.common.reliable_queue import ReliableQueue
    from deploy import queue_worker

    queue = ReliableQueue(FakeRedis(), name="worker:test", lease_seconds=30, max_attempts=2)
    message = queue.enqueue(
        {"message": "orphan", "session_id": "session-1"},
        "idem-orphan",
    )
    monkeypatch.setattr(queue_worker, "_queue", queue)

    def forbidden(*args, **kwargs):
        raise AssertionError("a task without a Principal must never reach the Agent graph")

    monkeypatch.setattr("app.agents.orchestrator.run_orchestrator_result", forbidden)

    assert queue_worker.process_one() is True
    assert queue.status(message.request_id) == "queued"
    assert queue.result(message.request_id) is None

    assert queue_worker.process_one() is True
    assert queue.status(message.request_id) == "dead"
    assert queue.result(message.request_id) is None


def test_queue_worker_uses_a_request_scoped_thread_when_the_session_is_missing(monkeypatch):
    from app.common.reliable_queue import ReliableQueue
    from deploy import queue_worker

    queue = ReliableQueue(FakeRedis(), name="worker:test", lease_seconds=30, max_attempts=2)
    message = queue.enqueue(_payload(session_id=""), "idem-thread")
    monkeypatch.setattr(queue_worker, "_queue", queue)
    seen = {}

    def fake_run(user_message, thread_id="default", user=None):
        seen["thread_id"] = thread_id
        return _result(answer="ok", request_id=message.request_id)

    monkeypatch.setattr("app.agents.orchestrator.run_orchestrator_result", fake_run)

    assert queue_worker.process_one() is True
    assert seen["thread_id"] == f"queue:{message.request_id}"


def test_queue_worker_retries_failures_without_ack(monkeypatch):
    from app.common.reliable_queue import ReliableQueue
    from deploy import queue_worker

    queue = ReliableQueue(FakeRedis(), name="worker:test", lease_seconds=30, max_attempts=2)
    message = queue.enqueue(_payload(message="boom"), "idem-worker")
    monkeypatch.setattr(queue_worker, "_queue", queue)
    monkeypatch.setattr(
        "app.agents.orchestrator.run_orchestrator_result",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("temporary")),
    )

    assert queue_worker.process_one() is True
    assert queue.status(message.request_id) == "queued"
    assert queue.reserve().request_id == message.request_id


def test_queue_worker_keeps_cancelled_processing_task_terminal(monkeypatch):
    from app.common.reliable_queue import ReliableQueue
    from deploy import queue_worker

    queue = ReliableQueue(FakeRedis(), name="worker:test", lease_seconds=30, max_attempts=2)
    message = queue.enqueue(_payload(message="cancel"), "idem-worker")
    monkeypatch.setattr(queue_worker, "_queue", queue)

    def cancelled_run(*args, **kwargs):
        queue.cancel(message.request_id)
        raise RuntimeError("stopped")

    monkeypatch.setattr("app.agents.orchestrator.run_orchestrator_result", cancelled_run)

    assert queue_worker.process_one() is True
    assert queue.status(message.request_id) == "cancelled"
    assert queue.reserve() is None