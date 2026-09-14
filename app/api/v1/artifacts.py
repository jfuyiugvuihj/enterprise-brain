"""Authenticated Artifact content and download routes."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.common.audit import record_audit
from app.common.authorization import principal_from_request
from app.common.permissions import ACTION_DOWNLOAD, ACTION_VIEW
from app.common.policy import authorization_decision
from app.storage import artifacts as artifact_storage

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

# Artifact bodies are authorized per Principal, so they must never be reused
# from a browser or proxy cache: a cached 200 answered to an anonymous or
# cross-department request reads as an authorization bypass. Pragma and
# Expires only cover HTTP/1.0 intermediaries and agree with no-store.
_NO_STORE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _authorized_artifact(request: Request, artifact_id: str, action: str):
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    artifact = artifact_storage.artifact_registry.get_active(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="resource_not_found")

    decision = authorization_decision(
        principal,
        artifact.resource_scope,
        action=action,
        require_resource_scope=True,
    )
    record_audit(
        principal,
        action,
        "allowed" if decision.allowed else "denied",
        artifact.artifact_id,
        decision.reason_code,
    )
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason_code)
    return artifact


@router.get("/{artifact_id}/content")
async def get_artifact_content(artifact_id: str, request: Request):
    artifact = _authorized_artifact(request, artifact_id, ACTION_VIEW)
    return FileResponse(
        artifact.storage_path,
        filename=artifact.filename,
        media_type=artifact.media_type,
        content_disposition_type="inline",
        headers=dict(_NO_STORE_HEADERS),
    )


@router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str, request: Request):
    artifact = _authorized_artifact(request, artifact_id, ACTION_DOWNLOAD)
    return FileResponse(
        artifact.storage_path,
        filename=artifact.filename,
        media_type=artifact.media_type,
        content_disposition_type="attachment",
        headers=dict(_NO_STORE_HEADERS),
    )
