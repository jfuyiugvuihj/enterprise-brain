"""Reliable Redis queue primitives.

This module is deliberately separate from the legacy queue adapter until the worker
integration contract is reviewed. It provides reserve/ack, lease expiry, retry,
dead-letter, idempotency, cancellation, explicit status transitions,
and passive queue-pressure readings (depth plus declared capacity) for monitoring.
"""
from __future__ import annotations

import json
import os
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

    def _idempotency_key(self, key: str) -> str:
        return f"{self.name}:idempotency:{key}"

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

    def complete(self, request_id: str, result: str) -> bool:
        """Persist the result before acknowledging the processing lease.

        取消优先且所有权优先：运行途中被取消、或租约已过期被回收时，本 worker
        已不再拥有这条消息，必须丢弃结果，既不得发布答案也不得谎报 done。
        """
        if self.is_cancelled(request_id) or self._lease_lost(request_id):
            self.redis.delete(self._result_key(request_id))
            self.ack(request_id)
            return False
        self.redis.set(self._result_key(request_id), result, ex=self.result_ttl)
        return self.ack(request_id)

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
        """
        if self.is_cancelled(request_id):
            self.redis.lrem(self.processing_key, 1, request_id)
            self.redis.lrem(self.pending_key, 1, request_id)
            self.redis.delete(self._lease_key(request_id))
            self.redis.set(self._status_key(request_id), "cancelled")
            return "cancelled"
        raw = self.redis.get(self._message_key(request_id))
        attempts = 0
        if raw:
            data = json.loads(raw)
            attempts = int(data.get("attempts", 0))
            data["last_error"] = error
            self.redis.set(self._message_key(request_id), json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        self.redis.lrem(self.processing_key, 1, request_id)
        self.redis.delete(self._lease_key(request_id))
        if not retryable or attempts >= self.max_attempts:
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
