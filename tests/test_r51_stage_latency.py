"""R51 stage-level P50/P95: the numbers must exist, add up, and attribute to a lane.

Judgement map (backend followup ticket 21 R51):
  1 -> stages ①: every named segment reports P50 and P95, from the shared percentile
     skeleton, with no second convention invented.
  2 -> coverage ②: the segments of one request must add up to that request within 1%,
     and the three ways to fake that (a dropped segment, overlapping segments, double
     counting) each have their own case.
  4 -> lanes ④: cost share reads back per lane and per tier, with lane and tier resolved
     by R42 itself rather than by a copy of its rules.
  5 -> offline ⑤: nothing here opens a socket, a vector store or a server.

Judgement 3 (observation must not change behaviour) is in
``tests/test_r51_observation_is_passive.py``, because it needs the live span path.
"""
from __future__ import annotations

import json

import pytest

from app.common.performance import PerformanceStats
from app.common.stage_timing import (
    CANONICAL_STAGES,
    StageSample,
    StageLedger,
    aggregate_stage_latency,
    classify_stage,
    default_stage_ledger,
    lane_tier_for_question,
    parse_r42_log_line,
    request_windows_from_events,
    reset_stage_ledger,
    record_stage_sample,
    samples_from_events,
    stage_timing_enabled,
    with_stage_latency,
)

TRACE_ID = "trace-r51"
REQUEST_ID = "request-r51"

#: The eleven rows of docs/perf/latency-budget-2026-09-16.md table 1, in seconds, exactly
#: as that measurement wrote them down. They are the reference judgement 2 is aligned to:
#: the sum is 160.552 s against a log-reported 160.6 s, i.e. an error of 0.03%.
LATENCY_BUDGET_ROWS: tuple[tuple[str, str, float], ...] = (
    ("classify", "rule: classify + deterministic plan + memory", 0.081),
    ("classify", "supervisor decision", 27.797),
    ("classify", "rule: route dispatch", 0.071),
    ("generate", "doc worker roundtrip 1", 24.046),
    ("rewrite", "multi-query rewrite", 41.581),
    ("retrieve", "retrieval body", 0.242),
    ("generate", "doc worker roundtrip 2", 50.448),
    ("classify", "supervisor roundtrip 2", 15.931),
    ("reflect", "reflect review", 0.033),
    ("classify", "rule: synthesis + checkpoint + trace", 0.322),
)
LATENCY_BUDGET_END_TO_END_MS = 160_600.0


@pytest.fixture(autouse=True)
def isolated_ledger(monkeypatch):
    """One clean ledger per case, and no dependence on the operator's environment."""
    monkeypatch.delenv("STAGE_TIMING_ENABLED", raising=False)
    reset_stage_ledger()
    yield default_stage_ledger()
    reset_stage_ledger()


def _sample(stage: str, duration_ms: float, **kwargs) -> StageSample:
    return StageSample(stage=stage, duration_ms=duration_ms, **kwargs)


def _samples_per_stage(per_stage: int = 20) -> list[StageSample]:
    return [
        _sample(stage, float(index))
        for stage in CANONICAL_STAGES
        for index in range(1, per_stage + 1)
    ]


def _config(**extra):
    from app.agents.contracts import Principal

    configurable = {
        "principal": Principal(user_id="u-r51", username="staff1", roles=["staff"], department="研发部"),
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
    }
    configurable.update(extra)
    return {"configurable": configurable}


# ==================== judgement 1: every segment answers P50 and P95 ====================


def test_canonical_stage_names_are_the_five_ticket_stages() -> None:
    assert CANONICAL_STAGES == ("classify", "rewrite", "retrieve", "generate", "reflect")


def test_p50_and_p95_are_reportable_for_every_stage() -> None:
    report = aggregate_stage_latency(_samples_per_stage())

    assert set(CANONICAL_STAGES) <= set(report["stages"])
    for stage in CANONICAL_STAGES:
        stats = report["stages"][stage]
        assert stats["count"] == 20, stage
        assert stats["p50_ms"] == 10.0, stage
        assert stats["p95_ms"] == 19.0, stage
        assert stats["total_ms"] == 210.0, stage
    assert report["missing_stages"] == []


def test_percentile_skeleton_reports_p50_and_p95_from_one_rank_rule() -> None:
    """The existing p95 convention was reused, not reimplemented, and the old keys hold."""
    stats = PerformanceStats()
    for value in [100, 120, 180, 240, 500, 300]:
        stats.observe(value)

    report = stats.report()

    assert report["count"] == 6
    assert report["p95_ms"] == 500
    assert report["error_rate"] == 0.0
    assert report["p50_ms"] == 180
    assert report["total_ms"] == 1440
    assert report["max_ms"] == 500
    assert stats.percentile(0.5) == 180


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"tool_name": "search_docs"}, "retrieve"),
        ({"tool_name": "analyze_data"}, "generate"),
        ({"tier": "rewrite"}, "rewrite"),
        ({"tier": "plan"}, "classify"),
        ({"tier": "chat"}, "generate"),
        ({"tier": "code"}, "generate"),
        ({"worker": "chart"}, "generate"),
        ({"stage": "reflect", "tool_name": "search_docs"}, "reflect"),
    ],
)
def test_stage_labels_come_from_tools_tiers_and_workers(kwargs, expected) -> None:
    assert classify_stage(**kwargs) == expected


def test_supervisor_call_is_classify_and_worker_call_is_generate() -> None:
    """Both are ``analysis``-tier model calls; only the worker identity separates them."""
    assert classify_stage("", tier="analysis", worker="") == "classify"
    assert classify_stage("", tier="analysis", worker="doc") == "generate"


def test_tiers_outside_the_five_segments_are_never_folded_in() -> None:
    for tier in ("compress", "alert"):
        assert classify_stage("", tier=tier) == ""
    assert classify_stage("", tool_name="export_report") == ""


def test_unattributed_samples_keep_their_label() -> None:
    report = aggregate_stage_latency(
        [_sample("classify", 10.0), _sample("", 40.0, tier="compress", label="compress")]
    )

    assert report["stages"]["classify"]["count"] == 1
    assert report["unattributed"]["count"] == 1
    assert report["unattributed"]["total_ms"] == 40.0
    assert report["unattributed"]["labels"] == {"compress": 1}
    assert report["attributed_total_ms"] == 50.0


# ==================== judgement 2: the segments must add up to the request ====================


def test_segments_that_add_up_to_the_request_pass_the_one_percent_gate() -> None:
    samples = _samples_per_stage()
    total = sum(sample.duration_ms for sample in samples)

    report = aggregate_stage_latency(samples, end_to_end_ms=total)

    assert report["coverage_error_pct"] == 0.0
    assert report["within_one_percent"] is True
    assert report["gap_ms"] == 0.0


def test_the_latency_budget_table_still_adds_up_to_its_own_end_to_end() -> None:
    """Judgement 2 aligned to the reference: 160.552 s of rows against a 160.6 s request."""
    samples = [
        _sample(stage, seconds * 1000.0, label=label, trace_id="budget")
        for stage, label, seconds in LATENCY_BUDGET_ROWS
    ]

    report = aggregate_stage_latency(samples, end_to_end_ms=LATENCY_BUDGET_END_TO_END_MS)

    assert report["attributed_total_ms"] == pytest.approx(160_552.0, abs=0.01)
    assert report["coverage_error_pct"] == pytest.approx(0.0299, abs=0.001)
    assert report["coverage_error_pct"] < 0.03
    assert report["within_one_percent"] is True


def test_a_dropped_segment_breaks_the_gate_and_grows_the_gap() -> None:
    """The obvious fraud: leave the 41.581 s rewrite row out and claim the sum matched."""
    samples = [
        _sample(stage, seconds * 1000.0, label=label)
        for stage, label, seconds in LATENCY_BUDGET_ROWS
        if "rewrite" not in label
    ]

    report = aggregate_stage_latency(samples, end_to_end_ms=LATENCY_BUDGET_END_TO_END_MS)

    assert report["coverage_error_pct"] > 25.0
    assert report["within_one_percent"] is False
    # 41.629 s, not 41.581 s: the budget table already left 48 ms of its own request
    # unattributed, and the gap has to carry that too or it is a second fudge.
    assert report["gap_ms"] == pytest.approx(41_629.0, abs=0.01)
    assert report["missing_stages"] == ["rewrite"]


def test_a_tiny_dropped_segment_stays_under_the_gate_so_the_ledger_lists_it() -> None:
    """The limit of a 1% gate, written down instead of hidden.

    One percent of a 160.6 s request is 1.606 s, so a segment of 0.033 s can never be
    caught by the percentage. The backstop is that the report still names the segment that
    has no samples at all, which is why both assertions are in this one case.
    """
    samples = [
        _sample(stage, seconds * 1000.0, label=label)
        for stage, label, seconds in LATENCY_BUDGET_ROWS
        if "reflect" not in label
    ]

    report = aggregate_stage_latency(samples, end_to_end_ms=LATENCY_BUDGET_END_TO_END_MS)

    assert report["coverage_error_pct"] < 1.0
    assert report["missing_stages"] == ["reflect"]

def test_the_one_percent_gate_is_a_knife_edge_not_a_round_number() -> None:
    """The aggregate gate has to fail at 1.01%, or "within 1%" is a slogan.

    9,899 ms attributed against a 10,000 ms request is 1.01%; 9,901 ms is 0.99%. Only a
    threshold of exactly one percent separates the two, so a gate loosened to five percent
    reddens the second case and a gate tightened below it reddens the first.
    """
    tight = aggregate_stage_latency(
        [_sample("generate", 9_901.0, trace_id="tight")], end_to_end_ms=10_000.0
    )
    loose = aggregate_stage_latency(
        [_sample("generate", 9_899.0, trace_id="loose")], end_to_end_ms=10_000.0
    )

    assert tight["coverage_error_pct"] == pytest.approx(0.99, abs=0.001)
    assert tight["within_one_percent"] is True
    assert loose["coverage_error_pct"] == pytest.approx(1.01, abs=0.001)
    assert loose["within_one_percent"] is False


def test_the_per_request_gate_is_a_knife_edge_too() -> None:
    """Same edge on the path that actually enforces it, request by request."""
    report = aggregate_stage_latency(
        [
            _sample("generate", 9_901.0, trace_id="tight"),
            _sample("generate", 9_899.0, trace_id="loose"),
        ],
        end_to_end_by_trace={"tight": 10_000.0, "loose": 10_000.0},
    )

    per_request = report["coverage"]["per_request"]
    assert per_request["tight"]["within_one_percent"] is True
    assert per_request["loose"]["within_one_percent"] is False
    assert report["coverage"]["within_one_percent"] is False



def test_overlapping_segments_cannot_pass_the_gate_even_when_the_sum_matches() -> None:
    """The second fraud: two segments measured over each other, totals made to fit.

    60 ms and 90 ms crossing at 30 ms add up to exactly a 150 ms request, so the
    arithmetic alone would call this clean. Neither window contains the other, which is
    what makes it unresolved, and an unresolved overlap is a red gate by itself.
    """
    samples = [
        _sample(
            "generate",
            60.0,
            trace_id="t",
            started_at="2026-09-18T06:00:00+00:00",
            completed_at="2026-09-18T06:00:00.060+00:00",
            label="generate",
        ),
        _sample(
            "retrieve",
            90.0,
            trace_id="t",
            started_at="2026-09-18T06:00:00.030+00:00",
            completed_at="2026-09-18T06:00:00.120+00:00",
            label="retrieve",
        ),
    ]

    report = aggregate_stage_latency(
        samples, end_to_end_ms=150.0, end_to_end_by_trace={"t": 150.0}
    )

    assert report["attributed_total_ms"] == 150.0
    assert report["coverage_error_pct"] == 0.0
    assert report["overlap"]["pairs"] == 1
    assert report["overlap"]["unresolved_pairs"] == 1
    assert report["overlap"]["nested_samples"] == 0
    assert report["overlap"]["measurable"] is True
    assert report["within_one_percent"] is False

    per_request = report["coverage"]["per_request"]
    assert per_request["t"]["coverage_error_pct"] == 0.0
    assert per_request["t"]["unresolved_overlap_pairs"] == 1
    assert per_request["t"]["within_one_percent"] is False


def test_a_tool_span_containing_a_model_span_is_excluded_from_the_sum_not_double_counted() -> None:
    """The honest shape: retrieval contains the rewrite call it triggered."""
    outer = _sample(
        "retrieve",
        500.0,
        trace_id="t",
        source="tool_span",
        started_at="2026-09-18T06:00:00+00:00",
        completed_at="2026-09-18T06:00:00.500+00:00",
    )
    inner = _sample(
        "rewrite",
        400.0,
        trace_id="t",
        source="model_span",
        started_at="2026-09-18T06:00:00.050+00:00",
        completed_at="2026-09-18T06:00:00.450+00:00",
    )

    # The retrieval span is the whole window here, so the only thing that could push the
    # sum past 1% is counting the rewrite call a second time.
    report = aggregate_stage_latency([outer, inner], end_to_end_ms=500.0)

    assert report["overlap"]["pairs"] == 1
    assert report["overlap"]["unresolved_pairs"] == 0
    assert report["overlap"]["nested_samples"] == 1
    assert report["overlap"]["nested_ms"] == 400.0
    assert report["overlap"]["excluded_from_ledger"] == ["rewrite"]
    assert report["attributed_total_ms"] == 500.0
    # Both segments still answer P50/P95 -- exclusion is about the sum, not about hiding.
    assert report["stages"]["rewrite"]["count"] == 1
    assert report["stages"]["rewrite"]["p95_ms"] == 400.0
    assert report["within_one_percent"] is True


def test_double_counting_over_attributes_and_gates_red() -> None:
    """The third fraud: the same second billed twice lands on the wrong side of the sum."""
    samples = [
        _sample("generate", 80.0, trace_id="t"),
        _sample("generate", 80.0, trace_id="t", label="duplicate"),
    ]

    report = aggregate_stage_latency(samples, end_to_end_ms=80.0)

    assert report["attributed_total_ms"] == 160.0
    assert report["over_attribution_ms"] == 80.0
    assert report["coverage_error_pct"] == 100.0
    assert report["within_one_percent"] is False


def test_end_to_end_window_comes_from_the_trace_events_themselves() -> None:
    """No new clock: the denominator is request.completed minus request.started."""
    events = [
        {"trace_id": "t", "event_type": "request.started", "timestamp": "2026-09-16T13:58:11.792+00:00"},
        {"trace_id": "t", "event_type": "step.finished", "timestamp": "2026-09-16T14:00:40.000+00:00"},
        {"trace_id": "t", "event_type": "request.completed", "timestamp": "2026-09-16T14:00:52.344+00:00"},
    ]

    windows = request_windows_from_events(events)

    assert windows == {"t": pytest.approx(160_552.0, abs=0.5)}


def test_the_gate_is_per_request_so_two_wrong_requests_cannot_cancel_out() -> None:
    samples = [
        _sample("generate", 200.0, trace_id="short"),
        _sample("generate", 800.0, trace_id="long"),
    ]

    report = aggregate_stage_latency(
        samples, end_to_end_by_trace={"short": 900.0, "long": 100.0}
    )

    coverage = report["coverage"]
    assert coverage["requests"] == 2
    assert coverage["per_request"]["short"]["coverage_error_pct"] == pytest.approx(77.7778, abs=0.01)
    assert coverage["per_request"]["long"]["coverage_error_pct"] == pytest.approx(700.0, abs=0.01)
    assert coverage["within_one_percent"] is False
    assert coverage["worst_coverage_error_pct"] == 700.0
    assert report["within_one_percent"] is False


def test_the_health_block_does_not_mistake_the_sum_of_requests_for_one_request() -> None:
    """``total_ms`` in the end-to-end block is every request added together."""
    record_stage_sample(stage="generate", duration_ms=1000.0, trace_id="a")
    record_stage_sample(stage="generate", duration_ms=1000.0, trace_id="b")

    block = with_stage_latency({"count": 2, "total_ms": 2000.0, "p95_ms": 1000.0})

    assert block["count"] == 2
    assert block["total_ms"] == 2000.0
    assert block["coverage"]["requests"] == 0
    assert block["coverage_error_pct"] is None


# ==================== judgement 4: R42 cost share, read back ====================


def _lane_samples() -> list[StageSample]:
    return [
        _sample("classify", 1_000.0, trace_id="fast", lane="qa", tier="chat"),
        _sample("retrieve", 242.0, trace_id="fast", lane="qa", tier="chat"),
        _sample("generate", 22_000.0, trace_id="fast", lane="qa", tier="chat"),
        _sample("classify", 27_000.0, trace_id="slow", lane="analysis", tier="analysis"),
        _sample("rewrite", 41_581.0, trace_id="slow", lane="analysis", tier="analysis"),
        _sample("retrieve", 300.0, trace_id="slow", lane="analysis", tier="analysis"),
        _sample("generate", 50_000.0, trace_id="slow", lane="analysis", tier="analysis"),
    ]


def test_cost_share_reads_back_per_lane_and_tier() -> None:
    report = aggregate_stage_latency(_lane_samples())

    assert report["lanes"]["qa"]["total_ms"] == 23_242.0
    assert report["lanes"]["analysis"]["total_ms"] == 118_881.0
    assert report["lanes"]["qa"]["requests"] == 1
    assert report["lanes"]["qa"]["share_pct"] == pytest.approx(16.3548, abs=0.01)
    assert report["lanes"]["analysis"]["share_pct"] == pytest.approx(83.6452, abs=0.01)
    assert report["lanes"]["analysis"]["stages"]["rewrite"]["p95_ms"] == 41_581.0
    assert report["lanes"]["qa"]["stages"]["rewrite"]["count"] == 0
    assert report["tiers"]["chat"]["total_ms"] == 23_242.0
    assert report["tiers"]["analysis"]["stages"]["generate"]["share_pct"] == pytest.approx(
        50_000.0 / 118_881.0 * 100.0, abs=0.01
    )


def test_lane_shares_add_up_to_the_whole_request() -> None:
    report = aggregate_stage_latency(_lane_samples())

    assert sum(view["share_pct"] for view in report["lanes"].values()) == pytest.approx(100.0, abs=0.01)
    assert sum(view["share_pct"] for view in report["stages"].values()) == pytest.approx(100.0, abs=0.01)


def test_lane_and_tier_are_resolved_by_r42_itself() -> None:
    """The readback must not drift from the discriminator: ask classify_route, do not copy it."""
    from app.agents.nodes import classify_route

    questions = {
        "trace-fast": "住宿费的标准是多少？",
        "trace-slow": "统计各季度营收并且画成柱状图",
    }
    samples = [_sample("generate", 500.0, trace_id=trace_id) for trace_id in sorted(questions)]

    report = aggregate_stage_latency(samples, lane_by_trace=questions)

    for trace_id, question in questions.items():
        resolved = lane_tier_for_question(question)
        assert resolved.lane == classify_route(question).lane
        assert resolved.tier == classify_route(question).tier.value
    assert set(report["lanes"]) == {"qa", "analysis"}
    assert report["stages"]["generate"]["count"] == 2
    assert report["lane_source"]["r42_question"] == 2
    assert report["lane_source"]["unknown"] == 0


def test_samples_that_arrive_with_a_lane_keep_it() -> None:
    sample = _sample("generate", 100.0, trace_id="t", lane="report", tier="analysis")

    report = aggregate_stage_latency([sample], lane_by_trace={"t": "住宿费的标准是多少？"})

    assert report["lanes"]["report"]["total_ms"] == 100.0
    assert "qa" not in report["lanes"]


def test_unlabelled_lanes_are_reported_as_unknown_instead_of_a_split_invented_here() -> None:
    report = aggregate_stage_latency([_sample("generate", 100.0, trace_id="t")])

    assert report["lanes"]["unknown"]["count"] == 1
    assert report["lane_source"]["unknown"] == 1
    assert report["lane_source"]["r42_question"] == 0


def test_log_anchors_are_parsed_from_the_bytes_the_code_actually_writes(monkeypatch) -> None:
    """The [R42] line is the readback anchor: capture what classify_route really logs.

    The wording is owned by another ticket and pinned elsewhere, so this case reads the
    real logger output instead of restating the format, and fails if the two ever drift.
    """
    import app.agents.nodes as nodes

    logged: list[str] = []

    class _Recorder:
        def info(self, message, *args):
            logged.append(str(message) % args if args else str(message))

        def warning(self, message, *args):
            logged.append(str(message) % args if args else str(message))

    monkeypatch.setattr(nodes, "logger", _Recorder())
    decision = nodes.classify_route("统计各季度营收并且画成柱状图")
    assert logged, "classify_route no longer logs the discriminator verdict"

    parsed = parse_r42_log_line("\n".join(logged))

    assert parsed.lane == decision.lane
    assert parsed.tier == decision.tier.value
    assert parsed.rule == decision.rule
    assert parsed.source == "r42_log"


def test_plan_skip_anchor_reads_as_the_qa_lane() -> None:
    parsed = parse_r42_log_line("[Plan] 问答档 → 不拆题")

    assert parsed.lane == "qa"
    assert parsed.rule == "plan_skipped"
    assert parse_r42_log_line("[Plan] 3 个子任务").lane == ""


def test_log_parsing_survives_a_line_that_is_not_the_anchor() -> None:
    assert parse_r42_log_line("").lane == ""
    assert parse_r42_log_line("2026-09-18 14:00:00 | INFO | some other text").lane == ""


# ==================== the live boundary feeding the ledger and the readouts ====================


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    from app.trace.store import TraceStore

    store = TraceStore(tmp_path / "traces" / "events.jsonl")
    from app.trace import spans

    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    return store


def _finish_real_spans() -> None:
    """Produce model and tool spans the way the pipeline does, then close them."""
    import time

    from app.trace.spans import start_model_call, start_tool_call

    supervisor = start_model_call(_config(), provider="ollama", model_name="qwen3.5:9b", model_tier="analysis")
    time.sleep(0.005)
    supervisor.finish("completed")

    rewrite = start_model_call(_config(), provider="ollama", model_name="qwen3.5:9b", model_tier="rewrite")
    time.sleep(0.002)
    rewrite.finish("completed")

    with start_tool_call(_config(), tool_name="search_docs", arguments={"query": "住宿费标准"}) as span:
        time.sleep(0.002)
        span.finish("completed", summary={"hit_count": 3})

    worker = start_model_call(
        _config(worker="doc"), provider="ollama", model_name="qwen3.5:9b", model_tier="analysis"
    )
    time.sleep(0.003)
    worker.finish("completed")


def test_a_finished_span_lands_in_the_ledger_under_its_own_segment(trace_store) -> None:
    _finish_real_spans()

    stages = default_stage_ledger().report()["stages"]

    assert stages["classify"]["count"] == 1
    assert stages["rewrite"]["count"] == 1
    assert stages["retrieve"]["count"] == 1
    assert stages["generate"]["count"] == 1
    assert stages["reflect"]["count"] == 0


def test_a_model_built_by_the_production_factory_reports_its_own_tier(trace_store) -> None:
    """Judgement 4's production pin: the tier that sized the budget is the tier the span carries.

    ``_make_model`` is the only model factory the pipeline uses and ``_span`` is the only
    place that model opens a span, so this walks the real chain from a tier to a segment
    instead of a hand-built stand-in. The conftest sentinel does set ``LOCAL_MODEL_NAME``,
    and the factory treats a configured name as a usable model, which is what makes it
    return a ``_ResilientModel`` here rather than the offline stub -- ``_make_model`` only
    returns ``_OfflineModel`` when the resolved name is empty. Nothing is invoked, so no
    socket is opened.
    """
    import time

    from app.agents import nodes
    from app.agents.contracts import ModelTier

    for tier, worker in ((ModelTier.PLAN, ""), (ModelTier.CHAT, "doc")):
        model = nodes._make_model(tier, prompt="住宿费标准是什么")
        assert isinstance(model, nodes._ResilientModel), tier
        span = model._span(_config(worker=worker))
        assert span.base_payload.get("model_tier") == tier.value
        time.sleep(0.002)
        span.finish("completed")

    finished = [event for event in trace_store.replay(TRACE_ID) if event["event_type"] == "model.finished"]
    assert [event["payload"]["model_tier"] for event in finished] == ["plan", "chat"]

    stages = default_stage_ledger().report()["stages"]
    assert stages["classify"]["count"] == 1
    assert stages["generate"]["count"] == 1
    assert stages["rewrite"]["count"] == 0


def test_replaying_a_persisted_trace_rebuilds_the_same_segments(trace_store) -> None:
    _finish_real_spans()

    events = trace_store.replay(TRACE_ID)
    report = aggregate_stage_latency(samples_from_events(events))

    assert [event["event_type"] for event in events].count("model.finished") == 3
    assert report["stages"]["rewrite"]["p50_ms"] == report["stages"]["rewrite"]["p95_ms"]
    assert report["stages"]["retrieve"]["count"] == 1
    assert report["sample_count"] == 4


def test_reflect_and_a_rule_segment_have_no_span_source_and_say_so(trace_store) -> None:
    """Honest hole: the segments that are pure rules never cross a span boundary.

    ``reflect`` is a rule pass (latency budget: 0.033 s, zero model calls) and the query
    rewriter runs behind app/common/model_handler.py, which this ticket may not touch.
    Neither one crosses a model or tool boundary, so a single chat-tier call leaves four
    of the five segments empty, and the report says which four.
    Its tier is recognised the moment a span carries it -- see the rewrite case above --
    but today the rewriter never opens one, so the only way a rewrite sample exists is a
    caller adopting ``stage_window`` or ``record_stage_event``.
    """
    from app.trace.spans import start_model_call

    span = start_model_call(_config(), provider="ollama", model_name="m", model_tier="chat")
    span.finish("completed")

    report = default_stage_ledger().report()

    assert report["missing_stages"] == ["classify", "rewrite", "retrieve", "reflect"]


def test_health_details_carries_the_stage_block(trace_store, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.common import auth, monitoring
    from app.main import app

    monkeypatch.setattr(monitoring, "_probe_ollama", lambda: {"status": "not_configured"})
    monkeypatch.setattr(monitoring, "_probe_postgres", lambda: {"status": "not_configured"})
    monkeypatch.setattr(monitoring, "_probe_redis", lambda: {"status": "not_configured"})
    _finish_real_spans()

    response = TestClient(app).get(
        "/api/v1/health/details", headers={"Authorization": f"Bearer {auth.create_token('admin')}"}
    )

    assert response.status_code == 200
    performance = response.json()["performance"]
    assert set(CANONICAL_STAGES) <= set(performance["stages"])
    assert performance["stages"]["generate"]["count"] >= 1
    assert performance["stage_timing_enabled"] is True
    assert "coverage" in performance and "overlap" in performance
    assert performance["missing_stages"] == ["reflect"]


def test_the_stage_latency_route_reads_one_persisted_trace(trace_store, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.api.v1 import observability
    from app.common.auth import create_token
    from app.main import app

    monkeypatch.setattr(observability, "_trace_store", lambda: trace_store)
    _finish_real_spans()

    response = TestClient(app).get(
        "/api/v1/stage-latency",
        params={"trace_id": TRACE_ID, "include_samples": True},
        headers={"Authorization": f"Bearer {create_token('admin')}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "trace"
    assert body["stages"]["retrieve"]["count"] == 1
    assert body["samples"][0]["trace_id"] == TRACE_ID
    assert json.dumps(body, ensure_ascii=False, default=str)


def test_the_stage_latency_route_needs_the_audit_permission() -> None:
    """A request with no principal must not infer an identity or fall back to admin."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1 import observability

    bare = FastAPI()
    bare.include_router(observability.router, prefix="/api/v1")

    response = TestClient(bare).get("/api/v1/stage-latency")

    assert response.status_code == 401
    envelope = response.json()["detail"]
    assert set(envelope) == {"code", "message", "retryable", "details"}
    assert envelope["code"] == "authentication_required"
    assert envelope["retryable"] is False


# ==================== the ledger buffer is bounded, both halves of it ====================


def test_the_ledger_evicts_oldest_samples_once_it_is_full() -> None:
    """A health readout answers "now"; a buffer that never evicts is a leak with a UI.

    Written because the acceptance knife that set the capacity to one billion changed
    nothing here: the class docstring promised a bound the tests never asked for.
    """
    ledger = StageLedger(capacity=3)

    for index in range(5):
        ledger.add(_sample("generate", float(index)))

    assert [sample.duration_ms for sample in ledger.samples()] == [2.0, 3.0, 4.0]
    assert ledger.dropped == 2


def test_the_request_window_buffer_is_bounded_too() -> None:
    """The windows that gate coverage are trimmed by the same rule, or they outlive the samples."""
    ledger = StageLedger(capacity=2)
    for trace_id in ("a", "b", "c"):
        ledger.add(_sample("generate", 100.0, trace_id=trace_id))
        ledger.add_request_window(trace_id, 100.0)

    assert set(ledger.request_windows()) == {"b", "c"}
    assert ledger.report()["coverage"]["requests"] == 2
