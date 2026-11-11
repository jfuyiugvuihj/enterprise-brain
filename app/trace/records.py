"""Canonical execution records produced by Agent and Worker boundaries.

A record stores identifiers, counts, timing and status only. Model output and
document bodies stay inside the business storage that owns them, never inside the
execution ledger.
"""
from __future__ import annotations

from typing import Any

from app.agents.contracts import AgentResult
from app.common.logger import logger
from app.trace.store import default_trace_store

_ENTRY_TYPES = {
    "sync": "agent.result.recorded",
    "queue": "agent.result.recorded",
}


def record_agent_result(
    record: AgentResult | dict[str, Any],
    *,
    owner_id: str = "",
    session_id: str = "",
    entry_point: str = "queue",
) -> dict[str, Any]:
    """Project one finished ``AgentResult`` onto the AgentRun row for its owner."""
    from app.agents.evidence import coerce_agent_result, summarize_agent_result

    payload = record if isinstance(record, dict) else (record.model_dump() if hasattr(record, "model_dump") else {})
    normalized = coerce_agent_result(str(payload.get("worker") or "orchestrator"), payload)
    if normalized is None:
        return {}
    owner_id = str(owner_id or "").strip()
    if not owner_id or not normalized.trace_id or not normalized.request_id:
        logger.warning("[Trace] AgentResult was not recorded: owner or trace identity missing")
        return {}

    summary = summarize_agent_result(normalized)
    status = "completed" if normalized.status in {"success", "partial"} else normalized.status
    try:
        default_trace_store().record_event(
            trace_id=normalized.trace_id,
            request_id=normalized.request_id,
            task_id=normalized.task_id,
            event_type=_ENTRY_TYPES.get(entry_point, "agent.result.recorded"),
            status=status,
            payload={
                "owner_id": owner_id,
                "session_id": session_id,
                "entry_point": entry_point,
                "agent_result": summary,
            },
        )
    except Exception as exc:  # a finished answer is never failed by telemetry
        logger.warning("[Trace] AgentResult persistence failed: %s", exc)
    return summary