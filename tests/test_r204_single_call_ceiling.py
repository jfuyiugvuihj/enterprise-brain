"""R204 judgement 4: the invariant, nailed with a fake clock instead of a sleep.

The invariant in the ticket's own words: if the budget says this answer is not affordable, a
single model call at the 120-second scale must stop being possible. The refusal earns that by
making no call at all, so every test below measures the same two things -- how many requests
reached the provider, and how much clock the round spent. The provider double advances an
elapsed counter by exactly what the budget predicted the answer would cost, which is the
behaviour run6 showed: a model on an unaffordable budget does not fail fast, it takes the time.

Two boundaries are driven, both real:

* ``app/agents/nodes.py`` -- the graph's model wrapper. Its refusal is not wired yet: the call
  site is outside this ticket's write domain, so the tests swap the one symbol that call site
  already imports, and nothing else in the file is touched. See ``_refusing_graph``.
* ``app/common/model_handler.py`` -- wired by this ticket, driven exactly as production does.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents import nodes
from app.agents.contracts import ModelTier
from app.agents.evidence import build_agent_result, new_evidence_bag
from app.common import model_budget
from app.common.model_budget import (
    TIMEOUT_ERROR_CODE,
    ModelClockUnaffordable,
    ModelContextLimitExceeded,
    max_tokens_verdict,
    model_tier_budget,
    request_timeout_ceiling_seconds,
    tier_max_tokens,
)
from tests.test_r204_budget_refusal import handler_with_stub_client

#: 489 tokens of prompt: the analysis tier's answer then costs 224 s against a 120 s ceiling and
#: the most the ceiling can pay for is 723 tokens, below the 1536-token floor. This is the shape
#: every analysis call in run6 logged as ``budget_unaffordable ... clamped=no``.
UNAFFORDABLE_PROMPT = "x" * 4 * 489

#: A rewrite prompt long enough to price its own 256-token answer out of the ceiling: 3000
#: tokens of prefill leaves 149 tokens of decode budget. It still fits n_ctx, so what refuses
#: it is the clock and not the window -- which is the whole point of R204.
UNAFFORDABLE_REWRITE = "x" * 4 * 3000

#: The same prompt priced out for a blocking answer, delivered on the streaming leg instead.
STREAMING_ANSWER_PROMPT = "x" * 4 * 1000


class _FakeClockProvider:
    """A provider that takes exactly the time the budget says an answer costs.

    It is called zero times on a refused round, and that is the entire content of the
    invariant: the clock stays at zero, so no single call can be 120 s or anything near it.
    """

    def __init__(self, clock: dict, tier: ModelTier):
        self.clock = clock
        self.tier = tier
        self.calls: list[dict] = []

    def _spend(self, messages) -> None:
        budget = model_tier_budget(self.tier)
        needed = (
            budget.prefill_seconds(model_budget.estimate_prompt_tokens(messages))
            + budget.decode_seconds()
        ) * budget.timeout_margin
        self.clock["seconds"] += needed

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        self._spend(messages)
        return AIMessage(content="ok", response_metadata={"finish_reason": "stop"})

    def stream(self, *args, **kwargs):
        messages = args[0] if args else kwargs.get("messages")
        self.calls.append({"messages": messages, **kwargs})
        self._spend(messages)
        yield AIMessage(content="ok", response_metadata={"finish_reason": "stop"})

    def bind_tools(self, tools):
        return self


def _bagged_config() -> tuple[dict, dict]:
    bag = new_evidence_bag()
    return {
        "configurable": {
            "evidence_bag": bag,
            "trace_id": "trace-r204",
            "request_id": "req-r204",
            "task_id": "task-r204",
        }
    }, bag


def _graph_model(tier: ModelTier, primary) -> nodes._ResilientModel:
    return nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(tier),
    )


def _refusing_graph(monkeypatch):
    """Install the one symbol change the graph boundary still needs, without editing it.

    ``app/agents/nodes.py:621`` reads ``authorized = authorize(self.budget, prompt_tokens,
    stream=stream)``. The change this ticket asks the coordinator to land is that call site
    reading ``authorize_or_refuse`` instead, plus that name in the import block above it.
    Nothing else in that file is involved: the pre-send handler twelve lines below already
    catches ``ModelContextLimitExceeded`` -- releases the slot, finishes the span with
    ``exc.code``, re-raises typed -- and the refusal raised here is a subclass of exactly that
    and carries ``task_timeout`` as its code. That is why this is one symbol and not a
    try/except, and it is what the two slot tests below are on record proving.
    """
    assert nodes.authorize is model_budget.authorize, "this file must not be the place nodes.py changes"
    monkeypatch.setattr(nodes, "authorize", model_budget.authorize_or_refuse)


# ==================== the invariant, at the graph boundary ====================


def test_an_unaffordable_call_makes_no_request_and_spends_no_clock(monkeypatch):
    """The headline: the budget says unaffordable, therefore there is no call to be slow."""
    _refusing_graph(monkeypatch)
    clock = {"seconds": 0.0}
    primary = _FakeClockProvider(clock, ModelTier.ANALYSIS)
    config, bag = _bagged_config()

    with pytest.raises(ModelContextLimitExceeded) as refused:
        _graph_model(ModelTier.ANALYSIS, primary).invoke(
            [HumanMessage(content=UNAFFORDABLE_PROMPT)], config=config
        )

    assert refused.value.code == TIMEOUT_ERROR_CODE
    assert primary.calls == [], "a request reached the provider"
    assert clock["seconds"] == 0.0, clock
    statuses = [(item["status"], item["error_code"]) for item in bag["model_statuses"]]
    assert ("failed", TIMEOUT_ERROR_CODE) in statuses, statuses
    assert "model_unavailable" not in " ".join(name for name, _ in statuses), statuses


def test_the_unchanged_boundary_still_buys_the_whole_ceiling_and_more():
    """What HEAD does with the same call on the same clock: the hole, kept as a witness.

    Without the refusal the request goes out and costs 236 s of the one service window at the
    shipped calibration -- almost twice ``MODEL_REQUEST_TIMEOUT``, which is the arithmetic that
    let a single question hold the machine for the best part of a night. This test is the
    counterfactual for every nail in this file: if the refusal ever stops firing, this is the
    pair that says why the other one went red.
    """
    clock = {"seconds": 0.0}
    primary = _FakeClockProvider(clock, ModelTier.ANALYSIS)
    config, _ = _bagged_config()

    _graph_model(ModelTier.ANALYSIS, primary).invoke(
        [HumanMessage(content=UNAFFORDABLE_PROMPT)], config=config
    )

    assert len(primary.calls) == 1, "the shipped behaviour is still to send it"
    verdict = max_tokens_verdict(
        model_tier_budget(ModelTier.ANALYSIS),
        model_budget.estimate_prompt_tokens([HumanMessage(content=UNAFFORDABLE_PROMPT)]),
    )
    assert verdict.unaffordable is True and verdict.clamped is False
    assert clock["seconds"] > 1.9 * request_timeout_ceiling_seconds(), clock


def test_no_call_on_the_sweep_exceeds_the_ceiling_once_the_budget_has_refused(monkeypatch):
    """The invariant as a sweep, not as one lucky case.

    For every tier over a ladder of prompt sizes, judged on the prompt the boundary itself will
    measure: where the clock cannot pay for the floor's answer, the boundary makes no call and
    contributes no seconds; where it can pay, the call goes out and its honest cost is inside
    the ceiling. Either way no single call reaches the 120 s scale, which is the sentence
    judgement 4 asks for.
    """
    _refusing_graph(monkeypatch)
    ceiling = request_timeout_ceiling_seconds()
    refused_cases = 0

    for tier in (ModelTier.CHAT, ModelTier.ALERT, ModelTier.CODE, ModelTier.ANALYSIS):
        for size in (4 * 40, 4 * 489, 4 * 1024, 4 * 2500):
            messages = [HumanMessage(content="x" * size)]
            prompt_tokens = model_budget.estimate_prompt_tokens(messages)
            budget = model_tier_budget(tier)
            if budget.context_window_code(prompt_tokens):
                continue  # a window refusal is R30's verdict, not this one

            clock = {"seconds": 0.0}
            primary = _FakeClockProvider(clock, tier)
            model = _graph_model(tier, primary)

            if max_tokens_verdict(budget, prompt_tokens).unaffordable:
                refused_cases += 1
                with pytest.raises(ModelClockUnaffordable):
                    model.invoke(messages)
                assert primary.calls == [], (tier, prompt_tokens)
                assert clock["seconds"] == 0.0, (tier, prompt_tokens)
            else:
                model.invoke(messages)
                assert len(primary.calls) == 1, (tier, prompt_tokens)
                assert clock["seconds"] < ceiling, (tier, prompt_tokens, clock)

    assert refused_cases >= 4, refused_cases


def test_a_refused_call_gives_the_only_slot_back(monkeypatch):
    """A call we never made must not occupy the single service window.

    With one slot, a leak is not a slowdown: the wrapper would find the budget exhausted and
    answer every later question with a canned offline sentence, so the refusal would install
    the outage it exists to avoid. If the slot leaked, the second refusal below would not
    raise at all.
    """
    _refusing_graph(monkeypatch)
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    clock = {"seconds": 0.0}
    model = _graph_model(ModelTier.ANALYSIS, _FakeClockProvider(clock, ModelTier.ANALYSIS))
    messages = [HumanMessage(content=UNAFFORDABLE_PROMPT)]

    try:
        for _ in range(3):
            with pytest.raises(ModelClockUnaffordable):
                model.invoke(messages)
        assert clock["seconds"] == 0.0
        remaining = model_budget.default_model_budget().acquire(wait_seconds=0)
        remaining.release()
    finally:
        model_budget.reset_default_budget()


def test_a_streamed_round_is_never_refused_by_the_clock_guard_and_gives_its_slot_back(monkeypatch):
    """A stream is billed for a stall between chunks, not for the price of the whole answer.

    So the analysis tier streams on a prompt the blocking branch would refuse, and that is the
    deliberate boundary of this ticket: nothing about how a customers answer arrives changes,
    and the slot a streamed round holds is handed back when the last piece is delivered.
    """
    _refusing_graph(monkeypatch)
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    clock = {"seconds": 0.0}
    primary = _FakeClockProvider(clock, ModelTier.ANALYSIS)
    model = _graph_model(ModelTier.ANALYSIS, primary)
    messages = [HumanMessage(content=UNAFFORDABLE_PROMPT)]

    assert max_tokens_verdict(model_tier_budget(ModelTier.ANALYSIS), 493).unaffordable is True
    try:
        pieces = list(model.stream(messages))
        assert pieces and primary.calls and clock["seconds"] > 0.0, "the stream was refused"
        remaining = model_budget.default_model_budget().acquire(wait_seconds=0)
        remaining.release()
    finally:
        model_budget.reset_default_budget()

def test_the_refusal_reaches_the_round_as_a_retryable_timeout(monkeypatch):
    """The code survives the trip through the evidence bag, and keeps its family.

    ``evidence._terminal_status`` reports ``model_unavailable`` ahead of a failure on purpose
    (R30), so a refusal that let an offline sentence into the same round would be heard by the
    client as "the model is broken" instead of "this answer does not fit this machine's clock".
    It is retryable because the fact is about the clock, not about the prompt: run6's own
    second attempt at the same question came back in 35 s.
    """
    _refusing_graph(monkeypatch)
    clock = {"seconds": 0.0}
    primary = _FakeClockProvider(clock, ModelTier.ANALYSIS)
    config, bag = _bagged_config()

    with pytest.raises(ModelContextLimitExceeded):
        _graph_model(ModelTier.ANALYSIS, primary).invoke(
            [HumanMessage(content=UNAFFORDABLE_PROMPT)], config=config
        )

    result = build_agent_result(worker="data", answer="", bag=bag, request_id="req-r204")

    assert result.status == "timeout", result
    assert result.error is not None
    assert result.error.code == TIMEOUT_ERROR_CODE
    assert result.error.retryable is True


# ==================== the boundary this ticket did wire: the handler leg ====================


def test_the_handler_refuses_a_priced_out_rewrite_without_sending_or_queueing():
    """The rewrite leg can be priced out too, and it is now refused the same way.

    A 3000-token rewrite prompt leaves 149 tokens of decode budget against this tier's 256,
    so the call cannot be written inside the ceiling at the shipped rates. Before this ticket
    the handler queued for a slot, sent it, waited the whole 120 s, and came back with the
    offline sentence -- which both of its callers already throw away: the query rewriter falls
    back to the original question either way. What changes is that the machine is not held for
    two minutes on the way.
    """
    handler = handler_with_stub_client()
    before = model_budget.budget_event_counts()["budget_unaffordable"]

    with pytest.raises(ModelClockUnaffordable) as refused:
        handler.chat(messages=[{"role": "user", "content": UNAFFORDABLE_REWRITE}], stream=False)

    assert refused.value.code == TIMEOUT_ERROR_CODE
    assert refused.value.max_tokens == tier_max_tokens(ModelTier.REWRITE)
    assert handler.completions.calls == [], "a rewrite request reached the provider"
    assert model_budget.budget_event_counts()["budget_unaffordable"] == before + 1
    slot = handler._budget.acquire(wait_seconds=0)
    slot.release()


def test_the_handler_still_sends_an_affordable_rewrite():
    """The guard has to let ordinary traffic through, or it is an outage with a code on it."""
    handler = handler_with_stub_client()

    reply = handler.chat(messages=[{"role": "user", "content": "x" * 40}], stream=False)

    assert len(handler.completions.calls) == 1
    assert str(reply) == "ok"
    assert reply.error_code == ""


def test_a_streaming_answer_leg_is_untouched_by_the_guard():
    """The legacy answer endpoint streams, and a stream is billed for a stall, not an answer.
    A 1000-token prompt prices the blocking analysis call out of the ceiling (600 affordable
    tokens against a 1536-token floor) and leaves the streaming one alone.


    ``_call_budget`` gives a streaming call the analysis tier, which is the tier this refusal
    fires on most often -- so it matters that the stream flag is what keeps it out: nothing
    about how a customer's answer arrives is changed by this ticket.
    """
    handler = handler_with_stub_client()

    pieces = list(handler.chat(messages=[{"role": "user", "content": STREAMING_ANSWER_PROMPT}], stream=True))

    assert handler.completions.calls, "the streaming leg was refused"
    assert handler.completions.calls[0]["stream"] is True
    assert [p.choices[0].delta.content for p in pieces] == ["ok"]
