"""R30 judgement (1): every tier states an explicit output cap, and every tier is called.

``ModelBudget.max_tokens`` used to be a field that existed and was never assigned, while
``_make_model`` handed one flat ``timeout=30`` scalar to five call sites. A cap nobody sets
buys nothing, so these tests follow the number all the way to the wire arguments, and then
check that no tier is a contract without a caller.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage

from app.agents.contracts import ModelBudget, ModelTier
from app.agents import nodes
from app.common.model_budget import (
    TIER_MAX_TOKEN_DEFAULTS,
    estimate_prompt_tokens,
    max_tokens_verdict,
    model_tier_budget,
    thinking_extra_body,
    tier_max_tokens,
    tier_max_tokens_env_name,
)

_REPOSITORY = Path(__file__).resolve().parents[1]
ALL_TIERS = sorted(ModelTier, key=lambda tier: tier.value)


class _RecordingModel:
    """Stand-in provider: records what would have gone over the wire, opens no socket."""

    def __init__(self, error: Exception | None = None):
        self.calls: list[dict] = []
        self.error = error

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if self.error is not None:
            raise self.error
        return SimpleNamespace(content="ok", response_metadata={"finish_reason": "stop"})

    def bind_tools(self, tools):
        return self



def _resilient(tier: ModelTier, error: Exception | None = None):
    """A model built the way ``_make_model`` builds one: with this tier's budget."""
    primary = _RecordingModel(error=error)
    model = nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(tier),
    )
    return model, primary


def test_no_tier_is_left_without_an_output_cap():
    """The dead-contract check: a declared field that nothing assigns is not a limit."""
    for tier in ALL_TIERS:
        budget = ModelBudget(tier=tier)
        assert isinstance(budget.max_tokens, int), tier
        assert budget.max_tokens > 0, tier
        assert budget.max_tokens == tier_max_tokens(tier), tier


def test_an_unassigned_budget_still_carries_its_tier_cap():
    """AgentContext builds ModelBudget() with no numbers at all; unset must not mean unlimited."""
    budget = ModelBudget()

    assert budget.tier is ModelTier.ANALYSIS
    assert budget.max_tokens == TIER_MAX_TOKEN_DEFAULTS[ModelTier.ANALYSIS]
    assert budget.context_limit_tokens == 4096


def test_a_cap_given_by_the_caller_wins_over_the_configured_one():
    budget = ModelBudget(tier=ModelTier.CHAT, max_tokens=99)

    assert budget.max_tokens == 99


#: The prompt the test below sends, kept as a value so the expectation is computed from the
#: same bytes rather than from a number that happens to match today.
GREETING = [HumanMessage(content="你好")]


def test_the_cap_is_declared_on_the_request_not_only_in_the_profile():
    """Judgement (1) proven at the boundary: max_tokens is on the wire for every tier.

    R99 rewrote the right-hand side of the last assertion. It used to read
    ``{"max_tokens": tier_max_tokens(tier)}``, and under the shipped defaults that is still
    the number on the wire -- but for a reason this file never claimed: the thinking floor
    (MODEL_MIN_ANSWER_TOKENS -- 1537 when R99 wrote this, 1536 since R100 re-measured it on the
    thinking-free link this client now sends) now forbids shortening an analysis request down to the 811
    tokens the CPU-only calibration says the clock can pay for, so the declared cap survives
    untouched and the old assertion passed by coincidence. What holds in every configuration
    is "the wire carries the cap this call was authorised to", so that is what is asserted
    now. The test below is the pair that keeps that from being a tautology.
    """
    for tier in ALL_TIERS:
        model, primary = _resilient(tier)

        model.invoke(GREETING, config=None)

        authorised = max_tokens_verdict(model.budget, estimate_prompt_tokens(GREETING))
        assert len(primary.calls) == 1, tier
        #: R100 added a second field to this body, composed here from the boundary that owns it so
        #: this file keeps pinning the cap and cannot drift into a second opinion about thinking.
        assert primary.calls[0]["extra_body"] == {
            "max_tokens": authorised.max_tokens, **thinking_extra_body(),
        }, tier
        assert authorised.max_tokens <= tier_max_tokens(tier), tier


def test_the_wire_carries_the_shortened_cap_when_the_clock_overrules_the_profile(monkeypatch):
    """Measured rates, a window that makes the request legal, a cap the clock cannot pay for.

    37 tok/s over (120 / 1.15 - 489/105) s writes 3688 tokens, so the request goes out with
    3688 and not 4096: judgement 3 shortens the answer, never the deadline.
    """
    monkeypatch.setenv("MODEL_PREFILL_TOKENS_PER_SECOND", "105")
    monkeypatch.setenv("MODEL_DECODE_TOKENS_PER_SECOND", "37")
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "8192")
    monkeypatch.setenv("MODEL_TIER_ANALYSIS_MAX_TOKENS", "4096")

    model, primary = _resilient(ModelTier.ANALYSIS)
    messages = [HumanMessage(content="数" * 485)]

    model.invoke(messages, config=None)

    assert tier_max_tokens(ModelTier.ANALYSIS) == 4096
    assert primary.calls[0]["extra_body"] == {
        "max_tokens": 3688, **thinking_extra_body(),
    }, primary.calls[0]


def test_a_cap_never_exceeds_the_window_it_has_to_share():
    """n_ctx is a hard ceiling: a tier that claims more than the window cannot honour it."""
    for tier in ALL_TIERS:
        budget = model_tier_budget(tier)
        assert budget.max_tokens < budget.context_limit_tokens, tier


def test_the_tier_cap_override_is_named_by_one_formula(monkeypatch):
    monkeypatch.setenv(tier_max_tokens_env_name(ModelTier.CODE), "64")

    assert tier_max_tokens(ModelTier.CODE) == 64
    assert model_tier_budget(ModelTier.CODE).max_tokens == 64


def test_every_tier_has_a_live_call_site():
    """A tier nobody calls is the same dead contract this ticket is deleting.

    ``contracts.py`` is skipped on purpose: naming a tier in its own definition is not the
    same as spending it somewhere.
    """
    sources = {
        path: path.read_text(encoding="utf-8")
        for path in (_REPOSITORY / "app").rglob("*.py")
        if path.name != "contracts.py"
    }

    for tier in ALL_TIERS:
        emitter = f"ModelTier.{tier.name}"
        hits = sorted(path.name for path, text in sources.items() if emitter in text)
        assert hits, f"{tier.value} is declared but no call site uses it"


def test_no_call_site_hands_the_factory_a_bare_timeout():
    """The five ``timeout=30`` constants are gone, and the shape cannot come back quietly.

    The factory keeps no compatibility shim for the old keyword on purpose: a caller that
    still wants a flat number of seconds has to add the parameter back, not forget it.
    """
    offenders = []
    # app and scripts only: this very file names the forbidden shape to keep it away,
    # and a guard that cannot tell a call site from an accusation is not a guard.
    for folder in ("app", "scripts"):
        for path in (_REPOSITORY / folder).rglob("*.py"):
            if "_make_model(timeout" in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(_REPOSITORY).as_posix())

    assert offenders == [], offenders


def test_the_factory_asks_for_a_tier_rather_than_a_number_of_seconds():
    with pytest.raises(TypeError):
        nodes._make_model(timeout=30)  # type: ignore[call-arg]


def test_the_default_tier_is_the_one_that_writes_answers():
    """Sizing an unlabelled call down to a greeting cap would truncate prose."""
    assert model_tier_budget(ModelTier.ANALYSIS).max_tokens == max(
        TIER_MAX_TOKEN_DEFAULTS.values()
    )
