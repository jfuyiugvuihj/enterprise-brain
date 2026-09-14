import asyncio
import json


class _FakeGraph:
    def __init__(self):
        self.config = None
        self.state = None

    def stream(self, state, config, **_kwargs):
        self.state = state
        self.config = config
        yield {"messages": [], "worker_results": {}}
        yield {
            "messages": [],
            "worker_results": {"doc": "Authorized document answer."},
            "final_answer": "Authorized document answer.",
        }


def test_streamed_orchestration_persists_ordered_lifecycle_trace(tmp_path, monkeypatch):
    from app.agents import orchestrator
    from app.trace.store import TraceStore

    graph = _FakeGraph()
    store = TraceStore(tmp_path / "traces.jsonl")
    monkeypatch.setattr(orchestrator, "multi_agent_graph", graph)

    events = list(
        orchestrator.run_with_stream(
            "What is the approved travel policy?",
            thread_id="session-1",
            user={"username": "alice", "department": "finance"},
            request_id="request-1",
            trace_id="trace-1",
            task_id="task-1",
            trace_store=store,
        )
    )

    assert len(events) == 2
    assert graph.config["configurable"]["request_id"] == "request-1"
    assert graph.config["configurable"]["trace_id"] == "trace-1"
    assert graph.config["configurable"]["task_id"] == "task-1"
    assert graph.state["request_id"] == "request-1"
    assert graph.state["trace_id"] == "trace-1"
    assert graph.state["task_id"] == "task-1"

    replay = store.replay("trace-1")
    assert [event["event_type"] for event in replay] == [
        "request.started",
        "step.progress",
        "step.progress",
        "tool.completed",
        "request.completed",
    ]
    assert [event["sequence"] for event in replay] == [1, 2, 3, 4, 5]
    assert replay[3]["payload"]["worker"] == "doc"
    assert replay[-1]["status"] == "completed"
    assert all(
        event["payload"].get("owner_id") == "alice"
        for event in replay
    )


def test_ask_passes_one_stable_trace_context_to_orchestration(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.common.identity import Principal
    from app.storage.sessions import SessionRegistry

    observed = {}
    principal = Principal.from_user(
        {"id": "alice", "username": "alice", "role": "manager", "department": "finance"}
    )
    http_request = type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": "alice"})()},
    )()

    def fake_stream(*_args, **kwargs):
        observed.update(kwargs)
        yield {
            "messages": [],
            "worker_results": {"doc": "Authorized document answer."},
            "final_answer": "Authorized document answer.",
        }

    async def consume(response):
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return "".join(parts)

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}))
    monkeypatch.setattr(
        "app.common.cache.check_rate_limit",
        lambda *_args, **_kwargs: (True, 9),
    )
    monkeypatch.setattr(
        "app.common.cache.get_cached_answer",
        lambda _question: None,
    )
    monkeypatch.setattr(
        "app.common.cache.cache_answer",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    response = asyncio.run(
        chat.ask(
            chat.AskRequest(
                message="What is the approved travel policy?",
                session_id="trace-session",
            ),
            http_request=http_request,
        )
    )
    body = asyncio.run(consume(response))

    assert observed["thread_id"] == "trace-session"
    assert observed["request_id"]
    assert observed["trace_id"]
    assert observed["task_id"]
    assert "event: done" in body


def test_ask_emits_canonical_start_and_terminal_events(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.common.identity import Principal
    from app.storage.sessions import SessionRegistry

    principal = Principal.from_user(
        {"id": "alice", "username": "alice", "role": "manager", "department": "finance"}
    )
    http_request = type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": "alice"})()},
    )()

    def fake_stream(*_args, **_kwargs):
        yield {
            "messages": [],
            "worker_results": {"doc": "Authorized document answer."},
            "final_answer": "Authorized document answer.",
        }

    async def consume(response):
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk)
        return "".join(parts)

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}))
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_args, **_kwargs: (True, 9))
    monkeypatch.setattr("app.common.cache.get_cached_answer", lambda _question: None)
    monkeypatch.setattr("app.common.cache.cache_answer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    response = asyncio.run(
        chat.ask(
            chat.AskRequest(
                message="What is the approved travel policy?",
                session_id="canonical-trace-session",
            ),
            http_request=http_request,
        )
    )
    body = asyncio.run(consume(response))

    payloads = {}
    for block in body.split("\n\n"):
        lines = block.splitlines()
        if len(lines) < 2 or not lines[0].startswith("event: request."):
            continue
        payloads[lines[0].removeprefix("event: ")] = json.loads(
            lines[1].removeprefix("data: ")
        )

    started = payloads["request.started"]
    completed = payloads["request.completed"]
    assert started["status"] == "running"
    assert completed["status"] == "completed"
    assert started["request_id"] == completed["request_id"]
    assert started["trace_id"] == completed["trace_id"]
    assert started["task_id"] == completed["task_id"]
    assert [started["sequence"], completed["sequence"]] == [1, 2]
