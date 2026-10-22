"""R99: the model budget may not contradict itself, and it may not answer for the model.

Two defects, one family. The analysis tier's own worst case (1536 tokens at the CPU-only
calibration in ``app/common/model_budget.py``) needs 192 s of clock while the ceiling for one
request is 120 s, so every analysis call announced ``clamped=yes`` and then spent the full
ceiling and came back as an offline sentence. And on the machine that actually ships -- GPU,
~37 tok/s, where that arithmetic would fit -- qwen3.5:9b spends a 1024 or 1536 token cap
entirely on hidden reasoning and returns **zero visible characters**, which the same path then
delivered as an answer.

Each test below removes one of those endings, or pins the measurement that decides them. The
expected numbers are written out here rather than re-derived from the production formula, so
changing the formula has to be argued with a failing test.
"""

import logging
import os
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents import nodes
from app.agents.contracts import (
    CONTEXT_LIMIT_CODE,
    MODEL_BUDGET_MARKER as MARKER,
    OUTPUT_TRUNCATED_CODE,
    STREAM_STALL_TOKENS,
    ModelTier,
)
from app.agents.evidence import build_agent_result, new_evidence_bag
from app.common import model_budget
from app.common.model_budget import (
    DEFAULT_DECODE_TOKENS_PER_SECOND,
    DEFAULT_MIN_ANSWER_TOKENS,
    DEFAULT_PREFILL_TOKENS_PER_SECOND,
    NO_ANSWER_CODE,
    TIMEOUT_ERROR_CODE,
    answer_text,
    authorize,
    authorize_call,
    budget_event_counts,
    clock_affordable_tokens,
    detect_empty_answer,
    max_tokens_verdict,
    min_answer_tokens,
    model_budget_readout,
    model_tier_budget,
    model_timeout_code,
    reset_budget_events,
    thinking_extra_body,
    tier_max_tokens,
)

_REPOSITORY = Path(__file__).resolve().parents[1]
BENCH_SCRIPT = _REPOSITORY / "scripts" / "bench_model_throughput.py"
ALL_TIERS = sorted(ModelTier, key=lambda tier: tier.value)

#: A measured prompt, small enough that prefill stays a rounding error in the stories below.
PROMPT_TOKENS = 100

#: One CJK character estimates to one token and each message adds MESSAGE_OVERHEAD_TOKENS=4,
#: so this body is exactly PROMPT_TOKENS... no: it is used where a call site's *estimate* is
#: what matters, and the number is spelled out at each use instead of being trusted here.
PROMPT_BODY = "数" * 485

#: The rates the shipping container measured on 2026-09-19 (qwen3.5:9b, 100% GPU, ~37 tok/s).
GPU_PREFILL = "105"
GPU_DECODE = "37"


@pytest.fixture(autouse=True)
def _clean_budget_environment(monkeypatch):
    """Every knob back to its shipped value and the counters to zero.

    The counters are process-wide on purpose -- that is what makes them countable from a
    health surface -- so a test that reads them has to be able to start from zero.

    ``reset_default_budget`` is load-bearing here and not decoration: the concurrency slot pool
    is one cached process-wide object, and ``_ResilientModel.stream()`` never releases the slot
    it took, neither on the success path nor on the ordinary-failure path (pre-existing,
    reported to the coordinator: with MODEL_MAX_CONCURRENCY=1 every streamed answer eats a
    slot for the life of the process). Without the reset the first stream test in this file
    passes and every later one is answered by the offline fallback, which looks exactly like a
    bug in the code under test.
    """
    for name in (
        "MODEL_PREFILL_TOKENS_PER_SECOND",
        "MODEL_DECODE_TOKENS_PER_SECOND",
        "MODEL_MIN_ANSWER_TOKENS",
        "MODEL_REQUEST_TIMEOUT",
        "MODEL_TIMEOUT_MARGIN",
        "MODEL_CONTEXT_TOKENS",
        "MODEL_TIER_ANALYSIS_MAX_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)
    model_budget.reset_default_budget()
    reset_budget_events()
    yield
    model_budget.reset_default_budget()
    reset_budget_events()


def _calibrated_gpu(monkeypatch, context_tokens: str = "4096", analysis_cap: str | None = None):
    """Point the budget at the container's measured throughput, and a window that can hold it."""
    monkeypatch.setenv("MODEL_PREFILL_TOKENS_PER_SECOND", GPU_PREFILL)
    monkeypatch.setenv("MODEL_DECODE_TOKENS_PER_SECOND", GPU_DECODE)
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", context_tokens)
    if analysis_cap:
        monkeypatch.setenv("MODEL_TIER_ANALYSIS_MAX_TOKENS", analysis_cap)


class _RecordingModel:
    """Stand-in provider: records the wire arguments, opens no socket."""

    def __init__(self, response=None, error: Exception | None = None):
        self.calls: list[dict] = []
        self.response = response if response is not None else AIMessage(
            content="答案", response_metadata={"finish_reason": "stop"}
        )
        self.error = error

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response

    def stream(self, *args, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        yield from self.response

    def bind_tools(self, tools):
        return self


class _OfflineReply:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages, config=None, **kwargs):
        self.calls += 1
        return AIMessage(content="离线模式已启用，但我仍可以继续帮你梳理问题。")

    def stream(self, *args, **kwargs):
        yield AIMessage(content="离线模式已启用")


def _resilient(tier: ModelTier, primary, offline=None):
    """A model built the way ``_make_model`` builds one, including the shared budget object."""
    return nodes._ResilientModel(
        primary,
        offline or _OfflineReply(),
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(tier),
    )


def _config():
    bag = new_evidence_bag()
    return {
        "configurable": {
            "evidence_bag": bag,
            "principal": {"user_id": "u-99", "username": "staff99", "roles": ["staff"]},
            "trace_id": "trace-r99",
            "request_id": "req-r99",
            "task_id": "task-r99",
        }
    }, bag


def _span_rows(tmp_path, monkeypatch):
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace import spans
    from app.trace.store import TraceStore

    store = TraceStore(
        tmp_path / "spans.jsonl", persistence=JsonPersistenceAdapter(tmp_path / "spans.json")
    )
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    return store


def _provider_rows(store):
    return [row for row in store.persistence.list("model_calls") if row["provider"] != "offline"]


def _unused_local_port() -> int:
    """A port nothing is listening on: a refused connect, not a slow one.

    Never 11434: tests must not touch the host model server (R56), and a calibration run
    belongs to a machine the coordinator chooses, not to a pytest worker.
    """
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port

# ==================== judgement 5: the self-consistency gate ====================


def test_no_tier_may_be_over_its_own_ceiling_without_saying_so():
    """The gate. A tier whose worst case exceeds the ceiling must be on the clamp path."""
    for tier in ALL_TIERS:
        budget = model_tier_budget(tier)
        verdict = max_tokens_verdict(budget, PROMPT_TOKENS)
        if budget.fits_within_timeout(PROMPT_TOKENS):
            assert not verdict.clamped, tier
            assert not verdict.unaffordable, tier
            assert verdict.max_tokens == tier_max_tokens(tier), tier
            continue
        assert verdict.clamped or verdict.unaffordable, (
            f"{tier.value} cannot write its own cap inside the ceiling and the budget said nothing"
        )


def test_the_analysis_tier_as_shipped_is_self_contradictory_and_says_so():
    """The contradiction R99 was opened for, in the code's own shipped defaults.

    1536 tokens at 8 tok/s is 192 s of decode against a 120 s ceiling, so the tier could only
    ever be told to stop. The old behaviour was to print ``clamped=yes`` on every call and then
    spend the whole ceiling anyway. The honest verdict is that no cap this machine can write in
    time is a cap this model will answer with -- 811 tokens sits below the answer floor, and
    nothing under that floor has a recorded non-empty answer on either thinking setting.
    """
    budget = model_tier_budget(ModelTier.ANALYSIS)

    assert budget.max_tokens == 1536
    assert (budget.prefill_seconds(PROMPT_TOKENS) + budget.decode_seconds()) * budget.timeout_margin == pytest.approx(224.09, abs=0.05)
    assert budget.fits_within_timeout(PROMPT_TOKENS) is False

    verdict = max_tokens_verdict(budget, PROMPT_TOKENS)

    assert verdict.affordable_max_tokens == 811
    assert verdict.min_answer_tokens == DEFAULT_MIN_ANSWER_TOKENS == 1536
    assert verdict.unaffordable is True
    assert verdict.clamped is False
    assert verdict.max_tokens == 1536


def test_a_calibrated_budget_leaves_no_tier_clamped_at_all(monkeypatch, caplog):
    """The other half of the gate: with real rates the same caps all fit, and nothing is logged.

    This is what makes the nail above more than a complaint about today's constants -- it shows
    the contradiction is a calibration failure and not an unavoidable property of the tiers, so
    an operator can fix it by measuring instead of by raising the ceiling until nothing times
    out at all.
    """
    _calibrated_gpu(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        for tier in ALL_TIERS:
            authorized = authorize(model_tier_budget(tier), PROMPT_TOKENS)
            assert authorized.verdict.clamped is False, tier
            assert authorized.verdict.unaffordable is False, tier
            assert authorized.budget.read_timeout_seconds(PROMPT_TOKENS) <= 120.0, tier

    assert [m for m in caplog.messages if MARKER in m] == [], caplog.text
    assert budget_event_counts()["max_tokens_clamped"] == 0


def test_a_configuration_that_contradicts_itself_is_caught_even_when_nobody_shipped_it(monkeypatch):
    """One tok/s is what a typo looks like. Every tier then overruns the ceiling; none may be quiet."""
    monkeypatch.setenv("MODEL_DECODE_TOKENS_PER_SECOND", "1")

    over_budget = []
    for tier in ALL_TIERS:
        budget = model_tier_budget(tier)
        verdict = max_tokens_verdict(budget, PROMPT_TOKENS)
        if not budget.fits_within_timeout(PROMPT_TOKENS):
            over_budget.append(tier.value)
            assert verdict.clamped or verdict.unaffordable, tier

    assert sorted(over_budget) == sorted(tier.value for tier in ALL_TIERS), over_budget
    assert budget_event_counts() == {name: 0 for name in model_budget.BUDGET_EVENT_NAMES}, (
        "a verdict about a configuration is not an event; only authorize() counts a call"
    )


def test_authorize_counts_both_halves_of_the_gate(monkeypatch):
    """A clamp and a refusal-to-clamp are different findings and both have to be countable."""
    _calibrated_gpu(monkeypatch, context_tokens="8192", analysis_cap="4096")
    authorize(model_tier_budget(ModelTier.ANALYSIS), 489)
    assert budget_event_counts()["max_tokens_clamped"] == 1

    monkeypatch.setenv("MODEL_DECODE_TOKENS_PER_SECOND", "8")
    monkeypatch.delenv("MODEL_TIER_ANALYSIS_MAX_TOKENS")
    authorize(model_tier_budget(ModelTier.ANALYSIS), 4000)

    counts = budget_event_counts()
    assert counts["max_tokens_clamped"] == 1, counts
    assert counts["budget_unaffordable"] == 1, counts


# ==================== judgement 3: clamp the answer, never the clock ====================


def test_the_answer_is_shortened_to_what_the_clock_can_write(monkeypatch, caplog):
    """A tier cap above the ceiling now buys a shorter answer, and the wire sees that number."""
    _calibrated_gpu(monkeypatch, context_tokens="8192", analysis_cap="4096")

    budget = model_tier_budget(ModelTier.ANALYSIS)
    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        authorized = authorize(budget, 489)
    verdict = authorized.verdict

    # 37 tok/s over (120 / 1.15 - 489/105) seconds of spare clock is 3688 tokens.
    assert verdict.declared_max_tokens == 4096
    assert verdict.affordable_max_tokens == 3688
    assert verdict.max_tokens == 3688
    assert verdict.clamped is True
    assert authorized.budget.max_tokens == 3688
    assert authorized.budget.read_timeout_seconds(489) == pytest.approx(119.98, abs=0.05)
    assert 489 + 4096 <= 8192, "the window is what makes this call legal at all"

    line = [m for m in caplog.messages if MARKER in m]
    assert len(line) == 1, line
    assert "clamped=yes" in line[0]
    assert "budget_verdict=clamped" in line[0]
    assert "max_tokens=3688" in line[0]
    assert "declared_max_tokens=4096" in line[0]
    assert "affordable_max_tokens=3688" in line[0]
    assert "min_answer_tokens=1536" in line[0]
    assert "MODEL_DECODE_TOKENS_PER_SECOND=37tok/s(env)" in line[0]
    assert "MODEL_REQUEST_TIMEOUT=120s(calibrated-default)" in line[0]


def test_the_clamp_never_relaxes_the_context_refusal(caplog):
    """``authorize_call`` refused this prompt before, and still must.

    A smaller answer *would* fit a window the declared cap cannot, which is exactly how a clamp
    would smuggle an oversized prompt onto the server. The context check therefore runs against
    what the tier asked for, before the clock gets any say at all.
    """
    budget = model_tier_budget(ModelTier.ANALYSIS)

    with pytest.raises(model_budget.ModelContextLimitExceeded) as refused:
        authorize(budget, 4000)

    assert refused.value.code == CONTEXT_LIMIT_CODE
    assert refused.value.max_tokens == 1536, "the refusal quoted a clamped cap, so the clamp ran first"
    line = [m for m in caplog.messages if MARKER in m]
    assert len(line) == 1, line
    assert "max_tokens=" not in line[0], "a refused call must not also claim to have been shortened"


def test_a_clamp_is_this_call_only_and_cannot_stick_to_the_shared_budget(monkeypatch):
    """The orchestrator builds one budget per graph, at import time, shared by every request.

    Clamping that object in place would let one long prompt set the cap for every shorter one
    after it, and two concurrent requests would clamp each other's baseline. The sized budget
    is a copy; the shared object keeps its declared number.
    """
    _calibrated_gpu(monkeypatch, context_tokens="8192", analysis_cap="4096")

    shared = model_tier_budget(ModelTier.ANALYSIS)
    first = authorize(shared, 489)
    second = authorize(shared, 100)

    assert shared.max_tokens == 4096
    assert first.budget is not shared
    assert first.verdict.max_tokens == 3688
    assert second.verdict.max_tokens == 3825, "a shorter prompt must buy more room, not inherit less"
    assert second.budget.max_tokens == 3825


def test_a_clamp_below_the_measured_thinking_floor_is_refused_and_said_out_loud(caplog):
    """The floor clause: shortening into the empty-answer zone is not a fix, it is the other bug.

    Measured in the shipping container on a thinking link: 1024 and 1536 output tokens both
    came back with zero visible characters, and 4096 produced 439. R100 then measured 1536 on
    the request this client actually sends (MODEL_THINKING=disabled) and got 93 characters with
    finish_reason=stop, so the floor sits at 1536 now. Shortening below it is still buying an
    answer that is not known to be writable, so the call keeps its cap and is reported instead.
    """
    budget = model_tier_budget(ModelTier.ANALYSIS)
    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        authorized = authorize(budget, 489)
    verdict = authorized.verdict

    assert verdict.affordable_max_tokens == 723
    assert verdict.unaffordable is True
    assert verdict.max_tokens == 1536, "it shortened into the floor instead of refusing to"
    assert authorized.budget.max_tokens == 1536
    assert budget_event_counts()["budget_unaffordable"] == 1
    line = [m for m in caplog.messages if MARKER in m][-1]
    # ``clamped=no`` is the point of the assertion: nothing was shortened here, and HEAD
    # printed clamped=yes on this exact line while sending the uncut cap. What the line has
    # to say instead is which finding it is, in its own token.
    assert "clamped=no" in line
    assert "budget_verdict=budget_unaffordable" in line
    assert "min_answer_tokens=1536" in line
    assert "affordable_max_tokens=723" in line
    assert "declared_max_tokens=1536" in line and "max_tokens=1536" in line


def test_the_floor_itself_is_a_measurement_and_can_be_measured_again(monkeypatch):
    """Lower the floor to a measured value and the clamp becomes available again.

    Without this, "the floor protects the answer" is indistinguishable from "the clamp is
    switched off". It is a bracket from a specific model on a specific day, and moving that
    bracket moves the verdict.
    """
    monkeypatch.setenv("MODEL_MIN_ANSWER_TOKENS", "300")

    verdict = max_tokens_verdict(model_tier_budget(ModelTier.ANALYSIS), 489)

    assert verdict.affordable_max_tokens == 723
    assert verdict.clamped is True
    assert verdict.max_tokens == 723
    assert verdict.unaffordable is False


def test_streams_and_unmeasured_prompts_are_never_shortened():
    """Two deliberate no-ops, both because neither ceiling applies to them.

    A stream's read clock is an allowance between chunks (``STREAM_STALL_TOKENS``), not the
    price of the whole answer; and ``prompt_tokens=None`` says the *call site* did not measure,
    for which the tier's worst case is the honest clock -- shortening it would punish a caller
    for somebody else's missing number.
    """
    analysis = model_tier_budget(ModelTier.ANALYSIS)
    streaming = max_tokens_verdict(analysis, 489, stream=True)
    unknown = max_tokens_verdict(analysis, None)

    assert streaming.max_tokens == 1536
    assert streaming.clamped is False and streaming.unaffordable is False
    assert unknown.max_tokens == 1536
    assert unknown.clamped is False and unknown.unaffordable is False
    assert analysis.decode_seconds(stream=True) * analysis.decode_tokens_per_second == STREAM_STALL_TOKENS


def test_the_returned_clock_is_priced_for_the_shortened_answer(monkeypatch):
    """The number a call site spends and the number it sends must be the same decision."""
    _calibrated_gpu(monkeypatch, context_tokens="8192", analysis_cap="4096")

    budget = model_tier_budget(ModelTier.ANALYSIS)
    seconds = authorize_call(budget, 489)

    assert clock_affordable_tokens(budget, 489) == 3688
    assert seconds == pytest.approx(119.98, abs=0.05)
    assert seconds < budget.timeout_ceiling_seconds, (
        "the ceiling is what the clamp was working around; returning it unchanged means the clamp did not run"
    )


def test_a_clamped_call_announces_a_length_stop_with_its_clamp(monkeypatch, caplog):
    """``detect_output_truncation`` keeps telling the truth about ``length``, and now says against what."""
    _calibrated_gpu(monkeypatch, context_tokens="8192", analysis_cap="4096")

    primary = _RecordingModel(
        response=AIMessage(content="说到一半", response_metadata={"finish_reason": "length"})
    )
    config, _bag = _config()

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        _resilient(ModelTier.ANALYSIS, primary).invoke([HumanMessage(content=PROMPT_BODY)], config=config)

    #: R100 put a second field on this body. The cap is what this file pins, so the fragment the
    #: thinking boundary owns is composed from that boundary rather than written out a second time
    #: -- the equality below is still an exact, whole-body check.
    assert primary.calls[0]["extra_body"] == {
        "max_tokens": 3688, **thinking_extra_body(),
    }, "the wire cap is not the clamped one"
    truncated = [m for m in caplog.messages if OUTPUT_TRUNCATED_CODE in m]
    assert truncated, caplog.text
    assert "max_tokens=3688" in truncated[0]
    assert "declared_max_tokens=4096" in truncated[0]

# ==================== judgement 2: rates are configuration, with a source ====================


@pytest.mark.parametrize("broken", ["0", "-8", "banana", "", "   "])
def test_a_broken_throughput_value_falls_back_to_the_calibration(broken):
    """A typo may not delete a rate: a rate of zero is a request that can never finish."""
    # The field is named for what it measures, not for the variable that sets it, so the
    # mapping is spelled out rather than derived: name.lower() would look up
    # ``model_prefill_tokens_per_second`` and report every rate as missing.
    for name, field, default in (
        (
            "MODEL_PREFILL_TOKENS_PER_SECOND",
            "prefill_tokens_per_second",
            DEFAULT_PREFILL_TOKENS_PER_SECOND,
        ),
        (
            "MODEL_DECODE_TOKENS_PER_SECOND",
            "decode_tokens_per_second",
            DEFAULT_DECODE_TOKENS_PER_SECOND,
        ),
    ):
        os.environ[name] = broken
        try:
            budget = model_tier_budget(ModelTier.ANALYSIS)
            assert getattr(budget, field) == default, (name, broken)
        finally:
            del os.environ[name]


@pytest.mark.parametrize("broken", ["0", "-1", "twelve", ""])
def test_a_broken_floor_falls_back_to_the_measured_bracket(broken):
    """A floor of zero would delete the protection this ticket exists to add."""
    os.environ["MODEL_MIN_ANSWER_TOKENS"] = broken
    try:
        assert min_answer_tokens() == DEFAULT_MIN_ANSWER_TOKENS
    finally:
        del os.environ["MODEL_MIN_ANSWER_TOKENS"]


def test_an_env_floor_is_honoured_to_the_token():
    os.environ["MODEL_MIN_ANSWER_TOKENS"] = "2048"
    try:
        assert min_answer_tokens() == 2048
        assert max_tokens_verdict(model_tier_budget(ModelTier.ANALYSIS), 489).min_answer_tokens == 2048
    finally:
        del os.environ["MODEL_MIN_ANSWER_TOKENS"]


def test_unset_knobs_reproduce_the_shipped_behaviour_byte_for_byte():
    """Not setting anything must equal the old machine, because the defaults are the calibration.

    The judgement here is that the rate variables were already there and the floor is the only
    new one: nothing in this ticket may change what an installation with no new lines in its
    ``.env`` does, except to stop it lying about what happened.
    """
    for name in ("MODEL_PREFILL_TOKENS_PER_SECOND", "MODEL_DECODE_TOKENS_PER_SECOND",
                 "MODEL_MIN_ANSWER_TOKENS", "MODEL_REQUEST_TIMEOUT", "MODEL_CONTEXT_TOKENS"):
        assert name not in os.environ or os.environ[name] == "", os.environ.get(name)

    budget = model_tier_budget(ModelTier.ANALYSIS)

    assert budget.prefill_tokens_per_second == DEFAULT_PREFILL_TOKENS_PER_SECOND
    assert budget.decode_tokens_per_second == DEFAULT_DECODE_TOKENS_PER_SECOND
    assert budget.timeout_ceiling_seconds == 120.0
    assert budget.max_tokens == 1536
    assert budget.read_timeout_seconds(489) == 120.0
    assert max_tokens_verdict(budget, 489).max_tokens == 1536


# ==================== judgement 4: a fallback the client cannot tell from an answer =========


def _cause_wrapped(cause: BaseException) -> BaseException:
    """An exception whose ``__cause__`` is the real timeout: what a wrapping client hands us."""
    outer = RuntimeError("provider call failed")
    outer.__cause__ = cause
    return outer

class APITimeoutError(RuntimeError):
    """Name-only stand-in for ``openai.APITimeoutError``; the boundary matches it by name.

    It is deliberately not a builtin ``TimeoutError``, which is exactly why
    ``app/trace/spans.py:error_code_for`` files the real one as ``internal_error``.
    """


@pytest.mark.parametrize(
    "exc",
    [
        APITimeoutError("Request timed out."),
        httpx.ReadTimeout("timed out"),
        httpx.ConnectTimeout("connect timed out"),
        TimeoutError("the read budget expired"),
        RuntimeError("upstream said: Request timed out."),
        _cause_wrapped(httpx.ReadTimeout("timed out")),
    ],
    ids=["openai-name", "httpx-read", "httpx-connect", "builtin", "message-only", "wrapped"],
)
def test_a_timeout_is_recognised_whichever_layer_it_reached_us_from(exc):
    assert model_timeout_code(exc) == TIMEOUT_ERROR_CODE


def test_the_timeout_recogniser_does_not_invent_a_code_for_everything():
    assert model_timeout_code(RuntimeError("connection reset by peer")) is None
    assert model_timeout_code(ValueError("n_ctx exceeded")) is None
    assert model_timeout_code(None) is None


def test_a_timeout_is_named_in_the_span_at_error_level_and_is_counted(tmp_path, monkeypatch, caplog):
    """Judgement 4's three dials: the span code, the log level, the count.

    The offline sentence itself stays -- judgement 4 asks for it to be loud, not for it to be
    gone -- but it may not arrive as ``internal_error`` at warning level, which is how a
    machine that is too slow for its own budget used to look like an ordinary afternoon.
    """
    store = _span_rows(tmp_path, monkeypatch)
    offline = _OfflineReply()
    primary = _RecordingModel(error=APITimeoutError("Request timed out."))
    model = _resilient(ModelTier.ANALYSIS, primary, offline)
    config, _bag = _config()

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        reply = model.invoke([HumanMessage(content=PROMPT_BODY)], config=config)

    assert "离线" in reply.content
    assert offline.calls == 1, "the wrapper still answers for the model on a timeout; that is judgement 4 as written"
    provider_rows = _provider_rows(store)
    assert [row["error_code"] for row in provider_rows] == [TIMEOUT_ERROR_CODE], provider_rows
    assert [row["status"] for row in provider_rows] == ["failed"]
    assert budget_event_counts()["timeout_offline_reply"] == 1
    errors = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    assert any(TIMEOUT_ERROR_CODE in message and MARKER in message for message in errors), caplog.text


def test_a_non_timeout_provider_failure_keeps_its_old_verdict(tmp_path, monkeypatch, caplog):
    """The guard must not swallow the general case: one code for a clock, another for a corpse."""
    store = _span_rows(tmp_path, monkeypatch)
    primary = _RecordingModel(error=RuntimeError("connection reset by peer"))
    model = _resilient(ModelTier.ANALYSIS, primary)
    config, _bag = _config()

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        model.invoke([HumanMessage(content="数" * 40)], config=config)

    assert [row["error_code"] for row in _provider_rows(store)] == ["internal_error"]
    assert budget_event_counts()["timeout_offline_reply"] == 0
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == [], caplog.text


def test_a_streaming_timeout_is_loud_too(tmp_path, monkeypatch, caplog):
    store = _span_rows(tmp_path, monkeypatch)
    primary = _RecordingModel(error=httpx.ReadTimeout("timed out"))
    model = _resilient(ModelTier.ANALYSIS, primary)
    config, _bag = _config()

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        list(model.stream([HumanMessage(content=PROMPT_BODY)], config=config))

    assert [row["error_code"] for row in _provider_rows(store)] == [TIMEOUT_ERROR_CODE]
    assert budget_event_counts()["timeout_offline_reply"] == 1
    assert [r for r in caplog.records if r.levelno >= logging.ERROR], caplog.text


def test_an_empty_completion_is_not_delivered_as_a_successful_answer(tmp_path, monkeypatch, caplog):
    """The first cause, per the container evidence: 1536 tokens, zero characters.

    A 200 whose visible text is empty is not an answer, and filing it as ``completed`` is what
    let it be shown as one -- and cached for thirty minutes, because the cache write behind
    ``if full_text:`` in ``app/api/v1/chat.py`` stores whatever non-empty text arrives. It is
    now a failed boundary carrying the ratified code for "this round produced no conclusion",
    the same one chat.py already uses for that fact one layer up, and there is no text left to
    store.
    """
    store = _span_rows(tmp_path, monkeypatch)
    empty = AIMessage(content="", response_metadata={"finish_reason": "length"})
    primary = _RecordingModel(response=empty)
    offline = _OfflineReply()
    model = _resilient(ModelTier.ANALYSIS, primary, offline)
    config, bag = _config()

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        reply = model.invoke([HumanMessage(content=PROMPT_BODY)], config=config)

    assert reply is empty, "the boundary answered for the model instead of reporting it"
    assert offline.calls == 0
    assert [(row["status"], row["error_code"]) for row in _provider_rows(store)] == [
        ("failed", NO_ANSWER_CODE)
    ]
    assert budget_event_counts()["empty_answer_rejected"] == 1
    assert any(NO_ANSWER_CODE in r.getMessage() and r.levelno >= logging.ERROR for r in caplog.records)
    assert detect_empty_answer(reply) == NO_ANSWER_CODE
    assert answer_text(reply) == "", "an empty body must not be reported as non-empty text"

    result = build_agent_result(worker="doc", answer=answer_text(reply), bag=bag, request_id="req-r99")
    assert result.status == "failed"
    assert result.error is not None and result.error.code == NO_ANSWER_CODE
    assert result.answer == ""


def test_a_response_of_only_whitespace_is_an_empty_answer():
    assert detect_empty_answer(AIMessage(content="   \n ")) == NO_ANSWER_CODE


def test_a_tool_call_round_is_not_an_empty_answer():
    """No text, but the round did something: a guard that cries wolf at every dispatch is muted."""
    tool_call = AIMessage(
        content="",
        tool_calls=[{"name": "search_docs", "args": {"query": "报销"}, "id": "call-1", "type": "tool_call"}],
    )

    assert detect_empty_answer(tool_call) is None


def test_a_tool_block_response_is_not_an_empty_answer():
    assert detect_empty_answer(SimpleNamespace(content=[{"type": "tool_use", "id": "t1"}])) is None


def test_an_empty_stream_is_filed_as_a_failure_without_changing_the_bytes_delivered(tmp_path, monkeypatch, caplog):
    """The same verdict in both transports, because the thinking model eats both of them."""
    store = _span_rows(tmp_path, monkeypatch)
    primary = _RecordingModel(response=[AIMessage(content="")])
    model = _resilient(ModelTier.ANALYSIS, primary)
    config, _bag = _config()

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        chunks = list(model.stream([HumanMessage(content=PROMPT_BODY)], config=config))

    assert chunks == [AIMessage(content="")]
    assert [(row["status"], row["error_code"]) for row in _provider_rows(store)] == [
        ("failed", NO_ANSWER_CODE)
    ]
    assert budget_event_counts()["empty_answer_rejected"] == 1


def test_a_stream_that_delivered_text_still_finishes_completed(tmp_path, monkeypatch):
    store = _span_rows(tmp_path, monkeypatch)
    primary = _RecordingModel(response=[AIMessage(content="一段"), AIMessage(content="答案")])
    model = _resilient(ModelTier.ANALYSIS, primary)
    config, _bag = _config()

    assert list(model.stream([HumanMessage(content="数" * 40)], config=config)) == [
        AIMessage(content="一段"),
        AIMessage(content="答案"),
    ]

    assert [(row["status"], row["error_code"]) for row in _provider_rows(store)] == [("completed", None)]
    assert budget_event_counts()["empty_answer_rejected"] == 0


# ==================== judgement 4 (exposure): the readout, and where it is not wired =======


def test_the_budget_readout_counts_and_names_its_own_numbers():
    authorize(model_tier_budget(ModelTier.ANALYSIS), 489)

    readout = model_budget_readout()

    assert readout["events"]["budget_unaffordable"] == 1
    assert set(readout["events"]) == set(model_budget.BUDGET_EVENT_NAMES)
    assert readout["min_answer_tokens"] == DEFAULT_MIN_ANSWER_TOKENS
    assert readout["request_timeout_ceiling_seconds"] == 120.0
    assert readout["throughput_tokens_per_second"] == {"prefill": 35.0, "decode": 8.0}
    assert readout["throughput_provenance"]["MODEL_DECODE_TOKENS_PER_SECOND"] == "calibrated-default"
    assert readout["tiers"]["analysis"]["declared_max_tokens"] == 1536
    assert readout["tiers"]["analysis"]["fits_ceiling"] is False
    assert readout["tiers"]["chat"]["fits_ceiling"] is True


def test_a_readout_of_a_moving_machine_says_which_values_are_in_force(monkeypatch):
    monkeypatch.setenv("MODEL_DECODE_TOKENS_PER_SECOND", "37")

    readout = model_budget_readout()

    assert readout["throughput_provenance"]["MODEL_DECODE_TOKENS_PER_SECOND"] == "env"
    assert readout["throughput_tokens_per_second"]["decode"] == 37.0
    assert readout["tiers"]["analysis"]["fits_ceiling"] is True


def test_the_readout_is_embedded_in_health_details_and_shares_one_accessor():
    """Judgement 4 second half: the readout is reachable from a health request now.

    R99 left this as a receipt that the counter dial was NOT reachable. It is wired:
    ``build_health_snapshot`` publishes ``model_budget`` next to ``hot_index``, through the
    same ``_subsystem_state`` accessor the storage subsystems use, so there is no second
    copy of these numbers to go stale, and a failing probe degrades to ``unavailable`
    instead of breaking the request. The check still reads source rather than calling the
    builder, for the reason this file already gave: the builder probes its dependencies over
    the network, and a pytest that opens a socket at 127.0.0.1:11434 is stopped by the R56
    host-model gate -- which is that gate working, not a test to route around.
    """
    import inspect

    from app.common import monitoring

    source = inspect.getsource(monitoring.build_health_snapshot)

    assert '"model_budget": _subsystem_state(' in source, source
    assert "model_budget_readout" in source, source
    assert callable(model_budget_readout)
    # Not a hand-copied dict: what health would publish is exactly what this boundary
    # reports, read through the accessor health itself uses.
    published = monitoring._subsystem_state(
        "app.common.model_budget", "model_budget_readout"
    )
    assert published == model_budget_readout()
    assert set(published["thinking"]) >= {"mode", "request_field_sent", "provenance"}
def test_every_offline_sentence_is_identifiable_as_one():
    """The recogniser has to survive a rewording, because it protects a cache, not a log.

    The fallback answers with one of three sentences depending on which keywords were in the
    question, and a fourth one when it is asked to stream. Every one of those is a sentence
    that must never be stored under the customer's question, so the check walks the branches
    instead of trusting that whoever edits a sentence also edited the constant list.
    """
    offline = nodes._OfflineModel()

    for question in ("报销流程是什么", "门店利润怎么分析", "随便问一个问题"):
        reply = offline.invoke([HumanMessage(content=question)])
        assert reply.content, question
        assert nodes.is_offline_reply_text(reply.content), (question, reply.content)

    chunk = next(iter(offline.stream()))
    streamed = chunk.choices[0].delta.content
    assert streamed == nodes.OFFLINE_STREAM_CHUNK
    assert nodes.is_offline_reply_text(streamed)

    # And the other direction, which is the half that costs something if it is wrong: an
    # answer a model actually wrote is not a canned sentence, so a recogniser built out of
    # substrings would quietly switch the answer cache off for real work.
    assert nodes.is_offline_reply_text("3 月营收环比增长 8%，主要来自华东门店。") is False
    assert nodes.is_offline_reply_text("") is False
    assert nodes.is_offline_reply_text(None) is False


def test_the_cache_guard_uses_the_recogniser_before_it_writes():
    """Judgement 4 cache half: the recogniser gates the cache write now.

    The clause below is the one R99 wrote down and left for the next shift. An offline
    sentence is loud rather than absent on purpose, and loudness is only honest if it never
    becomes somebody else's cached answer: a canned line stored under a customer question
    comes back in milliseconds, with the [cached] stamp, for a question that was never
    answered. The recogniser is the one nodes.py owns, so a reworded sentence cannot slip
    past this guard unnoticed -- test_every_offline_sentence_is_identifiable_as_one walks its
    branches. The first two assertions still guard the fact rather than the phrase: if the
    cache write or its empty-body guard ever moves, this test has to be re-read, not deleted.
    """
    source = (_REPOSITORY / "app" / "api" / "v1" / "chat.py").read_text(encoding="utf-8")

    assert "cache_answer(rewritten_msg, full_text" in source, "the write this pin is about moved"
    assert "if full_text:" in source, "an empty answer would now be cached, re-read this"
    assert (
        "if use_answer_cache and not intr and not is_offline_reply_text(full_text):" in source
    ), "a canned offline sentence can be cached again"
# ==================== judgement 1: the calibration artefact ================================


def test_the_calibration_script_help_is_readable_and_advertises_its_exit_codes():
    result = subprocess.run(
        [sys.executable, str(BENCH_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(_REPOSITORY),
    )

    assert result.returncode == 0, result.stderr
    assert "Exit codes are explicit" in result.stdout
    assert "--json" in result.stdout
    assert "--caps" in result.stdout


def test_the_calibration_script_skips_instead_of_passing_when_there_is_no_server(capsys):
    """No Ollama is a finding, not a green light: exit 3, and the text says nothing was measured."""
    from scripts.bench_model_throughput import EXIT_SKIPPED, main

    code = main(["--base-url", f"http://127.0.0.1:{_unused_local_port()}", "--model", "not-a-real-model"])
    captured = capsys.readouterr()

    assert code == EXIT_SKIPPED, "a skip must not be a zero, or CI reads it as a calibration"
    assert "RESULT: SKIP" in captured.out
    assert "not a pass" in captured.out
    assert "RESULT: PASS" not in captured.out


def test_the_calibration_script_refuses_to_write_a_result_inside_the_repository(capsys):
    from scripts.bench_model_throughput import EXIT_USAGE, main

    target = _REPOSITORY / "bench_model_throughput_results.json"
    if target.exists():
        target.unlink()

    code = main(["--json", str(target), "--base-url", f"http://127.0.0.1:{_unused_local_port()}"])
    captured = capsys.readouterr()

    assert code == EXIT_USAGE
    assert not target.exists(), "a calibration artefact landed in the tree"
    assert "refuses to write inside the repository" in captured.out


def test_the_calibration_script_carries_the_container_baseline_and_says_who_measured_it():
    """The four baseline groups are documentation, and their provenance is part of them.

    They came from the coordinator's container, not from this script, and a rerun that
    disagrees wins. That sentence has to live next to the numbers, or the next reader treats
    them as the script's own output and stops measuring.
    """
    doc = BENCH_SCRIPT.read_text(encoding="utf-8")

    for fragment in (
        "78b8507",
        "37 tok/s",
        "max_tokens=1024",
        "max_tokens=4096",
        "num_predict=1536",
        "0 chars",
        "439 chars",
        "NOT this script",
        "the rerun wins",
        "100% GPU",
    ):
        assert fragment in doc, fragment
    assert "options" in doc and "top-level" in doc, "the think-spelling trap must be recorded"


def test_the_calibration_script_matrix_covers_both_legs_and_both_streams():
    """The three candidate causes are only separable if the matrix is what the ticket said."""
    source = BENCH_SCRIPT.read_text(encoding="utf-8")

    assert "/v1/chat/completions" in source
    assert "/api/chat" in source
    assert "num_predict" in source
    assert "first_token" in source, "without time-to-first-token, prefill cannot be separated"
    assert "PREFILL_PROBE_CAP" in source
    assert "visible_chars" in source, "the thinking floor is invisible without counting characters"