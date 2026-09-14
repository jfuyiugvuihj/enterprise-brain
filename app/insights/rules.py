def detect_insights(rows: list[dict]) -> list[dict]:
    insights = []
    for row in rows:
        current = float(row.get("current", 0) or 0)
        previous = float(row.get("previous", 0) or 0)
        threshold = row.get("threshold")
        over_threshold = threshold is not None and current > float(threshold)
        growth = (current - previous) / previous if previous else 0.0
        if not over_threshold and growth <= 0.2:
            continue
        severity = "critical" if growth >= 0.5 else "warning"
        reasons = []
        if over_threshold:
            reasons.append(f"超过阈值 {threshold}")
        if growth > 0.2:
            reasons.append(f"环比增长 {growth:.1%}")
        insights.append({
            "title": f"{row.get('department', '')}{row.get('metric', '')}异常",
            "department": row.get("department", ""),
            "metric": row.get("metric", ""),
            "severity": severity,
            "current": current,
            "previous": previous,
            "reasons": reasons,
            "evidence": row.get("evidence", []),
        })
    return insights
