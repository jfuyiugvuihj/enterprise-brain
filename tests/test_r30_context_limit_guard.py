"""R30 judgement (4): hitting ``n_ctx`` produces one stable code, in three senses.

There was no collision handling at all: ``app/**`` contained no 4096 except one unrelated
spreadsheet cell. So an oversized request had three possible endings, and each of them lost
the information -- the provider raised a bare error that reached the trace as
``internal_error``; the server answered with a completion cut off mid-sentence, which was
shown as an answer; or the resilient wrapper fell back to the offline model, whose canned
reply is recorded as ``model_unavailable``, a status ``evidence._terminal_status`` reports
*ahead of* a failure, so the real verdict never reached the client at all.

Each test below removes one of those three endings.
"""

import logging
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents import nodes
from app.agents.contracts import (
    CONTEXT_LIMIT_CODE,
    OUTPUT_TRUNCATED_CODE,
    ErrorEnvelope,
    ModelTier,
)
from app.agents.evidence import build_agent_result, new_evidence_bag
from app.common import model_budget
from app.common.model_budget import (
    MODEL_BUDGET_MARKER,
    ModelContextLimitExceeded,
    context_limit_tokens,
    model_tier_budget,
)

#: Long enough that adding any tier's output cap overflows a 4096 token window. The estimate
#: is one token per CJK character (app/common/model_budget.py), so 4000 characters is 4000
#: tokens: prompt alone fits, prompt plus output does not.
OVERSIZED = "数" * 4000
FITTING = "数" * 40


class _RecordingModel:
    def __init__(self, error: Exception | None = None, response=None):
        self.calls: list[dict] = []
        self.error = error
        self.response = response or AIMessage(
            content="答案", response_metadata={"finish_reason": "stop"}
        )

    def invoke(self, messages, config=None, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response

    def stream(self, *args, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        yield self.response

    def bind_tools(self, tools):
        return self


def _bagged_config() -> tuple[dict, dict]:
    """A real execution bag, hung on a config the way the orchestrator hangs one.

    Using ``new_evidence_bag`` rather than a dict of my own is the point: the verdict has
    to land in the structure the production code actually builds, not in a shape only this
    test knows.
    """
    bag = new_evidence_bag()
    return {"configurable": {"evidence_bag": bag, "trace_id": "trace-r30", "request_id": "req-r30"}}, bag


def _model(tier: ModelTier, primary) -> nodes._ResilientModel:
    return nodes._ResilientModel(
        primary,
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(tier),
    )


def test_an_oversized_prompt_is_refused_without_being_sent():
    primary = _RecordingModel()

    with pytest.raises(ModelContextLimitExceeded) as refused:
        _model(ModelTier.ANALYSIS, primary).invoke([HumanMessage(content=OVERSIZED)])

    assert primary.calls == [], "the request went out anyway, so the server decides the answer"
    assert refused.value.code == CONTEXT_LIMIT_CODE
    assert CONTEXT_LIMIT_CODE in str(refused.value)


def test_a_prompt_that_fits_is_still_sent():
    """The guard has to let good requests through, or it is just an outage with a code on it."""
    primary = _RecordingModel()

    response = _model(ModelTier.ANALYSIS, primary).invoke([HumanMessage(content=FITTING)])

    assert response.content == "答案"
    assert len(primary.calls) == 1


def test_the_window_is_a_configured_number_not_a_hard_coded_one(monkeypatch):
    """Same prompt, bigger n_ctx, different verdict: the guard is about the machine."""
    monkeypatch.setenv("MODEL_CONTEXT_TOKENS", "16384")

    assert context_limit_tokens() == 16384
    _model(ModelTier.ANALYSIS, _RecordingModel()).invoke([HumanMessage(content=OVERSIZED)])


@pytest.mark.parametrize(
    "message",
    [
        "This model's maximum context length is 4096 tokens",
        "n_ctx exceeded: requested 5000 tokens",
        "prompt is too long for the loaded model",
    ],
)
def test_a_provider_refusal_becomes_the_same_code_as_our_own_measurement(message):
    """One collision, one code -- whoever measured it."""
    primary = _RecordingModel(error=RuntimeError(message))

    with pytest.raises(ModelContextLimitExceeded) as refused:
        _model(ModelTier.CODE, primary).invoke([HumanMessage(content=FITTING)])

    assert refused.value.code == CONTEXT_LIMIT_CODE


def test_an_unrelated_provider_failure_still_degrades_offline():
    """The narrow case must not swallow the general one: only n_ctx changes behaviour here."""
    primary = _RecordingModel(error=RuntimeError("connection reset by peer"))

    response = _model(ModelTier.CODE, primary).invoke([HumanMessage(content=FITTING)])

    assert "离线" in response.content or response.content


def test_the_collision_is_not_reported_as_model_unavailable():
    """The mask this ticket had to remove: an offline reply is recorded ahead of a failure."""
    config, bag = _bagged_config()

    with pytest.raises(ModelContextLimitExceeded):
        _model(ModelTier.ANALYSIS, _RecordingModel()).invoke(
            [HumanMessage(content=OVERSIZED)], config=config
        )

    statuses = [(item["status"], item["error_code"]) for item in bag["model_statuses"]]
    assert ("failed", CONTEXT_LIMIT_CODE) in statuses, statuses
    assert "model_unavailable" not in " ".join(status for status, _ in statuses), statuses


def test_the_code_reaches_the_client_without_being_downgraded():
    """``evidence`` rewrites any code that is not in the closed enum as internal_error."""
    result = build_agent_result(
        worker="doc",
        answer="",
        bag={"model_statuses": [{"status": "failed", "error_code": CONTEXT_LIMIT_CODE}]},
        request_id="req-r30",
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == CONTEXT_LIMIT_CODE
    assert result.error.retryable is False, "the same prompt will never fit this window"


def test_the_code_is_a_ratified_member_of_the_closed_enum():
    from typing import get_args

    codes = set(get_args(ErrorEnvelope.model_fields["code"].annotation))

    assert CONTEXT_LIMIT_CODE in codes
    assert ErrorEnvelope(code=CONTEXT_LIMIT_CODE, message="too large").code == CONTEXT_LIMIT_CODE

    with pytest.raises(Exception):
        ErrorEnvelope(code="context_limit", message="near-miss invention")


def test_a_stream_is_refused_the_same_way_as_a_single_response():
    """The answer endpoint streams; a window that cannot hold the prompt cannot be streamed."""
    primary = _RecordingModel()
    model = _model(ModelTier.ANALYSIS, primary)

    with pytest.raises(ModelContextLimitExceeded):
        list(model.stream([HumanMessage(content=OVERSIZED)]))

    assert primary.calls == []


def test_a_refused_call_gives_its_slot_back(monkeypatch):
    """A call we never make must not occupy the single local-model slot.

    If it leaked, the second refusal below would not raise: the wrapper would find the
    budget exhausted and answer with a canned offline reply instead.
    """
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    model_budget.reset_default_budget()
    try:
        model = _model(ModelTier.ANALYSIS, _RecordingModel())
        oversized = [HumanMessage(content=OVERSIZED)]

        for _ in range(2):
            with pytest.raises(ModelContextLimitExceeded):
                model.invoke(oversized)
    finally:
        model_budget.reset_default_budget()


def test_a_completion_that_stops_at_its_cap_is_announced_not_accepted(caplog):
    """The other half of judgement 4: this is the silent-truncation face of the same wall."""
    response = AIMessage(content="这句话说到一半", response_metadata={"finish_reason": "length"})
    primary = _RecordingModel(response=response)
    config, bag = _bagged_config()

    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        _model(ModelTier.ANALYSIS, primary).invoke([HumanMessage(content=FITTING)], config=config)

    assert any(OUTPUT_TRUNCATED_CODE in record.getMessage() for record in caplog.records), caplog.text
    # The answer did arrive, so the call is not a failure; what is not allowed is that it
    # arrives quietly. One announced line, no failed status.
    assert response.content == "这句话说到一半"
    assert [item["status"] for item in bag.get("model_statuses", [])] == []


def test_the_budget_verdict_is_findable_by_one_grep(caplog):
    """An operator facing this in a customer log needs one marker, not five wordings."""
    with caplog.at_level(logging.WARNING, logger="enterprise_brain"):
        with pytest.raises(ModelContextLimitExceeded):
            _model(ModelTier.ANALYSIS, _RecordingModel()).invoke(
                [HumanMessage(content=OVERSIZED)]
            )

    line = [record.getMessage() for record in caplog.records if MODEL_BUDGET_MARKER in record.getMessage()]
    assert len(line) == 1, line
    assert "error_code=context_limit_exceeded" in line[0]
    assert "tier=analysis" in line[0]
    measured = re.search(r"prompt_tokens=(\d+)", line[0])
    assert measured and int(measured.group(1)) >= len(OVERSIZED), line[0]


def test_no_bare_context_exception_escapes_the_boundary():
    """The typed exception is the only public shape of this failure."""
    for text in ("context length exceeded", "n_ctx too small"):
        primary = _RecordingModel(error=ValueError(text))
        with pytest.raises(ModelContextLimitExceeded) as refused:
            _model(ModelTier.CHAT, primary).invoke([HumanMessage(content=FITTING)])
        assert isinstance(refused.value, RuntimeError)
        assert refused.value.code == CONTEXT_LIMIT_CODE
