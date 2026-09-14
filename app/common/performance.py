import math
import time
from threading import Lock


class PerformanceStats:
    def __init__(self):
        self._durations: list[float] = []
        self._errors = 0
        self._lock = Lock()

    def observe(self, duration_ms: float, error: bool = False) -> None:
        with self._lock:
            self._durations.append(float(duration_ms))
            self._errors += int(error)

    def report(self) -> dict:
        with self._lock:
            durations = sorted(self._durations)
            count = len(durations)
            rank = max(1, math.ceil(count * 0.95)) if durations else 0
            return {
                "count": count,
                "average_ms": round(sum(durations) / count, 2) if count else 0,
                "p95_ms": durations[rank - 1] if durations else 0,
                "error_rate": self._errors / count if count else 0.0,
            }


class RequestBudget:
    def __init__(self, timeout_seconds: float, started_at: float | None = None):
        self.timeout_seconds = max(0.01, float(timeout_seconds))
        self.started_at = started_at or time.monotonic()

    def expired(self) -> bool:
        return time.monotonic() - self.started_at >= self.timeout_seconds

    def remaining(self) -> float:
        return max(0.0, self.timeout_seconds - (time.monotonic() - self.started_at))
