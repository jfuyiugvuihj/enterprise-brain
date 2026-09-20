from dataclasses import dataclass, asdict
import hashlib
import hmac
import json
import os
import secrets
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


#: The only two facts for which this registry refuses a write, named once here so that
#: every surface which has to state one of them states the same word.
#:
#: ``register_application`` raises ``ProductionReadOnlyProtection`` from two places that
#: mean opposite things. Either no store was ever asked for, and a production process
#: keeps applications nowhere, in a dictionary that dies with the worker -- a deployment
#: which never switched this feature on. Or a store was named and then failed the write,
#: which is an outage. Carrying both under one word told customers to retry something no
#: retry can change, let monitoring bill a disabled feature as downtime, and left the
#: audit trail blaming the disk for what is an operator's unfinished configuration.
#:
#: The second word is the one this exit has always answered with. A store that fails
#: really is read-only from the caller's seat, and a term an operator's runbook already
#: keys on is not ours to rename here.
STORAGE_REFUSAL_UNCONFIGURED = "open_platform_unconfigured"
STORAGE_REFUSAL_WRITE_FAILED = "storage_read_only"


#: ``max_clearance`` is recorded and consulted by nothing. No path in this application
#: compares it with a document's classification, and no Principal receives it. Whether a
#: level 2 caller may read a level 3 chunk is the owner's ruling to make -- open
#: decision H13, undecided -- and inventing one here would install a second,
#: unpublished clearance policy in the place that is supposed to be honest about not
#: having one. What is ours to fix is the appearance: a number sitting in a registry
#: reads like a control, so every surface that shows it now says that it decides
#: nothing until the owner rules.
MAX_CLEARANCE_ENFORCED = False
MAX_CLEARANCE_EFFECT = "registered_only"
MAX_CLEARANCE_NOTE = (
    "registered value only: no retrieval, no preview, and no Principal reads this "
    "field. The clearance comparison rule is pending the owner's ruling (open decision "
    "H13); until it lands, a higher value buys nothing and a lower one blocks nothing."
)


def clearance_registration(max_clearance: Any) -> dict[str, Any]:
    """Report one registered clearance together with the fact that it decides nothing.

    Written once so the registration response, the application list, and the request
    model cannot give three different answers about the same field.
    """
    try:
        value = max(1, int(max_clearance))
    except (TypeError, ValueError):
        value = 1
    return {
        "max_clearance": value,
        "max_clearance_effect": MAX_CLEARANCE_EFFECT,
        "max_clearance_enforced": MAX_CLEARANCE_ENFORCED,
        "max_clearance_note": MAX_CLEARANCE_NOTE,
    }


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
    """Report where application credentials live: durable store, memory, or nowhere.

    A state which refuses writes also says why, under ``reason``. That field is the one
    answer three surfaces quote: the status and detail of ``POST /api/v1/apps``, the
    reason written beside it in the audit, and this dict as published by
    ``/api/v1/health/details``. A durable store and the development dictionary accept
    writes, so neither carries a reason: an explanation would imply a refusal which
    never happened.
    """
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
            # A store was asked for by name and this process could not open or could not
            # write it. The disk is the news, so the word stays the one meaning disk.
            "reason": STORAGE_REFUSAL_WRITE_FAILED,
            "detail": error,
        }
    if _is_production_environment():
        return {
            "storage_mode": "unavailable",
            "durable": False,
            "shared_across_processes": False,
            "protection": "read_only",
            # ``protection`` says what happens to the write; this says why, which is the
            # half an operator can act on and the half the HTTP exit may answer with.
            "reason": STORAGE_REFUSAL_UNCONFIGURED,
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
                **clearance_registration(record.max_clearance),
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


#: ``app_id`` is 16 hex characters and ``secret`` is 64. Both are persisted as strings and
#: handed to third-party integrations, so the widths are a published shape, not a detail.
APP_ID_HEX_CHARS = 16
APP_SECRET_HEX_CHARS = 64
_APP_ID_BYTES = APP_ID_HEX_CHARS // 2
_APP_SECRET_BYTES = APP_SECRET_HEX_CHARS // 2

#: How many times one registration redraws an identity that is already taken before it
#: gives up. Two collisions in a row on a 64-bit id is not a realistic event, but
#: "not realistic" is exactly what the silent overwrite used to rest on.
_IDENTITY_ATTEMPTS = 8

#: The refusal when every draw collided. It stays in the family ``app_name_required``
#: and ``allowed_actions_required`` already use -- a bare ``ValueError`` the admin route
#: turns into a 400 -- because the ratified error-code vocabulary is closed and this is
#: not a code worth widening it for.
APP_ID_COLLISION = "app_id_collision"


class _AppIdTaken(ValueError):
    """Internal signal: this id already belongs to another application."""


def _new_app_id() -> str:
    """Draw an application id from the operating system's CSPRNG.

    This used to be ``sha256(f"{name}:{time.time_ns()}")[:16]``. A wall clock is not a
    unique-value source: on Windows it advances about 64 times a second, so two adjacent
    registrations of one name hash the same string into the same id. Measured on this
    machine, four registrations in a row collapsed into two.
    """
    return secrets.token_hex(_APP_ID_BYTES)


def _new_app_secret() -> str:
    """Draw a signing secret on its own, from the same CSPRNG.

    Deliberately not derived from the id it ships beside: ``app_id`` is in the
    administrator's application list and in every audit row this transport writes, so a
    secret computed from it is one anybody who can read that list can recompute. The old
    line hashed ``name:app_id:time_ns``, which was both predictable and -- whenever two
    registrations collided -- the same secret for two different applications.
    """
    return secrets.token_hex(_APP_SECRET_BYTES)


def _identity_is_free(app_id: str, store) -> bool:
    """True only when no application holds this id, in this process or on disk.

    The durable half is not decoration: another worker can hold a row this cache has
    never seen, and ``upsert`` keys on the id, so a collision only the file can see would
    still rewrite somebody else's application. A store this process cannot read counts as
    holding every id, because an id it might be holding is not one this call may claim.
    """
    if app_id in _APP_REGISTRY:
        return False
    if store is None:
        return True
    from app.storage.persistence import PersistenceWriteError

    try:
        held = store.get(_STORE_COLLECTION, app_id) is not None
    except (PersistenceWriteError, OSError, ValueError):
        return False
    return not held


def _install_application(record: OpenApplication, store) -> None:
    """The only write path into the registry, and it refuses to replace an existing row.

    What sat here before was a bare ``_APP_REGISTRY[app_id] = record``. On a colliding id
    that swapped one application's actions, departments, clearance and enabled flag for
    another's while the write-through repeated the swap on disk, and the caller was still
    handed the secret that had been issued for the first row. Callers hold ``_LOCK``.
    """
    if not _identity_is_free(record.app_id, store):
        raise _AppIdTaken(APP_ID_COLLISION)
    _APP_REGISTRY[record.app_id] = record


def _mint_application(app_name: str, *, actions, departments, max_clearance, description, store) -> OpenApplication:
    """Draw an identity until a free one is installed, or the draws run out.

    A collision is regenerated, never overwritten; running out of draws refuses the
    registration in the open rather than leaving one application signed with another
    one's permissions.
    """
    for _attempt in range(_IDENTITY_ATTEMPTS):
        candidate = OpenApplication(
            app_id=_new_app_id(),
            secret=_new_app_secret(),
            app_name=app_name,
            allowed_actions=actions,
            allowed_departments=departments,
            max_clearance=max_clearance,
            description=description,
        )
        try:
            _install_application(candidate, store)
        except _AppIdTaken:
            continue
        return candidate
    raise ValueError(APP_ID_COLLISION)


def register_application(app_name: str, *, allowed_actions: list[str], allowed_departments: list[str] | None = None, max_clearance: int = 3, description: str = "") -> dict[str, str]:
    """Register an open-platform application and return its one-time secret.

    Production requires a durable store: a registration that only lives in this
    process disappears on restart and is invisible to the other workers, which would
    silently break every signed request that another instance issued.

    ``max_clearance`` is stored and consulted by nothing: see
    ``clearance_registration``, which the registration and list responses carry.

    Two applications may share a name, and this is the function that decides what that
    means: every call registers a new application with its own id and its own secret, and
    none of them replaces another. Nothing here looks an application up by name, and no
    caller may start doing that to mean "update that one": the id is the identity, the
    name is a label. The id is drawn from a CSPRNG instead of derived from the name and
    the clock, and ``_install_application`` refuses to write over a row even when a drawn
    id somehow already exists -- see ``test_r80_app_identity_collision.py`` for what the
    old derivation cost: same-name registrations landing on one id, one shared secret,
    and the first application's whole grant replaced by the second.
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
    from app.storage.persistence import PersistenceWriteError

    departments = tuple(
        str(item).strip() for item in (allowed_departments or ()) if str(item).strip()
    )
    with _LOCK:
        record = _mint_application(
            name,
            actions=tuple(actions),
            departments=departments,
            max_clearance=max(1, int(max_clearance)),
            description=str(description or ""),
            store=store,
        )
        if store is not None:
            try:
                store.upsert(_STORE_COLLECTION, record.app_id, asdict(record))
            except (PersistenceWriteError, OSError, ValueError) as exc:
                # Roll back the row this call added, and only that row: the registry also
                # holds every other application, and one failed write is no licence to
                # prune or clear what somebody else registered.
                if _APP_REGISTRY.get(record.app_id) is record:
                    _APP_REGISTRY.pop(record.app_id, None)
                _STORE["error"] = f"application store write failed: {type(exc).__name__}"
                raise ProductionReadOnlyProtection("open_platform_store_write_failed") from exc
            _STORE["loaded"] = True
            try:
                _STORE["mtime"] = os.path.getmtime(store.path)
            except OSError:  # pragma: no cover - the file was just written
                _STORE["mtime"] = None
    return {"app_id": record.app_id, "secret": record.secret, "app_name": name}


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


# ---------------------------------------------------------------------- caller claims
#: Header an application uses to name the person it says it is acting for. Nothing
#: signs it: ``build_request_signature`` covers ``app_id.timestamp.body``, exactly like
#: the department header R71 had to stop trusting. A gateway legitimately wants its own
#: operator in the log, so the value is kept -- kept as what it is, a claim the caller
#: made about itself, and never as the actor of an audit row. A row filed under
#: "alice" joins alice's history in every audit view that filters by username, and
#: that is the whole of what an unsigned header must not be allowed to do.
OPEN_USER_CLAIM_HEADER = "x-open-user"
OPEN_USER_CLAIM_KEY = "open_user_claimed"
OPEN_USER_CLAIM_SIGNED_KEY = "open_user_signed"

#: Actor marker for a call made by an application: built from the app id the signature
#: authenticated, so it cannot be forged, and prefixed, so it cannot be mistaken for a
#: person's login name.
OPEN_ACTOR_PREFIX = "open-app:"


def open_actor_username(app_id: str) -> str:
    """The only username this transport may blame for a call: an application, not a person."""
    return f"{OPEN_ACTOR_PREFIX}{app_id}"


def open_user_claim_fields(claim: str) -> dict[str, Any]:
    """The audit shape of that claim: preserved, attributed, and marked as unsigned."""
    return {
        OPEN_USER_CLAIM_KEY: str(claim or ""),
        OPEN_USER_CLAIM_SIGNED_KEY: False,
    }


def open_audit_principal(principal: Principal, app_record: dict[str, Any]) -> Principal:
    """The subject to write in the journal for one verified open-platform call.

    Same id, same role, same department, one different username: ``actor`` comes from
    the registry row the signature authenticated, so no header decides who is blamed.
    The Principal ``verify_open_request`` hands back deliberately keeps the claimed
    name, because two transports read it today -- ``tests/test_open_platform.py`` and
    R67's pinned "the index is asked as the verified caller" -- and nothing behind it
    decides a scope. The department comes from the grant, the id from the signature,
    the clearance from the role, and never from a header. Attribution is the one thing
    the claim could reach, so attribution is what changes.
    """
    actor = str((app_record or {}).get("actor") or "")
    if not actor:
        return principal
    return principal.model_copy(update={"username": actor})


def verify_open_request(headers: dict[str, Any], body: str, required_action: str) -> tuple[Principal, dict]:
    """Authenticate one signed call, and keep the signed part apart from the asserted part.

    The answer is the request subject plus the registry row it was authenticated
    against, with two additions a row cannot make about a call: ``actor``, the name the
    journal blames, and ``open_user_claimed``, the name the caller typed for it. Both
    the refusal and the success row are filed under ``actor``.
    """
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

    # The department starts empty on purpose: it is resolved from the registry below,
    # never read out of the headers, so the subject on the denial row is the same
    # application that asked, minus a claim it is not entitled to make.
    claim = normalized.get(OPEN_USER_CLAIM_HEADER, "").strip()
    principal = Principal.from_user(
        {
            "id": app_id,
            # A label the caller chose, not a name this server verified: clients already
            # read it, and nothing behind it decides a scope. The journal blames the
            # application instead -- see ``open_audit_principal``.
            "username": claim or record.app_name,
            "role": "staff",
            "department": "",
            "permissions": set(),
            "status": "active",
        },
        auth_source="open_platform",
    )
    app_record = asdict(record)
    app_record["actor"] = open_actor_username(app_id)
    app_record[OPEN_USER_CLAIM_KEY] = claim
    try:
        department = _resolve_open_department(record, normalized.get("x-open-department", ""))
    except HTTPException:
        record_audit(
            open_audit_principal(principal, app_record),
            f"open:{required_action}",
            "denied",
            record.app_name,
            DEPARTMENT_SELF_REPORT_DENIED,
            after_summary=open_user_claim_fields(claim),
        )
        raise
    principal = principal.model_copy(update={"department": department})
    record_audit(
        open_audit_principal(principal, app_record),
        f"open:{required_action}",
        "allowed",
        record.app_name,
        after_summary=open_user_claim_fields(claim),
    )
    return principal, app_record
