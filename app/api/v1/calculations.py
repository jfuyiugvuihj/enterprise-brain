"""Authorized independent calculation history and its explicitly linked outputs."""
from fastapi import APIRouter, HTTPException, Request, Response

from app.common.audit import record_audit
from app.common.authorization import principal_from_request
from app.common.permissions import ACTION_ANALYZE, ACTION_VIEW
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
        record = _authorized_calculation(calculation_run_id, principal)
        return calculation_storage.with_artifacts(record, principal)
    except PersistenceWriteError as exc:
        raise HTTPException(status_code=503, detail="calculation_history_unavailable") from exc


def _authorized_calculation(calculation_run_id, principal):
    record = calculation_storage.get(calculation_run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    allowed = calculation_storage.can_view(record, principal)
    record_audit(principal, ACTION_VIEW, "allowed" if allowed else "denied",
                 calculation_run_id, "calculation_scope_match" if allowed else "permission_denied")
    if not allowed:
        raise HTTPException(status_code=403, detail="permission_denied")
    return record


@router.get("/{calculation_run_id}/reuse")
async def prepare_reanalysis(calculation_run_id: str, request: Request, response: Response):
    """Read-only draft: recheck both inputs, never create a task or run a calculation."""
    from app.api.v1 import data
    from app.semantics.execution import binding_digest, validate_binding

    principal = _principal(request, response)
    try:
        old = _authorized_calculation(calculation_run_id, principal)
        parameters = old['parameters']
        if old['status'] != 'completed' or not parameters.get('query') or not parameters.get('filename'):
            raise HTTPException(status_code=409, detail='原计算缺少已完成的问题或资料，无法复用。')
        current = data._authorized_dataset(request, parameters['filename'], ACTION_ANALYZE)
        original = data.dataset_registry.dataset_for_version(old['dataset_version_id'])
        if original is None or original.dataset_id != current.dataset_id:
            raise HTTPException(status_code=409, detail='原资料已被替换，无法直接复用。')
        binding = parameters.get('metric_binding')
        if old.get('metric_definition_id') or binding:
            if not binding or binding.get('definition_id') != old.get('metric_definition_id'):
                raise HTTPException(status_code=409, detail='原计算缺少完整指标口径，请重新选择。')
            try:
                validate_binding(binding, principal.user_id, current)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        preview = await data.preview_data_file(current.filename, request, response)
        if preview['version_id'] != current.version_id or preview['dataset_id'] != current.dataset_id:
            raise HTTPException(status_code=409, detail='dataset_version_changed')
        preview['reuse'] = {'calculation_run_id': calculation_run_id, 'metric_binding': binding,
                            'metric_binding_sha256': binding_digest(binding) if binding else None}
        return preview
    except PersistenceWriteError as exc:
        raise HTTPException(status_code=503, detail="calculation_history_unavailable") from exc
