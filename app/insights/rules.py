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
            reasons.append(f"输入值较比较值增加 {growth:.1%}；未核验可比期间")
        insights.append({
            "title": f"{row.get('department', '')}{row.get('metric', '')}输入试算提醒",
            "department": row.get("department", ""),
            "metric": row.get("metric", ""),
            "severity": severity,
            "current": current,
            "previous": previous,
            "reasons": reasons,
            "evidence": row.get("evidence", []),
            'evidence_status': 'caller_supplied_unverified',
        })
    return insights
