"""Route-level authorization for the remaining business intelligence resources."""

import asyncio
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.agents.contracts import Principal


def _principal(username: str, *, role="staff", department="研发部", permissions=None, **overrides):
    from app.common.permissions import ROLE_PERMISSIONS
    from app.common.rbac import clearance_for

    data = {
        "user_id": f"u-{username}",
        "username": username,
        "roles": [role],
        "permissions": sorted(
            ROLE_PERMISSIONS[role] if permissions is None else permissions
        ),
        "department": department,
        "clearance": clearance_for(role),
    }
    data.update(overrides)
    return Principal(**data)


def _request(principal):
    state = type("State", (), {"principal": principal, "username": getattr(principal, "username", "")})()
    return type("Request", (), {"state": state})()


def _call(coroutine):
    return asyncio.run(coroutine)


def test_dashboard_requires_an_analyze_permission():
    from app.api.v1.intelligence import DashboardRequest, dashboard

    restricted = _principal("no-perms", permissions=[])
    with pytest.raises(HTTPException) as excinfo:
        _call(dashboard(DashboardRequest(rows=[{"value": 1}], insights=[]), _request(restricted)))
    assert excinfo.value.status_code == 403

    payload = DashboardRequest(rows=[{"department": "研发部", "metric": "费用", "value": 10}], insights=[])
    result = _call(dashboard(payload, _request(_principal("analyst"))))
    assert result["metrics"]["费用"]["total"] == 10


def test_dashboard_requires_a_principal():
    from app.api.v1.intelligence import DashboardRequest, dashboard

    with pytest.raises(HTTPException) as excinfo:
        _call(dashboard(DashboardRequest(rows=[], insights=[]), _request(None)))
    assert excinfo.value.status_code == 401


def test_insight_detection_requires_an_analyze_permission():
    from app.api.v1.intelligence import InsightsRequest, insights_detect

    restricted = _principal("viewer", permissions=["resource:view"])
    with pytest.raises(HTTPException) as excinfo:
        _call(
            insights_detect(
                InsightsRequest(rows=[{"current": 130, "previous": 100, "threshold": 120}]),
                _request(restricted),
            )
        )
    assert excinfo.value.status_code == 403


def test_approval_precheck_uses_decimal_money_and_never_approves():
    from app.api.v1.intelligence import ApprovalRequest, approval_precheck

    result = _call(
        approval_precheck(
            ApprovalRequest(
                amount=Decimal("650.50"),
                standard=Decimal("500"),
                department="研发部",
                expense_type="住宿费",
                evidence=["差旅费报销制度.pdf 第3页"],
            ),
            _request(_principal("manager", role="manager")),
        )
    )

    assert result["approved"] is False
    assert Decimal(str(result["excess_amount"])) == Decimal("150.50")
    assert Decimal(str(result["amount"])) == Decimal("650.50")
    assert result["currency"]
    assert result["requested_by"] == "u-manager"


def test_knowledge_graph_relations_are_owner_scoped():
    from app.api.v1 import intelligence
    from app.knowledge_graph.service import KnowledgeGraph

    graph = KnowledgeGraph()
    intelligence._graph = graph

    author = _principal("author", department="研发部")
    stranger = _principal("stranger", department="市场部")

    created = _call(
        intelligence.add_relation(
            intelligence.RelationRequest(
                source_entity="差旅制度",
                relation="规定",
                target="住宿上限",
                source="差旅费报销制度.pdf 第3页",
            ),
            _request(author),
        )
    )
    assert created["status"] == "candidate"
    assert created["owner_id"]

    visible = _call(intelligence.list_relations(None, None, _request(author)))
    assert [item["relation_id"] for item in visible["relations"]] == [created["relation_id"]]

    other = _call(intelligence.list_relations(None, None, _request(stranger)))
    assert other["relations"] == []


def test_knowledge_graph_write_requires_upload_permission():
    from app.api.v1 import intelligence

    restricted = _principal("viewer", permissions=["resource:view"])
    with pytest.raises(HTTPException) as excinfo:
        _call(
            intelligence.add_relation(
                intelligence.RelationRequest(
                    source_entity="a", relation="b", target="c", source="doc.pdf 第1页"
                ),
                _request(restricted),
            )
        )
    assert excinfo.value.status_code == 403


def test_knowledge_graph_rejects_a_relation_without_a_source():
    from app.api.v1 import intelligence

    with pytest.raises(HTTPException) as excinfo:
        _call(
            intelligence.add_relation(
                intelligence.RelationRequest(source_entity="a", relation="b", target="c", source="   "),
                _request(_principal("author")),
            )
        )
    assert excinfo.value.status_code == 400


def test_provenance_summary_flags_client_supplied_results_as_unverified():
    from app.api.v1 import intelligence

    result = _call(
        intelligence.provenance_summary(
            intelligence.ProvenanceRequest(
                results=[
                    {
                        "worker": "doc",
                        "status": "success",
                        "answer": "500 元/晚",
                        "evidence": [{"source_type": "document", "source_name": "制度.pdf"}],
                    }
                ]
            ),
            _request(_principal("auditor", role="auditor")),
        )
    )

    assert result["workers"] == ["doc"]
    assert result["provenance_source"] == "client_provided"
    assert result["server_verified"] is False


def test_semantics_match_reports_definition_provenance():
    from app.api.v1 import intelligence

    result = _call(intelligence.semantics_match(intelligence.SemanticRequest(question="住宿费标准"), _request(_principal("staff"))))

    context = result["context"]
    assert context["metric_name"] == "住宿费标准"
    assert context["definition_version"]
    assert context["timezone"]
    assert any("未与已上传制度文件核对" in warning for warning in context["warnings"])