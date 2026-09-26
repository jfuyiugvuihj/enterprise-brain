"""R272 judgement 1: two processes may race for one number, but not for one body.

The defect R263 named and left open: ``trace_events`` is keyed by ``{trace_id}:{sequence}``, and
the number in that key comes from ``MAX(sequence)``. Two processes that both hear the tables
answer can read the same floor, and the later one then writes at the address the earlier one
already holds. That is not a collision the unique key refuses -- the key matches *itself*, and
``ON CONFLICT (event_id) DO UPDATE`` answers it by replacing the row that got there first: one
body gone, both writers told "success", and a readout that reports a trace neither process
recorded. Same family as R263's bug, one leg over: that one was in the settlement sweep, this
one is in the live write.

What these pins ask for:

* the race, manufactured in the only window that matters -- after A reads the floor, before A
  inserts -- between two stores that share one database and one trace;
* the winner keeps its body and the loser keeps its event: two numbers, two rows, nothing in the
  fallback journal, and no writer lied to about which row is its own;
* the refusal comes from the key and not from a memo inside this process, so the statement
  pinned is ``ON CONFLICT (event_id) DO NOTHING`` on ``trace_events`` alone -- ``upsert`` is
  unchanged, and a run still advances by rewriting the rows it owns (judgement 2's constraint);
* a number that cannot be won within ``SEQUENCE_ATTEMPTS`` is neither spun on nor dropped: it is
  counted, it goes out of the number book the way R263 sends an unconfirmed number, the readout
  still says the window is degraded, and the settlement sweep gives it an address (judgement 3);
* the counter-evidence is a test rather than a comment. Put the unconditional write back and the
  same assertions bite, naming the replaced body as the fact.

Hermetic: this is a contract check against ``tests._r250_fake_postgres``, which enforces the
primary key and the two conflict clauses. The real-server leg of the same race belongs to the
connected acceptance run -- see the handback, and ``EB_PG_ACCEPTANCE_URL`` in
``tests/test_r250_pg_trace_source_of_truth.py``.
"""
from __future__ import annotations

import inspect
import json
import uuid

import pytest

from app.storage.persistence import PostgresPersistenceAdapter
from app.trace import durability
from app.trace.durability import LOCAL_FALLBACK_NAME, POSTGRES_SOURCE, REASON_WRITE_FAILED
from app.trace.projections import run_id_for
from app.trace.schema import declared_columns
from app.trace.store import (
    FALLBACK_LINE_MARKER,
    ID_TAKEN_DETAIL,
    ID_TAKEN_SEQUENCE_STATEMENT,
    SEQUENCE_ATTEMPTS,
    TraceStore,
)
from tests._r250_fake_postgres import FakePostgres
from tests._r250_run_fixture import emit_full_run


#: The body the rival writes into the window: B's event, at the number A has just read.
RIVAL = ("model.started", "running")

#: The body the losing process is trying to record when it finds its address occupied.
CONTESTED = ("tool_call.started", "running")

#: Where an event's own body sits in the parameters of a ``trace_events`` insert, taken from
#: the column contract rather than counted by hand.
_EVENT_TYPE = declared_columns("trace_events").index("event_type")

_patches: list[tuple[object, str, object]] = []


@pytest.fixture(autouse=True)
def clean_ledger():
    durability.reset_durability_ledger()
    yield
    durability.reset_durability_ledger()


@pytest.fixture(autouse=True)
def revert_patched_attributes():
    """Undo the fault injection these pins use; no checked-in file is touched."""
    yield
    while _patches:
        owner, name, previous = _patches.pop()
        setattr(owner, name, previous)


def _patch(owner, name, value):
    # ``getattr_static`` for the reason R263 writes out: a plain getattr unwraps a staticmethod
    # into a bare function, and putting that back reinstalls it with a different shape -- a
    # harness that mutates what it restores cannot be trusted to accuse anyone else.
    _patches.append((owner, name, inspect.getattr_static(owner, name)))
    setattr(owner, name, value)


def _store(tmp_path, engine, name):
    """One process's view of one host: its own journal, the same six tables."""
    return TraceStore(
        tmp_path / f"{name}.jsonl",
        persistence=PostgresPersistenceAdapter(engine.connection_factory),
    )


def _recorder(store, trace, owner):
    def record(event_type, status, **payload):
        return store.record_event(
            trace_id=trace, request_id=f"{trace}:req", task_id=f"{trace}:task",
            event_type=event_type, status=status, payload={"owner_id": owner, **payload},
        )

    return record


def _event_lines(store):
    if not store.path.exists():
        return []
    return [
        json.loads(line)
        for line in store.path.read_text(encoding="utf-8").splitlines()
        if line.strip() and "fallback_receipt" not in line
    ]


def _rows(engine, trace):
    """What ``trace_events`` says about one trace: number -> (event_id, body)."""
    return {
        int(row["sequence"]): (row["event_id"], (row["event_type"], row["status"]))
        for row in engine.rows("trace_events").values()
        if row.get("trace_id") == trace
    }


def _faults(engine, trace, recorded):
    """Every way the rows can be wrong about one trace, in words an operator can use.

    A body that is not there -- the accident this ticket is about -- a body that is there twice,
    and two rows of one trace carrying one number. The last is what the unique key forbids, so
    in practice a lost event reads as the first: the number is still there, and the body behind
    it belongs to somebody else.
    """
    held = [kind for _event_id, kind in _rows(engine, trace).values()]
    faults = []
    for body in recorded:
        times = held.count(body)
        if times != 1:
            faults.append(f"{body[0]}/{body[1]}: recorded once, tables hold it {times} times")
    numbers = list(_rows(engine, trace))
    if len(set(numbers)) != len(numbers):
        faults.append("two rows of one trace carry the same number")
    return faults


def _rival_row(trace, sequence, owner):
    """A row a concurrent process wrote: same shape, different body, different request."""
    return {
        "event_id": f"{trace}:{sequence}", "trace_id": trace, "request_id": "the-rival:req",
        "task_id": "the-rival:task", "sequence": sequence, "event_type": RIVAL[0],
        "status": RIVAL[1], "owner_id": owner,
        "payload": {"owner_id": owner, "record_id": f"{trace}:model:rival"},
        "created_at": "2026-09-26T10:00:00+00:00",
    }


def _race(tmp_path, *, guard_off=False):
    """A reads the floor, B writes at the number A read, A writes second. ``guard_off`` = 摘钉."""
    engine = FakePostgres()
    trace = "r272-race-" + uuid.uuid4().hex[:6]
    owner = "owner:" + trace
    store_a = _store(tmp_path, engine, "a")
    store_b = _store(tmp_path, engine, "b")
    record_a = _recorder(store_a, trace, owner)
    record_b = _recorder(store_b, trace, owner)

    assert record_a("request.started", "started")["sequence"] == 1, (
        "the premise: one event is in the tables, and both processes read the same floor of 1"
    )

    real_floor = TraceStore._postgres_sequence_floor
    wrote: dict[str, dict | None] = {"event": None}

    def floor_that_lets_the_rival_in(self, trace_id):
        answer = real_floor(self, trace_id)
        if self is store_a and wrote["event"] is None:
            # B reaches the number A has just read, one moment before A can write it.
            wrote["event"] = record_b(
                *RIVAL, record_id=f"{trace}:model:rival", worker="doc_agent",
                provider="ollama", model_name="qwen3:8b",
            )
        return answer

    _patch(TraceStore, "_postgres_sequence_floor", floor_that_lets_the_rival_in)
    if guard_off:
        # Put the write back the way it was: no insert-if-absent, the later body wins the
        # address and nobody is told. Every assertion below has to bite on this.
        _patch(TraceStore, "_apply_event_row", lambda self, projection: self._apply(projection))
    contested = record_a(*CONTESTED, record_id=f"{trace}:tool:a", tool_name="search_documents")

    return {
        "engine": engine, "trace": trace, "owner": owner, "a": store_a, "b": store_b,
        "rival": wrote["event"], "contested": contested,
    }


def _always_losing_rival(store, engine, trace, owner):
    """Patch one store so every number it is offered is already held when it offers it."""
    real_floor = TraceStore._postgres_sequence_floor
    offered = {"rows": 0, "on": True}

    def floor_that_always_loses(self, trace_id):
        floor, proven, note = real_floor(self, trace_id)
        if self is store and proven and offered["on"]:
            offered["rows"] += 1
            engine.rows("trace_events")[f"{trace_id}:{floor + 1}"] = _rival_row(
                trace_id, floor + 1, owner
            )
        return floor, proven, note

    _patch(TraceStore, "_postgres_sequence_floor", floor_that_always_loses)
    return {"counter": offered, "stop": lambda: offered.update({"on": False}),
            "restore": lambda: _patch(TraceStore, "_postgres_sequence_floor", real_floor)}


def _insert_shapes(engine):
    """Which conflict clause each table was actually written with, in first-seen order."""
    shapes: dict[str, list[str]] = {}
    for statement, _params in engine.statements:
        if not statement.startswith("INSERT INTO "):
            continue
        table = statement.split(" ", 3)[2]
        clause = "DO NOTHING" if statement.endswith(" DO NOTHING") else (
            "DO UPDATE" if " DO UPDATE SET " in statement else "other"
        )
        seen = shapes.setdefault(table, [])
        if clause not in seen:
            seen.append(clause)
    return shapes


def _event_offers(engine, trace, body):
    """Every address one body was offered at, in order -- the writer's number book."""
    return [
        params[0]
        for statement, params in engine.statements
        if statement.startswith("INSERT INTO trace_events")
        and statement.endswith("ON CONFLICT (event_id) DO NOTHING")
        and params[_EVENT_TYPE] == body[0]
    ]


def test_the_race_leaves_two_bodies_and_two_numbers(tmp_path):
    """The judgement: a number is not an entitlement, and a collision costs nobody a body."""
    race = _race(tmp_path)
    rows = _rows(race["engine"], race["trace"])

    assert race["contested"]["sequence"] == 3, (
        "the loser gave up the number it was refused and took another one"
    )
    assert rows[2] == (f"{race['trace']}:2", RIVAL), "the row that got there first keeps its body"
    assert rows[3] == (f"{race['trace']}:3", CONTESTED), "the loser keeps its own event, one up"
    assert _faults(race["engine"], race["trace"], [RIVAL, CONTESTED]) == []


def test_the_race_costs_a_retry_and_nothing_else(tmp_path):
    """The cost of the fix, on the page: one more number, one more read, no window."""
    race = _race(tmp_path)
    ledger = durability.durability_status()

    assert ledger["sequence_retries"] == 1
    assert ledger["sequence_collision_events"] == 0
    assert ledger["fallback_events"] == 0
    assert ledger["unproven_sequence_events"] == 0
    assert ledger["degraded"] is False and ledger["durable"] is True
    assert not race["a"].path.exists(), "nothing was refused, so the journal was never opened"
    assert not race["b"].path.exists()
    readout = race["a"].read_run(run_id_for(race["trace"]))
    assert readout["source"] == POSTGRES_SOURCE
    assert "local_only" not in readout, "the tables answer for every event of this run"
    assert LOCAL_FALLBACK_NAME not in json.dumps(readout, default=str)


def test_the_refusal_comes_from_the_key_and_not_from_a_read(tmp_path):
    """Judgement 2: one offer, refused by the primary key, then one offer at another number."""
    race = _race(tmp_path)

    assert _event_offers(race["engine"], race["trace"], RIVAL) == [f"{race['trace']}:2"], (
        "the rival wrote its own address once and was never told anything about a collision"
    )
    assert _event_offers(race["engine"], race["trace"], CONTESTED) == [
        f"{race['trace']}:2",
        f"{race['trace']}:3",
    ], (
        "the loser asked the key at the number it read, was refused, and asked again one number "
        "higher -- not a pre-read that could be raced, and not a third spin"
    )


def test_only_the_event_row_is_written_insert_if_absent(tmp_path):
    """The hard constraint: ``trace_events`` is guarded, every other table still updates."""
    race = _race(tmp_path)
    shapes = _insert_shapes(race["engine"])

    assert shapes["trace_events"] == ["DO NOTHING"]
    for table in ("agent_runs", "model_calls", "tool_calls"):
        assert shapes[table] == ["DO UPDATE"], f"{table} must still be rewritten in place"


def test_a_run_still_advances_by_rewriting_the_rows_it_owns(tmp_path):
    """A whole production-shaped run through the guarded store: nothing about it may freeze."""
    engine = FakePostgres()
    trace = "r272-full-" + uuid.uuid4().hex[:6]
    store = _store(tmp_path, engine, "full")

    written = emit_full_run(store, trace=trace, owner="owner:" + trace)

    readout = store.read_run(written["run_id"])
    assert readout["source"] == POSTGRES_SOURCE
    assert readout["run"]["status"] == "completed", (
        "the terminal stamp is a legitimate rewrite of a row that already exists"
    )
    assert {row["status"] for row in engine.rows("agent_steps").values()} == {"completed"}, (
        "``agent_steps`` advances started -> finished on one row"
    )
    assert readout["counts"] == dict(written["counts"], agent_runs=1)
    assert _faults(engine, trace, [("request.started", "started")]) == []
    shapes = _insert_shapes(engine)
    assert shapes["trace_events"] == ["DO NOTHING"]
    for table in ("agent_runs", "agent_steps", "tool_calls", "model_calls", "retrieval_traces"):
        assert shapes[table] == ["DO UPDATE"]
    assert durability.durability_status()["sequence_retries"] == 0, (
        "one writer, one number line: the guard is silent when nobody races it"
    )


def test_the_primitive_refuses_the_key_and_still_raises_the_other_key(tmp_path):
    """``insert_if_absent``: the target key answers quietly, the other unique key still bites."""
    engine = FakePostgres()
    adapter = PostgresPersistenceAdapter(engine.connection_factory)
    trace = "r272-primitive-" + uuid.uuid4().hex[:6]

    def row(sequence, event_type, status, request_id):
        return {
            "trace_id": trace, "request_id": request_id, "task_id": f"{trace}:task",
            "sequence": sequence, "event_type": event_type, "status": status,
            "owner_id": "owner:" + trace, "payload": {"owner_id": "owner:" + trace},
            "created_at": "2026-09-26T10:00:00+00:00",
        }

    first = row(1, "request.started", "started", f"{trace}:req")
    assert adapter.insert_if_absent("trace_events", f"{trace}:1", first) is True
    assert adapter.insert_if_absent(
        "trace_events", f"{trace}:1", row(1, "tool_call.started", "running", "another:req")
    ) is False
    assert engine.rows("trace_events")[f"{trace}:1"]["event_type"] == "request.started", (
        "a refused offer leaves the body that was already there"
    )
    # A *different* address claiming the same (trace_id, sequence) is the other unique key, and
    # it is not this statement's conflict target: it has to raise, exactly as R263 depends on.
    with pytest.raises(Exception, match="trace_events_trace_id_sequence_key"):
        adapter.insert_if_absent(
            "trace_events", f"{trace}:token", row(1, "model.started", "running", "x")
        )
    with pytest.raises(Exception, match="owner_id is required"):
        adapter.insert_if_absent(
            "trace_events", f"{trace}:2", {**row(2, "a", "b", "c"), "owner_id": ""}
        )



def test_the_guard_removed_replaces_a_body_and_lies_to_both_writers(tmp_path):
    """摘钉: take the mechanism away and the same assertions bite on the replaced body."""
    race = _race(tmp_path, guard_off=True)
    engine, trace = race["engine"], race["trace"]
    rows = _rows(engine, trace)
    held = [kind for _event_id, kind in rows.values()]

    assert race["contested"]["sequence"] == 2
    assert rows[2] == (f"{trace}:2", CONTESTED)
    assert RIVAL not in held, (
        "the fixture is only evidence if the rival's body is really gone: B wrote first, A "
        "wrote the same address second, and the row now carries A's event"
    )
    assert _faults(engine, trace, [RIVAL, CONTESTED]) == [
        "model.started/running: recorded once, tables hold it 0 times"
    ]
    assert race["rival"]["sequence"] == race["contested"]["sequence"], (
        "both processes were told they own number 2 -- that is what the overwrite sounds like"
    )
    assert durability.durability_status()["sequence_retries"] == 0, (
        "the old write never learns it collided, which is the defect and not the fix"
    )


def test_a_number_that_cannot_be_won_goes_to_the_journal_not_into_the_air(tmp_path):
    """Judgement 3: bounded, counted, and still honest on the readout -- never silent."""

    engine = FakePostgres()
    trace = "r272-stuck-" + uuid.uuid4().hex[:6]
    owner = "owner:" + trace
    store = _store(tmp_path, engine, "stuck")
    record = _recorder(store, trace, owner)
    assert record("request.started", "started")["sequence"] == 1
    rival = _always_losing_rival(store, engine, trace, owner)

    event = record(*CONTESTED, record_id=f"{trace}:tool:never", tool_name="search_documents")

    ledger = durability.durability_status()
    lines = _event_lines(store)
    marker = lines[0][FALLBACK_LINE_MARKER]
    assert len(lines) == 1, "the event is in the journal, which is where a refusal belongs"
    assert event["sequence"] == SEQUENCE_ATTEMPTS + 1
    assert rival["counter"]["rows"] == SEQUENCE_ATTEMPTS, (
        "the bound is the number of numbers tried, and the loop stops there"
    )
    assert ledger["sequence_retries"] == SEQUENCE_ATTEMPTS - 1
    assert ledger["sequence_collision_events"] == 1
    assert ledger["fallback_events"] == 1
    assert ledger["unproven_sequence_events"] == 0, (
        "the tables did answer this event; they answered about somebody else"
    )
    assert ledger["degraded"] is True and ledger["fallback_by_reason"][REASON_WRITE_FAILED] == 1
    assert ID_TAKEN_DETAIL in ledger["last_error"], (
        "the ledger names the refusal the way the tables gave it, not as a generic write error"
    )
    assert marker["reason"] == REASON_WRITE_FAILED
    assert marker["sequence_proven"] is False
    assert marker["sequence_note"] == ID_TAKEN_SEQUENCE_STATEMENT
    assert marker["provisional_id"], "the line is addressed by a token, not by the number it lost"
    assert _faults(engine, trace, [("request.started", "started"), CONTESTED]) == [
        f"{CONTESTED[0]}/{CONTESTED[1]}: recorded once, tables hold it 0 times"
    ], "the refused event is not in the tables, and the file says so"
    for sequence, (event_id, kind) in _rows(engine, trace).items():
        assert kind == (RIVAL if sequence > 1 else ("request.started", "started"))
        assert event_id == f"{trace}:{sequence}", (
            "every address this process was refused is still held by the rival that won it"
        )

    readout = store.read_run(run_id_for(trace))
    gap = readout["local_only"]
    assert gap["name"] == LOCAL_FALLBACK_NAME and gap["events"] == 1
    assert gap["will_reach_tables"] == 1 and gap["will_not_reach_tables"] == 0, (
        "a window the sweep can still close is reported as a window, not as a loss"
    )


def test_the_line_that_lost_its_number_is_given_one_by_the_sweep(tmp_path):
    """The retry has an exit, and so has the journal line: R263's machinery, reused."""
    engine = FakePostgres()
    trace = "r272-settle-" + uuid.uuid4().hex[:6]
    owner = "owner:" + trace
    store = _store(tmp_path, engine, "settle")
    record = _recorder(store, trace, owner)
    record("request.started", "started")
    rival = _always_losing_rival(store, engine, trace, owner)

    refused = record(
        *CONTESTED, record_id=f"{trace}:tool:never", tool_name="search_documents"
    )
    rival["stop"]()
    rival["restore"]()
    report = store.backfill_fallback_journal()

    token = _event_lines(store)[0][FALLBACK_LINE_MARKER]["provisional_id"]
    rows = _rows(engine, trace)
    assert report["settled_events"] == 1 and report["unproven_lines"] == 1
    assert report["renumbered_lines"] == 1
    assert refused["sequence"] == SEQUENCE_ATTEMPTS + 1
    assert rows[refused["sequence"] + 1] == (f"{trace}:u{token}", CONTESTED), (
        "the sweep gives the line a number of its own, beside the rivals rather than on them"
    )
    assert _faults(engine, trace, [("request.started", "started"), CONTESTED]) == []
    assert durability.durability_status()["sequence_renumbered_events"] == 1
    assert "local_only" not in store.read_run(run_id_for(trace)), (
        "the window is closed, and the readout stops saying it is open"
    )


def test_the_sweep_does_not_borrow_the_number_it_was_refused_live(tmp_path):
    """The settled row is addressed by its token: the numbers it lost stay the rivals'."""
    engine = FakePostgres()
    trace = "r272-token-" + uuid.uuid4().hex[:6]
    owner = "owner:" + trace
    store = _store(tmp_path, engine, "token")
    record = _recorder(store, trace, owner)
    record("request.started", "started")
    rival = _always_losing_rival(store, engine, trace, owner)
    record(*CONTESTED, record_id=f"{trace}:tool:never", tool_name="search_documents")
    rival["stop"]()
    rival["restore"]()
    store.backfill_fallback_journal()

    token = _event_lines(store)[0][FALLBACK_LINE_MARKER]["provisional_id"]
    offered = _event_offers(engine, trace, CONTESTED)

    assert offered == [f"{trace}:{n}" for n in range(2, SEQUENCE_ATTEMPTS + 2)] + [
        f"{trace}:u{token}"
    ], "the live path offered only numbers, and the sweep offered only the token it owns"
    assert f"{trace}:1" in _event_offers(engine, trace, ("request.started", "started"))
