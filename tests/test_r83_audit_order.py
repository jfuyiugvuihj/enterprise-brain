"""R83: the audit journal replays in the order its events were written.

Before this slice ``_hydrate_view_locked`` ordered the journal by ``(created_at, event_id)``
while ``created_at`` came from ``datetime.now(timezone.utc)``, a clock that on Windows only
moves in ~1 ms steps, and ``event_id`` is a ``uuid4``. Two events written inside one tick
therefore came back in an order decided by a random string: the controller's probe measured
300 back-to-back ``record_audit`` calls colliding in 12 pairs (4%) and replaying inverted 4
times (1.3%). The repair is a process-local allocator that hands out strictly increasing
timestamps, so the tie that made the coin flip cannot form while one process is writing.

Every case below pins a *written* order against a *replayed* order with the module clock
injected -- never with sleeps standing in for the collision, and never by patching the
identifier source. What no case here claims is cross-process ordering: worker processes share
no allocator, so a same-tick pair written by two processes is still ordered by ``event_id``.
``_allocate_timestamp_locked`` carries that limitation as written.
"""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import threading

import pytest

from app.common import audit
from app.common.audit import (
    AUDIT_COLLECTION,
    audit_storage_status,
    configure_audit_storage,
    get_audit_events,
    hydrate_audit_events,
    record_audit,
    reset_audit_storage,
)
from app.common.identity import Principal

MODULE = Path(audit.__file__).resolve()

#: Microsecond field zero on purpose: ``_iso`` drops the whole fraction at this instant, so
#: the first persisted string and its successors differ in length, which the ordering of a
#: string sort key now has to survive.
TICK = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
STEP = timedelta(microseconds=1)
BURST = 12


def make_principal(username: str = "alice", role: str = "staff") -> Principal:
    principal = Principal.from_user(
        {"id": 1, "username": username, "role": role, "department": "finance"}
    )
    principal.request_id = "req-r83"
    return principal


class _ClockMeta(type):
    """Let the shim answer ``isinstance(value, datetime)`` the way the real name does."""

    def __instancecheck__(cls, obj):
        return isinstance(obj, datetime)


class _InjectedClock(metaclass=_ClockMeta):
    """Stand-in for the name ``datetime`` inside :mod:`app.common.audit`.

    ``readings`` is what the journal gets to see; once it runs out the last value repeats,
    which is what a coarse clock looks like to a tight write loop. Every reading is recorded
    so a case can prove the collision it claims was real instead of left to luck.
    """

    _readings: list[datetime] = [TICK]
    _delay = 0.0
    _index = 0
    _seen: list[datetime] = []

    @classmethod
    def set(cls, readings, *, delay: float = 0.0) -> None:
        cls._readings = list(readings)
        cls._delay = delay
        cls._index = 0
        cls._seen = []

    @classmethod
    def now(cls, tz=None):
        if cls._delay:
            threading.Event().wait(cls._delay)
        index = min(cls._index, len(cls._readings) - 1)
        cls._index += 1
        value = cls._readings[index]
        cls._seen.append(value)
        return value if tz is None else value.astimezone(tz)

    @classmethod
    def fromisoformat(cls, text):
        return datetime.fromisoformat(text)

    @classmethod
    def seen(cls) -> list[datetime]:
        return list(cls._seen)


def write_events(count: int, prefix: str = "doc") -> list[dict]:
    return [
        record_audit(
            make_principal(),
            "resource:view",
            "allowed",
            f"{prefix}-{index}",
            f"reason_{index}",
        )
        for index in range(count)
    ]


def stamps(events) -> list[str]:
    return [str(event["created_at"]) for event in events]


def instants(events) -> list[datetime]:
    return [datetime.fromisoformat(value) for value in stamps(events)]


def assert_strictly_instant(events, *, clock_readings: int | None = None) -> list[datetime]:
    """Pin the premise (the clock did not move) and the promise (the order did)."""
    seen = _InjectedClock.seen()
    assert len(seen) >= (clock_readings or len(events)), seen
    readings = seen[: clock_readings or len(events)]
    assert len(set(readings)) == 1, f"the injected clock moved: {readings}"
    values = instants(events)
    assert len(set(stamps(events))) == len(events), stamps(events)
    for previous, current in zip(values, values[1:]):
        assert current > previous, (previous, current)
        assert current - previous <= STEP, (previous, current)
    return values



@pytest.fixture
def journal(tmp_path, monkeypatch):
    """A real JSON audit journal, a clock the case owns, and an empty allocator floor.

    ``_last_issued_at`` is cleared to ``None`` because that is what a fresh process looks
    like: no allocator history. The durable journal is left exactly as the previous process
    wrote it, so a case that depends on the seed cannot pass by inheriting a warm floor.
    """
    path = tmp_path / "persistence.json"
    monkeypatch.setenv("PERSISTENCE_BACKEND", "json")
    monkeypatch.setenv("PERSISTENCE_FALLBACK_PATH", str(path))
    monkeypatch.delenv("AUDIT_PERSISTENCE", raising=False)
    monkeypatch.delenv("AUDIT_RETENTION_DAYS", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _InjectedClock.set([TICK])
    monkeypatch.setattr(audit, "datetime", _InjectedClock, raising=False)
    configure_audit_storage(backend="json", fallback_path=path)
    monkeypatch.setattr(audit, "_last_issued_at", None, raising=False)
    yield path
    reset_audit_storage()


def stored_journal(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get(AUDIT_COLLECTION, {})


# ------------------------------------------------------------------ the symptom ① ③


def test_a_same_tick_burst_replays_in_the_order_it_was_written(journal):
    written = write_events(BURST)
    values = assert_strictly_instant(written, clock_readings=BURST)

    reset_audit_storage()
    replayed = get_audit_events()

    assert [event["event_id"] for event in replayed] == [event["event_id"] for event in written]
    assert instants(replayed) == values


def test_the_written_order_is_not_the_order_event_ids_would_have_given(journal):
    """The case bites: replay matches the writes because of the stamps, not the id tie-break.

    Twelve random ``uuid4`` ids come out in write order once in 12! attempts, so if this ever
    reads "equal" the allocator has silently gone back to leaning on ``event_id``.
    """
    written = [event["event_id"] for event in write_events(BURST)]

    assert sorted(written) != written, "the ids happened to sort into write order"

    reset_audit_storage()
    assert [event["event_id"] for event in get_audit_events()] == written


def test_a_coarse_clock_that_only_steps_by_a_millisecond_keeps_every_write(journal):
    """Windows granularity: three writes share one reading, and the ladder keeps them apart."""
    readings = [TICK + timedelta(milliseconds=index // 3) for index in range(BURST * 3)]
    _InjectedClock.set(readings)

    written = write_events(BURST * 2)
    values = instants(written)

    assert len(set(stamps(written))) == len(written), stamps(written)
    for previous, current in zip(values, values[1:]):
        assert current > previous, (previous, current)
    assert values[0] == TICK
    assert values[-1] <= readings[BURST * 2 - 1] + len(readings) * STEP, values[-1]


def test_a_clock_stepping_backwards_cannot_reorder_the_journal(journal):
    """NTP stepping the wall clock back is the second cause of an inverted replay."""
    _InjectedClock.set([TICK, TICK + timedelta(seconds=5), TICK + timedelta(seconds=3)])

    written = write_events(4)
    values = instants(written)

    assert values == [
        TICK,
        TICK + timedelta(seconds=5),
        TICK + timedelta(seconds=5) + STEP,
        TICK + timedelta(seconds=5) + 2 * STEP,
    ], values

    reset_audit_storage()
    assert [event["event_id"] for event in get_audit_events()] == [
        event["event_id"] for event in written
    ]



# ------------------------------------------------------------------ the seed ④


def new_process() -> None:
    """A restart: the durable journal survives, the in-process allocator floor does not.

    The floor goes first, because that is the order a real restart happens in: the new
    process has no allocator history at all, and the first thing it does with the journal is
    read what its predecessor left behind.
    """
    if hasattr(audit, "_last_issued_at"):
        audit._last_issued_at = None
    reset_audit_storage()


def test_a_restart_does_not_issue_timestamps_older_than_the_journal(journal):
    """The fresh process reads the same tick the previous one died on."""
    first_half = write_events(4)
    new_process()
    second_half = write_events(4)

    written = [*first_half, *second_half]
    assert len(set(stamps(written))) == len(written), stamps(written)

    new_process()
    replayed = get_audit_events()
    assert [event["event_id"] for event in replayed] == [event["event_id"] for event in written]
    assert instants(replayed) == instants(written)


def test_the_seed_comes_from_the_durable_journal_and_not_from_the_wall_clock(journal):
    """A box whose clock was corrected backwards must still write itself after its history."""
    _InjectedClock.set([TICK + timedelta(hours=1)])
    before = write_events(2)

    new_process()
    _InjectedClock.set([TICK])
    after = write_events(2)

    assert instants(after) == [
        TICK + timedelta(hours=1) + 2 * STEP,
        TICK + timedelta(hours=1) + 3 * STEP,
    ], instants(after)
    reset_audit_storage()
    assert [event["event_id"] for event in get_audit_events()] == [
        event["event_id"] for event in [*before, *after]
    ]


def test_a_forced_rehydrate_seeds_the_allocator_too(journal):
    write_events(4)
    new_process()
    assert hydrate_audit_events(force=True) == 4

    ninth = write_events(1)

    assert instants(ninth) == [TICK + 4 * STEP], instants(ninth)


# ------------------------------------------------------------------ precision ⑤


def test_the_microsecond_step_survives_the_persisted_round_trip(journal):
    """JSON keeps an ISO string and the migration column is microsecond TIMESTAMPTZ."""
    written = write_events(BURST)
    records = stored_journal(journal)

    assert len(records) == BURST
    on_disk = [str(records[event["event_id"]]["created_at"]) for event in written]
    assert len(set(on_disk)) == BURST, on_disk
    assert on_disk[0] == "2026-09-18T12:00:00+00:00", on_disk[0]
    assert on_disk[1].endswith(".000001+00:00"), on_disk[1]
    assert on_disk == sorted(on_disk), "a longer string sorted before a shorter instant"
    for event, value in zip(written, on_disk):
        assert str(records[event["event_id"]]["payload"]["created_at"]) == value

    # The bucket itself is written with sort_keys=True, so the file order is the random id
    # order -- which is precisely why a strictly increasing stamp is the only carrier left.
    assert list(records) != [event["event_id"] for event in written]



# ------------------------------------------------------------------ concurrency ⑥


def test_concurrent_writers_never_share_a_timestamp(journal):
    """Eight threads, one unmoving clock: every write still gets its own instant.

    The switch interval is squeezed so writers really do interleave inside ``record_audit``.
    That makes this case a net for an allocator that is not inside the journal lock -- a race
    is never a promise, so the deterministic pin for the placement is
    ``test_the_journal_reads_the_clock_only_inside_its_lock`` instead.
    """
    workers, per_worker = 8, 12
    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            jobs = [
                pool.submit(write_events, per_worker, f"w{worker}") for worker in range(workers)
            ]
            issued = [event for job in jobs for event in job.result()]
    finally:
        sys.setswitchinterval(previous_interval)

    assert len(issued) == workers * per_worker
    assert len(set(stamps(issued))) == len(issued), stamps(issued)

    view = get_audit_events()
    values = instants(view)
    assert values == sorted(values), "the process view is not ordered by its own stamps"
    for worker in range(workers):
        prefix = f"w{worker}-"
        written = [
            event["event_id"] for event in issued if str(event["resource"]).startswith(prefix)
        ]
        seen = [
            event["event_id"] for event in view if str(event["resource"]).startswith(prefix)
        ]
        assert seen == written, (prefix, seen, written)

    new_process()
    assert [event["event_id"] for event in get_audit_events()] == [
        event["event_id"] for event in view
    ]


def test_a_slow_clock_read_cannot_be_beat_to_the_append(journal):
    """Reading the clock while holding the lock serialises writers instead of tangling them."""
    _InjectedClock.set([TICK], delay=0.02)
    gate = threading.Barrier(2)

    def write(name: str) -> dict:
        gate.wait()
        return record_audit(make_principal(name), "resource:view", "allowed", name, "owner_match")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(write, "slow-a")
        second = pool.submit(write, "slow-b")
        events = [first.result(), second.result()]

    assert {event["created_at"] for event in events} == {
        TICK.isoformat(),
        (TICK + STEP).isoformat(),
    }, events
    assert instants(get_audit_events()) == sorted(instants(get_audit_events()))


# ------------------------------------------------------------------ the rest of the face


def test_a_memory_only_journal_orders_the_same_tick(journal, monkeypatch):
    """No durable backend means no seed, so the in-process ladder is all there is."""
    monkeypatch.setenv("AUDIT_PERSISTENCE", "disabled")
    configure_audit_storage(backend="json", fallback_path=journal)

    written = write_events(6)

    assert_strictly_instant(written, clock_readings=6)
    assert [event["persisted"] for event in written] == [False] * 6
    status = audit_storage_status()
    assert status["durable"] is False
    assert status["health"] == "backend_unavailable"


def test_the_ordered_writes_still_report_a_healthy_journal(journal):
    write_events(BURST)

    status = audit_storage_status()

    assert status["health"] == "ok", status
    assert status["durable"] is True
    assert status["write_failures"] == 0
    assert status["read_failures"] == 0
    assert status["persisted_events"] == BURST
    assert status["in_memory_events"] == BURST


def test_the_event_keeps_its_published_fields_in_their_published_order(journal):
    """The stamp is now assigned inside the lock; nothing else about the row moved."""
    event = record_audit(make_principal(), "resource:view", "allowed", "doc-1", "owner_match")

    assert list(event) == [
        "event_id",
        "timestamp",
        "created_at",
        "username",
        "role",
        "owner_id",
        "auth_source",
        "actor_clearance",
        "actor_departments",
        "action",
        "resource",
        "outcome",
        "reason",
        "request_id",
        "resource_scope",
        "resource_scope_source",
        "policy_version",
        "policy_version_source",
        "before_summary",
        "after_summary",
        "retention_days",
        "expires_at",
        "persisted",
        "storage_mode",
    ]
    assert event["timestamp"] == event["created_at"]
    window = datetime.fromisoformat(event["expires_at"]) - datetime.fromisoformat(
        event["created_at"]
    )
    assert window == timedelta(days=180)


# ------------------------------------------------------------------ source guards


def _function(name: str):
    for node in ast.walk(ast.parse(MODULE.read_text(encoding="utf-8-sig"))):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() is gone from app/common/audit.py")


def _calls_named(node, name: str):
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id == name
    ]


def _clock_reads(node):
    """Every ``datetime.now(...)`` call inside ``node``."""
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "now"
        and isinstance(child.func.value, ast.Name)
        and child.func.value.id == "datetime"
    ]


def _journal_lock_sections(node):
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.With)
        and any(
            isinstance(item.context_expr, ast.Name) and item.context_expr.id == "_lock"
            for item in child.items
        )
    ]


def test_the_journal_reads_the_clock_only_inside_its_lock():
    """Allocation and append must be one critical section, or a late write can look older.

    This is the mechanical half of the fix: the moment used to be taken before ``with
    _lock``, which is exactly where two writers could be handed the same instant, or an
    earlier instant appended after a later one.
    """
    writer = _function("record_audit")
    sections = _journal_lock_sections(writer)
    assert len(sections) == 1, sections
    section = sections[0]

    assert _clock_reads(writer) == [], "record_audit() reads the wall clock by itself again"
    allocated = _calls_named(section, "_allocate_timestamp_locked")
    assert len(allocated) == 1, "the stamp is not taken once inside the journal lock"
    appended = [
        child
        for child in ast.walk(section)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "append"
        and isinstance(child.func.value, ast.Name)
        and child.func.value.id == "_events"
    ]
    assert len(appended) == 1, appended
    assert section.lineno < allocated[0].lineno < appended[0].lineno, (
        section.lineno,
        allocated[0].lineno,
        appended[0].lineno,
    )


def test_the_allocator_is_one_locked_helper_and_nothing_else():
    """A second lock here would let the view and the stamps disagree again."""
    allocator = _function("_allocate_timestamp_locked")
    assert _journal_lock_sections(allocator) == [], "the allocator brought its own lock"
    assert len(_clock_reads(allocator)) == 1, _clock_reads(allocator)
    assert not _calls_named(allocator, "sleep"), "the allocator must not wait for a clock tick"
    docstring = ast.get_docstring(allocator) or ""
    assert "_lock" in docstring, "the locking contract is undocumented"
    assert "process" in docstring.lower(), "the single-process limit is undocumented"


def test_hydrating_the_view_seeds_the_allocator_from_what_is_already_written():
    hydrate = _function("_hydrate_view_locked")
    assert len(_calls_named(hydrate, "_seed_timestamp_floor_locked")) == 1, (
        "the replay seed is no longer part of hydrating the view"
    )
    seeder = _function("_seed_timestamp_floor_locked")
    assert len(_calls_named(seeder, "_parse_iso")) == 1, seeder
    assert "'created_at'" in ast.dump(seeder), "the seed stopped reading the durable stamps"
