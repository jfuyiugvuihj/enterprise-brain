from datetime import datetime, timezone
from threading import Lock

_events: list[dict] = []
_lock = Lock()


def record_audit(principal, action: str, outcome: str, resource: str = "", reason: str = "") -> dict:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "username": getattr(principal, "username", "anonymous"),
        "role": getattr(principal, "role", "unknown"),
        "action": action,
        "resource": resource,
        "outcome": outcome,
        "reason": reason,
    }
    with _lock:
        _events.append(event)
    return event


def get_audit_events() -> list[dict]:
    with _lock:
        return [dict(event) for event in _events]


def clear_audit_events() -> None:
    with _lock:
        _events.clear()
