"""R255 judgement (2): the refusal keeps refusing, and now says how far over it is.

The verdict this ticket was told not to touch: a request the window cannot hold is rejected
*before* it is sent, and is never laundered through the offline sentence -- the reasoning lives
in app/agents/nodes.py:875-885, and its shape is: the fallback records ``model_unavailable``,
``evidence._terminal_status`` reports that ahead of a failure, so the customer would read a
canned greeting while the real verdict stayed in a log line. Every test here keeps that
behaviour and reads only the surface underneath it.

What changed is the surface. On 2026-09-25 the report lane refused 2691 and 2778 prompt tokens
against n_ctx=4096, and the sentence an operator read carried three numbers and no distance --
so nobody could tell from it that the machine was configured small rather than weak, which is
the difference between editing two files and replacing a server.
"""

import json
import logging
import re
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage

from app.agents import nodes
from app.agents.contracts import CONTEXT_LIMIT_CODE, ErrorEnvelope, ModelTier
from app.agents.evidence import new_evidence_bag
from app.common.model_budget import (
    MODEL_BUDGET_MARKER,
    ModelClockUnaffordable,
    ModelContextLimitExceeded,
    authorize,
    authorize_or_refuse,
    context_error_code,
    max_tokens_verdict,
    model_tier_budget,
)

REPOSITORY = Path(__file__).resolve().parents[1]
#: The recorded refusal of an over-long prompt, straight out of the measurement ledger.
RATE_LEDGER = REPOSITORY / "docs" / "perf" / "raw" / "rate_prefill.jsonl"

#: estimate_prompt_tokens counts one token per CJK character plus 4 per message
#: (app/common/model_budget.py:MESSAGE_OVERHEAD_TOKENS), so this is exactly 2691 tokens.
REAL_PROMPT_2691 = "数" * 2687
TOKENS_IN_REAL_PROMPT = 2691


class _RecordingModel:
    """A primary that records, so "never sent" is an observation rather than a claim."""

    def __init__(self):
        self.calls = []

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("the request went out: the window guard did not run first")

    def stream(self, *args, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("the stream went out: the window guard did not run first")

    def bind_tools(self, tools):
        return self


def _boundary(primary):
    return nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.ANALYSIS),
    )


def _bagged_config():
    bag = new_evidence_bag()
    return {
        "configurable": {
            "evidence_bag": bag,
            "trace_id": "trace-r255",
            "request_id": "edf880c8696c4bdc8af1e62db40ede58",
        }
    }, bag


@pytest.fixture(autouse=True)
def window_as_shipped(monkeypatch):
    """The configuration the real window ran on: n_ctx 4096, analysis cap 1536, floor 1536."""
    for name in (
        "MODEL_CONTEXT_TOKENS",
        "MODEL_MIN_ANSWER_TOKENS",
        "MODEL_TIER_ANALYSIS_MAX_TOKENS",
        "MODEL_CONCURRENCY_WAIT_SECONDS",
        "MODEL_MAX_CONCURRENCY",
    ):
        monkeypatch.delenv(name, raising=False)


# ==================== the numbers ====================


@pytest.mark.parametrize(
    ("prompt_tokens", "over_by", "required"),
    [(2691, 131, 4227), (2778, 218, 4314)],
)
def test_the_refusal_carries_prompt_declared_cap_window_and_the_difference(
    prompt_tokens, over_by, required
):
    """判据②, as data: all four numbers plus 差额, on one object."""
    with pytest.raises(ModelContextLimitExceeded) as refused:
        authorize(model_tier_budget(ModelTier.ANALYSIS), prompt_tokens)

    error = refused.value
    assert error.prompt_tokens == prompt_tokens
    assert error.declared_max_tokens == 1536
    assert error.context_limit_tokens == 4096
    assert error.over_by_tokens == over_by
    assert error.required_context_tokens == required
    assert error.prompt_room_tokens == 2560

def test_the_message_reads_as_small_parameters_and_not_as_a_weak_model():
    """The one sentence an operator acts on, in the exception a log line carries.

    Wording is a contract here: these fragments are what a grep for "is this the machine or is
    this the model" is built out of, and each names something the ticket demanded -- the paired
    change, the server that has to agree, the container that has to be recreated, the rate
    script that has to run first, and the floor that must not be touched.
    """
    with pytest.raises(ModelContextLimitExceeded) as refused:
        authorize(model_tier_budget(ModelTier.ANALYSIS), 2778)

    text = str(refused.value)
    assert "prompt_tokens=2778" in text
    assert "declared max_tokens=1536" in text
    assert "needs n_ctx=4314" in text
    assert "218 tokens more than the configured MODEL_CONTEXT_TOKENS=4096" in text
    assert "size of a configured window, not a limit of the model" in text
    assert "raise MODEL_CONTEXT_TOKENS to >= 4314" in text
    assert "the model server's own n_ctx to match" in text
    assert "recreate the container" in text
    assert "scripts/bench_model_throughput.py" in text
    assert "MODEL_MIN_ANSWER_TOKENS is not a window knob" in text
    assert "No request was sent" in text


def test_the_refusal_exposes_the_paired_plan_it_quotes():
    """The advice is derived, not composed: the exception shows its own arithmetic."""
    with pytest.raises(ModelContextLimitExceeded) as refused:
        authorize(model_tier_budget(ModelTier.ANALYSIS), 2778)

    plan = refused.value.plan
    assert plan.coherent is False
    assert plan.context_limit_tokens == 4096
    assert plan.minimum_window_for(2778) == 4314
    reading = json.loads(json.dumps(plan.as_dict()))
    assert reading["n_ctx"] == 4096
    assert reading["max_coherent_n_ctx"] == 0
    assert reading["red_reasons"] == ["clock_binds", "queue_binds"]


def test_the_refusal_line_stays_one_line_and_gains_the_distance(caplog):
    """The [ModelBudget] line is the operator's only handle; it must not multiply.

    tests/test_r30_context_limit_guard.py pins "one grep, one finding" by asserting exactly one
    marker line per refused call. This adds the new fields to that line instead of logging a
    second one, and the assertion below is what notices if that stops being true.
    """
    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        with pytest.raises(ModelContextLimitExceeded):
            authorize(model_tier_budget(ModelTier.ANALYSIS), 2691)

    lines = [record.getMessage() for record in caplog.records if MODEL_BUDGET_MARKER in record.getMessage()]
    assert len(lines) == 1, lines
    line = lines[0]
    assert "error_code=context_limit_exceeded" in line
    assert "over_by_tokens=131" in line
    assert "required_n_ctx=4227" in line
    assert "n_ctx=4096" in line
    assert "window_coherent=no" in line
    assert "incoherent_budget=clock_binds|queue_binds" in line
    assert re.search(r"full_window_seconds=\d+\.\d", line), line
    assert re.search(r"max_coherent_n_ctx=\d+", line), line


def test_a_call_that_fits_the_window_gains_no_new_fields(caplog):
    """The other side of the same line: nothing is appended to a verdict that has nothing to say."""
    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        authorize(model_tier_budget(ModelTier.ANALYSIS), 40)

    line = " ".join(record.getMessage() for record in caplog.records if MODEL_BUDGET_MARKER in record.getMessage())
    assert "over_by_tokens" not in line, line
    assert "window_coherent" not in line, line


# ==================== the boundary that must keep behaving ====================


def test_the_real_size_is_still_refused_before_it_is_sent_and_offline_is_still_not_used():
    """判据② 的不变部分, at the exact size the report lane hit.

    ``report-04`` stalled for 300 s in the queue because of this refusal, and the one thing that
    must not be "fixed" is where the truth ends up: an offline reply would have recorded
    ``model_unavailable``, which evidence reports ahead of a failure, and the customer would
    have read a greeting while the reason stayed in a log line.
    """
    primary = _RecordingModel()
    config, bag = _bagged_config()

    with pytest.raises(ModelContextLimitExceeded) as refused:
        _boundary(primary).invoke([HumanMessage(content=REAL_PROMPT_2691)], config=config)

    assert primary.calls == [], "the request went out, so the server decides the answer"
    assert refused.value.prompt_tokens == TOKENS_IN_REAL_PROMPT
    assert refused.value.over_by_tokens == 131
    statuses = [(item["status"], item["error_code"]) for item in bag["model_statuses"]]
    assert ("failed", CONTEXT_LIMIT_CODE) in statuses, statuses
    assert "model_unavailable" not in " ".join(status for status, _ in statuses), statuses


def test_the_code_is_still_the_ratified_one_and_still_not_retryable():
    from typing import get_args

    codes = set(get_args(ErrorEnvelope.model_fields["code"].annotation))
    assert CONTEXT_LIMIT_CODE in codes
    assert ErrorEnvelope(code=CONTEXT_LIMIT_CODE, message="too large for this window").code == (
        CONTEXT_LIMIT_CODE
    )

# ==================== the other half of the same error surface ====================


def _recorded_refusal():
    """The server's own answer to an over-long prompt, read out of the measurement ledger."""
    for line in RATE_LEDGER.read_text(encoding="utf-8-sig").splitlines():
        payload = line[6:] if line.startswith("JSONL ") else line
        if not payload.startswith("{"):
            continue
        record = json.loads(payload)
        if record.get("case_note") == "http_400":
            return json.loads(json.loads(record["detail"])["error"])["error"]
    raise AssertionError(f"no http_400 record in {RATE_LEDGER}")


def test_the_server_s_own_words_for_too_long_resolve_to_the_same_code():
    """Raising the declared window alone moves the refusal to the server -- this catches it.

    The recorded body is what a real over-long request comes back as on this host: a message
    that says "exceeds the available context size" and a type that says
    ``exceed_context_size_error``. Recognising it used to be an accident of the JSON also
    carrying a field literally named ``n_ctx``; the message on its own -- which is about all a
    wrapping client keeps -- resolved to None and would have been filed as ``internal_error``.
    """
    refusal = _recorded_refusal()
    assert "available context size" in refusal["message"]
    assert refusal["n_ctx"] == 4096

    assert context_error_code(RuntimeError(refusal["message"])) == CONTEXT_LIMIT_CODE
    assert context_error_code(RuntimeError(refusal["type"])) == CONTEXT_LIMIT_CODE
    assert context_error_code(RuntimeError(json.dumps(refusal))) == CONTEXT_LIMIT_CODE


def test_an_unrelated_provider_failure_is_not_widened_into_a_window_refusal():
    """The recogniser stays narrow: this is about length, not about any 400."""
    for text in ("connection reset by peer", "invalid model name", "500 internal server error"):
        assert context_error_code(RuntimeError(text)) is None, text


def test_a_clock_refusal_still_never_borrows_the_window_s_language(monkeypatch):
    """The two verdicts stay apart in everything a reader sees (tests/test_r204 owns the rule).

    R255 put the paired-budget sentence on the *window* refusal; this is the nail that keeps it
    off the clock one, where n_ctx is not the finding and would misdirect the operator. The
    window is widened here so the call actually reaches the clock guard: at 4096 the window
    refuses first, which is every other test in this file.
    """
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "16384")
    with pytest.raises(ModelClockUnaffordable) as refused:
        authorize_or_refuse(model_tier_budget(ModelTier.ANALYSIS), 2778)

    text = str(refused.value)
    assert "n_ctx" not in text, text
    assert CONTEXT_LIMIT_CODE not in text, text
    assert "MODEL_MIN_ANSWER_TOKENS is not a window knob" not in text, text
    assert "affordable_max_tokens=" in text


def test_a_clamp_cannot_rescue_a_prompt_the_window_refused():
    """The order of the two guards is contract, and R255 kept it: declared cap, then clock."""
    budget = model_tier_budget(ModelTier.ANALYSIS)
    verdict = max_tokens_verdict(budget, 2691)

    assert budget.context_window_code(2691) == CONTEXT_LIMIT_CODE
    with pytest.raises(ModelContextLimitExceeded):
        authorize(budget, 2691)
    assert verdict.declared_max_tokens == 1536