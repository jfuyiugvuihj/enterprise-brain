from app.insights.rules import detect_insights


def test_detect_insights_finds_threshold_and_growth_anomalies():
    rows = [
        {"department": "市场部", "metric": "差旅费", "current": 130, "previous": 100, "threshold": 120},
        {"department": "财务部", "metric": "差旅费", "current": 90, "previous": 100, "threshold": 120},
    ]
    insights = detect_insights(rows)
    assert len(insights) == 1
    assert insights[0]["department"] == "市场部"
    assert insights[0]["severity"] in {"warning", "critical"}


def test_detect_insights_is_deterministic_for_empty_input():
    assert detect_insights([]) == []
