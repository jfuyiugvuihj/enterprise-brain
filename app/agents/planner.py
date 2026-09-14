from __future__ import annotations

import re
from uuid import uuid4


def _task(worker: str, objective: str, depends_on: list[str] | None = None) -> dict:
    return {
        "task_id": f"{worker}-{uuid4().hex[:8]}",
        "worker": worker,
        "objective": objective,
        "depends_on": depends_on or [],
        "status": "pending",
    }


def build_task_plan(question: str) -> list[dict]:
    """用稳定规则拆解企业问题，避免简单任务额外调用一次大模型。"""
    q = (question or "").strip()
    if not q:
        return []

    tasks: list[dict] = []
    has_data = any(
        k in q
        for k in [
            "数据",
            "销售",
            "营收",
            "收入",
            "成本",
            "利润",
            "客流",
            "订单",
            "排名",
            "统计",
            "分析",
            "最高",
            "最低",
            "平均",
            "差距",
            "合计",
            "总额",
            "占比",
            "增长",
            "趋势",
            "对比",
            "比较",
        ]
    )
    has_doc = any(
        k in q
        for k in [
            "制度",
            "流程",
            "报销",
            "标准",
            "审批",
            "规定",
            "政策",
            "凭证",
            "发票",
            "复核",
            "材料",
            "依据",
            "谁承担",
        ]
    )
    has_chart = any(k in q for k in ["图", "图表", "趋势", "可视化"])
    has_approval = any(k in q for k in ["审批", "责任", "承担", "预审", "授权", "批准"])

    if has_data:
        tasks.append(_task("data", f"分析问题中的经营数据：{q}"))
    if has_doc:
        tasks.append(_task("doc", f"检索问题相关的企业制度和原文依据：{q}"))
    if has_chart:
        deps = [item["task_id"] for item in tasks if item["worker"] == "data"]
        tasks.append(_task("chart", f"根据真实分析结果生成图表：{q}", deps))
    if has_approval:
        deps = [item["task_id"] for item in tasks if item["worker"] in {"data", "doc"}]
        tasks.append(_task("approval", f"根据数据和制度生成审批预审建议：{q}", deps))

    if not tasks:
        tasks.append(_task("doc", f"检索并回答问题：{q}"))
    return tasks
