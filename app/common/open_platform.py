from dataclasses import dataclass, asdict
import hashlib
import hmac
import json
import os
import time
from threading import RLock
from typing import Any

from fastapi import HTTPException

from app.common.audit import record_audit
from app.common.authorization import DEPARTMENT_SELF_REPORT_DENIED
from app.common.identity import Principal
from app.common.monitoring import ProductionReadOnlyProtection


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
_STORE_PATH_ENV = "OPEN_PLATFORM_APP_STORE_PATH"
_STORE_COLLECTION = "open_platform_apps"
_PRODUCTION_ENVIRONMENTS = {"production", "prod"}
_LOCK = RLock()
# ``path`` starts as a sentinel so a late environment change is still picked up.
_UNCONFIGURED = object()
_STORE: dict[str, Any] = {"path": _UNCONFIGURED, "store": None, "error": "", "mtime": None, "loaded": False}


def _is_production_environment() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


def configure_app_store(store_path: str = "") -> None:
    """Point the registry at a durable JSON store; an empty value falls back to memory.

    The in-process cache is dropped because it belongs to the previous store.
    """
    resolved = str(store_path or os.getenv(_STORE_PATH_ENV, "") or "").strip() or None
    with _LOCK:
        _STORE["path"] = resolved
        _STORE["store"] = None
        _STORE["error"] = ""
        _STORE["mtime"] = None
        _STORE["loaded"] = False
        _APP_REGISTRY.clear()
        if resolved:
            from app.storage.persistence import JsonPersistenceAdapter

            try:
                _STORE["store"] = JsonPersistenceAdapter(resolved)
            except Exception as exc:  # pragma: no cover - unwritable data directory
                _STORE["error"] = f"cannot open application store: {type(exc).__name__}"


def _current_store():
    """Resolve the configured store lazily so environment changes take effect."""
    resolved = str(os.getenv(_STORE_PATH_ENV, "") or "").strip() or None
    if _STORE["path"] is _UNCONFIGURED or resolved != _STORE["path"]:
        configure_app_store(resolved)
    return _STORE["store"]


def app_registry_storage_state() -> dict:
    """Report where application credentials live: durable store, memory, or nowhere."""
    _current_store()
    path = _STORE["path"]
    error = str(_STORE["error"] or "")
    if path and not error:
        return {
            "storage_mode": "json",
            "durable": True,
            "shared_across_processes": True,
            "protection": "none",
            "detail": f"applications persisted to collection {_STORE_COLLECTION}",
        }
    if path and error:
        return {
            "storage_mode": "unavailable",
            "durable": False,
            "shared_across_processes": False,
            "protection": "read_only",
            "detail": error,
        }
    if _is_production_environment():
        return {
            "storage_mode": "unavailable",
            "durable": False,
            "shared_across_processes": False,
            "protection": "read_only",
            "detail": f"{_STORE_PATH_ENV} is not configured; application registration is refused",
        }
    return {
        "storage_mode": "memory",
        "durable": False,
        "shared_across_processes": False,
        "protection": "none",
        "detail": "process-local registry; registrations are lost on restart",
    }


def _record_from_payload(payload: Any) -> OpenApplication | None:
    if not isinstance(payload, dict):
        return None
    app_id = str(payload.get("app_id") or "")
    secret = str(payload.get("secret") or "")
    if not app_id or not secret:
        return None
    try:
        max_clearance = int(payload.get("max_clearance") or 1)
    except (TypeError, ValueError):
        max_clearance = 1
    return OpenApplication(
        app_id=app_id,
        app_name=str(payload.get("app_name") or app_id),
        secret=secret,
        allowed_actions=tuple(str(item) for item in (payload.get("allowed_actions") or ())),
        allowed_departments=tuple(str(item) for item in (payload.get("allowed_departments") or ())),
        max_clearance=max(1, max_clearance),
        enabled=bool(payload.get("enabled", True)),
        description=str(payload.get("description") or ""),
    )


def load_app_registry() -> int:
    """Re-read the durable registry into this process; returns the cached record count."""
    store = _current_store()
    if store is None:
        return len(_APP_REGISTRY)
    from app.storage.persistence import PersistenceWriteError

    try:
        records = store.list(_STORE_COLLECTION)
    except (PersistenceWriteError, OSError, ValueError) as exc:
        _STORE["error"] = f"application store read failed: {type(exc).__name__}"
        return len(_APP_REGISTRY)
    rebuilt = {}
    for payload in records:
        record = _record_from_payload(payload)
        if record is not None:
            rebuilt[record.app_id] = record
    with _LOCK:
        _APP_REGISTRY.clear()
        _APP_REGISTRY.update(rebuilt)
        _STORE["error"] = ""
        _STORE["loaded"] = True
    return len(_APP_REGISTRY)


def _refresh_from_store() -> None:
    """Adopt registrations made by another worker without reading disk on every request."""
    store = _current_store()
    if store is None:
        return
    try:
        mtime = os.path.getmtime(store.path)
    except OSError:
        mtime = None
    if mtime == _STORE["mtime"] and _STORE["loaded"]:
        return
    _STORE["mtime"] = mtime
    load_app_registry()


def list_applications() -> list[dict]:
    """Admin-safe overview; never includes the signing secret."""
    _refresh_from_store()
    with _LOCK:
        return [
            {
                "app_id": record.app_id,
                "app_name": record.app_name,
                "allowed_actions": list(record.allowed_actions),
                "allowed_departments": list(record.allowed_departments),
                "max_clearance": record.max_clearance,
                "enabled": record.enabled,
                "description": record.description,
            }
            for record in sorted(_APP_REGISTRY.values(), key=lambda item: item.app_name)
        ]


def clear_app_registry() -> None:
    """Drop the in-process cache only; records in a durable store stay on disk."""
    with _LOCK:
        _APP_REGISTRY.clear()
        _STORE["loaded"] = False
        _STORE["mtime"] = None


def register_application(app_name: str, *, allowed_actions: list[str], allowed_departments: list[str] | None = None, max_clearance: int = 3, description: str = "") -> dict[str, str]:
    """Register an open-platform application and return its one-time secret.

    Production requires a durable store: a registration that only lives in this
    process disappears on restart and is invisible to the other workers, which would
    silently break every signed request that another instance issued.
    """
    name = str(app_name or "").strip()
    actions = [str(item).strip() for item in (allowed_actions or []) if str(item).strip()]
    if not name:
        raise ValueError("app_name_required")
    if not actions:
        raise ValueError("allowed_actions_required")
    store = _current_store()
    if store is None and _is_production_environment():
        raise ProductionReadOnlyProtection(
            f"open_platform_registry_read_only: {_STORE_PATH_ENV} is required in production"
        )
    app_id = hashlib.sha256(f"{name}:{time.time_ns()}".encode("utf-8")).hexdigest()[:16]
    secret = hashlib.sha256(f"{name}:{app_id}:{time.time_ns()}".encode("utf-8")).hexdigest()
    record = OpenApplication(
        app_id=app_id,
        app_name=name,
        secret=secret,
        allowed_actions=tuple(actions),
        allowed_departments=tuple(str(item).strip() for item in (allowed_departments or ()) if str(item).strip()),
        max_clearance=max(1, int(max_clearance)),
        description=str(description or ""),
    )
    from app.storage.persistence import PersistenceWriteError

    with _LOCK:
        _APP_REGISTRY[app_id] = record
        if store is not None:
            try:
                store.upsert(_STORE_COLLECTION, app_id, asdict(record))
            except (PersistenceWriteError, OSError, ValueError) as exc:
                _APP_REGISTRY.pop(app_id, None)
                _STORE["error"] = f"application store write failed: {type(exc).__name__}"
                raise ProductionReadOnlyProtection("open_platform_store_write_failed") from exc
            _STORE["loaded"] = True
            try:
                _STORE["mtime"] = os.path.getmtime(store.path)
            except OSError:  # pragma: no cover - the file was just written
                _STORE["mtime"] = None
    return {"app_id": app_id, "secret": secret, "app_name": name}


def build_request_signature(app_id: str, secret: str, body: str, timestamp: str) -> str:
    payload = f"{app_id}.{timestamp}.{body}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _normalize_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in (headers or {}).items()}


def _granted_departments(record: OpenApplication) -> tuple[str, ...]:
    """The departments an administrator granted this application, normalized once."""
    return tuple(
        str(item or "").strip() for item in (record.allowed_departments or ()) if str(item or "").strip()
    )


def _resolve_open_department(record: OpenApplication, claimed: str) -> str:
    """Pick the department an application may speak for from the registry, and nothing else.

    The signature proves which application is asking and which action it holds. It proves
    nothing about whom it is asking for: ``build_request_signature`` covers
    ``app_id.timestamp.body``, so no identity header is signed and any client can write one.
    That header used to be the whole story, which is how R67 was bypassed -- a Principal built
    from an invented ``X-Open-Department`` then satisfied ``verify_department_self_report``,
    because the department it checks a claim against was the one the caller had just sent.

    The header is therefore only a selector among what an administrator granted:

    - no grant means no department, and the header is not consulted at all. The request then
      reaches the retrieval layer without a scope, which is R17's fail-closed and stays that way;
    - one grant needs no selector, so the header remains optional for clients written before it;
    - several grants make the header the only way to choose, and silence chooses nothing:
      filing a conclusion under a scope nobody asked for is a forgery of a different shape;
    - a value outside the grant is refused with the code the session transport already uses,
      because it is the same judgment -- a department the caller has no standing for.
    """
    granted = _granted_departments(record)
    requested = str(claimed or "").strip()
    if not granted:
        return ""
    if not requested:
        return granted[0] if len(granted) == 1 else ""
    if requested in granted:
        return requested
    raise HTTPException(
        status_code=403,
        detail={
            "code": DEPARTMENT_SELF_REPORT_DENIED,
            "message": "X-Open-Department must name a department granted to this application",
        },
    )


def verify_open_request(headers: dict[str, Any], body: str, required_action: str) -> tuple[Principal, dict]:
    normalized = _normalize_headers(headers)
    app_id = normalized.get("x-open-app-id", "").strip()
    timestamp = normalized.get("x-open-timestamp", "").strip()
    signature = normalized.get("x-open-signature", "").strip()
    if not app_id or not timestamp or not signature:
        raise HTTPException(status_code=401, detail="开放平台身份校验失败")

    _refresh_from_store()
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

    # The department starts empty on purpose: it is resolved from the registry below, never
    # read out of the headers, so the subject on the denial row is the same application that
    # asked, minus a claim it is not entitled to make.
    principal = Principal.from_user(
        {
            "id": app_id,
            "username": normalized.get("x-open-user", record.app_name),
            "role": "staff",
            "department": "",
            "permissions": set(),
            "status": "active",
        },
        auth_source="open_platform",
    )
    try:
        department = _resolve_open_department(record, normalized.get("x-open-department", ""))
    except HTTPException:
        record_audit(
            principal, f"open:{required_action}", "denied", record.app_name, DEPARTMENT_SELF_REPORT_DENIED
        )
        raise
    principal = principal.model_copy(update={"department": department})
    record_audit(principal, f"open:{required_action}", "allowed", record.app_name)
    return principal, asdict(record)
