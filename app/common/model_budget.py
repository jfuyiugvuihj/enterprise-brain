"""Machine-wide budget for the single local model server.

A private deployment runs one local model on the customer machine. Every boundary
that invokes that model must share one budget so a 14B model cannot be called
without limit. ``wait_seconds`` keeps legitimate parallel workers queueing instead
of stampeding the model; a zero wait preserves the previous non-blocking behavior.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


class ModelBudgetExhausted(RuntimeError):
    """The local model is busy and no slot became available in time."""

    code = "rate_limited"

    def __init__(self, wait_ms: int):
        super().__init__(
            "Local model capacity is exhausted "
            f"(error_code={self.code}); no business conclusion was generated."
        )
        self.wait_ms = wait_ms


@dataclass
class _ModelSlot:
    """A held budget slot. Release is idempotent so streaming paths cannot leak capacity."""

    _budget: "LocalModelBudget"
    wait_ms: int = 0
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._budget._semaphore.release()

    def __enter__(self) -> "_ModelSlot":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class LocalModelBudget:
    def __init__(self, max_concurrency: int | None = None, wait_seconds: float | None = None):
        configured = max_concurrency if max_concurrency is not None else _env_int(
            "MODEL_MAX_CONCURRENCY", 1
        )
        self.max_concurrency = max(1, configured)
        self.default_wait_seconds = (
            self._configured_wait() if wait_seconds is None else float(wait_seconds)
        )
        self._semaphore = threading.Semaphore(self.max_concurrency)

    @staticmethod
    def _configured_wait() -> float:
        raw = os.getenv("MODEL_CONCURRENCY_WAIT_SECONDS", "").strip()
        if not raw:
            return 60.0
        try:
            return max(0.0, float(raw))
        except ValueError:
            return 60.0

    def acquire(self, *, wait_seconds: float | None = None) -> _ModelSlot:
        """Take a model slot, waiting up to ``wait_seconds`` for free capacity."""
        budget_wait = self.default_wait_seconds if wait_seconds is None else float(wait_seconds)
        started = time.monotonic()
        acquired = (
            self._semaphore.acquire(blocking=False)
            if budget_wait == 0
            else self._semaphore.acquire(timeout=budget_wait)
        )
        wait_ms = int((time.monotonic() - started) * 1000)
        if not acquired:
            raise ModelBudgetExhausted(wait_ms)
        return _ModelSlot(self, wait_ms=wait_ms)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


_default: LocalModelBudget | None = None
_default_size: int | None = None
_default_lock = threading.Lock()


def default_model_budget() -> LocalModelBudget:
    """Process-wide budget shared by every model boundary."""
    global _default, _default_size
    configured = _env_int("MODEL_MAX_CONCURRENCY", 1)
    with _default_lock:
        if _default is None or _default_size != max(1, configured):
            _default = LocalModelBudget(max_concurrency=configured)
            _default_size = max(1, configured)
        return _default


def reset_default_budget() -> None:
    """Drop the cached budget so configuration changes take effect."""
    global _default, _default_size
    with _default_lock:
        _default = None
        _default_size = None