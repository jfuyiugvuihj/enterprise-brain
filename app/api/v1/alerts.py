"""
阶段 4 · 异常监控（P0 主动智能）

- 告警规则 CRUD（数值比较）
- evaluate_all(): 读经营数据 → 逐规则判定 → 触发则写告警 + AI 归因
- daily_report(): 汇总关键指标生成日报文本
导入不硬依赖 Postgres（懒建表）。
"""
import os
import json
import sys
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.common.logger import logger
from app.common.authorization import principal_from_request
from app.common.permissions import ACTION_MANAGE_ALERTS
from app.common.policy import authorization_decision
try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None
    dict_row = None
from app.common.notifications import send_im_notification

router = APIRouter()
_PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/enterprise_brain")
_MEM_RULES: list[dict] = []
_MEM_ALERTS: list[dict] = []
_MEM_NEXT_RULE_ID = 1
_initialized = False
_PRODUCTION_ENVIRONMENTS = {"production", "prod"}

OPS = {"gt": lambda a, b: a > b, "lt": lambda a, b: a < b,
       "gte": lambda a, b: a >= b, "lte": lambda a, b: a <= b}


def _conn():
    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _database_available() -> bool:
    auth_module = sys.modules.get("app.common.auth")
    return bool(auth_module and getattr(auth_module, "_db_ready", False))


def _is_production_environment() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


def _ensure():
    global _initialized
    if _initialized:
        return
    with _conn() as conn:
        if _is_production_environment():
            for table_name in ("alert_rules", "alerts"):
                row = conn.execute(f"SELECT to_regclass('public.{table_name}') AS table_name").fetchone()
                if not row or row["table_name"] is None:
                    raise RuntimeError(f"{table_name} table is required in production; run migrations first")
            _initialized = True
            return
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
    _initialized = True


class RuleCreate(BaseModel):
    name: str
    metric: str
    op: str = "lt"
    threshold: float


def _require_alert_management(request: Request | None):
    # Direct calls are reserved for offline/internal execution; HTTP routes always
    # receive a Request and therefore remain protected by the authorization check.
    if request is None:
        return None
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    decision = authorization_decision(principal, None, action=ACTION_MANAGE_ALERTS)
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason_code)
    return principal


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
    if _database_available():
        try:
            _ensure()
        except Exception as e:
            logger.warning(f"[Alert] Postgres 不可用，切换内存规则: {e}")

    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data")
    dfs = []
    if os.path.isdir(data_dir):
        for f in os.listdir(data_dir):
            if f.endswith((".xlsx", ".xls", ".csv")):
                try:
                    dfs.append(load_excel(os.path.join(data_dir, f)))
                except Exception:
                    continue

    if _database_available():
        with _conn() as conn:
            rules = conn.execute("SELECT * FROM alert_rules WHERE enabled = TRUE").fetchall()
    else:
        rules = [rule for rule in _MEM_RULES if rule["enabled"]]

    triggered = []
    for rule in rules:
        for df in dfs:
            value = _metric_value(df, rule["metric"])
            if value is None:
                continue
            if hit(value, rule["op"], rule["threshold"]):
                analysis = _ai_analysis(dict(rule), value)
                msg = f"{rule['name']}: {rule['metric']}={value:.1f} ({rule['op']} {rule['threshold']})"
                if _database_available():
                    with _conn() as conn:
                        conn.execute(
                            "INSERT INTO alerts (rule_id, message, ai_analysis) VALUES (%s, %s, %s)",
                            (rule["id"], msg, analysis),
                        )
                        conn.commit()
                else:
                    _MEM_ALERTS.append(
                        {
                            "id": len(_MEM_ALERTS) + 1,
                            "rule_id": rule["id"],
                            "message": msg,
                            "ai_analysis": analysis,
                            "read": False,
                            "created_at": datetime.now().isoformat(),
                        }
                    )
                triggered.append({"message": msg, "ai_analysis": analysis})
                send_im_notification(
                    "企业智脑告警",
                    f"{msg}\n{analysis}".strip(),
                    source="alerts",
                    severity="warning",
                )
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
    send_im_notification("企业智脑日报", text, source="scheduler", severity="info")
    logger.info(f"[DailyReport]\n{text}")
    return text


# ==================== API ====================

@router.post("/alerts/rules")
async def create_rule(data: RuleCreate, request: Request = None):
    _require_alert_management(request)
    if data.op not in OPS:
        raise HTTPException(status_code=400, detail=f"非法操作符: {data.op}")
    if not _database_available():
        global _MEM_NEXT_RULE_ID
        rule = {
            "id": _MEM_NEXT_RULE_ID,
            "name": data.name,
            "metric": data.metric,
            "op": data.op,
            "threshold": data.threshold,
            "enabled": True,
        }
        _MEM_NEXT_RULE_ID += 1
        _MEM_RULES.append(rule)
        return {"id": rule["id"], "status": "ok"}
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
async def list_rules(request: Request = None):
    _require_alert_management(request)
    if not _database_available():
        return {"rules": [dict(rule) for rule in _MEM_RULES]}
    _ensure()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM alert_rules ORDER BY id").fetchall()
    return {"rules": [dict(r) for r in rows]}


@router.delete("/alerts/rules/{rule_id}")
async def delete_rule(rule_id: int, request: Request = None):
    _require_alert_management(request)
    if not _database_available():
        before = len(_MEM_RULES)
        _MEM_RULES[:] = [rule for rule in _MEM_RULES if rule["id"] != rule_id]
        return {"status": "ok" if len(_MEM_RULES) < before else "not_found"}
    _ensure()
    with _conn() as conn:
        cur = conn.execute("DELETE FROM alert_rules WHERE id = %s", (rule_id,))
        conn.commit()
    return {"status": "ok" if cur.rowcount else "not_found"}


@router.get("/alerts")
async def list_alerts(request: Request):
    _require_alert_management(request)
    if not _database_available():
        return {"alerts": [dict(alert) for alert in reversed(_MEM_ALERTS[-100:])]}
    _ensure()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 100").fetchall()
    return {"alerts": [dict(r) for r in rows]}


@router.post("/alerts/check")
async def check_now(request: Request):
    """手动触发一次巡检"""
    _require_alert_management(request)
    return {"triggered": evaluate_all()}
