"""R263 judgement 2: one unanswered sequence read must not hand one id to two events.

The defect: ``app/trace/store.py`` took the next event number from
``max(postgres_floor, journal_floor) + 1``, and ``postgres_floor`` answered ``0`` whenever
PostgreSQL could not answer ``MAX(sequence)`` -- including the window in which PostgreSQL was
the thing that was broken. So a trace that degraded *midway* put a number on a fallback line
that the tables had already given to a different event, and since ``trace_events`` is written
``ON CONFLICT (event_id) DO UPDATE``, replaying that line did not fail: it replaced the row
that was already there, while the journal and the readout reported a recovery. R257 stopped a
sweep from replacing the row in front of it, at the cost of stranding those events in the
file forever; the numbers still collided.

What these pins ask for:

* two processes, one database, one journal each -- the topology a private host runs, where a
  process that degrades takes the numbers the other one already holds in the tables. Every
  event either recorded has to be in those tables afterwards, once, with its own body;
* a line admitted as unproven is never offered to the tables at the number printed on it, not
  even when that number happens to be vacant; it is given one from the tables at settlement;
* the page, the ledger, the replay and the readout all say which of those states a line is in,
  and a window that cannot be settled yet is reported as waiting rather than as recovered;
* the ordering this fix charges is pinned too: settled lines land below the event that
  followed them, never above it;
* the counter-evidence is a test and not a comment. Put the old floor reading back, or throw
  the address book away, and these same assertions have to bite.
"""
from __future__ import annotations

import inspect
import json
import uuid
from collections import Counter

import pytest

from app.storage.persistence import JsonPersistenceAdapter, PostgresPersistenceAdapter
from app.trace import durability
from app.trace.durability import (
    LOCAL_FALLBACK_NAME,
    POSTGRES_SOURCE,
    REASON_BACKEND_NOT_POSTGRES,
    REASON_OWNER_MISSING,
    REASON_WRITE_FAILED,
)
from app.trace.projections import run_id_for
from app.trace.store import BACKFILL_RECEIPT_MARKER, FALLBACK_LINE_MARKER, TraceStore
from tests._r250_fake_postgres import FakePostgres


#: The four events one trace of ``_degraded_pair`` records: two by a process the tables
#: answered, two by a process they did not.
RECORDED = [
    ("request.started", "started"),
    ("model.started", "running"),
    ("tool_call.started", "running"),
    ("tool_call.finished", "completed"),
]

_patches: list[tuple[object, str, object]] = []


@pytest.fixture(autouse=True)
def clean_ledger():
    durability.reset_durability_ledger()
    yield
    durability.reset_durability_ledger()


@pytest.fixture(autouse=True)
def revert_patched_attributes():
    """Undo the runtime breaks the counter-evidence nails make; no tracked file is touched."""
    yield
    while _patches:
        owner, name, previous = _patches.pop()
        setattr(owner, name, previous)


def _patch(owner, name, value):
    # ``inspect.getattr_static`` rather than ``getattr``: a plain getattr unwraps a
    # staticmethod into its bare function, and putting *that* back reinstalls it as an
    # instance method. A harness that changes the shape of what it restores has no business
    # accusing anyone else of a defect -- every failure it reports would be its own.
    _patches.append((owner, name, inspect.getattr_static(owner, name)))
    setattr(owner, name, value)


def _store(tmp_path, engine, name):
    """One process's view of the host: its own journal, the same six tables."""
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
        if line.strip() and BACKFILL_RECEIPT_MARKER not in line
    ]


def _held(engine, trace):
    """What ``trace_events`` says about one trace: address -> (number, kind, verdict)."""
    return {
        row["event_id"]: (int(row["sequence"]), row["event_type"], row["status"])
        for row in engine.rows("trace_events").values()
        if row.get("trace_id") == trace
    }


def _faults(engine, trace, recorded=None):
    """The two ways the tables can be wrong about one trace, in words an operator can use.

    An event recorded and not held (refused, or replaced by another one), a body held twice,
    and -- the accident this ticket is about -- one ``(trace_id, sequence)`` pair carrying two
    different events. The unique key makes the third unrepresentable in the rows, which is
    exactly why the first is what an overwrite looks like from the outside.
    """
    recorded = list(recorded if recorded is not None else RECORDED)
    rows = list(_held(engine, trace).values())
    kinds = [(row[1], row[2]) for row in rows]
    numbers = [row[0] for row in rows]
    faults = []
    for body in sorted(set(recorded) | set(kinds)):
        wanted, present = recorded.count(body), kinds.count(body)
        if present != wanted:
            faults.append(f"{body[0]}/{body[1]}: recorded {wanted}, tables hold {present}")
    if len(set(numbers)) != len(numbers):
        faults.append("two rows of one trace carry the same sequence")
    return faults


def _degraded_pair(tmp_path, *, old_floor_reading=False, printed_number_book=False):
    """A answers, B degrades, and the numbers B takes are the ones A's rows already carry.

    ``old_floor_reading`` puts back the reading this ticket is about: an unanswered
    ``MAX(sequence)`` answered as a *confirmed* floor of 0. ``printed_number_book`` keeps the
    admission and throws the address book away, so a recovered line is replayed at the number
    printed on it -- and blinds the sweep's lookup, because with one number book there is
    nothing left to ask with. Both are here to be caught.
    """
    engine = FakePostgres()
    trace = "r263-pair-" + uuid.uuid4().hex[:6]
    store_a = _store(tmp_path, engine, "a")
    store_b = _store(tmp_path, engine, "b")
    a = _recorder(store_a, trace, "owner:" + trace)
    b = _recorder(store_b, trace, "owner:" + trace)

    if old_floor_reading:
        probe = engine

        def _postgres_sequence_floor(self, trace_id):  # noqa: ANN001 - the pre-R263 reading
            if self.database is None or probe.unavailable:
                return 0, True, ""
            return self.database.max_sequence(trace_id), True, ""

        _patch(TraceStore, "_postgres_sequence_floor", _postgres_sequence_floor)
    if printed_number_book:
        _patch(
            TraceStore,
            "_event_identity",
            staticmethod(
                lambda event, marker: f"{event.get('trace_id')}:{event.get('sequence')}"
            ),
        )
        _patch(TraceStore, "_durable_row_by_id", lambda self, event_id: None)

    # A reaches the tables, which now hold (trace, 1) and (trace, 2).
    a("request.started", "started", session_id=f"{trace}:session")
    a("model.started", "running", record_id=f"{trace}:model:rewrite", worker="doc",
      provider="ollama", model_name="qwen3:8b")

    # B is the process that loses PostgreSQL. Its floor is its own file, which has never seen
    # A's events, so the numbers it takes are the ones A's rows carry.
    engine.set_unavailable(True)
    b("tool_call.started", "running", record_id=f"{trace}:tool:search", tool_name="search")
    b("tool_call.finished", "completed", record_id=f"{trace}:tool:search", tool_name="search")
    engine.set_unavailable(False)

    assert [line["sequence"] for line in _event_lines(store_b)] == [1, 2], (
        "the premise of this ticket: B numbered its lines from its own file, and the tables "
        "had already given those numbers to A's events"
    )
    return engine, trace, store_a, store_b


def test_borrowed_numbers_settle_beside_the_rows_they_borrowed_from(tmp_path):
    """The nail: after B recovers, A's events are still there and B's have arrived too."""
    engine, trace, _store_a, store_b = _degraded_pair(tmp_path)
    before = dict(_held(engine, trace))

    report = store_b.backfill_fallback_journal()

    assert report["settled_events"] == 2
    assert report["unproven_lines"] == 2
    assert report["renumbered_lines"] == 2
    assert report["refused"] == {}, "nothing here is a collision any more"
    assert report["still_local_lines"] == 0
    assert _faults(engine, trace) == []
    after = _held(engine, trace)
    assert set(before) <= set(after), "a recovered line replaced a row that was not its own"
    assert sorted(number for number, _kind, _status in after.values()) == [1, 2, 3, 4]
    assert "local_only" not in store_b.read_run(run_id_for(trace))
    assert durability.durability_status()["sequence_renumbered_events"] == 2


@pytest.mark.parametrize(
    ("old_floor_reading", "printed_number_book"),
    [(True, False), (False, True)],
    ids=["unanswered-floor-reads-0", "replay-at-the-printed-number"],
)
def test_the_guard_removed_makes_the_same_assertions_bite(
    tmp_path, old_floor_reading, printed_number_book
):
    """Counter-evidence as a test: without the guard, four events do not make four rows."""
    engine, trace, _store_a, store_b = _degraded_pair(
        tmp_path, old_floor_reading=old_floor_reading, printed_number_book=printed_number_book
    )

    report = store_b.backfill_fallback_journal()

    faults = _faults(engine, trace)
    assert faults, (
        "the break was not caught: the tables are right without the guard, so the guard "
        "was never what this ticket changed"
    )
    assert report["settled_events"] != 2 or faults, "a sweep may not call this settled"
    assert len(_held(engine, trace)) < 4, str(faults)


def test_an_unproven_line_is_not_offered_at_its_number_even_when_that_number_is_free(tmp_path):
    """The difference between refusing a collision and not inventing one.

    One degraded event over an empty table: its ordinal is vacant, and writing it there is
    still wrong, because what makes a number an address is PostgreSQL having said so -- not
    the absence of a rival at the moment this file happens to be looking.
    """
    engine = FakePostgres()
    trace = "r263-free-" + uuid.uuid4().hex[:6]
    store = _store(tmp_path, engine, "solo")
    engine.set_unavailable(True)
    _recorder(store, trace, "owner:" + trace)("request.started", "started")
    engine.set_unavailable(False)

    report = store.backfill_fallback_journal()

    assert report["settled_events"] == 1
    assert report["renumbered_lines"] == 1
    held = _held(engine, trace)
    assert len(held) == 1
    address = next(iter(held))
    token = _event_lines(store)[0][FALLBACK_LINE_MARKER]["provisional_id"]
    assert address == f"{trace}:u{token}", (
        "the row is addressed by the line that carried it, not by a number this file chose "
        "while nobody was answering"
    )
    assert held[address] == (1, "request.started", "started")
    assert _faults(engine, trace, [("request.started", "started")]) == []


def test_the_journal_says_its_number_is_not_the_tables(tmp_path):
    """The face on the page: admitted in the line, with the address it will be stored at."""
    engine, trace, _store_a, store_b = _degraded_pair(tmp_path)

    lines = _event_lines(store_b)

    assert len(lines) == 2
    for line in lines:
        assert set(line) == {
            "trace_id", "request_id", "task_id", "sequence", "timestamp", "event_type",
            "status", "payload", FALLBACK_LINE_MARKER,
        }, "the event keeps its eight keys; the admission rides beside them"
        marker = line[FALLBACK_LINE_MARKER]
        assert marker["is_fallback"] is True
        assert marker["sequence_proven"] is False
        assert marker["provisional_id"]
        assert "local ordinal only" in marker["sequence_note"]
        assert trace not in json.dumps(marker, ensure_ascii=False), (
            "an admission that echoed ids would make a count of this file double them"
        )
    ledger = durability.durability_status()
    assert ledger["unproven_sequence_events"] == 2
    assert ledger["fallback_by_reason"][REASON_WRITE_FAILED] == 2
    during = store_b.read_run(run_id_for(trace))
    assert during["source"] == POSTGRES_SOURCE, "A's rows are there, and they are short"
    assert during["local_only"]["events"] == 2
    assert during["local_only"]["will_reach_tables"] == 2
    assert during["local_only"]["will_not_reach_tables"] == 0


def test_a_window_still_degraded_defers_its_numbers_rather_than_guessing(tmp_path):
    """Recovery has to be able to say "not yet" without reporting it as lost."""
    engine, trace, _store_a, store_b = _degraded_pair(tmp_path)
    engine.set_unavailable(True)

    report = store_b.backfill_fallback_journal()

    assert report["unproven_deferred"] == 2
    assert report["settled_events"] == 0
    assert report["renumbered_lines"] == 0
    assert report["still_local_lines"] == 2
    assert report["receipt"] is False, "a sweep that settled nothing must not write a receipt"
    assert len(_event_lines(store_b)) == 2
    during = store_b.read_run(run_id_for(trace))
    # The tables are not answering for this read either, so the document comes from the file
    # and says so on its face. It is not *also* told a gap: the journal is the answer here,
    # and counting its lines back at the caller as missing rows would report them twice.
    assert during["source"] == LOCAL_FALLBACK_NAME
    assert during["fallback"] is True
    assert "local_only" not in during
    assert during["counts"]["trace_events"] == 2
    assert len(_held(engine, trace)) == 2, "the tables were not asked, so nothing moved"

    engine.set_unavailable(False)
    settled = store_b.backfill_fallback_journal()
    assert settled["settled_events"] == 2
    assert settled["renumbered_lines"] == 2
    assert len(_held(engine, trace)) == 4
    assert _faults(engine, trace) == []


def test_the_replay_shows_the_window_and_the_rows_that_hold_its_numbers(tmp_path):
    """A degraded stretch belongs to the trace even while it borrows a number.

    Keying both ledgers by the printed number is what made this read answer two events where
    the trace had four: B's lines hid behind A's rows, and the window looked like it had never
    happened. After settlement the same read still answers four, not eight -- a line that
    became a row is one event, not two.
    """
    engine, trace, _store_a, store_b = _degraded_pair(tmp_path)

    during = store_b.replay(trace)

    assert sorted((event["event_type"], event["status"]) for event in during) == sorted(RECORDED)
    assert len({event["payload"]["owner_id"] for event in during}) == 1

    store_b.backfill_fallback_journal()

    after = store_b.replay(trace)
    assert sorted((event["event_type"], event["status"]) for event in after) == sorted(RECORDED), (
        [event["event_type"] for event in after]
    )
    assert _faults(engine, trace) == []


def test_the_next_event_waits_for_the_window_it_follows(tmp_path):
    """Ordering is what this fix charges, so it is pinned rather than assumed.

    A line that could not be numbered gets its number when the tables can be asked, which is
    *after* the event that followed the window unless the sweep runs first. Numbering first
    would hand ``request.completed`` the low number and then ask ``agent_runs`` to walk a
    finished run back to ``started`` -- which the status guard rightly refuses and counts.
    """
    engine = FakePostgres()
    trace = "r263-order-" + uuid.uuid4().hex[:6]
    store = _store(tmp_path, engine, "order")
    record = _recorder(store, trace, "owner:" + trace)
    engine.set_unavailable(True)
    record("request.started", "started", session_id=f"{trace}:session")
    record("step.started", "running", step_id=f"{trace}:worker:doc", worker="doc", sequence=1)
    engine.set_unavailable(False)
    record("request.completed", "completed", worker_count=1, has_final_answer=True)

    assert sorted(
        (number, kind) for number, kind, _status in _held(engine, trace).values()
    ) == [
        (1, "request.started"), (2, "step.started"), (3, "request.completed"),
    ]
    assert [event["event_type"] for event in store.replay(trace)] == [
        "request.started", "step.started", "request.completed",
    ]
    assert durability.durability_status()["illegal_status_transitions"] == 0
    readout = store.read_run(run_id_for(trace))
    assert readout["run"]["status"] == "completed"
    assert readout["counts"]["trace_events"] == 3
    assert "local_only" not in readout


def test_the_line_that_could_never_be_owned_is_still_named_as_one(tmp_path):
    """R263 does not relabel somebody else's problem as a numbering one."""
    engine = FakePostgres()
    trace = "r263-noowner-" + uuid.uuid4().hex[:6]
    store = _store(tmp_path, engine, "noowner")
    engine.set_unavailable(True)
    store.record_event(
        trace_id=trace, request_id=f"{trace}:req", task_id=f"{trace}:task",
        event_type="step.started", status="running",
        payload={"step_id": f"{trace}:worker:doc", "worker": "doc", "sequence": 1},
    )
    engine.set_unavailable(False)

    line = _event_lines(store)[0]
    report = store.backfill_fallback_journal()

    assert line[FALLBACK_LINE_MARKER]["reason"] == REASON_OWNER_MISSING
    assert line[FALLBACK_LINE_MARKER]["sequence_proven"] is False
    assert report["never_in_tables"] == 1
    assert report["unproven_lines"] == 0, "a line that can never be a row is not a numbering gap"
    assert durability.durability_status()["fallback_by_reason"][REASON_OWNER_MISSING] == 1


def test_a_host_without_the_tables_still_numbers_from_its_journal(tmp_path):
    """The fix is about the tables, so a host that has none is not told it is unproven.

    ``PERSISTENCE_BACKEND=json`` has no ``trace_events`` to borrow an id from: the journal is
    the number line there, exactly as R250 left it, and an admission on every line of a
    notebook host would be a new wrong story about a backend that never lied.
    """
    store = TraceStore(
        tmp_path / "fallback.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / "records.json"),
    )

    events = [
        store.record_event(
            trace_id="r263-json", request_id="r", task_id="k",
            event_type="request.started" if index == 0 else "step.started", status="started",
            payload={"owner_id": "owner-1", "step_id": f"r263-json:worker:doc"},
        )
        for index in range(2)
    ]

    assert [event["sequence"] for event in events] == [1, 2]
    for line in _event_lines(store):
        assert "sequence_proven" not in line[FALLBACK_LINE_MARKER]
        assert line[FALLBACK_LINE_MARKER]["reason"] == REASON_BACKEND_NOT_POSTGRES
    assert durability.durability_status()["unproven_sequence_events"] == 0
    assert store.backfill_fallback_journal()["attempted"] is False


def test_a_proven_line_whose_id_a_foreign_row_holds_is_still_refused(tmp_path):
    """R257's guard, re-pinned where it still applies: a confirmed id can still be occupied.

    Confirming a number makes it an address; it does not make it vacant. A line written before
    this host's database was swapped, or one whose number a concurrent writer took between the
    question and the insert, is refused and stays visible rather than replacing a durable row.
    """
    engine = FakePostgres()
    trace = "r263-taken-" + uuid.uuid4().hex[:6]
    store = _store(tmp_path, engine, "taken")
    _recorder(store, trace, "owner:" + trace)("request.started", "started")
    engine.rows("trace_events")[f"{trace}:2"] = {
        "event_id": f"{trace}:2", "trace_id": trace, "request_id": "someone-else",
        "task_id": "", "sequence": 2, "event_type": "model.finished", "status": "completed",
        "owner_id": "owner:" + trace, "payload": {}, "created_at": "2026-09-26T10:00:00+00:00",
    }
    with store.path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "trace_id": trace, "request_id": f"{trace}:req", "task_id": f"{trace}:task",
            "sequence": 2, "timestamp": "2026-09-26T10:00:00+00:00",
            "event_type": "request.completed", "status": "completed",
            "payload": {"owner_id": "owner:" + trace, "worker_count": 1, "has_final_answer": True},
        }, ensure_ascii=False) + "\n")

    report = store.backfill_fallback_journal()

    assert report["settled_events"] == 0
    assert report["refused"] == {REASON_WRITE_FAILED: 1}
    assert engine.rows("trace_events")[f"{trace}:2"]["event_type"] == "model.finished", (
        "a sweep must not overwrite a durable row in order to settle a refused line"
    )
    gap = store.read_run(run_id_for(trace))["local_only"]
    assert gap["events"] == 1
    assert gap["will_reach_tables"] == 0 and gap["will_not_reach_tables"] == 1
    assert gap["name"] == LOCAL_FALLBACK_NAME

def test_a_number_taken_during_the_sweep_costs_a_sweep_and_not_a_body(tmp_path):
    """The race the sweep's own comment names, pinned rather than argued (judgement 1).

    An unproven line takes its number when it settles, so a concurrent writer can occupy that
    number between the reading and the insert. That is the one window where the guard cannot be
    this file's question -- it has to be the table's. So a rival row is planted in exactly that
    gap, and what is asserted is that ``UNIQUE (trace_id, sequence)`` refuses the insert, the
    rival keeps its body, the line stays in the journal, and the next sweep arrives one number
    higher with the same event on it. Nothing in this store addresses a line by an unconfirmed
    number, which is why a refusal is all that happens; the alternative is the overwrite.
    """
    engine = FakePostgres()
    trace = "r263-race-" + uuid.uuid4().hex[:6]
    store = _store(tmp_path, engine, "race")
    record = _recorder(store, trace, "owner:" + trace)

    engine.set_unavailable(True)
    record("request.started", "started", session_id=f"{trace}:session")
    engine.set_unavailable(False)

    persist = TraceStore._persist

    def persist_with_a_rival(self, event, owner_id, *, event_id=None):  # noqa: ANN001
        # A concurrent writer takes number 1 just after this sweep read the floor as 0.
        engine.rows("trace_events")[f"{trace}:1"] = {
            "event_id": f"{trace}:1", "trace_id": trace, "request_id": "someone-else",
            "task_id": "", "sequence": 1, "event_type": "model.finished",
            "status": "completed", "owner_id": "owner:" + trace, "payload": {},
            "created_at": "2026-09-26T10:00:00+00:00",
        }
        return persist(self, event, owner_id, event_id=event_id)

    _patch(TraceStore, "_persist", persist_with_a_rival)
    first = store.backfill_fallback_journal()

    assert first["settled_events"] == 0
    assert first["already_in_tables"] == 0
    assert first["refused"] == {REASON_WRITE_FAILED: 1}
    assert first["unproven_deferred"] == 0, "the tables answered: a refusal, not a wait"
    assert "trace_events_trace_id_sequence_key" in json.dumps(first["refused_detail"]), (
        "the unique key refused this insert, not a memo inside this process"
    )
    assert engine.rows("trace_events")[f"{trace}:1"]["event_type"] == "model.finished", (
        "the row that got there first keeps its body"
    )
    lines = _event_lines(store)
    assert [line["sequence"] for line in lines] == [1]
    assert lines[0][FALLBACK_LINE_MARKER]["sequence_proven"] is False

    _patch(TraceStore, "_persist", persist)
    second = store.backfill_fallback_journal()

    assert second["settled_events"] == 1
    assert second["renumbered_lines"] == 1
    held = _held(engine, trace)
    token = lines[0][FALLBACK_LINE_MARKER]["provisional_id"]
    assert held[f"{trace}:u{token}"] == (2, "request.started", "started"), (
        "the line arrives beside the rival, one number up, with its own body"
    )
    assert sorted(number for number, _kind, _verdict in held.values()) == [1, 2], (
        "two events, two numbers: a refused sweep cannot make one trace share a number"
    )
    assert "local_only" not in store.read_run(run_id_for(trace))
