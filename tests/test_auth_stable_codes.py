"""R10 (batch C-1): the authentication surface answers with stable codes, not prose.

``docs/handoff/2026-09-15-backend-followup-requests.md`` 8 fixed the boundary: no HTTP
status changes, no whitelist changes, only the ``detail`` value. Every case names the one
expression it guards, so a revert of a single site shows up as a single red test.

The optional ``token_expired`` split is deliberately **not** taken: ``verify_token``
returns ``None`` for ``ExpiredSignatureError`` and ``InvalidTokenError`` together, so the
middleware cannot tell an expired token from a forged one without a new contract in
``app/common/auth.py``. One case below pins that collapse, so a future split has to be a
decision instead of an accident.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

PROTECTED_PATH = "/api/v1/users"


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def accounts(monkeypatch):
    """Back the middleware with an in-memory user table this file controls."""
    from app.common import auth

    registry: dict[str, dict] = {}
    monkeypatch.setattr(auth, "get_user", lambda username: registry.get(username))

    def add(username: str, **fields) -> str:
        registry[username] = {
            "id": username,
            "username": username,
            "role": "staff",
            "department": "finance",
            **fields,
        }
        return username

    return add


def _detail(response) -> str:
    """The middleware shape is a bare ``detail`` string; only its value was in scope."""
    body = response.json()
    assert set(body) == {"detail"}, body
    return body["detail"]


# ------------------------------------------ app/main.py:104 - missing or unverifiable token


def test_a_request_without_a_token_reports_authentication_required(client):
    response = client.get(PROTECTED_PATH)

    assert response.status_code == 401
    assert _detail(response) == "authentication_required"


def test_a_non_bearer_header_reports_authentication_required(client):
    response = client.get(PROTECTED_PATH, headers={"Authorization": "Basic Zm86YmFy"})

    assert response.status_code == 401
    assert _detail(response) == "authentication_required"


def test_a_forged_token_reports_authentication_required(client):
    response = client.get(PROTECTED_PATH, headers={"Authorization": "Bearer not-a-jwt"})

    assert response.status_code == 401
    assert _detail(response) == "authentication_required"


def test_an_expired_token_is_not_yet_distinguishable_from_a_forged_one(client):
    """401 is the contract; the code stays shared until ``verify_token`` reports a reason."""
    from app.common import auth

    expired = jwt.encode(
        {"sub": "someone", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        auth._jwt_secret(),
        algorithm="HS256",
    )

    response = client.get(PROTECTED_PATH, headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401
    assert _detail(response) == "authentication_required"


# ------------------------------------------------- app/main.py:109 - a token with no account


def test_a_token_for_a_vanished_user_reports_authentication_required(client, accounts):
    accounts("someone-else")

    response = client.get(PROTECTED_PATH, headers=_headers("nobody-here-anymore"))

    assert response.status_code == 401
    assert _detail(response) == "authentication_required"


# ------------------------------------------------ app/main.py:113 - an account that is not active


def test_a_disabled_account_reports_account_unavailable(client, accounts):
    username = accounts("alice", status="disabled")

    response = client.get(PROTECTED_PATH, headers=_headers(username))

    assert response.status_code == 403
    assert _detail(response) == "account_unavailable"


def test_a_deleted_account_is_refused_the_same_way_as_a_disabled_one(client, accounts):
    username = accounts("bob", status="deleted")

    response = client.get(PROTECTED_PATH, headers=_headers(username))

    assert response.status_code == 403
    assert _detail(response) == "account_unavailable"


def test_an_active_account_still_reaches_the_handler(client, accounts):
    username = accounts("carol", role="admin")

    response = client.get(PROTECTED_PATH, headers=_headers(username))

    assert response.status_code not in (401, 403)


# ------------------------ app/common/authorization.py:53 and app/api/v1/auth.py:110 (route side)


def test_authorize_request_without_a_principal_reports_authentication_required():
    from app.common.authorization import authorize_request
    from app.common.permissions import ACTION_VIEW

    with pytest.raises(HTTPException) as exc:
        authorize_request(SimpleNamespace(state=SimpleNamespace()), ACTION_VIEW)

    assert exc.value.status_code == 401
    assert exc.value.detail == "authentication_required"


def test_the_password_route_without_a_principal_reports_authentication_required():
    import asyncio

    from app.api.v1.auth import ChangePasswordRequest, change_password

    payload = ChangePasswordRequest(username="alice", old_password="x", new_password="y")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(change_password(payload, SimpleNamespace(state=SimpleNamespace())))

    assert exc.value.status_code == 401
    assert exc.value.detail == "authentication_required"


# --------------------------------------------------------- the whitelist did not move either


@pytest.mark.parametrize("path", ["/api/v1/health", "/openapi.json", "/docs"])
def test_the_public_paths_are_still_reachable_without_a_token(path):
    from app.main import app

    response = TestClient(app).get(path)

    assert response.status_code not in (401, 403)


def test_no_prose_is_left_in_the_authentication_surface():
    """The Chinese sentences were the defect; reintroducing one must fail here."""
    root = Path(__file__).resolve().parents[1]

    for relative in ("app/main.py", "app/common/authorization.py", "app/api/v1/auth.py"):
        text = (root / relative).read_text(encoding="utf-8")
        for prose in ("请先登录", "账号不可用"):
            assert prose not in text, f"{relative} still answers {prose!r}"