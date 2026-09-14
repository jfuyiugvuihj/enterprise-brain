from dataclasses import dataclass, asdict
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException

from app.common.audit import record_audit
from app.common.identity import Principal


@dataclass
class OpenApplication:
    app_id: str
    app_name: str
    secret: str
    allowed_actions: tuple[str, ...]
    allowed_departments: tuple[str, ...] = ()
    max_clearance: int = 3
    enabled: bool = True
    description: str = ""


_APP_REGISTRY: dict[str, OpenApplication] = {}


def clear_app_registry() -> None:
    _APP_REGISTRY.clear()


def register_application(app_name: str, *, allowed_actions: list[str], allowed_departments: list[str] | None = None, max_clearance: int = 3, description: str = "") -> dict[str, str]:
    app_id = hashlib.sha256(f"{app_name}:{time.time_ns()}".encode("utf-8")).hexdigest()[:16]
    secret = hashlib.sha256(f"{app_name}:{app_id}:{time.time_ns()}".encode("utf-8")).hexdigest()
    _APP_REGISTRY[app_id] = OpenApplication(
        app_id=app_id,
        app_name=app_name,
        secret=secret,
        allowed_actions=tuple(allowed_actions),
        allowed_departments=tuple(allowed_departments or ()),
        max_clearance=max(1, int(max_clearance)),
        description=description,
    )
    return {"app_id": app_id, "secret": secret, "app_name": app_name}


def build_request_signature(app_id: str, secret: str, body: str, timestamp: str) -> str:
    payload = f"{app_id}.{timestamp}.{body}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _normalize_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in (headers or {}).items()}


def verify_open_request(headers: dict[str, Any], body: str, required_action: str) -> tuple[Principal, dict]:
    normalized = _normalize_headers(headers)
    app_id = normalized.get("x-open-app-id", "").strip()
    timestamp = normalized.get("x-open-timestamp", "").strip()
    signature = normalized.get("x-open-signature", "").strip()
    if not app_id or not timestamp or not signature:
        raise HTTPException(status_code=401, detail="开放平台身份校验失败")

    record = _APP_REGISTRY.get(app_id)
    if not record or not record.enabled:
        raise HTTPException(status_code=401, detail="未注册应用")
    if required_action not in record.allowed_actions:
        raise HTTPException(status_code=403, detail="应用无权调用该接口")

    expected = build_request_signature(app_id, record.secret, body, timestamp)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="签名校验失败")

    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="时间戳无效") from exc
    if abs(time.time() - ts) > 300:
        raise HTTPException(status_code=401, detail="请求已过期")

    principal = Principal.from_user(
        {
            "id": app_id,
            "username": normalized.get("x-open-user", record.app_name),
            "role": "staff",
            "department": normalized.get("x-open-department", ""),
            "permissions": set(),
            "status": "active",
        },
        auth_source="open_platform",
    )
    record_audit(principal, f"open:{required_action}", "allowed", record.app_name)
    return principal, asdict(record)
