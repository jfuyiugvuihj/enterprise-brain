import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.approval.assistant import build_precheck
from app.common.audit import record_audit
from app.common.authorization import authorize_request, principal_from_request
from app.common.monitoring import ProductionReadOnlyProtection
from app.common.open_platform import (
    app_registry_storage_state,
    list_applications,
    register_application,
    verify_open_request,
)
from app.common.permissions import ACTION_MANAGE_USERS
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
    amount: float
    standard: float
    department: str
    expense_type: str
    evidence: list[str] = []


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
    verify_open_request(dict(request.headers), "", required_action="insights")
    params = request.query_params
    rows = []
    if params.get("metric"):
        rows.append(
            {
                "department": params.get("department", ""),
                "metric": params.get("metric", ""),
                "current": float(params.get("current", 0) or 0),
                "previous": float(params.get("previous", 0) or 0),
                "threshold": float(params.get("threshold", 0) or 0) if params.get("threshold") else None,
            }
        )
    return {"insights": detect_insights(rows)}


@router.post("/approval/preview")
async def open_approval_preview(request: Request):
    body = await request.body()
    body_text = body.decode("utf-8") if body else "{}"
    verify_open_request(dict(request.headers), body_text, required_action="approval")
    data = json.loads(body_text or "{}")
    return build_precheck(
        data.get("amount", 0),
        data.get("standard", 0),
        data.get("department", ""),
        data.get("expense_type", ""),
        data.get("evidence", []),
    )


@router.get("/dashboard/summary")
async def open_dashboard_summary(request: Request):
    verify_open_request(dict(request.headers), "", required_action="dashboard")
    params = request.query_params
    rows = []
    if params.get("metric"):
        rows.append(
            {
                "department": params.get("department", ""),
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
