"""HITL 挂起待办的账本（请求 R13）。

一次挂起写成一行**有终态**的记录，而不是去查询图的瞬时位置：挂起态本身只活在
LangGraph checkpoint 里，``check_interrupt`` 必须先知道 thread_id 才能问一句
（app/agents/orchestrator.py:1152），全仓没有枚举能力，所以审批面板此前没有真话可读。

列端点仍然要复核：这张表是"事件记录"，不是"当前状态"的权威。读侧对每一行调
check_interrupt，对不上就地标 stale——这也是开发态 MemorySaver 降级
（app/agents/orchestrator.py 的 _fail_checkpointer_loudly，R98）重启后图里什么都没有时唯一不至于说谎的办法。
注：R98 之后生产环境不再允许这种降级（拒绝启动），所以"重启后图里什么都没有"只在开发态还可能发生。

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
#: R175：图自己跑挂了（internal_error）或跑超时了（task_timeout）。这一格既不是员工驳回
#: （refused），也不是员工按了停止（abandoned），更不是"图不再确认这次挂起"（stale）——把
#: 一次故障写成那三格里的任何一格，都是替员工说了一句他没说的话。裁定与 app/api/v1/chat.py
#: 取消腿的「停止 != 拒绝，写 abandoned 绝不写 refused」是同一条，不许开倒车。
FAILED = "failed"
DECIDED_STATUSES = frozenset({RESUMED, REFUSED, ABANDONED, FAILED})
ALL_STATUSES = (AWAITING, RESUMED, REFUSED, ABANDONED, STALE, FAILED)
#: 🔴 0008 的 CHECK 只认前五枚，``failed`` 不在其中，而 migrations/** 在 R175 写域之外
#: （同一处曾停着 R172 的 ``declared_lane``：0012 补了列、R187 补了绑值；``failed`` 至今没有
#: 对应迁移）。结论：PG 腿今天写不进这一格 —— ``mark_status``
#: 会撞 ``pending_approvals_status_check``，由 ``_decide_pending_approval`` 记 exception，
#: 那一行留在 awaiting。本机文件账能闭合，PG 那一半是**具名欠账**，不是"顺手拿 refused
#: 顶数"的理由。缺口由 tests/test_r175_failed_turn.py 逐枚钉住：多一枚漏一枚都会红。
PG_STATUSES = frozenset({AWAITING, RESUMED, REFUSED, ABANDONED, STALE})

_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")
_DEFAULT_TTL_HOURS = 24.0
_NOW = lambda: datetime.now(timezone.utc)  # noqa: E731 - 只有一处语义，测试按整体替换


@dataclass
class PendingApprovalRecord:
    """一行挂起记录。字段与台账列一一对应（0008 的十一枚 + 0012 的 ``declared_lane``）；parked_steps 不是 blob 而是数组。"""

    session_id: str
    owner_user_id: str
    parked_steps: list[str] = field(default_factory=list)
    #: R172：挂起**那一轮**调用方声明的档位。它是"这一轮的档是谁定的"这句话在批准后
    #: 续跑轮里唯一的凭据 —— 原始请求体与图内 configurable 都随那一轮流结束了，只有
    #: 随这行账本存下来才跨得过 HITL 那道门。
    #:
    #: 列由 0012 送进台账，R187 起 PG 分支的一枚 INSERT 与三枚显式列表 SELECT 一起绑它：
    #: 写得进也读得回。取值只有 ""／qa／analysis／report 四条，唯一通路是 app.agents.nodes
    #: 的 ``normalize_declared_lane``（未知拼写当场硬失败）；本层不猜、不校验、不另起第二份
    #: 归一化。读不到这一格的行（R172 之前挂起的旧行、0012 之前的库）一律回空串，续跑轮
    #: 于是读成"沿用一次没有记录的声明"，绝不许被补成 explicit —— 落点见 resumed_lane 与
    #: app/api/v1/chat.py 的 _parked_declaration。
    declared_lane: str = ""
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
    return _within_action_window(record, at)


def _within_action_window(record: PendingApprovalRecord, at: datetime) -> bool:
    """``expires_at`` 之前这一行还落在「当时还说得出口」的窗口里。

    读不懂到期时间就当还在窗口内：宁可多列一行让人核对，也不替账本宣布它已经过去了。
    抽出来是因为 R175 之后有两个读侧要用同一个窗口 —— ``awaiting`` 问的是「还能不能批」，
    ``failed`` 问的是「这一句『你批过而那一轮失败了』还算不算新话」，两者用的是同一格
    ``expires_at``，一处过滤过期一处不过滤迟早漂。
    """
    try:
        expires = datetime.fromisoformat(record.expires_at)
    except (TypeError, ValueError):
        return True
    return expires > at


class PendingApprovalStoreMissing(RuntimeError):
    """账本表不在——镜像比库新、``0008`` 没跑时唯一诚实的说法。

    故意做成 ``RuntimeError`` 的子类而不是替换它：写侧既有断言钉的是基类，具名化只许
    加一层，不许把旧断言弄红。存在的意义是让**读端点**能只接这一种错：把任何
    RuntimeError 都翻成 503，等于替真正的 bug 打掩护（驱动缺失也会走这条路）。
    """


def _require_table(conn) -> None:
    row = conn.execute("SELECT to_regclass('public.pending_approvals') AS table_name").fetchone()
    if not row or row["table_name"] is None:
        raise PendingApprovalStoreMissing(
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
        # 读到空串与压根读不到这一格（0012 之前的库、手搓的行字典）必须落同一个值：
        # 这正是上面那张兼容表要的形状，不是"忘了写"。
        declared_lane=str(row.get("declared_lane") or ""),
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
    declared_lane: str = "",
) -> PendingApprovalRecord:
    """为一次挂起开一行 awaiting；同一会话上未闭合的旧行先判 stale。

    旧行必须先闭合再插入：0008 上有 ``..._open_session_idx`` 的 partial unique 索引，
    一个会话同时只允许一条 awaiting，重试/续跑才不会撞约束。

    ``declared_lane``（R172）是挂起那一轮调用方声明的档位，由调用方走
    ``declared_lane_from_config`` → ``normalize_declared_lane`` 归一过后才交进来
    （""／qa／analysis／report 四值之一）；本层不猜、不校验、不替谁把它补成任何一档。
    R187 起 PG 分支随 INSERT 一起写这一格，绑的就是下面那枚 ``record.declared_lane`` ——
    与内存分支同一枚对象，不是第二份读数。🔴 前置条件是库已过 0012：没过的那台库上这一发
    会撞 UndefinedColumn，被 ``_record_pending_approval`` 吞掉之后**审批面板会一条待办都不
    剩**；这比绑值之前"照写不误、读回永远空串"更响，也正是它该有的音量。
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
        declared_lane=str(declared_lane or ""),
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
            " created_at, expires_at, declared_lane) "
            "VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)",
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
                record.declared_lane,
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

    R175 之后 ``FAILED`` 也在可写的终态里，而它恰恰是**唯一一枚 PG 写不进去**的：
    0008 的 ``pending_approvals_status_check`` 不认它，PG 分支的 UPDATE 会撞约束并由
    调用方 ``_decide_pending_approval`` 记 exception（那一行于是留在 awaiting）。本机
    文件账这一半是真闭合；PG 那一半是具名欠账，补法是一枚 migrations 脚本放开 CHECK，
    不是在这里换用 refused/abandoned 顶数。缺口由 tests/test_r175_failed_turn.py 钉住。
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
            "task_id, created_at, expires_at, decided_at, declared_lane FROM pending_approvals "
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


def _items_with_status(
    status: str,
    *,
    owner_user_id: str | None = None,
    session_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[PendingApprovalRecord]:
    """按状态取还在行动窗口内的行，页边界下推 SQL。WHERE 只有一份。

    ``open_items``（awaiting）与 ``failed_items``（failed）读的是同一张账本，差别只有
    那一格 status。两处各写一套 SQL，迟早漂成一处过滤过期、一处不过滤 —— 而「已闭合的
    失败行会不会永远挂在屏上」正是由这一格窗口决定的。
    """
    bounded = None if limit is None else max(0, int(limit))
    start = max(0, int(offset))

    if not _database_available():
        now = _NOW()
        with _LOCK:
            records = [
                record
                for record in _MEM_ROWS.values()
                if record.status == status
                and _within_action_window(record, now)
                and (owner_user_id is None or record.owner_user_id == str(owner_user_id))
                and (session_id is None or record.session_id == str(session_id))
            ]
        ordered = sorted(records, key=lambda record: record.created_at, reverse=True)
        return ordered[start : (start + bounded) if bounded is not None else None]

    sql = (
        "SELECT session_id, owner_user_id, parked_steps, status, request_id, trace_id, "
        "task_id, created_at, expires_at, decided_at, declared_lane FROM pending_approvals "
        "WHERE status = %s AND expires_at > NOW()"
    )
    params: list[Any] = [status]
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
    return _items_with_status(
        AWAITING,
        owner_user_id=owner_user_id,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )


def failed_items(
    *,
    owner_user_id: str,
    session_id: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[PendingApprovalRecord]:
    """R175：闭合为 ``failed`` 的那一轮 —— 员工批过板，而系统没把那轮跑完。

    这一份读侧是给「审批与待办」那一屏的一句话用的：待办行闭合之后就不在 ``open_items``
    里了，如果屏上只认待办，那一笔会**无声消失** —— 员工看到的是「我明明点了同意，它自己
    没了」。所以这一格必须与待办一起回，句子上屏才有据可依，而不是前端凭一次请求的成败猜。

    两条写死的规矩：
    - **绝不向图复核**。``check_interrupt`` 问的是「现在还挂着吗」，而这一行的答案本来就
      是「没挂着了」；拿它去问，``GET /hitl/pending`` 的复核腿会把失败行就地判成
      ``stale``（"已作废"）—— 那正是本单要消灭的那句话。
    - 只到 ``expires_at`` 为止。过期的失败行仍留在账本与审计里（一行都不删），但不再占用
      屏上那一格：这与「过期挂起不再算待办」是同一条既有口径，不是新造的失忆。

    ``owner_user_id`` 是必填：归属过滤 fail-closed，不带归属的读等于读全司。
    PG 腿今天读得到 ``failed`` 行（读不受 CHECK 约束），写不进去 —— 见模块常量段。
    """
    return _items_with_status(
        FAILED,
        owner_user_id=str(owner_user_id or ""),
        session_id=session_id,
        limit=limit,
        offset=offset,
    )


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
            "task_id, created_at, expires_at, decided_at, declared_lane FROM pending_approvals "
            "WHERE session_id = %s ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    return _record_from_row(dict(row)) if row else None


def _all_rows() -> list[PendingApprovalRecord]:
    """进程内账本的全部行；仅排障与测试可见，PG 模式下没有这个全景。"""
    with _LOCK:
        return list(_MEM_ROWS.values())
