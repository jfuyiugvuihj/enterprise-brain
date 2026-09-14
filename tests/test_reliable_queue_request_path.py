import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException

from app.common.identity import Principal


def _response_body(response) -> str:
    async def collect() -> str:
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    return asyncio.run(collect())


def _ask_over_limit(monkeypatch, queue_factory):
    """Drive /ask through the overload branch and return whatever it produced."""
    from app.api.v1 import chat
    from app.common import reliable_queue

    principal = Principal.from_user(
        {"id": "queue-user", "username": "queue-user", "role": "staff", "department": "ops"}
    )

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *args: None)
    monkeypatch.setattr(chat, "_save_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda session_id, message: message)
    monkeypatch.setattr(chat.auth, "get_user", lambda username: None)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *args, **kwargs: (False, 0))
    monkeypatch.setattr(reliable_queue, "connect_reliable_queue", queue_factory)

    return asyncio.run(
        chat.ask(
            chat.AskRequest(
                message="queue this",
                session_id="queue-session",
                idempotency_key="retry-key",
            ),
            http_request=SimpleNamespace(
                state=SimpleNamespace(username="queue-user", principal=principal),
                headers={},
            ),
        )
    )


def test_legacy_blpop_queue_module_is_deleted():
    """The BLPOP helper was dead code whose only caller proved it must not be used."""
    assert importlib.util.find_spec("app.common.queue") is None
    assert not Path("app/common/queue.py").exists()


def test_overloaded_ask_uses_reliable_queue_with_idempotency_key(monkeypatch):
    from app.common import reliable_queue

    captured = {}

    class FakeQueue:
        def enqueue(self, payload, idempotency_key):
            captured["payload"] = payload
            captured["idempotency_key"] = idempotency_key
            return SimpleNamespace(request_id="reliable-request")

    response = _ask_over_limit(monkeypatch, lambda: FakeQueue())
    body = _response_body(response)

    assert captured["idempotency_key"] == "retry-key"
    assert captured["payload"]["message"] == "queue this"
    assert captured["payload"]["session_id"] == "queue-session"
    assert captured["payload"]["username"] == "queue-user"
    assert json.loads(body.split("data: ", 1)[1].split("\n", 1)[0]) == {
        "type": "queued",
        "request_id": "reliable-request",
        "status": "queued",
    }


def test_overloaded_ask_fails_closed_without_redis(monkeypatch):
    """No Redis means no queue: the request is refused instead of parked in memory."""
    from app.common.reliable_queue import QueueConnectionError

    def refuse():
        raise QueueConnectionError("REDIS_URL is required for the reliable queue")

    try:
        _ask_over_limit(monkeypatch, refuse)
    except HTTPException as exc:
        assert exc.status_code == 503
        assert exc.detail["code"] == QueueConnectionError.code
    else:
        raise AssertionError("expected a 503 when the reliable queue is unavailable")
