"""The approval worker must derive its numbers, not invent them."""

from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.contracts import Principal


def _config(bag=None, principal=None):
    from app.agents.evidence import new_evidence_bag

    configurable = {
        "thread_id": "session-a",
        "request_id": "req-a",
        "trace_id": "trace-a",
        "task_id": "task-a",
        "evidence_bag": bag if bag is not None else new_evidence_bag(),
    }
    if principal is not None:
        configurable["principal"] = principal
    return {"configurable": configurable}


def _patch_retrieval(monkeypatch, hits):
    class _Pipeline:
        def __init__(self):
            self.calls = []

        def search_for_principal(self, query, principal, top_k=5):
            self.calls.append(query)
            return hits, []

    pipeline = _Pipeline()
    import app.agents.tools as tools

    monkeypatch.setattr(tools, "_get_pipeline", lambda: pipeline)
    return pipeline


def test_missing_amount_produces_a_failure_record_not_a_conclusion(monkeypatch):
    from app.agents.orchestrator import _approval_worker_node

    _patch_retrieval(monkeypatch, [])
    principal = Principal(
        user_id="u-5",
        username="staff5",
        roles=["staff"],
        permissions=["resource:view"],
        department="研发部",
        clearance=1,
    )
    state = {"messages": [HumanMessage(content="这笔住宿报销能批吗？")], "worker_results": {}, "agent_results": {}}

    update = _approval_worker_node(state, _config(principal=principal))

    record = update["agent_results"]["approval"]
    assert record["status"] == "failed"
    assert record["error"]["code"] == "validation_error"
    answer = update["worker_results"]["approval"]
    assert "600" not in answer and "500" not in answer
    assert "无法" in answer and "申请金额" in answer


def test_standard_is_taken_from_retrieved_policy_and_recorded_as_evidence(monkeypatch):
    from app.agents.orchestrator import _approval_worker_node

    hits = [
        {
            "content": "员工出差住宿费标准：每晚上限 500 元，超过部分需部门负责人审批。",
            "source": "差旅费报销制度.pdf",
            "chunk_index": 2,
            "_score": 0.91,
            "classification": 1,
            "department": "研发部",
        }
    ]
    pipeline = _patch_retrieval(monkeypatch, hits)
    principal = Principal(
        user_id="u-5",
        username="staff5",
        roles=["staff"],
        permissions=["resource:view"],
        department="研发部",
        clearance=1,
    )
    state = {
        "messages": [HumanMessage(content="住宿发票 20000 元，超过住宿费标准了吗？")],
        "worker_results": {},
        "agent_results": {},
        "department": "研发部",
    }

    update = _approval_worker_node(state, _config(principal=principal))

    record = update["agent_results"]["approval"]
    assert record["status"] == "success"
    assert pipeline.calls
    evidence = record["evidence"]
    assert evidence[0]["source_name"] == "差旅费报销制度.pdf"
    assert evidence[0]["permission_checked"] is True
    answer = update["worker_results"]["approval"]
    assert "20000" in answer
    assert record["metrics"][0]["metric_name"] == "住宿费标准"
    assert record["metrics"][0]["unit"] == "元/晚"
    assert record["metrics"][0]["definition_version"]
    assert "19500" in answer
    assert "需人工审批" in answer


def test_unauthorized_caller_retrieves_nothing(monkeypatch):
    from app.agents.orchestrator import _approval_worker_node

    pipeline = _patch_retrieval(monkeypatch, [])
    state = {
        "messages": [HumanMessage(content="住宿发票 20000 元是否超标")],
        "worker_results": {},
        "agent_results": {},
    }

    update = _approval_worker_node(state, _config(principal=None))

    record = update["agent_results"]["approval"]
    assert record["status"] == "rejected"
    assert record["error"]["code"] == "permission_denied"
    assert pipeline.calls == []