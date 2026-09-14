"""Append-only local trace store used until database trace tables are integrated."""

from dataclasses import dataclass
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.common.tracing import sanitize_trace_event
from app.storage.persistence import build_persistence_adapter


@dataclass(frozen=True)
class _SpanColumns:
    id_column: str


class TraceStoreError(ValueError):
    """Raised when a trace event cannot be safely recorded."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TraceStore:
    def __init__(self, path: str | Path, persistence=None):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.persistence = persistence

    def record_event(
        self,
        *,
        trace_id: str,
        request_id: str,
        event_type: str,
        status: str,
        payload: dict[str, Any] | None = None,
        task_id: str = "",
    ) -> dict[str, Any]:
        trace_id = str(trace_id or "").strip()
        request_id = str(request_id or "").strip()
        if not trace_id or not request_id:
            raise TraceStoreError(
                "validation_error",
                "Trace events require trace_id and request_id.",
            )

        with self._lock:
            event = {
                "trace_id": trace_id,
                "request_id": request_id,
                "task_id": task_id,
                "sequence": self._next_sequence(trace_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": str(event_type or ""),
                "status": str(status or ""),
                "payload": sanitize_trace_event(payload or {}),
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            owner_id = str((payload or {}).get("owner_id") or "").strip()
            if self.persistence is not None and owner_id:
                self.persistence.upsert(
                    "trace_events",
                    f"{trace_id}:{event['sequence']}",
                    {
                        "event_id": f"{trace_id}:{event['sequence']}",
                        "trace_id": trace_id,
                        "request_id": request_id,
                        "task_id": task_id,
                        "sequence": event["sequence"],
                        "event_type": event["event_type"],
                        "status": event["status"],
                        "owner_id": owner_id,
                        "payload": event["payload"],
                        "created_at": event["timestamp"],
                    },
                )
                self._persist_execution_records(event, owner_id)
            return event

    def _persist_execution_records(self, event: dict[str, Any], owner_id: str) -> None:
        trace_id = event["trace_id"]
        payload = event["payload"]
        run_id = f"{trace_id}:orchestrator"
        # Every lifecycle event refreshes the run row. The upsert key is derived
        # from the trace id, so overlapping events stay idempotent.
        current = self.persistence.get("agent_runs", run_id) or {}
        terminal = event["event_type"] in {
            "request.completed",
            "request.failed",
            "request.cancelled",
        }
        run_status = event["status"] if terminal else current.get("status", event["status"])
        self.persistence.upsert(
            "agent_runs",
            run_id,
            {
                "agent_run_id": run_id,
                "owner_id": owner_id,
                "request_id": event["request_id"],
                "trace_id": trace_id,
                "task_id": event["task_id"],
                "session_id": payload.get("session_id") or current.get("session_id"),
                "worker": "orchestrator",
                "status": run_status,
                "started_at": current.get("started_at") or event["timestamp"],
                "completed_at": event["timestamp"] if terminal else current.get("completed_at"),
                "error_code": (
                    payload.get("error_code")
                    if event["event_type"].startswith("request.")
                    else current.get("error_code")
                ),
                "metadata": {
                    "worker_count": payload.get("worker_count", current.get("metadata", {}).get("worker_count")),
                    "has_final_answer": payload.get(
                        "has_final_answer", current.get("metadata", {}).get("has_final_answer")
                    ),
                    "agent_result": payload.get("agent_result") or current.get("metadata", {}).get("agent_result"),
                    "entry_point": payload.get("entry_point") or current.get("metadata", {}).get("entry_point"),
                },
            },
        )

        if event["event_type"] == "tool.completed":
            worker = str(payload.get("worker") or "unknown")
            step_id = f"{trace_id}:{event['sequence']}"
            self.persistence.upsert(
                "agent_steps",
                step_id,
                {
                    "agent_step_id": step_id,
                    "agent_run_id": run_id,
                    "owner_id": owner_id,
                    "step_id": step_id,
                    "worker": worker,
                    "status": event["status"],
                    "sequence": event["sequence"],
                    "started_at": event["timestamp"],
                    "completed_at": event["timestamp"],
                    "output_summary": {"result_length": payload.get("result_length", 0)},
                },
            )
            tool_call_id = f"{step_id}:{worker}"
            self.persistence.upsert(
                "tool_calls",
                tool_call_id,
                {
                    "tool_call_id": tool_call_id,
                    "agent_run_id": run_id,
                    "agent_step_id": step_id,
                    "owner_id": owner_id,
                    "tool_name": worker,
                    "status": event["status"],
                    "request_id": event["request_id"],
                    "started_at": event["timestamp"],
                    "completed_at": event["timestamp"],
                    "arguments": {},
                    "result_summary": {"result_length": payload.get("result_length", 0)},
                },
            )

        if event["event_type"] in {"step.started", "step.finished"}:
            self._persist_step(event, owner_id)

        if event["event_type"] in {"model.started", "model.finished"}:
            self._persist_span(event, owner_id, "model_calls")

        if event["event_type"] in {"tool_call.started", "tool_call.finished"}:
            self._persist_span(event, owner_id, "tool_calls")

        if event["event_type"] == "retrieval.completed":
            retrieval_id = f"{trace_id}:{event['sequence']}"
            hits = payload.get("hits") or []
            self.persistence.upsert(
                "retrieval_traces",
                retrieval_id,
                {
                    "retrieval_trace_id": retrieval_id,
                    "agent_run_id": run_id,
                    "owner_id": owner_id,
                    "request_id": event["request_id"],
                    "trace_id": trace_id,
                    "query_hash": str(payload.get("query_hash") or ""),
                    "index_version_id": payload.get("index_version_id"),
                    "filter_snapshot": payload.get("filters") or {},
                    "result_summary": {"hit_count": len(hits)},
                    "status": event["status"],
                    "created_at": event["timestamp"],
                },
            )

    def _persist_span(self, event: dict[str, Any], owner_id: str, collection: str) -> None:
        """Project a model or tool span onto its own execution row."""
        payload = event["payload"]
        record_id = str(payload.get("record_id") or "").strip()
        if not record_id:
            return
        trace_id = event["trace_id"]
        definition = _SPAN_COLUMNS[collection]
        current = self.persistence.get(collection, record_id) or {}
        values = {
            definition.id_column: record_id,
            "owner_id": owner_id,
            "request_id": event["request_id"],
            "agent_run_id": payload.get("agent_run_id") or f"{trace_id}:orchestrator",
            "agent_step_id": payload.get("agent_step_id") or current.get("agent_step_id") or None,
            "status": payload.get("status") or event["status"],
            "started_at": payload.get("started_at") or current.get("started_at") or event["timestamp"],
        }
        if collection == "model_calls":
            values.update(
                {
                    "provider": payload.get("provider") or current.get("provider") or "",
                    "model_name": payload.get("model_name") or current.get("model_name") or "",
                    "first_token_at": payload.get("first_token_at") or current.get("first_token_at"),
                    "completed_at": payload.get("completed_at") or current.get("completed_at"),
                    "queue_wait_ms": _first_value(payload, current, "queue_wait_ms"),
                    "duration_ms": _first_value(payload, current, "duration_ms"),
                    "error_code": payload.get("error_code") or current.get("error_code"),
                    "metadata": {
                        "worker": payload.get("worker") or current.get("worker"),
                    },
                }
            )
            summary = payload.get("summary") or {}
            if "input_tokens" in summary or "output_tokens" in summary:
                values["input_tokens"] = summary.get("input_tokens")
                values["output_tokens"] = summary.get("output_tokens")
        else:
            values.update(
                {
                    "tool_name": payload.get("tool_name") or current.get("tool_name") or "",
                    "completed_at": payload.get("completed_at") or current.get("completed_at"),
                    "error_code": payload.get("error_code") or current.get("error_code"),
                    "arguments": payload.get("arguments") or current.get("arguments") or {},
                    "result_summary": payload.get("summary") or current.get("result_summary") or {},
                }
            )
        self.persistence.upsert(collection, record_id, values)

    def _persist_step(self, event: dict[str, Any], owner_id: str) -> None:
        payload = event["payload"]
        trace_id = event["trace_id"]
        step_id = str(payload.get("step_id") or f"{trace_id}:{event['sequence']}")
        run_id = payload.get("agent_run_id") or f"{trace_id}:orchestrator"
        current = self.persistence.get("agent_steps", step_id) or {}
        status = payload.get("status") or event["status"]
        self.persistence.upsert(
            "agent_steps",
            step_id,
            {
                "agent_step_id": step_id,
                "step_id": step_id,
                "agent_run_id": run_id,
                "owner_id": owner_id,
                "worker": payload.get("worker") or current.get("worker") or "",
                "status": status,
                "sequence": payload.get("sequence") or current.get("sequence") or event["sequence"],
                "started_at": payload.get("started_at") or current.get("started_at") or event["timestamp"],
                "completed_at": payload.get("completed_at") or current.get("completed_at"),
                "error_code": payload.get("error_code") if status not in {"completed", "success"} else None,
                "input_summary": payload.get("input_summary") or current.get("input_summary") or {},
                "output_summary": payload.get("summary") or current.get("output_summary") or {},
            },
        )

    def replay(self, trace_id: str) -> list[dict[str, Any]]:
        trace_id = str(trace_id or "").strip()
        if not trace_id or not self.path.exists():
            return []
        with self._lock:
            events = [
                event
                for event in self._read_events()
                if event.get("trace_id") == trace_id
            ]
        return sorted(events, key=lambda event: int(event.get("sequence") or 0))

    def _next_sequence(self, trace_id: str) -> int:
        events = [
            event
            for event in self._read_events()
            if event.get("trace_id") == trace_id
        ]
        if not events:
            return 1
        return max(int(event.get("sequence") or 0) for event in events) + 1

    def _read_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events


_SPAN_COLUMNS = {
    "model_calls": _SpanColumns("model_call_id"),
    "tool_calls": _SpanColumns("tool_call_id"),
}


def _first_value(payload: dict[str, Any], current: dict[str, Any], key: str) -> Any:
    value = payload.get(key)
    if value is None or value == "":
        return current.get(key)
    return value


_default_store: TraceStore | None = None
_default_lock = threading.Lock()


def default_trace_store() -> TraceStore:
    """Process-wide trace store used by every execution boundary."""
    global _default_store
    with _default_lock:
        if _default_store is None:
            import os

            _default_store = TraceStore(
                Path(os.getenv("TRACE_STORE_PATH", "./data/traces/events.jsonl")),
                persistence=build_persistence_adapter(),
            )
        return _default_store


def reset_default_trace_store() -> None:
    global _default_store
    with _default_lock:
        _default_store = None
