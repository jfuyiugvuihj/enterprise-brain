"""Execution spans recorded at the live model and tool boundaries.

A span only becomes a persisted record when the surrounding execution carries an
authenticated owner. Anonymous spans are dropped rather than attributed to an
invented principal, which keeps ``owner_id`` meaningful in every execution table.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Any
from uuid import uuid4

from app.agents.evidence import bag_from_config
from app.common.logger import logger
from app.trace.store import default_trace_store

_UNSET = object()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _owner_id(config: Any) -> str:
    configurable = _configurable(config)
    principal = configurable.get("principal")
    if principal is None:
        return ""
    user_id = getattr(principal, "user_id", None)
    if user_id is None and isinstance(principal, dict):
        user_id = principal.get("user_id")
    return str(user_id or "").strip()


def _configurable(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    configurable = config.get("configurable")
    return configurable if isinstance(configurable, dict) else {}


def span_identity(config: Any) -> dict[str, str]:
    """Resolve the identifiers a span belongs to, without inventing an owner."""
    configurable = _configurable(config)
    owner_id = _owner_id(config)
    trace_id = str(configurable.get("trace_id") or "").strip()
    step_id = str(configurable.get("step_id") or "").strip()
    if not step_id and owner_id and trace_id:
        worker = str(configurable.get("worker") or "").strip()
        step_id = f"{trace_id}:worker:{worker}" if worker else ""
    return {
        "owner_id": owner_id,
        "request_id": str(configurable.get("request_id") or "").strip(),
        "trace_id": trace_id,
        "task_id": str(configurable.get("task_id") or "").strip(),
        "worker": str(configurable.get("worker") or "").strip(),
        "agent_run_id": f"{trace_id}:orchestrator" if trace_id else "",
        "agent_step_id": step_id,
    }


@dataclass
class ExecutionSpan:
    """Base span: records lifecycle events plus one structured execution row."""

    record_kind: str
    record_id: str
    identity: dict[str, str]
    started_event: str
    finished_event: str
    base_payload: dict[str, Any] = field(default_factory=dict)
    bag: dict[str, Any] | None = None
    started_at: str = field(default_factory=_utc_now)
    monotonic_start: float = field(default_factory=time.monotonic)
    first_token_at: str | None = None
    finished: bool = False

    @property
    def active(self) -> bool:
        return bool(self.identity.get("owner_id")) and bool(self.identity.get("trace_id"))

    def mark_first_token(self) -> None:
        if self.first_token_at is None:
            self.first_token_at = _utc_now()

    def _record_boundary_status(self, status: str, error_code: str) -> None:
        """Tell the execution evidence bag which terminal state this boundary saw."""
        if self.bag is None:
            return
        from app.agents.evidence import record_model_status, record_tool_status

        try:
            if self.record_kind == "tool_calls":
                record_tool_status(
                    self.bag,
                    tool=str(self.base_payload.get("tool_name") or ""),
                    status=status,
                    error_code=error_code or status,
                )
            elif status != "completed":
                record_model_status(self.bag, status, error_code or status)
        except Exception as exc:  # evidence collection must never break a call
            logger.warning("[Trace] span status was not recorded: %s", exc)

    def record(self, event_type: str, status: str, payload: dict[str, Any]) -> None:
        if not self.active:
            return
        try:
            default_trace_store().record_event(
                trace_id=self.identity["trace_id"],
                request_id=self.identity["request_id"],
                task_id=self.identity["task_id"],
                event_type=event_type,
                status=status,
                payload={**self.base_payload, **payload, "owner_id": self.identity["owner_id"]},
            )
        except Exception as exc:  # a span must never change the business answer
            logger.warning("[Trace] %s span event failed: %s", event_type, exc)

    def begin(self) -> "ExecutionSpan":
        self.record(
            self.started_event,
            "running",
            {"started_at": self.started_at, "record_id": self.record_id},
        )
        return self

    def __enter__(self) -> "ExecutionSpan":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.finished:
            return False
        if exc_type is None:
            self.finish("completed")
        else:
            self.finish("failed", error_code=error_code_for(exc))
        return False

    def finish(
        self,
        status: str,
        *,
        error_code: str = "",
        summary: dict[str, Any] | None = None,
        record_evidence: bool = True,
    ) -> dict[str, Any]:
        """Close the span. ``record_evidence`` is the R110 switch, and it is the only one.

        A call the consumer threw away is over, so its ``*.finished`` event and its R51
        stage sample have to exist like any other exit. What must not happen is the
        execution evidence bag hearing about it: ``_record_boundary_status`` feeds
        ``model_statuses``, and ``evidence._terminal_status`` reads that list. A word it has
        never met is inert only for as long as none of its branches matches it -- the day one
        does, a stream the caller chose to stop reading buys the customer a warning sentence,
        or turns a ``success`` into a ``partial``. So the close skips the bag instead of
        betting on the branch table: the event bytes, the payload keys and the ledger sample
        are identical either way, and the round keeps the judgement it would have kept had
        the stream run to the end.
        """
        if self.finished:
            return {}
        self.finished = True
        if record_evidence:
            self._record_boundary_status(status, error_code)
        duration_ms = int((time.monotonic() - self.monotonic_start) * 1000)
        payload = {
            "record_id": self.record_id,
            "record_kind": self.record_kind,
            "status": status,
            "started_at": self.started_at,
            "first_token_at": self.first_token_at,
            "completed_at": _utc_now(),
            "duration_ms": duration_ms,
            "error_code": error_code or None,
            "summary": dict(summary or {}),
        }
        self.record(self.finished_event, status, payload)
        self._observe_stage(payload)
        return payload

    def _observe_stage(self, payload: dict[str, Any]) -> None:
        """Hand the finished duration to the R51 stage ledger.

        This is a consumer of what ``finish`` had already produced, not another step in
        the request: it sees the same ``duration_ms`` the event carries, and only for a
        span the store would accept (no owner, no record -- the rule that already guards
        ``record``). Anything it raises is swallowed and logged, because a collector that
        can fail a business answer is the failure judgement 3 forbids.
        """
        if not self.active:
            return
        try:
            from app.common.stage_timing import record_stage_sample, stage_timing_enabled

            if not stage_timing_enabled():
                return
            base = self.base_payload
            record_stage_sample(
                stage=str(base.get("stage") or ""),
                tool_name=str(base.get("tool_name") or ""),
                tier=str(base.get("model_tier") or ""),
                worker=str(base.get("worker") or ""),
                duration_ms=payload.get("duration_ms"),
                trace_id=self.identity.get("trace_id", ""),
                request_id=self.identity.get("request_id", ""),
                task_id=self.identity.get("task_id", ""),
                status=str(payload.get("status") or ""),
                source=self.record_kind,
                label=str(base.get("stage") or base.get("tool_name") or base.get("model_tier") or self.record_kind),
                started_at=payload.get("started_at"),
                completed_at=payload.get("completed_at"),
            )
        except Exception as exc:  # noqa: BLE001 - telemetry stays invisible
            logger.warning("[Trace] stage observation failed: %s", exc)


def record_stage_event(
    config: Any,
    *,
    stage: str,
    duration_ms: float,
    status: str = "completed",
    started_at: str | None = None,
    completed_at: str | None = None,
    tier: str = "",
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist one segment that is neither a model call nor a tool call.

    Not every segment R51 names has a span to inherit: ``reflect`` is a rule pass, and
    the query rewriter lives behind a file this ticket may not touch. This is the additive
    entry point those call sites can adopt with one line, and it goes through the same
    ``ExecutionSpan`` primitives so the "no owner, no record" rule still applies. It
    deliberately does not touch the evidence bag: writing a duration must not change what
    the answer cites.
    """
    identity = span_identity(config)
    span = ExecutionSpan(
        record_kind="stage_windows",
        record_id=f"{identity.get('trace_id') or 'trace'}:stage:{uuid4().hex}",
        identity=identity,
        started_event="stage.started",
        finished_event="stage.finished",
        base_payload={
            "stage": stage,
            "agent_run_id": identity["agent_run_id"],
            "agent_step_id": identity["agent_step_id"],
            "worker": identity["worker"],
            "model_tier": tier,
        },
    )
    payload = {
        "record_id": span.record_id,
        "record_kind": span.record_kind,
        "status": status,
        "started_at": started_at or span.started_at,
        "completed_at": completed_at or _utc_now(),
        "duration_ms": int(duration_ms),
        "summary": dict(summary or {}),
    }
    span.record(span.finished_event, status, payload)
    span._observe_stage(payload)
    return payload


def _reported_count(value: Any) -> int | None:
    """One rule for "the server counted this": an int, or ``None``.

    Shared by both reply shapes on purpose, because both failure modes of the old code lived
    in the gap between them: a count the server never reported had to stay ``None`` (a 0 here
    reads as "counted zero", and NULL is a different fact), and a count the server *did*
    report had to survive whatever object shape it arrived in. Nothing in here estimates:
    ``app.common.model_budget.estimate_prompt_tokens`` sizes clocks and budgets, and following
    跟进单 §21（「不得估算冒充实测 token 数」）it is not allowed to become a metered number.
    """
    return value if isinstance(value, int) else None


def model_token_counts(response: Any) -> dict[str, Any]:
    """The two token counts this call came back with, or ``None`` for "not reported".

    R38: exactly two reply shapes are read, and both now reach ``model_calls`` through
    ``app/trace/store.py``.

    * the provider object of the LangChain/OpenAI leg -- ``usage_metadata`` (LangChain) or a
      ``usage`` mapping, keyed ``input_tokens`` / ``output_tokens``;
    * :class:`app.common.model_handler.ModelReply` -- the attributes a leg carries after this
      ticket, ``input_tokens`` (native ``prompt_eval_count``) and ``output_tokens``
      (native ``eval_count``). Before R38 this shape matched neither branch, so a reply that
      had been counted came back as two ``None`` values.

    There is deliberately no third key. ``cached_tokens`` is the one an operator would expect
    here, and this deployment has no measured source for it: the local Ollama native
    ``/api/chat`` reply carries no cached-token field at all
    (``native_leg_reports_no_cached_tokens``), and the compatible leg's
    ``usage.prompt_tokens_details.cached_tokens`` measured 0 on product traffic because every
    round rewrites its prefix (``docs/perf/latency-budget-2026-09-16.md``, raw readings in
    ``docs/perf/raw/prodpath.jsonl``). So the 0 in the perf ledger is a measured 0, not a hit
    rate -- and writing a 0 here would be the one way to make it look like one.
    """
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, dict):
        usage = getattr(response, "usage", None) if isinstance(getattr(response, "usage", None), dict) else None
    if usage:
        return {
            "input_tokens": _reported_count(usage.get("input_tokens")),
            "output_tokens": _reported_count(usage.get("output_tokens")),
        }
    return {
        "input_tokens": _reported_count(getattr(response, "input_tokens", None)),
        "output_tokens": _reported_count(getattr(response, "output_tokens", None)),
    }


def start_model_call(
    config: Any,
    *,
    provider: str,
    model_name: str,
    queue_wait_ms: int | None = None,
    stage: str = "",
    model_tier: str = "",
) -> ExecutionSpan:
    """Open the span for one model call.

    R51 added ``stage`` and ``model_tier``. Both are optional and both are written
    only when the caller passes them: an event written by a call site that says
    nothing keeps the exact bytes it kept before, which is what lets judgement 3
    ("observation must not change behaviour") be tested against the old shape.
    """
    identity = span_identity(config)
    base_payload = {
        "provider": provider,
        "model_name": model_name,
        "agent_run_id": identity["agent_run_id"],
        "agent_step_id": identity["agent_step_id"],
        "worker": identity["worker"],
        "queue_wait_ms": queue_wait_ms,
    }
    if stage:
        base_payload["stage"] = stage
    if model_tier:
        base_payload["model_tier"] = model_tier
    span = ExecutionSpan(
        bag=bag_from_config(config),
        record_kind="model_calls",
        record_id=f"{identity.get('trace_id') or 'trace'}:model:{uuid4().hex}",
        identity=identity,
        started_event="model.started",
        finished_event="model.finished",
        base_payload=base_payload,
    )
    return span.begin()


def start_tool_call(
    config: Any,
    *,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> ExecutionSpan:
    identity = span_identity(config)
    span = ExecutionSpan(
        bag=bag_from_config(config),
        record_kind="tool_calls",
        record_id=f"{identity.get('trace_id') or 'trace'}:tool:{uuid4().hex}",
        identity=identity,
        started_event="tool_call.started",
        finished_event="tool_call.finished",
        base_payload={
            "tool_name": tool_name,
            "agent_run_id": identity["agent_run_id"],
            "agent_step_id": identity["agent_step_id"],
            "worker": identity["worker"],
            "arguments": _summarize_arguments(arguments),
        },
    )
    return span.begin()


def _summarize_arguments(arguments: dict[str, Any] | None) -> dict[str, Any]:
    from app.common.tracing import sanitize_trace_event

    if not isinstance(arguments, dict):
        return {}
    summary = {}
    for key, value in list(arguments.items())[:12]:
        if isinstance(value, (int, float, bool)) or value is None:
            summary[key] = value
        else:
            summary[key] = str(value)[:500]
    return sanitize_trace_event(summary)


def error_code_for(exc: BaseException) -> str:
    from app.common.model_budget import ModelBudgetExhausted

    if isinstance(exc, ModelBudgetExhausted):
        return ModelBudgetExhausted.code
    if isinstance(exc, TimeoutError):
        return "task_timeout"
    return "internal_error"


__all__ = [
    "ExecutionSpan",
    "record_stage_event",
    "model_token_counts",
    "error_code_for",
    "span_identity",
    "start_model_call",
    "start_tool_call",
]