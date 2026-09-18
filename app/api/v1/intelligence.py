"""Business intelligence routes.

Every route resolves the canonical Principal from the authenticated request, applies
the same default-deny policy used by the resource routes, and writes an audit record.
Nothing here infers an identity from a client-supplied field, and the approval
pre-check reports the caller's own department rather than a claimed one.
"""
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agents.contracts import AgentResult
from app.approval.assistant import (
    STANDARD_SOURCES,
    STANDARD_SOURCE_AUTO,
    STANDARD_SOURCE_EXPLICIT,
    build_precheck,
    match_expense_type,
    precheck_payload,
    resolve_standard_from_knowledge_base,
    to_decimal,
)
from app.common.audit import record_audit
from app.common.monitoring import ProductionReadOnlyProtection
from app.common.authorization import principal_from_request, verify_department_self_report
from app.common.permissions import ACTION_ANALYZE, ACTION_UPLOAD, ACTION_VIEW
from app.common.policy import authorization_decision
from app.common.logger import logger
from app.dashboard.service import build_dashboard
from app.insights.rules import detect_insights
from app.knowledge_graph.service import KnowledgeGraph
from app.quality.provenance import build_answer_provenance
from app.semantics.registry import match_metric_definition, metric_catalog

router = APIRouter()
_graph = KnowledgeGraph()


class DashboardRequest(BaseModel):
    rows: list[dict] = []
    insights: list[dict] = []


class InsightsRequest(BaseModel):
    rows: list[dict] = []


class ApprovalRequest(BaseModel):
    """One expense pre-check request.

    ``department`` is optional and is not an input to the conclusion: the server answers
    for the authenticated principal's own department and refuses a claim for another one.
    ``standard_source`` says where the compared number comes from, and ``standard`` is
    only consulted in ``explicit`` mode.
    """
    amount: Decimal
    standard: Decimal | None = None
    department: str = ""
    expense_type: str
    evidence: list[str] = Field(default_factory=list)
    standard_source: str = STANDARD_SOURCE_EXPLICIT


class RelationRequest(BaseModel):
    source_entity: str
    relation: str
    target: str
    source: str


class ProvenanceRequest(BaseModel):
    results: list[dict] = []


class SemanticRequest(BaseModel):
    question: str = ""


def _authorized(request: Request, action: str, resource_name: str):
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    decision = authorization_decision(principal, None, action=action)
    record_audit(principal, action, "allowed" if decision.allowed else "denied", resource_name, decision.reason_code)
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason_code)
    return principal


def _standard_source(value) -> str:
    """Resolve the requested standard source, refusing a spelling that is not the contract.

    An empty value keeps the historical default, so a client written before
    ``standard_source`` existed behaves exactly as it did. Anything else unknown is a
    caller bug and is answered with a stable code: reading a typo as ``explicit`` would
    silently keep comparing against a number the caller invented.
    """
    requested = str(value or "").strip().lower()
    if not requested:
        return STANDARD_SOURCE_EXPLICIT
    if requested not in STANDARD_SOURCES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_standard_source",
                "message": "standard_source must be explicit or auto_from_knowledge_base",
            },
        )
    return requested


@router.post("/dashboard")
async def dashboard(data: DashboardRequest, request: Request):
    principal = _authorized(request, ACTION_ANALYZE, "dashboard")
    result = build_dashboard(data.rows, data.insights)
    result["generated_for"] = str(principal.user_id)
    result["row_count"] = len(data.rows)
    return result


@router.post("/insights/detect")
async def insights_detect(data: InsightsRequest, request: Request):
    _authorized(request, ACTION_ANALYZE, "insights")
    return {"insights": detect_insights(data.rows), "row_count": len(data.rows)}


@router.post("/approval/precheck")
async def approval_precheck(data: ApprovalRequest, request: Request):
    """Pre-check one expense against a standard the server can account for.

    Two inputs are not taken on trust. The department is the caller's own: repeating it
    is allowed, naming another one is refused with ``department_override_denied``, so a
    conclusion cannot be filed against a scope the caller has no standing for. The
    standard either arrives as ``explicit`` -- the caller's own number, the historical
    behaviour -- or is retrieved and read out of the policy text this principal may see,
    in which case the request's number is not a fallback and an index that cannot be
    asked answers 503 rather than continuing with a guess.
    """
    principal = _authorized(request, ACTION_VIEW, "approval_precheck")
    requested_source = _standard_source(data.standard_source)
    department = verify_department_self_report(
        principal, data.department, action=ACTION_VIEW, resource_name="approval_precheck"
    )

    standard = data.standard
    evidence = data.evidence
    standard_evidence: list[str] = []
    if requested_source == STANDARD_SOURCE_AUTO:
        # Retrieved or nothing: both the figure and its provenance are overwritten from
        # the search result below, unconditionally, so a knowledge base that states no
        # limit leaves an unverifiable conclusion rather than the number that happened to
        # be in the request.
        try:
            resolved = resolve_standard_from_knowledge_base(data.expense_type, principal)
        except Exception as exc:
            logger.warning(f"[Intelligence] approval standard retrieval failed: {type(exc).__name__}: {exc}")
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "retrieval_unavailable",
                    "message": "the policy standard could not be retrieved",
                },
            ) from exc
        standard = resolved["standard"]
        evidence = standard_evidence = resolved["evidence"]

    try:
        result = build_precheck(
            to_decimal(data.amount, field="amount"),
            None if standard is None else to_decimal(standard, field="standard"),
            department,
            data.expense_type,
            evidence,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail={"code": "validation_error", "message": str(exc)}
        ) from exc
    payload = precheck_payload(result, requested_by=str(principal.user_id))
    payload["standard_source"] = requested_source
    # Provenance this server verified, never the caller's own text: the list stays empty
    # in explicit mode because no retrieved passage stood behind that number.
    payload["standard_evidence"] = standard_evidence
    payload["matched_expense_type"] = match_expense_type(data.expense_type)
    return payload


@router.post("/knowledge-graph/relations")
async def add_relation(data: RelationRequest, request: Request):
    principal = _authorized(request, ACTION_UPLOAD, "knowledge_graph_relation")
    try:
        record = _graph.add_relation(
            data.source_entity,
            data.relation,
            data.target,
            data.source,
            principal=principal,
            department_ids=list(principal.department_ids) or None,
            # A candidate relation inherits the author clearance, so it is readable by
            # the author and by higher clearance in the same department only.
            classification=str(principal.clearance),
        )
    except ProductionReadOnlyProtection as exc:
        logger.warning(f"[Intelligence] relation write refused: {exc}")
        record_audit(principal, "resource:upload", "denied", "knowledge_graph_relation", "storage_read_only")
        raise HTTPException(status_code=503, detail="storage_read_only") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="relation_source_required") from exc
    except PermissionError as exc:
        logger.warning(f"[Intelligence] relation refused: {exc}")
        raise HTTPException(status_code=403, detail="permission_denied") from exc
    return record.to_dict()


@router.get("/knowledge-graph/relations")
async def list_relations(source_entity: str | None = None, relation: str | None = None, request: Request = None):
    principal = _authorized(request, ACTION_VIEW, "knowledge_graph_relation")
    return {"relations": _graph.query(source_entity, relation, principal=principal)}


@router.post("/provenance/summary")
async def provenance_summary(data: ProvenanceRequest, request: Request):
    principal = _authorized(request, ACTION_VIEW, "provenance")
    normalized = []
    for item in data.results:
        payload = dict(item)
        payload.setdefault("worker", "unknown")
        payload.setdefault("status", "failed")
        try:
            normalized.append(AgentResult.model_validate(payload))
        except Exception as exc:
            logger.warning(f"[Intelligence] invalid agent result: {type(exc).__name__}: {exc}")
            raise HTTPException(status_code=400, detail="invalid_agent_result") from exc
    summary = build_answer_provenance(normalized)
    # These results arrive from the caller; the server has no verified run to compare
    # them against yet, so the summary must not claim otherwise.
    summary["provenance_source"] = "client_provided"
    summary["server_verified"] = False
    summary["requested_by"] = str(principal.user_id)
    return summary


@router.post("/semantics/match")
async def semantics_match(data: SemanticRequest, request: Request):
    principal = _authorized(request, ACTION_VIEW, "semantics")
    match = match_metric_definition(data.question, owner_id=str(principal.user_id))
    if match is None:
        return {"context": None, "definition_source": None, "provenance": None}
    provenance = match["definition"]["provenance"]
    return {
        "context": match["context"].model_dump(),
        # The context already carries definition_version and the warning; the source is
        # repeated at the top level so a caller can tell a curated metric_definitions row
        # from the code fallback without reading the warning text.
        "definition_source": provenance["source"],
        "provenance": provenance,
    }


@router.get("/semantics/metrics")
async def semantics_metrics(request: Request):
    """Every metric definition a question can be answered from, with its provenance.

    Read-only (request 2 / B-5). Each entry states its ``definition_version`` and where
    the definition came from. ``verified_against_documents`` is decided per row, not for
    the whole table: it is true only once a human has reconciled the wording against a
    named document and section (request R15-b), and the unreconciled warning stays on the
    rest, so the flag can be cleared without pretending it was never set.
    """
    principal = _authorized(request, ACTION_VIEW, "semantics")
    return metric_catalog(owner_id=str(principal.user_id))
