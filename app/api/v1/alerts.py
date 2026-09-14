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
from pathlib import Path
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


def _data_api_module():
    """Reuse the Data API module: it owns the tenant DATA_DIR contract."""
    from app.api.v1 import data as data_api

    return data_api


def _tenant_data_root() -> Path | None:
    """Resolve the tenant DATA_DIR, or None when there is nothing to scan.

    The sweep used to join "../../../data" from this module, which ignored
    DATA_DIR entirely: the tenant's own directory was never evaluated while
    leftover files inside the repository folder were analyzed as if they were
    that tenant's business data. A missing or unconfigured directory now means
    "no data"; it never falls back to a directory inside the source tree.
    """
    data_api = _data_api_module()
    configured = str(getattr(data_api, "DATA_DIR", "") or os.getenv("DATA_DIR", "") or "").strip()
    if not configured:
        return None
    root = Path(configured).expanduser()
    if not root.is_dir():
        return None
    return root.resolve()


def _data_file_extensions() -> set[str]:
    extensions = getattr(_data_api_module(), "DATA_FILE_EXTENSIONS", None)
    return {str(ext).lower() for ext in (extensions or {".csv", ".xlsx", ".xls"})}


def _directory_data_files(root: Path) -> list[Path]:
    """系统巡检（无 Principal）：租户 DATA_DIR 内的数据文件。"""
    return [
        path
        for path in sorted(root.iterdir())
        if path.is_file()
        and not path.name.startswith(".")
        and path.suffix.lower() in _data_file_extensions()
    ]


def _permitted_dataset_files(principal, root: Path) -> list[Path]:
    """带 Principal 的巡检：限定在该 Principal 有权 analyze 的 Dataset 集合内。"""
    from app.common.permissions import ACTION_ANALYZE
    from app.storage.datasets import dataset_registry

    try:
        records = list(dataset_registry.active_records())
    except Exception as exc:
        logger.warning(f"[Alert] 数据集登记表不可用，本次巡检不评估任何文件: {exc}")
        return []

    paths: list[Path] = []
    for record in records:
        decision = authorization_decision(
            principal,
            record.resource_scope,
            action=ACTION_ANALYZE,
            require_resource_scope=True,
        )
        if not decision.allowed:
            continue
        try:
            path = Path(str(record.storage_path)).expanduser().resolve()
        except OSError:
            continue
        if not path.is_file():
            continue
        if not path.is_relative_to(root):
            logger.warning(f"[Alert] 数据集 {record.dataset_id} 不在租户 DATA_DIR 内，跳过")
            continue
        paths.append(path)
    return paths


def _scan_data_files(principal) -> tuple[list[Path], dict]:
    """解析本次巡检的数据范围，并返回不含服务端路径的扫描摘要。"""
    summary: dict = {
        "data_dir_configured": False,
        "scoped_to_principal": principal is not None,
        "evaluated_files": [],
        "reason": "",
    }
    root = _tenant_data_root()
    if root is None:
        summary["reason"] = "tenant_data_dir_unavailable"
        logger.warning("[Alert] 无可用租户 DATA_DIR，本次巡检按无数据处理（不回落仓库 data/）")
        return [], summary
    summary["data_dir_configured"] = True
    paths = (
        _directory_data_files(root)
        if principal is None
        else _permitted_dataset_files(principal, root)
    )
    summary["evaluated_files"] = [path.name for path in paths]
    if not paths:
        summary["reason"] = "no_data_files" if principal is None else "no_permitted_datasets"
    return paths, summary


def evaluate_all(principal=None, scan_summary: dict | None = None) -> list[dict]:
    """读数据逐规则判定，触发则写告警+AI归因。返回本次触发的告警。"""
    from app.tools.excel import load_excel
    if _database_available():
        try:
            _ensure()
        except Exception as e:
            logger.warning(f"[Alert] Postgres 不可用，切换内存规则: {e}")

    data_paths, files_summary = _scan_data_files(principal)
    if scan_summary is not None:
        scan_summary.update(files_summary)
    dfs: list[tuple[str, object]] = []
    for data_path in data_paths:
        try:
            dfs.append((data_path.name, load_excel(str(data_path))))
        except Exception:
            continue

    if _database_available():
        with _conn() as conn:
            rules = conn.execute("SELECT * FROM alert_rules WHERE enabled = TRUE").fetchall()
    else:
        rules = [rule for rule in _MEM_RULES if rule["enabled"]]

    triggered = []
    recorded_findings: set[tuple] = set()
    for rule in rules:
        for dataset_name, df in dfs:
            value = _metric_value(df, rule["metric"])
            if value is None:
                continue
            if hit(value, rule["op"], rule["threshold"]):
                msg = f"{rule['name']}: {rule['metric']}={value:.1f} ({rule['op']} {rule['threshold']})"
                finding = (rule["id"], msg)
                if finding in recorded_findings:
                    # E1-11：同一次巡检内，同一规则 + 同一计算窗口只入库一次
                    logger.info(
                        f"[Alert] 同一巡检重复命中已去重: rule_id={rule['id']} dataset={dataset_name}"
                    )
                    continue
                recorded_findings.add(finding)
                analysis = _ai_analysis(dict(rule), value)
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
    report_root = _tenant_data_root()
    data_paths = [] if report_root is None else _directory_data_files(report_root)
    lines = [f"【企业智脑日报】{datetime.now().strftime('%Y-%m-%d')}"]
    if not data_paths:
        lines.append("  · 未配置可用的租户 DATA_DIR，本期日报无经营数据")
    for data_path in data_paths:
        try:
            df = load_excel(str(data_path))
        except Exception:
            continue
        numeric_columns = df.select_dtypes(include=["number"]).columns
        for metric_column in list(numeric_columns)[:5]:
            lines.append(f"  · {data_path.name} / {metric_column}: 合计 {df[metric_column].sum():.1f} 均值 {df[metric_column].mean():.1f}")
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
    principal = _require_alert_management(request)
    scan_scope: dict = {}
    triggered = evaluate_all(principal=principal, scan_summary=scan_scope)
    return {"triggered": triggered, "scan_scope": scan_scope}
