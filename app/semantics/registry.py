"""Code-defined metric aliases.

The registry maps business wording to a metric definition. It is not a substitute
for an uploaded policy document, so every context states where the definition came
from and what still has to be verified.
"""
import os

from app.agents.contracts import MetricContext

DEFINITION_VERSION = "semantic-registry-v1"

_WARNING = "定义来自代码语义注册表，未与已上传制度文件核对"

_METRIC_RULES = [
    {
        "keywords": ("住宿费", "住宿标准", "住宿费标准"),
        "metric_id": "expense.accommodation.standard",
        "metric_name": "住宿费标准",
        "definition": "公司制度规定的单晚住宿上限",
        "formula": "单晚住宿费用 <= 制度标准",
        "unit": "元/晚",
        "period_type": "single",
        "time_granularity": "单笔",
        "aliases": ("住宿", "差旅住宿", "差旅费"),
    },
    {
        "keywords": ("差旅费", "差旅费用"),
        "metric_id": "expense.travel.total",
        "metric_name": "差旅费",
        "definition": "员工因出差产生的住宿、交通、餐饮等合规费用",
        "formula": "差旅费用合计",
        "unit": "元",
        "period_type": "month",
        "time_granularity": "月",
        "aliases": ("出差",),
    },
]


def default_timezone() -> str:
    return (os.getenv("APP_TIMEZONE") or "Asia/Shanghai").strip() or "UTC"


def match_metric_context(question: str) -> MetricContext | None:
    q = (question or "").strip()
    if not q:
        return None
    for rule in _METRIC_RULES:
        if any(keyword in q for keyword in rule["keywords"] + rule["aliases"]):
            return MetricContext(
                metric_id=rule["metric_id"],
                metric_name=rule["metric_name"],
                definition=rule["definition"],
                definition_version=DEFINITION_VERSION,
                formula=rule["formula"],
                unit=rule["unit"],
                currency=(os.getenv("APP_DEFAULT_CURRENCY") or "CNY").strip() or "CNY",
                period_type=rule["period_type"],
                timezone=default_timezone(),
                time_granularity=rule["time_granularity"],
                source_file="",
                warnings=[_WARNING],
            )
    return None