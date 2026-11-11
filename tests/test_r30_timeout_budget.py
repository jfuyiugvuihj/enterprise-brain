"""R30 judgement (2): the clock a call gets is derived from the size of its prompt.

``_make_model`` used to take one int and spend it twice -- as ``ChatOpenAI(timeout=)`` and as
``httpx.Client(timeout=)`` -- so connect and read shared one number, and a long prompt was
paid for out of the same wall clock as a long answer. Every test below asks a question that
only makes sense once those are separate quantities: a bigger prompt, a slower machine, a
stream that keeps arriving.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest
from langchain_core.messages import HumanMessage

from app.agents import nodes, orchestrator
from app.agents.contracts import STREAM_STALL_TOKENS, ModelTier
from app.common import model_budget
from app.common.model_budget import (
    DEFAULT_CONTEXT_TOKENS,
    http_timeout,
    model_tier_budget,
    request_timeout_ceiling_seconds,
    tier_max_tokens,
)
from app.common.model_handler import ModelHandler

_REPOSITORY = Path(__file__).resolve().parents[1]


class _StubModel:
    def __init__(self, content: str = "ok"):
        self.content = content
        self.invoked_with = None

    def invoke(self, messages, config=None, **kwargs):
        self.invoked_with = (messages, kwargs)
        return SimpleNamespace(content=self.content)

    def bind_tools(self, tools):
        return self


@pytest.fixture
def factory_calls(monkeypatch):
    """Capture what ``_make_model`` would have built, without building a client."""
    seen: list[dict] = []

    def _fake_factory(tier=ModelTier.ANALYSIS, *, prompt=None):
        budget = model_tier_budget(tier)
        seen.append(
            {
                "tier": budget.tier,
                "prompt_tokens": model_budget.estimate_prompt_tokens(prompt),
                "read_seconds": budget.read_timeout_seconds(
                    model_budget.estimate_prompt_tokens(prompt)
                ),
            }
        )
        return _StubModel()

    monkeypatch.setattr(nodes, "_make_model", _fake_factory)
    return seen


def _read(budget, prompt_tokens: int, *, stream: bool = False) -> float:
    return http_timeout(budget, prompt_tokens, stream=stream).read


def test_a_longer_prompt_buys_a_longer_clock():
    budget = model_tier_budget(ModelTier.CHAT)

    small = _read(budget, 200)
    large = _read(budget, 2000)

    assert large > small, (small, large)
    assert large - small == pytest.approx(1800 / budget.prefill_tokens_per_second * budget.timeout_margin)


def test_prefill_and_decode_are_two_separate_quantities():
    """One scalar could not express this, which is why a long prompt used to eat the answer."""
    budget = model_tier_budget(ModelTier.CODE)

    assert budget.prefill_seconds(350) == pytest.approx(10.0)
    assert budget.decode_seconds() == pytest.approx(tier_max_tokens(ModelTier.CODE) / 8.0)


def test_a_slower_machine_lengthens_the_clock_without_anything_being_guessed(monkeypatch):
    """The operator raises a rate; nobody re-picks a number of seconds.

    This is the whole point of the budget: the machine is the only thing that decides how
    long a request may take, so the clock has to move when the machine moves.
    """
    prompt_tokens = 200
    baseline = model_tier_budget(ModelTier.ALERT)
    monkeypatch.setenv("MODEL_DECODE_TOKENS_PER_SECOND", "2")
    slow = model_tier_budget(ModelTier.ALERT)

    assert slow.decode_seconds() == pytest.approx(baseline.decode_seconds() * 4)
    assert slow.read_timeout_seconds(prompt_tokens) > baseline.read_timeout_seconds(prompt_tokens)
    assert slow.timeout_ceiling_seconds == request_timeout_ceiling_seconds()


def test_connect_and_read_are_no_longer_the_same_number():
    budget = model_tier_budget(ModelTier.COMPRESS)

    timeout = http_timeout(budget, 500)

    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == budget.connect_timeout_seconds
    assert timeout.read > timeout.connect
    assert timeout.write == timeout.connect
    assert timeout.pool == budget.timeout_floor_seconds


def _needed(budget, prompt_tokens: int, *, stream: bool = False) -> float:
    """What this call would cost with no ceiling at all: the honest estimate."""
    return (
        budget.prefill_seconds(prompt_tokens)
        + budget.decode_seconds(stream=stream)
    ) * budget.timeout_margin


def test_a_small_prompt_still_gets_the_floor():
    """Below the floor the estimate is not trusted, because a spinning disk and a wedged
    request look the same at one-second resolution.

    A stalled stream with almost nothing to say is the only case short enough to reach
    the floor: it is billed for 64 tokens of decode, not for a whole answer.
    """
    budget = model_tier_budget(ModelTier.CHAT)

    assert _needed(budget, 1, stream=True) < budget.timeout_floor_seconds
    assert _read(budget, 1, stream=True) == pytest.approx(budget.timeout_floor_seconds)


def test_the_ceiling_is_the_documented_one_request_timeout(monkeypatch):
    monkeypatch.setenv("MODEL_REQUEST_TIMEOUT", "20")

    budget = model_tier_budget(ModelTier.ANALYSIS)

    assert _read(budget, 4000) == 20.0
    assert budget.timeout_ceiling_seconds == 20.0


def test_an_unknown_prompt_is_sized_for_the_largest_prompt_the_tier_may_send():
    """None means "nobody measured it", which must never mean "assume it is cheap"."""
    budget = model_tier_budget(ModelTier.CODE)

    assert _read(budget, None) == pytest.approx(
        min(
            budget.timeout_ceiling_seconds,
            max(
                budget.timeout_floor_seconds,
                (
                    budget.prefill_seconds(budget.input_budget_tokens)
                    + budget.decode_seconds()
                )
                * budget.timeout_margin,
            ),
        )
    )
    assert budget.input_budget_tokens == DEFAULT_CONTEXT_TOKENS - tier_max_tokens(ModelTier.CODE)


def test_a_stream_is_billed_for_a_stall_not_for_the_whole_answer():
    """Bytes keep arriving, so read is an inter-chunk allowance; the full cap would be minutes."""
    budget = model_tier_budget(ModelTier.ANALYSIS)

    streaming = _read(budget, 1000, stream=True)
    blocking = _read(budget, 1000, stream=False)

    assert streaming < blocking
    assert budget.decode_seconds(stream=True) * budget.decode_tokens_per_second == STREAM_STALL_TOKENS


def test_the_factory_hands_the_client_a_split_clock_not_a_scalar(monkeypatch):
    built: dict = {}

    class _CapturingChatOpenAI:
        def __init__(self, **kwargs):
            built.update(kwargs)

    monkeypatch.setenv("LOCAL_MODEL_NAME", "r30-fake-model")
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", "http://example.invalid:1/v1")
    monkeypatch.setattr(nodes, "ChatOpenAI", _CapturingChatOpenAI)

    model = nodes._make_model(ModelTier.COMPRESS, prompt="x" * 400)

    assert isinstance(built["timeout"], httpx.Timeout)
    assert built["http_client"].timeout.read == built["timeout"].read
    assert built["http_client"].timeout.connect == built["timeout"].connect
    assert model.budget.tier is ModelTier.COMPRESS


@pytest.mark.parametrize(
    "tier",
    [tier for tier in ModelTier if tier is not ModelTier.REWRITE],
)
def test_a_model_built_for_a_tier_carries_that_tiers_budget(tier):
    """Construction and per-call sizing share one budget object, or the cap is decoration."""
    model = nodes._ResilientModel(_StubModel(), budget=model_tier_budget(tier))

    assert model.budget.max_tokens == tier_max_tokens(tier)


def test_the_four_short_call_sites_size_their_own_prompt(factory_calls, monkeypatch):
    """The four places that used to pass ``timeout=30`` are now tier-and-prompt sized."""
    from app.agents import tools
    from app.api.v1 import alerts

    # plan() short-circuits on a deterministic plan; this test is about which tier and
    # which prompt the site hands the factory, so the planner is held out of the way.
    monkeypatch.setattr(nodes, "build_task_plan", lambda question: [])

    nodes.respond({"messages": [HumanMessage(content="你好")]})
    nodes.plan({"messages": [HumanMessage(content="查一下报销制度，并且看看门店利润")]})
    tools._llm_pandas_code(pd.DataFrame({"收入": [1, 2]}), "收入合计是多少")
    alerts._ai_analysis({"name": "收入下滑", "metric": "revenue", "op": "<", "threshold": 1}, 0.5)

    assert [call["tier"] for call in factory_calls] == [
        ModelTier.CHAT,
        ModelTier.PLAN,
        ModelTier.CODE,
        ModelTier.ALERT,
    ]
    assert all(call["prompt_tokens"] for call in factory_calls), factory_calls


def test_the_short_tiers_get_shorter_clocks_than_the_prose_tier():
    """A greeting that is allowed 120 s of silence is a bug waiting for a slow afternoon."""
    short = model_tier_budget(ModelTier.CHAT)
    prose = model_tier_budget(ModelTier.ANALYSIS)

    assert short.read_timeout_seconds(100) < prose.read_timeout_seconds(100)


#: The files that talk to the local model. A database or webhook timeout is a different
#: quantity, and connect_timeout/socket_timeout are not the model clock at all.
MODEL_BOUNDARY_FILES = (
    "app/agents/nodes.py",
    "app/agents/orchestrator.py",
    "app/agents/tools.py",
    "app/api/v1/alerts.py",
    "app/common/model_handler.py",
    "app/common/model_budget.py",
)


def test_no_numeric_model_timeout_literal_is_left_on_the_boundary():
    """Every model timeout on the boundary is now a derived quantity or a named default."""
    pattern = re.compile(r"(?<![A-Za-z_])timeout\s*=\s*[0-9]")
    offenders = [
        relative
        for relative in MODEL_BOUNDARY_FILES
        if pattern.search((_REPOSITORY / relative).read_text(encoding="utf-8"))
    ]

    assert offenders == [], offenders


def test_the_worker_graphs_are_built_on_the_prose_tier():
    assert orchestrator.main_model.budget.tier is ModelTier.ANALYSIS
    assert orchestrator.main_model.budget.max_tokens == tier_max_tokens(ModelTier.ANALYSIS)


def test_the_rewrite_handler_shares_the_budget_vocabulary(monkeypatch):
    """The second model boundary must not keep its own idea of a default timeout."""
    monkeypatch.delenv("MODEL_REQUEST_TIMEOUT", raising=False)

    assert ModelHandler().request_timeout == request_timeout_ceiling_seconds() == 120.0
