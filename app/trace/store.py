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
"""

import json
import threading
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
    run_id_for,
)
from app.trace.run_reader import TraceDatabase, TraceDatabaseUnavailable, database_for
from app.trace.runs import assemble_run_readout, fold_events, trace_id_from_run_id
from app.trace.schema import TraceSchemaError


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
            event: dict[str, Any] = {}
            for attempt in range(attempts):
                event = self._build_event(
                    trace_id=trace_id,
                    request_id=request_id,
                    task_id=task_id,
                    event_type=event_type,
                    status=status,
                    payload=payload or {},
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
                reason, detail = self._persist(event, owner_id)
                if reason is None:
                    break
                if attempt == 0 and _is_sequence_collision(detail):
                    continue
                self._write_fallback(event, reason, detail)
                break
            self._observe_request_window(event)
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
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "request_id": request_id,
            "task_id": task_id,
            "sequence": self._next_sequence(trace_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": str(event_type or ""),
            "status": str(status or ""),
            "payload": sanitize_trace_event(payload or {}),
        }

    def _write_fallback(self, event: dict[str, Any], reason: str, detail: str) -> None:
        """Append one event to the local journal and say out loud that we had to."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        durability.note_local_fallback(
            reason, f"event_id={event['trace_id']}:{event['sequence']} {detail}"
        )

    def _persist(self, event: dict[str, Any], owner_id: str) -> tuple[str | None, str]:
        """Write one event and its rows to the configured backend.

        Returns ``(None, "")`` when the tables hold the whole event, and a
        ``(reason, detail)`` pair when they do not; the caller decides what the fallback
        journal has to keep.
        """
        if self.persistence is None:
            return REASON_BACKEND_NOT_POSTGRES, "no persistence adapter is configured"
        if not owner_id:
            return REASON_OWNER_MISSING, "trace events require an owner_id to reach the tables"
        try:
            self._apply(project_event_row(event, owner_id).seal())
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
            local = [event for event in self._read_events() if event.get("trace_id") == trace_id]
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
                    local = _merge_events(stored, local)
                return sorted(local, key=lambda event: int(event.get("sequence") or 0))
            try:
                events = self.database.fetch_events(trace_id)
            except TraceDatabaseUnavailable as exc:
                durability.note_local_read_fallback(exc.reason, str(exc))
                return sorted(local, key=lambda event: int(event.get("sequence") or 0))
            return sorted(
                _merge_events(events, local), key=lambda event: int(event.get("sequence") or 0)
            )

    @staticmethod
    def database_as_event(row: dict[str, Any]) -> dict[str, Any]:
        return TraceDatabase._as_event(row)

    def read_run(self, run_id: str) -> dict[str, Any]:
        """One run with its steps, tool calls and model calls, from the trace tables.

        Falls back to folding the local journal through the same projections when
        PostgreSQL cannot answer, and the returned document names which one it came from.
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
                        return assemble_run_readout(
                            run_id,
                            bundle,
                            source=POSTGRES_SOURCE,
                            durability_block=self.durability_status(),
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

    def _next_sequence(self, trace_id: str) -> int:
        """The next event sequence, taken from whichever ledger holds the higher one."""
        return max(self._postgres_sequence_floor(trace_id), self._file_sequence_floor(trace_id)) + 1

    def _postgres_sequence_floor(self, trace_id: str) -> int:
        """The highest event id PostgreSQL holds, or 0 when it cannot say.

        An unanswered sequence read is not counted as a fallback of its own: the event that
        is being built right now either reaches the tables (nothing was lost) or goes to the
        journal one statement later, and that write is what gets named. Naming both would
        double every degraded event in the ledger an operator reads.
        """
        if self.database is None:
            return 0
        try:
            return self.database.max_sequence(trace_id)
        except TraceDatabaseUnavailable:
            return 0

    def _file_sequence_floor(self, trace_id: str) -> int:
        events = [event for event in self._read_events() if event.get("trace_id") == trace_id]
        if not events:
            return 0
        return max(int(event.get("sequence") or 0) for event in events)

    def _run_events(self, run_id: str) -> list[dict[str, Any]]:
        """The fallback journal's events for one run's trace."""
        return [
            event
            for event in self._read_events()
            if event.get("trace_id") == trace_id_from_run_id(run_id)
        ]

    def _read_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events



def _is_sequence_collision(detail: str) -> bool:
    """Whether a failed write was the event id being taken, which is worth one retry."""
    text = str(detail or "").lower()
    return "duplicate key" in text or "unique" in text or "uq_trace" in text


def _merge_events(
    stored: list[dict[str, Any]], fallback: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Prefer the database rows, keep fallback events the database never received."""
    merged = {
        f"{event.get('trace_id')}:{event.get('sequence')}": event for event in fallback or []
    }
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

