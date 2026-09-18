import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.approval.assistant import (
    STANDARD_SOURCE_AUTO,
    build_precheck,
    match_expense_type,
    precheck_payload,
    resolve_standard_from_knowledge_base,
    resolve_standard_source,
    to_decimal,
)
from app.common.audit import record_audit
from app.common.authorization import authorize_request, principal_from_request, verify_department_self_report
from app.common.logger import logger
from app.common.monitoring import ProductionReadOnlyProtection
from app.common.open_platform import (
    app_registry_storage_state,
    list_applications,
    register_application,
    verify_open_request,
)
from app.common.permissions import ACTION_MANAGE_USERS, ACTION_VIEW
from app.dashboard.service import build_dashboard
from app.insights.rules import detect_insights
from app.quality.provenance import build_answer_provenance
from app.semantics.registry import match_metric_context

router = APIRouter(prefix="/open")

# Administrative registration surface. It is mounted without the /open prefix, so it
# never goes through the open-platform signature path and is not added to any auth
# whitelist: it requires a signed-in administrator.
apps_router = APIRouter()


class QueryRequest(BaseModel):
    query: str = ""


class AnalyzeRequest(BaseModel):
    rows: list[dict] = []
    insights: list[dict] = []


class ApprovalPreviewRequest(BaseModel):
    """One expense pre-check asked for by a signed application.

    The two fields R40 refuses to take on trust are not inputs here: ``department`` is
    optional and never ends up as the label on the answer, and ``standard`` is only read
    when the caller asks for ``explicit`` and states where the figure came from. Left
    unsaid, ``standard_source`` is ``auto_from_knowledge_base`` -- an application that
    bothers to sign a request is not one this server presumes has a policy number handy.
    """

    amount: float
    standard: float | None = None
    department: str = ""
    expense_type: str
    evidence: list[str] = []
    standard_source: str = STANDARD_SOURCE_AUTO


class ProvenanceRequest(BaseModel):
    results: list[dict] = []


async def _load_json_body(request: Request) -> dict:
    raw = await request.body()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


@router.post("/query")
async def open_query(request: Request):
    body = await request.body()
    body_text = body.decode("utf-8") if body else "{}"
    principal, app_record = verify_open_request(dict(request.headers), body_text, required_action="query")
    data = json.loads(body_text or "{}")
    context = match_metric_context(data.get("query", ""))
    return {
        "app": app_record["app_name"],
        "principal": principal.username,
        "query": data.get("query", ""),
        "context": context.model_dump() if context else None,
    }


@router.post("/analyze")
async def open_analyze(request: Request):
    body = await request.body()
    body_text = body.decode("utf-8") if body else "{}"
    verify_open_request(dict(request.headers), body_text, required_action="analyze")
    data = json.loads(body_text or "{}")
    return build_dashboard(data.get("rows", []), data.get("insights", []))


@router.get("/insights")
async def open_insights(request: Request):
    principal, _record = verify_open_request(dict(request.headers), "", required_action="insights")
    params = request.query_params
    # Resolved before any row is built. The label on the answer is the caller's own department
    # as the registry derives it, and a query parameter naming somebody else's is the same
    # self-report R67 refuses in a body: it is refused with the same code whether or not this
    # request would have used it, so "no metric given" is not a way to test the guard.
    department = verify_department_self_report(
        principal,
        str(params.get("department") or ""),
        action=ACTION_VIEW,
        resource_name="open_insights",
    )
    rows = []
    if params.get("metric"):
        rows.append(
            {
                "department": department,
                "metric": params.get("metric", ""),
                "current": float(params.get("current", 0) or 0),
                "previous": float(params.get("previous", 0) or 0),
                "threshold": float(params.get("threshold", 0) or 0) if params.get("threshold") else None,
            }
        )
    return {"insights": detect_insights(rows)}


@router.post("/approval/preview")
async def open_approval_preview(request: Request):
    """Pre-check one expense for a signed application without letting that application state the terms.

    The signature says which application is asking and which action it was granted; it
    says nothing about whose department a conclusion belongs to or what the policy limit
    is. Both of those were taken from the body, so one ``approval`` token could file a
    conclusion against any department and grade it against a number of its own invention
    -- with provenance it wrote itself. Now the department resolves through the same
    ``verify_department_self_report`` the session transport uses, and the standard is
    retrieved unless the caller asks for ``explicit`` and names its origin.

    R71 is what makes that guard mean anything on this transport: the department it verifies
    a claim against is now granted by an administrator in the application registry, not handed
    to it by the caller's own ``X-Open-Department`` header, which no signature covers.
    """
    body = await request.body()
    body_text = body.decode("utf-8") if body else "{}"
    principal, _record = verify_open_request(dict(request.headers), body_text, required_action="approval")
    data = json.loads(body_text or "{}")
    department = verify_department_self_report(
        principal,
        str(data.get("department") or ""),
        action=ACTION_VIEW,
        resource_name="open_approval_preview",
    )
    # R75: the judgment is made once, in app/approval/assistant.py. What this transport decides
    # for itself is only what silence means, and it means ``auto_from_knowledge_base``: an
    # application has no pre-field history of sending a number to be used as the standard.
    requested_source = resolve_standard_source(data.get("standard_source"), silent_default=STANDARD_SOURCE_AUTO)
    expense_type = str(data.get("expense_type") or "")

    standard = data.get("standard")
    evidence = data.get("evidence") or []
    standard_evidence: list[str] = []
    if requested_source == STANDARD_SOURCE_AUTO:
        # Retrieved or nothing: both the figure and its provenance are overwritten from
        # the search result, so a number still sitting in the body is not a fallback and
        # an index that cannot be asked answers 503 rather than continuing with a guess.
        try:
            resolved = resolve_standard_from_knowledge_base(expense_type, principal)
        except Exception as exc:
            logger.warning(f"[OpenPlatform] approval standard retrieval failed: {type(exc).__name__}: {exc}")
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "retrieval_unavailable",
                    "message": "the policy standard could not be retrieved",
                },
            ) from exc
        standard = resolved["standard"]
        evidence = standard_evidence = resolved["evidence"]
    elif not [item for item in evidence if str(item).strip()]:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "validation_error",
                "message": "standard_source=explicit requires evidence naming where the standard comes from",
            },
        )

    try:
        result = build_precheck(
            to_decimal(data.get("amount"), field="amount"),
            None if standard is None else to_decimal(standard, field="standard"),
            department,
            expense_type,
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
    payload["matched_expense_type"] = match_expense_type(expense_type)
    return payload


@router.get("/dashboard/summary")
async def open_dashboard_summary(request: Request):
    principal, _record = verify_open_request(dict(request.headers), "", required_action="dashboard")
    params = request.query_params
    # Same convergence as ``/insights``, refused the same way: the grouping key is the
    # server's own, never a department the application typed into a query string.
    department = verify_department_self_report(
        principal,
        str(params.get("department") or ""),
        action=ACTION_VIEW,
        resource_name="open_dashboard_summary",
    )
    rows = []
    if params.get("metric"):
        rows.append(
            {
                "department": department,
                "metric": params.get("metric", ""),
                "value": float(params.get("value", 0) or 0),
            }
        )
    return build_dashboard(rows, [])


@router.post("/provenance/summary")
async def open_provenance_summary(request: Request):
    body = await request.body()
    body_text = body.decode("utf-8") if body else "{}"
    verify_open_request(dict(request.headers), body_text, required_action="query")
    data = json.loads(body_text or "{}")
    return build_answer_provenance(data.get("results", []))


class ApplicationRegisterRequest(BaseModel):
    app_name: str
    allowed_actions: list[str] = []
    allowed_departments: list[str] = []
    max_clearance: int = 3
    description: str = ""


def _require_admin(request: Request, resource_name: str):
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    authorize_request(request, ACTION_MANAGE_USERS, resource_name=resource_name)
    return principal


@apps_router.post("/apps")
async def register_open_application(data: ApplicationRegisterRequest, request: Request):
    """Register an open-platform application; the secret is returned exactly once."""
    principal = _require_admin(request, "open_platform_application")
    try:
        issued = register_application(
            data.app_name,
            allowed_actions=list(data.allowed_actions),
            allowed_departments=list(data.allowed_departments),
            max_clearance=data.max_clearance,
            description=data.description,
        )
    except ValueError as exc:
        record_audit(principal, "open_platform:app_register", "denied", str(data.app_name or ""), str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProductionReadOnlyProtection as exc:
        record_audit(principal, "open_platform:app_register", "denied", str(data.app_name or ""), str(exc))
        raise HTTPException(status_code=503, detail="storage_read_only") from exc
    record_audit(principal, "open_platform:app_register", "allowed", issued["app_id"])
    return {**issued, "storage_mode": app_registry_storage_state()["storage_mode"]}


@apps_router.get("/apps")
async def list_open_applications(request: Request):
    """List registered applications without their secrets."""
    _require_admin(request, "open_platform_application")
    return {"applications": list_applications(), "storage": app_registry_storage_state()}
