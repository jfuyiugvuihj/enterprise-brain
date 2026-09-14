import asyncio
import json
from types import SimpleNamespace


def _response_body(response) -> str:
    async def collect() -> str:
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    return asyncio.run(collect())


def test_overloaded_ask_uses_reliable_queue_with_idempotency_key(monkeypatch):
    from app.api.v1 import chat
    from app.common import queue as legacy_queue
    from app.common import reliable_queue
    from app.common.identity import Principal

    captured = {}
    principal = Principal.from_user(
        {"id": "queue-user", "username": "queue-user", "role": "staff", "department": "ops"}
    )

    class FakeQueue:
        def enqueue(self, payload, idempotency_key):
            captured["payload"] = payload
            captured["idempotency_key"] = idempotency_key
            return SimpleNamespace(request_id="reliable-request")

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *args: None)
    monkeypatch.setattr(chat, "_save_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda session_id, message: message)
    monkeypatch.setattr(chat.auth, "get_user", lambda username: None)
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *args, **kwargs: (False, 0))
    monkeypatch.setattr(reliable_queue, "connect_reliable_queue", lambda: FakeQueue())
    monkeypatch.setattr(
        legacy_queue,
        "enqueue_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy queue must not receive overloaded asks")
        ),
    )

    response = asyncio.run(
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
