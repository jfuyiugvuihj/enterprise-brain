"""Authorized independent calculation history and its explicitly linked outputs."""
from fastapi import APIRouter, HTTPException, Request, Response

from app.common.audit import record_audit
from app.common.authorization import principal_from_request
from app.common.permissions import ACTION_VIEW
from app.storage.calculations import calculation_storage
from app.storage.persistence import PersistenceWriteError


router = APIRouter(prefix="/calculations", tags=["calculations"])


def _principal(request: Request, response: Response):
    response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache", "Expires": "0"})
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    return principal


@router.get("")
async def list_calculations(request: Request, response: Response, trace_id: str | None = None,
                            request_id: str | None = None, limit: int = 50):
    principal = _principal(request, response)
    try:
        items = calculation_storage.list_for(principal, trace_id=trace_id, request_id=request_id, limit=limit)
    except PersistenceWriteError as exc:
        raise HTTPException(status_code=503, detail="calculation_history_unavailable") from exc
    return {"items": items}


@router.get("/{calculation_run_id}")
async def get_calculation(calculation_run_id: str, request: Request, response: Response):
    principal = _principal(request, response)
    try:
        record = calculation_storage.get(calculation_run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="resource_not_found")
        allowed = calculation_storage.can_view(record, principal)
        record_audit(principal, ACTION_VIEW, "allowed" if allowed else "denied",
                     calculation_run_id, "calculation_scope_match" if allowed else "permission_denied")
        if not allowed:
            raise HTTPException(status_code=403, detail="permission_denied")
        return calculation_storage.with_artifacts(record, principal)
    except PersistenceWriteError as exc:
        raise HTTPException(status_code=503, detail="calculation_history_unavailable") from exc
