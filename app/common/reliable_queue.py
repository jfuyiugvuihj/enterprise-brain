"""Reliable Redis queue primitives.

This module is deliberately separate from the legacy queue adapter until the worker
integration contract is reviewed. It provides reserve/ack, lease expiry, retry,
dead-letter, idempotency, cancellation, and explicit status transitions.
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
    ):
        if (
            not name
            or lease_seconds <= 0
            or max_attempts <= 0
            or idempotency_ttl <= 0
            or result_ttl <= 0
        ):
            raise ValueError("invalid queue configuration")
        self.redis = redis_client
        self.name = name.rstrip(":")
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.idempotency_ttl = idempotency_ttl
        self.result_ttl = result_ttl

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

    def ack(self, request_id: str) -> bool:
        removed = self.redis.lrem(self.processing_key, 1, request_id)
        if not removed:
            return False
        self.redis.delete(self._lease_key(request_id))
        self.redis.set(self._status_key(request_id), "done")
        return True

    def complete(self, request_id: str, result: str) -> bool:
        """Persist the result before acknowledging the processing lease."""
        self.redis.set(self._result_key(request_id), result, ex=self.result_ttl)
        return self.ack(request_id)

    def result(self, request_id: str) -> str | None:
        value = self.redis.get(self._result_key(request_id))
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    def fail_or_retry(self, request_id: str, error: str) -> str:
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
        if attempts >= self.max_attempts:
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
    return ReliableQueue(client, **queue_options)
