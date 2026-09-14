from app.agents.contracts import (
    AgentContext,
    AgentResult,
    ErrorEnvelope,
    Evidence,
    MetricContext,
    Principal,
    ResourceScope,
)


def test_public_contract_carries_identity_scope_versions_and_provenance():
    principal = Principal(
        user_id="u-1",
        username="alice",
        roles=["staff"],
        permissions=["document.read"],
        department_ids=["dept-a"],
        request_id="req-1",
    )
    scope = ResourceScope(
        resource_type="document",
        resource_id="doc-1",
        owner_id="u-1",
        department_ids=["dept-a"],
        version_id="doc-v2",
    )
    context = AgentContext(
        principal=principal,
        request_id="req-1",
        trace_id="trace-1",
        task_id="task-1",
        allowed_actions=["document.read"],
        allowed_resource_scope=[scope],
    )
    evidence = Evidence(
        source_type="document",
        source_id="doc-1",
        source_name="policy.pdf",
        document_version_id="doc-v2",
        index_version_id="idx-v3",
        locator={"page": 3, "chunk_id": "chunk-7"},
        score=0.91,
        score_type="rerank",
        permission_checked=True,
        provenance_status="verified",
    )
    result = AgentResult(
        worker="doc",
        status="success",
        task_id=context.task_id,
        request_id=context.request_id,
        trace_id=context.trace_id,
        answer="制度结论",
        evidence=[evidence],
        metrics=[
            MetricContext(
                metric_name="费用",
                definition="制度定义",
                definition_version="metric-v1",
                formula="sum(amount)",
                unit="CNY",
                period_type="month",
                timezone="Asia/Shanghai",
            )
        ],
    )

    assert context.principal.user_id == "u-1"
    assert context.allowed_resource_scope[0].version_id == "doc-v2"
    assert result.evidence[0].permission_checked is True
    assert result.evidence[0].locator["page"] == 3
    assert result.metrics[0].definition_version == "metric-v1"


def test_error_envelope_distinguishes_model_failure_from_business_answer():
    error = ErrorEnvelope(
        code="model_unavailable",
        message="local model is unavailable",
        retryable=True,
    )
    result = AgentResult(
        worker="doc",
        status="model_unavailable",
        error=error,
        warnings=["no business conclusion was generated"],
    )

    assert result.answer == ""
    assert result.error.code == "model_unavailable"
    assert result.status != "success"


def test_error_envelope_supports_queue_unavailability():
    error = ErrorEnvelope(
        code="queue_unavailable",
        message="reliable queue is unavailable",
        retryable=True,
    )

    assert error.code == "queue_unavailable"
