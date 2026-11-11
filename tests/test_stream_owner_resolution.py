"""Owner resolution on the streaming chat path.

``/api/v1/ask`` hands ``run_with_stream`` a Principal model, while a queued task hands it a
serialized dict. A Principal is a model rather than a mapping, so the owner must be
resolved through the shared helper: assuming ``.get`` aborted every authenticated chat
before the graph was reached, and the SSE stream reported the internal error as the answer.
"""

import pytest


def _principal():
    from app.agents.contracts import Principal

    return Principal(user_id="u-1", username="staff1", roles=["staff"], department="R&D")


class _StubGraph:
    """Stand in for the compiled graph so the test never touches a live model."""

    def __init__(self):
        self.configs = []

    def stream(self, state, config, **kwargs):
        self.configs.append(config)
        yield {"worker_results": {"doc": "found"}, "final_answer": "found"}


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    from app.trace.store import TraceStore
    import app.agents.orchestrator as orchestrator

    store = TraceStore(tmp_path / "events.jsonl")
    monkeypatch.setattr(orchestrator, "_trace_store", store)
    return store


def _collect(monkeypatch, user, trace_id):
    import app.agents.orchestrator as orchestrator

    graph = _StubGraph()
    monkeypatch.setattr(orchestrator, "multi_agent_graph", graph)
    events = list(
        orchestrator.run_with_stream(
            "how much can I claim",
            thread_id="session-1",
            user=user,
            trace_id=trace_id,
        )
    )
    return events, graph


def test_principal_model_resolves_the_stream_owner(trace_store, monkeypatch):
    events, graph = _collect(
        monkeypatch, {"username": "staff1", "principal": _principal()}, "trace-model"
    )
    assert events
    assert [event for event in events if "error" in event] == []
    owners = {event["payload"].get("owner_id") for event in trace_store.replay("trace-model")}
    assert owners == {"u-1"}
    assert graph.configs[0]["configurable"]["principal"].user_id == "u-1"


def test_serialized_principal_resolves_the_same_stream_owner(trace_store, monkeypatch):
    principal = _principal()
    events, _graph = _collect(
        monkeypatch,
        {"username": "staff1", "principal": principal.model_dump(mode="json")},
        "trace-dict",
    )
    assert [event for event in events if "error" in event] == []
    owners = {event["payload"].get("owner_id") for event in trace_store.replay("trace-dict")}
    assert owners == {"u-1"}


def test_anonymous_stream_invents_no_owner(trace_store, monkeypatch):
    events, _graph = _collect(monkeypatch, None, "trace-anon")
    assert [event for event in events if "error" in event] == []
    replayed = trace_store.replay("trace-anon")
    assert replayed
    assert all("owner_id" not in event["payload"] for event in replayed)