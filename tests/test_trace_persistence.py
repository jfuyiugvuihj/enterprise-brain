import json


def test_trace_store_persists_redacted_events_for_replay(tmp_path):
    from app.trace.store import TraceStore

    store = TraceStore(tmp_path / "traces.jsonl")

    first = store.record_event(
        trace_id="trace-1",
        request_id="req-1",
        event_type="model.started",
        status="running",
        payload={"model": "qwen", "token": "secret-token"},
    )
    second = store.record_event(
        trace_id="trace-1",
        request_id="req-1",
        event_type="retrieval.completed",
        status="completed",
        payload={"hits": [{"source": "policy.pdf", "score": 0.92}]},
    )

    assert first["sequence"] == 1
    assert second["sequence"] == 2

    lines = [
        json.loads(line)
        for line in (tmp_path / "traces.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert lines[0]["payload"]["token"] == "[REDACTED]"

    replay = store.replay("trace-1")
    assert [event["event_type"] for event in replay] == [
        "model.started",
        "retrieval.completed",
    ]
    assert replay[1]["payload"]["hits"][0]["source"] == "policy.pdf"


def test_trace_store_rejects_events_without_trace_or_request_id(tmp_path):
    from app.trace.store import TraceStore, TraceStoreError

    store = TraceStore(tmp_path / "traces.jsonl")

    for kwargs in (
        {"trace_id": "", "request_id": "req-1"},
        {"trace_id": "trace-1", "request_id": ""},
    ):
        try:
            store.record_event(
                event_type="tool.completed",
                status="completed",
                payload={},
                **kwargs,
            )
        except TraceStoreError as exc:
            assert exc.code == "validation_error"
        else:
            raise AssertionError("trace events require stable identifiers")


def test_trace_store_uses_explicit_owner_id_for_persistence(tmp_path):
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace.store import TraceStore

    persistence = JsonPersistenceAdapter(tmp_path / "records.json")
    store = TraceStore(tmp_path / "traces.jsonl", persistence=persistence)

    store.record_event(
        trace_id="trace-owner",
        request_id="req-owner",
        event_type="request.started",
        status="running",
        payload={"owner_id": "principal-7"},
    )

    persisted = persistence.get("trace_events", "trace-owner:1")
    assert persisted is not None
    assert persisted["owner_id"] == "principal-7"


def test_trace_store_persists_structured_execution_records(tmp_path):
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace.store import TraceStore

    persistence = JsonPersistenceAdapter(tmp_path / "records.json")
    store = TraceStore(tmp_path / "traces.jsonl", persistence=persistence)

    store.record_event(
        trace_id="trace-structured",
        request_id="req-structured",
        task_id="task-structured",
        event_type="request.started",
        status="running",
        payload={"owner_id": "principal-7", "session_id": "session-7"},
    )
    store.record_event(
        trace_id="trace-structured",
        request_id="req-structured",
        task_id="task-structured",
        event_type="tool.completed",
        status="completed",
        payload={"owner_id": "principal-7", "worker": "doc", "result_length": 23},
    )
    store.record_event(
        trace_id="trace-structured",
        request_id="req-structured",
        task_id="task-structured",
        event_type="retrieval.completed",
        status="completed",
        payload={
            "owner_id": "principal-7",
            "query_hash": "1" * 64,
            "index_version_id": "index-v1",
            "hits": [{"source": "policy.pdf"}],
        },
    )
    store.record_event(
        trace_id="trace-structured",
        request_id="req-structured",
        task_id="task-structured",
        event_type="request.completed",
        status="completed",
        payload={"owner_id": "principal-7", "worker_count": 1},
    )

    run = persistence.get("agent_runs", "trace-structured:orchestrator")
    assert run["status"] == "completed"
    assert run["owner_id"] == "principal-7"
    assert run["session_id"] == "session-7"

    step = persistence.get("agent_steps", "trace-structured:2")
    assert step["worker"] == "doc"
    assert step["status"] == "completed"

    tool = persistence.get("tool_calls", "trace-structured:2:doc")
    assert tool["result_summary"] == {"result_length": 23}

    retrieval = persistence.get("retrieval_traces", "trace-structured:3")
    assert retrieval["query_hash"] == "1" * 64
    assert retrieval["result_summary"]["hit_count"] == 1


def test_trace_store_does_not_invent_an_owner_for_persistence(tmp_path):
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace.store import TraceStore

    persistence = JsonPersistenceAdapter(tmp_path / "records.json")
    store = TraceStore(tmp_path / "traces.jsonl", persistence=persistence)

    store.record_event(
        trace_id="trace-no-owner",
        request_id="req-no-owner",
        event_type="request.started",
        status="running",
        payload={},
    )

    assert persistence.get("trace_events", "trace-no-owner:1") is None
