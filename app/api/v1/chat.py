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
import itertools
from concurrent.futures import ThreadPoolExecutor
from contextlib import aclosing
from pathlib import Path

# 显式线程池 — 支持 1000+ 并发（每个 uvicorn 实例）
_executor = ThreadPoolExecutor(max_workers=50, thread_name_prefix="ezn_")
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, UploadFile, File, Form, Request as FastAPIRequest, Response as FastAPIResponse, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from app.common.no_store import NO_STORE_HEADERS
from pydantic import BaseModel

from app.agents.contracts import AuthorizationDecision, ErrorEnvelope
from app.common import auth
from app.common.audit import record_audit
from app.storage import pending_approvals
from app.common.authorization import principal_from_request
from app.rag.loader import load_document
from app.documents.preview import build_document_preview
from app.rag.retriever import DocumentRetriever
from app.rag.filters import (
    RetrievalScopeError,
    record_retrieval_scope,
    resolve_document_retrieval_scope,
)
from app.rag.indexing import (
    DocumentIndexPublication,
    IndexPublicationError,
    IndexPublisher,
    IndexRegistry,
    PostgresIndexStore,
    default_metadata_path,
)
from app.common.model_handler import ModelHandler, ModelSource
from app.common.logger import logger
from app.common.performance import PerformanceStats, RequestBudget
from app.common.permissions import ACTION_DELETE, ACTION_DOWNLOAD, ACTION_VIEW
from app.common.policy import authorization_decision
from app.documents.catalog import (
    build_storage_name,
    current_documents,
    public_document_row,
    _database_available as catalog_database_available,
    delete_document_versions,
    list_document_versions,
    peek_next_document_version,
    record_document_version,
    record_local_document_version,
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


class CancelGeneration(threading.Event):
    """一次运行的取消标记，它本身就是"这一代"的标识。

    标记按 ``(session_id, epoch)`` 登记，``epoch`` 取自进程内单调计数器，所以同一个会话
    的两代永不复用同一个标识：读的人能指名要哪一代，不会借到别人的取消状态。继承
    ``Event`` 是有意的——它要原样穿过 ``config["configurable"]`` 交给编排与工作线程，
    那边每步 ``is_set()`` 读的天然就是"我这一代有没有被停掉"，不必回头查任何登记表。
    """

    def __init__(self, session_id: str, epoch: int) -> None:
        super().__init__()
        self.session_id = session_id
        self.epoch = epoch


# 只反映在飞的运行：register 放入本代，运行收尾（正常/异常/取消/客户端断连）在 finally 里弹出。
_REQUESTS: dict[tuple[str, int], CancelGeneration] = {}
# 取消落在"没有在飞运行"上时的一次性标记，由下一代 register_request 消费掉。
_PENDING_CANCELLATIONS: set[str] = set()
_REQUESTS_LOCK = threading.Lock()
_GENERATION_SEQUENCE = itertools.count(1)
_ASK_STATS = PerformanceStats()


def _newest_generation(session_id: str) -> CancelGeneration | None:
    """该会话最新的一代（调用方必须已持有 ``_REQUESTS_LOCK``）。"""
    epochs = [epoch for (owner, epoch) in _REQUESTS if owner == session_id]
    if not epochs:
        return None
    return _REQUESTS[(session_id, max(epochs))]


def register_request(session_id: str) -> CancelGeneration:
    """开一代：按 (session_id, epoch) 登记并返回本代的取消标记。

    先到的取消在这里一次性消费掉。老实现无条件换上一个干净的 Event，于是
    ``ask()`` 返回之后、本行执行之前到达的停止会被抹掉；现在它归这一代读。
    """
    with _REQUESTS_LOCK:
        generation = CancelGeneration(session_id, next(_GENERATION_SEQUENCE))
        _REQUESTS[(session_id, generation.epoch)] = generation
        if session_id in _PENDING_CANCELLATIONS:
            _PENDING_CANCELLATIONS.discard(session_id)
            generation.set()
        return generation


def release_request(generation: CancelGeneration | None) -> None:
    """一次运行结束时弹出本代条目；只弹自己那一代，不带走并存的新一代。"""
    if generation is None:
        return
    with _REQUESTS_LOCK:
        key = (generation.session_id, generation.epoch)
        if _REQUESTS.get(key) is generation:
            _REQUESTS.pop(key, None)


def current_marker(session_id: str) -> CancelGeneration | None:
    """该会话当前在飞那一代的标记；没有在飞运行时返回 ``None``。"""
    with _REQUESTS_LOCK:
        return _newest_generation(session_id)


def cancel_request(session_id: str) -> bool:
    """取消该会话**当前这一代**，并报告这里是否真有在飞的运行。

    没有在飞运行时不假装成功，但标记必须留下，并且是留给**下一代一次性消费**：
    否则"归属校验之后、``register_request`` 之前"到达的停止，以及"会话停在 HITL 挂起时
    按停止、随后点批准"这两条都会静默丢失。已经结束的代不再受任何取消影响，标记也
    就无处跨代泄漏。返回值只在真的有在飞运行时为 ``True``——为空操作报成功会让 API
    宣称一个它没有造成的业务结果。
    """
    with _REQUESTS_LOCK:
        generation = _newest_generation(session_id)
        if generation is None:
            _PENDING_CANCELLATIONS.add(session_id)
            return False
        generation.set()
        return True


def is_request_cancelled(session_id: str, epoch: int | None = None) -> bool:
    """按**代**读取消状态。

    带 ``epoch`` 时只认那一代：已结束或从未存在即视为未取消，绝不把别人的取消算到它头上。
    不带 ``epoch`` 时读当前在飞那一代；没有在飞运行时，报告"取消正武装给下一代"，
    与 ``cancel_request`` 的口径一致。
    """
    with _REQUESTS_LOCK:
        if epoch is not None:
            generation = _REQUESTS.get((session_id, epoch))
            return bool(generation and generation.is_set())
        generation = _newest_generation(session_id)
        if generation is not None:
            return generation.is_set()
        return session_id in _PENDING_CANCELLATIONS


def _reap_agent_worker(future, *, session_id: str, stage: str) -> None:
    """给 executor 里的工作线程装上可见的收尾。

    两处 ``loop.run_in_executor(_executor, _run)`` 原先把返回的 future 直接丢掉：没有
    人持有它，CPython 只在 GC 时嘟囔一句，而工作线程里逃出的异常（``_run`` 的 try 覆盖
    不到的那部分，例如 put 本身失败、生成器 finally 里再抛）就此无声消失。线上表现是
    "流断了，日志里什么都没有"。回调只记日志，不改变任何流的语义。
    """

    def _done(fut) -> None:
        try:
            exc = fut.exception()
        except BaseException:
            # asyncio Future 在被取消后 exception() 会抛 CancelledError；回调本身
            # 跑在事件循环里，绝不能把异常再抛回循环。
            return
        if exc is not None:
            logger.error(
                f"[{stage}] agent worker raised for session={session_id}: "
                f"{type(exc).__name__}: {exc}"
            )

    future.add_done_callback(_done)


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


def _document_source_row(worker: str, evidence: dict) -> dict | None:
    """还原一条文档 Evidence 成 ``DocumentRetrievalScope.allows`` 认得的命中形状。

    旧 ``/chat`` 端点把 ``retriever.search`` 的返回字典直接喂给 ``scope.allows``；Agent 路径里
    同一份命中先被 ``app/agents/evidence.py::record_document_hits`` 记进证据袋，密级与部门
    落在 ``metadata`` 下。这里只做搬运，**不新增任何放行分支**：判据还是那个 ``scope.allows``，
    缺可用元数据的命中一律不可见。
    """
    if not isinstance(evidence, dict) or evidence.get("source_type") != "document":
        return None
    source = str(evidence.get("source_name") or "").strip()
    if not source:
        return None
    metadata = evidence.get("metadata") if isinstance(evidence.get("metadata"), dict) else {}
    locator = evidence.get("locator") if isinstance(evidence.get("locator"), dict) else {}
    return {
        "worker": worker,
        "source": source,
        "source_id": str(evidence.get("source_id") or source),
        "chunk_index": locator.get("chunk_index"),
        "score": evidence.get("score"),
        "score_type": evidence.get("score_type"),
        "document_version_id": evidence.get("document_version_id"),
        "index_version_id": evidence.get("index_version_id"),
        "content_sha256": metadata.get("content_sha256"),
        # 这两项就是 ``scope.allows`` 的判据，留在事件里是为了"这条为什么能看"可复核。
        "classification": metadata.get("classification"),
        "department": metadata.get("department"),
        "permission_checked": bool(evidence.get("permission_checked")),
        "provenance_status": evidence.get("provenance_status"),
    }


def _collect_document_sources(agent_results: dict, sink: dict) -> None:
    """把一次流式回报里所有 worker 的文档证据汇进 sink，按 ``source_id`` 去重。

    取证自工具边界实际检到的东西，不从正文里反推——那是 ``app/agents/evidence.py`` 开篇
    已经写死的纪律：本轮没有检索过的文档不允许凭着答案文本出现在来源里。
    """
    for worker, record in (agent_results or {}).items():
        if not isinstance(record, dict):
            continue
        for evidence in record.get("evidence") or []:
            row = _document_source_row(str(worker), evidence)
            if row is not None:
                sink.setdefault(row["source_id"], row)


def _authorized_source_rows(rows: dict, principal) -> tuple[list[dict], str]:
    """用与旧 ``/chat`` 同一个 ``scope.allows`` 复核每条来源，返回可见行与理由码。

    ``search_for_principal`` 已经把 ``scope.allows`` 当作 pred 过滤过一次，这里是新出口上
    的第二道防线：来源事件是本单新开的泄露面，不能默认上游永远没漏。
    """
    try:
        scope = resolve_document_retrieval_scope(principal)
    except RetrievalScopeError as scope_error:
        logger.warning(f"[ASK] 来源事件缺少可用检索范围: code={scope_error.code}")
        return [], scope_error.code
    return [row for row in rows.values() if scope.allows(row)], scope.reason_code


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


def _document_resource_scope(filename: str, version: dict) -> dict:
    """Build the authorization attributes one stored document version carries.

    ``owner_id`` used to be read out of a catalog row that never had the column, so
    every decision fell through to the department intersection. The catalog now
    records the uploader, and this projection is the single place where a document
    row becomes a resource scope, which also puts the same attributes into the audit
    journal as the decision itself.
    """
    return {
        "resource_type": "document",
        "resource_id": version.get("resource_id") or version.get("id") or filename,
        "owner_id": version.get("owner_id"),
        "department": version.get("department"),
        "department_ids": version.get("department_ids"),
        "classification": version.get("classification"),
        "visibility": version.get("visibility", "private"),
        "version_id": version.get("version_id") or str(version.get("version", "")),
        "status": version.get("status", "active"),
    }


def _document_storage_path(version: dict) -> str:
    return str(version.get("storage_path") or "")


def _document_authorization_decision(principal, filename: str, version: dict, action: str):
    return authorization_decision(
        principal,
        _document_resource_scope(filename, version),
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


def _agent_user_context(principal) -> dict | None:
    """Build the Agent runtime context that grants a request its authorization scope."""
    if principal is None:
        return None
    return {
        "username": principal.username,
        "role": principal.role,
        "department": principal.department or "",
        "principal": principal,
    }


def _visible_document_rows(request: FastAPIRequest, rows: list[dict]) -> list[dict]:
    principal = _document_principal_or_error(request)
    # The row is shaped after it has been filtered: an authorization decision must
    # read what the store recorded, and a response must carry the ownership and parse
    # state of that same row rather than whatever shape the caller handed over.
    return [
        public_document_row(row)
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
) -> tuple[dict, AuthorizationDecision]:
    """Authorize a document operation and put the whole judgment in the audit journal.

    The decision travels back with the stored version because the caller has to
    record which rule allowed the change it is about to perform, and a denial has to
    stay traceable after the response is gone.
    """
    principal = _document_principal_or_error(request)
    version = _latest_document_version(filename)
    if not version:
        raise HTTPException(status_code=404, detail="resource_not_found")

    decision = _document_authorization_decision(principal, filename, version, action)
    record_audit(
        principal,
        action,
        "allowed" if decision.allowed else "denied",
        filename,
        decision.reason_code,
        request_id=principal.request_id or None,
        resource_scope=_document_resource_scope(filename, version),
        policy_version=decision.policy_version,
    )
    if not decision.allowed:
        status_code = 401 if decision.reason_code == "authentication_required" else 403
        raise HTTPException(status_code=status_code, detail=decision.reason_code)
    return version, decision


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
                department TEXT,
                owner_id TEXT,
                size_bytes BIGINT,
                parse_status TEXT NOT NULL DEFAULT 'pending'
            )
        """)
        conn.commit()


if catalog_database_available():
    try:
        _ensure_documents_table()
    except Exception:
        pass  # 导入不硬依赖库；上传时再懒建表


def _upsert_document(
    filename: str,
    classification: int,
    department: str,
    owner_id: str | None = None,
    *,
    size_bytes: int | None = None,
    parse_status: str = "pending",
):
    """Keep the logical document row aligned with the version just stored.

    Ownership is written here too: the documents row is what an operator inspects when
    a version has to be reassigned, and an owner that only ever reached the version
    table would leave the logical row permanently unattributed.
    """
    _ensure_documents_table()
    with _sess_conn() as conn:
        conn.execute(
            "INSERT INTO documents (filename, classification, department, owner_id, size_bytes, parse_status) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (filename) DO UPDATE SET "
            "classification = EXCLUDED.classification, "
            "department = EXCLUDED.department, "
            "owner_id = COALESCE(documents.owner_id, EXCLUDED.owner_id), "
            "size_bytes = COALESCE(EXCLUDED.size_bytes, documents.size_bytes), "
            "parse_status = EXCLUDED.parse_status",
            (
                filename,
                int(classification),
                department or None,
                owner_id or None,
                size_bytes,
                parse_status,
            ),
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

@router.post("/chat")
async def chat(request: ChatRequest, http_request: FastAPIRequest):
    """旧版纯文本问答：检索同样必须落在 Principal 的权限范围内。"""
    principal = _document_principal_or_error(http_request)
    try:
        scope = resolve_document_retrieval_scope(principal)
    except RetrievalScopeError as scope_error:
        status_code = 401 if scope_error.code == "authentication_required" else 403
        logger.warning(f"[CHAT] 拒绝无范围检索: user={principal.username} code={scope_error.code}")
        raise HTTPException(status_code=status_code, detail=scope_error.code)
    retrieval_filter = scope.filters

    async def generate():
        try:
            sources = [source for source in retriever.search(request.message, k=5, where=retrieval_filter) if scope.allows(source)]
            record_retrieval_scope(principal, scope, hit_count=len(sources))
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
    from app.common.cache import answer_cache_scope, get_cached_answer
    # 会话问答必须保留当前会话语境，不能命中跨会话的全局答案缓存。
    # 无 session_id 的兼容调用仍可使用问题级缓存。
    use_answer_cache = not bool(request.session_id)
    # 缓存内容取决于调用者可检索的文档（归属、密级、部门），所以键必须带上调用者
    # 作用域：一次带权限的检索结果不能被另一个人用同样的问题文本读回去。
    answer_scope = answer_cache_scope(request_principal, username=username)
    cached = get_cached_answer(rewritten_msg, scope=answer_scope) if use_answer_cache else None
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
        # 注册与 finally 弹出必须在同一个帧里：generate() 一行都没跑就被 aclose() 时
        # 根本不会注册，注册过则无论正常收尾、抛异常、被取消还是客户端走人都走得到
        # 这个 finally，登记表才真的只反映在飞的运行。
        cancel_event = register_request(thread_id)
        try:
            async with aclosing(_ask_stream(cancel_event)) as stream:
                async for chunk in stream:
                    yield chunk
        finally:
            release_request(cancel_event)

    async def _ask_stream(cancel_event: CancelGeneration):
        from app.agents.orchestrator import run_with_stream

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
                    # 这一行是 R12 的正题：标记不传下去，编排里的取消检查点就恒等于
                    # _raise_if_cancelled(None)，用户按了停止图照样跑完。
                    cancel_event=cancel_event,
                ):
                    if cancel_event.is_set():
                        # 停止之后不再往没人读的流里塞事件；已经落盘的不回滚，那不是
                        # 本轮语义。
                        return
                    result_queue.put(("event", event))
                result_queue.put(("done", None))
            except Exception as e:
                logger.exception(f"[ask] agent worker raised for session={thread_id}")
                result_queue.put(("error", str(e)))

        loop = asyncio.get_running_loop()
        agent_future = loop.run_in_executor(_executor, _run)
        _reap_agent_worker(agent_future, session_id=thread_id, stage="ask")

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
        source_rows: dict[str, dict] = {}
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
            # 每步按**本代**比对，而不是"这个会话有没有被停过"：同会话并存的另一代
            # 被停，不该让这一轮误判已取消。
            if is_request_cancelled(thread_id, epoch=cancel_event.epoch):
                # 还没开工的 _run 直接取消；已经在跑的 cancel() 返回 False，由编排里的
                # 检查点协同退出——线程不能强杀，这里不假装能。
                agent_future.cancel()
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
                    # 码只走下面 canonical 的 data.error_code 字段：这句要经
                    # _save_message 落进会话历史，散文里再夹一遍码名就永久洗不掉了
                    # （R16；前端渲染期的清洗救得了新消息，救不了历史行）。
                    failure_text = "本轮未产出任何结论，请重试或补充数据范围。"
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
                        cache_answer(rewritten_msg, full_text, scope=answer_scope)
                    yield f"event: text\ndata: {json.dumps({'type': 'text', 'content': full_text}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)
                logger.info(f"[ASK] session={thread_id[:8]}... {elapsed_total}s | steps={len(steps_log)}")

                if intr:
                    # 与 SSE event: hitl 同一个地方写库：分了两处就会出现"事件发了、
                    # 表里没写"或反之，面板与流各说一套。
                    _record_pending_approval(
                        thread_id,
                        request_principal,
                        intr,
                        request_id=request_id,
                        trace_id=trace_id,
                        task_id=task_id,
                    )
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
                # R41：sources 提升为 canonical 事件。位置在 request.completed 之后、legacy
                # done 之前：done 仍是"流结束"的唯一信号，旧客户端遇到认不得的事件名也
                # 不会丢正文；request.started/completed 的 sequence 也不因本单漂移。
                visible_rows, scope_reason_code = _authorized_source_rows(source_rows, request_principal)
                yield canonical_sse_event(
                    "sources",
                    request_id=request_id,
                    trace_id=trace_id,
                    task_id=task_id,
                    sequence=sequence,
                    status="completed",
                    data={
                        "session_id": thread_id,
                        "sources": visible_rows,
                        "hit_count": len(visible_rows),
                        # 缺了这个数字，"0 条来源"就分不清"没检索到"与"检索到了但不给你看"。
                        "unauthorized_count": len(source_rows) - len(visible_rows),
                        "scope_reason_code": scope_reason_code,
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
            # R41：边跑边收证据，不在收尾时反推。取消/失败分支不会读到这个字典，
            # 所以"没有产出可见答案的一轮"也绝不会发出来源事件。
            agent_results = data.get("agent_results")
            if isinstance(agent_results, dict):
                _collect_document_sources(agent_results, source_rows)

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


def _record_pending_approval(
    session_id: str,
    principal,
    intr: dict | None,
    *,
    request_id: str = "",
    trace_id: str = "",
    task_id: str = "",
) -> None:
    """把一次挂起写成一行 awaiting。

    记账失败不许打断用户已经等到的回答流，所以这里吞异常；但也不许静默——面板少一条
    待办和面板说"没有待办"是两件不同的事，因此留 exception 级痕迹。
    """
    owner_user_id = str(getattr(principal, "user_id", "") or "")
    if not owner_user_id or not intr:
        return
    try:
        pending_approvals.record_awaiting(
            session_id,
            owner_user_id,
            list(intr.get("pending") or []),
            request_id=request_id,
            trace_id=trace_id,
            task_id=task_id,
        )
    except Exception:
        logger.exception(
            f"[HITL] 挂起待办没能写入 session={session_id}，审批面板可能少一条待办"
        )


def _decide_pending_approval(session_id: str, status: str) -> None:
    """把挂起行改成终态；同上，不许因为记账坏了而打断回答。"""
    try:
        pending_approvals.mark_status(session_id, status)
    except Exception:
        logger.exception(
            f"[HITL] 挂起待办没能改成 {status} session={session_id}，面板可能仍显示待批"
        )


DEFAULT_PENDING_LIMIT = 50
MAX_PENDING_LIMIT = 200


@router.get("/hitl/pending")
async def hitl_pending(
    http_request: FastAPIRequest,
    session_id: str = "",
    limit: int = DEFAULT_PENDING_LIMIT,
    offset: int = 0,
):
    """列出调用方自己的 HITL 挂起待办，并对每一行向图复核。

    这张表是"事件记录"，图才是"当前状态"的权威，所以列表前逐行问一次
    check_interrupt(session_id)：对不上就地标 stale 并排除。少了这一步，面板列出的就是
    已经跑完或已经被放弃的假待办（设计件 §3.2 点名的陷阱）。

    复核本身抛错时**不列**该行，但也**不改判**：一次图的临时故障不该把真待办判死。

    权限不新增语义：归属沿用 _authorize_session_request 的同一个谓词，别人的会话像
    不存在一样（404 resource_not_found），不是 403。

    分页：``limit`` 默认 50、硬上限 200，按 ``created_at DESC`` 截断，``offset`` 翻页。
    代价来自复核而不是取行，所以上限既要下推进 SQL（``open_items``），也要限定复核循环
    ——多取的那一行只用来回答 ``has_more``，绝不进复核循环，否则截断掉的待办会被误判
    stale（那是把"没看过"写成"已作废"）。
    """
    principal = _session_principal_or_error(http_request)
    if session_id:
        _authorize_session_request(http_request, session_id)

    from app.agents.orchestrator import check_interrupt

    applied_limit = max(1, min(int(limit), MAX_PENDING_LIMIT))
    applied_offset = max(0, int(offset))
    try:
        # 多问一行只为知道还有没有：这一行不参与下面的复核。
        rows = pending_approvals.open_items(
            owner_user_id=str(principal.user_id or ""),
            session_id=session_id or None,
            limit=applied_limit + 1,
            offset=applied_offset,
        )
    except pending_approvals.PendingApprovalStoreMissing as exc:
        # 只接这一种错。吞成 200 空列表是造假（R13 整单就是为了消灭它），翻成
        # internal_error 又等于把"跑迁移"这条运维可执行的诊断洗成通用故障。
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
    has_more = len(rows) > applied_limit
    page = rows[:applied_limit]

    items: list[dict] = []
    for row in page:
        if not row.parked_steps:
            continue
        try:
            confirmed = check_interrupt(row.session_id)
        except Exception:
            logger.exception(f"[HITL] 复核挂起态失败，本次不列出 session={row.session_id}")
            continue
        pending = [str(step) for step in ((confirmed or {}).get("pending") or [])]
        if not pending or not set(row.parked_steps) <= set(pending):
            _decide_pending_approval(row.session_id, pending_approvals.STALE)
            continue
        graph_labels = [str(label) for label in ((confirmed or {}).get("labels") or [])]
        if len(graph_labels) == len(pending):
            wanted = set(row.parked_steps)
            labels = [label for step, label in zip(pending, graph_labels) if step in wanted]
        else:
            labels = graph_labels
        items.append(
            {
                "session_id": row.session_id,
                "owner_user_id": row.owner_user_id,
                "parked_steps": list(row.parked_steps),
                "labels": labels,
                "status": row.status,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "request_id": row.request_id,
                "trace_id": row.trace_id,
                "task_id": row.task_id,
            }
        )
    # count 仍是"过滤后长度"（契约已明写它不得当总数用）；has_more 说的是账本还有行，
    # 不是"还有多少条能看"。
    return {
        "items": items,
        "count": len(items),
        "limit": applied_limit,
        "offset": applied_offset,
        "has_more": has_more,
    }


@router.post("/approve")
async def approve(request: ApproveRequest, http_request: FastAPIRequest):
    # /approve 会接管该会话的挂起轮次并把会话内容流式回传给调用方，
    # 因此它和读取会话必须是同一套归属判定，不能只校验"已登录"。
    principal = _authorize_session_request(http_request, request.session_id)
    user_ctx = _agent_user_context(principal)
    # canonical 事件必须带 request_id/trace_id/task_id，而 /approve 此前整条流只有
    # legacy 事件、从来没有过这三个 id。生成方式与 /ask (:784-786) 逐字相同，客户端
    # 不必为两个端点写两套解析。
    request_id = f"req-{uuid.uuid4().hex}"
    trace_id = f"trace-{uuid.uuid4().hex}"
    task_id = f"task-{uuid.uuid4().hex}"

    async def generate():
        # 同 /ask：注册与本代弹出留在同一个帧里。resume 起来的那一代才是取消唯一能打击
        # 的对象，所以停在 HITL 的会话被按过停止之后，随后的批准会拿到一个生来就置位的
        # 标记，编排的第一个检查点连 resume 都不发起（甲裁定的落地判据）。
        cancel_event = register_request(request.session_id)
        try:
            async with aclosing(_approve_stream(cancel_event)) as stream:
                async for chunk in stream:
                    yield chunk
        finally:
            release_request(cancel_event)

    async def _approve_stream(cancel_event: CancelGeneration):
        from app.agents.orchestrator import run_interrupt_stream

        budget = RequestBudget(float(os.getenv("CHAT_REQUEST_TIMEOUT", "300")))
        heartbeat_interval = float(os.getenv("SSE_HEARTBEAT_INTERVAL", "15"))
        result_queue: qmod.Queue = qmod.Queue()

        def _run():
            try:
                for event in run_interrupt_stream(
                    request.session_id,
                    approved=request.approved,
                    user=user_ctx,
                    cancel_event=cancel_event,
                ):
                    if cancel_event.is_set():
                        return
                    result_queue.put(("event", event))
                result_queue.put(("done", None))
            except Exception as e:
                logger.exception(
                    f"[approve] agent worker raised for session={request.session_id}"
                )
                result_queue.put(("error", str(e)))

        loop = asyncio.get_running_loop()
        agent_future = loop.run_in_executor(_executor, _run)
        _reap_agent_worker(agent_future, session_id=request.session_id, stage="approve")

        start_time = time.time()
        last_emit = time.monotonic()
        sequence = 1
        ai_reply: list[str] = []
        latest_worker_results: dict = {}
        latest_final_answer = ""
        answer_candidates: list[str] = []
        initial_count = -1
        # R55：来源取证复用 /ask 那一个收集器与同一种 sink，收尾时只读不反推。
        source_rows: dict[str, dict] = {}

        # canonical 信封事件从这一条起与 /ask (:1084-1093) 同构：同一个构造器、同一套
        # 三个 id、sequence 从 1 连续。legacy 事件全部照旧保留，canonical 是加在旁边。
        yield canonical_sse_event(
            "request.started",
            request_id=request_id,
            trace_id=trace_id,
            task_id=task_id,
            sequence=sequence,
            status="running",
            data={"session_id": request.session_id},
        )
        sequence += 1

        while True:
            # 与 /ask 同口径：按本代比对。上一代留下的取消判不到这一轮头上。
            if is_request_cancelled(request.session_id, epoch=cancel_event.epoch):
                agent_future.cancel()
                # 停止 != 拒绝（裁定 ④甲）：账面写 abandoned，绝不写 refused。
                # 这一行在 R12（826d318）之前是不敢写的——那时"停止"的会话其实跑完了。
                _decide_pending_approval(request.session_id, pending_approvals.ABANDONED)
                # 先发 canonical、再发 legacy，与 /ask 的取消形状 (:958-973) 一致：
                # 事件名、status="cancelled"、data.session_id 全同。legacy 保留是给
                # 还没接 canonical 的旧客户端的，不是过渡期垃圾。
                yield canonical_sse_event(
                    "request.cancelled",
                    request_id=request_id,
                    trace_id=trace_id,
                    task_id=task_id,
                    sequence=sequence,
                    status="cancelled",
                    data={"session_id": request.session_id},
                )
                sequence += 1
                yield sse_event(
                    "cancelled",
                    {"type": "cancelled", "session_id": request.session_id},
                )
                break
            if budget.expired():
                # error_code 与 /ask (:1117-1126) 同名同形状：同一个"超过处理时限"在两条
                # 流里必须是同一个码，客户端不必按端点分支。legacy error 原文照发。
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
                full_text = _select_final_answer(
                    final_answer=latest_final_answer,
                    worker_results=latest_worker_results,
                    candidates=answer_candidates + ai_reply,
                )
                _save_message(request.session_id, "assistant", full_text)
                # 批准与拒绝都要闭合账面，否则面板会一直显示一条其实已经处理过的待办。
                # refused 这一支对应 84af113「拒绝必须真的拒绝」的账面部分。
                _decide_pending_approval(
                    request.session_id,
                    pending_approvals.RESUMED if request.approved else pending_approvals.REFUSED,
                )
                if full_text and full_text not in ai_reply:
                    yield f"event: text\ndata: {json.dumps({'type': 'text', 'content': full_text}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)
                # R55 判据④：批准后图可能又停在下一个 HITL 节点。先问真实的挂起状态，再
                # 决定这一轮算"完成（含新挂起）"还是"什么都没产出"——与 /ask (:1149-1156)
                # 用同一个 check_interrupt，不凭正文猜。
                try:
                    from app.agents.orchestrator import check_interrupt
                    intr = check_interrupt(request.session_id)
                except Exception:
                    intr = None
                if not full_text and not intr:
                    # 图跑完了，既没有正文也没有新的等待确认：这是内部失败。报成
                    # request.completed 就是把"什么都没产出"伪装成"已回答"
                    # （/ask :1162-1188 同一裁定）。legacy 这一支只发 done，不新增 error：
                    # 本单对 legacy 只加不减，旧客户端收到 done 才是既有契约。
                    yield canonical_sse_event(
                        "request.failed",
                        request_id=request_id,
                        trace_id=trace_id,
                        task_id=task_id,
                        sequence=sequence,
                        status="failed",
                        data={
                            "session_id": request.session_id,
                            "error_code": "no_answer_produced",
                            "worker_count": len(latest_worker_results),
                        },
                    )
                    sequence += 1
                    yield f"event: done\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)
                    break
                if intr:
                    # 原注释登记的那条长期缺口在本单补上：新挂起既当场发给客户端（legacy
                    # hitl 与 /ask :1212 同一个 payload 形状），也记成新的 awaiting 行。写账
                    # 必须排在上面的 _decide_pending_approval 之后，否则 mark_status 会去
                    # 闭合刚写入的新行、把旧行留在待批里。
                    _record_pending_approval(
                        request.session_id,
                        principal,
                        intr,
                        request_id=request_id,
                        trace_id=trace_id,
                        task_id=task_id,
                    )
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
                        "session_id": request.session_id,
                        "worker_count": len(latest_worker_results),
                        "elapsed": round(time.time() - start_time, 1),
                        "answer_length": len(full_text),
                        "awaiting_hitl": bool(intr),
                        "awaiting_steps": list(intr["pending"]) if intr else [],
                    },
                )
                sequence += 1
                # R41 新立的 sources 事件在 /approve 这个出口上此前是缺失的。判定入口逐字
                # 复用 /ask (:1235) 的 _authorized_source_rows -> app/rag/filters.py 的
                # scope.allows，不另写一套过滤；本轮没检索过就是 0 条，不伪造。
                visible_rows, scope_reason_code = _authorized_source_rows(source_rows, principal)
                yield canonical_sse_event(
                    "sources",
                    request_id=request_id,
                    trace_id=trace_id,
                    task_id=task_id,
                    sequence=sequence,
                    status="completed",
                    data={
                        "session_id": request.session_id,
                        "sources": visible_rows,
                        "hit_count": len(visible_rows),
                        # 缺了这个数字，"0 条来源"就分不清"没检索到"与"检索到了但不给你看"。
                        "unauthorized_count": len(source_rows) - len(visible_rows),
                        "scope_reason_code": scope_reason_code,
                    },
                )
                sequence += 1
                yield f"event: done\ndata: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)
                break

            if kind == "error":
                # 编排线程抛错 = 这一轮失败。legacy error 只带人读的文字，机器读的码走
                # canonical（/ask :1262-1271 同一口径），legacy 原文照发不吞。
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
            # R41/R55：边跑边收证据，不在收尾时反推。取消/超时/抛错三条分支都走不到发
            # sources 的那一段，所以"没有产出可见答案的一轮"绝不会发出来源事件。
            agent_results = data.get("agent_results")
            if isinstance(agent_results, dict):
                _collect_document_sources(agent_results, source_rows)
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

def _record_uploaded_version(
    *,
    principal,
    owner_id: str | None,
    filename: str,
    classification: int,
    department: str,
    storage_path: str,
    version: int,
    size_bytes: int | None,
    parse_status: str,
) -> dict:
    """Persist a stored version on whichever catalog path this deployment has.

    Both persistence paths get the owner. A failure here stays a warning: the file is
    already on disk and indexed, and dropping an upload because a metadata table is
    unreachable would lose a document the caller can no longer address. What is lost
    instead is attribution, and an unattributed row is treated as legacy -- visible to
    the management level only -- rather than as public.
    """
    metadata = {"version": version, "size_bytes": size_bytes, "parse_status": parse_status}
    if catalog_database_available():
        try:
            _upsert_document(
                filename,
                classification,
                department,
                owner_id,
                size_bytes=size_bytes,
                parse_status=parse_status,
            )
        except Exception as exc:
            logger.warning(f"[Docs] metadata sync failed: {exc}")
        try:
            return record_document_version(
                filename,
                classification=classification,
                department=department,
                storage_path=storage_path,
                version=version,
                principal=principal,
                owner_id=owner_id,
                size_bytes=size_bytes,
                parse_status=parse_status,
            )
        except Exception as exc:
            logger.warning(f"[Docs] version record failed: {exc}")
            return metadata
    try:
        return record_local_document_version(
            filename,
            classification=classification,
            department=department,
            storage_path=storage_path,
            version=version,
            principal=principal,
            owner_id=owner_id,
            size_bytes=size_bytes,
            parse_status=parse_status,
        )
    except Exception as exc:
        logger.warning(f"[Docs] local version record failed: {exc}")
        return metadata


# ==================== Index publication (S4) ====================

_INDEX_PUBLISHER: IndexPublisher | None = None
_INDEX_MIRROR: PostgresIndexStore | None = None
_INDEX_LOCK = threading.Lock()


def index_mirror_store() -> PostgresIndexStore:
    """The PostgreSQL mirror follows the catalog's own database health signal."""
    global _INDEX_MIRROR
    if _INDEX_MIRROR is None:
        _INDEX_MIRROR = PostgresIndexStore(available=lambda: catalog_database_available())
    return _INDEX_MIRROR


def index_publisher() -> IndexPublisher:
    """One versioned index registry per process, stored at INDEX_METADATA_PATH."""
    global _INDEX_PUBLISHER
    with _INDEX_LOCK:
        if _INDEX_PUBLISHER is None:
            _INDEX_PUBLISHER = IndexPublisher(
                IndexRegistry(default_metadata_path()),
                store=index_mirror_store(),
            )
        return _INDEX_PUBLISHER


def _document_chunk_rows(filename: str) -> list[dict]:
    """Read back what the vector store really holds for one document.

    The published count comes from the store rather than from a fresh split: a record of
    chunks that were never written is exactly the kind of claim this slice removes.
    """
    reader = getattr(retriever, "document_chunks", None)
    if reader is None:
        return []
    try:
        return list(reader(filename))
    except Exception as exc:
        raise IndexPublicationError(
            "chunks", f"the vector chunks of {filename} could not be read", exc
        ) from exc


def _document_publication(
    *,
    filename: str,
    version: int,
    owner_id: str | None,
    classification: int,
    department: str,
    scope: dict | None = None,
    retirement: bool = False,
) -> DocumentIndexPublication:
    """Describe one document version's index state in catalog coordinates.

    ``scope`` is the same projection an authorization decision reads, so the resource
    version row the mirror writes can never disagree with the attributes the request was
    actually decided on. It defaults to the catalog coordinates already passed in rather
    than to an open scope: a publication built without a scope stays private.
    """
    declared = scope or {}
    shared = {
        "visibility": str(declared.get("visibility") or "private"),
        "department_ids": tuple(
            str(value).strip()
            for value in (declared.get("department_ids") or ())
            if str(value).strip()
        ),
        "resource_status": str(declared.get("status") or "active"),
    }
    if retirement:
        return DocumentIndexPublication(
            filename=filename,
            version=int(version),
            owner_id=owner_id,
            classification=classification,
            department=department,
            retirement=True,
            **shared,
        )
    rows = _document_chunk_rows(filename)
    return DocumentIndexPublication(
        filename=filename,
        version=int(version),
        owner_id=owner_id,
        classification=classification,
        department=department,
        chunks=tuple(str(row.get("content") or "") for row in rows),
        vector_ids=tuple(str(row.get("vector_id") or "") for row in rows),
        content_hash=str((rows[0] if rows else {}).get("hash") or ""),
        **shared,
    )


def _publish_document_index(publication: DocumentIndexPublication) -> dict:
    """Publish one index version, or report that there was nothing to publish.

    A version with no chunks has no index, and a retirement has none by definition; both
    answer with what actually happened instead of dressing it up as a publication. The
    registry and the mirror raise ``IndexPublicationError`` with the stage that failed,
    and the caller turns that into a 500 that does not claim success.
    """
    outcome = index_publisher().apply(publication)
    if outcome is None:
        reason = "no_published_index" if publication.retirement else "no_indexed_chunks"
        logger.warning(
            f"[Index] {publication.resource_version_id}: {reason}; no index version was published"
        )
        return {
            "status": "skipped",
            "reason": reason,
            "index_id": publication.index_id,
            "source_version_id": publication.resource_version_id,
            "chunk_count": 0,
            "mirrored": False,
            "warnings": [],
        }
    return outcome.as_dict()


def _document_index_error(
    filename: str, stage: str, message: str, *, code: str = "index_publish_failed"
):
    """One honest error body for an index publication that did not finish."""
    return HTTPException(
        status_code=500,
        detail=ErrorEnvelope(
            code=code,
            message=message,
            retryable=True,
            details={"filename": filename, "stage": stage},
        ).model_dump(),
    )


@router.post("/upload")
async def upload_document(file: UploadFile = File(...),
                          classification: int = Form(1),
                          department: str = Form(""),
                          request: FastAPIRequest = None):
    """Ingest one knowledge-base document and record who uploaded it.

    ``request`` stays optional so the in-process callers that predate the principal
    remain valid. Without a request there is no subject, and the version is recorded
    as an unowned (legacy) row rather than owned by a guessed user.

    The document scope is decided here rather than accepted from the form: retrieval
    matches a document against the departments of the caller asking, so a document that
    lands without one can never be found by anyone, and a department chosen by the
    client would let a caller publish into somebody else\u2019s results. The uploader''s own
    department is what the datasets and artifacts registries already use.
    """
    principal = principal_from_request(request) if request is not None else None
    owner_id = str(getattr(principal, "user_id", "") or "") or None
    department = str(getattr(principal, "department", "") or "")
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
        # The stored file and its catalog row are kept on purpose. A version that
        # cannot be parsed has to stay visible as failed so its owner or an
        # administrator can remove it; deleting the file and answering 500 made a
        # failed upload indistinguishable from one that never happened.
        _record_uploaded_version(
            principal=principal,
            owner_id=owner_id,
            filename=inspection.display_filename,
            classification=classification,
            department=department,
            storage_path=file_path,
            version=next_version,
            size_bytes=written,
            parse_status="failed",
        )
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
        version_meta = _record_uploaded_version(
            principal=principal,
            owner_id=owner_id,
            filename=inspection.display_filename,
            classification=classification,
            department=department,
            storage_path=file_path,
            version=next_version,
            size_bytes=written,
            parse_status="ready",
        )
        def _publish_upload_index():
            return _publish_document_index(
                _document_publication(
                    filename=inspection.display_filename,
                    version=version_meta["version"],
                    owner_id=owner_id,
                    classification=classification,
                    department=department,
                    scope=_document_resource_scope(inspection.display_filename, version_meta),
                )
            )

        try:
            index_publication = await asyncio.to_thread(_publish_upload_index)
        except IndexPublicationError as exc:
            logger.exception(f"[Docs] index publication failed: {inspection.display_filename}")
            raise _document_index_error(
                inspection.display_filename,
                exc.stage,
                "index publication failed; the stored file and its catalog row remain",
            ) from exc
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
            "size_bytes": version_meta.get("size_bytes"),
            "parse_status": version_meta.get("parse_status", "ready"),
            "owner_id": owner_id,
            "department": department,
            "chunk_count": index_publication.get("chunk_count", 0),
            "index_publication": index_publication,
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
    principal = _document_principal_or_error(request)
    versions = list_document_versions(filename)
    if not versions:
        raise HTTPException(status_code=404, detail="resource_not_found")
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
    version, _decision = _authorize_document_request(request, filename, ACTION_DOWNLOAD)
    file_path = _document_storage_path(version)

    media_type, _ = mimetypes.guess_type(file_path)
    media_type = media_type or "application/octet-stream"
    disposition = "inline" if inline else "attachment"
    return FileResponse(
        file_path,
        filename=os.path.basename(file_path),
        media_type=media_type,
        content_disposition_type=disposition,
        headers=dict(NO_STORE_HEADERS),
    )


@router.get("/documents/{filename}/preview")
async def get_document_preview(
    filename: str,
    request: FastAPIRequest,
    response: FastAPIResponse,
):
    version, _decision = _authorize_document_request(request, filename, ACTION_VIEW)
    file_path = _document_storage_path(version)
    try:
        payload = await asyncio.to_thread(build_document_preview, file_path, filename)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail="unsupported_preview") from exc
    except Exception as exc:
        logger.exception(f"[Docs] preview failed: {filename}")
        raise HTTPException(status_code=500, detail="document_preview_failed") from exc
    response.headers.update(NO_STORE_HEADERS)
    return payload


def _document_delete_before(stored_versions: list[dict]) -> dict:
    """Summarize what a document holds before anything is removed."""
    newest = stored_versions[0] if stored_versions else {}
    return {
        "versions": len(stored_versions),
        "classification": newest.get("classification"),
        "department": newest.get("department"),
        "owner_id": newest.get("owner_id"),
        "parse_status": newest.get("parse_status"),
    }


def _document_delete_error(filename: str, stage: str, message: str, *, code: str = "index_publish_failed"):
    """One honest error body for a delete that did not finish."""
    return _document_index_error(filename, stage, message, code=code)


@router.delete("/documents/{filename}")
async def delete_document(filename: str, request: FastAPIRequest):
    """Retire a document: authorize, roll the index back, clean the disk, audit.

    Each stage reports what it actually did. An index that could not be rolled back
    leaves the document stored and answers ``index_publish_failed``: saying ok while
    the knowledge base still retrieves the file would claim a result this process did
    not produce. Catalog rows go last, so a document that was only partly cleaned
    stays visible and retryable instead of becoming an orphan file.
    """
    version, decision = _authorize_document_request(request, filename, ACTION_DELETE)
    principal = _document_principal_or_error(request)
    scope = _document_resource_scope(filename, version)
    request_id = principal.request_id or None
    stored_versions = list_document_versions(filename)
    before = _document_delete_before(stored_versions)

    def _audit(outcome: str, reason: str, after: dict) -> None:
        record_audit(
            principal,
            ACTION_DELETE,
            outcome,
            filename,
            reason,
            request_id=request_id,
            resource_scope=scope,
            policy_version=decision.policy_version,
            before_summary=before,
            after_summary=after,
        )

    try:
        retriever.delete_document(filename)
    except Exception as exc:
        logger.exception(f"[Docs] vector index rollback failed: {filename}")
        _audit(
            "failed",
            "index_rollback_failed",
            {"deleted": False, "stage": "index_rollback", "error": type(exc).__name__},
        )
        raise _document_delete_error(
            filename, "index_rollback", "document index rollback failed; the document is still stored"
        ) from exc

    from app.agents.tools import rebuild_bm25

    try:
        rebuild_bm25()
    except Exception as exc:
        logger.exception(f"[Docs] keyword index rollback failed: {filename}")
        _audit(
            "failed",
            "index_rollback_failed",
            {"deleted": False, "stage": "keyword_index", "error": type(exc).__name__},
        )
        raise _document_delete_error(
            filename, "keyword_index", "keyword index rollback failed; the document is still stored"
        ) from exc

    newest = stored_versions[0] if stored_versions else (version or {})
    retirement = _document_publication(
        filename=filename,
        version=int(newest.get("version") or 1),
        owner_id=newest.get("owner_id"),
        classification=int(newest.get("classification") or 1),
        department=str(newest.get("department") or ""),
        scope=_document_resource_scope(filename, newest),
        retirement=True,
    )
    try:
        index_retirement = await asyncio.to_thread(_publish_document_index, retirement)
    except IndexPublicationError as exc:
        logger.exception(f"[Docs] index retirement failed: {filename}")
        _audit(
            "failed",
            "index_retire_failed",
            {"deleted": False, "stage": exc.stage, "error": exc.cause_name},
        )
        raise _document_delete_error(
            filename,
            exc.stage,
            "index retirement failed; the document is still catalogued",
        ) from exc

    removed: list[str] = []
    unremoved: list[str] = []
    for item in [*stored_versions, version]:
        storage_path = str(item.get("storage_path") or "")
        if not storage_path or not os.path.exists(storage_path):
            continue
        if storage_path in removed or storage_path in unremoved:
            continue
        try:
            os.remove(storage_path)
            removed.append(storage_path)
        except OSError:
            logger.exception(f"[Docs] stored file could not be removed: {storage_path}")
            unremoved.append(storage_path)

    if unremoved:
        _audit(
            "failed",
            "document_cleanup_incomplete",
            {"deleted": False, "stage": "physical_cleanup", "removed": len(removed), "unremoved": len(unremoved)},
        )
        raise _document_delete_error(
            filename,
            "physical_cleanup",
            "stored files could not be removed; the document is still catalogued",
            code="internal_error",
        )

    delete_document_versions(filename, storage_paths=tuple(removed))
    remaining = list_document_versions(filename)
    after = {
        "deleted": not remaining,
        "stage": "completed",
        "files_removed": len(removed),
        "versions_before": len(stored_versions),
        "catalog_rows_remaining": len(remaining),
        "index_retirement": index_retirement["status"],
    }
    _audit("allowed" if not remaining else "partial", decision.reason_code, after)
    return {
        "status": "ok" if not remaining else "partial",
        "filename": filename,
        "files_removed": len(removed),
        "catalog_rows_remaining": len(remaining),
        "index_retirement": index_retirement,
    }


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
