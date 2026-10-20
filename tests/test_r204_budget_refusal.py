"""R204 judgement 1 and 2: why ``clamped=no``, and what the answer to that is.

Forensics first, because the shape of the fix depends on it. The clamp arithmetic is **not**
skipped on the leg that stalled run6: ``authorize`` runs it at both model boundaries
(``app/agents/nodes.py:621`` via ``_budget_kwargs``, and ``app/common/model_handler.py`` via
the authorization at the top of ``chat``). What blocks it is the answer floor, and for the
analysis tier the block is structural rather than incidental:

    DEFAULT_MIN_ANSWER_TOKENS == TIER_MAX_TOKEN_DEFAULTS[ModelTier.ANALYSIS] == 1536

so on that tier ``affordable < declared`` *implies* ``affordable < floor``, which is exactly
the branch in ``max_tokens_verdict`` that refuses to shorten and hands the declared cap back.
``clamped=no`` is therefore R99's floor working as written -- not a missed code path, and not
a condition anyone can lift without buying the other bug: shortening into the floor is the
empty answer that follow-up 42 and R100 measured. What was missing is the sentence after the
finding. If no cap this machine can write in time is a cap the model will answer with, then
the request should not be sent at all.

That is ``authorize_or_refuse``: the same arithmetic, the same numbers on the same log line,
the same counter, and then a typed refusal carrying the already-ratified ``task_timeout`` code
before a slot is taken or a byte goes on the wire. Nothing is shortened, so no answer that
does get written changes bytes.
"""

import logging
from typing import get_args

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents import nodes
from app.agents.contracts import CONTEXT_LIMIT_CODE, ErrorEnvelope, ModelTier
from app.common import model_budget
from app.common.model_budget import (
    DEFAULT_MIN_ANSWER_TOKENS,
    MODEL_BUDGET_MARKER,
    TIER_MAX_TOKEN_DEFAULTS,
    TIMEOUT_ERROR_CODE,
    ModelClockUnaffordable,
    ModelContextLimitExceeded,
    authorize,
    authorize_or_refuse,
    budget_event_counts,
    clock_affordable_tokens,
    max_tokens_verdict,
    min_answer_tokens,
    model_tier_budget,
    tier_max_tokens,
)
from app.common.model_handler import ModelHandler

#: A prompt that leaves the shipped analysis tier outside its own clock: 489 tokens of prefill
#: plus 1536 tokens of decode at the CPU calibration is 224 s against a 120 s ceiling, and the
#: most that ceiling can pay for is 723 tokens -- below the 1536-token floor. This is the shape
#: run6 logged on every analysis call as ``budget_unaffordable ... clamped=no``.
UNAFFORDABLE_PROMPT_TOKENS = 489


def _fast_machine(monkeypatch):
    """The GPU-side calibration R99 uses, where every tier fits and nothing is refused."""
    monkeypatch.setenv("MODEL_DECODE_TOKENS_PER_SECOND", "37")
    monkeypatch.setenv("MODEL_PREFILL_TOKENS_PER_SECOND", "105")
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "8192")


# =================== judgement 1: the clamp path runs, the floor blocks it ===================


def test_the_analysis_tier_walks_the_clamp_path_and_the_floor_is_what_blocks_it():
    """Not "the clamp never ran": the verdict exists, and it says why it declined.

    Every field below is one link in the chain the run6 log line reports, asserted at the
    function that decides it rather than at a log formatter: the clock was priced, the answer
    was compared against it, the comparison came out short, and the floor is what turned a
    would-be clamp into a reported refusal-to-clamp.
    """
    budget = model_tier_budget(ModelTier.ANALYSIS)
    verdict = max_tokens_verdict(budget, UNAFFORDABLE_PROMPT_TOKENS)

    assert verdict.declared_max_tokens == tier_max_tokens(ModelTier.ANALYSIS) == 1536
    assert verdict.affordable_max_tokens == clock_affordable_tokens(
        budget, UNAFFORDABLE_PROMPT_TOKENS
    )
    assert verdict.affordable_max_tokens < verdict.declared_max_tokens, "the clock is short"
    assert verdict.unaffordable is True
    assert verdict.clamped is False
    assert verdict.verdict_word == "budget_unaffordable"


def test_the_floor_and_the_analysis_cap_are_the_same_number_so_a_clamp_is_unreachable():
    """The structural reason this tier can never print ``clamped=yes``.

    The floor is not merely high on the analysis tier, it *is* the tier's own cap. Any prompt
    whose clock binds is therefore also a prompt whose floor binds, and ``max_tokens_verdict``
    correctly concludes there is no cap left to clamp to. Lowering the floor would fix the log
    line by producing the empty answers follow-up 42 measured.
    """
    assert min_answer_tokens() == DEFAULT_MIN_ANSWER_TOKENS == 1536
    assert TIER_MAX_TOKEN_DEFAULTS[ModelTier.ANALYSIS] == min_answer_tokens()

    for prompt_tokens in (40, 489, 1024, 2500):
        verdict = max_tokens_verdict(model_tier_budget(ModelTier.ANALYSIS), prompt_tokens)
        if verdict.affordable_max_tokens < verdict.declared_max_tokens:
            assert verdict.affordable_max_tokens < verdict.min_answer_tokens, prompt_tokens
            assert verdict.clamped is False and verdict.unaffordable is True, prompt_tokens

def test_the_refusal_is_reported_before_it_is_raised(caplog):
    """A refused call leaves the same trail as the call it replaces, plus one code.

    The counter is R99's answer to "how many of today's requests were this?", and the log line
    is what an operator greps. Refusing must not cost either of them, and must not make the
    line claim a clamp that never happened: ``clamped=no`` stays ``no``, because nothing was
    shortened, and the one thing added is ``error_code=task_timeout`` on that same line.
    """
    before = budget_event_counts()["budget_unaffordable"]

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        with pytest.raises(ModelClockUnaffordable):
            authorize_or_refuse(
                model_tier_budget(ModelTier.ANALYSIS), UNAFFORDABLE_PROMPT_TOKENS
            )

    assert budget_event_counts()["budget_unaffordable"] == before + 1
    lines = [m for m in caplog.messages if MODEL_BUDGET_MARKER in m]
    assert len(lines) == 1, lines
    assert "clamped=no" in lines[0]
    assert "budget_verdict=budget_unaffordable" in lines[0]
    assert "error_code=" + TIMEOUT_ERROR_CODE in lines[0]
    assert "declared_max_tokens=1536" in lines[0] and "max_tokens=1536" in lines[0]


def test_sizing_a_call_without_a_send_decision_is_unchanged():
    """The opt-in half of the judgement: ``authorize`` still only sizes.

    R99's nails call this function directly and assert it returns an unshortened budget. A
    refusal raised there would be a refusal of the arithmetic rather than of the request, and
    would take the model boundary's whole pre-send story with it.
    """
    budget = model_tier_budget(ModelTier.ANALYSIS)

    authorized = authorize(budget, UNAFFORDABLE_PROMPT_TOKENS)

    assert authorized.verdict.unaffordable is True
    assert authorized.budget is budget, "the same object came back: nothing was sized down"
    assert authorized.budget.max_tokens == 1536


def test_no_tier_cap_moves_to_make_the_refusal_fit():
    """Judgement 5's witness: the guard borrows the tier budgets, it does not re-price them."""
    for tier, cap in TIER_MAX_TOKEN_DEFAULTS.items():
        assert tier_max_tokens(tier) == cap, tier.value
    assert min_answer_tokens() == DEFAULT_MIN_ANSWER_TOKENS


# ============ judgement 2: the code it reports, and what the refusal is not ============


def test_the_refusal_reports_a_ratified_code_and_not_an_invented_one():
    """``task_timeout`` is already in the closed enum, with this meaning."""
    codes = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    budget = model_tier_budget(ModelTier.ANALYSIS)
    refused = ModelClockUnaffordable(
        budget,
        UNAFFORDABLE_PROMPT_TOKENS,
        max_tokens_verdict(budget, UNAFFORDABLE_PROMPT_TOKENS),
    )

    assert TIMEOUT_ERROR_CODE == "task_timeout"
    assert TIMEOUT_ERROR_CODE in codes
    assert refused.code == TIMEOUT_ERROR_CODE
    assert refused.code != CONTEXT_LIMIT_CODE


def test_the_refusal_is_a_slot_returning_refusal_not_a_second_window_finding():
    """Why the base class is ``ModelContextLimitExceeded``, stated as an assertion.

    ``app/agents/nodes.py`` hands the single local-model slot back on exactly that class, so
    the subclass relationship is the plumbing that keeps ``MODEL_MAX_CONCURRENCY=1`` from being
    wedged by a call that never ran. The two verdicts stay apart in everything a reader sees:
    the code, and a message that never mentions ``n_ctx``.
    """
    assert issubclass(ModelClockUnaffordable, ModelContextLimitExceeded)

    with pytest.raises(ModelClockUnaffordable) as refused:
        authorize_or_refuse(
            model_tier_budget(ModelTier.ANALYSIS), UNAFFORDABLE_PROMPT_TOKENS
        )

    text = str(refused.value)
    assert "n_ctx" not in text and CONTEXT_LIMIT_CODE not in text, text
    assert "affordable_max_tokens=723" in text
    assert refused.value.max_tokens == 1536, "nothing was shortened to earn this refusal"
    assert refused.value.tier is ModelTier.ANALYSIS

def test_a_fast_machine_is_never_refused_by_this_guard(monkeypatch):
    """The guard is about a clock, not about a tier name: recalibrated, it says nothing."""
    _fast_machine(monkeypatch)
    before = dict(budget_event_counts())

    for tier in ModelTier:
        authorized = authorize_or_refuse(model_tier_budget(tier), UNAFFORDABLE_PROMPT_TOKENS)
        assert authorized.verdict.unaffordable is False, tier.value
        assert authorized.budget.max_tokens == tier_max_tokens(tier), tier.value

    assert budget_event_counts() == before, "a machine that fits pays for nothing, counting included"


def test_an_unmeasured_prompt_and_a_stream_are_still_never_refused():
    """The two deliberate no-ops carry over.

    ``prompt_tokens=None`` says the call site did not measure, which is a fact about the call
    site and not about the machine, and a stream is billed for a stall between chunks rather
    than for the price of the whole answer. Neither can be priced out of the ceiling, so
    refusing on either would be an invention, not a judgement.
    """
    analysis = model_tier_budget(ModelTier.ANALYSIS)

    assert authorize_or_refuse(analysis, None).verdict.unaffordable is False
    assert authorize_or_refuse(analysis, 1000, stream=True).verdict.unaffordable is False


# =========== judgement 1, second half: the call sites, not the signatures ===========


class _CountingPrimary:
    """A provider double that reports what it was asked to send, and never sleeps."""

    def __init__(self):
        self.calls: list[dict] = []

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append(kwargs)
        return AIMessage(content="ok", response_metadata={"finish_reason": "stop"})

    def stream(self, *args, **kwargs):
        self.calls.append(kwargs)
        yield AIMessage(content="ok", response_metadata={"finish_reason": "stop"})

    def bind_tools(self, tools):
        return self


class _CountingCompletions:
    def __init__(self):
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            delta = type("Delta", (), {"content": "ok"})()
            chunk = type("ChunkChoice", (), {"delta": delta})()
            return iter([type("Chunk", (), {"choices": [chunk]})()])
        message = type("Msg", (), {"content": "ok"})()
        choice = type("Choice", (), {"message": message, "finish_reason": "stop"})()
        usage = type("Usage", (), {"prompt_tokens": 10, "completion_tokens": 5})()
        return type("Resp", (), {"choices": [choice], "usage": usage})()


def handler_with_stub_client() -> ModelHandler:
    """A handler whose transport is a counter, built without touching the host model server.

    Assembled by field rather than through ``__init__``: the real constructor opens an
    ``OpenAI`` client against whatever the environment advertises, and R56 exists to keep a
    test run away from the host model port. Judgement 1 only needs the boundary that sizes and
    sends a call, so it gets exactly those two parts.
    """
    handler = ModelHandler.__new__(ModelHandler)
    handler.local_model = "test-model"
    handler.request_timeout = model_budget.request_timeout_ceiling_seconds()
    handler._native_supported = False
    handler._native_verdict = "untried"
    handler._native_request_rejections = 0
    handler._budget = model_budget.default_model_budget()
    completions = _CountingCompletions()
    chat = type("Chat", (), {"completions": completions})()
    handler.ollama_client = type("Client", (), {"chat": chat})()
    handler.local_client = handler.ollama_client
    handler.completions = completions
    return handler


def test_both_model_boundaries_reach_the_clamp_arithmetic(monkeypatch):
    """The rule this pipeline bought with an accident: look at the callers.

    ``max_tokens_verdict`` having the right signature proves nothing about run6. This drives
    the two boundaries that actually put a request on the wire and records that each of them
    asked the clamp question about its own tier, so "this leg never walked the clamp path" is
    excluded as an explanation of ``clamped=no`` rather than assumed away from a function name.
    """
    seen: list[tuple] = []
    real = model_budget.max_tokens_verdict

    def recorder(budget, prompt_tokens, *, stream=False):
        verdict = real(budget, prompt_tokens, stream=stream)
        seen.append((str(verdict.tier.value), verdict.stream, prompt_tokens))
        return verdict

    monkeypatch.setattr(model_budget, "max_tokens_verdict", recorder)

    primary = _CountingPrimary()
    graph_model = nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.ANALYSIS),
    )
    graph_model.invoke([HumanMessage(content="x" * 400)])

    handler = handler_with_stub_client()
    handler.chat(messages=[{"role": "user", "content": "x" * 400}], stream=False)

    tiers = {tier for tier, _, _ in seen}
    assert "analysis" in tiers and "rewrite" in tiers, seen
    assert primary.calls and handler.completions.calls, "both legs put a request on the wire"
    assert all(stream is False for _, stream, _ in seen), seen