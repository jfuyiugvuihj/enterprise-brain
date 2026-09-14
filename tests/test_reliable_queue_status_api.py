from fastapi.testclient import TestClient


def test_queue_status_reads_reliable_queue_state(monkeypatch):
    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.common.reliable_queue import ReliableQueue
    from app.main import app
    from tests.test_reliable_queue import FakeRedis

    queue = ReliableQueue(FakeRedis(), name="api:test", lease_seconds=30)
    message = queue.enqueue(
        {
            "message": "hello",
            "principal": {"user_id": "admin", "username": "admin"},
        },
        "api-idem",
    )
    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {"id": username, "username": username, "role": "admin"},
    )

    response = TestClient(app).get(
        f"/api/v1/queue/status/{message.request_id}",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "queued",
        "request_id": message.request_id,
        "position": 1,
        "failure": {"attempts": 0, "last_error": None, "max_attempts": 3},
    }


def test_queue_status_returns_result_after_reliable_completion(monkeypatch):
    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.common.reliable_queue import ReliableQueue
    from app.main import app
    from tests.test_reliable_queue import FakeRedis

    queue = ReliableQueue(FakeRedis(), name="api:test", lease_seconds=30)
    message = queue.enqueue(
        {
            "message": "hello",
            "principal": {"user_id": "admin", "username": "admin"},
        },
        "api-idem",
    )
    queue.reserve()
    queue.complete(message.request_id, "answer")
    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {"id": username, "username": username, "role": "admin"},
    )

    response = TestClient(app).get(
        f"/api/v1/queue/status/{message.request_id}",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "done",
        "request_id": message.request_id,
        "result": "answer",
        "failure": {"attempts": 1, "last_error": None, "max_attempts": 3},
    }


def test_queue_cancel_marks_reliable_task_cancelled(monkeypatch):
    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.common.reliable_queue import ReliableQueue
    from app.main import app
    from tests.test_reliable_queue import FakeRedis

    queue = ReliableQueue(FakeRedis(), name="api:test", lease_seconds=30)
    message = queue.enqueue(
        {
            "message": "hello",
            "principal": {"user_id": "admin", "username": "admin"},
        },
        "api-idem",
    )
    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {"id": username, "username": username, "role": "admin"},
    )

    response = TestClient(app).post(
        f"/api/v1/queue/{message.request_id}/cancel",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "cancelled": True,
        "request_id": message.request_id,
        "status": "cancelled",
    }
    assert queue.status(message.request_id) == "cancelled"


def test_queue_status_and_cancel_deny_non_owner(monkeypatch):
    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.common.reliable_queue import ReliableQueue
    from app.main import app
    from tests.test_reliable_queue import FakeRedis

    queue = ReliableQueue(FakeRedis(), name="api:test", lease_seconds=30)
    message = queue.enqueue(
        {
            "message": "private task",
            "principal": {"user_id": "owner", "username": "owner"},
        },
        "api-idem",
    )
    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": username,
            "username": username,
            "role": "manager",
            "department": "finance",
        },
    )

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_token('other-user')}"}

    assert client.get(f"/api/v1/queue/status/{message.request_id}", headers=headers).status_code == 403
    assert client.post(f"/api/v1/queue/{message.request_id}/cancel", headers=headers).status_code == 403
    assert queue.status(message.request_id) == "queued"


def _client_for(monkeypatch, queue):
    from app.api.v1 import chat
    from app.common import auth
    from app.common.auth import create_token
    from app.main import app

    monkeypatch.setattr(chat, "_get_reliable_queue", lambda: queue)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {"id": username, "username": username, "role": "admin"},
    )
    return TestClient(app), create_token("admin")


def test_queue_status_reports_the_last_failure_reason(monkeypatch):
    from app.common.reliable_queue import ReliableQueue
    from tests.test_reliable_queue import FakeRedis

    queue = ReliableQueue(FakeRedis(), name="api:test", lease_seconds=30, max_attempts=5)
    message = queue.enqueue(
        {"message": "hello", "principal": {"user_id": "admin", "username": "admin"}},
        "api-failure-idem",
    )
    queue.reserve()
    queue.fail_or_retry(message.request_id, "model_unavailable")

    client, token = _client_for(monkeypatch, queue)
    body = client.get(
        f"/api/v1/queue/status/{message.request_id}", headers={"Authorization": f"Bearer {token}"}
    ).json()

    assert body["status"] == "queued"
    assert body["failure"] == {"attempts": 1, "last_error": "model_unavailable", "max_attempts": 5}


def test_dead_letter_status_keeps_the_terminal_reason(monkeypatch):
    from app.common.reliable_queue import ReliableQueue
    from tests.test_reliable_queue import FakeRedis

    queue = ReliableQueue(FakeRedis(), name="api:test", lease_seconds=30, max_attempts=1)
    message = queue.enqueue(
        {"message": "hello", "principal": {"user_id": "admin", "username": "admin"}},
        "api-dead-idem",
    )
    queue.reserve()
    assert queue.fail_or_retry(message.request_id, "queue_unavailable") == "dead"

    client, token = _client_for(monkeypatch, queue)
    body = client.get(
        f"/api/v1/queue/status/{message.request_id}", headers={"Authorization": f"Bearer {token}"}
    ).json()

    assert body["status"] == "dead"
    assert body["failure"]["last_error"] == "queue_unavailable"
