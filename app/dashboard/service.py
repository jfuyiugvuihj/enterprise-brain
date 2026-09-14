def build_dashboard(rows: list[dict], insights: list[dict]) -> dict:
    metrics: dict[str, dict] = {}
    departments: dict[str, dict] = {}
    for row in rows:
        metric = str(row.get("metric", "未命名"))
        department = str(row.get("department", "未分配"))
        value = float(row.get("value", 0) or 0)
        bucket = metrics.setdefault(metric, {"total": 0.0, "count": 0})
        bucket["total"] += value
        bucket["count"] += 1
        departments.setdefault(department, {}).setdefault(metric, 0.0)
        departments[department][metric] += value
    for bucket in metrics.values():
        bucket["total"] = round(bucket["total"], 4)
    return {"metrics": metrics, "departments": departments, "insights": list(insights)}
