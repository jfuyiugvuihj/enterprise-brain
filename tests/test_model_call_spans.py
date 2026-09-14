"""Live model boundary: shared concurrency budget and model-call span records."""

import threading
import time

import pytest


@pytest.fixture(autouse=True)
def _fresh_budget():
    from app.common import model_budget

    model_budget.reset_default_budget()
    yield
    model_budget.reset_default_budget()


class _HoldingThread:
    """Hold a budget slot from another execution context."""

    def __init__(self, budget):
        self._budget = budget
        self._acquired = threading.Event()
        self._release = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self._acquired.wait(2)

    def _run(self):
        slot = self._budget.acquire(wait_seconds=2)
        self._acquired.set()
        self._release.wait(5)
        slot.release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._release.set()
        self._thread.join(2)


def _trace_store(tmp_path):
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace.store import TraceStore

    return TraceStore(
        tmp_path / "spans.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / "spans.json"),
    )


def test_budget_serializes_calls_beyond_configured_concurrency(monkeypatch):
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    from app.common.model_budget import default_model_budget

    budget = default_model_budget()

    with _HoldingThread(budget):
        with pytest.raises(RuntimeError) as excinfo:
            budget.acquire(wait_seconds=0)
        assert getattr(excinfo.value, "code", "") == "rate_limited"

    with budget.acquire(wait_seconds=0):
        pass


def test_budget_waits_for_a_slot_and_reports_queue_wait(monkeypatch):
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    from app.common.model_budget import default_model_budget

    budget = default_model_budget()

    with _HoldingThread(budget) as holder:

        def release_later():
            time.sleep(0.05)
            holder._release.set()

        threading.Thread(target=release_later).start()
        with budget.acquire(wait_seconds=2) as slot:
            assert slot.wait_ms >= 40


def test_budget_still_serializes_a_second_call_from_the_same_context(monkeypatch):
    """The cap is machine-wide: holding a slot never grants a second one."""
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    from app.common.model_budget import default_model_budget

    budget = default_model_budget()
    held = budget.acquire(wait_seconds=0)
    try:
        with pytest.raises(RuntimeError) as excinfo:
            budget.acquire(wait_seconds=0)
        assert getattr(excinfo.value, "code", "") == "rate_limited"
    finally:
        held.release()
    with budget.acquire(wait_seconds=0) as slot:
        assert slot.wait_ms == 0


def test_resilient_model_records_model_call_span(tmp_path, monkeypatch):
    from app.agents.contracts import Principal
    from app.agents.nodes import _ResilientModel
    from app.trace import spans

    store = _trace_store(tmp_path)
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)

    config = {
        "configurable": {
            "principal": Principal(user_id="u-9", username="staff9", roles=["staff"]),
            "request_id": "req-9",
            "trace_id": "trace-9",
            "task_id": "task-9",
            "worker": "doc",
            "step_id": "trace-9:worker:doc",
        }
    }

    class _Reply:
        content = "answer"
        usage_metadata = {"input_tokens": 11, "output_tokens": 7}

    class _Primary:
        model_name = "qwen2.5:14b"

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None, **kwargs):
            return _Reply()

    class _NeverOffline:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None, **kwargs):
            raise AssertionError("offline model must not be used")

    reply = _ResilientModel(_Primary(), _NeverOffline()).invoke([], config=config)
    assert reply.content == "answer"

    rows = store.persistence.list("model_calls")
    assert len(rows) == 1
    row = rows[0]
    assert row["owner_id"] == "u-9"
    assert row["status"] == "completed"
    assert row["model_name"] == "qwen2.5:14b"
    assert row["input_tokens"] == 11
    assert row["output_tokens"] == 7
    assert row["agent_run_id"] == "trace-9:orchestrator"
    assert row["agent_step_id"] == "trace-9:worker:doc"
    assert row["duration_ms"] >= 0


def test_resilient_model_records_fallback_as_model_unavailable(tmp_path, monkeypatch):
    from app.agents.contracts import Principal
    from app.agents.nodes import _ResilientModel
    from app.trace import spans

    store = _trace_store(tmp_path)
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)

    config = {
        "configurable": {
            "principal": Principal(user_id="u-8", username="staff8", roles=["staff"]),
            "request_id": "req-8",
            "trace_id": "trace-8",
            "task_id": "task-8",
        }
    }

    class _BrokenPrimary:
        model_name = "qwen2.5:14b"

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None, **kwargs):
            raise RuntimeError("connection refused")

    class _OfflineReply:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None, **kwargs):
            return type("Reply", (), {"content": "离线模式已启用"})()

    reply = _ResilientModel(_BrokenPrimary(), _OfflineReply()).invoke([], config=config)
    assert "离线" in (reply.content or "")

    rows = {(row['provider'], row['status']): row for row in store.persistence.list('model_calls')}
    assert set(rows) == {('local', 'failed'), ('offline', 'model_unavailable')}
    assert rows[('local', 'failed')]['error_code'] == 'internal_error'
    assert rows[('offline', 'model_unavailable')]['error_code'] == 'model_unavailable'


def test_model_span_requires_an_authenticated_owner(tmp_path, monkeypatch):
    from app.trace import spans

    store = _trace_store(tmp_path)
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)

    span = spans.start_model_call({}, provider="local", model_name="qwen2.5:14b")
    span.finish(status="completed")

    assert store.persistence.list("model_calls") == []


def test_model_span_reports_capacity_exhaustion(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    from app.agents.nodes import _ResilientModel
    from app.common.model_budget import default_model_budget
    from app.trace import spans

    store = _trace_store(tmp_path)
    monkeypatch.setattr(spans, "default_trace_store", lambda: store)

    config = {
        "configurable": {
            "principal": {"user_id": "u-7", "username": "staff7"},
            "request_id": "req-7",
            "trace_id": "trace-7",
            "task_id": "task-7",
        }
    }

    class _Primary:
        model_name = "qwen2.5:14b"

        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None, **kwargs):
            raise AssertionError("must not be called while the budget is exhausted")

    class _OfflineReply:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages, config=None, **kwargs):
            return type("Reply", (), {"content": "离线模式已启用"})()

    with _HoldingThread(default_model_budget()):
        reply = _ResilientModel(
            _Primary(), _OfflineReply(), capacity_wait_seconds=0
        ).invoke([], config=config)

    assert "离线" in (reply.content or "")
    rows = {(row['provider'], row['status']): row for row in store.persistence.list('model_calls')}
    assert set(rows) == {('local', 'rate_limited'), ('offline', 'model_unavailable')}
    assert rows[('local', 'rate_limited')]['error_code'] == 'rate_limited'
    assert rows[('local', 'rate_limited')]['queue_wait_ms'] >= 0
