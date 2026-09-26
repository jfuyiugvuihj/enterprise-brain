"""Trace persistence: the six PostgreSQL tables are the source of truth.

R250 replaced the sentence this file used to open with -- "Append-only local trace store
used until database trace tables are integrated". The tables in
``migrations/0002_execution_data_lineage.sql`` (``trace_events``, ``agent_runs``,
``agent_steps``, ``tool_calls``, ``model_calls``, ``retrieval_traces``) are integrated now:
every event is written there and read back from there, so a second API process, a worker,
or a restarted container sees the same run.

The append-only journal at ``TRACE_STORE_PATH`` did not disappear; it moved. It is the
fallback for the window in which PostgreSQL cannot take the write, and a fallback is only
safe if somebody can see it: every degraded event is counted and logged under
``app.trace.durability.LOCAL_FALLBACK_NAME``, and the run readout carries the same name in
its ``source`` field. When PostgreSQL is reachable that name appears nowhere.

Two details are load bearing rather than cosmetic:

* sequence numbers come from ``MAX(sequence)`` in ``trace_events`` (floored by the local
  journal, so the two ledgers can never hand out the same id twice). Deriving them from
  one process's file was how two writers produced colliding event ids, which the table's
  ``UNIQUE (trace_id, sequence)`` then rightly refused;
* a projection is never allowed to half-succeed silently. The store catches the database
  error, keeps the event in the fallback journal, and names the reason -- the answer to a
  broken ledger is an observable degraded one, not a request that dies on telemetry.

Two more claims belong here, because both of the sentences above are only true once the
fallback window has been closed -- and R257 is what closes it:

* the journal is an exception list, not the total account. Every line in it is a line
  PostgreSQL refused, and since R257 each one carries its own admission -- the reason code,
  the timestamp, and a pointer at the six tables as the complete ledger -- so nobody can
  read a count out of this file and mistake it for the number of events the system saw;
* a refused write does not stay refused. The next event that reaches the tables settles
  what the journal holds (``TraceStore.backfill_fallback_journal``): each recorded
  ``(trace_id, sequence)`` is replayed through the very projections above, so the unique key
  is what makes a second sweep a no-op instead of a second row. Settled lines are not
  erased -- the sweep appends a receipt line naming what it moved into the tables, because
  on a private host this file is the only copy until the tables say otherwise.

A fourth claim belongs here, because the two sentences above are only true while PostgreSQL
answers for itself. ``MAX(sequence)`` is the one reading that says what the tables already
hold; when it does not answer, there is no number this store is entitled to put on an event
and later replay at that address (R263). Such an event is recorded with a *local ordinal* --
enough to keep two journal lines apart, and admitted on the line itself as not confirmed by
the tables, under ``fallback.sequence_proven`` -- and it is addressed out of the number book,
by its own ``provisional_id``. The sweep that recovers it takes a number from the tables as
they are at that moment and stores the row under ``{trace_id}:u{token}``, so a number that
had turned out to be taken is refused by ``UNIQUE (trace_id, sequence)`` instead of landing
on ``ON CONFLICT (event_id) DO UPDATE`` over the row that already holds it. An unanswered
sequence read costs the trace its place in the tables' ordering, which the sweep restores in
journal order; what it can no longer cost is somebody else's event.
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.common.logger import logger
from app.common.tracing import sanitize_trace_event
from app.storage.persistence import PersistenceWriteError, build_persistence_adapter
from app.trace import durability
from app.trace.durability import (
    LOCAL_FALLBACK_NAME,
    POSTGRES_SOURCE,
    REASON_BACKEND_NOT_POSTGRES,
    REASON_OWNER_MISSING,
    REASON_READ_FAILED,
    REASON_SCHEMA_MISMATCH,
    REASON_WRITE_FAILED,
)
from app.trace.projections import (
    Projection,
    project_event,
    project_event_row,
    project_run,
    project_span,
    project_step,
    provisional_event_id,
    run_id_for,
)
from app.trace.run_reader import TraceDatabase, TraceDatabaseUnavailable, database_for
from app.trace.runs import assemble_run_readout, fold_events, trace_id_from_run_id
from app.trace.schema import TraceSchemaError


#: The two kinds of line the fallback journal holds. An event the tables refused carries a
#: ``fallback`` block saying why and where the whole ledger lives; a ``fallback_receipt``
#: block is a settlement sweep reporting which lines are now rows in the six tables. Neither
#: marker holds a trace id, so annotating a line cannot make ``grep -c`` on an id count it
#: twice -- the mistake this file stopped being able to answer for in R250.
FALLBACK_LINE_MARKER = "fallback"
BACKFILL_RECEIPT_MARKER = "fallback_receipt"

#: The sentence every refused line says about itself, in the line itself.
FULL_LEDGER_STATEMENT = (
    "local fallback copy: PostgreSQL refused this write, so this file is not the full trace "
    "ledger -- the six trace tables (trace_events and siblings) are"
)

#: The name a sweep gives the line whose event id the tables already hold for a different
#: event, so the log says which refusal left the line behind without a new reason code.
ID_TAKEN_DETAIL = "event id is held by another event"

#: What the ordinal of an unconfirmed event says about itself, on the line that carries it.
#: The number is real -- it keeps two journal lines apart and orders them -- it is simply not
#: this event's id in ``trace_events``, and an operator reading the file has to be able to
#: tell those two statements apart without opening this module (R263).
UNPROVEN_SEQUENCE_STATEMENT = (
    "local ordinal only: PostgreSQL did not answer MAX(sequence) when this number was taken, "
    "so it is not this event's id in trace_events; the settlement sweep gives it one"
)

#: Events one settlement sweep offers to the tables. The sweep runs under the write lock, so
#: a longer journal is drained over more than one sweep and each report names what is left.
BACKFILL_LINES_PER_SWEEP = 2_000


class TraceStoreError(ValueError):
    """Raised when a trace event cannot be safely recorded."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TraceStore:
    def __init__(self, path: str | Path, persistence=None, database: TraceDatabase | None = None):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.persistence = persistence
        #: None means "this process has no PostgreSQL trace tables", which is a durability
        #: statement, not an optimization: everything written from here lands in the file.
        self.database = database if database is not None else database_for(persistence)
        #: R51: trace_id -> the timestamp of its ``request.started`` event, so the
        #: health readout can state an end-to-end window without re-reading the log.
        #: Bounded because an abandoned request must not grow a process forever.
        self._request_started: dict[str, str] = {}
        #: Whether the journal may hold lines the tables do not. True to start with: another
        #: process, or a previous lifetime of this one, may have left refused lines behind,
        #: and the counters in ``app.trace.durability`` are process-local and cannot say so.
        #: ``_write_fallback`` re-arms it; one successful write spends it.
        self._backfill_sweep_pending = True
        #: The ``trace_events`` addresses of journal lines this process has watched settle.
        #: Only lines admitted as unproven are recorded: their row is addressed by a token
        #: rather than a number, so a read cannot recognise it from the rows alone. Bounded,
        #: because a settled line is answered by the tables from then on either way.
        self._durable_provisional_ids: set[str] = set()
        durability.set_backend(backend=self._backend_name(), postgres=self.database is not None)

    # ------------------------------------------------------------------ backends

    def _backend_name(self) -> str:
        if self.database is not None:
            return POSTGRES_SOURCE
        if self.persistence is None:
            return "none"
        return "json" if hasattr(self.persistence, "path") else type(self.persistence).__name__

    def is_postgres_backed(self) -> bool:
        """Whether a trace written here is stored in the six tables."""
        return self.database is not None

    def durability_status(self) -> dict[str, Any]:
        """The ledger an operator reads to know whether to trust the trace they are shown.

        ``source_of_truth`` is answered from this store's own backend rather than from the
        module ledger, so a readout can never claim one backend while talking to another.
        ``durable`` is answered the same way: a backend that is wired up but has refused a
        write in this process is not holding every trace, so it does not get to say it is.
        """
        status = durability.durability_status()
        status["backend"] = self._backend_name()
        status["source_of_truth"] = (
            POSTGRES_SOURCE if self.database is not None else LOCAL_FALLBACK_NAME
        )
        status["durable"] = self.database is not None and not status["degraded"]
        status["fallback_path"] = str(self.path)
        return status

    # --------------------------------------------------------------------- writes

    def record_event(
        self,
        *,
        trace_id: str,
        request_id: str,
        event_type: str,
        status: str,
        payload: dict[str, Any] | None = None,
        task_id: str = "",
    ) -> dict[str, Any]:
        trace_id = str(trace_id or "").strip()
        request_id = str(request_id or "").strip()
        if not trace_id or not request_id:
            raise TraceStoreError(
                "validation_error",
                "Trace events require trace_id and request_id.",
            )

        with self._lock:
            owner_id = str((payload or {}).get("owner_id") or "").strip()
            attempts = 2 if self.database is not None else 1
            #: An open window is settled before this event takes a number, so the events it
            #: held keep their place ahead of this one on the tables' number line instead of
            #: being re-numbered behind it. A process with nothing to settle pays for the
            #: same one ``exists()`` this call has always paid, one event later.
            self.maybe_backfill_fallback_journal()
            event: dict[str, Any] = {}
            settled = False
            for attempt in range(attempts):
                sequence, proven, unproven_note = self._next_sequence(trace_id)
                event = self._build_event(
                    trace_id=trace_id,
                    request_id=request_id,
                    task_id=task_id,
                    event_type=event_type,
                    status=status,
                    payload=payload or {},
                    sequence=sequence,
                )
                if self.database is None:
                    # No PostgreSQL in this process: whatever the configured journal holds,
                    # the six tables do not, so the fallback copy is taken and named.
                    reason, detail = self._persist(event, owner_id)
                    self._write_fallback(
                        event,
                        reason or REASON_BACKEND_NOT_POSTGRES,
                        detail or "the six trace tables are not configured for this process",
                    )
                    break
                if not proven:
                    # The tables would not say what they hold, so this number is an ordinal
                    # and nothing entitles this process to write at that address: whatever is
                    # there is a different event, and ``ON CONFLICT (event_id) DO UPDATE``
                    # would replace it without an error. The line is kept, named, and given a
                    # number by the sweep that runs once the tables answer again. Why it could
                    # not reach the tables for any *other* reason is still named first: an
                    # event nobody can own is not a numbering problem, and the operator who
                    # has to fix it is owed the reason that is true of it.
                    reason, detail = self._refusal_before_writing(owner_id) or (
                        REASON_WRITE_FAILED,
                        f"sequence {sequence} is not confirmed by the tables ({unproven_note})",
                    )
                    self._write_fallback(event, reason, detail, proven=False)
                    break
                reason, detail = self._persist(event, owner_id)
                if reason is None:
                    settled = True
                    break
                if attempt == 0 and _is_sequence_collision(detail):
                    continue
                self._write_fallback(event, reason, detail)
                break
            self._observe_request_window(event)
            if settled:
                # Reached only when this process can write to the tables right now, which is
                # exactly the moment a line in the fallback journal became stale.
                self.maybe_backfill_fallback_journal()
            return event

    def _build_event(
        self,
        *,
        trace_id: str,
        request_id: str,
        task_id: str,
        event_type: str,
        status: str,
        payload: dict[str, Any],
        sequence: int,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "request_id": request_id,
            "task_id": task_id,
            "sequence": sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": str(event_type or ""),
            "status": str(status or ""),
            "payload": sanitize_trace_event(payload or {}),
        }

    def _write_fallback(
        self, event: dict[str, Any], reason: str, detail: str, *, proven: bool = True
    ) -> None:
        """Append one event to the local journal and say out loud that we had to.

        Three places learn about it: the log line and the ledger count, as before, and now
        the line itself. That third one is the point -- since R250 this file holds *only*
        refused events, so anybody reading it with ``grep`` or a dump tool has to be able to
        tell from the bytes on the page that the number they are counting is not the number
        of events the system saw, without opening a document to find out.

        ``proven`` is R263's half of that sentence. When PostgreSQL would not answer
        ``MAX(sequence)`` for this event, the number it carries is an ordinal of this file,
        not an address in ``trace_events``, and the line says so and names the token the row
        will be addressed by once the tables can be asked. Both statements live in the
        marker, so the event keeps its eight keys and counting a trace id in this file still
        counts events.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        marker = {
            "is_fallback": True,
            "reason": str(reason or ""),
            # The event's own stamp, not a second reading of the clock: the admission
            # describes the moment this line was recorded, and the store already decided
            # what that moment was.
            "recorded_at": str(event.get("timestamp") or ""),
            "full_ledger": FULL_LEDGER_STATEMENT,
        }
        address = f"{event['trace_id']}:{event['sequence']}"
        if not proven:
            token = uuid.uuid4().hex
            marker["sequence_proven"] = False
            marker["provisional_id"] = token
            marker["sequence_note"] = UNPROVEN_SEQUENCE_STATEMENT
            address = provisional_event_id(str(event["trace_id"]), token)
        line = dict(event)
        line[FALLBACK_LINE_MARKER] = marker
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        durability.note_local_fallback(reason, f"event_id={address} {detail}")
        if not proven:
            durability.note_unproven_sequence()
        # A refused line is precisely what the next successful write has to settle.
        self._backfill_sweep_pending = True

    def _persist(
        self, event: dict[str, Any], owner_id: str, *, event_id: str | None = None
    ) -> tuple[str | None, str]:
        """Write one event and its rows to the configured backend.

        Returns ``(None, "")`` when the tables hold the whole event, and a
        ``(reason, detail)`` pair when they do not; the caller decides what the fallback
        journal has to keep. ``event_id`` is the address the ``trace_events`` row is stored
        at, and only R263's sweep passes one: a recovered line whose own number was never
        confirmed keeps its child rows on the number it is given then, but its event row on
        the id of the line, so the insert cannot land on another event's row.
        """
        refusal = self._refusal_before_writing(owner_id)
        if refusal is not None:
            return refusal
        try:
            self._apply(project_event_row(event, owner_id, event_id=event_id).seal())
            for projection in project_event(event, owner_id=owner_id, fetch=self._current_row):
                self._apply(projection)
        except TraceSchemaError as exc:
            return REASON_SCHEMA_MISMATCH, f"{exc.code}: {exc}"
        except PersistenceWriteError as exc:
            return REASON_WRITE_FAILED, str(exc)
        except (TraceDatabaseUnavailable, ValueError) as exc:
            return REASON_WRITE_FAILED, f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # telemetry never fails a request, but it is never silent
            return REASON_WRITE_FAILED, f"{type(exc).__name__}: {exc}"
        return None, ""

    def _refusal_before_writing(self, owner_id: str) -> tuple[str, str] | None:
        """Why an event cannot reach the tables whatever else is true of them.

        Two facts are independent of PostgreSQL being up, so R263 asks them before it takes
        the number's address to itself: no adapter configured, and no owner to attribute the
        row to. A line that fails one of those is named for it, not for the sequence read
        that also happened to be unanswered, or an operator reads a numbering problem where
        the trace has an identity problem.
        """
        if self.persistence is None:
            return REASON_BACKEND_NOT_POSTGRES, "no persistence adapter is configured"
        if not owner_id:
            return REASON_OWNER_MISSING, "trace events require an owner_id to reach the tables"
        return None

    def _apply(self, projection: Projection) -> None:
        """Push one sealed projection through the configured adapter."""
        refusal = str(projection.notes.get("status_refusal") or "")
        if refusal:
            durability.note_illegal_status_transition(
                projection.record_id,
                projection.notes.get("current_status"),
                projection.notes.get("requested_status"),
            )
        self.persistence.upsert(  # type: ignore[union-attr]
            projection.collection, projection.record_id, dict(projection.values)
        )

    def _current_row(self, collection: str, record_id: str) -> dict[str, Any] | None:
        if self.persistence is None or not record_id:
            return None
        return self.persistence.get(collection, record_id)

    # ---------------------------------------------------------------------- backfill

    @staticmethod
    def _event_identity(event: dict[str, Any], marker: dict[str, Any]) -> str:
        """Which book one journal line is addressed in.

        A line whose number the tables confirmed is addressed by that number, exactly as a
        live event is. A line admitted as unproven (R263) is addressed by its own token
        instead, in an id no ``(trace_id, sequence)`` pair can produce, so replaying it can
        only ever conflict with itself -- and a number that has since been taken is refused by
        the table's unique key rather than written over the event that holds it.
        """
        trace_id = str(event.get("trace_id") or "")
        if marker.get("sequence_proven") is False:
            token = str(marker.get("provisional_id") or "")
            if token:
                return provisional_event_id(trace_id, token)
        return f"{trace_id}:{event.get('sequence')}"

    def _remember_durable(self, identity: str) -> None:
        """Note that a token-addressed line is answered for by a row (bounded memo)."""
        if len(self._durable_provisional_ids) < 4096:
            self._durable_provisional_ids.add(identity)

    def _provisional_line_is_durable(self, identity: str) -> bool:
        """Whether a line addressed out of the number book is already a row.

        Only token-addressed lines are asked: a line with a confirmed number carries the row's
        own id, so the read path recognises it from the rows already in hand. The journal
        never deletes the line it settled, so the answer is remembered for this process.
        """
        if identity in self._durable_provisional_ids:
            return True
        if self._durable_row_by_id(identity) is None:
            return False
        self._remember_durable(identity)
        return True

    def _durable_row_by_id(self, event_id: str) -> dict[str, Any] | None:
        """The ``trace_events`` row stored at one address, when the tables have one.

        A question, not the guard: the guard is the unique key. Asking first is what lets a
        sweep tell an event it recovered from one the tables already answer for, and -- the
        reason it asks about content and not only about the id -- what lets it refuse to
        overwrite a durable row with a different event. Since R263 the ids it asks about come
        from two books: a confirmed line is asked about by its number, an unconfirmed one by
        its token, which is the only address that line will ever be written at.

        ``None`` means "the tables are not answering for this id", which includes "the
        question could not be asked": an unreadable table is no reason to skip a replay, and
        the insert will be refused by the key if it turns out to be occupied.
        """
        if self.persistence is None or not event_id:
            return None
        try:
            row = self.persistence.get("trace_events", event_id)
        except Exception:
            return None
        return row if isinstance(row, dict) else None

    def _durable_event_row(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """The row at one event's own address. See ``_durable_row_by_id``."""
        return self._durable_row_by_id(self._event_identity(event, {}))

    @staticmethod
    def _is_the_same_event(row: dict[str, Any], event: dict[str, Any]) -> bool:
        """Whether a ``trace_events`` row and a journal line describe one and the same event."""
        return (
            str(row.get("event_type") or ""), str(row.get("status") or "")
        ) == (str(event.get("event_type") or ""), str(event.get("status") or ""))

    def backfill_fallback_journal(
        self, *, limit: int | None = BACKFILL_LINES_PER_SWEEP
    ) -> dict[str, Any]:
        """Replay the fallback journal into the six tables, and say what is still missing.

        This is the debt R250 left open: PostgreSQL refused a write, the event went to the
        journal, and nothing ever carried it back, so "the six tables are the source of
        truth" was untrue for exactly that stretch of time -- and an administrator querying
        the run by id could not read those events at all. A sweep walks the journal in line
        order and hands every event to ``_persist``, the same owner check, the same
        projections and the same column contract as a live write, so there is no second
        writer for the first one to disagree with.

        Idempotency belongs to the tables, not to this loop. A line whose number the
        tables confirmed is addressed by that ``(trace_id, sequence)`` and ``trace_events``
        makes that pair unique; a line that could not confirm one (R263) is renumbered at
        the floor the tables report and keyed by its own token, which no pair can produce.
        Either way a sweep that runs twice leaves one row -- it does not need to remember

        having run. That is also why a settled line is never erased: the sweep appends a
        receipt naming the lines it covered and leaves the events exactly where they were,
        because on a private host this file is the only copy until the tables say otherwise.

        Two consequences worth stating rather than hiding. Lines written before the journal
        annotated itself are offered to the tables like any other, which also recovers what
        this file held back when it *was* the only store. And a line whose payload carries
        no ``owner_id`` can never reach the tables -- the live write refuses it for the same
        reason -- so it is counted in ``never_in_tables`` instead of being retried forever,
        and it is the one part of this answer that stays "not in the six tables", loudly.
        """
        if self.database is None:
            # No tables to fill. Naming that is the ledger's job, not a reason to sweep.
            return {"attempted": False, "skipped_reason": REASON_BACKEND_NOT_POSTGRES}
        with self._lock:
            report = self._empty_backfill_report()
            records = self._journal_records(tolerant=True)
            events = [record for record in records if record["kind"] == "event"]
            report["journal_events"] = len(events)
            report["unreadable_lines"] = sum(
                1 for record in records if record["kind"] == "unparsed"
            )
            report["receipt_lines"] = sum(
                1 for record in records if record["kind"] == "receipt"
            )
            report["still_local_lines"] = len(events)
            if not events:
                return report
            pending = events if limit is None else events[: max(0, int(limit))]
            for record in pending:
                report["scanned"] += 1
                event = record["event"]
                owner_id = str((event.get("payload") or {}).get("owner_id") or "").strip()
                if not owner_id:
                    report["never_in_tables"] += 1
                    continue
                marker = record["marker"]
                proven = marker.get("sequence_proven") is not False
                identity = self._event_identity(event, marker)
                if proven:
                    row = self._durable_event_row(event)
                else:
                    # R263: this line carries an ordinal of this file, not an address in the
                    # tables, so it is asked about -- and written -- under its own token.
                    report["unproven_lines"] += 1
                    row = self._durable_row_by_id(identity)
                if row is not None:
                    if self._is_the_same_event(row, event):
                        report["already_in_tables"] += 1
                        report["covered_through_line"] = int(record["line"])
                        if not proven:
                            self._remember_durable(identity)
                    else:
                        # The id is taken by a different event. Writing it would replace a
                        # durable row -- losing the event that is really there to "recover"
                        # one that is not -- so the line stays in the journal, where the
                        # readout reports it as missing, and the reason is named in the log.
                        report["refused"][REASON_WRITE_FAILED] = report["refused"].get(REASON_WRITE_FAILED, 0) + 1
                        report["refused_detail"][ID_TAKEN_DETAIL] = (
                            report["refused_detail"].get(ID_TAKEN_DETAIL, 0) + 1
                        )
                    continue
                if proven:
                    address = None
                else:
                    trace_id = str(event.get("trace_id") or "")
                    floor, answered, note = self._postgres_sequence_floor(trace_id)
                    if not answered:
                        # The tables still cannot say what they hold, so they cannot be told
                        # where to put this. The line waits, counted and named in the report,
                        # and the readout still calls it a gap: deferred, not lost.
                        report["unproven_deferred"] += 1
                        report["deferred_note"] = note[:200]
                        continue
                    event = {**event, "sequence": floor + 1}
                    address = identity
                why, detail = self._persist(event, owner_id, event_id=address)
                if why is None:
                    report["settled_events"] += 1
                    if not proven:
                        # Every number this sweep takes comes from the tables as they are at
                        # that moment, so the line before it has already raised the floor.
                        report["renumbered_lines"] += 1
                        durability.note_sequence_renumbered()
                        self._remember_durable(identity)
                    report["covered_through_line"] = int(record["line"])
                    continue
                # A refusal keeps the line exactly where it is, including the interesting
                # one: PostgreSQL refusing this (trace_id, sequence) because a concurrent
                # writer took it between the question above and this insert. Folding such a
                # line into already_in_tables would report a lost event as a recovered one,
                # so it is refused and stays visible -- in the journal, in this report, and
                # in the readout's gap. Since R263 the insert can actually be refused that
                # way rather than updating the row that got there first, and an unproven line
                # simply offers its number again on the next sweep, which asks again.
                report["refused"][why] = report["refused"].get(why, 0) + 1
                refused_detail = str(detail)[:200] or why
                report["refused_detail"][refused_detail] = (
                    report["refused_detail"].get(refused_detail, 0) + 1
                )

            report["still_local_lines"] = (
                report["journal_events"]
                - report["settled_events"]
                - report["already_in_tables"]
            )
            if report["settled_events"]:
                report["receipt"] = self._append_backfill_receipt(report)
            durability.note_backfill(
                settled_events=report["settled_events"],
                already_in_tables=report["already_in_tables"],
                local_only_lines=report["still_local_lines"],
                never_in_tables=report["never_in_tables"],
            )
            self._log_backfill(report)
            return report

    @staticmethod
    def _empty_backfill_report() -> dict[str, Any]:
        return {
            "attempted": True,
            "journal_events": 0,
            "scanned": 0,
            "settled_events": 0,
            "already_in_tables": 0,
            "never_in_tables": 0,
            "refused": {},
            "covered_through_line": 0,
            "still_local_lines": 0,
            "unreadable_lines": 0,
            "receipt_lines": 0,
            "receipt": False,
            "refused_detail": {},
            "unproven_lines": 0,
            "renumbered_lines": 0,
            "unproven_deferred": 0,
            "deferred_note": "",
        }

    def _log_backfill(self, report: dict[str, Any]) -> None:
        """Say what the sweep did, and name what it could not do, in the log."""
        if report["still_local_lines"]:
            logger.warning(
                "[Trace] %s backfill settled %d event(s) into the six tables (already there: "
                "%d) and %d line(s) are still held only by %s: no owner=%d refused=%s "
                "not scanned=%d. Why they were refused: %s -- the tables are the ledger and "
                "this file is the exception list, not the total account",
                LOCAL_FALLBACK_NAME,
                report["settled_events"],
                report["already_in_tables"],
                report["still_local_lines"],
                self.path,
                report["never_in_tables"],
                report["refused"],
                report["journal_events"] - report["scanned"],
                sorted(report["refused_detail"]),
            )
            return
        if report["settled_events"] or report["already_in_tables"]:
            logger.info(
                "[Trace] %s journal settled: %d event(s) replayed into the six tables, %d "
                "already answered for; %d unannotated line(s) left in place, none deleted",
                LOCAL_FALLBACK_NAME,
                report["settled_events"],
                report["already_in_tables"],
                report["unreadable_lines"],
            )

    def maybe_backfill_fallback_journal(self) -> dict[str, Any] | None:
        """One bounded settlement sweep, and only when this process has a reason to expect one.

        Called from the write path *after* an event has already reached the tables, so the
        request that triggered it pays for at most one sweep. A process whose PostgreSQL
        never went away pays for one ``exists()`` check: an absent journal is the normal
        case, and this never creates the file.
        """
        if self.database is None or not self._backfill_sweep_pending:
            return None
        self._backfill_sweep_pending = False
        try:
            return self.backfill_fallback_journal()
        except Exception as exc:  # recovery is telemetry, it does not fail a request
            durability.note_backfill_error(f"{type(exc).__name__}: {exc}")
            self._backfill_sweep_pending = True
            return None

    def _append_backfill_receipt(self, report: dict[str, Any]) -> dict[str, Any]:
        """Say on the journal itself which of its lines the six tables now hold.

        A receipt is the second kind of line in the same append-only file, and it repeats no
        trace id on purpose: a receipt that echoed ids would make a count of the file double,
        which is the exact mistake the annotations exist to prevent.
        """
        receipt = {
            "at": datetime.now(timezone.utc).isoformat(),
            "settled_events": report["settled_events"],
            "already_in_tables": report["already_in_tables"],
            "never_in_tables": report["never_in_tables"],
            "refused": dict(report["refused"]),
            "covered_through_line": report["covered_through_line"],
            "journal_events_at_receipt": report["journal_events"],
            "still_local_lines": report["still_local_lines"],
            "unreadable_lines": report["unreadable_lines"],
            "full_ledger": FULL_LEDGER_STATEMENT,
            "note": "every event line up to the numbered line above was offered to the six "
            "trace tables by this sweep; no journal line was deleted to get there",
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({BACKFILL_RECEIPT_MARKER: receipt}, ensure_ascii=False) + "\n")
        return receipt

    # -------------------------------------------------------------- projections API

    def _persist_execution_records(self, event: dict[str, Any], owner_id: str) -> None:
        """Project one event onto the execution tables (run first, children after)."""
        for projection in project_event(event, owner_id=owner_id, fetch=self._current_row):
            self._apply(projection)

    def _persist_span(self, event: dict[str, Any], owner_id: str, collection: str) -> None:
        """Project a model or tool span onto its own execution row."""
        payload = event["payload"]
        record_id = str(payload.get("record_id") or "").strip()
        if not record_id:
            return
        projection = project_span(event, owner_id, self._current_row(collection, record_id) or {}, collection)
        if projection is not None:
            self._apply(projection.seal())

    def _persist_step(self, event: dict[str, Any], owner_id: str) -> None:
        """Project one ``step.started`` / ``step.finished`` pair onto its step row."""
        payload = event["payload"]
        step_id = str(payload.get("step_id") or f"{event['trace_id']}:{event['sequence']}")
        self._apply(
            project_step(event, owner_id, self._current_row("agent_steps", step_id) or {}).seal()
        )

    def _persist_run(self, event: dict[str, Any], owner_id: str) -> None:
        """Refresh the orchestrator run row for one event."""
        record_id = run_id_for(event["trace_id"])
        self._apply(project_run(event, owner_id, self._current_row("agent_runs", record_id) or {}).seal())

    # ---------------------------------------------------------------------- reads

    def replay(self, trace_id: str) -> list[dict[str, Any]]:
        """Every event of one trace: PostgreSQL rows, plus anything the fallback kept.

        The fallback lines are merged by event id rather than ignored, because a degraded
        window is part of the trace it degraded in -- dropping it would make the replay
        look complete when it is not.
        """
        trace_id = str(trace_id or "").strip()
        if not trace_id:
            return []
        with self._lock:
            lines = self._local_trace_lines(trace_id)
            if self.database is None:
                if self.persistence is not None:
                    # The JSON adapter is a durable journal too; it is simply not the six
                    # tables, and the durability ledger already says which one this is.
                    try:
                        stored = [
                            self.database_as_event(row)
                            for row in (self.persistence.list("trace_events") or [])
                            if str(row.get("trace_id") or "") == trace_id
                        ]
                    except Exception as exc:
                        durability.note_local_read_fallback(REASON_READ_FAILED, str(exc))
                        stored = []
                    events = _merge_events(stored, lines)
                else:
                    events = [event for _, event in lines]
                return sorted(events, key=lambda event: int(event.get("sequence") or 0))
            try:
                events = self.database.fetch_events(trace_id)
            except TraceDatabaseUnavailable as exc:
                durability.note_local_read_fallback(exc.reason, str(exc))
                return sorted(
                    (event for _, event in lines),
                    key=lambda event: int(event.get("sequence") or 0),
                )
            return sorted(
                _merge_events(events, lines), key=lambda event: int(event.get("sequence") or 0)
            )

    def _local_trace_lines(self, trace_id: str) -> list[tuple[str, dict[str, Any]]]:
        """This trace's journal lines, as (address, event) pairs, minus the ones already rows.

        A line whose number the tables confirmed is addressed by that number, which is also
        the id of its row, so the merge below recognises it without asking. A line admitted as
        unproven (R263) carries an ordinal of this file, and the only thing that ties it to
        the row it settled into is its own token: the tables are asked for that, once per
        line, and the answer is remembered. Dropping such a line is honest only because the
        row is in the answer already -- dropping a line the tables never took would be the
        "this trace is complete" lie this file exists to prevent, and that is what the
        address is for: a confirmed line hides behind no row, because the two share an id.
        """
        lines: list[tuple[str, dict[str, Any]]] = []
        for record in self._journal_records():
            if record["kind"] != "event":
                continue
            event = record["event"]
            if str(event.get("trace_id") or "") != trace_id:
                continue
            marker = record["marker"] or {}
            identity = self._event_identity(event, marker)
            if marker.get("sequence_proven") is False:
                if self._provisional_line_is_durable(identity):
                    continue
            lines.append((identity, event))
        return lines

    @staticmethod
    def database_as_event(row: dict[str, Any]) -> dict[str, Any]:
        return TraceDatabase._as_event(row)

    def read_run(self, run_id: str) -> dict[str, Any]:
        """One run with its steps, tool calls and model calls, from the trace tables.

        Falls back to folding the local journal through the same projections when
        PostgreSQL cannot answer, and the returned document names which one it came from.
        When the tables answered but a degraded window is still waiting to be settled, the
        document also carries ``local_only``: the events this run has in the journal and not
        in the rows, counted and dated (``backfill_fallback_journal`` empties it).
        """
        run_id = str(run_id or "").strip()
        if not run_id:
            raise TraceStoreError("validation_error", "A run read requires a run_id.")
        with self._lock:
            if self.database is not None:
                try:
                    bundle = self.database.read_run_rows(run_id)
                except TraceDatabaseUnavailable as exc:
                    durability.note_local_read_fallback(exc.reason, str(exc))
                else:
                    if bundle.get("run") is not None or bundle.get("events"):
                        durable = {
                            f"{event.get('trace_id')}:{event.get('sequence')}": (
                                str(event.get("event_type") or ""),
                                str(event.get("status") or ""),
                            )
                            for event in bundle.get("events") or []
                        }
                        return assemble_run_readout(
                            run_id,
                            bundle,
                            source=POSTGRES_SOURCE,
                            durability_block=self.durability_status(),
                            local_only=self._local_only_gap(run_id, durable),
                        )
                    # PostgreSQL was reached and has no such run. The journal is still
                    # consulted, because a degraded window put events there on purpose; but a
                    # journal that also holds nothing does not get to be called the source,
                    # so an empty answer is reported against the durable backend.
                    folded = fold_events(self._run_events(run_id), run_id)
                    if folded.get("run") is not None or any(folded["tables"].values()):
                        return assemble_run_readout(
                            run_id,
                            folded,
                            source=LOCAL_FALLBACK_NAME,
                            durability_block=self.durability_status(),
                        )
                    return assemble_run_readout(
                        run_id, bundle, source=POSTGRES_SOURCE,
                        durability_block=self.durability_status(),
                    )
            events = self._run_events(run_id)
            # No gap to disclose beside this one: the journal *is* the answer it is being
            # read from, ``source`` already says so, and counting its lines back at the
            # caller as missing rows would report the same events twice.
            return assemble_run_readout(
                run_id,
                fold_events(events, run_id),
                source=LOCAL_FALLBACK_NAME,
                durability_block=self.durability_status(),
            )

    # ------------------------------------------------------------------- internals

    def _observe_request_window(self, event: dict[str, Any]) -> None:
        """Note the wall clock of one request for the stage coverage gate.

        Both timestamps are already in the event the store just wrote, so this is not a
        third clock: it is the same subtraction the latency budget used, done in-process.
        Nothing persisted depends on it and a failure is invisible to the caller.
        """
        try:
            from app.common.stage_timing import (
                REQUEST_TERMINAL_EVENTS,
                default_stage_ledger,
                stage_timing_enabled,
                to_epoch_ms,
            )

            if not stage_timing_enabled():
                return
            trace_id = str(event.get("trace_id") or "")
            event_type = str(event.get("event_type") or "")
            if not trace_id:
                return
            if event_type == "request.started":
                self._request_started[trace_id] = str(event.get("timestamp") or "")
                while len(self._request_started) > 512:
                    self._request_started.pop(next(iter(self._request_started)))
                return
            if event_type in REQUEST_TERMINAL_EVENTS:
                started = to_epoch_ms(self._request_started.pop(trace_id, ""))
                finished = to_epoch_ms(event.get("timestamp"))
                if started is not None and finished is not None and finished >= started:
                    default_stage_ledger().add_request_window(trace_id, finished - started)
        except Exception as exc:  # noqa: BLE001 - a counter is never a request failure
            logger.warning("[Trace] request window was not recorded: %s", exc)

    def _next_sequence(self, trace_id: str) -> tuple[int, bool, str]:
        """The number for the next event, and whether the tables stand behind it.

        ``max(pg, file) + 1`` is the rule; what R263 adds is that the two floors are not the
        same kind of fact. PostgreSQL answering is what makes a number safe to replay at that
        address, while the journal floor only says what this file has handed out. So the
        answer is a triple: the number, whether the tables confirmed it, and what they said
        when they did not. An unconfirmed number is still taken, because two lines of one
        trace must not read as one event, but it is an ordinal of this file and is never used
        as an address in ``trace_events`` -- see ``record_event`` and the sweep.
        """
        floor, proven, note = self._postgres_sequence_floor(trace_id)
        file_floor = self._file_sequence_floor(trace_id)
        if not proven:
            return file_floor + 1, False, note
        return max(floor, file_floor) + 1, True, ""

    def _postgres_sequence_floor(self, trace_id: str) -> tuple[int, bool, str]:
        """What PostgreSQL says the highest event id is, and whether it answered at all.

        The second value is the whole of R263. Reading an unanswered ``MAX(sequence)`` as a
        floor of 0 is what let a trace that degrades *midway* hand a fallback line an id the
        tables had already given to another event, and a replay addressed at that id does not
        fail loudly: ``trace_events`` is written ``ON CONFLICT (event_id) DO UPDATE``, so the
        other event's row is quietly replaced while the journal reports a recovery. "Nothing
        here yet" and "not answering" are two different facts, and only the first is a floor.

        An unanswered sequence read is not counted as a fallback of its own: the event being
        built right now either reaches the tables (nothing was lost) or goes to the journal
        one statement later, and that write is what gets named. Naming both would double
        every degraded event in the ledger an operator reads.
        """
        if self.database is None:
            # No six tables in this process at all, so there is no number line to disagree
            # with and the journal floor is the whole of it. That is a durability statement,
            # already named by the fallback source, not an unanswered question.
            return 0, True, ""
        try:
            return self.database.max_sequence(trace_id), True, ""
        except TraceDatabaseUnavailable as exc:
            return 0, False, f"{exc.reason}: {exc}"

    def _file_sequence_floor(self, trace_id: str) -> int:
        events = [event for event in self._read_events() if event.get("trace_id") == trace_id]
        if not events:
            return 0
        return max(int(event.get("sequence") or 0) for event in events)

    def _local_only_gap(self, run_id: str, durable: dict[str, tuple[str, str]]) -> dict[str, Any]:
        """The journal lines this run holds that the six tables do not, counted and dated.

        The honest half of "the tables are the source of truth": between a degraded window
        and the sweep that closes it, an administrator counting this run's events from the
        tables alone would count too few, and the direction of the error is "it never
        happened". So the gap is reported with its own count and time range rather than
        folded into the durable answer as if it had come from there. It is empty as soon as
        ``backfill_fallback_journal`` has settled the lines, and it is the only place the
        events that can never reach the tables are named: the ones with no owner to
        attribute them to, and the ones whose id the tables already gave to a different
        event (see ``_event_in_tables``).
        """
        trace_id = trace_id_from_run_id(run_id)
        stamps: list[str] = []
        reasons: set[str] = set()
        unanswerable = 0
        for record in self._journal_records(tolerant=True):
            if record["kind"] != "event":
                continue
            event = record["event"]
            if str(event.get("trace_id") or "") != trace_id:
                continue
            marker = record.get("marker") or {}
            identity = self._event_identity(event, marker)
            if marker.get("sequence_proven") is False:
                # Out of the number book, so the rows in hand cannot name it: ask once. A
                # settled line is not a gap, and an unsettled one is not an answer the
                # tables will refuse either -- they only have to be asked again.
                if self._provisional_line_is_durable(identity):
                    continue
            held = durable.get(identity)
            if held == (str(event.get("event_type") or ""), str(event.get("status") or "")):
                continue
            stamps.append(str(event.get("timestamp") or ""))
            reason = str((record.get("marker") or {}).get("reason") or "")
            if reason:
                reasons.add(reason)
            owner_id = str((event.get("payload") or {}).get("owner_id") or "").strip()
            if not owner_id or held is not None:
                # Either nothing can own it, or its id is taken: the tables will not be
                # holding this event tomorrow either, and an operator is owed that
                # distinction rather than a number that keeps promising recovery.
                unanswerable += 1
        if not stamps:
            return {}
        stamps.sort()
        return {
            "name": LOCAL_FALLBACK_NAME,
            "events": len(stamps),
            "first_event_at": stamps[0],
            "last_event_at": stamps[-1],
            "reasons": sorted(reasons),
            "will_reach_tables": len(stamps) - unanswerable,
            "will_not_reach_tables": unanswerable,
        }

    def _run_events(self, run_id: str) -> list[dict[str, Any]]:
        """The fallback journal's events for one run's trace."""
        return [
            event
            for event in self._read_events()
            if event.get("trace_id") == trace_id_from_run_id(run_id)
        ]

    def _journal_records(self, *, tolerant: bool = False) -> list[dict[str, Any]]:
        """Read the fallback journal as typed lines rather than as a bag of events.

        A line is one of three things: an event the tables refused (from R257 on, carrying
        the ``fallback`` marker that says why and where the whole ledger lives), a receipt a
        settlement sweep appended, or a line that will not parse. Line numbers are physical
        and one-based, because an append-only journal never moves a line and a receipt has
        to name the ones it covered.

        ``tolerant`` is how a sweep reads: one torn line must not stop a thousand other
        events from reaching the tables. The read path is deliberately strict and raises,
        exactly as it did before, so a damaged journal is never quietly read as a shorter
        trace -- and the events it does return keep the eight-key contract, with neither a
        receipt nor a marker in them.
        """
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                if not tolerant:
                    raise
                records.append({"line": number, "kind": "unparsed", "event": None, "marker": {}})
                continue
            if not isinstance(record, dict):
                if not tolerant:
                    raise ValueError(f"journal line {number} is not a JSON object")
                records.append({"line": number, "kind": "unparsed", "event": None, "marker": {}})
                continue
            receipt = record.get(BACKFILL_RECEIPT_MARKER)
            if isinstance(receipt, dict):
                records.append(
                    {"line": number, "kind": "receipt", "event": None, "marker": {}, "receipt": receipt}
                )
                continue
            marker = record.get(FALLBACK_LINE_MARKER)
            records.append({
                "line": number,
                "kind": "event",
                "event": {key: value for key, value in record.items() if key != FALLBACK_LINE_MARKER},
                "marker": marker if isinstance(marker, dict) else {},
            })
        return records

    def _read_events(self) -> list[dict[str, Any]]:
        """The journal's event lines, in the shape the write side produces.

        Receipts are not events and a line's ``fallback`` marker is not part of an event, so
        both are filtered here: the journal is a page an operator reads, while ``replay`` and
        ``fold_events`` speak the trace-event contract.
        """
        return [record["event"] for record in self._journal_records() if record["kind"] == "event"]



def _is_sequence_collision(detail: str) -> bool:
    """Whether a failed write was the event id being taken, which is worth one retry."""
    text = str(detail or "").lower()
    return "duplicate key" in text or "unique" in text or "uq_trace" in text


def _merge_events(
    stored: list[dict[str, Any]], fallback: list[tuple[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Prefer the database rows, keep fallback events the database never received.

    ``fallback`` arrives paired with the address its line is recognised by -- the number for
    a confirmed line, the token for one R263 admitted the tables never confirmed. Keying both
    by the number printed on the line is what let a degraded window hide behind the row that
    had taken that number: the replay came back complete and the event in it was not this one.
    """
    merged = {identity: event for identity, event in fallback or []}
    for event in stored or []:
        merged[f"{event.get('trace_id')}:{event.get('sequence')}"] = event
    return list(merged.values())


_default_store: TraceStore | None = None
_default_lock = threading.Lock()


def default_trace_store() -> TraceStore:
    """Process-wide trace store used by every execution boundary."""
    global _default_store
    with _default_lock:
        if _default_store is None:
            import os

            _default_store = TraceStore(
                Path(os.getenv("TRACE_STORE_PATH", "./data/traces/events.jsonl")),
                persistence=build_persistence_adapter(),
            )
        return _default_store


def reset_default_trace_store() -> None:
    global _default_store
    with _default_lock:
        _default_store = None

