"""R255 judgement (3): the env sample has to hand an operator the whole conversion.

Two claims belong next to MODEL_CONTEXT_TOKENS, and this file reads them out of the file the
way an operator would:

  * what actually makes an edit take effect -- and the honest answer is narrower than the
    sentence that used to circulate: these values are resolved when compose *creates* the
    container, so an edit alone and a restart alone both change nothing, while an image
    rebuild is only needed for a DEFAULT_* constant in the code (跟进单 §70 measured this and
    retired the older, wider wording in runbook P-8);
  * the arithmetic that connects the window to the two rates, the request ceiling and the
    queue, because a window raised without them is a refusal that changes error code rather
    than an outage that ends.

Every number quoted in the comment block is recomputed here from the code. If the formula
moves and the prose does not, that is a red test on purpose: documentation that cannot be
recomputed is how "改了 .env 不重建镜像等于没改" became a half-truth nobody could check.
"""

import re
from pathlib import Path

import pytest

from app.agents.contracts import ModelTier
from app.common.model_budget import (
    DEFAULT_CONTEXT_TOKENS,
    DEFAULT_MIN_ANSWER_TOKENS,
    budget_env_defaults,
    min_answer_tokens,
    tier_max_tokens,
    window_plan,
)

REPOSITORY = Path(__file__).resolve().parents[1]
ENV_SAMPLE = REPOSITORY / ".env.example"
SERVER_SAMPLE = REPOSITORY / "deploy" / ".env.server.example"

#: The rate pair the window block quotes, i.e. the 2026-09-25 measurement in ch. 5 of
#: docs/testing/run8-phase2-plan-2026-09-25.md.
MEASURED = {"MODEL_PREFILL_TOKENS_PER_SECOND": "1200", "MODEL_DECODE_TOKENS_PER_SECOND": "40"}


@pytest.fixture(scope="module")
def sample():
    return ENV_SAMPLE.read_text(encoding="utf-8")


def window_block_of(sample: str) -> str:
    """The comment block an operator reads immediately above the window variable."""
    return sample[sample.index("# n_ctx of the local server") : sample.index("MODEL_CONTEXT_TOKENS=")]


@pytest.fixture
def window_block(sample):
    return window_block_of(sample)


@pytest.fixture
def floor_block(sample):
    start = sample.index("# The output cap an answer is never shortened below")
    end = sample.index("MODEL_MIN_ANSWER_TOKENS=")
    return sample[start:end]


@pytest.fixture
def concurrency_block(sample):
    start = sample.index("# MODEL_MAX_CONCURRENCY is a safety valve")
    end = sample.index("MODEL_MAX_CONCURRENCY=")
    return sample[start:end]


# ==================== the two claims ====================


def test_the_block_says_where_a_value_is_actually_read(window_block):
    """判据③, first half: an edit is not an effect, and a restart is not an edit's effect."""
    assert "when the container is CREATED" in window_block
    assert "docker restart" in window_block
    assert "--force-recreate" in window_block
    assert "env | grep MODEL_" in window_block
    assert "The image carries no" in window_block and ".env of its own" in window_block
    assert "code default" in window_block
    #: ...and the rebuild claim stays where it belongs: only a code constant needs one.
    assert "Only a" in window_block and "needs an image rebuild" in window_block


def test_the_block_says_the_server_has_to_agree_with_the_number(window_block):
    """The second physical fact: this file cannot resize the model server by itself."""
    assert "CLAIM ABOUT THE SERVER" in window_block
    assert "never sends" in window_block and "num_ctx" in window_block
    assert "A100 80G" in window_block, "the sentence the owner already knows belongs in the doc"
    assert "exceeds the" in window_block and "available context" in window_block
    assert "docs/perf/raw/rate_prefill.jsonl" in window_block, "the claim has to be checkable"


def test_the_block_names_every_variable_in_the_conversion(window_block):
    """判据③, second half: the formula, with all five knobs named in their own spelling."""
    for name in (
        "MODEL_CONTEXT_TOKENS",
        "MODEL_TIMEOUT_MARGIN",
        "MODEL_PREFILL_TOKENS_PER_SECOND",
        "MODEL_DECODE_TOKENS_PER_SECOND",
        "MODEL_REQUEST_TIMEOUT",
        "MODEL_CONCURRENCY_WAIT_SECONDS",
        "MODEL_MAX_CONCURRENCY",
    ):
        assert name in window_block, name
    assert "prompt room        = MODEL_CONTEXT_TOKENS - tier max_tokens" in window_block
    assert "worst-case seconds = MODEL_TIMEOUT_MARGIN * (" in window_block
    assert "MODEL_CONCURRENCY_WAIT_SECONDS / MODEL_MAX_CONCURRENCY" in window_block
    assert "largest coherent MODEL_CONTEXT_TOKENS" in window_block

@pytest.mark.parametrize(
    ("n_ctx", "seconds", "coherent"),
    [(4096, 46.6, True), (16384, 58.4, True), (32768, 74.1, False)],
)
def test_every_worked_number_in_the_block_is_a_number_the_code_produces(
    monkeypatch, sample, n_ctx, seconds, coherent
):
    """The block is allowed to quote 46.6 / 58.4 / 74.1 only because window_plan says so."""
    for name, value in MEASURED.items():
        monkeypatch.setenv(name, value)

    plan = window_plan(ModelTier.ANALYSIS, context_limit_tokens=n_ctx)

    assert plan.seconds_at_full_window == pytest.approx(seconds, abs=0.05)
    assert plan.coherent is coherent
    assert f"{seconds:.1f} s" in sample, f"the block stopped quoting {seconds}"


def test_the_largest_coherent_window_in_the_block_is_the_one_the_code_computes(monkeypatch, sample):
    for name, value in MEASURED.items():
        monkeypatch.setenv(name, value)

    plan = window_plan(ModelTier.ANALYSIS, context_limit_tokens=16384)

    assert plan.maximum_coherent_context_tokens == 18064
    assert "18064" in sample


def test_the_block_does_not_hide_the_shipped_rates_behind_the_gpu_numbers(sample):
    """The CPU-only default pair is the one a stock install refuses on, and the doc says so.

    1536 tokens at the shipped 8 tok/s is 192 s: longer than a 120 s ceiling and longer than a
    60 s queue, so no window is coherent. Writing only the GPU row would leave the operator who
    changes one line with the rates untouched reading a doc that is true of another machine.
    """
    plan = window_plan(ModelTier.ANALYSIS)

    assert plan.prefill_tokens_per_second == 35.0 and plan.decode_tokens_per_second == 8.0
    assert plan.declared_max_tokens / plan.decode_tokens_per_second == 192.0
    assert plan.maximum_coherent_context_tokens == 0
    assert "192 s" in sample
    assert "NO window is coherent" in sample


# ==================== the two claims that are not about the window line ====================


def test_the_floor_block_says_it_is_not_a_way_to_buy_room(floor_block):
    """判据④ 的文档半条: the floor is a measurement, and it is not in this arithmetic."""
    assert "NOT a lever" in floor_block
    assert "MODEL_CONTEXT_TOKENS" in floor_block
    assert "tier's output cap, not this floor" in floor_block
    assert "answer with nothing" in floor_block


def test_the_concurrency_block_quotes_the_measurement_that_killed_the_idea(concurrency_block):
    """并发不是调出来的: 1 / 2 / 4 routes came out a flat line on the shipping host."""
    assert "safety valve, not a throughput knob" in concurrency_block
    assert "38.6 / 40.6 /" in concurrency_block and "39.9 tok/s" in concurrency_block
    assert "OLLAMA_NUM_PARALLEL" in concurrency_block
    assert "MODEL_CONCURRENCY_WAIT_SECONDS" in concurrency_block
    assert "the offline sentence" in concurrency_block


def test_the_concurrency_value_is_still_one_in_the_sample(sample):
    assert re.search(r"^MODEL_MAX_CONCURRENCY=1$", sample, re.MULTILINE), "本单不许抬并发"


def test_both_samples_still_document_the_same_four_numbers_and_neither_moved():
    """This ticket may add prose, not values: the code default and both files still agree.

    ``tests/test_r30_config_defaults.py`` covers every budget variable; these four are the ones
    R255 was tempted to edit, so they are named here instead of relying on coverage.
    """
    expected = {
        "MODEL_CONTEXT_TOKENS": DEFAULT_CONTEXT_TOKENS,
        "MODEL_MIN_ANSWER_TOKENS": DEFAULT_MIN_ANSWER_TOKENS,
        "MODEL_MAX_CONCURRENCY": 1,
        "MODEL_REQUEST_TIMEOUT": 120,
    }
    for relative, path in ((".env.example", ENV_SAMPLE), ("deploy/.env.server.example", SERVER_SAMPLE)):
        written = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, _, value = stripped.partition("=")
            if name.strip() in expected:
                written[name.strip()] = value.strip()

        assert written == {name: str(value) for name, value in expected.items()}, relative
    assert min_answer_tokens() == DEFAULT_MIN_ANSWER_TOKENS
    assert tier_max_tokens(ModelTier.ANALYSIS) == 1536


def test_the_plan_invented_no_new_knob_and_left_one_documented_only_in_prose(sample):
    """One derivation site means no new variable, and this pins that it stayed that way.

    A MODEL_CONCURRENCY_WAIT_SECONDS entry in ``budget_env_defaults()`` would oblige the ticket
    to document the variable in ``deploy/.env.server.example`` too -- a file this ticket does
    not own -- so the honest delivery is: no new key, and the existing one named in prose where
    the arithmetic needs it. Its 60 s default is still a literal in
    ``LocalModelBudget._configured_wait``, which is exactly the gap 跟进单 R135 published as a
    caveat rather than copying; whoever names it should do it in both samples at once.
    """
    base = {
        "MODEL_MAX_CONCURRENCY",
        "MODEL_REQUEST_TIMEOUT",
        "MODEL_CONTEXT_TOKENS",
        "MODEL_PREFILL_TOKENS_PER_SECOND",
        "MODEL_DECODE_TOKENS_PER_SECOND",
        "MODEL_TIMEOUT_MARGIN",
        "MODEL_MIN_ANSWER_TOKENS",
        "MODEL_TIMEOUT_FLOOR_SECONDS",
        "MODEL_CONNECT_TIMEOUT_SECONDS",
    }
    defaults = budget_env_defaults()

    assert set(defaults) - base == {
        f"MODEL_TIER_{tier.value.upper()}_MAX_TOKENS" for tier in ModelTier
    }
    assert len(defaults) == len(base) + len(list(ModelTier)) == 16
    assert "MODEL_CONCURRENCY_WAIT_SECONDS" not in defaults
    assert "MODEL_CONCURRENCY_WAIT_SECONDS" in window_block_of(sample)
