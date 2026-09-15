"""
Day 11: Data API — Excel 画像 / 图表生成 / 报表导出
"""
import asyncio
import mimetypes
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Response
from fastapi.responses import FileResponse
from app.common.no_store import NO_STORE_HEADERS
from pydantic import BaseModel
from app.tools.excel import load_excel, profile_dataframe
from app.tools.chart import bar_chart, line_chart, pie_chart, radar_chart
from app.tools.visualize import gantt_chart, mindmap
from app.tools.export import generate_pdf_report, export_to_excel
from app.common.logger import logger
from app.common.audit import record_audit
from app.common.authorization import principal_from_request
from app.common.permissions import (
    ACTION_ANALYZE,
    ACTION_DELETE,
    ACTION_DOWNLOAD,
    ACTION_EXPORT,
    ACTION_UPLOAD,
    ACTION_VIEW,
)
from app.common.policy import authorization_decision
from app.storage import artifacts as artifact_storage
from app.storage.datasets import dataset_registry

router = APIRouter()
DATA_DIR = os.getenv("DATA_DIR", "./data")
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE_EXTENSIONS = {".xlsx", ".xls", ".csv"}
# A dataset is owned by the account that uploaded it, and the registry derives that
# ownership from a department scope. An account without one - the first administrator
# of a fresh install, unless AUTH_DEPARTMENT named its department - can sign in and
# manage users but cannot own data, which is a refusal, not a server fault.
_OWNER_SCOPE_ERROR = "dataset owner must have a department scope"
OWNER_SCOPE_REQUIRED = "department_scope_required"


def _format_data_file_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _safe_data_filename(filename: str) -> str:
    safe_name = Path(filename or "").name
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="invalid_filename")
    return safe_name


def _resolve_data_path(filename: str) -> Path:
    safe_name = _safe_data_filename(filename)
    path = Path(DATA_DIR) / safe_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="resource_not_found")
    return path


def _authorized_dataset(request: Request, filename: str, action: str):
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    record = dataset_registry.get_active_by_filename(_safe_data_filename(filename))
    if record is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    decision = authorization_decision(
        principal,
        record.resource_scope,
        action=action,
        require_resource_scope=True,
    )
    record_audit(
        principal,
        action,
        "allowed" if decision.allowed else "denied",
        record.dataset_id,
        decision.reason_code,
    )
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason_code)
    return record


def _json_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def build_dataframe_preview(df: pd.DataFrame, filename: str, limit: int = 100) -> dict:
    sample = df.head(limit)
    rows = [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in sample.to_dict(orient="records")
    ]
    return {
        "filename": filename,
        "columns": [str(column) for column in df.columns],
        "rows": rows,
        "profile": profile_dataframe(df),
        "truncated": len(df) > limit,
    }


# ==================== Excel 上传 + 画像 ====================

@router.get("/data-files")
async def list_data_files(request: Request = None):
    directory = Path(DATA_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    principal = principal_from_request(request) if request is not None else None
    for path in directory.iterdir():
        if not path.is_file() or path.suffix.lower() not in DATA_FILE_EXTENSIONS:
            continue
        record = dataset_registry.get_active_by_filename(path.name)
        if request is not None:
            if record is None:
                continue
            decision = authorization_decision(
                principal,
                record.resource_scope,
                action=ACTION_VIEW,
                require_resource_scope=True,
            )
            if not decision.allowed:
                continue
        stat = path.stat()
        item = {
            "filename": path.name,
            "size": stat.st_size,
            "size_label": _format_data_file_size(stat.st_size),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            "extension": path.suffix.lower(),
            "_modified_timestamp": stat.st_mtime,
        }
        if record is not None:
            item.update(
                {
                    "dataset_id": record.dataset_id,
                    "version_id": record.version_id,
                    "classification": record.classification,
                }
            )
        files.append(item)
    files.sort(key=lambda item: item["_modified_timestamp"], reverse=True)
    for item in files:
        item.pop("_modified_timestamp")
    return {"files": files}


@router.post("/upload-excel")
async def upload_excel(request: Request, file: UploadFile = File(...)):
    """上传 Excel/CSV → 解析 → 返回数据画像"""
    filename = _safe_data_filename(file.filename)
    principal = _authorized_principal(request, ACTION_UPLOAD)
    if dataset_registry.get_active_by_filename(filename) is not None:
        raise HTTPException(status_code=409, detail="dataset_filename_conflict")
    file_path = Path(DATA_DIR) / filename
    content = await file.read()
    temp_path = file_path.with_name(f".{file_path.name}.upload")
    with open(temp_path, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, file_path)

    try:
        df = await asyncio.to_thread(load_excel, str(file_path))
        dataset = dataset_registry.register(file_path, principal=principal, filename=filename)
    except Exception as exc:
        if file_path.exists() and dataset_registry.get_active_by_filename(filename) is None:
            file_path.unlink()
        if str(exc) == _OWNER_SCOPE_ERROR:
            raise HTTPException(status_code=403, detail=OWNER_SCOPE_REQUIRED) from exc
        raise
    preview = build_dataframe_preview(df, filename)
    preview.update(
        {
            "dataset_id": dataset.dataset_id,
            "version_id": dataset.version_id,
            "classification": dataset.classification,
        }
    )

    return preview


@router.get("/data-files/{filename}/preview")
async def preview_data_file(filename: str, request: Request, response: Response):
    record = _authorized_dataset(request, filename, ACTION_VIEW)
    path = Path(record.storage_path)
    response.headers.update(NO_STORE_HEADERS)
    try:
        df = await asyncio.to_thread(load_excel, str(path))
        preview = build_dataframe_preview(df, record.filename)
        preview.update({"dataset_id": record.dataset_id, "version_id": record.version_id})
        return preview
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"[Data] preview failed: {filename}")
        raise HTTPException(status_code=500, detail="dataset_preview_failed") from exc


@router.get("/data-files/{filename}/file")
async def get_data_file(filename: str, request: Request, inline: bool = False):
    record = _authorized_dataset(request, filename, ACTION_DOWNLOAD)
    path = Path(record.storage_path)
    media_type, _ = mimetypes.guess_type(record.filename)
    return FileResponse(
        path,
        filename=record.filename,
        media_type=media_type or "application/octet-stream",
        content_disposition_type="inline" if inline else "attachment",
        headers=dict(NO_STORE_HEADERS),
    )


@router.delete("/data-files/{filename}")
async def delete_data_file(filename: str, request: Request):
    """Retire a dataset: authorize, remove the file, tombstone the row, audit (R8).

    The order is the one ``DELETE /api/v1/documents/{filename}`` already uses - bytes
    first, catalogue last - so a cleanup that stops halfway leaves the record active and
    the request retryable rather than forgetting a file still sitting on the disk. A
    dataset owned by somebody else is answered with the policy's own reason at 403, not
    hidden behind a 404: that is what ``_authorized_dataset`` has always done for every
    other dataset route, and its owner reaches the deletion through ``owner_match``
    without any new grant. What is *not* touched on purpose: artifacts generated from a
    dataset, the dataframe cache, and anything in the knowledge-base index. Only the
    uploaded file and its own registry row are this route's subject.
    """
    record = _authorized_dataset(request, filename, ACTION_DELETE)
    principal = principal_from_request(request)
    path = Path(record.storage_path)
    size_before = path.stat().st_size if path.is_file() else None
    before = {
        "filename": record.filename,
        "owner_id": record.owner_id,
        "department_ids": list(record.department_ids),
        "classification": record.classification,
        "size_bytes": size_before,
    }

    def _audit(outcome: str, reason: str, after: dict) -> None:
        # The authorization decision was already audited by _authorized_dataset; this is
        # the completion record, named for its stage like the document route does.
        record_audit(
            principal,
            ACTION_DELETE,
            outcome,
            record.dataset_id,
            reason,
            request_id=principal.request_id or None,
            resource_scope=record.resource_scope,
            before_summary=before,
            after_summary=after,
        )

    try:
        os.remove(path)
    except OSError as exc:
        logger.exception(f"[Data] dataset file could not be removed: {record.filename}")
        _audit("failed", "dataset_cleanup_incomplete", {"deleted": False, "stage": "physical_cleanup"})
        raise HTTPException(status_code=500, detail="internal_error") from exc

    if not dataset_registry.soft_delete(record.dataset_id):
        # The bytes are gone and the row refused to retire, which leaves exactly the
        # residue this route exists to prevent. Reported as a failure rather than
        # smoothed over: a retry now answers 404 because the active lookup needs a file.
        logger.error(f"[Data] dataset row could not be retired: {record.dataset_id}")
        _audit(
            "failed",
            "dataset_cleanup_incomplete",
            {"deleted": False, "stage": "catalog", "file_removed": True},
        )
        raise HTTPException(status_code=500, detail="internal_error")

    _audit(
        "allowed",
        "dataset_deleted",
        {"deleted": True, "stage": "completed", "file_removed": True, "record_status": "deleted"},
    )
    return {
        "status": "ok",
        "filename": record.filename,
        "dataset_id": record.dataset_id,
        "file_removed": True,
        "record_status": "deleted",
    }


# ==================== 图表生成 ====================

class ChartRequest(BaseModel):
    type: str                          # bar / line / pie / radar / gantt / mindmap
    title: str = ""
    labels: list[str] | None = None    # bar/pie/line x轴
    values: list[float] | None = None  # bar/pie 值
    datasets: dict[str, list[float]] | None = None  # line/radar 多系列
    categories: list[str] | None = None   # radar 维度
    tasks: list[dict] | None = None       # gantt 任务
    root: str | None = None               # mindmap 中心
    branches: dict[str, list[str]] | None = None  # mindmap 分支


def _authorized_principal(request: Request, action: str):
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    decision = authorization_decision(principal, None, action=action)
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason_code)
    return principal


def _artifact_response(path: str, artifact_type: str, principal) -> dict:
    artifact = artifact_storage.register_artifact(
        path,
        artifact_type=artifact_type,
        principal=principal,
    )
    return {
        "path": artifact.content_url,
        "download_url": artifact.download_url,
        "artifact": artifact.public_payload(),
        "error": None,
    }


def _require_artifact_scope(principal) -> None:
    """Refuse an artifact an owner could not be recorded for, before doing the work.

    The registry rejects an owner without a department, and until now that arrived as
    HTTP 200 with ``{"error": ...}``, so a caller could not tell a failure from a
    result. ``upload_excel`` already answers 403 with this code.
    """
    if not str(getattr(principal, "department", "") or ""):
        raise HTTPException(status_code=403, detail=OWNER_SCOPE_REQUIRED)


@router.post("/chart")
async def generate_chart(req: ChartRequest, request: Request):
    """根据参数生成图表，返回图片路径"""
    try:
        principal = _authorized_principal(request, ACTION_ANALYZE)
        _require_artifact_scope(principal)
        if req.type == "bar":
            path = bar_chart(req.labels, req.values, title=req.title)
        elif req.type == "line":
            path = line_chart(req.labels, req.datasets, title=req.title)
        elif req.type == "pie":
            path = pie_chart(req.labels, req.values, title=req.title)
        elif req.type == "radar":
            path = radar_chart(req.categories, req.datasets, title=req.title)
        elif req.type == "gantt":
            path = gantt_chart(req.tasks, title=req.title)
        elif req.type == "mindmap":
            path = mindmap(req.root, req.branches, title=req.title)
        else:
            raise HTTPException(status_code=400, detail="unsupported_chart_type")

        # 转成相对 URL
        return _artifact_response(path, "chart", principal)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"图表生成失败: {e}")
        raise HTTPException(status_code=500, detail="chart_generation_failed") from e

# ==================== 报告导出 ====================

class ExportRequest(BaseModel):
    format: str = "pdf"                # pdf / excel
    title: str = ""
    sections: list[dict] | None = None  # pdf: [{type, content}]
    sheets: dict[str, list[dict]] | None = None  # excel: {"Sheet1": [{col:val}]}


@router.post("/export")
async def export_report(req: ExportRequest, request: Request):
    """生成 PDF 或 Excel 报告，返回下载链接"""
    try:
        principal = _authorized_principal(request, ACTION_EXPORT)
        _require_artifact_scope(principal)
        if req.format == "pdf":
            path = generate_pdf_report(
                title=req.title,
                sections=req.sections or []
            )
        elif req.format == "excel":
            path = export_to_excel(
                title=req.title,
                sheets=req.sheets or {}
            )
        else:
            raise HTTPException(status_code=400, detail="unsupported_export_format")

        return _artifact_response(path, "report", principal)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出失败: {e}")
        raise HTTPException(status_code=500, detail="export_failed") from e
