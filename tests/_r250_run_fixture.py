"""One production-shaped run, emitted through the trace store, with its write-side tally.

R250's first judgement is a number-matching exercise: whatever the write side put into the
six tables has to come back through the read side -- run, steps, tool calls, model calls --
so both the hermetic and the live-PostgreSQL tests need one emitter and one expectation.
Keeping them in a single module is what stops "the test that passed" from being a different
trace than the one the operator reads.

The shape mirrors the boundaries that actually exist: ``app/agents/orchestrator.py`` wraps
each worker in ``step.started`` / ``step.finished`` (step id ``{trace}:worker:{name}``, the
same id ``app/trace/spans.py:span_identity`` puts on every span), ``start_model_call`` and
``start_tool_call`` emit the ``*.started`` / ``*.finished`` pair, ``tool.completed`` is the
legacy worker boundary, and the request closes with ``request.completed``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

WORKERS = ("doc_agent", "data_agent")

#: A clock the emitter can move forward without sleeping: ``app/trace/spans.py`` stamps
#: ``started_at`` / ``first_token_at`` / ``completed_at`` on every finished span, and a test
#: that leaves them out would be testing a payload no boundary ever produces.
_T0 = datetime(2026, 9, 25, 10, 0, 0, tzinfo=timezone.utc)


def _iso_offset(milliseconds: int) -> str:
    return (_T0 + timedelta(milliseconds=int(milliseconds))).isoformat()


def emit_full_run(store: Any, *, trace: str, owner: str) -> dict[str, Any]:
    """Write one whole run through ``store.record_event`` and report what was written."""
    written: dict[str, list[str]] = {
        "trace_events": [],
        "agent_steps": [],
        "tool_calls": [],
        "model_calls": [],
        "retrieval_traces": [],
    }

    def record(event_type: str, status: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = {"owner_id": owner}
        body.update(payload or {})
        event = store.record_event(
            trace_id=trace,
            request_id=f"{trace}:req",
            task_id=f"{trace}:task",
            event_type=event_type,
            status=status,
            payload=body,
        )
        written["trace_events"].append(f"{trace}:{event['sequence']}")
        return event

    def step_ids(worker: str) -> str:
        return f"{trace}:worker:{worker}"

    record("request.started", "started", {"session_id": f"{trace}:session"})

    first = step_ids(WORKERS[0])
    record("step.started", "running", {
        "step_id": first, "worker": WORKERS[0], "sequence": 1,
        "input_summary": {"question_length": 42},
    })
    written["agent_steps"].append(first)
    model_one = f"{trace}:model:rewrite"
    record("model.started", "running", {
        "record_id": model_one, "agent_step_id": first, "worker": WORKERS[0],
        "provider": "ollama", "model_name": "qwen3:8b", "queue_wait_ms": 12,
    })
    written["model_calls"].append(model_one)
    record("model.finished", "completed", {
        "record_id": model_one, "agent_step_id": first, "provider": "ollama",
        "model_name": "qwen3:8b", "status": "completed", "duration_ms": 900,
        "first_token_at": _iso_offset(120), "completed_at": _iso_offset(900),
        "summary": {"input_tokens": 1200, "output_tokens": 240},
    })
    retrieval = {"hits": [1, 2, 3], "query_hash": "a" * 64, "index_version_id": "index-v1",
                 "filters": {"department": "finance"}}
    retrieval_event = record("retrieval.completed", "completed", retrieval)
    written["retrieval_traces"].append(f"{trace}:{retrieval_event['sequence']}")

    tool_one = f"{trace}:tool:search"
    record("tool_call.started", "running", {
        "record_id": tool_one, "agent_step_id": first, "tool_name": "search_documents",
    })
    written["tool_calls"].append(tool_one)
    record("tool_call.finished", "completed", {
        "record_id": tool_one, "agent_step_id": first, "tool_name": "search_documents",
        "status": "completed", "arguments": {"query": "revenue"},
        "completed_at": _iso_offset(300), "duration_ms": 300,
        "summary": {"hit_count": 3},
    })
    record("step.finished", "completed", {
        "step_id": first, "worker": WORKERS[0], "summary": {"answer_length": 512},
    })

    second = step_ids(WORKERS[1])
    record("step.started", "running", {
        "step_id": second, "worker": WORKERS[1], "sequence": 2,
        "input_summary": {"question_length": 42},
    })
    written["agent_steps"].append(second)
    model_two = f"{trace}:model:analysis"
    record("model.started", "running", {
        "record_id": model_two, "agent_step_id": second, "worker": WORKERS[1],
        "provider": "ollama", "model_name": "qwen3:8b",
    })
    written["model_calls"].append(model_two)
    record("model.finished", "completed", {
        "record_id": model_two, "agent_step_id": second, "provider": "ollama",
        "model_name": "qwen3:8b", "status": "completed", "duration_ms": 1_400,
        "first_token_at": _iso_offset(200), "completed_at": _iso_offset(1400),
        "summary": {"input_tokens": 2_000, "output_tokens": 600},
    })
    tool_two = f"{trace}:tool:analyze"
    record("tool_call.started", "running", {
        "record_id": tool_two, "agent_step_id": second, "tool_name": "analyze_dataset",
    })
    written["tool_calls"].append(tool_two)
    record("tool_call.finished", "completed", {
        "record_id": tool_two, "agent_step_id": second, "tool_name": "analyze_dataset",
        "status": "completed", "arguments": {"dataset": "sales.xlsx"},
        "completed_at": _iso_offset(600), "duration_ms": 600,
        "summary": {"rows": 240},
    })
    tool_three = f"{trace}:tool:chart"
    record("tool_call.started", "running", {
        "record_id": tool_three, "agent_step_id": second, "tool_name": "make_chart",
    })
    written["tool_calls"].append(tool_three)
    record("tool_call.finished", "failed", {
        "record_id": tool_three, "agent_step_id": second, "tool_name": "make_chart",
        "status": "failed", "error_code": "chart_generation_failed",
        "completed_at": _iso_offset(700), "duration_ms": 100,
    })

    record("step.finished", "completed", {
        "step_id": second, "worker": WORKERS[1], "summary": {"answer_length": 1_024},
    })

    legacy_sequence = len(written["trace_events"]) + 1
    legacy_step = f"{trace}:{legacy_sequence}"
    record("tool.completed", "completed", {"worker": WORKERS[0], "result_length": 512})
    assert legacy_step == written["trace_events"][-1], (legacy_step, written["trace_events"][-1])
    written["agent_steps"].append(legacy_step)
    written["tool_calls"].append(f"{legacy_step}:{WORKERS[0]}")

    record("request.completed", "completed", {"worker_count": 2, "has_final_answer": True})

    return {
        "run_id": f"{trace}:orchestrator",
        "trace_id": trace,
        "owner_id": owner,
        "written": written,
        "counts": {key: len(value) for key, value in written.items()},
        "written_retrieval_ids": written["retrieval_traces"],
    }
