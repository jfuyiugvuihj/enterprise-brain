"""Reliable Redis queue primitives.

This module is deliberately separate from the legacy queue adapter until the worker
integration contract is reviewed. It provides reserve/ack, lease expiry with an
in-run renewal heartbeat (R227), retry, dead-letter, idempotency, cancellation,
explicit status transitions,
and passive queue-pressure readings (depth plus declared capacity) for monitoring.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any


class QueueConnectionError(RuntimeError):
    """Raised when the reliable queue cannot establish a verified Redis connection."""

    code = "queue_unavailable"


#: R155: 部署侧声明的排队上限。这一枚常量只产生「看得见」的读数，不产生任何执法——
#: 「满了怎么办」（拒收 / 排队上限 / 降级）是业主裁定（跟进单 §79 三 R155），今天入队照旧全收。
QUEUE_CAPACITY_ENV = "QUEUE_MAX_PENDING"
#: capacity_source 的四枚取值：报出这枚容量从哪来，以及「读不到」算谁的。
CAPACITY_SOURCE_ENV = f"env:{QUEUE_CAPACITY_ENV}"
CAPACITY_SOURCE_EXPLICIT = "constructor"
CAPACITY_SOURCE_NOT_CONFIGURED = "not_configured"
CAPACITY_SOURCE_INVALID = "invalid_configuration"
#: depth_source: 深度一律现读 Redis 服务端的 LLEN，多进程/多副本读的是同一份账。
DEPTH_SOURCE_REDIS_LLEN = "redis_llen"

#: ---- R227：处理租约的续拍与丢弃原因码 -------------------------------------------
#:
#: 租约从前只在 `reserve()` 写过一次（TTL = lease_seconds，生产默认 300 s），运行途中
#: 全树零续租点。09-25 总控亲测：一档报告题跑完 311 s > 300 s，任务还在正常跑就被自己
#: 的持有者判成"租约已丢失"，1519 字正文在 `complete()` 门口当场丢弃。那一枚判定读的是
#: "起跑之后过了多久"，不是"持有者还活着吗"——心跳把语义修回后者。
#:
#: 间隔取 lease_seconds / DIVISOR：一份租约的有效期内至少落三拍，任何一拍没赶上（GIL
#: 卡顿、瞬时断连）后面还有两拍兜着。下限 1 s 是给测试里那种 2 s 短租约用的：不许把
#: 心跳变成 busy loop。
LEASE_HEARTBEAT_DIVISOR = 3
LEASE_HEARTBEAT_MIN_INTERVAL_SECONDS = 1.0
#: 续租的墙钟保险丝：一条任务最多让心跳续这么多秒，到点停手让租约自然过期，交给
#: `requeue_expired` 回收。没有这条线，一个卡死但没崩的 worker 就能无限期把消息占在
#: 处理表上——那等于心跳把租约机制存在的理由吃掉了。代价口径见 R227 交工报告：
#: 崩溃检测照旧是 lease_seconds 量级，"活着但卡死"的检测从 lease_seconds 变成这一枚。
LEASE_MAX_RENEW_SECONDS_ENV = "QUEUE_LEASE_MAX_RENEW_SECONDS"
LEASE_MAX_RENEW_SECONDS_DEFAULT = 3600
#: 保险丝的天花板：坏配置一律回落到默认值，不许把上限读成"无限"。
LEASE_MAX_RENEW_SECONDS_CEILING = 86400
#: 稳定码：结果被丢弃这件事的成因。只进队列账本（`failure()["last_error"]`）与日志，
#: 不进用户正文（R16 同口径）。
RESULT_DISCARDED = "result_discarded"
DISCARD_REASON_CANCELLED = "cancelled"
DISCARD_REASON_LEASE_LOST = "lease_lost"
#: R254 判据①：队列里「在等人批准」的那一轮从今天起有自己的一枚状态词。
#: 为什么非新增不可：09-25 那扇窗的 20 行终态里 `awaiting_hitl=True` 有 12 枚，其中 11 枚
#: 把同一句 37 字挂起文案当正文交回、队列侧照报 `final=done`——客户读到的是「跑完了」，
#: 真相是「一步都没往下走」。那是谎报终态，不是慢。
#: 🔴 新增一枚状态词有三处必须同批改口，缺一处就是假契约：
#:   1. `docs/api/contract-v1.md` 的 `## Long Task Status`：那枚同步钉用 AST 逐枚比对词表，
#:      且只认「往 status 键写一枚字符串字面量」这一种形状，写成常量会被记成 blind spot；
#:   2. 前端停表名单 `frontend/src/components/ChatPanel.vue::QUEUE_SETTLED`；
#:   3. 量具停表 `scripts/eval_transport_ask_v2.py::_poll_queue`。
#: 后两枚在 R254 写域之外，已作为转出项写进交工报告。本仓那枚「词表一字未加」的钉
#:（`tests/test_r227_discard_is_honest.py`）收窄成「R227 的丢弃路径没加字」——它本来要护的
#: 就是这件事，不是替后人预先批准或否决每一个新状态词。
AWAITING_APPROVAL = "awaiting_approval"
#: 结构化终态载荷的结构名。redis 里在位的旧行没有这一格，读回来时据此走兼容路径。
TERMINAL_SCHEMA = "queue-terminal-v1"
#: 队列只认上面那两枚终态语义；第三枚由 `_terminal_awaits_approval` 当场拒，不许静默降级
#: 回 `done`。构造点（`app/api/v1/chat.py::build_queue_terminal`）与落库点之间不存在第二份词表。

#: 结构化终态的两枚语义（R254 判据①②④）。取值由 `app/api/v1/chat.py::build_queue_terminal`
#: 独家构造，队列只认这两枚，别的一律拒——「载荷说在等人、状态键说已跑完」这种自相矛盾的
#: 终态就是这么被挡在门外的。
TERMINAL_STATE_ANSWERED = "answered"
TERMINAL_STATE_AWAITING_APPROVAL = "awaiting_approval"
#: 终态语义 -> 队列状态键。`answered` 走的还是 `ack()` 原本写的那枚 `done`，一个字都没改。
TERMINAL_STATE_TO_STATUS = {
    TERMINAL_STATE_ANSWERED: "done",
    TERMINAL_STATE_AWAITING_APPROVAL: AWAITING_APPROVAL,
}
#: 结构化终态读回来时的三种可能：键不在位（本单之前的旧行）、在位且解得开、在位但解不开。
TERMINAL_ABSENT = "absent"
TERMINAL_OK = "ok"
TERMINAL_UNREADABLE = "unreadable"
#: ==================== R585：死终态那一笔账 ====================
#: 状态键上那枚「彻底失败」的词。🔴 写入处必须仍旧是字符串字面量（`tests/test_r232_queue_status_vocabulary_sync.py` 的 AST 只认「往 status 键写一枚字面量」这一种形状，写成常量会落进它的 blind spot），所以这一枚常量只给**读侧**比对用；它与那处字面量逐字相等由本单的钉看着。
DEAD_STATUS = "dead"
#: 死终态在可读面上的结构名。它与 `TERMINAL_SCHEMA` 是两枚不同的形状：成功终态那一份键集合已由 R254 冻结（R585 判据②一字不改），失败这一份只说「为什么失败」，绝不冒充成功形状。这一格不是错误码——稳定码的唯一词表是 `app/agents/contracts.py::ErrorEnvelope.code`。
DEAD_TERMINAL_SCHEMA = "queue-dead-v1"
#: 队列账本（message 键那本 JSON）里那一笔终态判定的键名。只在**真落 dead 的那一次**写入，形状 `{"reason": <交给队列的原始文本>, "retryable": <调用方的终局判定>}`。它是 R585 判据③那条分家的唯一凭据：`attempts` 与 `max_attempts` 反推不出它——一枚「名额恰好用完、且契约又判了不可重试」的行，两种成因在这两个数上一模一样。
DEAD_VERDICT_LEDGER_KEY = "dead_verdict"

#: R558 判据①：队列道逐字片段的**增量投递面**接在既有轮询面上——不新开路由、不加状态词、
#: 不动终态帧。worker 每攒够这么多片、或距上一发汇流超过这么多秒，就把这一截字打成一批
#: ``RPUSH`` 进片段表；客户端每 3 s 轮一次，所以「递增」这件事量的就是这两枚阈值本身。
#: 阈值刻意不做成 env：把投递节奏交给配置，等于允许「同一轮在不同机器上递增性不同」的口径。
PIECE_FLUSH_PIECES = 8
PIECE_FLUSH_SECONDS = 1.0
#: 片段表里最多存这么多批。超了就停止存正文、只把停止这件事如实报进读数（``truncated``）：
#: 增量面截不动终态帧，客户端到终态照旧拿完整正文，缺的只是「逐片长出来」那一截表演。
#: 不静默丢、也不把它读成「一个片段都没有」——判据④ 要的就是这两个数分得开。
PIECE_BATCH_LIMIT = 1024
#: 一批的结构名。读回来先认它，认不出就按 ``unreadable`` 说，不猜形状。
PIECE_BATCH_SCHEMA = "queue-piece-batch-v1"
#: 片段读数的三态与终态读数同形：键不在位（这一轮一枚都没汇出来）／在位解得开／
#: 在位解不开（半截 JSON、被人手改过、换代留下的异形）。第三态宁缺毋造。
PIECE_ABSENT = "absent"
PIECE_OK = "ok"
PIECE_UNREADABLE = "unreadable"


def _terminal_awaits_approval(terminal: dict[str, Any] | None) -> bool:
    """这枚终态是不是「在等人批准」。读不懂就当场 raise，不许猜、也不许退回 `done`。"""
    if terminal is None:
        return False
    state = str(terminal.get("terminal_state") or "")
    if state not in TERMINAL_STATE_TO_STATUS:
        raise ValueError(f"unknown queue terminal_state: {state!r}")
    return TERMINAL_STATE_TO_STATUS[state] == AWAITING_APPROVAL


def parse_queue_capacity(raw: Any, *, source: str = CAPACITY_SOURCE_ENV) -> tuple[int | None, str]:
    """把配置里的排队上限读成一枚容量读数；读不懂就报「不知道」。

    不拿 0 冒充「没有上限」，也不拿默认值冒充「还空着」——那两种糊法都会让「队列已满」
    重新变回一个编出来的数。读不到时返回 (None, 原因)，由读数面原样上报成 null。
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        return None, CAPACITY_SOURCE_NOT_CONFIGURED
    try:
        value = int(text)
    except ValueError:
        return None, CAPACITY_SOURCE_INVALID
    if value <= 0:
        return None, CAPACITY_SOURCE_INVALID
    return value, source


def lease_renew_budget(raw: Any = None) -> float:
    """续租保险丝的秒数：没声明、读不懂、不为正、超出天花板，一律回落到默认值。

    坏配置的方向刻意是"退回 3600 s"而不是"取消上限"：一句打错的 env 不许把幽灵任务
    窗口拉成无限——那正是本单要修的谎报的另一副面孔。
    """
    text = (os.getenv(LEASE_MAX_RENEW_SECONDS_ENV, "") if raw is None else str(raw)).strip()
    if not text:
        return float(LEASE_MAX_RENEW_SECONDS_DEFAULT)
    try:
        value = float(text)
    except ValueError:
        return float(LEASE_MAX_RENEW_SECONDS_DEFAULT)
    if not 0 < value <= LEASE_MAX_RENEW_SECONDS_CEILING:
        return float(LEASE_MAX_RENEW_SECONDS_DEFAULT)
    return value


@dataclass(frozen=True)
class QueueMessage:
    request_id: str
    payload: dict[str, Any]
    attempts: int = 0


class ReliableQueue:
    def __init__(
        self,
        redis_client,
        *,
        name: str = "enterprise-brain:tasks",
        lease_seconds: int = 300,
        max_attempts: int = 3,
        idempotency_ttl: int = 86400,
        result_ttl: int = 1800,
        capacity: int | None = None,
        capacity_source: str = CAPACITY_SOURCE_EXPLICIT,
    ):
        if (
            not name
            or lease_seconds <= 0
            or max_attempts <= 0
            or idempotency_ttl <= 0
            or result_ttl <= 0
        ):
            raise ValueError("invalid queue configuration")
        if capacity is not None and (
            isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0
        ):
            #: 容量只接受「正整数」或「不知道」两种形态；0、负数、字符串一律当场拒，
            #: 免得半吊子配置把 saturated 变成一枚看着像真数的假读数。
            raise ValueError("invalid queue configuration")
        self.redis = redis_client
        self.name = name.rstrip(":")
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.idempotency_ttl = idempotency_ttl
        self.result_ttl = result_ttl
        self.capacity = capacity
        #: 容量与来源必须成对：capacity 是空的而来源写 constructor 是句假话。
        self.capacity_source = (
            CAPACITY_SOURCE_NOT_CONFIGURED
            if capacity is None and capacity_source == CAPACITY_SOURCE_EXPLICIT
            else capacity_source
        )

    @property
    def pending_key(self) -> str:
        return f"{self.name}:pending"

    @property
    def processing_key(self) -> str:
        return f"{self.name}:processing"

    @property
    def dead_key(self) -> str:
        return f"{self.name}:dead"

    def _message_key(self, request_id: str) -> str:
        return f"{self.name}:message:{request_id}"

    def _status_key(self, request_id: str) -> str:
        return f"{self.name}:status:{request_id}"

    def _result_key(self, request_id: str) -> str:
        return f"{self.name}:result:{request_id}"

    def _lease_key(self, request_id: str) -> str:
        return f"{self.name}:lease:{request_id}"

    def _terminal_key(self, request_id: str) -> str:
        return f"{self.name}:terminal:{request_id}"

    def _idempotency_key(self, key: str) -> str:
        return f"{self.name}:idempotency:{key}"

    def _pieces_key(self, request_id: str) -> str:
        return f"{self.name}:pieces:{request_id}"

    def _cancel_key(self, request_id: str) -> str:
        return f"{self.name}:cancel:{request_id}"

    def enqueue(self, payload: dict[str, Any], idempotency_key: str) -> QueueMessage:
        key = (idempotency_key or "").strip()
        if not key:
            raise ValueError("idempotency_key is required")
        existing = self.redis.get(self._idempotency_key(key))
        if existing:
            request_id = existing.decode() if isinstance(existing, bytes) else str(existing)
            message = self.redis.get(self._message_key(request_id))
            if message:
                data = json.loads(message)
                return QueueMessage(request_id, data["payload"], int(data.get("attempts", 0)))

        request_id = uuid.uuid4().hex
        body = {"request_id": request_id, "payload": payload, "attempts": 0, "enqueued_at": time.time()}
        serialized = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        self.redis.set(self._idempotency_key(key), request_id, ex=self.idempotency_ttl)
        self.redis.set(self._message_key(request_id), serialized)
        self.redis.set(self._status_key(request_id), "queued")
        self.redis.rpush(self.pending_key, request_id)
        return QueueMessage(request_id, payload, 0)

    def reserve(self, timeout: int = 0) -> QueueMessage | None:
        if timeout == 0:
            request_id = self.redis.rpoplpush(self.pending_key, self.processing_key)
        else:
            request_id = self.redis.brpoplpush(self.pending_key, self.processing_key, timeout=timeout)
        if request_id is None:
            return None
        if isinstance(request_id, bytes):
            request_id = request_id.decode()
        if self.is_cancelled(request_id):
            self.redis.lrem(self.processing_key, 1, request_id)
            self.redis.delete(self._lease_key(request_id))
            self.redis.set(self._status_key(request_id), "cancelled")
            return None
        raw = self.redis.get(self._message_key(request_id))
        if not raw:
            self.redis.lrem(self.processing_key, 1, request_id)
            self.redis.set(self._status_key(request_id), "failed")
            return None
        data = json.loads(raw)
        attempts = int(data.get("attempts", 0)) + 1
        data["attempts"] = attempts
        data["reserved_at"] = time.time()
        self.redis.set(self._message_key(request_id), json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        self.redis.set(self._status_key(request_id), "processing")
        self.redis.set(self._lease_key(request_id), "1", ex=self.lease_seconds)
        return QueueMessage(request_id, data["payload"], attempts)

    def _lease_lost(self, request_id: str) -> bool:
        """True when this worker no longer holds the processing lease.

        租约按 request_id 记账而非按持有者记账，因此这里只能判断“租约是否还在”，
        无法区分持有者；跨持有者的令牌围栏仍是已知限制。
        """
        return not bool(self.redis.exists(self._lease_key(request_id)))

    def renew_lease(self, request_id: str) -> bool:
        """把还在手上的处理租约续满；租约已经不在了就返回 False，绝不复活它。

        Redis 的 `EXPIRE` 对不存在的键返回 0，这一枚语义正是本单要的：任务一旦被
        `requeue_expired` 收回或改派，上一任再想续也续不回来。改用 `SET ... EX` 续
        会把这道保护踩平——那等于两任持有者同时声称在跑同一条消息，而账上只有后写的
        那一份租约。（跨持有者的令牌围栏仍是已知限制，本方法不假装解决它。）
        """
        return bool(self.redis.expire(self._lease_key(request_id), self.lease_seconds))

    def lease_heartbeat(
        self,
        request_id: str,
        *,
        interval_seconds: float | None = None,
        budget_seconds: float | None = None,
        clock=time.monotonic,
    ) -> LeaseHeartbeat:
        """为一条在跑的任务造一枚续租心跳。未 `start()` 前它是哑的，`with` 会自己开。

        间隔默认 `lease_seconds / 3`（下限 1 s），保险丝默认 `lease_renew_budget()`；
        两者都能显式传入，是为了让"311 s 的长任务"这一格能被量出来而不必真等 311 s。
        """
        if interval_seconds is None:
            interval = max(
                self.lease_seconds / LEASE_HEARTBEAT_DIVISOR,
                LEASE_HEARTBEAT_MIN_INTERVAL_SECONDS,
            )
        else:
            interval = float(interval_seconds)
        budget = lease_renew_budget() if budget_seconds is None else float(budget_seconds)
        return LeaseHeartbeat(
            self,
            request_id,
            interval_seconds=interval,
            budget_seconds=budget,
            clock=clock,
        )

    def ack(self, request_id: str) -> bool:
        removed = self.redis.lrem(self.processing_key, 1, request_id)
        if removed:
            # 只有在处理队列里确实取走了这条消息才允许释放租约，
            # 否则可能误删重试持有者刚写入的新租约。
            self.redis.delete(self._lease_key(request_id))
        if self.is_cancelled(request_id):
            self.redis.delete(self._result_key(request_id))
            self.redis.set(self._status_key(request_id), "cancelled")
            return False
        if not removed:
            return False
        self.redis.set(self._status_key(request_id), "done")
        return True

    def complete(self, request_id: str, result: str | None, *, terminal: dict[str, Any] | None = None) -> bool:
        """Persist the result before acknowledging the processing lease.

        R254 把这条腿从「只有一个正文字符串」扩成「正文 + 结构化终态」。`terminal` 是随答案
        一起发布的那份读数（终态语义、出处、批准把手；形状由 `app/api/v1/chat.py`
        ::build_queue_terminal` 独家定义），落在独立的 `:terminal:` 键上，与答案键同生同死：
        丢弃的两支一并删它，绝不出现「正文没了、读数还在」。
        `result=None` 说的是「这一轮压根没有正文」——挂起在等人批准的那一轮就是它，从此不再由
        一句 37 字挂起文案顶替。状态键由 `terminal["terminal_state"]` 推导，不是第二枚参数：
        两枚各填各的就会造出「载荷说在等人、状态说已跑完」这种自相矛盾的终态。认得两枚
        （`answered` -> `done`、`awaiting_approval` -> `awaiting_approval`），第三枚当场 raise，
        绝不静默降级回 `done`——那等于把本单要消灭的那句谎报留在原地。
        关键字参数带默认值，所以本单之前的每一处调用、以及 redis 里在位的每一枚旧行，逐字节不变。

        取消优先且所有权优先：运行途中被取消、或租约已过期被回收时，本 worker
        已不再拥有这条消息，必须丢弃结果，既不得发布答案也不得谎报 done。

        R227 把"不得谎报 done"落成读得到的东西。`complete()` 交回 False 当且仅当这一格
        结果被丢弃，此时三件事同时成立：

        1. 答案键不存在（`result()` 读回 None，永不出现"跑完了、正文空"）；
        2. 状态**不是** `done`——取消那一支仍由 `ack()` 落成 `cancelled`，租约那一支
           不去 `ack()`（正是它把状态写成 done 的），消息留在处理表里等 `requeue_expired`
           重投，所读到的仍是非终态 `processing`，下一任跑完的答案才是发布出去的那一份；
        3. `failure()["last_error"]` 写着 `result_discarded:<reason>`，成因可区分,
           `attempts` 一个字节不动——重试预算属于队列，不属于这一任。
        """
        awaiting = _terminal_awaits_approval(terminal)
        if self.is_cancelled(request_id):
            self._record_discard(request_id, DISCARD_REASON_CANCELLED)
            self.redis.delete(self._result_key(request_id))
            self.redis.delete(self._terminal_key(request_id))
            self.ack(request_id)
            return False
        if self._lease_lost(request_id):
            self._record_discard(request_id, DISCARD_REASON_LEASE_LOST)
            self.redis.delete(self._result_key(request_id))
            self.redis.delete(self._terminal_key(request_id))
            return False
        if result is not None:
            self.redis.set(self._result_key(request_id), result, ex=self.result_ttl)
        if terminal is not None:
            self.redis.set(
                self._terminal_key(request_id),
                json.dumps(terminal, ensure_ascii=False, separators=(",", ":")),
                ex=self.result_ttl,
            )
        if not self.ack(request_id):
            return False
        if awaiting:
            # 写在这里而不并进 `ack()`：ack 那一支说的仍是「闭合成 done」这件旧事，只有带着待批准
            # 把手的这一轮才改口。🔴 必须是字符串字面量：R232 用 AST 认「往 status 键写字面量」
            # 这枚形状，写成常量会落进它的 blind_spots，而那枚钉的文本计数还会把注释也数进去。
            self.redis.set(self._status_key(request_id), "awaiting_approval")
        return True

    def terminal(self, request_id: str) -> dict[str, Any]:
        """读回结构化终态：`{"state": ..., "payload": ...}`，三态各有名。

        `absent` 是「这一格根本没有」——R254 之前发布的那些在位行就是它。读的人必须把它和
        「有但读不懂」分开说，因为前者是兼容、后者是损坏。`unreadable` 是键在位而载荷解不开
        （半截 JSON、被人手改过的、换代留下的异形）：那一格宁缺毋造。
        """
        raw = self.redis.get(self._terminal_key(request_id))
        if raw is None:
            return {"state": "absent", "payload": None}
        try:
            data = json.loads(raw.decode() if isinstance(raw, bytes) else str(raw))
        except (TypeError, ValueError):
            return {"state": "unreadable", "payload": None}
        if not isinstance(data, dict):
            return {"state": "unreadable", "payload": None}
        return {"state": "ok", "payload": data}

    def append_piece_batch(self, request_id: str, batch: dict[str, Any]) -> bool:
        """把队列道刚汇出来的一截字打成一批，推进片段表。

        一批就是**一次** ``RPUSH``：不存在「正文到了、计数还没到」的中间态，也不存在写坏一半。
        每批自带序号与累计计数器，读数侧取「序号最大的那一批」当账面数，并按序号去重——
        连接抖动让同一批重发时，客户端看见的字不会翻倍。

        租约过期、这一轮被取消之类的旁支不在这里判：片段表只是**过程表演**，终态那一份
        由 ``complete()`` 独立负责，两者同生不同死（表跟着 ``result_ttl`` 走，过期就没了）。
        """
        if not isinstance(batch, dict):
            raise ValueError("piece batch must be a dict")
        if batch.get("schema") != PIECE_BATCH_SCHEMA:
            raise ValueError("piece batch schema must be %r" % PIECE_BATCH_SCHEMA)
        seq = batch.get("seq")
        if isinstance(seq, bool) or not isinstance(seq, int) or seq <= 0:
            raise ValueError("piece batch seq must be a positive int")
        payload = json.dumps(batch, ensure_ascii=False, separators=(",", ":"))
        key = self._pieces_key(request_id)
        self.redis.rpush(key, payload)
        # TTL 这一手要**问着打**：真 Redis 有 `expire`，仓里那枚离线双件
        # `tests/test_reliable_queue.py::FakeRedis` 从头到尾只建模 `set(..., ex=)`，没有 `expire`。
        # 无条件打就会在每一次汇流上抛 AttributeError，被投递面记成一条告警——R548 那枚「片流不许让
        # 日志面多出一行」的在册钉当场把这件事抓出来了（10-01 现场）。跳过不等于放过：TTL 在位由
        # `test_the_incremental_store_expires_with_the_result_ttl` 盯着，它把 `expire` 装回双件并
        # 断言片段键真被叫到，摘掉这一行照样红。
        expire = getattr(self.redis, "expire", None)
        if callable(expire):
            expire(key, self.result_ttl)
        return True

    def piece_readout(self, request_id: str, *, since: int = 0) -> dict[str, Any]:
        """读回片段表的增量读数：``text`` 是 ``since`` 之后新长出来的那一截字。

        三态与 ``terminal()`` 同形，因为这三件事差一个字就会读成假绿：

        * ``absent``：表里什么都没有——这一轮一枚片都没汇出来（或已经过期）。它不等于「零片」，
          更不等于「跑完了没正文」；
        * ``unreadable``：表在位但解不开（半截 JSON、人手改过、换代留下的异形）。那一格宁缺毋造，
          并把 ``reason`` 说清，绝不回一串空字冒充「还没长出来」；
        * ``ok``：``cursor`` 是这批之后的新游标，客户端下一发把它原样填回 ``since``。

        ``discarded`` 说的是 worker **内存账本**超上限丢掉的片数（判据④ 那一行），
        ``truncated`` 说的是增量表自己停止存正文之后又过了几批——两枚分开报，
        因为前者不影响客户端拿到的字，后者影响，混成一枚就分不清是内存问题还是投递问题。
        """
        empty = {
            "state": PIECE_ABSENT,
            "text": "",
            "cursor": 0,
            "pieces": 0,
            "chars": 0,
            "discarded": 0,
            "truncated": 0,
            "legs": [],
            "reason": "",
        }
        raw = self.redis.lrange(self._pieces_key(request_id), 0, -1)
        if not raw:
            return empty
        seen: dict[int, dict[str, Any]] = {}
        for item in raw:
            try:
                data = json.loads(item.decode() if isinstance(item, bytes) else str(item))
            except (TypeError, ValueError):
                return dict(empty, state=PIECE_UNREADABLE, reason="batch_payload_unparsable")
            if not isinstance(data, dict) or data.get("schema") != PIECE_BATCH_SCHEMA:
                return dict(empty, state=PIECE_UNREADABLE, reason="batch_schema_mismatch")
            seq = data.get("seq")
            if isinstance(seq, bool) or not isinstance(seq, int) or seq <= 0:
                return dict(empty, state=PIECE_UNREADABLE, reason="batch_seq_invalid")
            seen[seq] = data
        ordered = [seen[seq] for seq in sorted(seen)]
        latest = ordered[-1]
        cursor = int(latest["seq"])
        offset = since if isinstance(since, int) and since > 0 else 0
        if offset > cursor:
            # 游标比表尾还靠前一次换代／过期后的空表：当成 0 整段重讲。屏侧多拿一遍已有的字
            # 是可恢复的，冻在一枚没人能推进的游标上才是事故——这一格也为此不新造错误码。
            offset = 0
        delta = "".join(
            str(entry.get("text", "")) for entry in ordered if int(entry["seq"]) > offset
        )
        return {
            "state": PIECE_OK,
            "text": delta,
            "cursor": cursor,
            "pieces": int(latest.get("pieces", 0) or 0),
            "chars": int(latest.get("chars", 0) or 0),
            "discarded": int(latest.get("discarded", 0) or 0),
            "truncated": int(latest.get("truncated", 0) or 0),
            "legs": [str(name) for name in (latest.get("legs") or [])],
            "reason": "",
        }

    def _record_discard(self, request_id: str, reason: str) -> None:
        """把"结果被丢弃"写进重试账本，供 `failure()` 与 /queue/status 读得到。

        账本读不懂（消息键不在、或载荷不是当年那本 dict 账）就一个字节都不盖——
        宁可少一笔原因，也不拿伪造的账本冒充事实。
        """
        raw = self.redis.get(self._message_key(request_id))
        if not raw:
            return
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        data["last_error"] = f"{RESULT_DISCARDED}:{reason}"
        self.redis.set(
            self._message_key(request_id),
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        )

    def result(self, request_id: str) -> str | None:
        value = self.redis.get(self._result_key(request_id))
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    def fail_or_retry(self, request_id: str, error: str, *, retryable: bool = True) -> str:
        """Retry a failed task, or park it in the dead-letter list.

        ``retryable=False`` is a caller-supplied verdict that another attempt cannot
        change the outcome — an authorization denial is the case that motivated it.
        Such a task goes straight to the dead list and its attempt counter is left
        exactly where it was, so the retry budget stays intact for real faults.
        Every existing caller keeps its previous behaviour because the default is
        ``True``, which makes the condition below identical to the old one.

        R585：真正落 dead 的那一次，把「为什么落 dead」也记进同一本账（`dead_verdict`），可读面才第一次说得出成因——过去这枚判定只活在 worker 的日志行里。账本读不到（message 键不在位）仍旧一个字节都不盖，与 `_record_discard` 同一口径：宁可少一笔原因，不伪造账本。
        """
        if self.is_cancelled(request_id):
            self.redis.lrem(self.processing_key, 1, request_id)
            self.redis.lrem(self.pending_key, 1, request_id)
            self.redis.delete(self._lease_key(request_id))
            self.redis.set(self._status_key(request_id), "cancelled")
            return "cancelled"
        raw = self.redis.get(self._message_key(request_id))
        attempts = 0
        data = None
        if raw:
            data = json.loads(raw)
            attempts = int(data.get("attempts", 0))
            data["last_error"] = error
        dead = not retryable or attempts >= self.max_attempts
        if data is not None:
            if dead:
                # R585 判据①③：这一枚判定必须在写状态键**之前**落账——反过来就留出一瞬「状态已经叫 dead、账上还答不出为什么」的窗口。
                data[DEAD_VERDICT_LEDGER_KEY] = {"reason": str(error), "retryable": bool(retryable)}
            self.redis.set(self._message_key(request_id), json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        self.redis.lrem(self.processing_key, 1, request_id)
        self.redis.delete(self._lease_key(request_id))
        if dead:
            self.redis.rpush(self.dead_key, request_id)
            self.redis.set(self._status_key(request_id), "dead")
            return "dead"
        self.redis.rpush(self.pending_key, request_id)
        self.redis.set(self._status_key(request_id), "queued")
        return "queued"

    def requeue_expired(self) -> int:
        moved = 0
        for item in self.redis.lrange(self.processing_key, 0, -1):
            request_id = item.decode() if isinstance(item, bytes) else str(item)
            if self.redis.exists(self._lease_key(request_id)):
                continue
            self.fail_or_retry(request_id, "lease_expired")
            moved += 1
        return moved

    def cancel(self, request_id: str) -> bool:
        if not self.redis.exists(self._message_key(request_id)):
            return False
        self.redis.set(self._cancel_key(request_id), "1", ex=self.lease_seconds)
        if self.redis.lrem(self.pending_key, 1, request_id):
            self.redis.set(self._status_key(request_id), "cancelled")
        else:
            self.redis.set(self._status_key(request_id), "cancel_requested")
        return True

    def is_cancelled(self, request_id: str) -> bool:
        return bool(self.redis.exists(self._cancel_key(request_id)))

    def status(self, request_id: str) -> str | None:
        value = self.redis.get(self._status_key(request_id))
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    def dead_verdict(self, request_id: str) -> dict[str, Any] | None:
        """这一枚 dead 是怎么落下来的；没有这笔账就交回 None，不拿 False 冒充「不可重试」。

        R585 判据①③：可读面要说的两件事——落 dead 时交给队列的那枚原始文本，以及调用方当时给出的终局判定。读不懂（键不在位、载荷不是当年那本 dict 账、那一格压根没记）一律交回 None：这一格说的是「读不到」，不是「没有发生过」。
        """
        raw = self.redis.get(self._message_key(request_id))
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        verdict = data.get(DEAD_VERDICT_LEDGER_KEY)
        if not isinstance(verdict, dict):
            return None
        return {"reason": verdict.get("reason"), "retryable": verdict.get("retryable")}

    def failure(self, request_id: str) -> dict[str, Any]:
        """Report retry bookkeeping so a failed task always carries a reason."""
        raw = self.redis.get(self._message_key(request_id))
        try:
            data = json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {
            "attempts": int(data.get("attempts") or 0),
            "last_error": data.get("last_error"),
            "max_attempts": self.max_attempts,
        }

    def _list_depth(self, key: str) -> int:
        """队列深度现读 Redis 服务端的 LLEN，不在本进程里数。

        多进程/多副本下这是唯一能信的说法：API 进程与 worker 进程各自记的账都不作数，
        只有服务端那一份会随入队/出队一起动。也不拿 LRANGE 拉全长列表回来数长度——
        观测面不该把被观测的压力再放大一遍。
        """
        return int(self.redis.llen(key))

    def pending_depth(self) -> int:
        #: 排队区深度：等开跑的请求数，「满」按这一枚算。
        return self._list_depth(self.pending_key)

    def processing_depth(self) -> int:
        #: 处理中深度：已被 worker 领走、还挂在处理表上的请求数。
        return self._list_depth(self.processing_key)

    def dead_letter_depth(self) -> int:
        #: 死信深度：重试预算耗尽或被判定不可重试后停车的请求数。
        return self._list_depth(self.dead_key)

    def stats(self) -> dict[str, Any]:
        """把「满没满」变成能被读到的状态——只交读数，不做任何执法。

        - queue_length / processing：与 GET /api/v1/queue/stats 今天交出的两枚键同名
          同值（LLEN 与 len(LRANGE 0 -1) 在 Redis 语义上恒等），路由改成直接返回本方法时
          那两枚数一个字都不许变。
        - capacity：部署声明的排队上限；没声明就是 null，既不是 0 也不是「无限」。
        - remaining：capacity - queue_length，夹到不小于 0；容量未知时 null。
        - saturated：queue_length >= capacity。**容量未知时是 null，不是 false**——
          「读不到」和「还没满」是两句话，合并成一句就开始编数了。
        - capacity_source / depth_source：这两枚数是从哪来的，供审计与前端分色。

        入队语义与本页无关：本方法一个字节都不写，也拒不了任何一条消息。
        """
        pending = self.pending_depth()
        capacity = self.capacity
        return {
            "queue_length": pending,
            "processing": self.processing_depth(),
            "capacity": capacity,
            "remaining": None if capacity is None else max(capacity - pending, 0),
            "saturated": None if capacity is None else pending >= capacity,
            "capacity_source": self.capacity_source,
            "depth_source": DEPTH_SOURCE_REDIS_LLEN,
        }


class LeaseHeartbeat:
    """在任务运行期间把处理租约续到满格；一旦不再持有，立刻停表。

    心跳是"持有者还活着"的读数，不是所有权凭证。三条边界写死在这里：

    - 续租走 `EXPIRE`：键已经不在就返回 0，所以被 `requeue_expired` 收回或改派的租约
      绝不会被上一任 worker 唤醒。
    - 心跳死了就是租约死了：线程随进程一起消失，租约在 `lease_seconds` 内过期，
      `requeue_expired` 照旧重投——崩溃检测的速度一个字节都没变慢。
    - 到 `budget_seconds` 这条保险丝就停手：卡死但没崩的进程不许无限期占着消息。

    `renewals` / `refusals` / `stopped_reason` 三枚读数交给 worker 落日志。下次再有人问
    "这一格到底是哪一支触发的"，不必再从两枚时间戳之差反推。

    `beat()` 是可以脱离线程单独驱动的（注入 `clock` 后按假时钟推进），这一格之所以要能
    离线量：真等 311 s 的用例在全量门里跑不动，而跑不动的判据等于没有判据。
    """

    STOP_MANUAL = "manual"
    STOP_LEASE_LOST = "lease_lost"
    STOP_BUDGET = "renew_budget_spent"
    STOP_RENEW_ERROR = "renew_error"

    def __init__(
        self,
        queue: ReliableQueue,
        request_id: str,
        *,
        interval_seconds: float,
        budget_seconds: float,
        clock=time.monotonic,
    ):
        if interval_seconds <= 0 or budget_seconds <= 0:
            raise ValueError("invalid lease heartbeat configuration")
        self.queue = queue
        self.request_id = request_id
        self.interval_seconds = float(interval_seconds)
        self.budget_seconds = float(budget_seconds)
        self.renewals = 0
        self.refusals = 0
        self.stopped_reason: str | None = None
        self.started_at = clock()
        self._clock = clock
        self._next_due = self.started_at + self.interval_seconds
        self._thread: threading.Thread | None = None
        self._wake = threading.Event()

    @property
    def running(self) -> bool:
        return self.stopped_reason is None and self._thread is not None

    def start(self) -> "LeaseHeartbeat":
        if self.stopped_reason is not None or self._thread is not None:
            return self
        self._thread = threading.Thread(
            target=self._loop,
            name=f"lease-heartbeat-{self.request_id[:8]}",
            daemon=True,
        )
        self._thread.start()
        return self

    def beat(self, now: float | None = None) -> bool:
        """到点的一拍：续上了返回 True（继续跳），停表返回 False。

        没到 `interval_seconds` 的拍一个字节都不写 Redis。心跳的意义是"定期报活",
        不是"每次被调度都重盖一次章"——否则一枚被高频驱动的假时钟能把它读成无限租约。
        """
        if self.stopped_reason is not None:
            return False
        now = self._clock() if now is None else now
        if now - self.started_at >= self.budget_seconds:
            self._stop(self.STOP_BUDGET)
            return False
        if now < self._next_due:
            return True
        self._next_due = now + self.interval_seconds
        try:
            held = self.queue.renew_lease(self.request_id)
        except Exception:
            # 客户端不支持 EXPIRE、连接瞬断……一律停表：租约就此自然过期，交给回收器。
            # 心跳不许把正在跑的这一轮打死，也不许在报不了活的时候装作报到了。
            self._stop(self.STOP_RENEW_ERROR)
            return False
        if held:
            self.renewals += 1
            return True
        self.refusals += 1
        self._stop(self.STOP_LEASE_LOST)
        return False

    def _loop(self) -> None:
        while self.stopped_reason is None:
            self._wake.wait(self.interval_seconds)
            self.beat()

    def _stop(self, reason: str) -> None:
        self.stopped_reason = reason
        self._wake.set()

    def stop(self) -> str:
        """停表并回收线程，返回停表原因；正常跑完是 `manual`，提前停的就是那枚成因。"""
        if self.stopped_reason is None:
            self._stop(self.STOP_MANUAL)
        thread = self._thread
        self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self.interval_seconds + 1.0)
        return str(self.stopped_reason)

    def readings(self) -> dict[str, Any]:
        return {
            "renewals": self.renewals,
            "refusals": self.refusals,
            "stopped_reason": self.stopped_reason,
        }

    def __enter__(self) -> "LeaseHeartbeat":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.stop()
        return False


def connect_reliable_queue(
    redis_url: str | None = None,
    *,
    redis_factory=None,
    **queue_options,
) -> ReliableQueue:
    """Return a queue only after its Redis dependency has passed a health probe."""
    url = (redis_url or os.getenv("REDIS_URL", "")).strip()
    if not url:
        raise QueueConnectionError("REDIS_URL is required for the reliable queue")

    if redis_factory is None:
        try:
            import redis
        except ModuleNotFoundError as exc:
            raise QueueConnectionError("Redis client dependency is unavailable") from exc
        redis_factory = redis.Redis.from_url

    try:
        client = redis_factory(url)
        client.ping()
    except Exception as exc:
        raise QueueConnectionError(f"Redis queue is unavailable: {exc}") from exc
    #: 容量读数在健康探针通过之后才去读：REDIS_URL 缺失、Redis 不通、redis 依赖不在，
    #: 仍然是 QueueConnectionError → 503 queue_unavailable，这条路径一个字没动（判据③）。
    capacity, capacity_source = parse_queue_capacity(os.getenv(QUEUE_CAPACITY_ENV))
    queue_options.setdefault("capacity", capacity)
    queue_options.setdefault("capacity_source", capacity_source)
    return ReliableQueue(client, **queue_options)
