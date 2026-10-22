"""R102: ``_ResilientModel.stream()`` may not keep the slot it borrowed.

The streaming boundary takes one slot from the machine-wide local-model budget exactly like
``invoke()`` does, and the shipped pool is one slot deep (``DEFAULT_MAX_CONCURRENCY = 1`` in
``app/common/model_budget.py``, with no override in ``deploy/.env.server``). Before this ticket
the slot came back on the two refusal paths only, so the first *successful* streamed answer kept
the only slot for the life of the process: every later model call, streamed or not, logged
``本地模型并发预算耗尽，使用离线回复`` and answered from the offline template, filed as
``rate_limited``. On site that reads like a broken model, not like a leak.

Three exits had to balance: the answer completed; the provider blew up and the boundary answered
offline; and the consumer threw the generator away half way through, which is not an exception
at all but ``GeneratorExit`` arriving at a ``yield``. And they had to balance exactly once: the
pool is a semaphore, so a slot released twice becomes a second concurrent request the one model
server cannot serve, which is a different outage wearing the same uniform.

Every test below is behavioural: a leaked slot is read back as the next call answering from the
offline template, and a double release as one slot too many to take. Nothing here greps source.
"""

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from app.agents import nodes
from app.agents.contracts import ModelTier
from app.common import model_budget
from app.common.model_budget import ModelContextLimitExceeded, model_tier_budget

#: The chitchat tier, because a streamed answer is what ``respond`` produces.
GREETING = [HumanMessage(content="你好")]

#: One CJK character estimates to one token, so this prompt cannot fit a 4096 window on any
#: tier: the boundary refuses it before the provider is asked for anything.
OVERSIZED = [HumanMessage(content="数" * 4400)]

#: What the offline template says, spelled out so a test fails on the answer itself.
OFFLINE_TEXT = "离线模式已启用，但我仍可以继续帮你梳理问题。"


@pytest.fixture(autouse=True)
def _one_slot(monkeypatch, tmp_path):
    """One slot for the whole machine, and nobody waits in line for it.

    A slot that is borrowed and never handed back is invisible in a deep pool and merely slows a
    caller that queues. With one slot and a zero queue, which is what ships, it turns the very
    next model call into an offline reply, and that is what these tests read.
    ``reset_default_budget`` is load-bearing: the pool is one cached process-wide object, and a
    slot leaked by one test would otherwise answer every test after it.

    The spans are parked under ``tmp_path``: reading an exit off its trace row is useful here,
    and it must not be written into the tree to find out.
    """
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace import spans
    from app.trace.store import TraceStore

    store = TraceStore(
        tmp_path / "spans.jsonl", persistence=JsonPersistenceAdapter(tmp_path / "spans.json")
    )
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    model_budget.reset_budget_events()
    model_budget.reset_default_budget()
    yield
    model_budget.reset_default_budget()
    model_budget.reset_budget_events()


class _Provider:
    """Stand-in provider: records every transport it was asked for, opens no socket."""

    def __init__(self, *, chunks=None, error=None):
        self.invoke_calls = 0
        self.stream_calls = 0
        self.chunks = chunks if chunks is not None else [AIMessageChunk(content="一段答案")]
        self.error = error

    def invoke(self, messages, config=None, **kwargs):
        self.invoke_calls += 1
        if self.error is not None:
            raise self.error
        return AIMessage(content="一段答案", response_metadata={"finish_reason": "stop"})

    def stream(self, *args, **kwargs):
        self.stream_calls += 1
        if self.error is not None:
            raise self.error
        yield from self.chunks

    def bind_tools(self, tools):
        return self


class _OfflineReply:
    """The canned sentence, counted so a provider answer and an offline answer differ."""

    def __init__(self):
        self.invoke_calls = 0
        self.stream_calls = 0

    def invoke(self, messages, config=None, **kwargs):
        self.invoke_calls += 1
        return AIMessage(content=OFFLINE_TEXT)

    def stream(self, *args, **kwargs):
        self.stream_calls += 1
        yield AIMessage(content=OFFLINE_TEXT)

    def bind_tools(self, tools):
        return self


def _resilient(primary, offline=None):
    """A model built the way ``_make_model`` builds one: tier budget, compat leg, no queueing."""
    return nodes._ResilientModel(
        primary,
        offline if offline is not None else _OfflineReply(),
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.CHAT),
    )


def _free_slots() -> int:
    """How many slots the machine has to offer right now, measured by taking them.

    Deliberately not a read of the semaphore's own counter: the invariant is about what a
    *caller* can get. One is balanced, zero is the leak this ticket fixes, two is a slot invented
    out of a double release.
    """
    budget = model_budget.default_model_budget()
    held = []
    try:
        while True:
            try:
                held.append(budget.acquire(wait_seconds=0))
            except model_budget.ModelBudgetExhausted:
                return len(held)
    finally:
        for slot in held:
            slot.release()


# ==================== the three exits of stream() ====================


def test_two_completed_streams_still_leave_a_slot_for_a_third():
    """Judgement 2: red before the fix, where the first completed stream keeps the only slot.

    Three streamed answers in a row, none refused and none abandoned. Only the second and third
    prove anything: they can come from the provider on one condition, which is that the answer
    before them handed its slot back.
    """
    provider = _Provider()
    offline = _OfflineReply()
    model = _resilient(provider, offline)

    for attempt in range(3):
        assert [chunk.content for chunk in model.stream(GREETING)] == ["一段答案"], attempt

    assert provider.stream_calls == 3
    assert offline.stream_calls == 0


def test_a_stream_abandoned_after_the_first_token_returns_the_slot():
    """Exit three: the consumer stops reading, so ``GeneratorExit`` arrives at the ``yield``.

    This one needs no failure at all. A caller that takes one token and walks away -- which is
    what a client that closes the SSE connection does -- was enough to strand the slot forever.
    """
    first = _resilient(_Provider(), _OfflineReply())
    stream = first.stream(GREETING)

    assert next(stream).content == "一段答案"
    stream.close()

    assert _free_slots() == 1
    again = _Provider()
    assert [chunk.content for chunk in _resilient(again).stream(GREETING)] == ["一段答案"]
    assert again.stream_calls == 1


def test_a_provider_failure_part_way_through_a_stream_returns_the_slot():
    """Exit two: the boundary answers offline, and an offline answer is not a reason to hold it.

    The timeout branch leaves through this same block, so the assertion is about the exit, not
    about which exception opened it.
    """
    offline = _OfflineReply()
    broken = _resilient(_Provider(error=RuntimeError("connection reset by peer")), offline)

    assert [chunk.content for chunk in broken.stream(GREETING)] == [OFFLINE_TEXT]
    assert offline.stream_calls == 1
    assert _free_slots() == 1

    healthy = _Provider()
    assert [chunk.content for chunk in _resilient(healthy).stream(GREETING)] == ["一段答案"]
    assert healthy.stream_calls == 1


def test_an_empty_streamed_answer_returns_the_slot_too():
    """The ``no_answer_produced`` verdict leaves the same body by its own ``return``."""
    provider = _Provider(chunks=[AIMessageChunk(content="")])
    offline = _OfflineReply()

    assert [chunk.content for chunk in _resilient(provider, offline).stream(GREETING)] == [""]
    assert provider.stream_calls == 1
    assert offline.stream_calls == 0
    assert _free_slots() == 1


# ==================== and not one slot more than once ====================


def test_a_refusal_before_the_wire_releases_exactly_once():
    """A prompt that cannot fit ``n_ctx`` is refused before the provider is asked for anything.

    This is one of the two paths that already released, so it is green on both sides of the fix.
    It is here for what the fix must not do: release a second time on the way out and mint a
    slot the machine never had.
    """
    provider = _Provider()
    model = _resilient(provider, _OfflineReply())

    with pytest.raises(ModelContextLimitExceeded):
        list(model.stream(OVERSIZED))

    assert provider.stream_calls == 0
    assert _free_slots() == 1


def test_a_context_error_from_the_provider_releases_exactly_once():
    """The other refusal: the server answers with a context error and the boundary re-raises."""
    provider = _Provider(error=ValueError("This model's maximum context length is 4096 tokens"))
    model = _resilient(provider, _OfflineReply())

    with pytest.raises(ModelContextLimitExceeded):
        list(model.stream(GREETING))

    assert provider.stream_calls == 1
    assert _free_slots() == 1


# ==================== judgement 3: invoke() was balanced, and must stay so ====================


def test_invoke_returns_the_slot_on_all_four_paths():
    """The non-streaming boundary already balanced; the streaming fix must not disturb it.

    Four paths, one call each, on the same single-slot machine: a completed answer, a prompt
    refused before the wire, a context error from the server, and an ordinary provider failure
    answered offline. The free-slot count after each one is the whole assertion.
    """
    offline = _OfflineReply()

    completed = _resilient(_Provider(), offline)
    assert completed.invoke(GREETING).content == "一段答案"
    assert _free_slots() == 1

    refused = _resilient(_Provider(), offline)
    with pytest.raises(ModelContextLimitExceeded):
        refused.invoke(OVERSIZED)
    assert _free_slots() == 1

    out_of_window = _resilient(
        _Provider(error=ValueError("This model's maximum context length is 4096 tokens")), offline
    )
    with pytest.raises(ModelContextLimitExceeded):
        out_of_window.invoke(GREETING)
    assert _free_slots() == 1

    failed = _resilient(_Provider(error=RuntimeError("connection reset by peer")), offline)
    assert failed.invoke(GREETING).content == OFFLINE_TEXT
    assert offline.invoke_calls == 1
    assert _free_slots() == 1
