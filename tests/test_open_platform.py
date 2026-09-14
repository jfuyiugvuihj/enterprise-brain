import time

from fastapi.testclient import TestClient

from app.common.open_platform import (
    build_request_signature,
    clear_app_registry,
    register_application,
    verify_open_request,
)
from app.main import app

client = TestClient(app)


def _signed_headers(app_info: dict[str, str], body: str, action: str, user: str = "alice", department: str = "market") -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "X-Open-App-Id": app_info["app_id"],
        "X-Open-Timestamp": timestamp,
        "X-Open-Signature": build_request_signature(app_info["app_id"], app_info["secret"], body, timestamp),
        "X-Open-Action": action,
        "X-Open-User": user,
        "X-Open-Department": department,
    }


def test_registered_app_can_sign_and_verify_query_request():
    clear_app_registry()
    app_info = register_application("oa-system", allowed_actions=["query", "dashboard"])
    body = '{"query":"本月差旅费是否超标"}'
    timestamp = str(int(time.time()))
    headers = {
        "X-Open-App-Id": app_info["app_id"],
        "X-Open-Timestamp": timestamp,
        "X-Open-Signature": build_request_signature(app_info["app_id"], app_info["secret"], body, timestamp),
        "X-Open-User": "alice",
        "X-Open-Department": "market",
    }

    principal, record = verify_open_request(headers, body, required_action="query")

    assert record["app_name"] == "oa-system"
    assert principal.username == "alice"
    assert principal.department == "market"


def test_unregistered_app_is_rejected():
    clear_app_registry()
    body = '{}'
    headers = {
        "X-Open-App-Id": "missing",
        "X-Open-Timestamp": str(int(time.time())),
        "X-Open-Signature": "bad",
    }

    try:
        verify_open_request(headers, body, required_action="query")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401
    else:
        raise AssertionError("expected rejection")


def test_disallowed_action_is_rejected():
    clear_app_registry()
    app_info = register_application("metrics-bot", allowed_actions=["query"])
    body = '{"rows": []}'
    timestamp = str(int(time.time()))
    headers = {
        "X-Open-App-Id": app_info["app_id"],
        "X-Open-Timestamp": timestamp,
        "X-Open-Signature": build_request_signature(app_info["app_id"], app_info["secret"], body, timestamp),
    }

    try:
        verify_open_request(headers, body, required_action="approval")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("expected rejection")


def test_open_query_endpoint_accepts_signed_request():
    clear_app_registry()
    app_info = register_application("oa-system", allowed_actions=["query"])
    body = '{"query":"本月差旅费是否超标"}'

    response = client.post("/api/v1/open/query", content=body, headers=_signed_headers(app_info, body, "query"))

    assert response.status_code == 200
    assert response.json()["context"]["metric_name"] == "住宿费标准"


def test_open_approval_preview_requires_action_permission():
    clear_app_registry()
    app_info = register_application("oa-system", allowed_actions=["query"])
    body = '{"amount":600,"standard":500,"department":"市场部","expense_type":"住宿费","evidence":["制度.pdf"]}'

    response = client.post("/api/v1/open/approval/preview", content=body, headers=_signed_headers(app_info, body, "approval"))

    assert response.status_code == 403
