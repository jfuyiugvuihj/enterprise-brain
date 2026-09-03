"""
阶段 4 · 异常监控（P0 主动智能）

- 告警规则 CRUD（数值比较）
- evaluate_all(): 读经营数据 → 逐规则判定 → 触发则写告警 + AI 归因
- daily_report(): 汇总关键指标生成日报文本
导入不硬依赖 Postgres（懒建表）。
"""
import os
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg
from psycopg.rows import dict_row
from app.common.logger import logger

router = APIRouter()
_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")

OPS = {"gt": lambda a, b: a > b, "lt": lambda a, b: a < b,
       "gte": lambda a, b: a >= b, "lte": lambda a, b: a <= b}


def _conn():
    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _ensure():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_rules (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                metric TEXT NOT NULL,
                op TEXT NOT NULL DEFAULT 'lt',
                threshold REAL NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id SERIAL PRIMARY KEY,
                rule_id INT,
                message TEXT,
                ai_analysis TEXT,
                read BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TEXT NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai')::text
            )
        """)
        conn.commit()


class RuleCreate(BaseModel):
    name: str
    metric: str
    op: str = "lt"
    threshold: float


# ==================== 纯判定（可单测） ====================

def hit(value: float, op: str, threshold: float) -> bool:
    fn = OPS.get(op)
    if fn is None:
        return False
    return fn(value, threshold)


def _metric_value(df, metric: str):
    """对指标列取合计（列不存在返回 None）"""
    if metric not in df.columns:
        return None
    col = df[metric]
    if not __import__("pandas").api.types.is_numeric_dtype(col):
        return None
    return float(col.sum())


def _ai_analysis(rule: dict, value: float) -> str:
    try:
        from app.agents.nodes import _make_model
        from langchain_core.messages import HumanMessage
        prompt = (
            f"告警规则「{rule['name']}」被触发：指标 {rule['metric']} 当前值 {value:.1f}，"
            f"条件 {rule['op']} {rule['threshold']}。请用 2-3 句话分析可能原因并给一条建议。只输出分析。"
        )
        resp = _make_model(timeout=30).invoke([HumanMessage(content=prompt)])
        return resp.content or ""
    except Exception as e:
        logger.warning(f"[Alert] AI 归因失败: {e}")
        return ""


def evaluate_all() -> list[dict]:
    """读数据逐规则判定，触发则写告警+AI归因。返回本次触发的告警。"""
    from app.tools.excel import load_excel
    try:
        _ensure()
    except Exception as e:
        logger.warning(f"[Alert] Postgres 不可用，跳过巡检: {e}")
        return []

    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
    dfs = []
    if os.path.isdir(data_dir):
        for f in os.listdir(data_dir):
            if f.endswith((".xlsx", ".xls", ".csv")):
                try:
                    dfs.append(load_excel(os.path.join(data_dir, f)))
                except Exception:
                    continue

    with _conn() as conn:
        rules = conn.execute("SELECT * FROM alert_rules WHERE enabled = TRUE").fetchall()

    triggered = []
    for rule in rules:
        for df in dfs:
            value = _metric_value(df, rule["metric"])
            if value is None:
                continue
            if hit(value, rule["op"], rule["threshold"]):
                analysis = _ai_analysis(dict(rule), value)
                msg = f"{rule['name']}: {rule['metric']}={value:.1f} ({rule['op']} {rule['threshold']})"
                with _conn() as conn:
                    conn.execute(
                        "INSERT INTO alerts (rule_id, message, ai_analysis) VALUES (%s, %s, %s)",
                        (rule["id"], msg, analysis),
                    )
                    conn.commit()
                triggered.append({"message": msg, "ai_analysis": analysis})
                logger.warning(f"[Alert] 触发: {msg}")
    return triggered


def daily_report() -> str:
    """汇总关键指标生成日报文本"""
    from app.tools.excel import load_excel
    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
    lines = [f"【企业智脑日报】{datetime.now().strftime('%Y-%m-%d')}"]
    if os.path.isdir(data_dir):
        for f in os.listdir(data_dir):
            if f.endswith((".xlsx", ".xls", ".csv")):
                try:
                    df = load_excel(os.path.join(data_dir, f))
                except Exception:
                    continue
                nums = df.select_dtypes(include=["number"]).columns
                for c in list(nums)[:5]:
                    lines.append(f"  · {f} / {c}: 合计 {df[c].sum():.1f} 均值 {df[c].mean():.1f}")
    text = "\n".join(lines)
    logger.info(f"[DailyReport]\n{text}")
    return text


# ==================== API ====================

@router.post("/alerts/rules")
async def create_rule(data: RuleCreate):
    if data.op not in OPS:
        raise HTTPException(status_code=400, detail=f"非法操作符: {data.op}")
    _ensure()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO alert_rules (name, metric, op, threshold) VALUES (%s, %s, %s, %s) RETURNING id",
            (data.name, data.metric, data.op, data.threshold),
        )
        rid = cur.fetchone()["id"]
        conn.commit()
    return {"id": rid, "status": "ok"}


@router.get("/alerts/rules")
async def list_rules():
    _ensure()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM alert_rules ORDER BY id").fetchall()
    return {"rules": [dict(r) for r in rows]}


@router.delete("/alerts/rules/{rule_id}")
async def delete_rule(rule_id: int):
    _ensure()
    with _conn() as conn:
        cur = conn.execute("DELETE FROM alert_rules WHERE id = %s", (rule_id,))
        conn.commit()
    return {"status": "ok" if cur.rowcount else "not_found"}


@router.get("/alerts")
async def list_alerts():
    _ensure()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 100").fetchall()
    return {"alerts": [dict(r) for r in rows]}


@router.post("/alerts/check")
async def check_now():
    """手动触发一次巡检"""
    return {"triggered": evaluate_all()}
