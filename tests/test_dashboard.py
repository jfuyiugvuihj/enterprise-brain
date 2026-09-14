from app.dashboard.service import build_dashboard


def test_dashboard_aggregates_metrics_and_insights():
    result = build_dashboard([
        {"department": "市场部", "metric": "费用", "value": 100},
        {"department": "财务部", "metric": "费用", "value": 50},
    ], [{"title": "费用上升", "severity": "warning"}])
    assert result["metrics"]["费用"]["total"] == 150
    assert result["departments"]["市场部"]["费用"] == 100
    assert result["insights"][0]["title"] == "费用上升"
