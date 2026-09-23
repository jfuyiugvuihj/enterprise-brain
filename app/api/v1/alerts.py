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
from itertools import islice
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.common.logger import logger
# Resolved through the module so the journal stays the single sink a test harness can
# observe: an early `from app.common.audit import record_audit` would freeze the binding.
from app.common import audit as audit_log
from app.common.authorization import principal_from_request
from app.common.permissions import ACTION_MANAGE_ALERTS
from app.common.policy import authorization_decision, is_administrator
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
            # 行级归属依赖 alerts.department。生产库的 schema 只由 migrations 负责，本件
            # 不在这儿偷偷 ALTER，所以缺列要像缺表一样当场讲清楚，而不是让读路径撞一个
            # ``column "department" does not exist`` 的 500。
            column = conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'alerts' AND column_name = 'department' LIMIT 1"
            ).fetchone()
            # 有行就是列在，没行就是列缺 —— 只认这一件事，不猜驱动返回的键名。
            if not column:
                raise RuntimeError(
                    "alerts.department column is required in production; run migrations first"
                )
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
                department TEXT NOT NULL DEFAULT '',
                read BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TEXT NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai')::text
            )
        """)
        # 归属列：一条告警属于哪个部门（逗号分隔的多部门，'' 表示无归属）。自建库就地补列
        # （IF NOT EXISTS 幂等），生产库的补法归 migrations —— 由上面那条检查守门。
        conn.execute(
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS department TEXT NOT NULL DEFAULT ''"
        )
        conn.commit()
    _initialized = True


class RuleCreate(BaseModel):
    name: str
    metric: str
    op: str = "lt"
    threshold: float


# 审计里的资源名：读台账与写规则是两条不同的口，拒绝行要看得出是哪条拒的。
ALERT_LEDGER_RESOURCE = "alerts"
ALERT_RULES_RESOURCE = "alert_rules"
#: 行级归属列的分隔符：一条告警可以属于多个部门，'' 表示无归属。
ALERT_DEPARTMENT_SEPARATOR = ","


def _joined_departments(departments) -> str:
    return ALERT_DEPARTMENT_SEPARATOR.join(sorted(departments or ()))


def _split_departments(value) -> set[str]:
    parts = str(value or "").split(ALERT_DEPARTMENT_SEPARATOR)
    return {part.strip() for part in parts if part.strip()}


def _principal_departments(principal) -> set[str]:
    """这个主体自己的部门集合（含兼任部门）；无身份就是空集，不是「全公司」。"""
    if principal is None:
        return set()
    departments = {str(principal.department or "")}
    departments.update(str(value) for value in (principal.department_ids or []))
    departments.discard("")
    return departments


def alert_row_scope_departments(principal) -> set[str] | None:
    """行级归属这一层读到的部门集合；``None`` 表示这一层对该主体不设条件。

    不设条件只有 administrator 一条路，而且判定直接取平台唯一那一条
    （``policy.is_administrator``，也就是 ``authorization_decision`` 里给出
    ``administrator_scope`` 那个 reason code 的同一把尺）—— 本件不新增第二种「算管理员」的
    定义，也不给它加任何新口子。
    """
    if principal is not None and is_administrator(principal):
        return None
    return _principal_departments(principal)


def _alert_row_departments(row) -> set[str]:
    """一条告警自己声称的归属部门。

    两个来源都认：``department``（本件写下的逗号分隔串）与 ``department_ids``（登记表与
    ResourceScope 那套惯用列表）。两个都没有就是无归属行 —— 归属列出现之前的历史行。
    """
    values = row.get("department_ids")
    if values is not None:
        departments = {str(value).strip() for value in values if str(value).strip()}
        if departments:
            return departments
    return _split_departments(row.get("department"))


def alert_row_visible(principal, row) -> bool:
    """行级判定：这一条告警是不是他部门的。过了资源级那道门不等于每一条都归他读。

    无归属行（历史行，以及既有用例依赖的 ``{"id": 1, "read": False}`` 那种形状）既不认作任何
    部门的私有内容，也不认作越权目标，对已过资源级那道门的主体保持可见 —— 与
    ``app/common/policy.py`` 对「无主文档」同一条心智：它只对管理层开放，从来不是公开资源。
    """
    departments = alert_row_scope_departments(principal)
    if departments is None:
        return True
    owners = _alert_row_departments(row)
    if not owners:
        return True
    return bool(owners & departments)


def alert_row_scope_sql(principal) -> tuple[str, tuple]:
    """同一份判定的 SQL 形状：归属条件要落进查询，不许只在 ``LIMIT 100`` 之后补一刀。

    裁在页外才是对的：一个只有几条告警的部门 manager，若先取 100 条再在 Python 里筛，只要
    别的部门刚写过 100 条，他就会看到一张空表 —— 真实存在、却被分页吃掉的假空。
    """
    departments = alert_row_scope_departments(principal)
    if departments is None:
        return "", ()
    return (
        "WHERE (department IS NULL OR department = '' "
        f"OR string_to_array(department, '{ALERT_DEPARTMENT_SEPARATOR}') && %s::text[])",
        (sorted(departments),),
    )


def alert_owner_department(principal, dataset_name: str, dataset_departments: dict[str, str]) -> str:
    """这条告警该盖哪个部门的章：先跟数据自己登记的部门，再看触发巡检的人。

    归属跟着**内容**走，不跟着读者走：定时巡检（无 Principal）也一样能盖章，别部门的
    manager 因此读不到；数据没登记、又没有人触发时才留空，那正是无归属行。
    """
    owner = str(dataset_departments.get(str(dataset_name or "")) or "")
    if owner:
        return owner
    return _joined_departments(_principal_departments(principal))


def _dataset_department_index() -> dict[str, str]:
    """登记表里每份数据的部门（filename -> "a,b"）；登记不可用时退回空表，不猜。"""
    from app.storage.datasets import dataset_registry

    try:
        records = list(dataset_registry.active_records())
    except Exception as exc:
        logger.warning(f"[Alert] 数据集登记表不可用，本次告警按无归属落章: {exc}")
        return {}
    index: dict[str, str] = {}
    for record in records:
        departments = {str(value).strip() for value in (record.department_ids or []) if str(value).strip()}
        if departments:
            index[str(record.filename)] = _joined_departments(departments)
    return index


def _audit_alert_denial(principal, resource: str, reason: str) -> None:
    """把一次告警面的拒绝写进既有那本账（``app/common/audit.py``，集合 ``audit_events``）。

    载荷只有主体、动作、资源名、判定结果与稳定码：别人的告警正文、部门值、密级值一个字都不
    进 payload。也只在拒绝这一侧记账：台账每次开面板与刷新都要读一遍，把放行也写成一行
    只会淹掉账本，
    而「资源级放行、行级裁掉几行」按平台既有心智并不是一次拒绝事件（与检索按档位裁剪同理）。
    """
    audit_log.record_audit(principal, ACTION_MANAGE_ALERTS, "denied", resource, reason)


def _require_alert_management(request: Request | None, resource: str = ALERT_LEDGER_RESOURCE):
    """第一层：资源级授权 —— 这个人到底能不能用告警功能。行级归属落在 ``alert_row_visible``。

    状态码与稳定码是既端口径，本件一个字不改：无身份 401 ``authentication_required``，无权限
    403 交回 ``authorization_decision`` 的 reason code（staff 即 ``permission_denied``），两条都
    不许降级成「200 空列表」。改的只有两件事：每条拒绝出口都落一笔审计，以及把「是哪条口拒的」
    写进审计资源名（读台账与写规则分名）。
    """
    # Direct calls are reserved for offline/internal execution; HTTP routes always
    # receive a Request and therefore remain protected by the authorization check.
    if request is None:
        return None
    principal = principal_from_request(request)
    if principal is None:
        _audit_alert_denial(None, resource, "authentication_required")
        raise HTTPException(status_code=401, detail="authentication_required")
    decision = authorization_decision(principal, None, action=ACTION_MANAGE_ALERTS)
    if not decision.allowed:
        _audit_alert_denial(principal, resource, decision.reason_code)
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
        from app.agents.contracts import ModelTier
        from langchain_core.messages import HumanMessage
        prompt = (
            f"告警规则「{rule['name']}」被触发：指标 {rule['metric']} 当前值 {value:.1f}，"
            f"条件 {rule['op']} {rule['threshold']}。请用 2-3 句话分析可能原因并给一条建议。只输出分析。"
        )
        resp = _make_model(ModelTier.ALERT, prompt=prompt).invoke([HumanMessage(content=prompt)])
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
    # 落章用的部门：每份数据自己登记的归属（登记表不可用时为空表）。
    dataset_departments = _dataset_department_index()
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
                # 行级归属落章：读侧那道判定要靠这一列才裁得动人。
                owner_department = alert_owner_department(
                    principal, dataset_name, dataset_departments
                )
                if _database_available():
                    with _conn() as conn:
                        conn.execute(
                            "INSERT INTO alerts (rule_id, message, ai_analysis, department) "
                            "VALUES (%s, %s, %s, %s)",
                            (rule["id"], msg, analysis, owner_department),
                        )
                        conn.commit()
                else:
                    _MEM_ALERTS.append(
                        {
                            "id": len(_MEM_ALERTS) + 1,
                            "rule_id": rule["id"],
                            "message": msg,
                            "ai_analysis": analysis,
                            "department": owner_department,
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
    _require_alert_management(request, ALERT_RULES_RESOURCE)
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
    _require_alert_management(request, ALERT_RULES_RESOURCE)
    if not _database_available():
        return {"rules": [dict(rule) for rule in _MEM_RULES]}
    _ensure()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM alert_rules ORDER BY id").fetchall()
    return {"rules": [dict(r) for r in rows]}


@router.delete("/alerts/rules/{rule_id}")
async def delete_rule(rule_id: int, request: Request = None):
    _require_alert_management(request, ALERT_RULES_RESOURCE)
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
    """第二层：行级归属。资源级那道门放行之后，这一条还得真的是他部门的。

    两条腿共用 ``alert_row_scope_departments`` 这一份判定：无库时在内存行上跑谓词，有库时把
    条件带进 SQL。谁都不许在 ``LIMIT 100`` 之后再筛，也不许换个部门集合另算一套。
    """
    principal = _require_alert_management(request, ALERT_LEDGER_RESOURCE)
    if not _database_available():
        visible = list(
            islice(
                (
                    dict(alert)
                    for alert in reversed(_MEM_ALERTS)
                    if alert_row_visible(principal, alert)
                ),
                100,
            )
        )
        return {"alerts": visible}
    _ensure()
    predicate, params = alert_row_scope_sql(principal)
    sql = " ".join(
        part
        for part in ("SELECT * FROM alerts", predicate, "ORDER BY id DESC LIMIT 100")
        if part
    )
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"alerts": [dict(r) for r in rows]}


@router.post("/alerts/check")
async def check_now(request: Request):
    """手动触发一次巡检"""
    principal = _require_alert_management(request, ALERT_LEDGER_RESOURCE)
    scan_scope: dict = {}
    triggered = evaluate_all(principal=principal, scan_summary=scan_scope)
    return {"triggered": triggered, "scan_scope": scan_scope}
