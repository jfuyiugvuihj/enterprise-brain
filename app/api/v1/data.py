"""
Day 11: Data API — Excel 画像 / 图表生成 / 报表导出
"""
import asyncio
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse
from app.common.no_store import NO_STORE_HEADERS
from pydantic import BaseModel
from app.tools.excel import (
    UnsupportedDataFile,
    accepted_data_file_extensions,
    ensure_data_file_readable,
    load_excel,
    profile_dataframe,
)
from app.tools.chart import bar_chart, line_chart, pie_chart, radar_chart
from app.tools.visualize import gantt_chart, mindmap
from app.tools.export import generate_pdf_report, export_to_excel
from app.common.logger import logger
from app.api.v1.restricted import DATA_FILE_TEMPLATE, restricted_summary
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
from app.common.policy import authorization_decision, _classification_level
from app.common.rbac import filter_dataframe_rows_with_scope
from app.documents.file_security import (
    DatasetFilenameConflictError,
    UploadSecurityError,
    guard_dataset_name_conflict,
    inspect_dataset_upload,
    sanitize_upload_filename,
)
from app.documents.knowledge_ingest import index_dataset_copy
from app.storage import artifacts as artifact_storage
from app.storage.datasets import DatasetOwnerScopeMissing, DatasetRowConflict, dataset_registry

router = APIRouter()
DATA_DIR = os.getenv("DATA_DIR", "./data")


async def _publish_dataset_update(principal, record, file_path, df, department, visibility):
    """Publish vectors, data lineage and knowledge catalogue in one PG transaction."""
    from app.storage.datasets import DatasetRegistry, PostgresDatasetTableStore
    from app.documents.catalog import record_document_version
    from app.documents.knowledge_ingest import classification_level_for
    from app.common.auth import get_user
    from app.agents.contracts import Principal
    published = {}

    def publish(connection):
        current_user = get_user(principal.user_id)
        if (not current_user or current_user.get('status', 'active') != 'active'
                or current_user.get('must_change_password')
                or int(current_user.get('auth_version', 0)) != principal.auth_version):
            raise PermissionError('account_changed')
        current = Principal.from_user(current_user)
        registry = DatasetRegistry(root=dataset_registry.root,
            metadata_path=dataset_registry.metadata_path,
            store=PostgresDatasetTableStore(connection=connection))
        connection.execute('SELECT dataset_id FROM datasets WHERE dataset_id=%s FOR UPDATE', (record.dataset_id,)).fetchone()
        actual = registry.get(record.dataset_id)
        if (actual is None or not authorization_decision(current, actual.resource_scope,
                action=ACTION_UPLOAD, require_resource_scope=True).allowed
                or (current.role == 'staff' and actual.owner_id != current.user_id)):
            raise PermissionError('permission_denied')
        updated = registry.register(file_path, principal=current, filename=record.filename,
            expected_version_id=record.version_id,
            schema_snapshot={'columns': list(map(str, df.columns)), 'rows': int(len(df))})
        metadata = record_document_version(record.filename, classification_level_for(updated.classification),
            department, str(file_path), owner_id=updated.owner_id, size_bytes=file_path.stat().st_size,
            parse_status='ready', index_status='indexed', visibility=visibility, connection=connection)
        published.update(dataset=updated, metadata=metadata)

    receipt = await index_dataset_copy(display_filename=record.filename, storage_path=file_path,
        department=department, classification=record.classification,
        retriever=_knowledge_base_retriever(), owner_id=record.owner_id, publish=publish, visibility=visibility)
    if receipt.get('status') != 'indexed' or 'dataset' not in published:
        record_audit(principal, ACTION_UPLOAD, 'failed', record.dataset_id, 'dataset_version_not_published',
            before_summary={'version_id': record.version_id})
        current = dataset_registry.get(record.dataset_id)
        if current is None or current.version_id != record.version_id:
            raise HTTPException(status_code=409, detail='dataset_version_changed')
        raise HTTPException(status_code=503, detail='dataset_update_not_published')
    from app.documents.catalog import _record_local_version
    _record_local_version(published['metadata'])
    record_audit(principal, ACTION_UPLOAD, 'succeeded', record.dataset_id, 'dataset_version_published',
        before_summary={'version_id': record.version_id},
        after_summary={'version_id': published['dataset'].version_id})
    return published['dataset'], receipt
os.makedirs(DATA_DIR, exist_ok=True)
#: 收口名单不是另一份手抄：它就是 app/tools/excel.py 那张「扩展名 -> 读引擎」的声明表
#: （`DATA_READ_ENGINES`）现算出来的键。上一版这里写着 {".xlsx", ".xls", ".csv"}，而 .xls 的
#: 引擎（xlrd）从来不在依赖里 —— 闸门放了行，脚下那条腿是断的，客户传 .xls 换来一条 500。
#: 今天加一枚没有引擎的后缀，tests/test_r336_read_engine_backs_the_whitelist.py 当场咬人。
DATA_FILE_EXTENSIONS = accepted_data_file_extensions()
# A dataset is owned by the account that uploaded it, and the registry derives that
# ownership from a department scope. An account without one - the first administrator
# of a fresh install, unless AUTH_DEPARTMENT named its department - can sign in and
# manage users but cannot own data, which is a refusal, not a server fault.
# R714: that refusal is recognized here by its type, never by its sentence. Until now this
# route compared ``str(exc)`` against a copy of the registry's own words, so rewording the
# prose anywhere in storage silently changed what a department-free caller hears, and the
# copy here was a second statement of a rule the registry states once. The type is the
# contract; the sentence is prose.
OWNER_SCOPE_REQUIRED = "department_scope_required"

# R180: file-level authorization (app/common/policy.py) and row-level ownership
# (app/common/rbac.py) are two independent judgments; the preview route only ever
# ran the first one (criterion 1). The two public codes below are NOT a new error
# shape: they are the already-ratified members of app/agents/contracts.py
# ErrorEnvelope.code, also consumed by frontend/src/lib/errcodes.js and emitted on the
# tool leg by app/agents/tools.py. Which rbac reason earns which code is decided in
# exactly ONE place -- the translation layer in tools.py -- so this route asks that
# layer instead of restating its table (test_r64_row_scope_error_codes forbids a second
# copy); the two strings are pinned against the canonical ones by test_r180.
ROW_SCOPE_DENIED = "row_scope_denied"
NO_VISIBLE_ROWS = "no_visible_rows"


def _format_data_file_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _dataset_row_owner_id(record) -> str | None:
    """The owning account of one catalogue row, spelled the way the document catalogue spells it.

    The value is the ``DatasetRecord.owner_id`` this route already holds, so reading it opens no
    second lookup and no second permission chain, and it never travels for a row the caller was
    refused at. The unowned rule is the one in ``app/documents/catalog.py::public_document_row``
    (``None if _is_unowned(value) else str(value)``, unowned meaning ``None`` or whitespace-only),
    restated here instead of imported so an API router does not grow a new import edge into the
    document layer for one field: an empty owner is ``None``, never ``""`` and never a word like
    未分配. A row the registry never heard of (``record is None``) has no owner to state and answers
    ``None`` as well -- the key is present on every row, because "nobody is on record" and "this
    surface does not speak about owners" are different answers.

    R337 gives one more shape that same answer: a record object carrying no owner column at all (a
    hand-built row, never one ``app/storage/datasets.py`` produces -- it fills ``owner_id`` for every
    row it reads) is nobody-on-record too, and answers ``None``. It must not raise: inside the preview
    route an ``AttributeError`` would surface as a 500 `dataset_preview_failed`, which reports a
    missing ownership field as a server fault.
    """
    try:
        value = None if record is None else record.owner_id
    except AttributeError:
        return None
    if value is None or str(value).strip() == "":
        return None
    return str(value)


def _safe_data_filename(filename: str) -> str:
    """Filename legality for a dataset, answered by the guard the knowledge base uses.

    R700 judgement 2. This was a private two-line rule that quietly *stripped* directories
    out of a name (`Path("a/b.csv").name` -> `b.csv`) and waved a disguise like
    `policy.pdf.xlsx` through. It now asks `app/documents/file_security.py`, the same guard
    POST /api/v1/upload refuses with: a path separator, a leading dot and a middle
    extension that is itself a document or executable suffix are all refusals. The public
    code stays the documented `invalid_filename`, so no response shape moves and
    `frontend/src/lib/errcodes.js` gains no key.
    """
    try:
        return sanitize_upload_filename(filename)
    except UploadSecurityError as exc:
        raise HTTPException(status_code=400, detail="invalid_filename") from exc


def _knowledge_base_retriever():
    """The handle that answers knowledge-base reads today, borrowed from the route that owns it.

    R700 writes through it instead of building a `DocumentRetriever` of its own because the
    hot subset of the index lives per handle: a private handle would park the new rows in
    the durable store while the handle that answers questions keeps answering without them
    until the next process start. The import is lazy -- `app/api/v1/chat.py` constructs its
    handle at import time, and this route must stay loadable without pulling that along.
    """
    from app.api.v1 import chat

    return chat.retriever


def _refuse_unreadable_data_file(filename: str) -> None:
    """收口名单之外的数据文件：400 具名拒绝，不是 500「系统坏了」。

    判据只有 `app/tools/excel.py` 那一处（`ensure_data_file_readable`），本函数只负责把它翻成
    HTTP 形状：`code` 复用封闭枚举里已有的 `unsupported_file`（零新增错误码），`message` 是给
    员工的那句下一步做什么。上传与预览两条腿都问这一处，不各写一份后缀判断。
    """
    try:
        ensure_data_file_readable(filename)
    except UnsupportedDataFile as exc:
        raise HTTPException(
            status_code=400, detail={"code": exc.code, "message": str(exc)}
        ) from exc


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


def _row_scope_status(scope_info: dict) -> dict:
    """Turn one row-level filtering result into a status layer for the route body.

    This is the row-level judgment, kept in its own field and deliberately separate
    from the file-level grant `_authorized_dataset` already produced (criterion 1):
    the two are not to be folded into each other's return. It carries counts and a
    stable code only -- no data rows, no column names, no other account's department
    (criterion 4). When a frame had rows but the caller may see none of them, the code
    and the sentence come from the tool leg's translation layer, which shares one
    judgement source for both: it says `row_scope_denied` only when rbac can show the
    department dimension really hid rows, and the neutral `no_visible_rows` when it
    cannot -- so a frame cleared by some other, unratified dimension is never dressed
    up as a permission call, and a real refusal never degrades into an empty list or a
    bare "empty table" (criteria 2 and 3). A genuinely empty table (rows_in == 0) is
    left to the R170 `empty` profile marker with a blank code, and an administrator or
    any caller who does get rows keeps a blank code.
    """
    # Lazy: main.py does not load app.agents.tools at startup, and pulling langchain in
    # through a router import is what chat.py deliberately avoids at module top.
    from app.agents.tools import _row_scope_code, _row_scope_reason

    rows_in = int(scope_info.get("rows_in") or 0)
    rows_visible = int(scope_info.get("rows_visible") or 0)
    # Only a frame that came back with nothing left is this layer's to explain; a
    # partially visible frame is a normal answer and an empty table is R170's.
    cleared = rows_in > 0 and rows_visible == 0
    code = _row_scope_code(scope_info) if cleared else ""
    message = _row_scope_reason(scope_info) if cleared else ""
    status = {
        "code": code,
        "reason_code": str(scope_info.get("reason_code") or ""),
        "rows_in": rows_in,
        "rows_visible": rows_visible,
    }
    if message:
        status["message"] = message
    return status


# ==================== Excel 上传 + 画像 ====================

@router.get("/data-files")
async def list_data_files(request: Request = None):
    files = []
    # A registered file the caller is refused at the file level is neither appended to
    # `files` nor dropped in silence: it is counted and its reason kept, so the catalogue
    # can say "these exist but you cannot see them" without naming them (naming a resource
    # an account has no scope for is its own leak, and every other dataset route already
    # hides behind 403/404). R180 criteria 2/3/4. Nothing about the tally is shaped here
    # any more: the leg hands its own (dataset id, reason code) pairs to the one shared
    # builder (app/api/v1/restricted.py) and that one sentence template - the canon is
    # `restricted -> the one shared projection` in docs/api/contract-v1.md, and
    # tests/test_r200_restricted_single_source.py keeps every exit honest to it.
    restricted_withheld: list[tuple[str, str]] = []
    principal = principal_from_request(request) if request is not None else None
    for record in dataset_registry.active_records():
        path = Path(record.storage_path)
        if path.suffix.lower() not in DATA_FILE_EXTENSIONS:
            continue
        if request is not None:
            decision = authorization_decision(
                principal,
                record.resource_scope,
                action=ACTION_VIEW,
                require_resource_scope=True,
            )
            if not decision.allowed:
                # Registered, present, refused at the file level. The old code just
                # continued: "there is a file you cannot open" answered exactly like
                # "there is no file", with no audit trail. Now it both speaks and lands
                # on the audit path (subject / dataset id / verdict, zero body).
                restricted_withheld.append((record.dataset_id, decision.reason_code))
                record_audit(
                    principal,
                    ACTION_VIEW,
                    "denied",
                    record.dataset_id,
                    decision.reason_code,
                )
                continue
        stat = path.stat()
        item = {
            "filename": record.filename,
            "owner_id": _dataset_row_owner_id(record),
            "size": stat.st_size,
            "size_label": _format_data_file_size(stat.st_size),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            "extension": Path(record.filename).suffix.lower(),
            "_modified_timestamp": stat.st_mtime,
        }
        item.update(
            {
                "dataset_id": record.dataset_id,
                "version_id": record.version_id,
                "classification": record.classification,
                "classification_level": _classification_level(record.classification),
                "department_ids": list(record.department_ids),
            }
        )
        files.append(item)
    restricted_count = len(restricted_withheld)
    files.sort(key=lambda item: item["_modified_timestamp"], reverse=True)
    for item in files:
        item.pop("_modified_timestamp")
    result = {"files": files}
    if restricted_count:
        result["restricted"] = restricted_summary(restricted_withheld, DATA_FILE_TEMPLATE)
    return result


@router.post("/upload-excel")
async def upload_excel(
    request: Request,
    file: UploadFile = File(...),
    classification: Annotated[str | None, Form()] = None,
    new_version: Annotated[bool, Form()] = False,
    expected_version_id: Annotated[str | None, Form()] = None,
):
    """上传 Excel/CSV → 解析 → 返回数据画像，并把同一份表格并进知识库（R700）。"""
    filename = _safe_data_filename(file.filename)
    principal = _authorized_principal(request, ACTION_UPLOAD)
    if new_version:
        # A new version is an update of an existing dataset, never a way to create one
        # under an already-used name. The registry keeps the dataset id and appends a
        # version row, so alert finding keys stay stable across a data refresh.
        existing = dataset_registry.get_active_by_filename(filename)
        if existing is None:
            raise HTTPException(status_code=404, detail="resource_not_found")
        record = _authorized_dataset(request, filename, ACTION_UPLOAD)
        if expected_version_id is not None and expected_version_id != record.version_id:
            raise HTTPException(status_code=409, detail='dataset_version_changed')
        expected_version_id = record.version_id
        from app.documents.catalog import latest_document_version
        knowledge = latest_document_version(filename) or {}
        knowledge_department = str(knowledge.get('department') or '')
        knowledge_visibility = str(knowledge.get('visibility') or 'private')
        if not knowledge_department and len(record.department_ids) == 1:
            knowledge_department = str(record.department_ids[0])
        from app.common.departments import canonical_department
        if canonical_department(knowledge_department) not in {canonical_department(v) for v in record.department_ids}:
            raise HTTPException(status_code=409, detail='dataset_scope_requires_management')
        if principal.role == "staff" and str(record.owner_id) != str(principal.user_id):
            raise HTTPException(status_code=403, detail="owner_mismatch")
        if classification is not None and _classification_level(classification) != _classification_level(record.classification):
            raise HTTPException(status_code=400, detail="classification_change_requires_management")
        classification = record.classification
    # 冲突那一格今天起由 `app/documents/file_security.py` 定夺（R700 判据②）：登记表还是本路由
    # 自己查（只有它认得自己的账），但「同名即拒、不是新版本」这条规则写在两路共读的那本字典
    # 旁边，数据集不会悄悄长出知识库的版本语义，反过来也不会。
    else:
        try:
            guard_dataset_name_conflict(filename, dataset_registry.get_active_by_filename(filename))
            from app.documents.catalog import latest_document_version
            guard_dataset_name_conflict(filename, latest_document_version(filename))
        except DatasetFilenameConflictError as exc:
            raise HTTPException(status_code=409, detail="dataset_filename_conflict") from exc
        if classification is None:
            classification = "1"
    if not isinstance(classification, str) or _classification_level(classification) not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="invalid_classification")
    if _classification_level(classification) > principal.clearance:
        raise HTTPException(status_code=400, detail="invalid_classification")
    # 拒绝发生在落盘之前：读不动的格式既不该留在 DATA_DIR 里，也不该走到 load_excel 那一步
    # 才炸出一条 import 失败（那正是旧版 .xls 的下场）。
    _refuse_unreadable_data_file(filename)
    file_path = dataset_registry.new_version_path(filename)
    content = await file.read()
    # 类型与表头两格同样并进那本字典：后缀必须在 `_ALLOWED_TYPES` 里，表头字节必须对得上那一格
    # 声明的签名。于是同一份文件在两条上传路上答同一个码——伪造的 .xlsx 在写第一个字节之前就被
    # 拒（过去它先落盘，再在 openpyxl 上炸成一条 500），与 POST /upload 对同一份文件的答复一致。
    try:
        inspect_dataset_upload(filename, content)
    except UploadSecurityError as exc:
        raise HTTPException(
            status_code=400, detail=getattr(exc, "code", None) or "unsupported_file"
        ) from exc

    temp_path = file_path.with_name(f".{file_path.name}.upload")
    with open(temp_path, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, file_path)

    try:
        df = await asyncio.to_thread(load_excel, str(file_path))
        if new_version:
            original_frame = await asyncio.to_thread(load_excel, record.storage_path)
            import hashlib
            if hashlib.sha256(content).hexdigest() == record.content_sha256:
                dataset, receipt = record, {'status': 'unchanged'}
            else:
                dataset, receipt = await _publish_dataset_update(principal, record, file_path, df, knowledge_department, knowledge_visibility)
        else:
            dataset = dataset_registry.register(file_path, principal=principal, filename=filename, classification=classification)
    except Exception as exc:
        if file_path.exists():
            file_path.unlink()
        if isinstance(exc, DatasetOwnerScopeMissing):
            raise HTTPException(status_code=403, detail=OWNER_SCOPE_REQUIRED) from exc
        if isinstance(exc, DatasetRowConflict):
            raise HTTPException(status_code=409, detail='dataset_version_changed') from exc
        raise
    if Path(dataset.storage_path).resolve() != file_path.resolve():
        file_path.unlink()
    preview = build_dataframe_preview(df, filename)
    # R337: 上传回执也是资源出口，owner 只能走目录列表那一枚同源 helper。取值用一枚局部名，是为了让
    # 「读的就是手上这枚 dataset」在形状上也是一眼可读的一件事；不开第二次查询，也不长第二条权限链。
    owner_id = _dataset_row_owner_id(dataset)
    preview.update(
        {
            "dataset_id": dataset.dataset_id,
            "version_id": dataset.version_id,
            "classification": dataset.classification,
            "owner_id": owner_id,
            **({'version_unchanged': dataset.version_id == expected_version_id} if new_version else {}),
        }
    )

    # R700 判据①：这条表格的第二条命。入库只走知识库既有那条腿的四个出口（正文=loader 的
    # load_document，值不值得入=documents/index_policy 的判定，写=retriever.add_document，
    # 关键词=tools.rebuild_bm25），本路由不另起第二套入库腿，也不新增任何 Chroma 写点。
    # 读数只进日志：数据集那一半的字段与状态码一个字不许改（判据②），所以知识库这一腿
    # 无论成功、被策略排除、还是模型没在，都不许把一次已注册成功的上传回报成故障。
    if new_version:
        old_columns, new_columns = set(map(str, original_frame.columns)), set(map(str, df.columns))
        preview['version_change'] = {'previous_version_id': record.version_id, 'version_id': dataset.version_id,
            'previous_rows': len(original_frame), 'rows': len(df),
            'added_columns': sorted(new_columns - old_columns), 'removed_columns': sorted(old_columns - new_columns)}
        preview['knowledge_index'] = receipt
        return preview
    await index_dataset_copy(
        display_filename=filename,
        storage_path=dataset.storage_path,
        department=str(knowledge_department if new_version else getattr(principal, "department", "") or ""),
        classification=dataset.classification,
        retriever=_knowledge_base_retriever(),
        owner_id=str(dataset.owner_id),
    )

    return preview



@router.get("/data-files/{filename}/preview")
async def preview_data_file(filename: str, request: Request, response: Response):
    record = _authorized_dataset(request, filename, ACTION_VIEW)
    path = Path(record.storage_path)
    response.headers.update(NO_STORE_HEADERS)
    # 登记表里可能留着一份切换前落盘的 .xls：那一格同样只能给一句具名拒绝，
    # 不许顺着 `except Exception` 滑成 500 dataset_preview_failed（那是把拒绝伪装成故障）。
    _refuse_unreadable_data_file(record.filename)
    try:
        df = await asyncio.to_thread(load_excel, str(path))
        # R180: the preview is a structured excerpt channel, so it must apply the same
        # row-level scope app/agents/tools.py uses on the tool leg, not only the file-level
        # grant above. `_authorized_dataset` (file level) already ran and, for a
        # department mismatch, already answered 403 with the policy reason; reaching here
        # means the caller may open the file, which is NOT the same as seeing every row.
        principal = principal_from_request(request)
        # `_authorized_dataset` already answered 401 for a missing principal, so None can
        # only come from a direct call with the file-level gate stubbed out. No principal
        # means no department to scope by: fail closed (rbac's
        # `authorization_unavailable`), never a channel that sees every row (criterion 1).
        scoped_df, scope_info = filter_dataframe_rows_with_scope(
            df,
            role=getattr(principal, "role", "") or "",
            department=getattr(principal, "department", "") or "",
        )
        row_scope = _row_scope_status(scope_info)
        if row_scope["code"] == ROW_SCOPE_DENIED:
            # Authorized for the file, refused every row: record the refusal on the existing
            # audit path with subject / dataset id / verdict only -- no data rows (criterion 4).
            record_audit(
                principal, ACTION_VIEW, "denied", record.dataset_id, ROW_SCOPE_DENIED
            )
        preview = build_dataframe_preview(scoped_df, record.filename)
        preview["row_scope"] = row_scope
        # R337: the preview names its owner with the same single reader the catalogue row above uses,
        # over the record already in hand -- no second lookup, no second permission chain.
        # `classification` is deliberately NOT added here: whether registration fields belong on a
        # preview surface is an open ruling, not an oversight (docs/api/contract-v1.md, R337).
        owner_id = _dataset_row_owner_id(record)
        preview.update(
            {
                "dataset_id": record.dataset_id,
                "version_id": record.version_id,
                "owner_id": owner_id,
            }
        )
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
    await asyncio.to_thread(
        authorize_raw_table_download, request, path, record.dataset_id
    )
    media_type, _ = mimetypes.guess_type(record.filename)
    return FileResponse(
        path,
        filename=record.filename,
        media_type=media_type or "application/octet-stream",
        content_disposition_type="inline" if inline else "attachment",
        headers=dict(NO_STORE_HEADERS),
    )


def authorize_raw_table_download(request: Request, path: Path, resource_id: str) -> None:
    """Raw bytes cannot apply row filtering; refuse if any sheet contains hidden rows.

    The data and document routes share this check. Checking only the preview sheet
    would expose other (including hidden) sheets when the complete workbook is sent.
    """
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    if principal.role == "admin":
        return
    _refuse_unreadable_data_file(str(path))
    try:
        if path.suffix.lower() == ".xlsx":
            with pd.ExcelFile(path, engine="openpyxl") as workbook:
                frames = [workbook.parse(sheet) for sheet in workbook.sheet_names]
        else:
            frames = [load_excel(str(path))]
        for frame in frames:
            visible, info = filter_dataframe_rows_with_scope(
                frame, role=principal.role, department=principal.department or ""
            )
            if len(visible) != len(frame) or info.get("reason_code") == "authorization_unavailable":
                record_audit(
                    principal, ACTION_DOWNLOAD, "denied", resource_id, ROW_SCOPE_DENIED
                )
                raise HTTPException(status_code=403, detail=ROW_SCOPE_DENIED)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[Data] raw download scope check failed")
        raise HTTPException(status_code=500, detail="dataset_preview_failed") from exc


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
    from app.documents.catalog import latest_document_version
    linked = latest_document_version(filename)
    if linked and Path(linked.get("storage_path") or "").resolve() == Path(record.storage_path).resolve():
        # Retire the shared knowledge entry before removing the dataset bytes.
        # The document route keeps an active dataset's original file in place.
        from app.api.v1.chat import delete_document
        await delete_document(filename, request)
    principal = principal_from_request(request)
    path = Path(record.storage_path)
    size_before = path.stat().st_size if path.is_file() else None
    owner_id = _dataset_row_owner_id(record)
    before = {
        "filename": record.filename,
        "owner_id": owner_id,
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
    """Register one generated file and answer with its delivery URLs.

    The request identity is the generating request's own (R509): this route has no
    conversation behind it, so it records a request and leaves the session unrecorded rather
    than inventing one. The registry, not this function, decides how those two names are
    spelled and stored.
    """
    artifact = artifact_storage.register_artifact(
        path,
        artifact_type=artifact_type,
        principal=principal,
        request_id=principal.request_id,
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
