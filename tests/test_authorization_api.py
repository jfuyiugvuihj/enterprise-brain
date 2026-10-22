import asyncio

from fastapi import HTTPException

from app.common.authorization import authorize_request
from app.common.identity import Principal
from app.common.permissions import ACTION_DELETE


def test_authorize_request_uses_403_for_authenticated_denial():
    request = type(
        "Request",
        (),
        {
            "state": type(
                "State",
                (),
                {
                    "principal": Principal.from_user(
                        {"username": "u", "role": "staff", "department": "finance"}
                    )
                },
            )()
        },
    )()
    try:
        authorize_request(request, ACTION_DELETE)
    except HTTPException as exc:
        assert exc.status_code == 403
        assert "权限" in str(exc.detail)
    else:
        raise AssertionError("expected HTTPException")


def test_authorize_request_rejects_missing_principal_as_401():
    request = type("Request", (), {"state": type("State", (), {})()})()
    try:
        authorize_request(request, ACTION_DELETE)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("expected HTTPException")


def test_user_management_rejects_staff():
    from app.api.v1.auth import list_users

    request = type(
        "Request",
        (),
        {
            "state": type(
                "State",
                (),
                {
                    "principal": Principal.from_user(
                        {"username": "staff", "role": "staff", "department": "general"}
                    )
                },
            )()
        },
    )()

    try:
        asyncio.run(list_users(request))
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("expected staff user management denial")


def test_authorize_request_does_not_trust_unknown_username_in_request_state(monkeypatch):
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: None)
    request = type(
        "Request",
        (),
        {"state": type("State", (), {"username": "not-a-user"})()},
    )()

    try:
        authorize_request(request, ACTION_DELETE)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("unknown request username must not become a principal")
