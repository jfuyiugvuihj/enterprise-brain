"""R51 — stage-level latency: one ledger, five named segments, no behaviour change.

The ticket (``docs/handoff/2026-09-15-backend-followup-requests.md`` 21 R51) asks for a
question the end-to-end number cannot answer: *which segment* is expensive. One P95 for
a whole request cannot tell a 41 s rewrite from a 0.24 s retrieval, and it is exactly the
number R42 handed over here -- its cost share was demoted to "reported, not gated"
because nothing could read it back per lane.

Design rules, each of them pinned by ``tests/test_r51_stage_latency.py``:

* Segments are named ``classify / rewrite / retrieve / generate / reflect``. Anything the
  rule table below cannot name lands in ``unattributed`` with its raw label, never
  silently dropped: a dropped segment is how a stage sum fakes a match.
* Nothing here measures a request by itself. It aggregates durations that the trace
  boundary already produced (``app/trace/spans.py``), so the timing source stays the one
  place that actually made the call.
* Nested spans are excluded from the additive ledger. A tool span contains the model
  calls it triggered, so summing both would over-attribute; ``overlap`` reports what was
  excluded instead of hiding it.
* ``gap_ms`` is derived, never assumed to be zero: it is the wall clock nobody
  instruments (rule nodes, HTTP, queueing), and it is what makes an end-to-end match
  honest -- latency-budget 2026-09-16 reached 0.03% precisely by listing its rule rows.
* Aggregation is pure arithmetic over what it is handed, so every judgement is testable
  offline with no server, no database, no model.

Lane and tier come from R42 itself (``app/agents/nodes.py::classify_route``), which is a
pure function of the question. The question deliberately is *not* copied into trace
events -- ``summarize_agent_result`` keeps traces to counts and identifiers -- so the
join is supplied by whoever holds the questions (an eval run, a log replay) via
``lane_by_trace``. Samples that arrive with an explicit lane win, and every lane value
records where it came from so an unlabelled run reports unknown lanes instead of
inventing a split.
"""
from __future__ import annotations

import contextlib
import os
import re
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from app.common.performance import PerformanceStats

#: The five segments the ticket names, in pipeline order.
CANONICAL_STAGES: tuple[str, ...] = ("classify", "rewrite", "retrieve", "generate", "reflect")

#: ``ModelTier`` value -> segment. Tiers are the enum the call sites already pass, so no
#: new label has to be trusted. ``compress`` / ``alert`` are real tiers with real callers
#: that are none of the five segments; mapping them to "" is deliberate -- they surface in
#: ``unattributed`` rather than inflating a named segment.
TIER_TO_STAGE: dict[str, str] = {
    "chat": "generate",      # app/agents/nodes.py respond -- the answer text
    "plan": "classify",      # app/agents/nodes.py plan -- split the compound question
    "rewrite": "rewrite",    # app/common/model_handler.py chat, the query rewriter
    "code": "generate",      # app/agents/tools.py _llm_pandas_code
    "analysis": "generate",  # doc/data/chart/export workers
    "compress": "",          # short-term memory compression: outside the five
    "alert": "",             # alert attribution: not on the ask path at all
}

#: ``tool_name`` -> segment. Retrieval is a tool span already, which is why it needs no
#: new instrumentation. ``export_report`` writes a file, which is none of the five.
TOOL_TO_STAGE: dict[str, str] = {
    "search_docs": "retrieve",
    "analyze_data": "generate",
    "query_data": "generate",
    "generate_chart": "generate",
    "export_report": "",
}

#: The supervisor shares ``analysis`` with the workers, so the worker identity is what
#: separates "decide who works" (classify) from "do the work" (generate).
SUPERVISOR_STAGE = "classify"
WORKER_TO_STAGE: dict[str, str] = {
    "doc": "generate",
    "data": "generate",
    "chart": "generate",
    "export": "generate",
    "approval": "generate",
}

#: How a latency-budget table would read this ledger, for the humans checking 2.
STAGE_DESCRIPTIONS: dict[str, str] = {
    "classify": "意图/路由/拆题决策（含 supervisor 往返）",
    "rewrite": "多路查询改写（app/common/model_handler.py，非流式）",
    "retrieve": "检索本体：向量 + BM25 + RRF（search_docs 工具跨度）",
    "generate": "worker 与闲聊的作答往返、pandas 代码生成",
    "reflect": "复审（当前为纯规则，见 latency-budget 的 0.033 s）",
}


def classify_stage(
    stage: str = "",
    *,
    tool_name: str = "",
    tier: str = "",
    worker: str = "",
) -> str:
    """Name the segment one execution belongs to. Empty string means "unattributed".

    Order is the whole rule: an explicit label wins, then the tool, then the model tier
    (with the supervisor disambiguated by worker), then the worker alone. Removing any
    step has to make a case go red, so each one is pinned separately.
    """
    label = str(stage or "").strip().lower()
    if label in CANONICAL_STAGES:
        return label
    tool = str(tool_name or "").strip()
    if tool:
        if tool in TOOL_TO_STAGE:
            return TOOL_TO_STAGE[tool]
        return ""
    tier_key = str(tier or "").strip().lower().removeprefix("modeltier.")
    if tier_key:
        named = SUPERVISOR_STAGE if (tier_key == "analysis" and not str(worker or "").strip()) else TIER_TO_STAGE.get(tier_key)
        if named is None:
            return ""
        return named
    return WORKER_TO_STAGE.get(str(worker or "").strip(), "")


# ==================== lane / tier: R42 read back ====================

#: Where a sample's lane/tier came from. "unknown" must stay visible in the report.
LANE_SOURCE_EXPLICIT = "explicit"
LANE_SOURCE_QUESTION = "r42_question"
LANE_SOURCE_LOG = "r42_log"
LANE_SOURCE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class LaneTier:
    """One R42 verdict: which lane, which tier, and how this copy learned it."""

    lane: str = ""
    tier: str = ""
    rule: str = ""
    source: str = LANE_SOURCE_UNKNOWN

    def as_dict(self) -> dict[str, str]:
        return {"lane": self.lane, "tier": self.tier, "rule": self.rule, "source": self.source}


def lane_tier_for_question(question: str) -> LaneTier:
    """Ask R42 itself. Imported lazily so aggregation stays cheap and offline.

    This is the anti-drift choice: re-implementing the lane rules here would let the
    readback disagree with the discriminator and still look green.
    """
    try:
        from app.agents.nodes import classify_route

        decision = classify_route(str(question or ""))
    except Exception:  # a missing discriminator must not invent a lane
        return LaneTier()
    tier = getattr(getattr(decision, "tier", None), "value", "") or ""
    return LaneTier(
        lane=str(getattr(decision, "lane", "") or ""),
        tier=str(tier),
        rule=str(getattr(decision, "rule", "") or ""),
        source=LANE_SOURCE_QUESTION,
    )


#: The [R42] log line as written in app/agents/nodes.py::classify_route. Pinned byte for
#: byte against the source by tests/test_r51_stage_latency.py so a wording change shows up
#: here as a red test instead of a silently useless parser.
R42_LOG_PATTERN = re.compile(
    r"\[R42\]\s+'(?P<question>.*?)'\s*→\s*lane=(?P<lane>\S+)\s+tier=(?P<tier>\S+)"
    r"(?:\s+rule=(?P<rule>\S+))?(?:\s+hit=(?P<hit>\S+))?"
)

#: The other anchor the ticket names: the qa lane skipping the split call entirely.
R42_PLAN_SKIP_PATTERN = re.compile(r"\[Plan\]\s+问答档\s*→\s*不拆题")


def parse_r42_log_line(line: str) -> LaneTier:
    """Recover one lane/tier from the log, for a replay that has no other join key."""
    text = str(line or "")
    if R42_PLAN_SKIP_PATTERN.search(text):
        return LaneTier(lane="qa", tier="chat", rule="plan_skipped", source=LANE_SOURCE_LOG)
    match = R42_LOG_PATTERN.search(text)
    if not match:
        return LaneTier()
    groups = match.groupdict()
    return LaneTier(
        lane=str(groups.get("lane") or ""),
        tier=str(groups.get("tier") or ""),
        rule=str(groups.get("rule") or ""),
        source=LANE_SOURCE_LOG,
    )


# ==================== samples ====================


@dataclass(frozen=True)
class StageSample:
    """One measured segment of one request."""

    stage: str
    duration_ms: float
    trace_id: str = ""
    request_id: str = ""
    task_id: str = ""
    lane: str = ""
    tier: str = ""
    rule: str = ""
    lane_source: str = LANE_SOURCE_UNKNOWN
    worker: str = ""
    source: str = ""
    tool_name: str = ""
    label: str = ""
    status: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    depth: int = 0

    @property
    def canonical(self) -> bool:
        return self.stage in CANONICAL_STAGES

    @property
    def label_or_stage(self) -> str:
        return self.stage or self.label or "unattributed"

    def with_lane_tier(self, lane_tier: LaneTier) -> "StageSample":
        if not lane_tier.lane and not lane_tier.tier:
            return self
        return replace(
            self,
            lane=self.lane or lane_tier.lane,
            tier=self.tier or lane_tier.tier,
            rule=self.rule or lane_tier.rule,
            lane_source=self.lane_source if (self.lane or self.tier) else lane_tier.source,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "duration_ms": self.duration_ms,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "lane": self.lane,
            "tier": self.tier,
            "lane_source": self.lane_source,
            "worker": self.worker,
            "source": self.source,
            "tool_name": self.tool_name,
            "label": self.label,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "depth": self.depth,
        }


#: Trace event types that carry a finished, timed execution. ``*.started`` events are
#: only read to pair an interval, never to add duration: counting both is double
#: attribution, which is the failure mode judgement 2 warns about.
FINISHED_EVENTS = {
    "model.finished": "model",
    "tool_call.finished": "tool",
    "stage.finished": "stage",
}


#: Terminal events that close one request's wall-clock window.
REQUEST_TERMINAL_EVENTS = {"request.completed", "request.failed", "request.cancelled"}


def request_windows_from_events(events: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    """Derive each request's end-to-end milliseconds from its own trace events.

    ``request.started`` and ``request.completed`` are both already persisted by the
    orchestrator, so the denominator for judgement 2 needs no new instrumentation. The
    arithmetic is the one the latency-budget table used: a millisecond timestamp
    difference per request, not a log line read by eye.
    """
    opened: dict[str, float] = {}
    windows: dict[str, float] = {}
    for event in events or []:
        body = event or {}
        trace_id = str(body.get("trace_id") or "")
        event_type = str(body.get("event_type") or "")
        stamp = _to_ms(body.get("timestamp") or (body.get("payload") or {}).get("started_at"))
        if not trace_id or stamp is None:
            continue
        if event_type == "request.started":
            opened[trace_id] = stamp
            continue
        if event_type in REQUEST_TERMINAL_EVENTS and trace_id in opened:
            windows[trace_id] = round(stamp - opened.pop(trace_id), 6)
    return windows


def _duration_ms(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number >= 0 else None


def _text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    return str(value).strip() if value is not None else ""


def samples_from_span_payload(
    payload: Mapping[str, Any],
    *,
    identity: Mapping[str, str] | None = None,
    source: str = "span",
) -> list[StageSample]:
    """Build the sample a finished span produced. Pure extraction, no guessing."""
    body = dict(payload or {})
    identity = dict(identity or {})
    duration_ms = _duration_ms(body.get("duration_ms"))
    if duration_ms is None:
        return []
    tool_name = _text(body, "tool_name")
    label = _text(body, "stage")
    tier = _text(body, "model_tier")
    worker = _text(body, "worker") or identity.get("worker", "")
    stage = classify_stage(label, tool_name=tool_name, tier=tier, worker=worker)
    question = _text(body, "question")
    sample = StageSample(
        stage=stage,
        duration_ms=duration_ms,
        trace_id=_text(body, "trace_id") or identity.get("trace_id", ""),
        request_id=_text(body, "request_id") or identity.get("request_id", ""),
        task_id=_text(body, "task_id") or identity.get("task_id", ""),
        lane=_text(body, "lane"),
        tier=tier,
        worker=worker,
        source=source,
        tool_name=tool_name,
        label=label or tool_name or tier or _text(body, "record_kind"),
        status=_text(body, "status"),
        started_at=body.get("started_at"),
        completed_at=body.get("completed_at"),
    )
    if not sample.lane and not sample.tier and question:
        return [sample.with_lane_tier(lane_tier_for_question(question))]
    return [sample]


def samples_from_events(
    events: Iterable[Mapping[str, Any]],
    *,
    lane_by_trace: Mapping[str, str] | None = None,
) -> list[StageSample]:
    """Fold a replayed trace into samples, keyed by ``record_id``.

    ``lane_by_trace`` maps ``trace_id -> question``; it is how an offline reader gives
    R42's lane to a run whose spans never saw the question.
    """
    collected: dict[str, StageSample] = {}
    order: list[str] = []
    started: dict[str, str] = {}
    for index, event in enumerate(events or []):
        payload = dict((event or {}).get("payload") or {})
        event_type = str((event or {}).get("event_type") or "")
        identity = {
            "trace_id": str((event or {}).get("trace_id") or ""),
            "request_id": str((event or {}).get("request_id") or ""),
            "task_id": str((event or {}).get("task_id") or ""),
            "worker": _text(payload, "worker"),
        }
        record_id = _text(payload, "record_id") or f"event:{index}"
        if event_type.endswith(".started"):
            started[record_id] = str(event.get("timestamp") or payload.get("started_at") or "")
            continue
        kind = FINISHED_EVENTS.get(event_type)
        if kind is None:
            continue
        source = _text(payload, "source") or f"{kind}_span"
        for sample in samples_from_span_payload(payload, identity=identity, source=source):
            if not sample.started_at:
                sample = replace(sample, started_at=started.get(record_id) or None)
            collected[record_id] = sample
            order.append(record_id)
    samples = [collected[key] for key in order]
    if not lane_by_trace:
        return samples
    return [_apply_lane_lookup(sample, lane_by_trace) for sample in samples]


def _apply_lane_lookup(sample: StageSample, lane_by_trace: Mapping[str, str]) -> StageSample:
    if sample.lane or sample.tier or not sample.trace_id:
        return sample
    question = lane_by_trace.get(sample.trace_id)
    if question is None:
        return sample
    value = question if isinstance(question, LaneTier) else lane_tier_for_question(str(question))
    return sample.with_lane_tier(value)


# ==================== aggregation ====================


def _to_ms(value: Any) -> float | None:
    """ISO-8601 (or epoch seconds/milliseconds) to epoch milliseconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number * 1000.0 if number < 1e11 else number
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            return float(text) * 1000.0
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp() * 1000.0


def to_epoch_ms(value: Any) -> float | None:
    """Public wrapper: the store needs the same timestamp arithmetic, nothing else."""
    return _to_ms(value)


def _interval(sample: StageSample) -> tuple[float, float] | None:
    start = _to_ms(sample.started_at)
    end = _to_ms(sample.completed_at)
    if start is None or end is None or end < start:
        return None
    return (start, end)


def _stats(samples: list[StageSample]) -> dict[str, Any]:
    """One segment's P50/P95 plus the sum, from the shared percentile skeleton."""
    stats = PerformanceStats()
    for sample in samples:
        stats.observe(sample.duration_ms)
    report = stats.report()
    return {
        "count": report["count"],
        "p50_ms": report["p50_ms"],
        "p95_ms": report["p95_ms"],
        "average_ms": report["average_ms"],
        "max_ms": report["max_ms"],
        "total_ms": report["total_ms"],
    }


def _entry(
    members: list[StageSample],
    ledger_members: list[StageSample],
    *,
    whole_ms: float,
    description: str = "",
) -> dict[str, Any]:
    """One segment as two views, because nesting makes them different questions.

    ``p50_ms`` / ``p95_ms`` answer judgement 1 and are measured over every sample of
    the segment -- a rewrite call that sits inside a retrieval span is still a rewrite
    call worth reporting. ``total_ms`` and ``share_pct`` answer judgement 2 and are the
    ledger view, which is why they exclude nested samples: adding a tool span and the
    model calls inside it would bill the same second twice. ``excluded_*`` says what was
    left out of the sum, so the two views can never be confused for each other.
    """
    measured = _stats(members)
    ledger = _stats(ledger_members)
    return {
        "count": measured["count"],
        "p50_ms": measured["p50_ms"],
        "p95_ms": measured["p95_ms"],
        "average_ms": measured["average_ms"],
        "max_ms": measured["max_ms"],
        "total_ms": ledger["total_ms"],
        "ledger_count": ledger["count"],
        "excluded_count": measured["count"] - ledger["count"],
        "excluded_ms": round(measured["total_ms"] - ledger["total_ms"], 6),
        "share_pct": _percent(ledger["total_ms"], whole_ms),
        "description": description,
    }


def _percent(part: float, whole: float) -> float:
    return round(part / whole * 100.0, 4) if whole else 0.0


def _group_view(
    samples: list[StageSample],
    ledger: list[StageSample],
    *,
    key: Callable[[StageSample], str],
    whole_ms: float,
) -> dict[str, Any]:
    """Per lane / per tier: each segment's percentiles, totals and share of the group."""
    measured: dict[str, list[StageSample]] = {}
    for sample in samples:
        measured.setdefault(key(sample) or "unknown", []).append(sample)
    grouped_ledger: dict[str, list[StageSample]] = {}
    for sample in ledger:
        grouped_ledger.setdefault(key(sample) or "unknown", []).append(sample)
    view: dict[str, Any] = {}
    for name in sorted(measured):
        members = measured[name]
        ledger_members = grouped_ledger.get(name, [])
        total_ms = round(sum(sample.duration_ms for sample in ledger_members), 6)
        by_label: dict[str, list[StageSample]] = {}
        ledger_by_label: dict[str, list[StageSample]] = {}
        for sample in members:
            by_label.setdefault(sample.label_or_stage, []).append(sample)
        for sample in ledger_members:
            ledger_by_label.setdefault(sample.label_or_stage, []).append(sample)
        stages = {
            stage: _entry(
                by_label.get(stage, []), ledger_by_label.get(stage, []), whole_ms=total_ms
            )
            for stage in CANONICAL_STAGES
        }
        for label in sorted(set(by_label) - set(CANONICAL_STAGES)):
            stages[label] = _entry(
                by_label[label], ledger_by_label.get(label, []), whole_ms=total_ms
            )
        view[name] = {
            "count": len(members),
            "requests": len({sample.trace_id for sample in members if sample.trace_id}),
            "total_ms": total_ms,
            "share_pct": _percent(total_ms, whole_ms),
            "stages": stages,
        }
    return view


def aggregate_stage_latency(
    samples: Iterable[StageSample],
    *,
    end_to_end_ms: float | None = None,
    end_to_end_by_trace: Mapping[str, float] | None = None,
    lane_by_trace: Mapping[str, str] | None = None,
    overlap_slack_ms: float = 1.0,
) -> dict[str, Any]:
    """The stage table plus the arithmetic that keeps an end-to-end match honest.

    Judgement 1 -> ``stages`` (P50 and P95 per named segment) and ``missing_stages``.
    Judgement 2 -> ``coverage_error_pct`` / ``within_one_percent``, backed by
    ``overlap`` (nesting excluded) and ``gap_ms`` (the un-instrumented remainder).
    Judgement 4 -> ``lanes`` and ``tiers``, aggregated per segment with shares.
    """
    items = list(samples or [])
    if lane_by_trace:
        items = [_apply_lane_lookup(sample, lane_by_trace) for sample in items]

    slack = float(overlap_slack_ms)
    intervals = {id(sample): _interval(sample) for sample in items}
    nested_ids: set[int] = set()
    overlap_pairs = 0
    unresolved_pairs = 0
    unresolved_by_trace: dict[str, int] = {}
    for position, outer in enumerate(items):
        outer_interval = intervals.get(id(outer))
        if outer_interval is None:
            continue
        for inner in items[position + 1 :]:
            # One pass per unordered pair: counting a pair in both directions would make
            # the diagnostics say something is twice as wrong as it is.
            inner_interval = intervals.get(id(inner))
            if inner_interval is None:
                continue
            shared = min(outer_interval[1], inner_interval[1]) - max(outer_interval[0], inner_interval[0])
            if shared <= slack:
                continue
            overlap_pairs += 1
            # Only strict containment justifies excluding one side from the sum. Two
            # segments that merely cross each other cannot be resolved without picking a
            # victim, so they are reported and the gate refuses to close over them.
            enclosing = None
            if (
                outer_interval[0] - slack <= inner_interval[0]
                and inner_interval[1] <= outer_interval[1] + slack
                and outer_interval != inner_interval
            ):
                enclosing = id(inner)
            elif (
                inner_interval[0] - slack <= outer_interval[0]
                and outer_interval[1] <= inner_interval[1] + slack
                and outer_interval != inner_interval
            ):
                enclosing = id(outer)
            if enclosing is None:
                unresolved_pairs += 1
                traced = outer.trace_id or inner.trace_id or ""
                unresolved_by_trace[traced] = unresolved_by_trace.get(traced, 0) + 1
            else:
                nested_ids.add(enclosing)

    additive = [sample for sample in items if id(sample) not in nested_ids]
    nested = [sample for sample in items if id(sample) in nested_ids]
    nested_ms = round(sum(sample.duration_ms for sample in nested), 6)
    untimed = [
        sample
        for sample in items
        if intervals.get(id(sample)) is None
    ]
    grand_total = round(sum(sample.duration_ms for sample in additive), 6)

    measured_stage: dict[str, list[StageSample]] = {}
    ledger_stage: dict[str, list[StageSample]] = {}
    measured_rest: list[StageSample] = []
    ledger_rest: list[StageSample] = []
    for sample in items:
        if sample.canonical:
            measured_stage.setdefault(sample.stage, []).append(sample)
        else:
            measured_rest.append(sample)
    for sample in additive:
        if sample.canonical:
            ledger_stage.setdefault(sample.stage, []).append(sample)
        else:
            ledger_rest.append(sample)

    stages: dict[str, Any] = {
        stage: _entry(
            measured_stage.get(stage, []),
            ledger_stage.get(stage, []),
            whole_ms=grand_total,
            description=STAGE_DESCRIPTIONS[stage],
        )
        for stage in CANONICAL_STAGES
    }

    unattributed_stats = _entry(measured_rest, ledger_rest, whole_ms=grand_total)
    labels: dict[str, int] = {}
    for sample in measured_rest:
        labels[sample.label or "unattributed"] = labels.get(sample.label or "unattributed", 0) + 1
    unattributed_stats["labels"] = dict(sorted(labels.items()))

    stage_total_ms = round(sum(stats["total_ms"] for stats in stages.values()), 6)
    attributed_total_ms = round(stage_total_ms + unattributed_stats["total_ms"], 6)

    coverage_error_pct: float | None = None
    within_one_percent: bool | None = None
    gap_ms: float | None = None
    over_attribution_ms: float | None = None
    if end_to_end_ms is not None:
        end_to_end = float(end_to_end_ms)
        coverage_error_pct = round(abs(attributed_total_ms - end_to_end) / end_to_end * 100.0, 4) if end_to_end else None
        if coverage_error_pct is not None:
            # An overlap resolved by exclusion is not a reason to fail the gate: the
            # excluded duration is out of the sum, so it cannot inflate the match. A
            # crossing overlap is exactly that reason, because nothing was removed.
            within_one_percent = bool(coverage_error_pct < 1.0 and not unresolved_pairs)
        gap_ms = round(end_to_end - attributed_total_ms, 6)
        over_attribution_ms = round(max(0.0, attributed_total_ms - end_to_end), 6)

    # Judgement 2 is a per-request claim. Rolling one number over every request would
    # let a request that over-attributed cancel one that dropped a segment, so each trace is
    # gated on its own and the rollup reports the worst one.
    per_request: dict[str, Any] = {}
    for trace_id, window_ms in sorted((end_to_end_by_trace or {}).items()):
        members = [sample for sample in additive if sample.trace_id == trace_id]
        segment_sum_ms = round(sum(sample.duration_ms for sample in members), 6)
        window = float(window_ms)
        if window <= 0:
            continue
        error_pct = round(abs(segment_sum_ms - window) / window * 100.0, 4)
        per_request[trace_id] = {
            "segment_sum_ms": segment_sum_ms,
            "end_to_end_ms": round(window, 6),
            "gap_ms": round(window - segment_sum_ms, 6),
            "coverage_error_pct": error_pct,
            "unresolved_overlap_pairs": unresolved_by_trace.get(trace_id, 0),
            "within_one_percent": bool(
                error_pct < 1.0 and not unresolved_by_trace.get(trace_id, 0)
            ),
        }
    coverage: dict[str, Any] = {
        "requests": len(per_request),
        "within_one_percent": (
            None if not per_request else all(item["within_one_percent"] for item in per_request.values())
        ),
        "worst_coverage_error_pct": (
            None if not per_request else max(item["coverage_error_pct"] for item in per_request.values())
        ),
        "per_request": per_request,
    }
    if end_to_end_ms is None and per_request:
        within_one_percent = coverage["within_one_percent"]

    return {
        "schema": "r51.stage-latency/1",
        "sample_count": len(items),
        "stages": stages,
        "unattributed": unattributed_stats,
        "missing_stages": [stage for stage in CANONICAL_STAGES if not stages[stage]["count"]],
        "stage_total_ms": stage_total_ms,
        "attributed_total_ms": attributed_total_ms,
        "end_to_end_ms": None if end_to_end_ms is None else float(end_to_end_ms),
        "coverage_error_pct": coverage_error_pct,
        "within_one_percent": within_one_percent,
        "gap_ms": gap_ms,
        "gap_share_pct": None if gap_ms is None else _percent(max(0.0, gap_ms), float(end_to_end_ms or 0.0)),
        "over_attribution_ms": over_attribution_ms,
        "coverage": coverage,
        "overlap": {
            "pairs": overlap_pairs,
            "unresolved_pairs": unresolved_pairs,
            "nested_samples": len(nested),
            "nested_ms": round(nested_ms, 6),
            "excluded_from_ledger": sorted({sample.label_or_stage for sample in nested}),
            "timed_samples": len(items) - len(untimed),
            "untimed_samples": len(untimed),
            # Timing windows are only comparable when every sample carries both ends;
            # claiming "no overlap" from duration-only samples would be a fake green.
            "measurable": bool(items) and not untimed,
        },
        "lane_source": {
            source: sum(1 for sample in items if (sample.lane_source or LANE_SOURCE_UNKNOWN) == source)
            for source in (LANE_SOURCE_EXPLICIT, LANE_SOURCE_QUESTION, LANE_SOURCE_LOG, LANE_SOURCE_UNKNOWN)
        },
        "lanes": _group_view(
            items, additive, key=lambda sample: sample.lane, whole_ms=grand_total
        ),
        "tiers": _group_view(
            items, additive, key=lambda sample: sample.tier, whole_ms=grand_total
        ),
    }


# ==================== the in-process ledger ====================

#: How many recent samples the readouts keep. It is a rolling window on purpose: the
#: health endpoint answers "what is this process doing now", and an unbounded list in a
#: long-lived private deployment is a memory leak with a nicer name.
DEFAULT_LEDGER_CAPACITY = 2000

_ENABLED_VALUES = {"1", "true", "yes", "on"}
_DISABLED_VALUES = {"0", "false", "no", "off", ""}


def stage_timing_enabled() -> bool:
    """Kill switch for the readout side only (judgement 3).

    Disabled means no sample is added to the ledger; it never changes what a span records
    or how long a request took, so an operator can switch observation off and still get
    the same answer bytes.
    """
    raw = os.getenv("STAGE_TIMING_ENABLED")
    if raw is None:
        return True
    lowered = raw.strip().lower()
    if lowered in _DISABLED_VALUES:
        return False
    return lowered in _ENABLED_VALUES


class StageLedger:
    """Bounded, thread-safe sample buffer feeding ``/health/details`` and the trace API."""

    def __init__(self, capacity: int = DEFAULT_LEDGER_CAPACITY, *, recorder: Callable[[StageSample], None] | None = None):
        self.capacity = max(1, int(capacity))
        self._recorder = recorder
        self._samples: list[StageSample] = []
        self._windows: dict[str, float] = {}
        self._window_order: list[str] = []
        self._lock = threading.Lock()
        self.dropped = 0
        self.failures = 0

    def add(self, sample: StageSample) -> None:
        with self._lock:
            self._samples.append(sample)
            overflow = len(self._samples) - self.capacity
            if overflow > 0:
                del self._samples[:overflow]
                self.dropped += overflow
        if self._recorder is not None:
            try:
                self._recorder(sample)
            except Exception:  # a failing sink is recorded, never propagated
                self.failures += 1

    def samples(self) -> list[StageSample]:
        with self._lock:
            return list(self._samples)

    def add_request_window(self, trace_id: str, duration_ms: float) -> None:
        """Remember one request's wall-clock window so coverage can be gated per request.

        Bounded the same way the samples are: a health readout answers "now", not
        "since the process started".
        """
        trace_id = str(trace_id or "").strip()
        if not trace_id or _duration_ms(duration_ms) is None:
            return
        with self._lock:
            self._windows[trace_id] = float(duration_ms)
            if trace_id in self._window_order:
                self._window_order.remove(trace_id)
            self._window_order.append(trace_id)
            overflow = len(self._window_order) - self.capacity
            if overflow > 0:
                for stale in self._window_order[:overflow]:
                    self._windows.pop(stale, None)
                del self._window_order[:overflow]

    def request_windows(self) -> dict[str, float]:
        with self._lock:
            return dict(self._windows)

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()
            self._windows.clear()
            self._window_order.clear()
            self.dropped = 0
            self.failures = 0

    def report(
        self,
        *,
        end_to_end_ms: float | None = None,
        lane_by_trace: Mapping[str, str] | None = None,
        end_to_end_by_trace: Mapping[str, float] | None = None,
    ) -> dict[str, Any]:
        return aggregate_stage_latency(
            self.samples(),
            end_to_end_ms=end_to_end_ms,
            lane_by_trace=lane_by_trace,
            end_to_end_by_trace=(
                self._windows if end_to_end_by_trace is None else end_to_end_by_trace
            ),
        )


default_ledger = StageLedger()


def default_stage_ledger() -> StageLedger:
    return default_ledger


def reset_stage_ledger() -> None:
    """Forget every buffered sample. Tests and the health readout's own reset path."""
    default_stage_ledger().clear()


def record_stage_sample(**fields: Any) -> StageSample | None:
    """Add one sample from a span payload or a caller. Never raises.

    Observation is a side effect: the caller must not be able to fail a business request
    through it, so anything unexpected is swallowed and counted.
    """
    try:
        if not stage_timing_enabled():
            return None
        payload = dict(fields)
        stage = classify_stage(
            str(payload.pop("stage", "") or ""),
            tool_name=str(payload.pop("tool_name", "") or ""),
            tier=str(payload.get("tier", "") or ""),
            worker=str(payload.get("worker", "") or ""),
        )
        duration_ms = _duration_ms(payload.pop("duration_ms", None))
        if duration_ms is None:
            default_stage_ledger().failures += 1
            return None
        known = {name for name in StageSample.__dataclass_fields__}
        sample = StageSample(stage=stage, duration_ms=duration_ms, **{k: v for k, v in payload.items() if k in known})
    except Exception:  # noqa: BLE001 - judgement 3: a broken collector must be silent
        with contextlib.suppress(Exception):
            default_stage_ledger().failures += 1
        return None
    try:
        default_stage_ledger().add(sample)
    except Exception:  # noqa: BLE001
        return None
    return sample


@contextlib.contextmanager
def stage_window(stage: str, **identity: Any):
    """Time one block of work and hand the sample to the ledger.

    This exists for the segments that are not a model or tool span -- a rule node that
    does real work has no span to inherit. Callers inside files this ticket may not touch
    (``app/rag/**``, ``app/common/model_handler.py``) can adopt it with one line each;
    until they do, the segment shows up in ``missing_stages`` instead of being guessed.
    """
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    sample: StageSample | None = None
    try:
        yield
    finally:
        duration_ms = (time.monotonic() - started) * 1000.0
        fields = dict(identity)
        fields.setdefault("source", "window")
        fields["duration_ms"] = round(duration_ms, 3)
        fields["started_at"] = started_at
        fields["completed_at"] = datetime.now(timezone.utc).isoformat()
        sample = record_stage_sample(stage=stage, **fields)


def with_stage_latency(performance: Mapping[str, Any] | None) -> dict[str, Any]:
    """Extend the ``/health/details`` performance block with the stage ledger.

    Additive on purpose: the keys the endpoint already answers with keep their values,
    so a consumer of ``performance.p95_ms`` cannot tell that this ticket happened.
    """
    report = dict(performance or {})
    try:
        # ``total_ms`` is every request this process served added together, which is
        # not an end-to-end window; coverage comes from the per-request windows only.
        stages = default_stage_ledger().report()
        report["stages"] = stages["stages"]
        report["unattributed"] = stages["unattributed"]
        report["missing_stages"] = stages["missing_stages"]
        report["coverage_error_pct"] = stages["coverage_error_pct"]
        report["within_one_percent"] = stages["within_one_percent"]
        report["overlap"] = stages["overlap"]
        report["gap_ms"] = stages["gap_ms"]
        report["coverage"] = stages["coverage"]
        report["lanes"] = stages["lanes"]
        report["tiers"] = stages["tiers"]
        report["stage_timing_enabled"] = stage_timing_enabled()
    except Exception as exc:  # a health readout must not fail because of telemetry
        report["stage_latency_error"] = type(exc).__name__
    return report


def stage_latency_readout(
    *,
    end_to_end_ms: float | None = None,
    lane_by_trace: Mapping[str, str] | None = None,
    end_to_end_by_trace: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """What the read endpoints answer with: the ledger, plus the sample list itself."""
    ledger = default_stage_ledger()
    report = ledger.report(
        end_to_end_ms=end_to_end_ms,
        lane_by_trace=lane_by_trace,
        end_to_end_by_trace=end_to_end_by_trace,
    )
    report["samples"] = [sample.as_dict() for sample in ledger.samples()]
    report["capacity"] = ledger.capacity
    report["dropped"] = ledger.dropped
    report["collector_failures"] = ledger.failures
    report["enabled"] = stage_timing_enabled()
    return report


__all__ = [
    "CANONICAL_STAGES",
    "DEFAULT_LEDGER_CAPACITY",
    "FINISHED_EVENTS",
    "LaneTier",
    "R42_LOG_PATTERN",
    "R42_PLAN_SKIP_PATTERN",
    "STAGE_DESCRIPTIONS",
    "StageLedger",
    "StageSample",
    "aggregate_stage_latency",
    "classify_stage",
    "default_stage_ledger",
    "lane_tier_for_question",
    "parse_r42_log_line",
    "record_stage_sample",
    "reset_stage_ledger",
    "samples_from_events",
    "samples_from_span_payload",
    "stage_latency_readout",
    "to_epoch_ms",
    "stage_timing_enabled",
    "stage_window",
    "with_stage_latency",
]
