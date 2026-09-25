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
