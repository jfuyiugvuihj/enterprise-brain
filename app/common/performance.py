import math
import time
from threading import Lock


class PerformanceStats:
    """Nearest-rank latency stats for one measured thing.

    R51 grew this from ``count / average_ms / p95_ms / error_rate`` to also answer P50,
    the maximum and the sum, because stage-level reporting needs all three and must not
    invent a second percentile convention to argue about later. The rank rule below is
    the one ``p95_ms`` already used: the value sitting at ``ceil(n * q)``, 1-based.
    """

    def __init__(self):
        self._durations: list[float] = []
        self._errors = 0
        self._lock = Lock()

    def observe(self, duration_ms: float, error: bool = False) -> None:
        with self._lock:
            self._durations.append(float(duration_ms))
            self._errors += int(error)

    @staticmethod
    def _rank(sorted_durations: list[float], quantile: float) -> float:
        if not sorted_durations:
            return 0
        position = max(1, math.ceil(len(sorted_durations) * quantile))
        return sorted_durations[position - 1]

    def percentile(self, quantile: float) -> float:
        """Nearest-rank quantile of what has been observed so far."""
        bounded = min(max(float(quantile), 0.0), 1.0)
        with self._lock:
            return self._rank(sorted(self._durations), bounded)

    def report(self) -> dict:
        with self._lock:
            durations = sorted(self._durations)
            count = len(durations)
            total = round(sum(durations), 2)
            return {
                "count": count,
                "average_ms": round(total / count, 2) if count else 0,
                "p50_ms": self._rank(durations, 0.50),
                "p95_ms": self._rank(durations, 0.95),
                "max_ms": durations[-1] if durations else 0,
                "total_ms": total,
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
