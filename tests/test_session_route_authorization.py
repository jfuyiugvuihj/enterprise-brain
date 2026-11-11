import asyncio

from fastapi import HTTPException

from app.common.identity import Principal


def _request(principal):
    return type("Request", (), {"state": type("State", (), {"principal": principal})()})()


def _principal(username: str) -> Principal:
    return Principal.from_user(
        {"username": username, "role": "manager", "department": "finance"}
    )


def test_session_routes_filter_by_registered_owner(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.storage.sessions import SessionRegistry

    registry = SessionRegistry(tmp_path / "sessions.json")
    registry.bind("alice-session", _principal("alice"))
    registry.bind("bob-session", _principal("bob"))
    monkeypatch.setattr(chat, "session_registry", registry)
    monkeypatch.setattr(
        chat,
        "_list_sessions",
        lambda: [{"id": "alice-session"}, {"id": "bob-session"}],
    )

    response = asyncio.run(chat.list_sessions(_request(_principal("alice"))))

    assert response == {"sessions": [{"id": "alice-session"}]}


def test_session_detail_rejects_non_owner(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.storage.sessions import SessionRegistry

    registry = SessionRegistry(tmp_path / "sessions.json")
    registry.bind("alice-session", _principal("alice"))
    monkeypatch.setattr(chat, "session_registry", registry)

    try:
        asyncio.run(chat.get_session("alice-session", _request(_principal("bob"))))
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "resource_not_found"
    else:
        raise AssertionError("session detail must not reveal another owner's session")
