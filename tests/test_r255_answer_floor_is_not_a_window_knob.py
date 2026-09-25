"""R255 judgement (4): the answer floor stays where the measurement put it.

``MODEL_MIN_ANSWER_TOKENS=1536`` is the smallest output cap this model has been recorded
answering at all once thinking is switched off (跟进单 §42 row #6; R100 re-measured the value
for the link that ships). It is also the number an operator reaches for when a window refusal
arrives, because at the analysis tier it happens to equal the tier cap and therefore *looks*
like the same knob. It is not: the guard that refuses ``prompt_tokens + max_tokens > n_ctx``
reads the tier's declared cap, and never subtracts the floor at all.

So the floor is not lowered by this ticket, and these tests are the shape of that claim:
turning the floor down to something absurd fits not one more prompt token, the coherence plan
reports the move as its own red reason, and the cap an answer is never shortened below is
still 1536.
"""

import pytest

from app.agents.contracts import CONTEXT_LIMIT_CODE, ModelTier
from app.common import model_budget as mb
from app.common.model_budget import (
    DEFAULT_MIN_ANSWER_TOKENS,
    ModelContextLimitExceeded,
    authorize,
    budget_env_defaults,
    max_tokens_verdict,
    min_answer_tokens,
    model_tier_budget,
    window_plan,
)

REAL_REFUSED_PROMPTS = (2691, 2778)


@pytest.fixture(autouse=True)
def window_as_shipped(monkeypatch):
    for name in (
        "MODEL_CONTEXT_TOKENS",
        "MODEL_MIN_ANSWER_TOKENS",
        "MODEL_TIER_ANALYSIS_MAX_TOKENS",
        "MODEL_PREFILL_TOKENS_PER_SECOND",
        "MODEL_DECODE_TOKENS_PER_SECOND",
        "MODEL_MAX_CONCURRENCY",
        "MODEL_CONCURRENCY_WAIT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_the_floor_that_ships_is_the_floor_that_was_measured():
    """1536, in the code, in the defaults, and in what the reader resolves."""
    assert DEFAULT_MIN_ANSWER_TOKENS == 1536
    assert min_answer_tokens() == 1536
    assert budget_env_defaults()["MODEL_MIN_ANSWER_TOKENS"] == 1536


@pytest.mark.parametrize("floor", ["1", "64", "1535"])
@pytest.mark.parametrize("prompt_tokens", REAL_REFUSED_PROMPTS)
def test_lowering_the_floor_fits_not_one_more_prompt_token(monkeypatch, prompt_tokens, floor):
    """判据④ as an experiment: the refusal is arithmetic about the tier cap, not the floor.

    2691 + 1536 is 4227 and 2778 + 1536 is 4314 against a 4096 window, and every one of those
    sums is true whatever this variable says. An implementation that subtracted the floor from
    the window instead of the declared cap would go red here -- which is also the reason the
    "fix" cannot be smuggled in later by somebody reusing this number for two purposes.
    """
    monkeypatch.setenv("MODEL_MIN_ANSWER_TOKENS", floor)

    assert min_answer_tokens() == int(floor)
    with pytest.raises(ModelContextLimitExceeded) as refused:
        authorize(model_tier_budget(ModelTier.ANALYSIS), prompt_tokens)

    assert refused.value.code == CONTEXT_LIMIT_CODE
    assert refused.value.declared_max_tokens == 1536
    assert refused.value.required_context_tokens == prompt_tokens + 1536
    assert refused.value.over_by_tokens == prompt_tokens + 1536 - 4096


@pytest.mark.parametrize("floor", ["1", "64", "1535"])
def test_a_moved_floor_is_reported_as_its_own_red_reason(monkeypatch, floor):
    """The floor is configurable; the measurement is not, and the plan keeps them apart."""
    monkeypatch.setenv("MODEL_MIN_ANSWER_TOKENS", floor)
    plan = window_plan(ModelTier.ANALYSIS)

    assert plan.min_answer_tokens == int(floor)
    assert plan.measured_min_answer_tokens == DEFAULT_MIN_ANSWER_TOKENS
    assert plan.floor_below_measurement is True
    assert mb.WINDOW_RED_FLOOR in plan.red_reasons
    assert plan.coherent is False


def test_the_refusal_says_the_floor_is_not_the_knob_to_move(monkeypatch):
    monkeypatch.setenv("MODEL_MIN_ANSWER_TOKENS", "64")

    with pytest.raises(ModelContextLimitExceeded) as refused:
        authorize(model_tier_budget(ModelTier.ANALYSIS), 2778)

    text = str(refused.value)
    assert "MODEL_MIN_ANSWER_TOKENS is not a window knob" in text
    assert "subtracts the tier cap, not the floor" in text

def test_the_floor_still_holds_the_answer_cap_up(monkeypatch):
    """The floor does its original job here, unchanged: an answer is never shortened past it.

    On a machine calibrated to the 2026-09-25 rates with a 45 s ceiling, this tier's own answer
    is unaffordable at 1498 tokens -- and the cap stays at 1536, because shortening it further
    is the empty-answer region. Same call, floor pushed below the measurement: the clamp
    happens. That pair is the evidence that 1536 is load-bearing, and the opposite of a knob
    for fitting a bigger prompt.
    """
    monkeypatch.setenv("MODEL_PREFILL_TOKENS_PER_SECOND", "1200")
    monkeypatch.setenv("MODEL_DECODE_TOKENS_PER_SECOND", "40")
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT", "45")
    budget = model_tier_budget(ModelTier.ANALYSIS)

    held = max_tokens_verdict(budget, 2000)
    assert held.affordable_max_tokens == 1498
    assert held.unaffordable is True and held.clamped is False
    assert held.max_tokens == 1536, "the floor is what kept the cap from being shaved"

    monkeypatch.setenv("MODEL_MIN_ANSWER_TOKENS", "1024")
    moved = max_tokens_verdict(model_tier_budget(ModelTier.ANALYSIS), 2000)
    assert moved.clamped is True and moved.max_tokens == 1498
    assert window_plan(ModelTier.ANALYSIS).floor_below_measurement is True


def test_no_tier_cap_moved_to_make_the_refusal_fit():
    """The other number in that subtraction is also a ratified default, and it stayed put."""
    assert mb.TIER_MAX_TOKEN_DEFAULTS[ModelTier.ANALYSIS] == 1536
    for tier, cap in mb.TIER_MAX_TOKEN_DEFAULTS.items():
        assert mb.tier_max_tokens(tier) == cap, tier.value
    assert model_tier_budget(ModelTier.ANALYSIS).max_tokens == 1536