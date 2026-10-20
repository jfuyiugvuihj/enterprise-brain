"""Durability ledger for the trace layer: where a run's trace actually ended up.

R250 made the six PostgreSQL execution tables (``agent_runs``, ``agent_steps``,
``tool_calls``, ``model_calls``, ``retrieval_traces``, ``trace_events``) the source of
truth for one trace. The append-only local journal that used to be the only store stays
behind as the fallback for the window in which PostgreSQL cannot take the write. A
fallback is not an error -- a notebook host runs with ``PERSISTENCE_BACKEND=json`` on
purpose -- but it is a *different durability*, so it has to be named rather than
swallowed: an operator reading ``/api/v1/runs/{run_id}`` or the log must be able to tell
"this run's trace is in PostgreSQL" apart from "this run's trace only exists in a file on
this machine".

The shape follows ``app/common/audit.py``, which already answers "can this journal be
trusted right now" with ``degraded`` / ``degraded_reason`` / ``health`` instead of a bare
boolean ``ok``: a journal nobody else can read is not healthy just because the write call
returned. The counters here are process-local; the authoritative numbers live in the
tables, this ledger only says whether they can be trusted right now.

R257 added the recovery half of that sentence, on the same page and with no new
vocabulary: ``fallback_events`` says how many events the tables refused, and
``backfilled_events`` / ``local_only_lines`` say how many of them the tables hold again
after a settlement sweep (``app.trace.store.TraceStore.backfill_fallback_journal``) and how
many the file still holds alone -- including ``never_in_tables``, the lines that can never
reach the tables because they carry no owner to attribute them to. A successful backfill
does not walk ``degraded`` back: the window happened, and an operator reading this ledger
should still be able to see that it did.

R263 adds the two counters of the numbering book. ``unproven_sequence_events`` says how many
events this process recorded with a number the tables never confirmed -- PostgreSQL would not
answer ``MAX(sequence)``, so the journal could state the order of those events but not where
they belong among the rows -- and ``sequence_renumbered_events`` says how many of them a
settlement sweep has since given a number of its own. Neither is a degradation of its own and
neither sets ``degraded``: the refused write is already named by ``fallback_events``, and
counting the same window twice is how an operator ends up reading two where there was one.

R272 adds the two counters of the race itself. ``sequence_retries`` says how many times a live
write gave up a number because the tables answered that the address made from it already holds
another event -- each of those is one more trip to ``MAX(sequence)``, and the event normally
lands on the tables one number later with nothing lost, so it is a cost and not a degradation.
``sequence_collision_events`` says how many events ran out of attempts (the bound lives in
``app.trace.store.SEQUENCE_ATTEMPTS``) and went to the journal still without an address, which
is the one number here that says "two processes on this host are racing for one trace's number
line and one of them is being pushed out of the tables". Such a line is *also* a
``fallback_events`` line -- it is in the file, and that is what ``degraded`` is for -- and it is
deliberately not also an ``unproven_sequence_events`` line: the tables did answer that event,
they simply answered about somebody else.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from app.common.logger import logger

#: The one name that says "this trace did not make it into PostgreSQL". It is repeated in
#: the log line and in the run readout, so a grep for it answers the question without
#: opening the database.
LOCAL_FALLBACK_NAME = "trace_local_fallback"

#: The name a readout carries when the answer did come out of the six tables.
POSTGRES_SOURCE = "postgres"

#: Why a write went to the fallback journal. Stable codes, so an operator can count them
#: instead of parsing sentences.
REASON_BACKEND_NOT_POSTGRES = "postgres_backend_not_configured"
REASON_WRITE_FAILED = "postgres_write_failed"
REASON_READ_FAILED = "postgres_read_failed"
REASON_OWNER_MISSING = "owner_identity_missing"
REASON_SCHEMA_MISMATCH = "trace_column_mismatch"
REASON_ILLEGAL_STATUS = "illegal_run_status_transition"

_FALLBACK_REASONS = (
    REASON_BACKEND_NOT_POSTGRES,
    REASON_WRITE_FAILED,
    REASON_READ_FAILED,
    REASON_OWNER_MISSING,
    REASON_SCHEMA_MISMATCH,
    REASON_ILLEGAL_STATUS,
)

#: Repeated failures must not flood the log: the first occurrence and every 50th after it
#: are written, the count in between stays in the ledger. Same throttle audit.py uses.
_RELOG_EVERY = 50

_lock = threading.Lock()


def _fresh_ledger() -> dict[str, Any]:
    return {
        "backend": "none",
        "source_of_truth": LOCAL_FALLBACK_NAME,
        "durable": False,
        "degraded": True,
        "degraded_reason": "",
        "fallback_events": 0,
        "fallback_reads": 0,
        "illegal_status_transitions": 0,
        "backfilled_events": 0,
        "unproven_sequence_events": 0,
        "sequence_renumbered_events": 0,
        "sequence_retries": 0,
        "sequence_collision_events": 0,

        "backfill_already_in_tables": 0,
        "backfill_errors": 0,
        "local_only_lines": 0,
        "never_in_tables": 0,
        "last_backfill_at": "",
        "fallback_by_reason": {reason: 0 for reason in _FALLBACK_REASONS},
        "last_error": "",
        "last_fallback_at": "",
        "health": "fallback_active",
    }


_ledger = _fresh_ledger()


def set_backend(*, backend: str, postgres: bool) -> None:
    """Say which backend this process writes through, so the ledger cannot drift from it."""
    with _lock:
        _ledger["backend"] = str(backend or "none")
        _ledger["durable"] = bool(postgres)
        _ledger["source_of_truth"] = POSTGRES_SOURCE if postgres else LOCAL_FALLBACK_NAME
        if postgres:
            _ledger["degraded"] = bool(_ledger["fallback_events"] or _ledger["fallback_reads"])
            _ledger["health"] = "fallback_active" if _ledger["degraded"] else "ok"
            if not _ledger["degraded"]:
                _ledger["degraded_reason"] = ""
        else:
            _ledger["degraded"] = True
            _ledger["degraded_reason"] = _ledger["degraded_reason"] or REASON_BACKEND_NOT_POSTGRES
            _ledger["health"] = "fallback_active"


def _note_reason(reason: str) -> None:
    _ledger["fallback_by_reason"][reason] = _ledger["fallback_by_reason"].get(reason, 0) + 1


def note_local_fallback(reason_code: str, detail: str) -> int:
    """Record that one trace event went to the local journal instead of PostgreSQL.

    Returns the running fallback count for this process. The name is always in the log
    line, because "the write call did not raise" is not the same claim as "the row is in
    the database".
    """
    reason = str(reason_code or REASON_WRITE_FAILED)
    message = str(detail or "")
    with _lock:
        _ledger["fallback_events"] += 1
        _note_reason(reason)
        _ledger["degraded"] = True
        _ledger["degraded_reason"] = reason
        _ledger["last_error"] = message[:500]
        _ledger["last_fallback_at"] = datetime.now(timezone.utc).isoformat()
        _ledger["health"] = "fallback_active"
        count = _ledger["fallback_events"]
    if count == 1 or count % _RELOG_EVERY == 0:
        logger.warning(
            "[Trace] %s: trace event was not stored in PostgreSQL (backend=%s); "
            "reason=%s occurrences=%d detail=%s",
            LOCAL_FALLBACK_NAME,
            _ledger["backend"],
            reason,
            count,
            message[:200] or "-",
        )
    return count


def note_unproven_sequence() -> int:
    """Count one event recorded with a number the tables have not confirmed (R263).

    The event is not lost and is not counted as a second fallback -- the write that went to
    the journal already said that. What this says is narrower and was never on the page: the
    number on that line is an ordinal of the file, and until the tables answer for it the
    trace has events whose place among the rows is undecided.
    """
    with _lock:
        _ledger["unproven_sequence_events"] += 1
        return _ledger["unproven_sequence_events"]


def note_sequence_renumbered() -> int:
    """Count one line the tables have now given a number of its own."""
    with _lock:
        _ledger["sequence_renumbered_events"] += 1
        return _ledger["sequence_renumbered_events"]


def note_sequence_retry() -> int:
    """Count one number a live write gave up because the tables said it was another event's.

    R272. The counter answers a question no other cell on this page answers: how often the
    processes on this host race for one trace's number line, and how much of that race costs a
    second trip to ``MAX(sequence)``. It is not a degradation -- the event that gave a number up
    is normally written one number later on the very next attempt, with nothing lost and no
    window opened -- and it is deliberately not folded into ``fallback_events``, because an
    operator comparing the two numbers wants to know how many *events* the file holds, not how
    many numbers this process refused.
    """
    with _lock:
        _ledger["sequence_retries"] += 1
        return _ledger["sequence_retries"]


def note_sequence_collision() -> int:
    """Count one event that ended in the journal with no number the tables would let it use.

    The bound in ``app.trace.store.SEQUENCE_ATTEMPTS`` ran out: every address this process was
    offered is already held by a different event, so the line went out of the number book the
    way R263 sends an unconfirmed number, and the settlement sweep is what gives it an address.
    This is the expensive half of the race and it is the reason the retry is bounded: it always
    coincides with one ``fallback_events`` line (the same event, named once for being in the
    file), and never with ``unproven_sequence_events`` -- the tables did answer this event, they
    answered about somebody else.
    """
    with _lock:
        _ledger["sequence_collision_events"] += 1
        return _ledger["sequence_collision_events"]



def note_local_read_fallback(reason_code: str, detail: str) -> int:
    """Record that one trace read had to come from the local journal."""
    reason = str(reason_code or REASON_READ_FAILED)
    message = str(detail or "")
    with _lock:
        _ledger["fallback_reads"] += 1
        _note_reason(reason)
        _ledger["degraded"] = True
        _ledger["degraded_reason"] = reason
        _ledger["last_error"] = message[:500]
        count = _ledger["fallback_reads"]
    if count == 1 or count % _RELOG_EVERY == 0:
        logger.warning(
            "[Trace] %s: trace was read from the local journal, not from PostgreSQL; "
            "reason=%s occurrences=%d detail=%s",
            LOCAL_FALLBACK_NAME,
            reason,
            count,
            message[:200] or "-",
        )
    return count


def note_backfill_error(detail: str) -> int:
    """Count a settlement sweep that did not finish, in the ledger it was reporting to.

    A failed backfill is not a request failure: the events stay where they are, in the
    journal, and the next sweep offers them again. But "we will get to it" is only honest
    while somebody can see that we have not.
    """
    with _lock:
        _ledger["backfill_errors"] += 1
        _ledger["last_error"] = str(detail or "")[:500]
        count = _ledger["backfill_errors"]
    logger.warning(
        "[Trace] %s backfill sweep did not finish (occurrences=%d): %s",
        LOCAL_FALLBACK_NAME,
        count,
        str(detail or "")[:200] or "-",
    )
    return count


def note_backfill(
    *,
    settled_events: int,
    already_in_tables: int,
    local_only_lines: int,
    never_in_tables: int = 0,
) -> dict[str, Any]:
    """Record what one settlement sweep moved from the journal into the six tables.

    Same ledger, same reason codes, new numbers -- not a second book: ``settled_events``
    reached the tables for the first time here, ``already_in_tables`` were answered for by
    an earlier sweep or an earlier writer (which is what makes a repeat sweep cheap instead
    of double-counting), and ``local_only_lines`` is what this file still holds alone.
    """
    with _lock:
        _ledger["backfilled_events"] += int(settled_events or 0)
        _ledger["backfill_already_in_tables"] += int(already_in_tables or 0)
        _ledger["local_only_lines"] = max(0, int(local_only_lines or 0))
        _ledger["never_in_tables"] = max(0, int(never_in_tables or 0))
        _ledger["last_backfill_at"] = datetime.now(timezone.utc).isoformat()
        return dict(_ledger)


def note_illegal_status_transition(run_id: str, current: str, requested: str) -> int:
    """Count a write that tried to move a finished run, and name it in the log.

    The status is not changed: a run that already reached a terminal verdict stays there.
    Refusing in silence would be the same lie in the other direction.
    """
    with _lock:
        _ledger["illegal_status_transitions"] += 1
        _note_reason(REASON_ILLEGAL_STATUS)
        count = _ledger["illegal_status_transitions"]
    logger.error(
        "[Trace] run %s kept status %r: %r is not a permitted transition (occurrences=%d)",
        run_id or "-",
        str(current or ""),
        str(requested or ""),
        count,
    )
    return count


def durability_status() -> dict[str, Any]:
    """A copy of the ledger, safe to embed in an operator-facing readout."""
    with _lock:
        snapshot = dict(_ledger)
        snapshot["fallback_by_reason"] = dict(_ledger["fallback_by_reason"])
    return snapshot


def fallback_is_live() -> bool:
    """True when the process knows of at least one trace only the file holds."""
    with _lock:
        return bool(_ledger["fallback_events"] or _ledger["fallback_reads"])


def reset_durability_ledger() -> None:
    """Drop the process counters; a test fixture boundary, not a runtime call."""
    global _ledger
    with _lock:
        _ledger = _fresh_ledger()
