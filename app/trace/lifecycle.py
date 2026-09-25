"""The run lifecycle vocabulary, and the two transitions a run may never make.

A run row is the one place an operator reads "did this request finish", so the words in
``agent_runs.status`` are load bearing. This module does not invent a vocabulary: it reads
the ratified one. ``AgentResult.status`` (``app/agents/contracts.py``) is the closed per-worker
Literal, ``app/trace/records.py`` and ``app/agents/orchestrator.py`` both fold ``success``
and ``partial`` into ``completed`` before writing a run, and
``app.common.stage_timing.REQUEST_TERMINAL_EVENTS`` is the closed set of events that end a
request. Everything below is derived from those three, so a new AgentResult status shows up
here without anybody editing a list by hand -- and a status that is not in it is a bug, not
a word.

The two forbidden transitions, both of which R250 pins:

* terminal -> open: a run that finished cannot be walked back to ``running``;
* anything -> an unregistered literal: a word outside the vocabulary never enters the table.

Terminal -> terminal stays allowed, because that is what the store already does and the
later verdict is the one a caller has more information behind: an optimistic ``completed``
must not launder a ``request.failed`` that arrives after it. A refusal is counted and
logged by name (``durability.note_illegal_status_transition``); the row is left alone.
"""
from __future__ import annotations

from typing import Any, get_args

from app.agents.contracts import AgentResult
from app.common.stage_timing import REQUEST_TERMINAL_EVENTS

#: The closed Literal on ``AgentResult.status`` -- eight words, no more.
AGENT_RESULT_STATUSES: tuple[str, ...] = tuple(
    get_args(AgentResult.model_fields["status"].annotation)
)

#: Worker verdicts that mean "the request produced an answer", folded into ``completed``
#: by ``app/trace/records.py:34`` and ``app/agents/orchestrator.py:1066`` before they reach
#: a run row. They are worker statuses, they are not run statuses.
_SUCCESSFUL_WORKER_STATUSES = ("success", "partial")

#: A run status that answers "this request is over", spelled with ``completed`` plus the
#: worker verdicts that already mean the request stopped: failed, rejected, timeout,
#: cancelled, model_unavailable, retrieval_unavailable.
RUN_TERMINAL_STATUSES: tuple[str, ...] = ("completed",) + tuple(
    status for status in AGENT_RESULT_STATUSES if status not in _SUCCESSFUL_WORKER_STATUSES
)

#: Statuses that mean "still going", which is exactly what the two emitters write today:
#: ``request.started`` carries ``started`` and ``step.started`` carries ``running``.
RUN_OPEN_STATUSES: tuple[str, ...] = ("started", "running")

#: Every literal this column may ever hold. Anything else is refused by name.
RUN_STATUSES: tuple[str, ...] = RUN_OPEN_STATUSES + RUN_TERMINAL_STATUSES

#: The event types that end a request -- imported, not retyped, from stage_timing.
RUN_TERMINAL_EVENT_TYPES: frozenset[str] = frozenset(REQUEST_TERMINAL_EVENTS)

#: Written when a status would otherwise be lost: the run row exists, and it says so.
UNREGISTERED_STATUS_FALLBACK = "running"

REFUSAL_UNREGISTERED_STATUS = "unregistered_run_status"
REFUSAL_TERMINAL_REGRESSION = "terminal_run_regression"


def is_terminal_status(status: Any) -> bool:
    """Whether a status word ends a run."""
    return str(status or "") in RUN_TERMINAL_STATUSES


def is_registered_status(status: Any) -> bool:
    """Whether a status word is in the vocabulary at all."""
    return str(status or "") in RUN_STATUSES


def resolve_run_status(
    *,
    run_id: str,
    current_status: Any,
    event_type: str,
    event_status: Any,
) -> tuple[str, str]:
    """Decide the status a run row may hold, and say why when it may not change.

    Returns ``(status, refusal_reason)``. ``refusal_reason`` is empty when the requested
    move is permitted; when it is not, the returned status is the one that stays in the
    table, so the caller cannot both refuse and write.
    """
    current = str(current_status or "")
    requested = str(event_status or "")
    terminal_event = str(event_type or "") in RUN_TERMINAL_EVENT_TYPES

    if not is_registered_status(requested):
        if current:
            return current, REFUSAL_UNREGISTERED_STATUS
        return UNREGISTERED_STATUS_FALLBACK, REFUSAL_UNREGISTERED_STATUS

    if is_terminal_status(current) and not is_terminal_status(requested):
        # A finished run does not restart. The row keeps its verdict, and the attempt is
        # counted -- "silently ignored" and "never happened" are different claims.
        return current, REFUSAL_TERMINAL_REGRESSION

    if terminal_event or not current:
        # A terminal event states the verdict; the first event of a trace seeds the row.
        # Anything else leaves an already-recorded verdict alone.
        return requested, ""
    return current, ""


def terminal_verdict(run: dict[str, Any] | None) -> dict[str, Any]:
    """Report the end state of a run row with the honesty flag the readout needs.

    ``status_is_terminal`` answers "did this request stop", ``completed_at_is_set``
    answers "did the store actually see the terminal event". They are read together: a run
    that reports ``completed`` without a completion timestamp is a verdict the ledger
    cannot back up, and the readout says so instead of smoothing it over.
    """
    status = str((run or {}).get("status") or "")
    return {
        "status": status,
        "status_is_terminal": is_terminal_status(status),
        "status_is_registered": is_registered_status(status),
        "completed_at_is_set": (run or {}).get("completed_at") is not None,
        "error_code": (run or {}).get("error_code"),
    }
