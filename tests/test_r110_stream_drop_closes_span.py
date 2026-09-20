"""R110: a stream the consumer throws away still has to close its span.

``_ResilientModel.stream()`` opens one ``model.started`` event per call and closes it in
``span.finish(...)``. R102 made every exit hand the borrowed concurrency slot back, but the
consumer-stopped-reading exit arrives as ``GeneratorExit`` raised at a ``yield``, which is not
an ``Exception``, so it walked past every ``except`` here and reached the ``finally`` with the
span still open. Two things followed, not one: the trace kept a ``model.started`` that never
pairs, and ``_observe_stage`` -- called by ``finish()`` alone -- never fed the R51 stage
ledger, so the abandoned calls were missing from the duration statistics entirely. Those
abandoned calls are the slow tail (a user who stopped waiting), so the ledger was biased, not
merely short one row.

Closing the span is the easy half. ``finish()`` also reports the state to the execution
evidence bag, and ``evidence._terminal_status`` reads that bag: a word it has never met is
inert today only because none of its branches matches it, and the day one does, the stream a
caller chose to stop reading buys the customer a warning sentence or turns a ``success`` into
a ``partial``. That is why the close and the "do not re-judge this round" promise arrive
together: ``finish(..., record_evidence=False)`` is the switch, and the judgement-2 test
below is what pins it.

Everything here drives a real generator (``next`` / ``close``, the sync form of ``aclose``) and
reads back events, persisted rows, evidence bags and ledger samples. Nothing greps source text.
"""

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage

from app.agents import nodes
from app.agents.contracts import ModelTier, Principal
from app.common import model_budget
from app.common.model_budget import model_tier_budget
from app.common.stage_timing import default_stage_ledger, reset_stage_ledger

OWNER = "u-r110"
TRACE_ID = "trace-r110"
REQUEST_ID = "request-r110"
WORKER = "doc"

#: Three parts is the minimum that makes "stopped half way" a different shape from both
#: "never started" and "ran to the end".
ANSWER_PARTS = ["第一段答案", "第二段答案", "第三段答案"]
FULL_ANSWER = "".join(ANSWER_PARTS)
OFFLINE_PARTS = ["离线第一段", "离线第二段"]
GREETING = [HumanMessage(content="你好")]


@pytest.fixture(autouse=True)
def _one_slot_and_an_empty_ledger(monkeypatch):
    """One machine-wide slot and a ledger of this test's own, so both readings are exact.

    ``reset_default_budget`` is load-bearing the way it is in the R102 file: the pool is one
    cached process-wide object, and a slot this test strandeds would answer every later test
    with the offline template.
    """
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    monkeypatch.delenv("STAGE_TIMING_ENABLED", raising=False)
    reset_stage_ledger()
    model_budget.reset_default_budget()
    yield
    reset_stage_ledger()
    model_budget.reset_default_budget()


def _new_store(tmp_path, monkeypatch, name="r110"):
    """A trace volume under tmp_path: no test here may write into the tree."""
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace import spans
    from app.trace.store import TraceStore

    instance = TraceStore(
        tmp_path / f"{name}.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / f"{name}.json"),
    )
    monkeypatch.setattr(spans, "default_trace_store", lambda: instance)
    return instance


@pytest.fixture
def store(tmp_path, monkeypatch):
    return _new_store(tmp_path, monkeypatch)


def _config(bag=None):
    """A production-shaped config: an owner, a trace, and optionally an evidence bag."""
    from app.agents.evidence import BAG_KEY

    configurable = {
        "principal": Principal(user_id=OWNER, username="staff-r110", roles=["staff"]),
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
        "worker": WORKER,
        "step_id": f"{TRACE_ID}:worker:{WORKER}",
    }
    if bag is not None:
        configurable[BAG_KEY] = bag
    return {"configurable": configurable}


class _Provider:
    """Stand-in provider: opens no socket, and hands back one chunk at a time."""

    def __init__(self, *, parts=None, error=None):
        self.parts = parts if parts is not None else ANSWER_PARTS
        self.error = error
        self.stream_calls = 0

    def stream(self, *args, **kwargs):
        self.stream_calls += 1
        if self.error is not None:
            raise self.error
        for part in self.parts:
            yield AIMessageChunk(content=part)

    def bind_tools(self, tools):
        return self


class _OfflineReply:
    def __init__(self, parts=None):
        self.parts = parts if parts is not None else OFFLINE_PARTS

    def stream(self, *args, **kwargs):
        for part in self.parts:
            yield AIMessageChunk(content=part)

    def bind_tools(self, tools):
        return self


def _resilient(primary=None, offline=None):
    """A model built the way ``_make_model`` builds one, on the tier a streamed answer uses."""
    return nodes._ResilientModel(
        primary if primary is not None else _Provider(),
        offline if offline is not None else _OfflineReply(),
        provider="local-openai-compatible",
        model_name="test-model",
        capacity_wait_seconds=0,
        budget=model_tier_budget(ModelTier.CHAT),
    )


def _abandon_after_one_chunk(model, config):
    """Read a single chunk and walk away -- what a closed SSE connection leaves behind."""
    stream = model.stream(GREETING, config=config)
    delivered = [next(stream).content]
    stream.close()
    return delivered


def _span_events(store):
    return [
        event
        for event in store.replay(TRACE_ID)
        if event["event_type"] in {"model.started", "model.finished"}
    ]


def _finished(store):
    return [event for event in _span_events(store) if event["event_type"] == "model.finished"]


def _free_slots() -> int:
    """What a caller can still get right now: 1 balanced, 0 stranded, 2 a slot invented twice."""
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


# ==================== judgement 1 and 4: the drop closes that one span ====================


def test_abandoning_a_stream_after_one_chunk_closes_the_model_span(store):
    """The orphan this ticket is about: a ``model.started`` with no partner at all.

    Red before the fix, and red in the way that matters -- the pairing itself, not a wording
    choice: there is no second event to compare.
    """
    delivered = _abandon_after_one_chunk(_resilient(), _config())

    assert delivered == [ANSWER_PARTS[0]], "the consumer really did stop after one chunk"
    events = _span_events(store)
    assert [event["event_type"] for event in events] == ["model.started", "model.finished"]

    started, finished = events
    assert started["status"] == "running"
    assert finished["status"] == "cancelled"
    # Pairing is by record_id, not by adjacency: this is the same call, not a new one.
    assert finished["payload"]["record_id"] == started["payload"]["record_id"]
    assert finished["payload"]["completed_at"]
    assert finished["payload"]["first_token_at"], "the chunk it delivered is part of the record"
    assert finished["payload"]["duration_ms"] >= 0
    # "cancelled" is a new word and deliberately not an error code: an alarm the customer
    # never asked for is the other half of what judgement 1 refuses to invent.
    assert finished["payload"]["error_code"] is None


def test_the_abandoned_call_is_not_left_running_in_the_execution_table(store):
    """The same close, read where an operator reads it: the projected ``model_calls`` row."""
    _abandon_after_one_chunk(_resilient(), _config())

    rows = store.persistence.list("model_calls")
    assert len(rows) == 1
    assert rows[0]["status"] == "cancelled"
    assert rows[0]["completed_at"], "a row with no end is what made the pairing statistics lie"
    assert rows[0]["error_code"] in (None, "")


def test_a_stream_read_to_the_end_is_still_filed_completed(store):
    """The fix must not read every stream as cancelled: this is the exit that already closed."""
    chunks = [chunk.content for chunk in _resilient().stream(GREETING, config=_config())]

    assert chunks == ANSWER_PARTS
    events = _span_events(store)
    assert [event["event_type"] for event in events] == ["model.started", "model.finished"]
    assert events[1]["status"] == "completed"


def test_closing_a_stream_before_the_first_chunk_leaves_no_unpaired_event(store):
    """The degenerate pairing case: nothing started, so nothing has to close.

    Before the fix this was already green; it is here because "close the span in the finally"
    done carelessly is what would break it -- an exit that never opened a span must not
    invent one.
    """
    stream = _resilient().stream(GREETING, config=_config())
    stream.close()

    assert _span_events(store) == []
    assert store.persistence.list("model_calls") == []
    assert _free_slots() == 1


def test_the_cancelled_event_has_the_fields_a_completed_event_has(store, tmp_path, monkeypatch):
    """The close adds a status value, not a schema: the event bytes stay the contract.

    ``tests/test_model_call_spans.py`` and ``tests/test_r51_observation_is_passive.py`` pin
    what a model event looks like on the wire, so the new exit has to answer with exactly the
    same field set and the same labels, differing only in the values the clock chose.
    """
    config = _config()

    ran_store = _new_store(tmp_path, monkeypatch, "ran")
    list(_resilient().stream(GREETING, config=config))
    ran = _finished(ran_store)[0]["payload"]

    drop_store = _new_store(tmp_path, monkeypatch, "dropped")
    _abandon_after_one_chunk(_resilient(), config)
    dropped = _finished(drop_store)[0]["payload"]

    assert set(dropped) == set(ran), "a new exit may not add or drop a payload field"
    assert ran["status"] == "completed" and dropped["status"] == "cancelled"
    unchanged = {"record_kind", "provider", "model_name", "agent_run_id", "agent_step_id", "worker"}
    for key in unchanged & set(ran):
        assert dropped[key] == ran[key], key


# ==================== judgement 2: closing must not re-judge the round ====================


def _bag_with_one_document():
    from app.agents.evidence import new_evidence_bag, record_document_hits

    bag = new_evidence_bag()
    record_document_hits(
        bag,
        query="二季度营收",
        hits=[{"source": "财务手册.pdf", "content": "第二季度营收 1.2 亿元", "chunk_index": 3, "_score": 0.91}],
    )
    return bag


def test_dropping_the_stream_leaves_the_round_verdict_word_for_word_the_same(store):
    """One machine, two endings, one judgement: this is the assertion the ticket names.

    ``answer`` is the same text on both sides on purpose. The only variable is whether the
    consumer read the stream to the end or threw it away, and a verdict that moved would be
    the transport deciding what the evidence means.
    """
    from app.agents.evidence import _terminal_status

    def run(drop):
        bag = _bag_with_one_document()
        model = _resilient()
        if drop:
            _abandon_after_one_chunk(model, _config(bag))
        else:
            list(model.stream(GREETING, config=_config(bag)))
        return bag, _terminal_status(bag, FULL_ANSWER)

    ran_bag, ran = run(drop=False)
    dropped_bag, dropped = run(drop=True)

    assert ran == ("success", ""), "the control case must be a real success, not two equal blanks"
    assert dropped == ran
    # And the mechanism behind it: the close never reaches the bag, so no word the evidence
    # vocabulary does not own is sitting there waiting to be folded into a failure.
    assert dropped_bag["model_statuses"] == []
    assert ran_bag["model_statuses"] == []
    assert dropped_bag["tool_statuses"] == ran_bag["tool_statuses"] == []
    assert dropped_bag["documents"] == ran_bag["documents"]


def test_the_abandoned_round_answers_without_a_failure_warning(store):
    """The customer-visible form of judgement 2: no extra sentence, no invented error envelope.

    ``evidence.build_agent_result`` turns any error_code coming out of ``_terminal_status``
    into "执行边界报告了失败状态：{error_code}", which is the alarm the ticket warns about; a
    status that folds to nothing but drags the verdict to ``partial`` is the other half.
    """
    from app.agents.evidence import build_agent_result

    dropped_bag = _bag_with_one_document()
    _abandon_after_one_chunk(_resilient(), _config(dropped_bag))
    ran_bag = _bag_with_one_document()
    list(_resilient().stream(GREETING, config=_config(ran_bag)))

    dropped = build_agent_result(
        worker=WORKER, answer=FULL_ANSWER, bag=dropped_bag, request_id=REQUEST_ID, trace_id=TRACE_ID
    )
    ran = build_agent_result(
        worker=WORKER, answer=FULL_ANSWER, bag=ran_bag, request_id=REQUEST_ID, trace_id=TRACE_ID
    )

    assert (dropped.status, dropped.warnings, dropped.error) == (ran.status, ran.warnings, ran.error)
    assert dropped.status == "success"
    assert dropped.warnings == []
    assert dropped.error is None


# ==================== judgement 3: the ledger gets the slow tail back ====================


def test_an_abandoned_call_lands_in_the_stage_ledger_as_cancelled_not_completed(store):
    """The bias, measured: without the close the abandoned call is not in the ledger at all.

    ``_observe_stage`` runs from ``finish()`` and nowhere else, so the missing close was a
    missing sample -- and the calls a consumer abandons are the ones that had been running
    longest. The status word is what keeps the tail out of the ``completed`` bucket.
    """
    list(_resilient().stream(GREETING, config=_config()))
    ran = default_stage_ledger().samples()
    assert [sample.status for sample in ran] == ["completed"]
    assert ran[0].stage == "generate"

    reset_stage_ledger()
    _abandon_after_one_chunk(_resilient(), _config())
    dropped = default_stage_ledger().samples()

    assert [sample.status for sample in dropped] == ["cancelled"]
    assert [sample for sample in dropped if sample.status == "completed"] == []
    assert dropped[0].stage == "generate", "the same segment the completed call was charged to"
    assert dropped[0].source == "model_calls"
    assert dropped[0].duration_ms >= 0


def test_the_span_still_closes_with_the_stage_ledger_switched_off(store, monkeypatch):
    """Observation is a consumer of the close, never a condition for it.

    A kill switch on the readout side must not put the orphan trace row back: judgement 3 of
    R51 is that switching observation off changes nothing the business path does.
    """
    monkeypatch.setenv("STAGE_TIMING_ENABLED", "0")

    _abandon_after_one_chunk(_resilient(), _config())

    assert [event["status"] for event in _finished(store)] == ["cancelled"]
    assert default_stage_ledger().samples() == []
    assert store.persistence.list("model_calls")[0]["status"] == "cancelled"

# ==================== the exits the close does not own ====================


def test_a_provider_failure_answered_offline_keeps_its_two_verdicts_when_the_consumer_leaves(store):
    """The exit that was already closing spans: the new ``finally`` must not rewrite it.

    A provider blows up, the boundary answers offline, and the consumer leaves during the
    offline answer. Both spans close -- the first as the failure it saw, the second as the
    offline reply it is -- and the word ``cancelled`` appears nowhere, because
    ``finish()`` is idempotent and this finally is the last thing to run, not the first.
    """
    model = _resilient(_Provider(error=RuntimeError("connection reset by peer")))
    stream = model.stream(GREETING, config=_config())
    first = next(stream).content
    stream.close()

    assert first == OFFLINE_PARTS[0]
    events = _span_events(store)
    assert [event["event_type"] for event in events] == [
        "model.started",
        "model.finished",
        "model.started",
        "model.finished",
    ]
    assert [event["status"] for event in _finished(store)] == ["failed", "model_unavailable"]
    assert "cancelled" not in {event["status"] for event in events}
    assert {(row["provider"], row["status"]) for row in store.persistence.list("model_calls")} == {
        ("local-openai-compatible", "failed"),
        ("offline", "model_unavailable"),
    }


def test_a_prompt_refused_before_the_wire_still_leaves_by_its_failure_exit(store):
    """The oversized-prompt refusal closes as ``failed`` and is not relabelled either."""
    oversized = [HumanMessage(content="数" * 4400)]
    from app.common.model_budget import ModelContextLimitExceeded

    stream = _resilient().stream(oversized, config=_config())
    with pytest.raises(ModelContextLimitExceeded):
        next(stream)
    stream.close()

    assert [event["status"] for event in _finished(store)] == ["failed"]
    assert store.persistence.list("model_calls")[0]["error_code"] == "context_limit_exceeded"


def test_the_slot_still_comes_back_exactly_once_when_the_stream_is_dropped(store):
    """R102's invariant survives the new line: one close, one release, no invented slot."""
    _abandon_after_one_chunk(_resilient(), _config())

    assert _free_slots() == 1
    provider = _Provider()
    streamed = [chunk.content for chunk in _resilient(provider).stream(GREETING, config=_config())]
    assert streamed == ANSWER_PARTS
    assert provider.stream_calls == 1, "the next caller got the provider, not the offline template"


# ==================== the switch itself, at the span boundary ====================


def test_a_span_closed_without_evidence_writes_the_event_and_the_sample_but_not_the_bag(store):
    """What ``record_evidence=False`` is for, isolated from the generator around it."""
    from app.agents.evidence import new_evidence_bag
    from app.trace.spans import start_model_call

    bag = new_evidence_bag()
    span = start_model_call(_config(bag), provider="local", model_name="m", model_tier="chat")

    payload = span.finish("cancelled", record_evidence=False)

    assert payload["status"] == "cancelled"
    assert payload["record_id"] == span.record_id
    assert payload["summary"] == {}
    assert bag["model_statuses"] == [], "the round it belongs to is judged without this word"
    assert [event["status"] for event in _finished(store)] == ["cancelled"]
    assert [sample.status for sample in default_stage_ledger().samples()] == ["cancelled"]


def test_finish_still_reaches_the_evidence_bag_by_default(store):
    """The other direction: leaving the switch out must keep every old behaviour intact."""
    from app.agents.evidence import new_evidence_bag
    from app.trace.spans import start_model_call

    bag = new_evidence_bag()
    start_model_call(_config(bag), provider="local", model_name="m").finish(
        "failed", error_code="internal_error"
    )

    assert bag["model_statuses"] == [{"status": "failed", "error_code": "internal_error"}]
    assert [event["status"] for event in _finished(store)] == ["failed"]


def test_finishing_a_span_twice_answers_the_second_call_with_nothing(store):
    """The guard the new ``finally`` leans on instead of a status table of its own."""
    from app.agents.evidence import new_evidence_bag
    from app.trace.spans import start_model_call

    bag = new_evidence_bag()
    span = start_model_call(_config(bag), provider="local", model_name="m")

    assert span.finish("completed") != {}
    assert span.finish("cancelled", record_evidence=False) == {}
    assert span.finish("failed", error_code="internal_error") == {}
    assert [event["event_type"] for event in _span_events(store)] == [
        "model.started",
        "model.finished",
    ]
    assert _finished(store)[0]["status"] == "completed"
    assert bag["model_statuses"] == []
