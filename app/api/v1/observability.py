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
from dataclasses import dataclass
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
REPORT_SOURCE_CONFIGURED = "configured"
REPORT_SOURCE_SHIPPED_DEFAULT = "shipped_default"
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


def _shipped_report_paths() -> set[Path]:
    """Absolute identities of the report files that ship inside the image.

    Resolved instead of compared as strings: the same bundled score can also arrive through
    a configured directory (the append at observability.py:333 is unconditional), and "which
    file is this" has to survive both spellings of it.
    """
    resolved: set[Path] = set()
    for name in DEFAULT_EVALUATION_REPORT_FILES:
        try:
            resolved.add(Path(name).resolve())
        except OSError:
            continue
    return resolved


def _report_provenance(path: Path) -> str:
    """Whether an operator asked for this report, or the image came with it.

    Since the first real score was committed, "no configured report dir" no longer means "no
    reports": the defaults are appended after the configured entries either way. That is only
    honest if the answer says which part of the list nobody asked for. Provenance is a
    property of the file, not of the discovery route -- the bundled score stays bundled even
    when an operator points a report dir at docs/testing.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return REPORT_SOURCE_CONFIGURED
    if resolved in _shipped_report_paths():
        return REPORT_SOURCE_SHIPPED_DEFAULT
    return REPORT_SOURCE_CONFIGURED


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


def _report_summary(path: Path, *, source: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": path.stem,
        "path": path.as_posix(),
        "source": source,
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


# ==================== R105 · three-tier SLO contract: shape and arithmetic, no numbers ====

#: R36 judgement 2, restated in 计划书 §3.1 ("P95 且样本 ≥100 条"): a percentile is
#: reportable only from at least this many samples of the distribution it describes.
#: Defined once, here. The contract document names this constant instead of carrying a
#: second copy of the number.
MIN_SLO_SAMPLES = 100

#: Every target slot in the contract starts empty on purpose. 乙半 fills it from the D14甲
#: window; nothing else may put a number in it, because no real sample has been drawn yet.
#: Writing "800 ms" here would be invented data, the same line R36 drew at demo corpora.
SLO_TARGET_PENDING = "awaiting_real_samples"

#: Readout verdicts. ``insufficient_samples`` exists because the alternative is a lie:
#: ``PerformanceStats.report()`` answers ``0`` for a distribution it has never seen
#: (``app/common/performance.py:27-28``), and a ``p95_ms`` of ``0`` is the most convincing
#: fake SLO this module could emit.
SLO_INSUFFICIENT = "insufficient_samples"
SLO_MEASURED = "measured"
SLO_NOT_MEASURABLE = "not_measurable"

#: Where a slot's distribution comes from. ``stage_ledger`` answers without reading
#: persisted traces; ``no_measurement_piece`` is a statement about the code, not about a
#: shortage of samples -- no amount of traffic will fill it.
SLO_SOURCE_LEDGER = "stage_ledger"
SLO_SOURCE_TRACE = "persisted_trace_events"
SLO_SOURCE_NONE = "no_measurement_piece"

#: Judgement 3 of this ticket, as a machine-readable pointer: percentiles come from this
#: one implementation or nowhere. Nothing in this file computes a rank.
SLO_PERCENTILE_SOURCE = (
    "app/common/performance.py::PerformanceStats"
    " (nearest rank: the value at ceil(n * q), 1-based)"
)

#: Where "屏" is defined. R104 made the router the only source, so a backend row may name
#: a route -- it may never invent one. tests/test_r105_slo_contract.py reads that file.
SLO_SCREEN_SOURCE = "frontend/src/router/index.js"

#: Why a slot cannot be computed even after the window has run, each entry pointing at the
#: code that proves it. These are the holes 乙半 has to close somewhere else first.
SLO_BLOCKERS: dict[str, str] = {
    "lane_attribution_absent": (
        "app/trace/spans.py:201-215 hands the ledger stage, tool_name, model_tier and worker "
        "but never a lane, and no request event carries the question, so every live sample "
        "groups under lanes.unknown and no per-tier population exists to take a P95 of."
    ),
    "first_token_not_a_stage_sample": (
        "first_token_at is recorded on a model span (app/trace/spans.py:174) and persisted "
        "(app/trace/store.py:259), but app/common/stage_timing.py:330-345 never reads it into "
        "a sample, so 首屏 is computable per trace and not from the in-process ledger."
    ),
    "wire_first_text_not_recorded": (
        "the plan's 首屏 is the first ``text`` event on the wire (计划书 §3.1). The only "
        "timestamped first-token evidence is model-side; chat.py:218-243 stamps canonical SSE "
        "envelopes but does not persist them, so a wire-side number would be a proxy."
    ),
    "cache_hits_are_not_traced": (
        "a cache hit returns its StreamingResponse at app/api/v1/chat.py:1191-1215, before any "
        "request.started event, so it records no window and no sample. The honest denominator "
        "for 缓存命中 is therefore zero today, not 'fast'."
    ),
    "wire_step_events_are_not_recorded": (
        "step.progress is persisted per graph superstep (app/agents/orchestrator.py:1173-1185), "
        "which measures how often the graph advanced, not when a client saw a ``step``/``status`` "
        "event; the interval the promise is about has no timestamped source."
    ),
    "export_leg_has_no_stage": (
        "app/common/stage_timing.py:71 maps export_report to no segment, so a report tier's file "
        "writing lands in unattributed. A five-stage sum is not that tier's end-to-end and must "
        "not be published as one; coverage_error_pct is what says so."
    ),
}


@dataclass(frozen=True)
class SloMetric:
    """One addressable number slot: 乙半 fills ``target``, and nothing else may write it."""

    name: str
    label_zh: str
    population: str
    source: str
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class SloTier:
    """One row of the contract: a product lane, the surface it is reachable on, its stages."""

    lane: str
    label_zh: str
    screen: str
    screen_path: str
    endpoints: tuple[str, ...]
    stages: tuple[str, ...]
    metrics: tuple[SloMetric, ...]
    note: str = ""


def slo_units() -> dict[str, Any]:
    """① : the three units the phrase "三档" collides, read live from their owners.

    计划书 R32 names 问答/分析/报告. ``app/agents/contracts.py:69 ModelTier`` names
    chat/plan/compress/rewrite/code/alert/analysis. ``app/common/stage_timing.py:48
    CANONICAL_STAGES`` names classify/rewrite/retrieve/generate/reflect. Three different
    enumerations over three different things, and no member of one may be renamed to
    flatter another -- so the bridge is read out of ``LANE_TIERS`` here instead of being
    retyped, and the document table below is pinned against this by a test.
    """
    from app.agents.contracts import ModelTier
    from app.agents.nodes import LANE_ANALYSIS, LANE_QA, LANE_REPORT, LANE_TIERS
    from app.common.stage_timing import CANONICAL_STAGES

    lanes = (LANE_QA, LANE_ANALYSIS, LANE_REPORT)
    return {
        "product_lane": {
            "owns_the_name": "app/agents/nodes.py (LANE_QA / LANE_ANALYSIS / LANE_REPORT)",
            "decided_by": "R42 classify_route, rules only, zero model calls",
            "members": list(lanes),
            "this_is_the_unit_of_the_slo": True,
        },
        "model_budget_tier": {
            "owns_the_name": "app/agents/contracts.py:69 ModelTier",
            "decided_by": "the call site that asks for budget",
            "members": [tier.value for tier in ModelTier],
            "this_is_the_unit_of_the_slo": False,
            "bridge_from_product_lane": {lane: LANE_TIERS[lane].value for lane in lanes},
            "bridge_note": (
                "not one-to-one: analysis and report share ModelTier.ANALYSIS, and six of the "
                "seven budget tiers belong to no lane at all"
            ),
        },
        "ledger_stage": {
            "owns_the_name": "app/common/stage_timing.py CANONICAL_STAGES",
            "decided_by": "classify_stage(), from label, tool, tier then worker",
            "members": list(CANONICAL_STAGES),
            "this_is_the_unit_of_the_slo": False,
        },
    }


def slo_tiers() -> tuple[SloTier, ...]:
    """② : 档 -> 屏/端点 -> stage 组, the only place this mapping is written down.

    Lane ids are imported from R42 and stage names from ``CANONICAL_STAGES``, so this table
    cannot drift from either. Screens are route names from the router: all three tiers share
    the ``chat`` screen because ``ChatPanel.vue`` is the only panel that calls ``/ask``
    (checked against the router source by tests/test_r105_slo_contract.py, which this ticket
    may not edit). "三屏" is therefore a name for three tiers, not for three screens, and the
    contract says so rather than inventing two more screens to match the phrase.
    """
    from app.agents.nodes import LANE_ANALYSIS, LANE_QA, LANE_REPORT
    from app.common.stage_timing import CANONICAL_STAGES

    stages = tuple(CANONICAL_STAGES)
    ask = ("POST /api/v1/ask",)
    return (
        SloTier(
            lane=LANE_QA,
            label_zh="问答档",
            screen="chat",
            screen_path="/chat",
            endpoints=ask,
            stages=stages,
            metrics=(
                SloMetric(
                    name="end_to_end_p95_ms",
                    label_zh="结论完成",
                    population=(
                        "one request in this lane that reached a terminal event, including "
                        "failed and cancelled ones"
                    ),
                    source=SLO_SOURCE_LEDGER,
                    blockers=("lane_attribution_absent",),
                ),
                SloMetric(
                    name="first_text_p95_ms",
                    label_zh="首屏（第一个 text 事件）",
                    population=(
                        "one streamed request in this lane: request.started to the first "
                        "model span that observed a token"
                    ),
                    source=SLO_SOURCE_TRACE,
                    blockers=(
                        "lane_attribution_absent",
                        "first_token_not_a_stage_sample",
                        "wire_first_text_not_recorded",
                    ),
                ),
                SloMetric(
                    name="cache_hit_p95_ms",
                    label_zh="缓存命中",
                    population="one cache-hit response on the ask path",
                    source=SLO_SOURCE_NONE,
                    blockers=("cache_hits_are_not_traced",),
                ),
            ),
            note=(
                "the default lane: R42 sends an unlabelled question here, so this row is also "
                "the one that answers 'what happens to a normal question'"
            ),
        ),
        SloTier(
            lane=LANE_ANALYSIS,
            label_zh="分析档",
            screen="chat",
            screen_path="/chat",
            endpoints=ask,
            stages=stages,
            metrics=(
                SloMetric(
                    name="end_to_end_p95_ms",
                    label_zh="端到端",
                    population=(
                        "one request in this lane that reached a terminal event, including "
                        "failed and cancelled ones"
                    ),
                    source=SLO_SOURCE_LEDGER,
                    blockers=("lane_attribution_absent",),
                ),
                SloMetric(
                    name="progress_interval_p95_ms",
                    label_zh="相邻进度事件的最大间隔",
                    population=(
                        "one gap between consecutive step.progress events inside a single trace"
                    ),
                    source=SLO_SOURCE_TRACE,
                    blockers=("lane_attribution_absent", "wire_step_events_are_not_recorded"),
                ),
            ),
        ),
        SloTier(
            lane=LANE_REPORT,
            label_zh="报告档",
            screen="chat",
            screen_path="/chat",
            endpoints=ask + ("GET /api/v1/queue/status/{request_id}",),
            stages=stages,
            metrics=(
                SloMetric(
                    name="end_to_end_p95_ms",
                    label_zh="端到端（含后台化后查回）",
                    population=(
                        "one request in this lane that reached a terminal event, queue entry "
                        "point included"
                    ),
                    source=SLO_SOURCE_LEDGER,
                    blockers=("lane_attribution_absent", "export_leg_has_no_stage"),
                ),
            ),
            note=(
                "the only tier with a second addressable surface: /ask answers it and "
                "GET /api/v1/queue/status/{request_id} reads the result back. That route only "
                "exists once REPORT_LANE_VIA_QUEUE is on (app/api/v1/chat.py:742-757), and its "
                "export leg is not a ledger stage at all"
            ),
        ),
    )


def _slo_stat(values: list[float], floor: int) -> dict[str, Any]:
    """One gated number. Percentiles come from ``PerformanceStats`` and nowhere else.

    Below ``floor`` samples the slot reports its own shortfall and no number at all. That is
    the whole job of this function: the skeleton answers ``0`` for an empty distribution, and
    a zero passed through would read as "p95 is 0 ms" -- a passing SLO manufactured out of
    nothing, which is exactly what R36 judgement 2 forbids.
    """
    from app.common.performance import PerformanceStats

    stats = PerformanceStats()
    for value in values:
        stats.observe(float(value))
    report = stats.report()
    sufficient = report["count"] >= floor
    return {
        "n": report["count"],
        "required_samples": floor,
        "shortfall": max(0, floor - report["count"]),
        "status": SLO_MEASURED if sufficient else SLO_INSUFFICIENT,
        "p50_ms": report["p50_ms"] if sufficient else None,
        "p95_ms": report["p95_ms"] if sufficient else None,
        "percentile_source": SLO_PERCENTILE_SOURCE,
        "target": None,
        "target_status": SLO_TARGET_PENDING,
        "reason": (
            ""
            if sufficient
            else (
                f"insufficient samples: {report['count']} of {floor} observed, so the "
                "percentile is withheld rather than reported as a passing number"
            )
        ),
    }


def _slo_not_measurable(metric: SloMetric, floor: int) -> dict[str, Any]:
    """A slot with no distribution to compute: still no number, and a named reason."""
    return {
        "n": 0,
        "required_samples": floor,
        "shortfall": floor,
        "status": SLO_NOT_MEASURABLE,
        "p50_ms": None,
        "p95_ms": None,
        "percentile_source": SLO_PERCENTILE_SOURCE,
        "target": None,
        "target_status": SLO_TARGET_PENDING,
        "reason": (
            f"{metric.label_zh} has no measurement piece to sample from yet: "
            + "; ".join(metric.blockers)
        ),
        "blockers": [
            {"code": code, "detail": SLO_BLOCKERS[code]} for code in metric.blockers
        ],
    }


def slo_readout(*, min_samples: int = MIN_SLO_SAMPLES) -> dict[str, Any]:
    """Read the ledger against the contract. Answers with shortfalls, not with numbers.

    Only two distributions are computed here: a tier's request windows and a tier's per-stage
    samples. Both are gated by ``min_samples``, which is deliberately not a query parameter --
    an SLO floor a caller can lower is not a floor.
    """
    from app.common.stage_timing import default_stage_ledger

    floor = max(1, int(min_samples))
    ledger = default_stage_ledger()
    samples = ledger.samples()
    windows = ledger.request_windows()

    tiers: list[dict[str, Any]] = []
    for tier in slo_tiers():
        lane_samples = [sample for sample in samples if sample.lane == tier.lane]
        lane_traces = {sample.trace_id for sample in lane_samples if sample.trace_id}
        end_to_end = [windows[trace] for trace in sorted(lane_traces) if trace in windows]
        numbers: dict[str, Any] = {}
        for metric in tier.metrics:
            # The request-window distribution is the only one the in-process ledger can answer
            # with, so the branch is spelled against that slot rather than against the source
            # alone: a second ledger-sourced metric has to be wired deliberately, not inherit.
            if metric.source == SLO_SOURCE_LEDGER and metric.name == "end_to_end_p95_ms":
                number = _slo_stat(end_to_end, floor)
                number["blockers"] = [
                    {"code": code, "detail": SLO_BLOCKERS[code]} for code in metric.blockers
                ]
            else:
                number = _slo_not_measurable(metric, floor)
            number["label"] = metric.label_zh
            number["population"] = metric.population
            number["measured_from"] = metric.source
            numbers[metric.name] = number
        tiers.append(
            {
                "lane": tier.lane,
                "label": tier.label_zh,
                "note": tier.note,
                "screen": {"route": tier.screen, "path": tier.screen_path, "source": SLO_SCREEN_SOURCE},
                "endpoints": list(tier.endpoints),
                "stages": list(tier.stages),
                "observed_requests": len(lane_traces),
                "numbers": numbers,
                "stage_numbers": {
                    stage: _slo_stat(
                        [
                            sample.duration_ms
                            for sample in lane_samples
                            if sample.stage == stage
                        ],
                        floor,
                    )
                    for stage in tier.stages
                },
            }
        )

    return {
        "schema": "r105.slo/1",
        "sample_floor": floor,
        "target_status": SLO_TARGET_PENDING,
        "percentile_source": SLO_PERCENTILE_SOURCE,
        "units": slo_units(),
        "tiers": tiers,
        "unattributed_pool": {
            "what": (
                "every request window this process recorded, whatever lane it belonged to. "
                "Not a tier and not publishable as one: it is the only real distribution the "
                "ledger can answer with while lane attribution is missing"
            ),
            "blockers": [
                {
                    "code": "lane_attribution_absent",
                    "detail": SLO_BLOCKERS["lane_attribution_absent"],
                }
            ],
            "end_to_end": _slo_stat([windows[key] for key in sorted(windows)], floor),
        },
        "sample_population_note": (
            "requests are counted whether they completed, failed or were cancelled: dropping "
            "the slow failures is how a P95 becomes optimistic. Calls discarded before the "
            "stream body ran never reach the ledger at all (R110), so a window filled before "
            "that merge is biased the same way and must say so"
        ),
    }


@router.get("/slo", responses=_ERROR_RESPONSES)
async def read_slo(request: Request) -> dict[str, Any]:
    """The three-tier SLO contract, plus what the ledger may honestly say about it now.

    Read-only, and empty on purpose: every target is ``awaiting_real_samples`` until the D14甲
    window produces the samples 乙半 will write in. ``min_samples`` is not a query parameter
    for the reason given on :func:`slo_readout`.
    """
    principal = _require_action(request, ACTION_AUDIT, "slo")
    report = slo_readout()
    report["requested_by"] = _principal_summary(principal)
    return report


@router.get("/evaluations", responses=_ERROR_RESPONSES)
async def read_evaluations(request: Request, limit: int | None = None) -> dict[str, Any]:
    """List evaluation suites and stored reports without executing the model stack."""
    principal = _require_admin(request, EVALUATION_READ_ACTION, "evaluations")
    applied_limit, limit_clamped = _clamped(
        limit, default=MAX_EVALUATION_REPORTS, maximum=MAX_EVALUATION_REPORTS
    )
    candidates = _evaluation_report_candidates()
    summaries = [
        _report_summary(path, source=_report_provenance(path))
        for path in candidates[:applied_limit]
    ]
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


# ==================== R135·S1 · 模型档位事实（只读出口） ====================

#: 一台私有化机器到底跑在多大的窗口上，今天要么翻日志、要么猜 env——R135 查证就是靠两枪
#: ``docker run --entrypoint env`` 才发现三枚关键变量根本没有任何部署文件设置过。这一节把
#: 四问答成一次 GET：生效的 context 窗口、生成档真正能塞的房、并发闸门与等待秒数、以及
#: 🔴 每一枚数字是 env 设的还是代码默认。数值一律由 ``app/common/model_budget.py`` 自己的
#: 读数器交出（``context_limit_tokens`` / ``tier_profile`` / ``budget_env_defaults`` /
#: ``model_tier_budget`` / ``LocalModelBudget``），本模块一处都不重算、一处都不抄第二份。
MODEL_BUDGET_FACTS_PATH = "/model-budget/facts"
SOURCE_ENV = "env"
SOURCE_DEFAULT = "default"
SOURCE_ENV_IGNORED = "env_ignored"
MAX_ENV_ECHO_CHARS = 64


def _provenance_number(raw: Any) -> float | None:
    """只判"这串 env 值像不像一个数"，用于出处分类；不参与任何读数本身。"""
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _budget_knob(name: str, effective: Any, code_default: Any) -> dict[str, Any]:
    """一枚数字的完整出处：``effective`` 是谁在生效，``source`` 说它是谁定的。

    🔴 三种来源必须分开交。今天这台机器上 ``MODEL_MAX_CONCURRENCY=1`` 是 compose 写的，
    而 ``MODEL_CONTEXT_TOKENS`` / ``MODEL_CONCURRENCY_WAIT_SECONDS`` /
    ``MODEL_MIN_ANSWER_TOKENS`` 一个部署文件都没写、跑的是代码默认——把两枚默认和一枚 env
    压成"一个数"，就是把这一班的坑原样交给下一班。``env_ignored`` 是第四种最难的坑：操作员
    确实写了，但值不合法或被代码夹回默认，生效的其实是默认值，"我明明设过"在这一档里必须
    当场可辨。

    词汇与现成口径的关系（不是第二套口径）：判定用的谓词就是 ``model_budget._env_set``，
    写过的取值 ``"env"`` 与 ``model_budget.py:769`` 里速率出处的 ``origin = "env"`` 同一个词、
    同一个谓词；只有"没写过"这一档这里叫 ``default`` 而不叫 ``calibrated-default``——窗口默认
    4096 是兜底数、不是标定值，沿用它那个词会把两件不同的事说成一件。两种写法在同一条响应里
    都看得见（``budget_readout`` 原样嵌在下面），不做隐藏。
    """
    from app.common.model_budget import _env_set  # 现成的出处判定，本模块不再造第二套

    written = _env_set(name)
    raw = os.environ.get(name, "")
    number = _provenance_number(raw)
    if not written:
        source = SOURCE_DEFAULT
    elif code_default is None:
        source = SOURCE_ENV if number is not None else SOURCE_ENV_IGNORED
    elif number is None:
        source = SOURCE_ENV_IGNORED
    elif float(effective) == float(code_default):
        source = SOURCE_ENV if number == float(code_default) else SOURCE_ENV_IGNORED
    else:
        source = SOURCE_ENV
    return {
        "env": name,
        "effective": effective,
        "source": source,
        "code_default": code_default,
        "written": bool(written),
        "written_value": str(raw)[:MAX_ENV_ECHO_CHARS] if written else None,
    }


def model_budget_facts() -> dict[str, Any]:
    """四问的读数：窗口 / 生成档房 / 并发闸门与等待 / 每一枚的出处。纯进程内，零 I/O。"""
    from app.agents.contracts import ModelTier
    from app.common.model_budget import (
        LocalModelBudget,
        budget_env_defaults,
        context_limit_tokens,
        min_answer_tokens,
        model_budget_readout,
        model_tier_budget,
        tier_max_tokens_env_name,
    )

    defaults = budget_env_defaults()
    window = int(context_limit_tokens())
    #: 只为读回两枚已配置的闸门数而新建一个实例：它不占槽、不开 socket，也不去碰
    #: ``default_model_budget()`` 那个进程级单例——一条 GET 不该有把全局闸换掉的能力。
    gate = LocalModelBudget()
    analysis = model_tier_budget(ModelTier.ANALYSIS)
    tiers = []
    for tier in ModelTier:
        budget = model_tier_budget(tier)
        cap_name = tier_max_tokens_env_name(tier)
        tiers.append(
            {
                "tier": tier.value,
                "declared_output_cap": _budget_knob(
                    cap_name, int(budget.max_tokens), defaults.get(cap_name)
                ),
                "generation_room_tokens": int(budget.input_budget_tokens),
                "fits_timeout_ceiling": bool(budget.fits_within_timeout(0, stream=False)),
            }
        )
    return {
        "as_of": _now(),
        "context_window": _budget_knob(
            "MODEL_CONTEXT_TOKENS", window, defaults.get("MODEL_CONTEXT_TOKENS")
        ),
        "generation_room": {
            "tier": ModelTier.ANALYSIS.value,
            "input_budget_tokens": int(analysis.input_budget_tokens),
            "basis": "context_limit_tokens - 本档声明的输出上限（contracts.py:ModelBudget.input_budget_tokens）",
            "output_cap": _budget_knob(
                tier_max_tokens_env_name(ModelTier.ANALYSIS),
                int(analysis.max_tokens),
                defaults.get(tier_max_tokens_env_name(ModelTier.ANALYSIS)),
            ),
            "timeout_ceiling_seconds": float(analysis.timeout_ceiling_seconds),
        },
        "concurrency": {
            "max_concurrency": _budget_knob(
                "MODEL_MAX_CONCURRENCY", int(gate.max_concurrency), defaults.get("MODEL_MAX_CONCURRENCY")
            ),
            "wait_seconds": _budget_knob(
                "MODEL_CONCURRENCY_WAIT_SECONDS", float(gate.default_wait_seconds), None
            ),
        },
        "answer_floor": _budget_knob(
            "MODEL_MIN_ANSWER_TOKENS", int(min_answer_tokens()), defaults.get("MODEL_MIN_ANSWER_TOKENS")
        ),
        "tiers": tiers,
        #: 现成件原样嵌进来，不抄第二份：夹取计数、速率出处、每档声明值都在这里面。
        "budget_readout": model_budget_readout(),
        "caveats": [
            "窗口这一枚是产品按之计算的那个数；服务端 n_ctx 是否被显式设定不在本读数声称范围"
            "内（R135·S1 现场查证：全仓 app/** 无任何一处把 num_ctx 发进请求载荷，命中的全是注释与报错文案）。",
            "MODEL_CONCURRENCY_WAIT_SECONDS 的代码默认没有命名常数（60.0 是 "
            "LocalModelBudget._configured_wait 里的裸字面量），所以本出口不发布它的 "
            "code_default，只发布 effective 与 source——拒绝为它抄第二份 60.0。",
            "镜像内没有 .env：未被 compose 提供的变量跑的就是代码默认，"
            "source=default 的读数与 env 写的读数在这台机器上含义完全不同。",
        ],
    }


@router.get(MODEL_BUDGET_FACTS_PATH, responses=_ERROR_RESPONSES)
async def read_model_budget_facts(request: Request) -> dict[str, Any]:
    """模型档位事实：不看日志、不猜 env，一次 GET 回答"我们到底跑在 4096 上吗"。

    只读：不开模型往返、不开 socket、不读向量库、不写审计以外的任何东西；没有任何一次
    探测，因为一次巡检不该把本地模型服务叫醒排队（同 R51 对被观测性的要求）。
    """
    principal = _require_action(request, ACTION_VIEW, "model-budget")
    report = model_budget_facts()
    report["requested_by"] = _principal_summary(principal)
    return report
