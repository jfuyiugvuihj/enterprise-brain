from fastapi.testclient import TestClient
from app.main import app
from app.common.auth import create_token

client = TestClient(app)


def headers(username="admin"):
    return {"Authorization": f"Bearer {create_token(username)}"}


def test_dashboard_endpoint_returns_aggregated_view():
    response = client.post("/api/v1/dashboard", json={"rows": [{"department": "市场部", "metric": "费用", "value": 10}], "insights": []}, headers=headers())
    assert response.status_code == 200
    assert response.json()["metrics"]["费用"]["total"] == 10


def test_insights_endpoint_returns_detected_anomalies():
    response = client.post("/api/v1/insights/detect", json={"rows": [{"department": "市场部", "metric": "费用", "current": 130, "previous": 100, "threshold": 120}]}, headers=headers())
    assert response.status_code == 200
    assert response.json()["insights"][0]["department"] == "市场部"


def test_approval_endpoint_never_auto_approves():
    response = client.post("/api/v1/approval/precheck", json={"amount": 600, "standard": 500, "department": "市场部", "expense_type": "住宿费", "evidence": ["制度.pdf"]}, headers=headers())
    assert response.status_code == 200
    assert response.json()["approved"] is False


def test_graph_endpoint_returns_source_backed_relation():
    response = client.post("/api/v1/knowledge-graph/relations", json={"source_entity": "制度", "relation": "规定", "target": "住宿费", "source": "制度.pdf 第3页"}, headers=headers())
    assert response.status_code == 200
    assert response.json()["status"] == "candidate"


def test_provenance_endpoint_summarizes_results():
    response = client.post(
        "/api/v1/provenance/summary",
        json={
            "results": [
                {
                    "worker": "doc",
                    "status": "success",
                    "answer": "住宿费标准为500元/晚。",
                    "confidence": 0.9,
                    "evidence": [
                        {
                            "source_type": "document",
                            "source_name": "制度.pdf",
                            "locator": "第3页",
                            "excerpt": "住宿费标准为500元/晚。",
                        }
                    ],
                }
            ]
        },
        headers=headers(),
    )
    assert response.status_code == 200
    assert response.json()["workers"] == ["doc"]


def test_semantics_endpoint_returns_metric_context():
    response = client.post(
        "/api/v1/semantics/match",
        json={"question": "本月住宿费标准是多少？"},
        headers=headers(),
    )
    assert response.status_code == 200
    assert response.json()["context"]["metric_name"] == "住宿费标准"