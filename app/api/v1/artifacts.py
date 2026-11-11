"""Authenticated Artifact content and download routes."""
import os
import hashlib
import json
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.common.audit import record_audit
from app.common.cache import get_redis
from app.common.authorization import principal_from_request
from app.common.logger import logger
from app.common.permissions import ACTION_DELETE, ACTION_DOWNLOAD, ACTION_VIEW
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


def _authorized_artifact(request: Request, artifact_id: str, action: str, *, record_allowed: bool = True):
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
    # Removing an already authorized artifact does not reveal its retired source.
    # Read, download and ticket issuance still require current source access.
    source_allowed = decision.allowed and (action == ACTION_DELETE or artifact_storage.artifact_sources_allowed(artifact, principal))
    if not source_allowed or record_allowed:
        record_audit(
            principal,
            action,
            "allowed" if source_allowed else "denied",
            artifact.artifact_id,
            decision.reason_code if source_allowed else "source_scope_denied",
        )
    if not source_allowed:
        raise HTTPException(status_code=403, detail=decision.reason_code if not decision.allowed else "source_scope_denied")
    return artifact


_DOWNLOAD_TICKET_TTL_SECONDS = 120
_DOWNLOAD_TICKET_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def _ticket_store():
    # A process-local fallback would make a ticket fail on another backend worker.
    if not os.getenv("REDIS_URL", "").strip():
        raise HTTPException(status_code=503, detail="download_unavailable")
    return get_redis()


def _ticket_key(ticket: str) -> str:
    return f"artifact-download:{hashlib.sha256(ticket.encode()).hexdigest()}"


@router.post("/{artifact_id}/download-link")
async def create_artifact_download_link(artifact_id: str, request: Request):
    artifact = _authorized_artifact(request, artifact_id, ACTION_DOWNLOAD, record_allowed=False)
    principal = principal_from_request(request)
    ticket = secrets.token_urlsafe(32)
    payload = json.dumps({"artifact_id": artifact.artifact_id, "username": principal.username,
                          "auth_version": principal.auth_version})
    try:
        _ticket_store().setex(_ticket_key(ticket), _DOWNLOAD_TICKET_TTL_SECONDS, payload)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Artifact download ticket store unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="download_unavailable") from exc
    return {"url": f"/api/v1/artifacts/attachment/{ticket}", "expires_in": _DOWNLOAD_TICKET_TTL_SECONDS}


@router.get("/attachment")
async def download_artifact_with_ticket(request: Request):
    # Nginx rewrites /attachment/<ticket> to this fixed path, keeping the
    # capability out of backend access logs. It never contains a login JWT.
    ticket = request.headers.get("X-Download-Ticket", "")
    if not _DOWNLOAD_TICKET_PATTERN.fullmatch(ticket):
        raise HTTPException(status_code=404, detail="resource_not_found")
    try:
        raw = _ticket_store().get(_ticket_key(ticket))
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Artifact download ticket read unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="download_unavailable") from exc
    if not raw:
        raise HTTPException(status_code=404, detail="resource_not_found")
    try:
        payload = json.loads(raw)
        artifact_id, username = payload["artifact_id"], payload["username"]
        from app.common.auth import UserStoreUnavailable, get_user
        from app.agents.contracts import Principal
        from psycopg import Error as DatabaseError
        try:
            user = get_user(username)
        except (UserStoreUnavailable, DatabaseError) as exc:
            raise HTTPException(status_code=503, detail="storage_unavailable") from exc
        if not user:
            raise ValueError("user missing")
        principal = Principal.from_user(user)
        if principal.status != "active":
            raise ValueError("account inactive")
        if principal.auth_version != payload.get('auth_version', 0):
            raise ValueError("credential expired")
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=403, detail="permission_denied") from exc
    request.state.principal = principal
    artifact = _authorized_artifact(request, artifact_id, ACTION_DOWNLOAD)
    return FileResponse(
        artifact.storage_path,
        filename=artifact.filename,
        media_type=artifact.media_type,
        content_disposition_type="attachment",
        headers={**_NO_STORE_HEADERS, "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"},
    )


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


@router.delete("/{artifact_id}")
async def delete_artifact(artifact_id: str, request: Request):
    """Retire one artifact: authorize for delete, remove the bytes, tombstone, audit (R8).

    Same order as the dataset and document routes - file first, registry last - so a
    half-finished cleanup leaves a visible, retryable record instead of an orphan on the
    disk. A same-department peer without ``resource:delete`` is refused ``permission_denied``
    because deleting is a controlling action, and the account that generated the artifact
    reaches it through ``owner_match``: no grant here is new or widened. The row survives as
    ``deleted`` rather than vanishing, because the audit trail is reconstructed from it;
    a chat answer quoting this artifact keeps its text but its image stops resolving,
    which is the honest consequence of removing the bytes, not a silent rewrite.
    """
    artifact = _authorized_artifact(request, artifact_id, ACTION_DELETE)
    principal = principal_from_request(request)
    path = Path(artifact.storage_path)
    before = {
        "filename": artifact.filename,
        "owner_id": artifact.owner_id,
        "artifact_type": artifact.artifact_type,
        "classification": artifact.classification,
        "size_bytes": path.stat().st_size if path.is_file() else None,
    }

    def _audit(outcome: str, reason: str, after: dict) -> None:
        record_audit(
            principal,
            ACTION_DELETE,
            outcome,
            artifact.artifact_id,
            reason,
            request_id=principal.request_id or None,
            resource_scope=artifact.resource_scope,
            before_summary=before,
            after_summary=after,
        )

    try:
        os.remove(path)
    except OSError as exc:
        logger.exception(f"[Artifacts] stored file could not be removed: {artifact.filename}")
        _audit("failed", "artifact_cleanup_incomplete", {"deleted": False, "stage": "physical_cleanup"})
        raise HTTPException(status_code=500, detail="internal_error") from exc

    if not artifact_storage.artifact_registry.soft_delete(artifact_id):
        logger.error(f"[Artifacts] record could not be retired: {artifact_id}")
        _audit(
            "failed",
            "artifact_cleanup_incomplete",
            {"deleted": False, "stage": "registry", "file_removed": True},
        )
        raise HTTPException(status_code=500, detail="internal_error")

    _audit(
        "allowed",
        "artifact_deleted",
        {"deleted": True, "stage": "completed", "file_removed": True, "record_status": "deleted"},
    )
    return {
        "status": "ok",
        "artifact_id": artifact.artifact_id,
        "filename": artifact.filename,
        "file_removed": True,
        "record_status": "deleted",
    }


# The collection route is declared after the two single-artifact routes so the path
# grammar of ``/artifacts/{artifact_id}/...`` keeps precedence over the bare list.
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100


def _artifact_row(record) -> dict:
    """One artifact as the list reports it: delivery URLs, its scope, and its generation lineage.

    The two lineage keys come from ``record.lineage_payload()``, i.e. from the artifact row's
    own ``session_id`` / ``request_id`` columns (R509 / migration 0017) - never off the reading
    Principal, which would make the same row claim a different source for every visitor. A
    column that is NULL publishes no key at all, so "this deployment never recorded which turn
    produced it" stays visibly different from "it was produced by the empty string".
    """
    row = record.public_payload()
    row.update(
        {
            "filename": record.filename,
            "owner_id": record.owner_id,
            "department_ids": list(record.department_ids),
            "classification": record.classification,
            "visibility": record.visibility,
            "created_at": record.created_at,
            "source_version_id": record.source_version_id,
        }
    )
    row.update(record.lineage_payload())
    if record.metadata.get('source_alert_id'):
        row['source_alert_id'] = record.metadata['source_alert_id']
    if record.metadata.get('source_artifact_ids'):
        row['source_artifact_ids'] = record.metadata['source_artifact_ids']
    # Generation-time versions remain visible after updates; never imply they are current.
    sources = record.metadata.get("source_documents", [])
    versions = []
    historical = False
    if record.source_version_id:
        from app.storage.datasets import dataset_registry
        source = dataset_registry.dataset_for_version(record.source_version_id)
        if source:
            historical = source.current_version_id != record.source_version_id
        versions.append(record.source_version_id)
    if sources:
        from app.rag.indexing import read_index_metadata, document_index_id
        _versions, current = read_index_metadata()
        for source in sources:
            versions.append(f"{source['source_name']} · 版本 {source.get('version_id') or '未记录'}")
            historical = historical or current.get(document_index_id(source['source_name'])) != source.get('index_version_id')
    if versions:
        row["source_version_label"] = ("历史成果，依据生成时版本：" if historical else "生成时版本：") + "；".join(versions)
    return row


@router.get("")
async def list_artifacts(
    request: Request,
    artifact_type: str | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
    offset: int = 0,
):
    """Page through the artifacts this caller may open, newest first (R2).

    Membership is decided by ``authorization_decision`` with ``ACTION_VIEW`` - the very
    call ``_authorized_artifact`` makes before it serves a body - so an artifact is listed
    exactly when it can be fetched, and no row in this list is a promise the content route
    would break. Nothing about the access rule is invented here, which is the point: a
    listing with its own narrower or wider judgment is how a second permission chain
    starts. Anonymous callers are refused the same way the delivery routes refuse them.
    """
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    applied_limit = max(1, min(int(limit), MAX_LIST_LIMIT))
    applied_offset = max(0, int(offset))
    visible = [
        record
        for record in artifact_storage.artifact_registry.list_active(artifact_type=artifact_type)
        if authorization_decision(
            principal,
            record.resource_scope,
            action=ACTION_VIEW,
            require_resource_scope=True,
        ).allowed and artifact_storage.artifact_sources_allowed(record, principal)
    ]
    page = visible[applied_offset : applied_offset + applied_limit]
    return {
        "artifacts": [_artifact_row(record) for record in page],
        "total": len(visible),
        "returned": len(page),
        "limit": applied_limit,
        "offset": applied_offset,
        "has_more": applied_offset + len(page) < len(visible),
        "artifact_type": artifact_type,
    }
