"""Durable security-audit journal for every authorization boundary.

The original implementation appended to a process-local list, so a restart erased the
whole judgment chain. Every event is now also written through the project's single
persistence adapter (``app.storage.persistence.build_persistence_adapter``), which keeps
the existing JSON/PostgreSQL backends instead of adding a parallel store.

Degradation is explicit rather than silent:

* ``storage_mode`` is ``json`` or ``postgres`` only when the durable write succeeded;
* ``memory_only`` means the event lives only in this process, ``persisted`` is ``False``,
  ``persistence_error`` explains why, the failure is logged, and ``audit_storage_status()``
  counts it. A caller can also request ``raise_on_write_failure=True``.

``AUDIT_PERSISTENCE=disabled`` or an unreachable configured backend therefore reports a
degraded audit journal instead of pretending that events were stored durably, so a
production deployment without a reachable database is honest about the difference.

Replay order is carried by the stamp, not by luck. The merge in ``_hydrate_view_locked`` sorts
by ``(created_at, event_id)``, while ``created_at`` came from a wall clock that only moves in
~1 ms steps on Windows, so two events written inside one tick came back in whichever order
their random ids happened to sort. ``_allocate_timestamp_locked`` now hands out strictly
increasing stamps inside the journal lock, seeded on hydrate from the newest record already
written. That covers one writing process and no more: worker processes share no allocator, so
a same-tick pair written by two of them is still ordered by ``event_id``.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import json
import os
from threading import RLock
from typing import Any
from uuid import uuid4

from app.common.logger import logger
from app.common.tracing import sanitize_trace_event
from app.storage.persistence import build_persistence_adapter

AUDIT_COLLECTION = "audit_events"
AUDIT_MIGRATION = "0005_audit_events"
DEFAULT_RETENTION_DAYS = 180
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 32767
MAX_SUMMARY_CHARS = 600
MAX_SUMMARY_FIELDS = 12
MAX_SUMMARY_DEPTH = 3
MAX_VIEW_EVENTS = 20000
MEMORY_ONLY = "memory_only"
#: Smallest gap the allocator can put between two events. TIMESTAMPTZ and the ISO text the
#: JSON journal stores both keep a microsecond, so a lift of this size survives storage.
_STAMP_STEP = timedelta(microseconds=1)

_SCOPE_KEYS = (
    "resource_type",
    "resource_id",
    "version_id",
    "owner_id",
    "department_ids",
    "department",
    "classification",
    "visibility",
    "status",
)
_TRANSIENT_KEYS = ("persisted", "persistence_error", "storage_mode")

_events: list[dict[str, Any]] = []
_lock = RLock()
_init_lock = RLock()
_persistence: Any = None
_injected_persistence: Any = None
_storage_arguments: dict[str, Any] = {}
_storage: dict[str, Any] = {}
_storage_ready = False
_view_ready = False
_error_counts: dict[str, int] = {}
#: Newest stamp this process has handed out; guarded by ``_lock`` like the view itself.
_last_issued_at: datetime | None = None


class AuditPersistenceError(RuntimeError):
    """Raised only by callers that opt in with ``raise_on_write_failure=True``."""


def _persistence_enabled() -> bool:
    return (os.getenv("AUDIT_PERSISTENCE", "enabled") or "enabled").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def _log_repeated(key: str, message: str) -> int:
    count = _error_counts.get(key, 0) + 1
    _error_counts[key] = count
    if count == 1 or count % 50 == 0:
        logger.error("%s (occurrences=%d)", message, count)
    return count


def _describe_adapter(adapter: Any) -> tuple[str, str]:
    path = getattr(adapter, "path", None)
    if path is not None:
        return "json", str(path)
    name = type(adapter).__name__
    if "Postgres" in name:
        return "postgres", "PostgreSQL connection factory"
    return name.lower(), ""


def _fresh_status(backend: str) -> dict[str, Any]:
    return {
        "backend": backend,
        "configured": False,
        "durable": False,
        "degraded": True,
        "degraded_reason": "",
        "location": "",
        "collection": AUDIT_COLLECTION,
        "migration": AUDIT_MIGRATION,
        "view_complete": False,
        "write_failures": 0,
        "read_failures": 0,
        "last_error": "",
        "persisted_events": 0,
    }


def _ensure_storage() -> None:
    """Build the shared adapter lazily so imports never require a live dependency."""
    if _storage_ready:
        return
    with _init_lock:
        if _storage_ready:
            return
        _build_storage_locked()


def _build_storage_locked() -> None:
    """Populate the adapter and status; the caller holds ``_init_lock``."""
    global _persistence, _storage, _storage_ready, _view_ready
    selected = str(
        _storage_arguments.get("backend") or os.getenv("PERSISTENCE_BACKEND", "json") or "json"
    ).strip().lower()
    _storage = _fresh_status(selected)
    if not _persistence_enabled():
        _storage["degraded_reason"] = "AUDIT_PERSISTENCE is disabled"
        _storage_ready = True
        _view_ready = True
        logger.error("审计持久化已显式关闭：事件仅存于进程内存，重启即丢失")
        return
    try:
        adapter = (
            _injected_persistence
            if _injected_persistence is not None
            else build_persistence_adapter(**_storage_arguments)
        )
    except Exception as exc:  # a misconfigured backend must stay observable, never fatal
        _storage["degraded_reason"] = f"{type(exc).__name__}: {exc}"
        _storage_ready = True
        _view_ready = True
        logger.error("审计持久化后端不可用：事件仅存于进程内存（%s）", _storage["degraded_reason"])
        return
    _persistence = adapter
    kind, location = _describe_adapter(adapter)
    _storage.update(
        {
            "backend": kind or selected,
            "location": location,
            "configured": True,
            "durable": True,
            "degraded": False,
        }
    )
    _storage_ready = True
    logger.info("审计持久化后端已就绪：mode=%s location=%s", _storage["backend"], location or "-")


def _mode() -> str:
    _ensure_storage()
    return MEMORY_ONLY if _persistence is None else str(_storage.get("backend") or MEMORY_ONLY)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _allocate_timestamp_locked() -> datetime:
    """Issue the next event timestamp; the caller holds ``_lock``.

    ``datetime.now`` is coarse, so two back-to-back events can read the same instant, and the
    ``(created_at, event_id)`` merge in ``_hydrate_view_locked`` would then replay them in
    whichever order random ids come out in. A reading that is not newer than the last one
    issued is lifted by one microsecond instead, which covers both ways that happens: a clock
    that has not ticked yet, and a clock that has stepped backwards.

    This allocator is process-local and there is no shared form of it. Two worker processes can
    still write the same tick, and their relative order is still decided by ``event_id``;
    closing that needs a sequence the storage itself hands out, which the audit schema does not
    have. Order is guaranteed here, wall-clock accuracy is not: after seeding, stamps can run
    ahead of a clock that is behind its own journal history.
    """
    global _last_issued_at
    now = datetime.now(timezone.utc)
    previous = _last_issued_at
    if previous is not None and now <= previous:
        now = previous + _STAMP_STEP
    _last_issued_at = now
    return now


def _seed_timestamp_floor_locked(events: list[dict[str, Any]]) -> None:
    """Raise the allocator floor to the newest stamp the journal already holds.

    Hydrating calls this so a process that starts inside the tick its predecessor was still
    writing cannot hand out a stamp that sorts before a record already on disk.
    """
    global _last_issued_at
    newest = _last_issued_at
    for event in events:
        stamp = _parse_iso(event.get("created_at"))
        if stamp is not None and (newest is None or stamp > newest):
            newest = stamp
    _last_issued_at = newest


def _resolve_retention_days(explicit: int | None) -> int:
    raw: Any = explicit if explicit is not None else os.getenv("AUDIT_RETENTION_DAYS", "")
    try:
        days = int(str(raw).strip())
    except (TypeError, ValueError):
        days = DEFAULT_RETENTION_DAYS
    if not MIN_RETENTION_DAYS <= days <= MAX_RETENTION_DAYS:
        _log_repeated(
            "retention_invalid",
            f"审计保留期配置无效（{raw!r}），回退为 {DEFAULT_RETENTION_DAYS} 天",
        )
        days = DEFAULT_RETENTION_DAYS
    return days


def _resolve_request_id(principal: Any, explicit: str | None) -> str:
    for candidate in (explicit, getattr(principal, "request_id", "")):
        text = str(candidate or "").strip()
        if text:
            return text[:128]
    # An absent correlation id is recorded as empty; it is never invented here.
    return ""


def _resolve_policy_version(explicit: str | None) -> tuple[str, str]:
    text = str(explicit or "").strip()
    if text:
        return text[:128], "explicit"
    module_version = ""
    try:
        from app.common import policy

        module_version = str(
            getattr(policy, "POLICY_VERSION", "") or getattr(policy, "_POLICY_VERSION", "")
        ).strip()
    except Exception as exc:  # the audit journal must not depend on policy internals
        _log_repeated("policy_version_unavailable", f"无法读取策略版本：{type(exc).__name__}: {exc}")
    if module_version:
        return module_version[:128], "in_effect"
    return "", "unavailable"


def _is_container(value: Any) -> bool:
    return isinstance(value, (Mapping, list, tuple, set, frozenset))


def _truncate(value: Any) -> Any:
    """Keep scalars readable and replace unknown objects with a type marker only."""
    if isinstance(value, str):
        if len(value) <= MAX_SUMMARY_CHARS:
            return value
        return value[:MAX_SUMMARY_CHARS] + f"...[truncated len={len(value)}]"
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, datetime):
        return _iso(value)
    # Anything else is reduced to a type marker: repr() of an arbitrary object can
    # carry credentials, and the audit journal must not become a secret store.
    return {"type": type(value).__name__}


def _scalar(value: Any, depth: int = 0) -> Any:
    if _is_container(value):
        return _summarize(value, depth) or None
    return _truncate(value)


def _summarize(value: Any, depth: int = 0) -> dict[str, Any]:
    """Bound a before/after snapshot so an audit row cannot grow without limit.

    Containers are projected structurally instead of stringified so a secret can never
    reach the journal through a ``repr`` of an object that happened to hold one.
    """
    if value is None:
        return {}
    if isinstance(value, Mapping):
        if depth >= MAX_SUMMARY_DEPTH:
            return {"type": "object", "keys": sorted(str(key) for key in value)[:MAX_SUMMARY_FIELDS]}
        items = list(value.items())
        summary: dict[str, Any] = {
            str(key): _scalar(item, depth + 1) for key, item in items[:MAX_SUMMARY_FIELDS]
        }
        if len(items) > MAX_SUMMARY_FIELDS:
            summary["_truncated_fields"] = len(items) - MAX_SUMMARY_FIELDS
        return sanitize_trace_event(summary)
    if isinstance(value, (list, tuple, set, frozenset)):
        return {
            "type": "list",
            "length": len(value),
            "sample": [_scalar(item, depth + 1) for item in list(value)[:3]],
        }
    return {"value": _truncate(value)}


def _scope_value(value: Any) -> Any:
    """Keep authorization-relevant scope values readable instead of summarising them."""
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item)[:64] for item in list(value)[:MAX_SUMMARY_FIELDS]]
    if isinstance(value, Mapping):
        return {
            str(key)[:64]: _truncate(item)
            for key, item in list(value.items())[:MAX_SUMMARY_FIELDS]
        }
    return _truncate(value)


def _project_scope(resource_scope: Any, resource: str) -> tuple[dict[str, Any], str]:
    if resource_scope is None:
        return {}, "resource_name" if resource else "unavailable"
    if isinstance(resource_scope, str):
        text = resource_scope.strip()
        if not text:
            return {}, "resource_name" if resource else "unavailable"
        return {"resource_id": text[:256]}, "explicit"
    if isinstance(resource_scope, Mapping):
        attributes: dict[str, Any] = dict(resource_scope)
    else:
        attributes = {key: getattr(resource_scope, key, None) for key in _SCOPE_KEYS}
    projection: dict[str, Any] = {}
    for key in _SCOPE_KEYS:
        value = attributes.get(key)
        if key in attributes and value is not None and value != "":
            projection[key] = _scope_value(value)
    omitted = [key for key in attributes if key not in _SCOPE_KEYS]
    if omitted:
        projection["_omitted_keys"] = len(omitted)
    if not projection:
        return {}, "resource_name" if resource else "unavailable"
    return sanitize_trace_event(projection), "explicit"


def _durable_record(event: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in event.items() if key not in _TRANSIENT_KEYS}
    return {
        "event_id": event["event_id"],
        "request_id": event.get("request_id", ""),
        "actor_username": event.get("username", "anonymous"),
        "actor_role": event.get("role", "unknown"),
        "owner_id": event.get("owner_id", ""),
        "action": event.get("action", ""),
        "resource": event.get("resource", ""),
        "resource_scope": event.get("resource_scope", {}),
        "outcome": event.get("outcome", ""),
        "reason_code": event.get("reason", ""),
        "policy_version": event.get("policy_version", ""),
        "before_summary": event.get("before_summary", {}),
        "after_summary": event.get("after_summary", {}),
        "payload": payload,
        "retention_days": event.get("retention_days", DEFAULT_RETENTION_DAYS),
        "expires_at": event.get("expires_at"),
        "created_at": event.get("created_at"),
    }


def _from_durable_record(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            payload = {}
    event = dict(payload) if isinstance(payload, Mapping) else {}
    mapping = {
        "event_id": "event_id",
        "request_id": "request_id",
        "username": "actor_username",
        "role": "actor_role",
        "owner_id": "owner_id",
        "action": "action",
        "resource": "resource",
        "outcome": "outcome",
        "reason": "reason_code",
        "policy_version": "policy_version",
        "resource_scope": "resource_scope",
        "before_summary": "before_summary",
        "after_summary": "after_summary",
        "retention_days": "retention_days",
        "expires_at": "expires_at",
        "created_at": "created_at",
    }
    for key, column in mapping.items():
        value = record.get(column)
        if value is not None:
            event[key] = value
        else:
            event.setdefault(key, {} if key.endswith("summary") or key == "resource_scope" else "")
    for key in ("created_at", "expires_at"):
        value = event.get(key)
        if isinstance(value, datetime):
            # The PostgreSQL codec returns timestamptz values as datetime objects.
            event[key] = _iso(value)
    event["timestamp"] = event.get("created_at") or ""
    event["persisted"] = True
    event["storage_mode"] = _mode()
    event.pop("persistence_error", None)
    return event


def _hydrate_view(force: bool = False) -> int:
    """Load the durable journal into the process view exactly once."""
    global _view_ready
    _ensure_storage()
    with _lock:
        return _hydrate_view_locked(force)


def _hydrate_view_locked(force: bool) -> int:
    """Merge durable events into the process view; the caller holds ``_lock``."""
    global _view_ready
    if _view_ready and not force:
        return 0
    if _persistence is None:
        _view_ready = True
        _storage["view_complete"] = True
        return 0
    try:
        records = list(_persistence.list(AUDIT_COLLECTION) or [])
    except Exception as exc:
        _storage["read_failures"] += 1
        _storage["view_complete"] = False
        _storage["last_error"] = f"{type(exc).__name__}: {exc}"
        _log_repeated(
            f"audit_read_failed:{type(exc).__name__}",
            f"审计事件读取失败，进程视图不完整：{type(exc).__name__}: {exc}",
        )
        return 0
    loaded = [_from_durable_record(record) for record in records if isinstance(record, Mapping)]
    loaded_ids = {str(event.get("event_id")) for event in loaded}
    retained = [
        event
        for event in _events
        if not event.get("persisted") and str(event.get("event_id")) not in loaded_ids
    ]
    merged = sorted(
        [*loaded, *retained],
        key=lambda event: (str(event.get("created_at") or ""), str(event.get("event_id") or "")),
    )
    _seed_timestamp_floor_locked(merged)
    _events[:] = merged[-MAX_VIEW_EVENTS:]
    _view_ready = True
    _storage["view_complete"] = True
    return len(loaded)


def _persist_event(event: dict[str, Any]) -> None:
    """Write one event; failures stay attached to the event and are counted."""
    _ensure_storage()
    event["storage_mode"] = MEMORY_ONLY if _persistence is None else str(_storage.get("backend"))
    if _persistence is None:
        event["persisted"] = False
        event["persistence_error"] = _storage.get("degraded_reason") or "no durable audit backend"
        return
    try:
        _persistence.upsert(AUDIT_COLLECTION, event["event_id"], _durable_record(event))
    except Exception as exc:
        _storage["write_failures"] += 1
        _storage["last_error"] = f"{type(exc).__name__}: {exc}"
        event["persisted"] = False
        event["persistence_error"] = f"{type(exc).__name__}: {exc}"
        _log_repeated(
            f"audit_write_failed:{type(exc).__name__}",
            f"审计事件持久化失败 action={event.get('action')} outcome={event.get('outcome')}"
            f"：{type(exc).__name__}: {exc}",
        )
        return
    _storage["persisted_events"] += 1
    event["persisted"] = True


def record_audit(
    principal,
    action: str,
    outcome: str,
    resource: str = "",
    reason: str = "",
    *,
    request_id: str | None = None,
    resource_scope: Any = None,
    policy_version: str | None = None,
    before_summary: Any = None,
    after_summary: Any = None,
    retention_days: int | None = None,
    raise_on_write_failure: bool = False,
) -> dict:
    """Record one authorization decision and return its (possibly degraded) event.

    The five positional parameters keep the historical signature so every existing
    call site remains valid. The keyword parameters are optional additions.
    """
    resolved_retention = _resolve_retention_days(retention_days)
    scope_projection, scope_source = _project_scope(resource_scope, resource)
    version, version_source = _resolve_policy_version(policy_version)
    departments = {str(getattr(principal, "department", "") or "")}
    departments.update(str(value) for value in (getattr(principal, "department_ids", None) or []))
    event: dict[str, Any] = {
        "event_id": f"aud-{uuid4().hex}",
        "timestamp": "",
        "created_at": "",
        "username": str(getattr(principal, "username", "") or "anonymous"),
        "role": str(getattr(principal, "role", "") or "unknown"),
        "owner_id": str(getattr(principal, "user_id", "") or ""),
        "auth_source": str(getattr(principal, "auth_source", "") or ""),
        "actor_clearance": _truncate(getattr(principal, "clearance", None)),
        "actor_departments": sorted(value for value in departments if value),
        "action": str(action or ""),
        "resource": str(resource or ""),
        "outcome": str(outcome or ""),
        "reason": str(reason or ""),
        "request_id": _resolve_request_id(principal, request_id),
        "resource_scope": scope_projection,
        "resource_scope_source": scope_source,
        "policy_version": version,
        "policy_version_source": version_source,
        "before_summary": _summarize(before_summary),
        "after_summary": _summarize(after_summary),
        "retention_days": resolved_retention,
        "expires_at": "",
        "persisted": False,
        "storage_mode": MEMORY_ONLY,
    }
    event = sanitize_trace_event(event)
    with _lock:
        _ensure_storage()
        if not _view_ready:
            _hydrate_view()
        # The stamp is taken in the same critical section that appends the event, so the order
        # the journal replays cannot disagree with the order the events were issued in.
        issued_at = _allocate_timestamp_locked()
        event["timestamp"] = _iso(issued_at)
        event["created_at"] = _iso(issued_at)
        event["expires_at"] = _iso(issued_at + timedelta(days=resolved_retention))
        _events.append(event)
        if len(_events) > MAX_VIEW_EVENTS:
            del _events[: len(_events) - MAX_VIEW_EVENTS]
        _persist_event(event)
        failure = str(event.get("persistence_error") or "")
    if failure and raise_on_write_failure:
        raise AuditPersistenceError(failure)
    return dict(event)


def get_audit_events(
    *,
    username: str | None = None,
    role: str | None = None,
    action: str | None = None,
    outcome: str | None = None,
    resource: str | None = None,
    request_id: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Return the process view of the journal; a no-argument call returns everything."""
    _hydrate_view()
    with _lock:
        events = [dict(event) for event in _events]
    filters = {
        "username": username,
        "role": role,
        "action": action,
        "outcome": outcome,
        "resource": resource,
        "request_id": request_id,
    }
    for key, expected in filters.items():
        if expected is None:
            continue
        wanted = str(expected)
        events = [event for event in events if str(event.get(key) or "") == wanted]
    if limit is not None and int(limit) > 0:
        events = events[-int(limit) :]
    return events


def clear_audit_events() -> None:
    """Reset the in-process view; the durable journal is append-only and untouched."""
    with _lock:
        _events.clear()
        _ensure_storage()
        _view_ready = True
        _storage["view_complete"] = True


def hydrate_audit_events(*, force: bool = True) -> int:
    """Re-read the durable journal, returning how many durable events were visible."""
    return _hydrate_view(force=force)


def audit_storage_status() -> dict:
    """Describe durability so health checks cannot mistake memory for storage.

    ``durable`` answers "is a durable backend configured"; ``degraded`` answers the
    operational question "can this journal actually be trusted right now", so a backend
    that accepts no writes never reports a healthy journal. ``view_complete`` is False
    while the durable journal is unreadable, meaning the in-process list is partial.
    """
    _hydrate_view()
    with _lock:
        status = dict(_storage)
        status["in_memory_events"] = len(_events)
        status["errors"] = dict(_error_counts)
        status["retention_days"] = _resolve_retention_days(None)
        status["mode"] = MEMORY_ONLY if _persistence is None else str(_storage.get("backend"))
        if not status["durable"]:
            status["degraded"] = True
            status["health"] = "backend_unavailable"
        elif status["write_failures"]:
            status["degraded"] = True
            status["health"] = "write_failing"
            status["degraded_reason"] = status["last_error"]
        elif status["read_failures"] or not status["view_complete"]:
            status["degraded"] = True
            status["health"] = "read_failing"
            status["degraded_reason"] = status["last_error"]
        else:
            status["degraded"] = False
            status["health"] = "ok"
    return status


def purge_expired_audit_events(
    now: datetime | None = None,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply the retention window to the durable journal.

    The shared adapter exposes upsert only, so expiry overwrites a record with a
    tombstone that keeps the ledger line and drops its content. A real ``DELETE`` job
    belongs to the deployment runbook.
    """
    reference = now or datetime.now(timezone.utc)
    _ensure_storage()
    if _persistence is None:
        return {
            "status": "unavailable",
            "reason": _storage.get("degraded_reason") or "no durable audit backend",
            "checked": 0,
            "expired": 0,
            "purged": 0,
        }
    try:
        records = list(_persistence.list(AUDIT_COLLECTION) or [])
    except Exception as exc:
        _storage["read_failures"] += 1
        message = f"审计事件读取失败，无法执行保留期清理：{type(exc).__name__}: {exc}"
        _log_repeated(f"audit_read_failed:{type(exc).__name__}", message)
        return {
            "status": "error",
            "reason": message,
            "checked": 0,
            "expired": 0,
            "purged": 0,
        }

    expired: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        expires_at = _parse_iso(record.get("expires_at"))
        if record.get("purged_at") or expires_at is None:
            continue
        if expires_at < reference:
            expired.append(dict(record))
    if dry_run or not expired:
        return {
            "status": "ok",
            "reason": "dry_run" if dry_run else "nothing_to_purge",
            "checked": len(records),
            "expired": len(expired),
            "purged": 0,
        }

    purged = 0
    for record in expired:
        event_id = str(record.get("event_id") or "")
        if not event_id:
            continue
        tombstone = dict(record)
        tombstone.update(
            {
                "resource": "",
                "resource_scope": {},
                "before_summary": {},
                "after_summary": {},
                "actor_username": "[REDACTED]",
                "owner_id": "",
                "request_id": "",
                "payload": {
                    "event_id": event_id,
                    "action": record.get("action", ""),
                    "outcome": record.get("outcome", ""),
                    "created_at": record.get("created_at", ""),
                    "purged_at": _iso(reference),
                    "purge_reason": "retention_window_elapsed",
                },
                "purged_at": _iso(reference),
                # Clearing the window stops a tombstone from being re-purged, and
                # PostgreSQL keeps the marker inside ``payload``.
                "expires_at": None,
            }
        )
        try:
            _persistence.upsert(AUDIT_COLLECTION, event_id, tombstone)
        except Exception as exc:
            _storage["write_failures"] += 1
            _log_repeated(
                f"audit_purge_failed:{type(exc).__name__}",
                f"审计事件保留期清理写入失败 event_id={event_id}："
                f"{type(exc).__name__}: {exc}",
            )
            continue
        purged += 1

    if purged:
        _hydrate_view(force=True)
    return {
        "status": "ok",
        "reason": "purged" if purged else "purge_failed",
        "checked": len(records),
        "expired": len(expired),
        "purged": purged,
    }


def configure_audit_storage(
    *,
    persistence: Any = None,
    backend: str | None = None,
    database_url: str | None = None,
    fallback_path: Any = None,
) -> dict:
    """Rebind the audit journal to an explicit adapter (used by tests and migrations)."""
    global _injected_persistence, _storage_arguments, _storage_ready, _view_ready, _persistence
    with _lock:
        _injected_persistence = persistence
        arguments: dict[str, Any] = {}
        if backend:
            arguments["backend"] = backend
        if database_url:
            arguments["database_url"] = database_url
        if fallback_path is not None:
            arguments["fallback_path"] = fallback_path
        _storage_arguments = arguments
        _persistence = None
        _storage = {}
        _storage_ready = False
        _view_ready = False
        _events.clear()
        _error_counts.clear()
    return audit_storage_status()


def reset_audit_storage() -> dict:
    """Forget every cached adapter and view so the next call re-reads the environment."""
    return configure_audit_storage()