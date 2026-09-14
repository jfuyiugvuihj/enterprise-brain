"""
Chat API — Multi-Agent SSE 流式 / 文档上传 / 会话管理 (PostgreSQL 持久化)
"""
import os
import mimetypes
import re
import json
import time
import uuid
import queue as qmod
import asyncio
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# 显式线程池 — 支持 1000+ 并发（每个 uvicorn 实例）
_executor = ThreadPoolExecutor(max_workers=50, thread_name_prefix="ezn_")
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, UploadFile, File, Form, Request as FastAPIRequest, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.common import auth
from app.common.authorization import principal_from_request
from app.rag.loader import load_document
from app.documents.preview import build_document_preview
from app.rag.retriever import DocumentRetriever
from app.rag.filters import RetrievalScopeError, build_document_retrieval_filter
from app.common.model_handler import ModelHandler, ModelSource
from app.common.logger import logger
from app.common.performance import PerformanceStats, RequestBudget
from app.common.permissions import ACTION_DELETE, ACTION_DOWNLOAD, ACTION_VIEW
from app.common.policy import authorization_decision
from app.documents.catalog import (
    build_storage_name,
    current_documents,
    _database_available as catalog_database_available,
    delete_document_versions,
    list_document_versions,
    peek_next_document_version,
    record_document_version,
)
from app.documents.file_security import (
    UploadSecurityError,
    build_storage_path,
    inspect_upload_header,
)
from app.storage.sessions import session_registry

router = APIRouter()
retriever = DocumentRetriever()
model_handler = ModelHandler()

DOCUMENTS_DIR = os.getenv("DOCUMENTS_DIR", "./documents")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
MAX_DOCUMENT_UPLOAD_BYTES = int(
    os.getenv("DOCUMENT_UPLOAD_MAX_BYTES", str(25 * 1024 * 1024))
)

_tz = timezone(timedelta(hours=8))
_REQUESTS: dict[str, threading.Event] = {}
_REQUESTS_LOCK = threading.Lock()
_ASK_STATS = PerformanceStats()


def register_request(session_id: str) -> threading.Event:
    event = threading.Event()
    with _REQUESTS_LOCK:
        _REQUESTS[session_id] = event
    return event


def cancel_request(session_id: str) -> bool:
    """Arm the cancellation marker and report whether a run was actually in flight.

    The marker is armed either way, so a request that starts between the ownership
    check and this call cannot slip through. The return value is only `True` when this
    process really had a running request for that session; claiming success for a no-op
    would make the API report a business outcome it did not produce.
    """
    with _REQUESTS_LOCK:
        event = _REQUESTS.get(session_id)
        in_flight = event is not None and not event.is_set()
        if event is None:
            event = threading.Event()
            _REQUESTS[session_id] = event
        event.set()
        return in_flight


def is_request_cancelled(session_id: str) -> bool:
    with _REQUESTS_LOCK:
        event = _REQUESTS.get(session_id)
        return bool(event and event.is_set())


def sse_event(event_name: str, payload: dict) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def canonical_sse_event(
    event_name: str,
    *,
    request_id: str,
    trace_id: str,
    task_id: str,
    sequence: int,
    status: str,
    data: dict | None = None,
) -> str:
    return sse_event(
        event_name,
        {
            "request_id": request_id,
            "trace_id": trace_id,
            "task_id": task_id,
            "sequence": sequence,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": status,
            "data": data or {},
        },
    )


def _latest_document_version(filename: str) -> dict | None:
    for item in list_document_versions(filename):
        storage_path = item.get("storage_path")
        if storage_path and os.path.exists(storage_path):
            return dict(item)

    stem, ext = os.path.splitext(filename)
    directory = Path(DOCUMENTS_DIR)
    if directory.is_dir():
        matches = sorted(directory.glob(f"{stem}__v*{ext}"), reverse=True)
        for path in matches:
            if path.is_file():
                return {"filename": filename, "storage_path": str(path)}

    direct = directory / filename
    if direct.exists():
        return {"filename": filename, "storage_path": str(direct)}
    return None


def _document_authorization_decision(principal, filename: str, version: dict, action: str):
    return authorization_decision(
        principal,
        {
            "resource_type": "document",
            "resource_id": version.get("resource_id") or version.get("id") or filename,
            "owner_id": version.get("owner_id"),
            "department": version.get("department"),
            "department_ids": version.get("department_ids"),
            "classification": version.get("classification"),
            "visibility": version.get("visibility", "private"),
            "version_id": version.get("version_id") or str(version.get("version", "")),
            "status": version.get("status", "active"),
        },
        action=action,
        require_resource_scope=True,
    )


def _document_principal_or_error(request: FastAPIRequest):
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    return principal


def _session_principal_or_error(request: FastAPIRequest):
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    return principal


def _authorize_session_request(request: FastAPIRequest, session_id: str):
    principal = _session_principal_or_error(request)
    if not session_registry.is_owned_by(session_id, principal):
        raise HTTPException(status_code=404, detail="resource_not_found")
    return principal


def _visible_document_rows(request: FastAPIRequest, rows: list[dict]) -> list[dict]:
    principal = _document_principal_or_error(request)
    return [
        row
        for row in rows
        if _document_authorization_decision(
            principal,
            str(row.get("filename") or ""),
            row,
            ACTION_VIEW,
        ).allowed
    ]


def _authorize_document_request(
    request: FastAPIRequest,
    filename: str,
    action: str,
) -> tuple[dict, str]:
    version = _latest_document_version(filename)
    if not version:
        raise HTTPException(status_code=404, detail="resource_not_found")

    principal = _document_principal_or_error(request)
    decision = _document_authorization_decision(principal, filename, version, action)
    if not decision.allowed:
        status_code = 401 if decision.reason_code == "authentication_required" else 403
        raise HTTPException(status_code=status_code, detail=decision.reason_code)
    return version, str(version["storage_path"])


def _resolve_document_path(filename: str) -> str | None:
    """Resolve the latest stored file path for a logical document name."""
    version = _latest_document_version(filename)
    if version:
        return str(version["storage_path"])
    return None


def _get_reliable_queue():
    from app.common.reliable_queue import connect_reliable_queue

    return connect_reliable_queue()


def _authorize_queue_task(
    request: FastAPIRequest,
    queue,
    request_id: str,
) -> dict:
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    raw = queue.redis.get(queue._message_key(request_id))
    if raw is None:
        raise HTTPException(status_code=404, detail="resource_not_found")
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        payload = json.loads(raw).get("payload") or {}
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=403, detail="authorization_unavailable") from exc
    owner = payload.get("principal") or {}
    owner_id = str(owner.get("user_id") or "")
    if not owner_id:
        raise HTTPException(status_code=403, detail="authorization_unavailable")
    if owner_id != str(principal.user_id):
        raise HTTPException(status_code=403, detail="permission_denied")
    return payload


# ==================== PostgreSQL 会话存储 ====================

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None
    dict_row = None

_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")
_MEM_SESSIONS: dict[str, dict] = {}
_MEM_SESSION_MESSAGES: dict[str, list[dict]] = {}
_PRODUCTION_ENVIRONMENTS = {"production", "prod"}


def _sess_conn():
    if psycopg is None:
        raise RuntimeError("PostgreSQL driver is unavailable")
    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _session_database_available() -> bool:
    auth_module = sys.modules.get("app.common.auth")
    return bool(auth_module and getattr(auth_module, "_db_ready", False))


def _is_production_environment() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


def _require_migrated_tables(conn, *table_names: str) -> None:
    for table_name in table_names:
        row = conn.execute(f"SELECT to_regclass('public.{table_name}') AS table_name").fetchone()
        if not row or row["table_name"] is None:
            raise RuntimeError(f"{table_name} table is required in production; run migrations first")


def _ensure_session(session_id: str, user_id: str = "") -> dict:
    now = datetime.now(_tz).isoformat()
    if not _session_database_available():
        return _MEM_SESSIONS.setdefault(
            session_id,
            {"id": session_id, "title": "", "created_at": now, "updated_at": now},
        )
    owner_id = str(user_id or "").strip()
    if not owner_id:
        raise RuntimeError("an authenticated user_id is required to persist a session")
    with _sess_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (id, user_id, title, created_at, updated_at) VALUES (%s, %s, '', %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (session_id, owner_id, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM sessions WHERE id = %s", (session_id,)).fetchone()
        return dict(row) if row else {"id": session_id, "title": "", "created_at": now, "updated_at": now}


def _save_message(session_id: str, role: str, content: str, steps: list | None = None):
    now = datetime.now(_tz).isoformat()
    if not _session_database_available():
        session = _ensure_session(session_id)
        _MEM_SESSION_MESSAGES.setdefault(session_id, []).append(
            {"role": role, "content": content, "steps": steps or [], "created_at": now}
        )
        if role == "user" and not session["title"]:
            session["title"] = content[:30]
        session["updated_at"] = now
        return
    with _sess_conn() as conn:
        conn.execute(
            "INSERT INTO session_messages (session_id, role, content, steps, created_at) VALUES (%s, %s, %s, %s, %s)",
            (session_id, role, content, json.dumps(steps or [], ensure_ascii=False), now),
        )
        if role == "user":
            title = content[:30]
            conn.execute(
                "UPDATE sessions SET title = %s, updated_at = %s WHERE id = %s AND title = ''",
                (title, now, session_id),
            )
        conn.execute("UPDATE sessions SET updated_at = %s WHERE id = %s", (now, session_id))
        conn.commit()


def _list_sessions() -> list[dict]:
    if not _session_database_available():
        result = []
        for session in _MEM_SESSIONS.values():
            item = dict(session)
            item["msg_count"] = sum(
                1 for message in _MEM_SESSION_MESSAGES.get(session["id"], [])
                if message["role"] == "user"
            )
            result.append(item)
        return sorted(result, key=lambda item: item["updated_at"], reverse=True)
    with _sess_conn() as conn:
        rows = conn.execute(
            """SELECT s.*,
               (SELECT COUNT(*) FROM session_messages WHERE session_id = s.id AND role = 'user') as msg_count
               FROM sessions s ORDER BY s.updated_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def _get_session_messages(session_id: str) -> list[dict]:
    if not _session_database_available():
        return [dict(message) for message in _MEM_SESSION_MESSAGES.get(session_id, [])]
    with _sess_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, steps, created_at FROM session_messages WHERE session_id = %s ORDER BY id",
            (session_id,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["steps"] = json.loads(d["steps"])
        except (json.JSONDecodeError, TypeError):
            d["steps"] = []
        result.append(d)
    return result


def _delete_session(session_id: str):
    if not _session_database_available():
        _MEM_SESSIONS.pop(session_id, None)
        _MEM_SESSION_MESSAGES.pop(session_id, None)
        return
    with _sess_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
        conn.commit()


# ==================== 阶段 2：文档密级表 ====================

def _ensure_documents_table():
    with _sess_conn() as conn:
        if _is_production_environment():
            _require_migrated_tables(conn, "documents")
            return
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                filename TEXT UNIQUE NOT NULL,
                classification INT NOT NULL DEFAULT 1,
                department TEXT
            )
        """)
        conn.commit()


if catalog_database_available():
    try:
        _ensure_documents_table()
    except Exception:
        pass  # 导入不硬依赖库；上传时再懒建表


def _upsert_document(filename: str, classification: int, department: str):
    _ensure_documents_table()
    with _sess_conn() as conn:
        conn.execute(
            "INSERT INTO documents (filename, classification, department) VALUES (%s, %s, %s) "
            "ON CONFLICT (filename) DO UPDATE SET classification = EXCLUDED.classification, department = EXCLUDED.department",
            (filename, int(classification), department or None),
        )
        conn.commit()


# ==================== 追问改写 ====================

def _rewrite_followup(session_id: str, user_msg: str) -> str:
    triggers = ["那", "它", "这个", "那个", "他们", "换", "改成"]
    if not any(user_msg.startswith(t) for t in triggers):
        return user_msg

    msgs = _get_session_messages(session_id)
    prev_user = [m["content"] for m in msgs if m["role"] == "user"]
    if not prev_user:
        return user_msg

    try:
        prompt = f"""把追问改写为完整独立问题。结合上文语境。

上一问: {prev_user[-1]}
当前: {user_msg}

只输出改写后的问题:"""
        result = model_handler.chat(
            messages=[{"role": "user", "content": prompt}],
            source=ModelSource.LOCAL,
            stream=False,
        )
        rewritten = result.strip() if isinstance(result, str) else result.choices[0].message.content.strip()
        if rewritten and len(rewritten) > 3:
            logger.info(f"[REWRITE] '{user_msg}' → '{rewritten[:60]}'")
            return rewritten
    except Exception as e:
        logger.warning(f"[REWRITE] 失败: {e}")

    return user_msg


# ==================== Pydantic ====================

class ChatRequest(BaseModel):
    message: str


class AskRequest(BaseModel):
    message: str
    session_id: str = ""
    data_filename: str = ""
    idempotency_key: str = ""


def _should_use_data_context(message: str, filename: str) -> bool:
    if not filename:
        return False
    text = (message or "").strip().lower()
    if not text:
        return False

    document_terms = (
        "制度",
        "流程",
        "报销",
        "标准",
        "审批",
        "规定",
        "政策",
        "凭证",
        "发票",
        "复核",
        "材料",
        "依据",
        "谁承担",
    )
    data_terms = (
        "数据",
        "csv",
        "excel",
        "xlsx",
        "表格",
        "记录",
        "列",
        "行",
        "最高",
        "最低",
        "平均",
        "差距",
        "合计",
        "总额",
        "排名",
        "统计",
        "分析",
        "对比",
        "比较",
        "趋势",
    )
    has_document_intent = any(term in text for term in document_terms)
    has_data_intent = any(term in text for term in data_terms)
    return has_data_intent and not has_document_intent


def _ensure_sessions_table():
    """Create chat session tables for a fresh PostgreSQL database."""
    if not _session_database_available():
        return
    with _sess_conn() as conn:
        if _is_production_environment():
            _require_migrated_tables(conn, "sessions", "session_messages")
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS user_id TEXT")
        conn.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS updated_at TEXT")
        conn.execute("UPDATE sessions SET updated_at = created_at WHERE updated_at IS NULL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_messages (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                steps TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("ALTER TABLE session_messages ADD COLUMN IF NOT EXISTS steps TEXT NOT NULL DEFAULT '[]'")
        conn.commit()


# ==================== 旧版 Chat（保留兼容） ====================

def _source_in_scope(source: dict, allowed_levels: set[int], allowed_departments: set[str]) -> bool:
    """本地复核下推过滤的结果；缺元数据的 chunk 一律视为不可见。"""
    try:
        level = int(source.get("classification"))
    except (TypeError, ValueError):
        return False
    return (
        level in allowed_levels
        and str(source.get("department") or "") in allowed_departments
    )


@router.post("/chat")
async def chat(request: ChatRequest, http_request: FastAPIRequest):
    """旧版纯文本问答：检索同样必须落在 Principal 的权限范围内。"""
    principal = _document_principal_or_error(http_request)
    try:
        retrieval_filter = build_document_retrieval_filter(principal)
    except RetrievalScopeError as scope_error:
        status_code = 401 if scope_error.code == "authentication_required" else 403
        logger.warning(f"[CHAT] 拒绝无范围检索: user={principal.username} code={scope_error.code}")
        raise HTTPException(status_code=status_code, detail=scope_error.code)
    allowed_levels = set(retrieval_filter["$and"][0]["classification"]["$in"])
    allowed_departments = set(retrieval_filter["$and"][1]["department"]["$in"])

    async def generate():
        try:
            sources = [
                source
                for source in retriever.search(request.message, k=5, where=retrieval_filter)
                if _source_in_scope(source, allowed_levels, allowed_departments)
            ]
            context = "\n\n".join(
                f"[来源: {s['source']}]\n{s['content']}" for s in sources
            ) if sources else "暂无相关文档"

            prompt = f"""你是一个企业智能助手。参考以下文档内容回答用户问题。

## 参考文档
{context}

## 用户问题
{request.message}

## 要求
- 如果文档包含相关信息，明确引用来源
- 如果文档不包含相关信息，如实告知并给出建议"""

            stream = model_handler.chat(
                messages=[{"role": "user", "content": prompt}],
                source=ModelSource.LOCAL,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:  # noqa: BLE001 - 旧端点同样不得把内部异常发给客户端
            logger.error(f"Chat error: {exc}")
            yield "\n[错误] 本轮检索或模型调用失败，请重试或改用 /api/v1/ask。"

    return StreamingResponse(generate(), media_type="text/plain")


# ==================== Multi-Agent Ask (SSE) ====================

def _complete_pending_steps(steps: list[dict], elapsed: float) -> list[dict]:
    """将流结束时仍在运行的步骤统一收口，避免前端永久显示加载状态。"""
    completed = []
    for step in steps:
        if step.get("status") != "running":
            continue
        step["status"] = "done"
        step["elapsed"] = elapsed
        completed.append(dict(step))
    return completed


def _select_final_answer(
    final_answer: str = "",
    worker_results: dict | None = None,
    candidates: list[str] | None = None,
) -> str:
    """Choose the authoritative answer after the graph has finished."""
    worker_results = worker_results or {}
    worker_answers = [
        str(value).strip()
        for value in worker_results.values()
        if str(value).strip()
    ]
    if worker_answers:
        return "\n\n".join(worker_answers)
    if str(final_answer).strip():
        return str(final_answer).strip()
    for candidate in reversed(candidates or []):
        if str(candidate).strip():
            return str(candidate).strip()
    return ""


@router.post("/ask/{session_id}/cancel")
async def cancel_ask(session_id: str, http_request: FastAPIRequest):
    # 取消是对他人会话的破坏性动作，先证明归属再动手。
    _authorize_session_request(http_request, session_id)
    return {"cancelled": cancel_request(session_id), "session_id": session_id}


@router.get("/ask/metrics")
async def ask_metrics():
    return _ASK_STATS.report()


@router.post("/ask")
async def ask(request: AskRequest, http_request: FastAPIRequest = None):
    thread_id = request.session_id or uuid.uuid4().hex
    request_id = f"req-{uuid.uuid4().hex}"
    trace_id = f"trace-{uuid.uuid4().hex}"
    task_id = f"task-{uuid.uuid4().hex}"
    request_principal = principal_from_request(http_request) if http_request else None
    if request_principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    _ensure_sessions_table()
    try:
        session_registry.bind(thread_id, request_principal)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="permission_denied") from exc
    _ensure_session(thread_id, str(request_principal.user_id))
    _save_message(thread_id, "user", request.message)

    original_msg = request.message
    orchestration_msg = original_msg
    if _should_use_data_context(original_msg, request.data_filename):
        orchestration_msg = (
            f"请仅使用数据分析工具分析数据文件《{request.data_filename}》。"
            f"用户问题：{original_msg}"
        )
    rewritten_msg = _rewrite_followup(thread_id, orchestration_msg)

    # ——— 限流检查 (Layer 5: 超限入队而非拒绝) ———
    from app.common.cache import check_rate_limit
    username = getattr(http_request.state if http_request else None, "username", None) or "anonymous"
    allowed, remaining = check_rate_limit(username, max_per_minute=10)

    # 阶段 2：解析调用者角色/部门，随 config 下发做检索权限过滤
    user_ctx = None
    try:
        from app.common import auth as _auth
        u = _auth.get_user(username)
        if u:
            user_ctx = {"username": username, "role": u.get("role") or "staff",
                        "department": u.get("department") or ""}
        if request_principal is not None:
            user_ctx = user_ctx or {"username": username}
            user_ctx["principal"] = request_principal
        if _should_use_data_context(original_msg, request.data_filename):
            user_ctx = user_ctx or {"username": username}
            user_ctx["data_filename"] = request.data_filename
    except Exception:
        user_ctx = None
    if not allowed:
        idempotency_key = request.idempotency_key.strip()
        if not idempotency_key and http_request is not None:
            idempotency_key = str(http_request.headers.get("Idempotency-Key", "")).strip()
        if not idempotency_key:
            raise HTTPException(status_code=400, detail="idempotency_key_required")

        from app.common.reliable_queue import QueueConnectionError, connect_reliable_queue

        payload = {
            "task_type": "ask",
            "message": rewritten_msg,
            "session_id": thread_id,
            "username": username,
            "principal": request_principal.model_dump(mode="json") if request_principal is not None else None,
        }
        try:
            queue = connect_reliable_queue()
            message = queue.enqueue(payload, idempotency_key)
        except QueueConnectionError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": exc.code, "message": str(exc)},
            ) from exc
        queued = {
            "type": "queued",
            "request_id": message.request_id,
            "status": "queued",
        }
        async def queued_response():
            yield f"event: queued\ndata: {json.dumps(queued, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            yield f"event: done\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
        return StreamingResponse(
            queued_response(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ——— 答案缓存 ———
    from app.common.cache import get_cached_answer
    # 会话问答必须保留当前会话语境，不能命中跨会话的全局答案缓存。
    # 无 session_id 的兼容调用仍可使用问题级缓存。
    use_answer_cache = not bool(request.session_id)
    cached = get_cached_answer(rewritten_msg) if use_answer_cache else None
    if cached:
        _save_message(thread_id, "assistant", cached)
        async def cached_response():
            yield f"event: status\ndata: {json.dumps({'type': 'status', 'content': '📋 缓存命中，直接返回'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            yield f"event: text\ndata: {json.dumps({'type': 'text', 'content': cached}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            yield f"event: done\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
        return StreamingResponse(
            cached_response(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def generate():
        from app.agents.orchestrator import run_with_stream

        cancel_event = register_request(thread_id)
        budget = RequestBudget(float(os.getenv("CHAT_REQUEST_TIMEOUT", "300")))
        heartbeat_interval = float(os.getenv("SSE_HEARTBEAT_INTERVAL", "15"))
        result_queue: qmod.Queue = qmod.Queue()

        def _run():
            try:
                for event in run_with_stream(
                    rewritten_msg,
                    thread_id=thread_id,
                    user=user_ctx,
                    request_id=request_id,
                    trace_id=trace_id,
                    task_id=task_id,
                ):
                    result_queue.put(("event", event))
                result_queue.put(("done", None))
            except Exception as e:
                result_queue.put(("error", str(e)))

        loop = asyncio.get_running_loop()
        loop.run_in_executor(_executor, _run)

        yield f"event: status\ndata: {json.dumps({'type': 'status', 'content': '🔍 正在分析您的问题...'}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)

        start_time = time.time()
        last_emit = time.monotonic()
        steps_log: list[dict] = []
        ai_full_reply: list[str] = []
        saved = False
        last_workers: list[str] = []
        last_completed: set[str] = set()
        emitted_running: set[str] = set()
        emitted_done: set[str] = set()
        initial_msg_count = -1
        initial_worker_results: dict = {}
        latest_worker_results: dict = {}
        latest_final_answer = ""
        answer_candidates: list[str] = []
        sequence = 1

        yield canonical_sse_event(
            "request.started",
            request_id=request_id,
            trace_id=trace_id,
            task_id=task_id,
            sequence=sequence,
            status="running",
            data={"session_id": thread_id},
        )
        sequence += 1

        while True:
            if cancel_event.is_set():
                _ASK_STATS.observe((time.time() - start_time) * 1000)
                yield canonical_sse_event(
                    "request.cancelled",
                    request_id=request_id,
                    trace_id=trace_id,
                    task_id=task_id,
                    sequence=sequence,
                    status="cancelled",
                    data={"session_id": thread_id},
                )
                sequence += 1
                yield sse_event("cancelled", {"type": "cancelled", "session_id": thread_id})
                break
            if budget.expired():
                _ASK_STATS.observe((time.time() - start_time) * 1000, error=True)
                yield canonical_sse_event(
                    "request.failed",
                    request_id=request_id,
                    trace_id=trace_id,
                    task_id=task_id,
                    sequence=sequence,
                    status="failed",
                    data={"error_code": "task_timeout"},
                )
                sequence += 1
                yield sse_event("error", {"type": "error", "content": "请求超过系统处理时限"})
                break
            try:
                kind, data = result_queue.get_nowait()
            except qmod.Empty:
                if time.monotonic() - last_emit >= heartbeat_interval:
                    yield sse_event("heartbeat", {"type": "heartbeat"})
                    last_emit = time.monotonic()
                await asyncio.sleep(0.05)
                continue

            if kind == "done":
                elapsed_total = round(time.time() - start_time, 1)
                _ASK_STATS.observe(elapsed_total * 1000)
                for step in _complete_pending_steps(steps_log, elapsed_total):
                    yield f"event: step\ndata: {json.dumps({'type': 'step', **step}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)
                full_text = _select_final_answer(
                    final_answer=latest_final_answer,
                    worker_results=latest_worker_results,
                    candidates=answer_candidates,
                )
                # 图停在 interrupt_before 节点之前时本轮确实没有产出任何结论。
                # 此时空正文 + request.completed 会让前端把“等待确认”画成“已回答”，
                # 所以先查真实的挂起节点，再据此生成一句可核验的状态说明。
                try:
                    from app.agents.orchestrator import check_interrupt
                    intr = check_interrupt(thread_id)
                except Exception:
                    intr = None
                if not full_text and intr:
                    full_text = (
                        "本轮在「" + "、".join(intr["labels"]) + "」前等待你确认，"
                        "确认后才会执行，目前尚未产出回答内容。"
                    )
                if not full_text:
                    # 图跑完了，既没有正文也没有等待确认的步骤：这是内部失败。
                    # 把它报成 request.completed 就是把“什么都没产出”伪装成“已回答”。
                    failure_text = (
                        "本轮未产出任何结论（error_code=no_answer_produced），"
                        "请重试或补充数据范围。"
                    )
                    _save_message(thread_id, "assistant", failure_text, steps_log)
                    saved = True
                    yield sse_event("error", {"type": "error", "content": failure_text})
                    yield canonical_sse_event(
                        "request.failed",
                        request_id=request_id,
                        trace_id=trace_id,
                        task_id=task_id,
                        sequence=sequence,
                        status="failed",
                        data={
                            "session_id": thread_id,
                            "error_code": "no_answer_produced",
                            "worker_count": len(latest_worker_results),
                        },
                    )
                    sequence += 1
                    yield f"event: done\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)
                    break

                _save_message(thread_id, "assistant", full_text, steps_log)
                saved = True
                if full_text:
                    from app.common.cache import cache_answer
                    # 等待确认的状态说明不是一个问题的答案，不允许进全局答案缓存。
                    if use_answer_cache and not intr:
                        cache_answer(rewritten_msg, full_text)
                    yield f"event: text\ndata: {json.dumps({'type': 'text', 'content': full_text}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)
                logger.info(f"[ASK] session={thread_id[:8]}... {elapsed_total}s | steps={len(steps_log)}")

                if intr:
                    yield f"event: hitl\ndata: {json.dumps({'type': 'hitl', 'pending': intr['pending'], 'labels': intr['labels']}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)

                yield canonical_sse_event(
                    "request.completed",
                    request_id=request_id,
                    trace_id=trace_id,
                    task_id=task_id,
                    sequence=sequence,
                    status="completed",
                    data={
                        "session_id": thread_id,
                        "worker_count": len(latest_worker_results),
                        "elapsed": elapsed_total,
                        "answer_length": len(full_text),
                        "awaiting_hitl": bool(intr),
                        "awaiting_steps": list(intr["pending"]) if intr else [],
                    },
                )
                sequence += 1
                yield f"event: done\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
                break

            if kind == "error":
                _ASK_STATS.observe((time.time() - start_time) * 1000, error=True)
                logger.error(f"[ASK] session={thread_id[:8]}... ERROR: {data}")
                if not saved:
                    _save_message(thread_id, "assistant", f"[错误] {data}")
                yield canonical_sse_event(
                    "request.failed",
                    request_id=request_id,
                    trace_id=trace_id,
                    task_id=task_id,
                    sequence=sequence,
                    status="failed",
                    data={"error_code": "internal_error"},
                )
                sequence += 1
                yield f"event: error\ndata: {json.dumps({'type': 'error', 'content': data}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
                break

            ns = ()
            if isinstance(data, tuple):
                ns = data[0] if len(data) > 1 else ()
                data = data[1] if len(data) > 1 else data[0]
            if not isinstance(data, dict):
                continue
            if ns and ns != ("",):
                continue

            msgs = data.get("messages", [])
            worker_results = data.get("worker_results", {})
            if worker_results:
                latest_worker_results = dict(worker_results)
            if data.get("final_answer"):
                latest_final_answer = str(data["final_answer"])

            dispatched: list[str] = []
            for msg in msgs:
                tools = getattr(msg, "tool_calls", None) or []
                for tc in tools:
                    if tc["name"] == "dispatch":
                        dispatched = tc["args"].get("workers", [])
                        break
                if dispatched:
                    break

            if dispatched:
                user_msg = ""
                for m in reversed(msgs):
                    if type(m).__name__ == "HumanMessage":
                        user_msg = getattr(m, "content", "") or ""
                        break
                chart_kw = ["画", "图", "图表", "柱状图", "折线图", "饼图", "可视化", "图形"]
                export_kw = ["导出", "PDF", "pdf", "报告", "下载"]
                data_kw = ["排名", "最高", "最低", "统计", "分析数据", "对比", "比较", "哪个"]
                if any(kw in user_msg for kw in chart_kw):
                    dispatched = ["chart"]
                elif any(kw in user_msg for kw in export_kw) and not any(kw in user_msg for kw in chart_kw):
                    dispatched = ["export"]
                elif any(kw in user_msg for kw in data_kw) and "chart" not in dispatched:
                    if "data" not in dispatched:
                        dispatched = ["data"]

            if dispatched and dispatched != last_workers:
                for w in dispatched:
                    if w not in emitted_running:
                        emitted_running.add(w)
                        labels = {"doc": "📄 搜索知识库", "data": "📊 分析数据",
                                  "chart": "📈 生成图表", "export": "📋 导出报告"}
                        label = labels.get(w, f"🔧 {w}")
                        steps_log.append({"tool": w, "label": label, "status": "running", "elapsed": None})
                        yield f"event: step\ndata: {json.dumps({'type': 'step', 'tool': w, 'label': label, 'status': 'running'}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0)

            if not initial_worker_results:
                initial_worker_results = dict(worker_results)
            for w in worker_results:
                is_new = w not in initial_worker_results
                is_changed = w in initial_worker_results and worker_results[w] != initial_worker_results[w]
                if w not in emitted_done and (is_new or is_changed):
                    emitted_done.add(w)
                    elapsed = round(time.time() - start_time, 1)
                    for s in steps_log:
                        if s["tool"] == w and s["status"] == "running":
                            s["status"] = "done"
                            s["elapsed"] = elapsed
                            yield f"event: step\ndata: {json.dumps({'type': 'step', 'tool': w, 'label': s['label'], 'status': 'done', 'elapsed': elapsed}, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0)

            last_workers = dispatched

            if initial_msg_count < 0:
                initial_msg_count = len(msgs)
            pending = [w for w in last_workers if w not in worker_results]
            if not pending:
                for idx in range(len(msgs) - 1, initial_msg_count - 1, -1):
                    msg = msgs[idx]
                    msg_type = type(msg).__name__
                    content = getattr(msg, "content", "") or ""
                    has_tools = getattr(msg, "tool_calls", None)
                    if msg_type == "AIMessage" and content and not has_tools:
                        if content.startswith("【") and "Agent 返回】" in content[:50]:
                            continue
                        if content not in answer_candidates:
                            answer_candidates.append(content)
                        break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ApproveRequest(BaseModel):
    session_id: str
    approved: bool = True


@router.post("/approve")
async def approve(request: ApproveRequest, http_request: FastAPIRequest):
    # /approve 会接管该会话的挂起轮次并把会话内容流式回传给调用方，
    # 因此它和读取会话必须是同一套归属判定，不能只校验"已登录"。
    _authorize_session_request(http_request, request.session_id)

    async def generate():
        from app.agents.orchestrator import run_interrupt_stream

        cancel_event = register_request(request.session_id)
        budget = RequestBudget(float(os.getenv("CHAT_REQUEST_TIMEOUT", "300")))
        heartbeat_interval = float(os.getenv("SSE_HEARTBEAT_INTERVAL", "15"))
        result_queue: qmod.Queue = qmod.Queue()

        def _run():
            try:
                for event in run_interrupt_stream(request.session_id, approved=request.approved):
                    result_queue.put(("event", event))
                result_queue.put(("done", None))
            except Exception as e:
                result_queue.put(("error", str(e)))

        loop = asyncio.get_running_loop()
        loop.run_in_executor(_executor, _run)

        start_time = time.time()
        last_emit = time.monotonic()
        ai_reply: list[str] = []
        latest_worker_results: dict = {}
        latest_final_answer = ""
        answer_candidates: list[str] = []
        initial_count = -1

        while True:
            if cancel_event.is_set():
                yield sse_event(
                    "cancelled",
                    {"type": "cancelled", "session_id": request.session_id},
                )
                break
            if budget.expired():
                yield sse_event("error", {"type": "error", "content": "请求超过系统处理时限"})
                break
            try:
                kind, data = result_queue.get_nowait()
            except qmod.Empty:
                if time.monotonic() - last_emit >= heartbeat_interval:
                    yield sse_event("heartbeat", {"type": "heartbeat"})
                    last_emit = time.monotonic()
                await asyncio.sleep(0.05)
                continue

            if kind == "done":
                full_text = _select_final_answer(
                    final_answer=latest_final_answer,
                    worker_results=latest_worker_results,
                    candidates=answer_candidates + ai_reply,
                )
                _save_message(request.session_id, "assistant", full_text)
                if full_text and full_text not in ai_reply:
                    yield f"event: text\ndata: {json.dumps({'type': 'text', 'content': full_text}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)
                yield f"event: done\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
                break

            if kind == "error":
                yield f"event: error\ndata: {json.dumps({'type': 'error', 'content': data}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
                break

            ns = ()
            if isinstance(data, tuple):
                ns = data[0] if len(data) > 1 else ()
                data = data[1] if len(data) > 1 else data[0]
            if not isinstance(data, dict):
                continue
            if ns and ns != ("",):
                continue

            msgs = data.get("messages", [])
            worker_results = data.get("worker_results", {})
            if worker_results:
                latest_worker_results = dict(worker_results)
            if data.get("final_answer"):
                latest_final_answer = str(data["final_answer"])
            if initial_count < 0:
                initial_count = len(msgs)

            for idx in range(len(msgs) - 1, initial_count - 1, -1):
                msg = msgs[idx]
                msg_type = type(msg).__name__
                content = getattr(msg, "content", "") or ""
                has_tools = getattr(msg, "tool_calls", None)
                if msg_type == "AIMessage" and content and not has_tools:
                    if content.startswith("【") and "Agent 返回】" in content[:50]:
                        continue
                    if content not in ai_reply:
                        ai_reply.append(content)
                        answer_candidates.append(content)
                        yield f"event: text\ndata: {json.dumps({'type': 'text', 'content': content}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0)
                    break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ==================== 会话管理 API ====================

@router.get("/sessions")
async def list_sessions(request: FastAPIRequest):
    principal = _session_principal_or_error(request)
    return {
        "sessions": [
            session
            for session in _list_sessions()
            if session_registry.is_owned_by(session.get("id", ""), principal)
        ]
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: FastAPIRequest):
    _authorize_session_request(request, session_id)
    msgs = _get_session_messages(session_id)
    if not _session_database_available():
        return {"session": _MEM_SESSIONS.get(session_id), "messages": msgs}
    with _sess_conn() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = %s", (session_id,)).fetchone()
    return {
        "session": dict(row) if row else None,
        "messages": msgs,
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: FastAPIRequest):
    _authorize_session_request(request, session_id)
    _delete_session(session_id)
    try:
        from app.agents.orchestrator import clear_session
        clear_session(session_id)
    except Exception:
        pass
    return {"status": "ok"}


# ==================== 文档管理 ====================

@router.post("/upload")
async def upload_document(file: UploadFile = File(...),
                          classification: int = Form(1),
                          department: str = Form("")):
    header = await file.read(8192)
    try:
        inspection = inspect_upload_header(file.filename, header)
    except UploadSecurityError as exc:
        raise HTTPException(
            status_code=400, detail=getattr(exc, "code", None) or "unsupported_file"
        ) from exc

    next_version = peek_next_document_version(inspection.display_filename)
    resource_id = uuid.uuid4().hex
    storage_path = build_storage_path(DOCUMENTS_DIR, resource_id, inspection.extension)
    temp_path = storage_path.with_name(f".upload-{resource_id}.tmp")
    written = 0
    try:
        with temp_path.open("xb") as output:
            written += len(header)
            if written > MAX_DOCUMENT_UPLOAD_BYTES:
                raise UploadSecurityError("upload exceeds the configured size limit")
            output.write(header)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_DOCUMENT_UPLOAD_BYTES:
                    raise UploadSecurityError("upload exceeds the configured size limit")
                output.write(chunk)
            output.flush()
        os.replace(temp_path, storage_path)
    except UploadSecurityError as exc:
        if temp_path.exists():
            temp_path.unlink()
        if storage_path.exists():
            storage_path.unlink()
        raise HTTPException(status_code=413, detail="upload_too_large") from exc
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        if storage_path.exists():
            storage_path.unlink()
        raise

    stored_name = storage_path.name
    file_path = str(storage_path)
    logger.info(f"[Docs] upload received: {inspection.display_filename} -> {stored_name}")
    try:
        content = await asyncio.to_thread(load_document, file_path)
    except Exception as exc:
        logger.exception(f"[Docs] parse failed: {file.filename}")
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail="document_parse_failed") from exc

    try:
        ok, msg = await asyncio.to_thread(
            retriever.add_document,
            inspection.display_filename,
            content,
            classification,
            department or None,
        )
    except Exception as exc:
        logger.exception(f"[Docs] index failed: {file.filename}")
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail="document_index_failed") from exc

    if ok:
        version_meta = {"version": next_version}
        if catalog_database_available():
            try:
                _upsert_document(inspection.display_filename, classification, department)
            except Exception as exc:
                logger.warning(f"[Docs] metadata sync failed: {exc}")
            try:
                version_meta = record_document_version(
                    inspection.display_filename,
                    classification=classification,
                    department=department,
                    storage_path=file_path,
                    version=next_version,
                )
            except Exception as exc:
                logger.warning(f"[Docs] version record failed: {exc}")
        from app.agents.tools import rebuild_bm25
        rebuild_future = _executor.submit(rebuild_bm25)
        rebuild_future.add_done_callback(
            lambda future: logger.error(f"[BM25] 索引重建失败: {future.exception()}")
            if future.exception()
            else None
        )
        return {
            "filename": inspection.display_filename,
            "stored_name": stored_name,
            "resource_id": resource_id,
            "version": version_meta["version"],
            "status": "ok",
            "message": msg,
        }
    if os.path.exists(file_path):
        os.remove(file_path)
    return {"filename": inspection.display_filename, "status": "skipped", "message": msg}


@router.get("/documents")
async def list_documents(request: FastAPIRequest):
    indexed_names = set(retriever.list_documents())
    visible_rows = _visible_document_rows(request, current_documents())
    return {
        "documents": [
            row["filename"]
            for row in visible_rows
            if row.get("filename") in indexed_names
        ]
    }


@router.get("/documents/catalog")
async def list_document_catalog(request: FastAPIRequest):
    return {"documents": _visible_document_rows(request, current_documents())}


@router.get("/documents/{filename}/versions")
async def document_version_history(filename: str, request: FastAPIRequest):
    versions = list_document_versions(filename)
    if not versions:
        raise HTTPException(status_code=404, detail="resource_not_found")
    principal = _document_principal_or_error(request)
    decision = _document_authorization_decision(principal, filename, versions[0], ACTION_VIEW)
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason_code)
    return {
        "filename": filename,
        "versions": _visible_document_rows(request, versions),
    }


@router.get("/documents/{filename}/file")
async def get_document_file(
    filename: str,
    request: FastAPIRequest,
    inline: bool = False,
):
    _, file_path = _authorize_document_request(request, filename, ACTION_DOWNLOAD)

    media_type, _ = mimetypes.guess_type(file_path)
    media_type = media_type or "application/octet-stream"
    disposition = "inline" if inline else "attachment"
    return FileResponse(
        file_path,
        filename=os.path.basename(file_path),
        media_type=media_type,
        content_disposition_type=disposition,
    )


@router.get("/documents/{filename}/preview")
async def get_document_preview(filename: str, request: FastAPIRequest):
    _, file_path = _authorize_document_request(request, filename, ACTION_VIEW)
    try:
        return await asyncio.to_thread(build_document_preview, file_path, filename)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail="unsupported_preview") from exc
    except Exception as exc:
        logger.exception(f"[Docs] preview failed: {filename}")
        raise HTTPException(status_code=500, detail="document_preview_failed") from exc


@router.delete("/documents/{filename}")
async def delete_document(filename: str, request: FastAPIRequest):
    _, file_path = _authorize_document_request(request, filename, ACTION_DELETE)
    retriever.delete_document(filename)
    from app.agents.tools import rebuild_bm25
    rebuild_bm25()  # C1: ?????????
    for item in list_document_versions(filename):
        storage_path = item.get("storage_path")
        if storage_path and os.path.exists(storage_path):
            os.remove(storage_path)
    if os.path.exists(file_path):
        os.remove(file_path)
    delete_document_versions(filename)
    return {"status": "ok", "filename": filename}


# ==================== Layer 5: 队列削峰 API ====================

@router.get("/queue/status/{request_id}")
async def queue_status(request_id: str, request: FastAPIRequest):
    """轮询队列请求的处理状态。前端每 3s 调用一次，直到 status=done"""
    from app.common.reliable_queue import QueueConnectionError

    try:
        queue = _get_reliable_queue()
    except QueueConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    _authorize_queue_task(request, queue, request_id)
    status = queue.status(request_id)
    if status is None:
        return {"status": "expired", "message": "请求已过期，请重新提交"}
    failure = queue.failure(request_id)
    if status == "done":
        return {
            "status": "done",
            "request_id": request_id,
            "result": queue.result(request_id),
            "failure": failure,
        }
    if status == "queued":
        pending = queue.redis.lrange(queue.pending_key, 0, -1)
        ids = [item.decode() if isinstance(item, bytes) else str(item) for item in pending]
        return {
            "status": "queued",
            "request_id": request_id,
            "position": ids.index(request_id) + 1 if request_id in ids else None,
            "failure": failure,
        }
    return {"status": status, "request_id": request_id, "failure": failure}


@router.post("/queue/{request_id}/cancel")
async def cancel_queued_request(request_id: str, request: FastAPIRequest):
    from app.common.reliable_queue import QueueConnectionError

    try:
        queue = _get_reliable_queue()
    except QueueConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    _authorize_queue_task(request, queue, request_id)
    if not queue.cancel(request_id):
        raise HTTPException(status_code=404, detail="resource_not_found")
    return {
        "cancelled": True,
        "request_id": request_id,
        "status": queue.status(request_id),
    }


@router.get("/queue/stats")
async def queue_stats():
    """队列监控：当前排队数、处理中数"""
    from app.common.reliable_queue import QueueConnectionError

    try:
        queue = _get_reliable_queue()
    except QueueConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    return {
        "queue_length": len(queue.redis.lrange(queue.pending_key, 0, -1)),
        "processing": len(queue.redis.lrange(queue.processing_key, 0, -1)),
    }
