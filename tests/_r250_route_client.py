"""One authenticated test client for the management plane, shared by R250's route pins.

``tests/test_observability_routes.py`` already keeps an in-memory user table behind the
authentication middleware; this is the same trick in one place so R250's permission matrix
(admin / manager / staff / auditor) and its fallback-body test both drive the real ASGI
stack instead of calling the handler with a hand-made Request.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

#: The four roles judgement 4 asks about, in the order the report lists them.
ROLE_MATRIX = ("admin", "manager", "staff", "auditor")


@pytest.fixture()
def users(monkeypatch):
    """Back the authentication middleware with an in-memory user table."""
    from app.common import auth

    registry = {}

    def add(username, role, **fields):
        registry[username] = {
            "id": f"u-{username}",
            "username": username,
            "role": role,
            "department": "研发部",
            **fields,
        }
        return username

    monkeypatch.setattr(auth, "get_user", lambda username: registry.get(username))
    return add


def headers_for(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


@pytest.fixture()
def app_client(users):
    from app.main import app

    return TestClient(app)
