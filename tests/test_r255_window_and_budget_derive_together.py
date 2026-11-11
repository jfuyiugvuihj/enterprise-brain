"""R255 judgement (1): the window and the budget around it are derived in one place.

The 2026-09-25 real window put the report lane's first refusal on the map: ``prompt_tokens``
2691 and 2778, both at ``max_tokens=1536``, against ``n_ctx=4096``, twice on one request
(``report-04``, request_id edf880c8696c4bdc8af1e62db40ede58) -- the numbers recorded in
docs/testing/run8-phase2-readout-2026-09-25.md section 2. The obvious operator reaction is to
raise MODEL_CONTEXT_TOKENS. The obvious reaction is also wrong on its own, and this file is
the nail that keeps it wrong: the window buys a longer worst-case request, and a longer
worst-case request has to be paid for by a clock and by a queue that were not resized.

Nothing here touches a model, a port or a container: every judgement below is arithmetic on
injected numbers, which is the whole point of a guard that fires before a request is sent.
"""

import pytest

from app.agents.contracts import CONTEXT_LIMIT_CODE, ModelTier
from app.common import model_budget as mb
from app.common.model_budget import (
    ModelClockUnaffordable,
    ModelContextLimitExceeded,
    authorize,
    authorize_or_refuse,
    model_tier_budget,
    queue_gates,
    window_plan,
)

#: The two prompt sizes this ticket was opened for.
REAL_REFUSED_PROMPTS = (2691, 2778)
#: The shortfall, computed by hand from the recorded window: 2691 + 1536 - 4096 = 131.
REAL_OVER_BY = {2691: 131, 2778: 218}
#: The rates measured on the shipping container the same afternoon (run8 phase-2 plan, ch. 5).
MEASURED_PREFILL = "1200"
MEASURED_DECODE = "40"
#: The window those rates can pay for, and the one the ticket asks for.
PAIRED_WINDOW = 16384
BIG_WINDOW = 32768


@pytest.fixture(autouse=True)
def stock_configuration(monkeypatch):
    """Every budget variable unset: the code defaults are the configuration under test.

    A host shell can carry any of these, and a ticket about configuration coherence cannot be
    judged against whatever the machine it is checked out on happens to export.
    """
    for name in (
        "MODEL_CONTEXT_TOKENS",
        "MODEL_MIN_ANSWER_TOKENS",
        "MODEL_REQUEST_TIMEOUT",
        "MODEL_PREFILL_TOKENS_PER_SECOND",
        "MODEL_DECODE_TOKENS_PER_SECOND",
        "MODEL_TIMEOUT_MARGIN",
        "MODEL_MAX_CONCURRENCY",
        "MODEL_CONCURRENCY_WAIT_SECONDS",
        "MODEL_TIER_ANALYSIS_MAX_TOKENS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_the_window_plan_reads_the_same_numbers_the_guards_enforce():
    """One derivation site means the plan and the two guards cannot disagree by construction.

    ``MODEL_REQUEST_TIMEOUT`` has exactly one reader in this repository, and the slots and the
    queue have exactly one owner. A plan that kept its own default for either would be a second
    copy, and a second copy is the defect this ticket is about.
    """
    budget = model_tier_budget(ModelTier.ANALYSIS)
    slots, queue_seconds = queue_gates()
    plan = window_plan(budget)

    assert plan.timeout_ceiling_seconds == mb.request_timeout_ceiling_seconds()
    assert plan.timeout_ceiling_seconds == budget.timeout_ceiling_seconds
    assert (plan.max_concurrency, plan.queue_wait_seconds) == (slots, queue_seconds)
    gate = mb.default_model_budget()
    assert (slots, queue_seconds) == (gate.max_concurrency, gate.default_wait_seconds), (
        "the queue the plan divides is the queue callers actually wait on"
    )


def test_the_plan_says_what_the_window_costs_in_the_order_the_physics_happens():
    """The formula, recomputed independently of the implementation."""
    plan = window_plan(ModelTier.ANALYSIS)
    room = plan.context_limit_tokens - plan.declared_max_tokens
    expected = plan.timeout_margin * (
        room / plan.prefill_tokens_per_second
        + plan.declared_max_tokens / plan.decode_tokens_per_second
    )

    assert plan.prompt_room_tokens == room
    assert plan.prompt_room_tokens == model_tier_budget(ModelTier.ANALYSIS).input_budget_tokens
    assert plan.seconds_at_full_window == pytest.approx(expected)
    assert plan.required_timeout_seconds == pytest.approx(expected)
    assert plan.queue_seconds_per_caller == pytest.approx(
        plan.queue_wait_seconds / plan.max_concurrency
    )


@pytest.mark.parametrize("prompt_tokens", REAL_REFUSED_PROMPTS)
def test_the_two_real_sizes_are_refused_by_the_window_as_shipped(prompt_tokens):
    """The starting point, restated as something this tree can reproduce offline."""
    with pytest.raises(ModelContextLimitExceeded) as refused:
        authorize(model_tier_budget(ModelTier.ANALYSIS), prompt_tokens)

    assert refused.value.code == CONTEXT_LIMIT_CODE
    assert refused.value.over_by_tokens == REAL_OVER_BY[prompt_tokens]
    assert refused.value.required_context_tokens == prompt_tokens + 1536
    assert refused.value.prompt_room_tokens == 4096 - 1536


def test_raising_only_the_window_is_red_and_names_the_other_two_heads():
    """THE counter-evidence nail of this ticket: one head moved, so the plan reads red.

    An operator who edits MODEL_CONTEXT_TOKENS alone has widened the guard, not the machine.
    Delete the ``min(ceiling, queue)`` coupling in
    ``WindowPlan.maximum_coherent_context_tokens``, or let ``window_plan`` size a window
    without its clock and queue, and this is the test that goes red -- which is the property
    judgement (1) asked for: "only one head changed" has to be detectable, not survivable.
    """
    plan = window_plan(ModelTier.ANALYSIS, context_limit_tokens=PAIRED_WINDOW)

    assert plan.context_limit_tokens == PAIRED_WINDOW
    assert plan.coherent is False
    assert set(plan.red_reasons) == {mb.WINDOW_RED_CLOCK, mb.WINDOW_RED_QUEUE}
    assert plan.clock_binds and plan.queue_binds
    #: On the CPU-only rates this file still defaults to, this tier's own answer (1536 tokens
    #: at 8 tok/s) costs 192 s -- longer than the clock and longer than the queue, so the
    #: honest verdict is that no window is coherent until a rate or a ceiling moves.
    assert plan.maximum_coherent_context_tokens == 0
    assert plan.seconds_at_full_window > plan.timeout_ceiling_seconds
    assert plan.seconds_at_full_window > plan.queue_seconds_per_caller

def test_raising_only_the_window_moves_the_refusal_one_guard_later(monkeypatch):
    """The behavioural half of the same sentence: the request still never goes out.

    ``MODEL_CONTEXT_TOKENS=16384`` written into an env file on a machine whose rates are still
    the shipped pair turns a window refusal into a clock refusal. That is what "it fixed
    nothing" looks like from the caller's side: a different code, the same outage, and one more
    line for somebody to interpret at three in the morning.
    """
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", str(PAIRED_WINDOW))
    budget = model_tier_budget(ModelTier.ANALYSIS)

    with pytest.raises(ModelClockUnaffordable) as refused:
        authorize_or_refuse(budget, 2778)

    assert refused.value.code == mb.TIMEOUT_ERROR_CODE
    assert refused.value.code != CONTEXT_LIMIT_CODE
    assert refused.value.plan is None, "a clock finding computes no window plan"


def test_the_shipped_default_pair_is_also_incoherent_without_anybody_touching_it():
    """The reading that must not be lost: this is arithmetic, so no real window was needed.

    R214's calibration window found the container running with neither rate set -- on the
    CPU-only defaults -- and reported ``budget_unaffordable`` lines from that. The plan reaches
    the same conclusion from the two default constants and the two budgets alone.
    """
    assert mb.DEFAULT_PREFILL_TOKENS_PER_SECOND == 35.0
    assert mb.DEFAULT_DECODE_TOKENS_PER_SECOND == 8.0
    plan = window_plan(ModelTier.ANALYSIS)

    assert plan.coherent is False
    assert plan.maximum_coherent_context_tokens == 0
    assert plan.admits(2778) is False


# ==================== judgement (1), the green half: the paired raise ====================


@pytest.fixture
def measured_rates(monkeypatch):
    """The two rates measured on the shipping container on 2026-09-25 (plan, ch. 5)."""
    monkeypatch.setenv("MODEL_PREFILL_TOKENS_PER_SECOND", MEASURED_PREFILL)
    monkeypatch.setenv("MODEL_DECODE_TOKENS_PER_SECOND", MEASURED_DECODE)


@pytest.mark.parametrize("prompt_tokens", REAL_REFUSED_PROMPTS)
def test_the_paired_raise_puts_both_real_sizes_through(measured_rates, monkeypatch, prompt_tokens):
    """The path this ticket exists to hand over: window raised *with* the budget around it."""
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", str(PAIRED_WINDOW))
    budget = model_tier_budget(ModelTier.ANALYSIS)

    plan = window_plan(budget)
    assert plan.coherent is True, plan.red_reasons
    assert plan.admits(prompt_tokens) is True

    authorized = authorize_or_refuse(budget, prompt_tokens)
    assert authorized.budget.max_tokens == 1536, "nothing was shortened to earn this pass"


def test_the_coupling_is_a_number_and_not_a_mood(measured_rates):
    """The worked figures the env sample documents, produced by the code, not by this test.

    46.6 s is what today's 4096 costs at those rates, 58.4 s is what 16384 costs, and 18064 is
    the largest window a 60 s queue at one slot still pays for. ``.env.example`` prints all
    three; tests/test_r255_env_documents_the_conversion.py compares the file against these.
    """
    assert window_plan(ModelTier.ANALYSIS, context_limit_tokens=4096).seconds_at_full_window == (
        pytest.approx(46.6, abs=0.05)
    )
    plan = window_plan(ModelTier.ANALYSIS, context_limit_tokens=PAIRED_WINDOW)
    assert plan.seconds_at_full_window == pytest.approx(58.4, abs=0.05)
    assert plan.maximum_coherent_context_tokens == 18064
    assert plan.coherent is True


def test_the_queue_binds_long_before_the_clock_does(measured_rates):
    """Why the concurrency budget belongs in this derivation at all.

    A 32k window is comfortably inside a 120 s request ceiling at the measured rates -- and
    still incoherent, because at one slot the second caller would wait 74 s against a 60 s
    queue, and what that caller gets is the offline sentence rather than a late answer.
    """
    plan = window_plan(ModelTier.ANALYSIS, context_limit_tokens=BIG_WINDOW)

    assert plan.clock_binds is False, "the clock is not what stops this one"
    assert plan.queue_binds is True
    assert plan.seconds_at_full_window == pytest.approx(74.1, abs=0.05)
    assert set(plan.red_reasons) == {mb.WINDOW_RED_QUEUE}
    #: admits() judges one request; coherent judges the whole window as configured. A 2778-token
    #: prompt still fits inside a 32k window -- the incoherence is that the machine cannot
    #: wait for the worst case that window licenses.
    assert plan.admits(2778) is True


def test_the_concurrency_budget_is_read_here_and_never_raised_here(measured_rates):
    """本单的红线: 不许顺手把 MODEL_MAX_CONCURRENCY 从 1 抬到 2.

    The queue term divides by the slots, so a plan that "fixed" an incoherent window by
    multiplying the slots would be buying throughput nobody measured (1 / 2 / 4 routes came out
    38.6 / 40.6 / 39.9 tok/s aggregated) while spending 60 s of somebody else's patience. The
    number is asserted, not asserted-unchanged: raising the default turns this red.
    """
    assert mb.DEFAULT_MAX_CONCURRENCY == 1
    assert window_plan(ModelTier.ANALYSIS).max_concurrency == 1
    assert window_plan(ModelTier.ANALYSIS, context_limit_tokens=BIG_WINDOW).queue_binds is True