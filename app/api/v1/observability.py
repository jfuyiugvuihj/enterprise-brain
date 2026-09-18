"""Read-only management-plane routes for retrieval, trace, evaluation and audit data.

Every engine behind these four routes already existed and was already unit tested; what
was missing was an HTTP surface, so an operator could not reach a replay, an evaluation
report or an audit trail at all. This module adds no second identity model, no second
authorization rule and no second error body:

* the subject comes from ``app.common.authorization.principal_from_request``;
* the decision comes from ``app.common.policy.authorization_decision``;
* every error body is an ``ErrorEnvelope`` from ``app.agents.contracts``;
* a request without a Principal fails closed as ``401 authentication_required`` and is
  never promoted to an administrator.
"""

import importlib.util
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.agents.contracts import ErrorEnvelope, Principal
from app.common import audit as audit_log
from app.common.authorization import principal_from_request
from app.common.permissions import ACTION_AUDIT, ACTION_VIEW
from app.common.policy import authorization_decision
from app.rag.debug import run_retrieval_debug
from app.rag.filters import RetrievalScopeError
from app.trace.store import TraceStoreError

router = APIRouter(tags=["observability"])

DEFAULT_TOP_K = 5
MAX_TOP_K = 20
MAX_QUERY_CHARS = 500
MAX_TRACE_ID_CHARS = 200
MAX_TRACE_EVENTS = 200
DEFAULT_AUDIT_EVENTS = 100
MAX_AUDIT_EVENTS = 200
MAX_EVALUATION_REPORTS = 20
MAX_EVALUATION_CASES = 500
MAX_EVALUATION_CATEGORIES = 30
MAX_EVALUATION_FILE_BYTES = 524_288
MAX_REWRITES = 5
MAX_EXCERPT_CHARS = 240
MAX_DICT_ITEMS = 40
MAX_LIST_ITEMS = 50
MAX_STRING_CHARS = 2_000
ADMIN_ROLE = "admin"
EVALUATION_READ_ACTION = "evaluation:read"
AUDIT_EVENT_SOURCE = "app.common.audit.get_audit_events"
DEFAULT_EVALUATION_REPORT_FILES = ("docs/testing/evaluation-report.json",)
DEFAULT_EVALUATION_SET_PATHS = ("tests/fixtures/business_evaluation_30.jsonl",)
EVALUATION_COMMAND_TEMPLATE = (
    "python scripts/run_quality_evaluation.py --fixture {fixture} "
    "--answers {answers} --output {output}"
)

_RETRIEVAL_CAPABILITIES = (
    ("chromadb", "vector_store", "chroma_persistent_client", "offline_json_collection"),
    ("rank_bm25", "keyword_scoring", "rank_bm25", "token_overlap_shim"),
    ("jieba", "tokenizer", "jieba", "naive_char_or_whitespace"),
    ("sentence_transformers", "reranker", "cross_encoder", "rrf_only"),
)
_SCOPE_ERROR_STATUS = {
    "authentication_required": 401,
    "permission_denied": 403,
    "authorization_unavailable": 403,
}
_REPORT_RATIO_KEYS = ("answer_correctness", "evidence_coverage", "unsupported_claim_rate")
_REPORT_LATENCY_KEYS = ("count", "average", "p95")


class ApiError(BaseModel):
    """The body FastAPI really emits: an ``ErrorEnvelope`` nested under ``detail``."""

    detail: ErrorEnvelope


class RetrievalDebugRequest(BaseModel):
    query: str = ""
    top_k: int | None = None
    index_version_id: str = ""
    strategy_version: str = ""
    trace_id: str = ""
    request_id: str = ""


_ERROR_RESPONSES = {
    400: {"model": ApiError, "description": "validation_error"},
    401: {"model": ApiError, "description": "authentication_required"},
    403: {"model": ApiError, "description": "permission_denied"},
    404: {"model": ApiError, "description": "resource_not_found"},
    500: {"model": ApiError, "description": "internal_error"},
}


def _fail(
    status_code: int,
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
) -> NoReturn:
    envelope = ErrorEnvelope(
        code=code,
        message=message,
        retryable=retryable,
        details=dict(details or {}),
    )
    raise HTTPException(status_code=status_code, detail=envelope.model_dump())


def _roles_of(principal: Principal) -> list[str]:
    roles = [str(role) for role in (principal.roles or []) if str(role)]
    return roles or [principal.role]


def _principal_summary(principal: Principal) -> dict[str, Any]:
    return {
        "username": principal.username,
        "roles": _roles_of(principal),
        "department": principal.department,
        "clearance": principal.clearance,
        "auth_source": principal.auth_source,
    }


def _principal_or_fail(request: Request, resource: str) -> Principal:
    principal = principal_from_request(request)
    if principal is None:
        _fail(
            401,
            "authentication_required",
            f"{resource} requires an authenticated principal.",
            details={"resource": resource},
        )
    return principal


def _deny(principal: Principal, action: str, resource: str, reason_code: str) -> NoReturn:
    audit_log.record_audit(principal, action, "denied", resource, reason_code)
    _fail(
        403,
        "permission_denied",
        f"{action} is not permitted for this principal.",
        details={
            "resource": resource,
            "action": action,
            "reason_code": reason_code,
            "username": principal.username,
        },
    )


def _require_action(request: Request, action: str, resource: str) -> Principal:
    """Default-deny gate delegated to the shared resource policy."""
    principal = _principal_or_fail(request, resource)
    decision = authorization_decision(principal, None, action=action)
    if not decision.allowed:
        _deny(principal, action, resource, decision.reason_code)
    return principal


def _require_admin(request: Request, action: str, resource: str) -> Principal:
    """The role gate is explicit: an empty Principal never means administrator."""
    principal = _principal_or_fail(request, resource)
    if principal.status != "active":
        _deny(principal, action, resource, "principal_inactive")
    if ADMIN_ROLE not in _roles_of(principal):
        _deny(principal, action, resource, "admin_role_required")
    return principal


def _clamped(
    requested: int | None,
    *,
    default: int,
    maximum: int,
    minimum: int = 1,
) -> tuple[int, bool]:
    """Return ``(applied, clamped)`` for a client supplied ceiling."""
    candidate = default if requested is None else requested
    try:
        number = int(candidate)
    except (TypeError, ValueError):
        number = default
    applied = max(minimum, min(number, maximum))
    return applied, applied != number


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _bounded_value(value: Any) -> tuple[Any, bool]:
    """Cap collection breadth and string length so a replay cannot size the response."""
    if isinstance(value, dict):
        bounded: dict[Any, Any] = {}
        truncated = False
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_DICT_ITEMS:
                truncated = True
                break
            bounded[key], item_truncated = _bounded_value(item)
            truncated = truncated or item_truncated
        return bounded, truncated
    if isinstance(value, (list, tuple)):
        truncated = len(value) > MAX_LIST_ITEMS
        items = [_bounded_value(item)[0] for item in list(value)[:MAX_LIST_ITEMS]]
        return items, truncated
    if isinstance(value, str):
        return value[:MAX_STRING_CHARS], len(value) > MAX_STRING_CHARS
    if isinstance(value, bool) or value is None:
        return value, False
    if isinstance(value, (int, float)):
        finite = _finite_float(value)
        return finite, finite is None
    number = _finite_float(value)
    if number is not None:
        return number, False
    text = str(value)
    return text[:MAX_STRING_CHARS], len(text) > MAX_STRING_CHARS


def _normalized_result(document: Any) -> dict[str, Any]:
    result = dict(document) if isinstance(document, dict) else {"source": str(document)}
    source = str(result.get("source", ""))
    excerpt = str(result.get("excerpt", ""))
    result["source"] = source[:MAX_STRING_CHARS]
    result["excerpt"] = excerpt[:MAX_EXCERPT_CHARS]
    result["score"] = _finite_float(result.get("score"))
    return result


def _bounded_report(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep the debug report bounded regardless of what the pipeline returned."""
    rewrites = [str(item) for item in (report.get("rewrites") or [])]
    results = list(report.get("results") or [])
    permission_filter, filter_truncated = _bounded_value(report.get("permission_filter") or {})
    bounded_results, results_truncated = _bounded_value(
        [_normalized_result(item) for item in results[:MAX_TOP_K]]
    )
    bounded = dict(report)
    bounded["permission_filter"] = permission_filter
    bounded["rewrites"] = [item[:MAX_STRING_CHARS] for item in rewrites[:MAX_REWRITES]]
    bounded["results"] = bounded_results
    bounded["stages"], stages_truncated = _bounded_value(list(report.get("stages") or []))
    bounds = {
        "rewrites_total": len(rewrites),
        "rewrites_returned": min(len(rewrites), MAX_REWRITES),
        "results_total": len(results),
        "results_returned": min(len(results), MAX_TOP_K),
        "excerpt_max_chars": MAX_EXCERPT_CHARS,
        "string_max_chars": MAX_STRING_CHARS,
        "truncated": bool(
            len(rewrites) > MAX_REWRITES
            or len(results) > MAX_TOP_K
            or filter_truncated
            or results_truncated
            or stages_truncated
        ),
    }
    return bounded, bounds


def _bounded_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pass every recorded field through, so a richer event schema is never hidden."""
    bounded = []
    for event in events:
        item, _truncated = _bounded_value(event if isinstance(event, dict) else str(event))
        bounded.append(item)
    return bounded


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def retrieval_environment() -> dict[str, Any]:
    """State which optional retrieval engines are importable on this machine."""
    available: dict[str, bool] = {}
    engines: dict[str, str] = {}
    missing: list[str] = []
    for name, capability, installed_engine, fallback_engine in _RETRIEVAL_CAPABILITIES:
        present = _module_available(name)
        available[name] = present
        engines[capability] = installed_engine if present else fallback_engine
        if not present:
            missing.append(name)
    return {
        "optional_dependencies": available,
        "engines": engines,
        "missing_dependencies": missing,
        "degraded": bool(missing),
        "note": (
            "A degraded stack still returns a permission-scoped, structurally bounded "
            "report; it is not evidence about recall quality."
        ),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evaluation_report_candidates() -> list[Path]:
    configured = os.getenv("EVALUATION_REPORT_DIRS", "") or os.getenv("EVALUATION_REPORT_DIR", "")
    entries = [item.strip() for item in configured.split(os.pathsep) if item.strip()]
    candidates: list[Path] = []
    for entry in entries:
        path = Path(entry)
        if path.is_file():
            candidates.append(path)
        elif path.is_dir():
            candidates.extend(sorted(path.glob("*.json")))
    for name in DEFAULT_EVALUATION_REPORT_FILES:
        path = Path(name)
        if path.is_file() and path not in candidates:
            candidates.append(path)
    return [path for path in candidates if path.suffix.lower() == ".json"]


def _suite_paths() -> list[str]:
    configured = os.getenv("EVALUATION_SET_PATHS", "")
    entries = [item.strip() for item in configured.split(os.pathsep) if item.strip()]
    return entries or list(DEFAULT_EVALUATION_SET_PATHS)


def _report_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if "total" in payload:
        try:
            metrics["total"] = int(payload["total"])
        except (TypeError, ValueError):
            pass
    for key in _REPORT_RATIO_KEYS:
        if key in payload:
            number = _finite_float(payload[key])
            if number is not None:
                metrics[key] = number
    latency = payload.get("latency_ms")
    if isinstance(latency, dict):
        for key in _REPORT_LATENCY_KEYS:
            if key in latency:
                number = _finite_float(latency[key])
                if number is not None:
                    metrics[f"latency_{key}"] = number
    return metrics


def _report_summary(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": path.stem,
        "path": path.as_posix(),
        "status": "unreadable",
        "metrics": {},
    }
    try:
        stat = path.stat()
    except OSError:
        return record
    record["size_bytes"] = stat.st_size
    record["modified_at"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
    if stat.st_size > MAX_EVALUATION_FILE_BYTES:
        record["status"] = "too_large"
        return record
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return record
    if not isinstance(payload, dict):
        return record
    record["status"] = "ok"
    record["metrics"] = _report_metrics(payload)
    categories = payload.get("category_metrics")
    record["category_count"] = len(categories) if isinstance(categories, dict) else 0
    return record


def _suite_summary(path: Path) -> dict[str, Any]:
    suite: dict[str, Any] = {
        "id": path.stem,
        "path": path.as_posix(),
        "exists": False,
        "case_count": 0,
        "categories": [],
        "truncated": False,
    }
    if not path.is_file():
        return suite
    suite["exists"] = True
    categories: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return suite
    for line in lines[:MAX_EVALUATION_CASES]:
        if not line.strip():
            continue
        suite["case_count"] += 1
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            category = str(row.get("category") or "")
            if category and category not in categories:
                categories.append(category)
    suite["truncated"] = len(lines) > MAX_EVALUATION_CASES
    suite["categories"] = categories[:MAX_EVALUATION_CATEGORIES]
    return suite


def _pipeline() -> Any:
    """Reuse the process-wide pipeline; a debug route must not build a second index."""
    from app.agents.tools import _get_pipeline

    return _get_pipeline()


def _trace_store() -> Any:
    from app.trace.store import default_trace_store

    return default_trace_store()


@router.post("/retrieval/debug", responses=_ERROR_RESPONSES)
async def retrieval_debug(payload: RetrievalDebugRequest, request: Request) -> dict[str, Any]:
    """Run one permission-scoped retrieval and return a bounded, replayable report."""
    principal = _require_action(request, ACTION_VIEW, "retrieval/debug")
    query = str(payload.query or "").strip()
    if not query:
        _fail(400, "validation_error", "query is required.", details={"field": "query"})
    if len(query) > MAX_QUERY_CHARS:
        _fail(
            400,
            "validation_error",
            f"query exceeds {MAX_QUERY_CHARS} characters.",
            details={"field": "query", "max_chars": MAX_QUERY_CHARS},
        )
    applied_top_k, top_k_clamped = _clamped(payload.top_k, default=DEFAULT_TOP_K, maximum=MAX_TOP_K)
    trace_id = str(payload.trace_id or "").strip() or f"retrieval-debug:{uuid4().hex}"
    request_id = str(payload.request_id or "").strip() or f"retrieval-debug:{uuid4().hex}"
    for field, value in (("trace_id", trace_id), ("request_id", request_id)):
        if len(value) > MAX_TRACE_ID_CHARS:
            _fail(
                400,
                "validation_error",
                f"{field} exceeds {MAX_TRACE_ID_CHARS} characters.",
                details={"field": field, "max_chars": MAX_TRACE_ID_CHARS},
            )
    try:
        report = run_retrieval_debug(
            query,
            principal,
            pipeline=_pipeline(),
            trace_store=_trace_store(),
            trace_id=trace_id,
            request_id=request_id,
            index_version_id=str(payload.index_version_id or "").strip(),
            strategy_version=str(payload.strategy_version or "").strip(),
            top_k=applied_top_k,
        )
    except RetrievalScopeError as exc:
        code = exc.code if exc.code in _SCOPE_ERROR_STATUS else "authorization_unavailable"
        _fail(
            _SCOPE_ERROR_STATUS.get(code, 403),
            code,
            str(exc),
            details={"stage": "retrieval_scope", "resource": "retrieval/debug"},
        )
    except TraceStoreError as exc:
        _fail(
            400,
            exc.code if exc.code in _SCOPE_ERROR_STATUS else "validation_error",
            str(exc),
            details={"stage": "trace_store"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        _fail(
            500,
            "internal_error",
            f"retrieval debug failed: {type(exc).__name__}",
            details={"stage": "retrieval_pipeline"},
        )
    bounded, bounds = _bounded_report(report)
    audit_log.record_audit(principal, ACTION_VIEW, "allowed", "retrieval/debug", "permission_granted")
    return {
        **bounded,
        "trace_id": trace_id,
        "request_id": request_id,
        "replay_path": f"/api/v1/traces/{trace_id}",
        "requested_by": _principal_summary(principal),
        "scope_versions": {
            "index_version_id": bounded.get("index_version_id", ""),
            "strategy_version": bounded.get("strategy_version", ""),
            "source": "request_body",
            "server_verified": False,
        },
        "bounds": bounds,
        "limits": {
            "default_top_k": DEFAULT_TOP_K,
            "max_top_k": MAX_TOP_K,
            "requested_top_k": payload.top_k,
            "applied_top_k": applied_top_k,
            "clamped": top_k_clamped,
        },
        "retrieval_environment": retrieval_environment(),
        "generated_at": _now(),
    }


@router.get("/traces/{trace_id}", responses=_ERROR_RESPONSES)
async def read_trace(trace_id: str, request: Request, limit: int | None = None) -> dict[str, Any]:
    """Replay one recorded trace for an auditor."""
    principal = _require_action(request, ACTION_AUDIT, f"traces/{trace_id}")
    normalized = str(trace_id or "").strip()
    if not normalized:
        _fail(400, "validation_error", "trace_id is required.", details={"field": "trace_id"})
    if len(normalized) > MAX_TRACE_ID_CHARS:
        _fail(
            400,
            "validation_error",
            f"trace_id exceeds {MAX_TRACE_ID_CHARS} characters.",
            details={"field": "trace_id", "max_chars": MAX_TRACE_ID_CHARS},
        )
    applied_limit, limit_clamped = _clamped(
        limit, default=MAX_TRACE_EVENTS, maximum=MAX_TRACE_EVENTS
    )
    try:
        events = _trace_store().replay(normalized)
    except HTTPException:
        raise
    except Exception as exc:
        _fail(
            500,
            "internal_error",
            f"trace replay failed: {type(exc).__name__}",
            details={"stage": "trace_store"},
        )
    events = list(events or [])
    page = events[:applied_limit]
    if not page:
        _fail(
            404,
            "resource_not_found",
            f"No trace events are recorded for trace_id {normalized!r}.",
            details={"trace_id": normalized},
        )
    return {
        "trace_id": normalized,
        "requested_by": _principal_summary(principal),
        "event_count": len(page),
        "events_total": len(events),
        "truncated": len(events) > len(page),
        "first_sequence": page[0].get("sequence") if isinstance(page[0], dict) else None,
        "last_sequence": page[-1].get("sequence") if isinstance(page[-1], dict) else None,
        "events": _bounded_events(page),
        "limits": {
            "max_events": MAX_TRACE_EVENTS,
            "applied_limit": applied_limit,
            "requested_limit": limit,
            "clamped": limit_clamped,
        },
    }


def _stage_report_from_trace(trace_id: str) -> dict[str, Any]:
    """Fold one persisted trace into the R51 stage ledger, from recorded bytes only.

    The events this reads were written by the execution boundaries that already exist;
    nothing here re-runs a request, so an operator can audit yesterday's trace.
    """
    from app.common.stage_timing import (
        aggregate_stage_latency,
        request_windows_from_events,
        samples_from_events,
    )

    events = list(_trace_store().replay(trace_id) or [])
    if not events:
        _fail(
            404,
            "resource_not_found",
            f"No trace events are recorded for trace_id {trace_id!r}.",
            details={"trace_id": trace_id},
        )
    samples = samples_from_events(events)
    report = aggregate_stage_latency(
        samples,
        end_to_end_by_trace=request_windows_from_events(events),
    )
    report["samples"] = [sample.as_dict() for sample in samples]
    return report


@router.get("/stage-latency", responses=_ERROR_RESPONSES)
async def read_stage_latency(
    request: Request,
    trace_id: str | None = None,
    include_samples: bool = False,
) -> dict[str, Any]:
    """Read the stage ledger: P50/P95 per segment, plus the coverage arithmetic.

    With ``trace_id`` the answer comes from that one persisted trace, which is how
    judgement 2 -- the segments must add up to the request within one percent -- gets
    checked against real recorded bytes rather than a live process. Without it, the
    in-process rolling window is reported, the same block ``/health/details`` carries.
    """
    principal = _require_action(request, ACTION_AUDIT, "stage-latency")
    from app.common.stage_timing import stage_latency_readout

    normalized = str(trace_id or "").strip()
    if normalized and len(normalized) > MAX_TRACE_ID_CHARS:
        _fail(
            400,
            "validation_error",
            f"trace_id exceeds {MAX_TRACE_ID_CHARS} characters.",
            details={"field": "trace_id", "max_chars": MAX_TRACE_ID_CHARS},
        )
    if normalized:
        report = _stage_report_from_trace(normalized)
        report["scope"] = "trace"
        report["trace_id"] = normalized
    else:
        report = stage_latency_readout()
        report["scope"] = "process"
        report["requested_by"] = _principal_summary(principal)
    if not include_samples:
        report.pop("samples", None)
    return report


@router.get("/evaluations", responses=_ERROR_RESPONSES)
async def read_evaluations(request: Request, limit: int | None = None) -> dict[str, Any]:
    """List evaluation suites and stored reports without executing the model stack."""
    principal = _require_admin(request, EVALUATION_READ_ACTION, "evaluations")
    applied_limit, limit_clamped = _clamped(
        limit, default=MAX_EVALUATION_REPORTS, maximum=MAX_EVALUATION_REPORTS
    )
    candidates = _evaluation_report_candidates()
    summaries = [_report_summary(path) for path in candidates[:applied_limit]]
    suites = [_suite_summary(Path(name)) for name in _suite_paths()]
    return {
        "status": "reports_available" if summaries else "no_reports",
        "requested_by": _principal_summary(principal),
        "generated_at": _now(),
        "reports": summaries,
        "reports_total": len(candidates),
        "truncated": len(candidates) > len(summaries),
        "evaluation_sets": suites,
        "execution": {
            "runs_on_request": False,
            "reason": (
                "An evaluation executes the full retrieval and model stack over every "
                "case, so it cannot run inside a read-only management request."
            ),
            "command_template": EVALUATION_COMMAND_TEMPLATE,
            "report_module": "app.quality.runner.run_recorded_evaluation",
        },
        "limits": {
            "max_reports": MAX_EVALUATION_REPORTS,
            "applied_limit": applied_limit,
            "requested_limit": limit,
            "clamped": limit_clamped,
        },
    }


@router.get("/audit/events", responses=_ERROR_RESPONSES)
async def read_audit_events(
    request: Request,
    username: str = "",
    action: str = "",
    outcome: str = "",
    limit: int | None = None,
) -> dict[str, Any]:
    """Read the audit trail newest-first; this route never writes an allowed event."""
    principal = _require_action(request, ACTION_AUDIT, "audit/events")
    applied_limit, limit_clamped = _clamped(
        limit, default=DEFAULT_AUDIT_EVENTS, maximum=MAX_AUDIT_EVENTS
    )
    filters = {
        key: str(value or "").strip()
        for key, value in (("username", username), ("action", action), ("outcome", outcome))
        if str(value or "").strip()
    }
    events = list(audit_log.get_audit_events() or [])
    matching = [
        event
        for event in events
        if all(str((event or {}).get(key) or "") == value for key, value in filters.items())
    ]
    page = list(reversed(matching))[:applied_limit]
    return {
        "requested_by": _principal_summary(principal),
        "source": AUDIT_EVENT_SOURCE,
        "filters": filters,
        "events": _bounded_events(page),
        "event_count": len(page),
        "events_total": len(matching),
        "recorded_total": len(events),
        "truncated": len(matching) > len(page),
        "order": "newest_first",
        "limits": {
            "default_limit": DEFAULT_AUDIT_EVENTS,
            "max_limit": MAX_AUDIT_EVENTS,
            "applied_limit": applied_limit,
            "requested_limit": limit,
            "clamped": limit_clamped,
        },
    }