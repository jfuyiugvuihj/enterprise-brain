"""HITL resume and cancel must not be usable against somebody else’s session."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

SESSION_ID = "e2e-owned-session"


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _user(username: str) -> dict[str, str]:
    return {"id": f"id-{username}", "username": username, "role": "staff", "department": "dept-a"}


def _wired(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.common import auth
    from app.storage import sessions as sessions_module

    registry = sessions_module.SessionRegistry(tmp_path / "session-registry.json")
    registry.bind(SESSION_ID, _principal("owner-a"))
    monkeypatch.setattr(chat, "session_registry", registry)
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username))
    return registry


def _principal(username: str):
    from app.common.identity import Principal

    return Principal.from_user(_user(username))


def _request_for(username: str):
    return SimpleNamespace(state=SimpleNamespace(principal=_principal(username), username=username))


def test_cancel_requires_authentication(monkeypatch, tmp_path):
    from app.main import app

    _wired(monkeypatch, tmp_path)
    response = TestClient(app).post(f"/api/v1/ask/{SESSION_ID}/cancel")

    assert response.status_code == 401


def test_cancel_refuses_a_foreign_session(monkeypatch, tmp_path):
    from app.main import app

    _wired(monkeypatch, tmp_path)
    response = TestClient(app).post(
        f"/api/v1/ask/{SESSION_ID}/cancel",
        headers=_headers("intruder-b"),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "resource_not_found"


def test_cancel_still_works_for_the_owner(monkeypatch, tmp_path):
    from app.api.v1 import chat

    _wired(monkeypatch, tmp_path)
    import asyncio

    # Positive control: the guard must not degrade into a blanket denial.
    answer = asyncio.run(chat.cancel_ask(SESSION_ID, _request_for("owner-a")))

    assert answer == {"cancelled": False, "session_id": SESSION_ID}
    # Nothing was in flight, so the endpoint must not claim it cancelled a run.
    assert answer["cancelled"] is False


def test_cancel_reports_true_only_for_a_run_that_is_in_flight(monkeypatch, tmp_path):
    from app.api.v1 import chat

    import asyncio

    _wired(monkeypatch, tmp_path)
    chat.register_request(SESSION_ID)

    answer = asyncio.run(chat.cancel_ask(SESSION_ID, _request_for("owner-a")))

    assert answer["cancelled"] is True
    assert chat.is_request_cancelled(SESSION_ID) is True


def test_approve_refuses_a_foreign_session(monkeypatch, tmp_path):
    from app.main import app

    _wired(monkeypatch, tmp_path)
    response = TestClient(app).post(
        "/api/v1/approve",
        json={"session_id": SESSION_ID, "approved": True},
        headers=_headers("intruder-b"),
    )

    assert response.status_code == 404


def test_approve_refuses_an_unbound_session(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from fastapi import HTTPException

    import asyncio

    _wired(monkeypatch, tmp_path)
    try:
        asyncio.run(
            chat.approve(
                __import__("app.api.v1.chat", fromlist=["ApproveRequest"]).ApproveRequest(
                    session_id="never-bound-session", approved=True
                ),
                _request_for("owner-a"),
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("an unbound session must not be resumable")


def test_approve_passes_the_guard_for_the_owner(monkeypatch, tmp_path):
    from app.api.v1 import chat

    import asyncio

    _wired(monkeypatch, tmp_path)
    response = asyncio.run(
        chat.approve(
            chat.ApproveRequest(session_id=SESSION_ID, approved=True),
            _request_for("owner-a"),
        )
    )

    assert response.media_type == "text/event-stream"
