"""HITL 挂起待办的账本（请求 R13）。

一次挂起写成一行**有终态**的记录，而不是去查询图的瞬时位置：挂起态本身只活在
LangGraph checkpoint 里，``check_interrupt`` 必须先知道 thread_id 才能问一句
（app/agents/orchestrator.py:1152），全仓没有枚举能力，所以审批面板此前没有真话可读。

列端点仍然要复核：这张表是"事件记录"，不是"当前状态"的权威。读侧对每一行调
check_interrupt，对不上就地标 stale——这也是 MemorySaver 降级
（app/agents/orchestrator.py:68-71）重启后图里什么都没有时唯一不至于说谎的办法。

存储后端与 app/storage/sessions.py 一样是过渡形态：PG 就绪时读写
``pending_approvals``（migrations/0008_pending_approvals.sql），否则退到进程内账本。
区别在于**只要真的在跟 PG 说话，表就必须在**：缺表直接 RuntimeError，不再往内存悄悄
降级，因为那会让"面板空了"看起来像"没有待办"。
"""
from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from itertools import count
from typing import Any, Iterable

try:  # pragma: no cover - 驱动缺失时下面所有 PG 分支都不会被走到
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None

TABLE = "pending_approvals"
# 状态名在这里是具名常量而不是散落的字面量：0008 上有 CHECK 约束钉着同一组词，路由
     # 侧写错一个字母就会在真库上撞约束，而在内存后端里悄悄"成功"。
AWAITING = "awaiting"
RESUMED = "resumed"
REFUSED = "refused"
ABANDONED = "abandoned"
STALE = "stale"
DECIDED_STATUSES = frozenset({RESUMED, REFUSED, ABANDONED})
ALL_STATUSES = (AWAITING, RESUMED, REFUSED, ABANDONED, STALE)

_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")
_DEFAULT_TTL_HOURS = 24.0
_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731 - 只有一处语义，测试按整体替换


@dataclass
class PendingApprovalRecord:
    """一行挂起记录。字段与 0008 的列一一对应，parked_steps 不是 blob 而是数组。"""

    session_id: str
    owner_user_id: str
    parked_steps: list[str] = field(default_factory=list)
    status: str = AWAITING
    request_id: str = ""
    trace_id: str = ""
    task_id: str = ""
    created_at: str = ""
    expires_at: str = ""
    decided_at: str | None = None


_MEM_ROWS: dict[int, PendingApprovalRecord] = {}
_MEM_SEQUENCE = count(1)
_LOCK = threading.Lock()


def _database_available() -> bool:
    auth_module = sys.modules.get("app.common.auth")
    return bool(auth_module and getattr(auth_module, "_db_ready", False))


def _conn():
    if psycopg is None:
        raise RuntimeError("PostgreSQL driver is unavailable")
    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _ttl_window() -> timedelta:
    raw = os.getenv("PENDING_APPROVAL_TTL_HOURS", str(_DEFAULT_TTL_HOURS))
    try:
        hours = float(raw)
    except ValueError:
        hours = _DEFAULT_TTL_HOURS
    if hours <= 0:
        hours = _DEFAULT_TTL_HOURS
    return timedelta(hours=hours)


def _is_open(record: PendingApprovalRecord, at: datetime) -> bool:
    if record.status != AWAITING:
        return False
    try:
        expires = datetime.fromisoformat(record.expires_at)
    except (TypeError, ValueError):
        return True
    return expires > at


def _require_table(conn) -> None:
    row = conn.execute("SELECT to_regclass('public.pending_approvals') AS table_name").fetchone()
    if not row or row["table_name"] is None:
        raise RuntimeError(
            "pending_approvals table is required; run migrations first "
            "(migrations/0008_pending_approvals.sql)"
        )


def _record_from_row(row: dict) -> PendingApprovalRecord:
    steps = row.get("parked_steps")
    if isinstance(steps, str):
        import json as _json

        steps = _json.loads(steps)
    return PendingApprovalRecord(
        session_id=str(row.get("session_id") or ""),
        owner_user_id=str(row.get("owner_user_id") or ""),
        parked_steps=[str(step) for step in (steps or [])],
        status=str(row.get("status") or AWAITING),
        request_id=str(row.get("request_id") or ""),
        trace_id=str(row.get("trace_id") or ""),
        task_id=str(row.get("task_id") or ""),
        created_at=str(row.get("created_at") or ""),
        expires_at=str(row.get("expires_at") or ""),
        decided_at=str(row["decided_at"]) if row.get("decided_at") else None,
    )


def record_awaiting(
    session_id: str,
    owner_user_id: str,
    parked_steps: Iterable[str],
    *,
    request_id: str = "",
    trace_id: str = "",
    task_id: str = "",
    expires_at: str | None = None,
) -> PendingApprovalRecord:
    """为一次挂起开一行 awaiting；同一会话上未闭合的旧行先判 stale。

    旧行必须先闭合再插入：0008 上有 ``..._open_session_idx`` 的 partial unique 索引，
    一个会话同时只允许一条 awaiting，重试/续跑才不会撞约束。
    """
    session_id = str(session_id or "").strip()
    owner_user_id = str(owner_user_id or "").strip()
    steps = [str(step) for step in (parked_steps or []) if str(step).strip()]
    if not session_id or not owner_user_id or not steps:
        raise ValueError("session_id, owner_user_id and at least one parked step are required")

    now = _NOW()
    created_at = now.isoformat()
    until = expires_at or (now + _ttl_window()).isoformat()
    record = PendingApprovalRecord(
        session_id=session_id,
        owner_user_id=owner_user_id,
        parked_steps=steps,
        status=AWAITING,
        request_id=str(request_id or ""),
        trace_id=str(trace_id or ""),
        task_id=str(task_id or ""),
        created_at=created_at,
        expires_at=until,
    )

    if not _database_available():
        with _LOCK:
            _supersede_open_in_memory(session_id)
            _MEM_ROWS[next(_MEM_SEQUENCE)] = record
        return record

    with _conn() as conn:
        _require_table(conn)
        conn.execute(
            "UPDATE pending_approvals SET status = %s, decided_at = NOW() "
            "WHERE session_id = %s AND status = %s",
            (STALE, session_id, AWAITING),
        )
        conn.execute(
            "INSERT INTO pending_approvals "
            "(session_id, owner_user_id, parked_steps, status, request_id, trace_id, task_id, "
            " created_at, expires_at) "
            "VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)",
            (
                record.session_id,
                record.owner_user_id,
                __import__("json").dumps(record.parked_steps),
                AWAITING,
                record.request_id or None,
                record.trace_id or None,
                record.task_id or None,
                created_at,
                until,
            ),
        )
    return record


def _supersede_open_in_memory(session_id: str) -> None:
    for record in _MEM_ROWS.values():
        if record.session_id == session_id and record.status == AWAITING:
            record.status = STALE
            record.decided_at = _NOW().isoformat()


def mark_status(session_id: str, status: str) -> PendingApprovalRecord | None:
    """把一个会话**当前未闭合**的挂起行改成终态；没有可改的行就返回 None。

    只碰还在 awaiting 且没到期的行：过期的挂起不该还能被批准，那会写出一条
    decided_at 晚于 expires_at 的自相矛盾记录。
    """
    session_id = str(session_id or "").strip()
    if status not in ALL_STATUSES or status == AWAITING:
        raise ValueError(f"unsupported pending approval status: {status}")

    if not _database_available():
        with _LOCK:
            open_row = _latest_open_in_memory(session_id)
            if open_row is None:
                return None
            open_row.status = status
            open_row.decided_at = _NOW().isoformat()
            return open_row

    with _conn() as conn:
        _require_table(conn)
        conn.execute(
            "UPDATE pending_approvals SET status = %s, decided_at = NOW() "
            "WHERE session_id = %s AND status = %s AND expires_at > NOW()",
            (status, session_id, AWAITING),
        )
        row = conn.execute(
            "SELECT session_id, owner_user_id, parked_steps, status, request_id, trace_id, "
            "task_id, created_at, expires_at, decided_at FROM pending_approvals "
            "WHERE session_id = %s ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    return _record_from_row(dict(row)) if row else None


def _latest_open_in_memory(session_id: str) -> PendingApprovalRecord | None:
    now = _NOW()
    candidates = [
        record
        for record in _MEM_ROWS.values()
        if record.session_id == session_id and _is_open(record, now)
    ]
    return max(candidates, key=lambda record: record.created_at) if candidates else None


def open_items(
    *,
    owner_user_id: str | None = None,
    session_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[PendingApprovalRecord]:
    """未闭合（awaiting 且未过期）的行，按挂起时间从新到旧。

    ``limit`` 默认**不设限**：分页是读端点的代价策略（`GET /hitl/pending` 每列一行就要向图
    复核一次 ``check_interrupt``），账本层自己不需要页。传了就把页边界**下推进 SQL 的
    LIMIT/OFFSET**，而不是把整表读回来再切片——后者只是把"有上限"说成半句真话。
    不传时 SQL 一字不变，免得内部读侧被这次的接口改动带着漂移。
    """
    bounded = None if limit is None else max(0, int(limit))
    start = max(0, int(offset))

    if not _database_available():
        now = _NOW()
        with _LOCK:
            records = [
                record
                for record in _MEM_ROWS.values()
                if _is_open(record, now)
                and (owner_user_id is None or record.owner_user_id == str(owner_user_id))
                and (session_id is None or record.session_id == str(session_id))
            ]
        ordered = sorted(records, key=lambda record: record.created_at, reverse=True)
        return ordered[start : (start + bounded) if bounded is not None else None]

    sql = (
        "SELECT session_id, owner_user_id, parked_steps, status, request_id, trace_id, "
        "task_id, created_at, expires_at, decided_at FROM pending_approvals "
        "WHERE status = %s AND expires_at > NOW()"
    )
    params: list[Any] = [AWAITING]
    if owner_user_id is not None:
        sql += " AND owner_user_id = %s"
        params.append(str(owner_user_id))
    if session_id is not None:
        sql += " AND session_id = %s"
        params.append(str(session_id))
    sql += " ORDER BY created_at DESC"
    if bounded is not None:
        sql += " LIMIT %s"
        params.append(bounded)
    if start:
        sql += " OFFSET %s"
        params.append(start)

    with _conn() as conn:
        _require_table(conn)
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [_record_from_row(dict(row)) for row in rows]


def get_row(session_id: str) -> PendingApprovalRecord | None:
    """某个会话最近一行（含已闭合的），供复核与排障使用。"""
    session_id = str(session_id or "").strip()
    if not _database_available():
        with _LOCK:
            candidates = [record for record in _MEM_ROWS.values() if record.session_id == session_id]
        if not candidates:
            return None
        return max(candidates, key=lambda record: record.created_at)

    with _conn() as conn:
        _require_table(conn)
        row = conn.execute(
            "SELECT session_id, owner_user_id, parked_steps, status, request_id, trace_id, "
            "task_id, created_at, expires_at, decided_at FROM pending_approvals "
            "WHERE session_id = %s ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    return _record_from_row(dict(row)) if row else None


def _all_rows() -> list[PendingApprovalRecord]:
    """进程内账本的全部行；仅排障与测试可见，PG 模式下没有这个全景。"""
    with _LOCK:
        return list(_MEM_ROWS.values())
