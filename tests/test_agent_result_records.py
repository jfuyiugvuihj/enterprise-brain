"""Canonical AgentResult records produced by the worker and tool boundaries."""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage


@pytest.fixture
def trace_store(tmp_path, monkeypatch):
    from app.storage.persistence import JsonPersistenceAdapter
    from app.trace.store import TraceStore

    store = TraceStore(
        tmp_path / "events.jsonl",
        persistence=JsonPersistenceAdapter(tmp_path / "records.json"),
    )
    import app.agents.orchestrator as orchestrator

    monkeypatch.setattr(orchestrator, "_trace_store", store)
    from app.trace import spans

    monkeypatch.setattr(spans, "default_trace_store", lambda: store)
    return store


def _principal():
    from app.agents.contracts import Principal

    return Principal(user_id="u-1", username="staff1", roles=["staff"], department="研发部")


def test_worker_wrapper_records_agent_result_and_evidence(trace_store):
    from app.agents.evidence import record_document_hits
    from app.agents.orchestrator import _make_worker_wrapper

    def fake_graph(state, config=None):
        bag = config["configurable"]["evidence_bag"]
        record_document_hits(
            bag,
            query="住宿费标准",
            hits=[
                {
                    "content": "员工出差住宿标准每晚上限为制度规定金额。",
                    "source": "差旅费报销制度.pdf",
                    "chunk_index": 3,
                    "_score": 0.82,
                    "classification": 2,
                    "department": "研发部",
                }
            ],
        )
        return {"messages": [AIMessage(content="住宿费上限 500 元/晚。来源：差旅费报销制度.pdf")]}

    fake_graph.invoke = fake_graph  # the wrapper calls graph.invoke(...)
    wrapper = _make_worker_wrapper(fake_graph, "doc")
    state = {"messages": [HumanMessage(content="住宿费标准是多少？")], "worker_results": {}}
    config = {
        "configurable": {
            "thread_id": "session-1",
            "principal": _principal(),
            "request_id": "req-1",
            "trace_id": "trace-1",
            "task_id": "task-1",
        }
    }

    update = wrapper(state, config)

    answer = update["worker_results"]["doc"]
    assert isinstance(answer, str) and "500" in answer
    record = update["agent_results"]["doc"]
    assert record["worker"] == "doc"
    assert record["status"] == "success"
    assert record["request_id"] == "req-1"
    assert record["trace_id"] == "trace-1"
    assert record["task_id"] == "task-1"
    assert record["duration_ms"] >= 0
    assert record["confidence_label"] == "引用充分"
    assert record["evidence"][0]["source_name"] == "差旅费报销制度.pdf"
    assert record["evidence"][0]["permission_checked"] is True
    assert record["evidence"][0]["provenance_status"] == "verified"

    events = [json.loads(line) for line in trace_store.path.read_text(encoding="utf-8").splitlines()]
    assert [event["event_type"] for event in events] == ["step.started", "step.finished"]

    step = trace_store.persistence.get("agent_steps", "trace-1:worker:doc")
    assert step["worker"] == "doc"
    assert step["status"] == "completed"
    assert step["output_summary"]["evidence_count"] == 1


def test_worker_without_any_tool_becomes_partial_not_success(trace_store):
    from app.agents.orchestrator import _make_worker_wrapper

    class _Chatty:
        def invoke(self, state, config=None):
            return {"messages": [AIMessage(content="我认为可以直接批准。")]}

    wrapper = _make_worker_wrapper(_Chatty(), "data")
    update = wrapper(
        {"messages": [HumanMessage(content="哪个部门利润最高？")], "worker_results": {}},
        {
            "configurable": {
                "thread_id": "s2",
                "principal": _principal(),
                "request_id": "req-2",
                "trace_id": "trace-2",
                "task_id": "task-2",
            }
        },
    )

    record = update["agent_results"]["data"]
    assert record["status"] == "partial"
    assert record["confidence_label"] == "引用不足"
    assert record["warnings"]


def test_unavailable_model_is_reported_as_model_unavailable_not_an_answer(trace_store):
    from app.agents.orchestrator import _make_worker_wrapper

    class _ModelDown:
        def invoke(self, state, config=None):
            from app.agents.evidence import bag_from_config, record_model_status

            record_model_status(bag_from_config(config), "model_unavailable")
            return {"messages": [AIMessage(content="离线模式：模型不可用（error_code=model_unavailable）")]}

    wrapper = _make_worker_wrapper(_ModelDown(), "doc")
    update = wrapper(
        {"messages": [HumanMessage(content="制度问题")], "worker_results": {}},
        {
            "configurable": {
                "thread_id": "s3",
                "principal": _principal(),
                "request_id": "req-3",
                "trace_id": "trace-3",
                "task_id": "task-3",
            }
        },
    )

    record = update["agent_results"]["doc"]
    assert record["status"] == "model_unavailable"
    assert record["error"]["code"] == "model_unavailable"
    assert record["error"]["retryable"] is True


def test_search_docs_records_real_evidence_and_tool_span(trace_store, monkeypatch):
    from app.agents import tools
    from app.agents.evidence import new_evidence_bag

    class _Pipeline:
        def search_for_principal(self, query, principal, top_k=5):
            return (
                [
                    {
                        "content": "报销需要发票。",
                        "source": "报销制度.docx",
                        "chunk_index": 1,
                        "_score": 0.5,
                        "classification": 2,
                        "department": "研发部",
                    }
                ],
                ["发票"],
            )

    monkeypatch.setattr(tools, "_get_pipeline", lambda: _Pipeline())
    config = {
        "configurable": {
            "principal": _principal(),
            "request_id": "req-t",
            "trace_id": "trace-t",
            "task_id": "task-t",
            "worker": "doc",
            "step_id": "trace-t:worker:doc",
            "evidence_bag": new_evidence_bag(),
        }
    }

    text = tools.search_docs.invoke({"query": "报销"}, config=config)
    assert "报销制度.docx" in text

    bag = config["configurable"]["evidence_bag"]
    assert bag["documents"][0]["source_name"] == "报销制度.docx"
    assert bag["tool_statuses"][0]["tool"] == "search_docs"

    rows = trace_store.persistence.list("tool_calls")
    assert [row["tool_name"] for row in rows] == ["search_docs"]
    assert rows[0]["status"] == "completed"
    assert rows[0]["owner_id"] == "u-1"
    assert rows[0]["agent_step_id"] == "trace-t:worker:doc"
    assert rows[0]["result_summary"]["hit_count"] == 1


def test_search_docs_denied_without_identity_records_rejection(trace_store, monkeypatch):
    from app.agents import tools
    from app.agents.evidence import new_evidence_bag

    config = {"configurable": {"evidence_bag": new_evidence_bag()}}

    text = tools.search_docs.invoke({"query": "报销"}, config=config)

    assert "authorization_required" in text
    bag = config["configurable"]["evidence_bag"]
    assert bag["tool_statuses"][0]["status"] == "rejected"


def test_agent_results_feed_the_critic_review(trace_store):
    from app.agents.nodes import reflect_node

    state = {
        "messages": [HumanMessage(content="住宿费标准？")],
        "agent_results": {
            "doc": {
                "worker": "doc",
                "status": "success",
                "answer": "500 元/晚",
                "evidence": [
                    {
                        "source_type": "document",
                        "source_name": "差旅费报销制度.pdf",
                        "excerpt": "每晚上限 500 元",
                        "permission_checked": True,
                        "provenance_status": "verified",
                    }
                ],
            }
        },
        "worker_results": {"doc": "500 元/晚"},
        "final_answer": "500 元/晚",
        "retry_count": 0,
        "reflect_count": 0,
    }

    update = reflect_node(state)

    assert update["review_result"]["passed"] is True
    assert update["redo"] is False


def test_critic_retries_a_worker_that_failed_for_real(trace_store):
    from app.agents.nodes import reflect_node

    state = {
        "messages": [HumanMessage(content="分析一下数据")],
        "agent_results": {
            "data": {
                "worker": "data",
                "status": "model_unavailable",
                "answer": "离线模式：模型不可用（error_code=model_unavailable）",
                "error": {"code": "model_unavailable", "message": "model down", "retryable": True},
            }
        },
        "worker_results": {"data": "离线模式：模型不可用"},
        "final_answer": "离线模式：模型不可用",
        "retry_count": 0,
        "reflect_count": 0,
    }

    update = reflect_node(state)

    assert update["review_result"]["passed"] is False
    assert update["redo"] is True
    assert update["retry_count"] == 1


def test_queue_records_canonical_agent_result(monkeypatch):
    import deploy.queue_worker as worker

    recorded = {}
    completed = {}

    class _Queue:
        def complete(self, request_id, result):
            completed["request_id"] = request_id
            completed["result"] = result
            return True

        def reserve(self, timeout=0):
            return type(
                "Message",
                (),
                {
                    "request_id": "req-q",
                    "payload": {
                        "message": "住宿费标准",
                        "session_id": "s-q",
                        "principal": {"user_id": "u-q", "username": "staffq"},
                    },
                },
            )()

    result = {
        "worker": "orchestrator",
        "status": "success",
        "answer": "住宿费上限 500 元/晚。",
        "request_id": "req-q",
        "trace_id": "trace-q",
        "task_id": "task-q",
        "evidence": [],
        "duration_ms": 12,
    }

    monkeypatch.setattr(worker, "_get_queue", lambda: _Queue())
    monkeypatch.setattr(
        "app.agents.orchestrator.run_orchestrator_result",
        lambda message, **kwargs: type(
            "R",
            (),
            {"model_dump": staticmethod(lambda: result), "answer": result["answer"]},
        )(),
    )
    monkeypatch.setattr(worker, "record_agent_result", lambda record, **kwargs: recorded.update(record))

    assert worker.process_one() is True
    assert completed["result"] == "住宿费上限 500 元/晚。"
    assert recorded["status"] == "success"
    assert recorded["request_id"] == "req-q"