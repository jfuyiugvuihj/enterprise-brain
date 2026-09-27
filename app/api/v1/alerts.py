"""
阶段 4 · 异常监控（P0 主动智能）

- 告警规则 CRUD（数值比较）
- evaluate_all(): 读经营数据 → 逐规则判定 → 触发则写告警 + AI 归因
  R345：读不开的数据文件不再一声不响 —— 本轮摘要点名每一份跳过的文件与异常类名，
  一份都没读成功时说的是「读不到」，不是「无异常」
- daily_report(): 汇总关键指标生成日报文本；处置闭环（R251）：确认 / 转派 / 关闭 —— 状态机、处置人与时间落库、处置后按新状态读回
导入不硬依赖 Postgres（懒建表）。
"""
import os
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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

#: 巡检「有文件、但一份都没读成功」那一格的 reason 词。与 _scan_data_files 已有的
#: tenant_data_dir_unavailable / no_data_files / no_permitted_datasets 同一族写法（内部摘要词，
#: 不是对外错误码：它只出现在 scan_summary 里，谁都不许把它塞进 HTTPException 的 detail）。
ALL_DATA_FILES_UNREADABLE = "all_data_files_unreadable"

OPS = {"gt": lambda a, b: a > b, "lt": lambda a, b: a < b,
       "gte": lambda a, b: a >= b, "lte": lambda a, b: a <= b}


def _conn():
    return psycopg.connect(_PG_URL, row_factory=dict_row)


def _database_available() -> bool:
    auth_module = sys.modules.get("app.common.auth")
    return bool(auth_module and getattr(auth_module, "_db_ready", False))


def _is_production_environment() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


class AlertSchemaNotMigratedError(RuntimeError):
    """生产库里该由 migrations 建的那枚表/列不在——本模块三句 "run migrations first" 的唯一类型。

    故意做成 ``RuntimeError`` 的子类而不是替换它，也没有新造第二份基类语义（同
    ``app/storage/pending_approvals.py:140`` 那条既有裁定）：写侧的既有断言钉的就是基类
    （``pytest.raises(RuntimeError, match=...)``：``tests/test_memory_production_schema.py:83``、
    ``tests/test_r184_alerts_department_column.py:420``、``tests/test_r176_alert_row_scope.py:469``），
    具名化只许加一层，不许把旧账弄红。三句消息文本一个字都不改，改的只有「谁能接住它」。

    存在的意义是让 **HTTP 出口** 能只接这一种错：把任何 RuntimeError 都翻成 503，等于替真正的
    bug 打掩护——驱动缺失、以及本件 ``_dispose_alert`` 那句「写成了却读不回来」都会跟着洗白。
    """


#: 三格缺口的排查路各不相同，日志必须分开说：缺表跑 0003、缺归属列跑 0012、缺处置列跑 0014。
#: 键与上面那三句消息的开头逐字对齐，值是 migrations/ 目录里真存在的文件名（有钉对账存在性，
#: 也判「三格解析出的迁移两两不同」）。响应侧三格共用同一枚 503 ``storage_unavailable``
#: （零新增错误码是本单硬规矩），能把它们分辨开的只有这一行日志。
MIGRATION_REQUIRED_HINTS: dict[str, str] = {
    "alert_rules table": "migrations/0003_legacy_runtime_tables.sql",
    "alerts table": "migrations/0003_legacy_runtime_tables.sql",
    "alerts.department column": "migrations/0012_alert_and_pending_approval_attribution_columns.sql",
    "alerts.status column": "migrations/0014_alert_disposal_columns.sql",
}


def migration_hint_for(message: str) -> str:
    """这一句 "run migrations first" 该去看哪一枚迁移文件；认不出来就明说 unknown。"""
    for schema_object, migration in MIGRATION_REQUIRED_HINTS.items():
        if message.startswith(f"{schema_object} "):
            return migration
    return "unknown"


def _require_ready_store(operation: str, *, migrations_missing: bool = False) -> None:
    """生产环境 + 存储未就绪 = 这一条腿拒答，不许退回进程内台账（R359）。

    ``migrations_missing``（R371）是同一道门上的第二种「没就绪」：库连着、旗标也翻到了 True，
    可 ``_ensure()`` / ``_require_alert_disposal_schema`` 已经现查到该由 migrations 建的表或列
    不在。它不新增判定，只是把那次现查的结论递给这道已有的闸——全模块那枚 503 仍然只在这儿
    抛出（``tests/test_r359_alerts_refuse_a_store_that_is_not_there.py`` 按 AST 数 503 出口）。

    判的两件事都是本件既有的读数，一枚都不新造、也不另算一遍: 库在不在取
    ``_database_available()``（本模块唯一那枚探针），是不是生产取
    ``_is_production_environment()``（就在上面）。两支同时成立才拒，回的必须是仓里
    已有的那一码 —— ``app/api/v1/dashboard.py:143``、``app/api/v1/notifications.py:161``、
    ``app/api/v1/chat.py:3037`` 三处出口都是 503 ``storage_unavailable``，本单零新增错误码。

    为什么不许退成「200 + 空数组」: ``_MEM_ALERTS`` 是客户机上永远为空的那张进程内表，
    于是每一次存储拒答都长成「这家公司现在没有异常」的样子，而那一屏照字面画的就是这句
    话（``frontend/src/lib/alerts.js`` 的 ALERTS_EMPTY_TITLE）。读侧不许把存储拒答翻译成
    空集 —— 与 ``/users``（R356）、``/dashboard``（R332）、通知（R299）是同一条裁定，
    告警是这四条里最后还在沉默回空的那一条。

    为什么开发态一个字都不改: 裸机与开发环境里内存 store 今天就是合法后端（``_ensure()``
    还替它就地建表），那一支的回包形状、行数、排序逐字保持。本单分开的是两张脸，不是一律
    503 —— 把开发态一起打死同样是在说假话，只不过反着说。

    调用点一律排在授权之后（``_require_alert_management``）、排在 ``_ensure()`` 与任何一次
    读写之前: 先答「你是谁、这件事你能不能做」，再答「这台机器的库在不在」。反过来就把 401 /
    403 与 503 之差做成了一枚「这家客户起没起 PG」的探针，而那不是调用方的信息。
    """
    if (_database_available() and not migrations_missing) or not _is_production_environment():
        return
    logger.warning(
        f"[Alert] 生产环境存储未就绪，这一条腿拒答而不是回内存台账: operation={operation} "
        "code=storage_unavailable（PG 未起或迁移未跑）"
    )
    raise HTTPException(status_code=503, detail="storage_unavailable")


@contextmanager
def _migrations_first_at_http_exit(operation: str):
    """把「生产库没迁移」这一类错在 **HTTP 出口** 翻成已有的那道 503，而不是裸 500（R371）。

    只接 ``AlertSchemaNotMigratedError`` 一种：判据要求转换做窄，宽捕获（``except Exception`` /
    ``except RuntimeError``）会把真正的 bug 一起翻成 503，替它打掩护。

    只做在出口这一层：``_ensure()`` 与 ``_require_alert_disposal_schema()`` 继续抛
    ``RuntimeError``——既有钉打的就是那一层（``pytest.raises``），把它们改成 ``HTTPException``
    就是改别人的账。这里也不新抛第二枚 503：它把结论交给 ``_require_ready_store``，
    全模块那道存储门仍然只有一扇。

    开发态一个字都不改：``_ensure()`` 的非生产分支就地补 DDL 自愈，``_require_alert_disposal_schema``
    在非生产直接 return，两格都到不了这里；万一到了（只有消息同族而环境不是生产），闸门不回话，
    原样 ``raise`` 上抛——那一格不是部署缺口，不许被洗成 503。
    """
    try:
        yield
    except AlertSchemaNotMigratedError as exc:
        logger.warning(
            f"[Alert] 生产库缺该由迁移建的表/列，出口按存储拒答而不是裸 500: operation={operation} "
            f"code=storage_unavailable migration={migration_hint_for(str(exc))} reason={exc}"
        )
        _require_ready_store(operation, migrations_missing=True)
        raise


#: 处置闭环（R251）落在 alerts 行上的八枚列，自建库（非生产）就地补的 DDL。逐枚写死而不是拼
#: 字符串：「与 migrations/0014 逐枚同名同默认值」这件事由 tests/test_r251_alert_disposal.py 对着
#: 迁移目录判等，不靠注释维持。生产库的补法只归 migrations，本件在那条分支里只查不建。
_ALERT_DISPOSAL_LAZY_DDLS: tuple[str, ...] = (
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'open'",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged_by TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS closed_by TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS closed_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS assignee TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS assigned_by TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS assigned_at TEXT NOT NULL DEFAULT ''",
)


def _ensure():
    global _initialized
    if _initialized:
        return
    with _conn() as conn:
        if _is_production_environment():
            for table_name in ("alert_rules", "alerts"):
                row = conn.execute(f"SELECT to_regclass('public.{table_name}') AS table_name").fetchone()
                if not row or row["table_name"] is None:
                    raise AlertSchemaNotMigratedError(
                        f"{table_name} table is required in production; run migrations first"
                    )
            # 行级归属依赖 alerts.department。生产库的 schema 只由 migrations 负责，本件
            # 不在这儿偷偷 ALTER，所以缺列要像缺表一样当场讲清楚，而不是让读路径撞一个
            # ``column "department" does not exist`` 的 500。
            column = conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'alerts' AND column_name = 'department' LIMIT 1"
            ).fetchone()
            # 有行就是列在，没行就是列缺 —— 只认这一件事，不猜驱动返回的键名。
            if not column:
                raise AlertSchemaNotMigratedError(
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
                status TEXT NOT NULL DEFAULT 'open',
                acknowledged_by TEXT NOT NULL DEFAULT '',
                acknowledged_at TEXT NOT NULL DEFAULT '',
                closed_by TEXT NOT NULL DEFAULT '',
                closed_at TEXT NOT NULL DEFAULT '',
                assignee TEXT NOT NULL DEFAULT '',
                assigned_by TEXT NOT NULL DEFAULT '',
                assigned_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (NOW() AT TIME ZONE 'Asia/Shanghai')::text
            )
        """)
        # 归属列：一条告警属于哪个部门（逗号分隔的多部门，'' 表示无归属）。自建库就地补列
        # （IF NOT EXISTS 幂等），生产库的补法归 migrations —— 由上面那条检查守门。
        conn.execute(
            "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS department TEXT NOT NULL DEFAULT ''"
        )
        # 处置列同一套路：IF NOT EXISTS 幂等补列，给这一版之前已经自建过的开发库让出位置。
        for _disposal_ddl in _ALERT_DISPOSAL_LAZY_DDLS:
            conn.execute(_disposal_ddl)
        conn.commit()
    _initialized = True


class RuleCreate(BaseModel):
    name: str
    metric: str
    op: str = "lt"
    threshold: float


#: 转派的请求体只有一枚目标用户名：谁派的、什么时候派的，服务端自己记，不接受客户端代填。
class AlertAssignCreate(BaseModel):
    assignee: str


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


# ==================== 处置闭环（R251）：状态词表、守卫与三件动作 ====================

#: 台账上「处置一条告警」这条口子的审计资源名。读台账、写规则、动处置是三道不同的口，
#: 拒绝行要看得出是哪一道拒的（与 ALERT_LEDGER_RESOURCE / ALERT_RULES_RESOURCE 同一命名法）。
ALERT_DISPOSAL_RESOURCE = "alert_disposal"

#: 一条告警的处置状态：封闭集合，``closed`` 是唯一的终态。词表的第二份拼写在
#: migrations/0014 的 CHECK 里 —— 那是 PostgreSQL 唯一能持有封闭集的形状，不是第三份。
#: 两份取值集合必须逐枚相等，由 tests/test_r251_alert_disposal.py 现读迁移判，抄不算。
ALERT_STATUS_OPEN = "open"
ALERT_STATUS_ACKNOWLEDGED = "acknowledged"
ALERT_STATUS_CLOSED = "closed"
ALERT_STATUSES: tuple[str, ...] = (
    ALERT_STATUS_OPEN,
    ALERT_STATUS_ACKNOWLEDGED,
    ALERT_STATUS_CLOSED,
)
#: 进了这一枚就不许再往前推，也不许退回来：重开不在本单三件动作里，所以也没有那条出口。
ALERT_TERMINAL_STATUSES: frozenset[str] = frozenset({ALERT_STATUS_CLOSED})

#: 三件动作，与三条路径一一对应（ack / close / assign 各自可寻址，判据 J-2）。
ALERT_ACTION_ACK = "ack"
ALERT_ACTION_CLOSE = "close"
ALERT_ACTION_ASSIGN = "assign"
ALERT_ACTIONS: tuple[str, ...] = (ALERT_ACTION_ACK, ALERT_ACTION_CLOSE, ALERT_ACTION_ASSIGN)

#: 每一枚动作唯一的合法形状：``(允许出发的当前状态, 写入后的状态)``，目标为 ``None`` 即状态不动。
#: assign 有意不动状态：派出去说的是「现在归他」，不是「有人决定了」，接手的本人还得自己确认一次；
#: 已关闭那一枚不再改派，那等于替别人重开一笔已经销掉的账。
ALERT_DISPOSAL_RULES: dict[str, tuple[frozenset[str], str | None]] = {
    ALERT_ACTION_ACK: (
        frozenset({ALERT_STATUS_OPEN}),
        ALERT_STATUS_ACKNOWLEDGED,
    ),
    ALERT_ACTION_CLOSE: (
        frozenset({ALERT_STATUS_OPEN, ALERT_STATUS_ACKNOWLEDGED}),
        ALERT_STATUS_CLOSED,
    ),
    ALERT_ACTION_ASSIGN: (
        frozenset({ALERT_STATUS_OPEN, ALERT_STATUS_ACKNOWLEDGED}),
        None,
    ),
}

#: 每一枚动作往行上写的列。顺序就是 UPDATE 里 SET 的顺序，也是值串的顺序，两处不再各数一遍。
ALERT_DISPOSAL_WRITE_COLUMNS: dict[str, tuple[str, ...]] = {
    ALERT_ACTION_ACK: ("status", "acknowledged_by", "acknowledged_at"),
    ALERT_ACTION_CLOSE: ("status", "closed_by", "closed_at"),
    ALERT_ACTION_ASSIGN: ("assignee", "assigned_by", "assigned_at"),
}

#: 八枚处置列的默认值，与 migrations/0014 逐枚同值：没记过处置的行就是 ``open``，
#: 处置人、处置时间与转派目标就是空串 —— 空串是「没记过」，不是猜出来的名字或时间。
ALERT_DISPOSAL_DEFAULTS: dict[str, str] = {
    "status": ALERT_STATUS_OPEN,
    "acknowledged_by": "",
    "acknowledged_at": "",
    "closed_by": "",
    "closed_at": "",
    "assignee": "",
    "assigned_by": "",
    "assigned_at": "",
}

#: 三枚拒绝出口的稳定码，全部复用 ErrorEnvelope.code 里**已有**的字面量，本单一枚都不新造：
#: 新造一枚要同时动 app/agents/contracts.py 的封闭枚举、docs/api/contract-v1.md 那张错误码表与
#: tests/test_error_code_vocabulary.py 的出处账，三处都在本单写域之外。
#: 404 那一枚同时是「这一条不存在」与「这一条存在但不归你读」的同一句话 —— 平台既有口径
#: （app/api/v1/chat.py、app/api/v1/data.py、app/api/v1/artifacts.py 都这么答越权读），
#: 因为「这条告警在不在」本身就是别人的信息，404 与 403 之差在这里就是一条存在性 oracle。
ALERT_DISPOSAL_NOT_FOUND_CODE = "resource_not_found"
ALERT_DISPOSAL_CONFLICT_CODE = "conflict"
ALERT_DISPOSAL_ASSIGNEE_CODE = "validation_error"

#: 生产库这一腿依赖 alerts.status；缺它就像缺归属列一样当场指名 run migrations first，
#: 而不是让处置的 UPDATE 撞一个 column "status" does not exist 的 500。只查，不建。
ALERT_DISPOSAL_SCHEMA_COLUMN = "status"


def alert_disposal_target_status(action: str, current_status: str) -> str | None:
    """这一枚动作从 ``current_status`` 出发要写成的状态；``None`` ＝ 这一枚跳转不合法。

    全仓只有这一处判状态机：守卫、写集、测试三边都问它，所以「允不允许」与「写成什么」
    不可能各说一套。原地转派回当前状态，那是合法但不改状态的一件。
    """
    rule = ALERT_DISPOSAL_RULES.get(action)
    if rule is None:
        return None
    allowed_from, target = rule
    if current_status not in allowed_from:
        return None
    return current_status if target is None else target


def alert_disposal_guard(action: str, current_status: str) -> bool:
    """这一枚动作能不能从这一格状态出发。"""
    return alert_disposal_target_status(action, current_status) is not None


def alert_disposal_writes(
    action: str,
    current_status: str,
    *,
    actor: str,
    assignee: str = "",
    disposed_at: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(列名串, 值串)``：守卫过了才谈得上写，非法跳转在这里直接抛。

    刻意不回「空写集」： 回一份空写集会让人忘记判守卫的那条调用路安静地什么都不做，
    而那条路今天就是判据 J-1 要拦的那一条。``actor`` 与 ``assignee`` 都是 username。
    """
    target = alert_disposal_target_status(action, current_status)
    if target is None:
        raise ValueError(f"非法的告警处置跳转: action={action} from status={current_status!r}")
    columns = ALERT_DISPOSAL_WRITE_COLUMNS[action]
    if action == ALERT_ACTION_ASSIGN:
        return columns, (assignee, actor, disposed_at)
    return columns, (target, actor, disposed_at)


def alert_row_status(row: dict) -> str:
    """这一行现在的处置状态。

    缺键或空串按 ``open`` 读：那是 0014 给存量行填的同一个默认值，不是新加的第三种状态 ——
    迁移之前写下的行确实没有人处置过它。
    """
    return str(row.get("status") or ALERT_STATUS_OPEN)


def alert_ledger_row(row: dict) -> dict:
    """读路径交回的行：八枚处置列永远在场。

    有库那条腿永远读得到它们（迁移给存量行填的就是这些常量），无库那条腿里的行是测试与旧代码
    直接塞进内存表的字典，可能没带这些键。补的是同一组默认值，不是新判定：两条腿对同一行
    必须答出同一个形状，否则「处置之后列表与详情读到处置后的状态」只对一腿成立。
    """
    merged = dict(row)
    for column, default in ALERT_DISPOSAL_DEFAULTS.items():
        if merged.get(column) in (None, ""):
            merged[column] = default
    return merged


def _alert_disposal_now() -> str:
    """处置时间：两条腿共用服务端这一枚时钟，所以再读一次时这个字段逐字相同。

    有库那条腿如果让 ``NOW()`` 去生成，``_MEM_ALERTS`` 与 PostgreSQL 会各交一套时间写法，
    「逐字段一致」这件事就只能对一腿断言。既有 ``created_at`` 的列默认值仍然由服务端 SQL 写，
    那一条口径本单不动。
    """
    # 服务端那枚时钟：两条腿共用它（app/common/auth.py、app/api/v1/chat.py 同一个固定偏移，
    # 中国无夏令时）。既有 created_at 的列默认值仍由服务端 SQL 生成，本单不动。
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def alert_assignee_principal(username: str):
    """按 username 找人；查人走 ``app.common.auth`` 的模块属性，与 ``principal_from_request``
    同一个缝（桩换得到它，本件不自建第二张用户表，也不接受客户端代填的身份）。"""
    from app.agents.contracts import Principal
    from app.common import auth

    if not username:
        return None
    user = auth.get_user(username)
    if not user:
        return None
    return Principal.from_user(user)


def alert_assignee_can_handle(assignee, row: dict) -> bool:
    """转派的目标自己必须处置得了这一条：两道既有的门都过，本件不加第三道判定。

    资源级那道（``alerts:manage``）判他能不能用告警功能，行级那道（``alert_row_visible``）判这一条
    归不归他。派给看不见这一行的人是假闭环 —— 他列表里都找不到它，确认与关闭都无从谈起；派给没有
    ``alerts:manage`` 的人（staff / auditor）同样是死胡同，那一格今天就是 403。停用账号由
    ``authorization_decision`` 自己判（``principal_inactive``），这里不再抄一遍它的口径。
    """
    if assignee is None:
        return False
    if not authorization_decision(assignee, None, action=ACTION_MANAGE_ALERTS).allowed:
        return False
    return alert_row_visible(assignee, row)


def _alert_scoped_select(principal, *, for_update: bool = False) -> tuple[str, tuple]:
    """按行级归属读单条告警的 SQL 与参数（参数按 SQL 里 ``%s`` 的出现次序）。

    归属谓词在这里不重写一遍：``alert_row_scope_sql`` 的 WHERE 整体是一括号的析取，剥掉那五个
    字符直接挂到 ``id = %s`` 后面还是同一个判定，读列表、读单条、处置写回三条路共用一份。
    ``for_update`` 只有处置那条腿要：它锁住这一行，让「守卫读到的那一版」与「即将写的那一版」
    是同一版，否则两个 manager 同时确认会互相看不见对方已经改过。
    """
    predicate, params = alert_row_scope_sql(principal)
    clause = ""
    if predicate:
        body = predicate.strip()
        if body.upper().startswith("WHERE"):
            body = body[len("WHERE"):].strip()
        clause = f"AND ({body})"
    sql = " ".join(
        part
        for part in (
            "SELECT * FROM alerts WHERE id = %s",
            clause,
            "FOR UPDATE" if for_update else "",
        )
        if part
    )
    return sql, params


def _alert_row_from_connection(conn, principal, alert_id: int, *, for_update: bool = False) -> dict | None:
    """有库那条腿的单行读。读不到＝这一条不存在，或者存在但不归这个人的行级范围（两者同形）。"""
    sql, params = _alert_scoped_select(principal, for_update=for_update)
    row = conn.execute(sql, (alert_id, *params)).fetchone()
    return dict(row) if row else None


def _alert_row_from_memory(principal, alert_id: int) -> dict | None:
    """无库那条腿的单行读：谓词跑在内存行上，与列表那条腿同一个 ``alert_row_visible``。"""
    for row in reversed(_MEM_ALERTS):
        if row.get("id") == alert_id and alert_row_visible(principal, row):
            return row
    return None


def _require_alert_disposal_schema(conn) -> None:
    """生产库缺 ``alerts.status`` 就说指名的一句话，不退 500，也不在这儿偷偷 ALTER。"""
    if not _is_production_environment():
        return
    column = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'alerts' AND column_name = %s LIMIT 1",
        (ALERT_DISPOSAL_SCHEMA_COLUMN,),
    ).fetchone()
    if not column:
        raise AlertSchemaNotMigratedError(
            "alerts.status column is required in production; run migrations first"
        )


def _refuse_alert_disposal(principal, code: str, status_code: int) -> None:
    """三道拒绝出口共用同一笔账与同一次抛出。

    审计里只落主体、动作、判定、资源名与那枚稳定码（沿用 ``_audit_alert_denial``），告警正文、
    别人的部门、目标用户的属性一个字都不进 payload；``reason`` 取的就是响应那枚码，本件不为
    审计另开第二份码表。
    """
    _audit_alert_denial(principal, ALERT_DISPOSAL_RESOURCE, code)
    raise HTTPException(status_code=status_code, detail=code)


def _require_capable_assignee(principal, row: dict, assignee: str) -> None:
    """转派的四格失败共用一枚码。

    查无此人、账号停用、没有 ``alerts:manage``、读不到这一条 —— 响应里不说是哪一格：
    「这个用户名在不在我们系统里」不是调用方的信息，拆开答就是一条用户名枚举口。
    """
    candidate = alert_assignee_principal(assignee)
    if not alert_assignee_can_handle(candidate, row):
        _refuse_alert_disposal(principal, ALERT_DISPOSAL_ASSIGNEE_CODE, 400)


def _dispose_alert(principal, alert_id: int, action: str, assignee: str = "") -> dict:
    """把一条告警处置掉，并把**处置之后**的行交回。

    三件事按顺序判，前一件不过就碰不到后一件的数据：

    1. 这一条归不归他读（行级归属，与列表同一份谓词）→ 否则 404，与「不存在」同形；
    2. 这一枚动作能不能从当前状态出发（``alert_disposal_guard``）→ 否则 409 ``conflict``；
    3. 转派的目标是不是自己处置得了这一条（两道既有的门）→ 否则 400 ``validation_error``。

    有库那条腿把 1 锁进事务（``FOR UPDATE``），守卫之后才拼 UPDATE，写完 commit 再从同一条
    归属谓词读回来 —— 交回的不是「我以为写成什么样」，是库里现在什么样。

    R359 另加一条前置：生产环境而库不在 ⇒ 503，三条处置写口一起过这道闸。写成「200 +
    处置后的行」而实际只落进内存，等于在台账上留下一笔谁都无法复核的处置。
    """
    _require_ready_store(f"dispose_{action}")
    if not _database_available():
        row = _alert_row_from_memory(principal, alert_id)
        if row is None:
            _refuse_alert_disposal(principal, ALERT_DISPOSAL_NOT_FOUND_CODE, 404)
        current = alert_row_status(row)
        if not alert_disposal_guard(action, current):
            _refuse_alert_disposal(principal, ALERT_DISPOSAL_CONFLICT_CODE, 409)
        if action == ALERT_ACTION_ASSIGN:
            _require_capable_assignee(principal, row, assignee)
        columns, values = alert_disposal_writes(
            action,
            current,
            actor=principal.username,
            assignee=assignee,
            disposed_at=_alert_disposal_now(),
        )
        row.update(zip(columns, values))
        return alert_ledger_row(row)

    _ensure()
    with _conn() as conn:
        _require_alert_disposal_schema(conn)
        row = _alert_row_from_connection(conn, principal, alert_id, for_update=True)
        if row is None:
            _refuse_alert_disposal(principal, ALERT_DISPOSAL_NOT_FOUND_CODE, 404)
        current = alert_row_status(row)
        if not alert_disposal_guard(action, current):
            _refuse_alert_disposal(principal, ALERT_DISPOSAL_CONFLICT_CODE, 409)
        if action == ALERT_ACTION_ASSIGN:
            _require_capable_assignee(principal, row, assignee)
        columns, values = alert_disposal_writes(
            action,
            current,
            actor=principal.username,
            assignee=assignee,
            disposed_at=_alert_disposal_now(),
        )
        assignments = ", ".join(f"{column} = %s" for column in columns)
        updated = conn.execute(
            f"UPDATE alerts SET {assignments} WHERE id = %s", (*values, alert_id)
        )
        if updated.rowcount != 1:
            # 锁内一行都没写成：与「读不到」同形交回，不补第二笔，也不换个说法再试一次。
            conn.rollback()
            _refuse_alert_disposal(principal, ALERT_DISPOSAL_NOT_FOUND_CODE, 404)
        conn.commit()
        refreshed = _alert_row_from_connection(conn, principal, alert_id)
        if refreshed is None:
            raise RuntimeError("alert disposal wrote a row that cannot be read back")
        return alert_ledger_row(refreshed)


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
    """告警巡检认哪些后缀: 现读 R336 那把单一事实源, 本件不留第二份手抄。

    上一版这里写的是 getattr(data_api, "DATA_FILE_EXTENSIONS", None)，拿不到就兜一份手抄字面量。
    那枚回退今天走不到（data.py 一定回值），它是**死的可见的**: 谁改了 data.py 的导入路径、或者
    _data_api_module() 递不出那一格，巡检就悄悄恢复扫 .xls —— 而 R336 刚刚关掉读它的那条腿
    （load_excel 现在先吐 UnsupportedDataFile），名单与读腿从此各漂各的。
    真源只有一处: app/tools/excel.py::DATA_READ_ENGINES 那张「后缀 -> 用什么引擎读」的声明表，
    对外名单是 accepted_data_file_extensions()，data.py 的 DATA_FILE_EXTENSIONS 收口闸读的就是同一枚调用。
    名单为空 = 这台机器上一种可读的数据格式都没有，那本次巡检就按「无数据文件」处理并写明原因
    （见 _scan_data_files），绝不拿一份可能过期的手抄名单继续算。
    """
    from app.tools.excel import accepted_data_file_extensions

    return {str(ext).lower() for ext in accepted_data_file_extensions()}


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
    unreadable: list[dict[str, str]] = []
    for data_path in data_paths:
        try:
            dfs.append((data_path.name, load_excel(str(data_path))))
        except Exception as exc:
            # R345: 读不开的那一份必须留下名字与原因。旧实现是裸的一句 except Exception: continue，
            # 于是「这个月没有异常」与「这个月的数据一份都没读出来」在屏上是同一张脸 —— 读不到被
            # 伪装成零，正是本仓最忌的那类病。摘要只放文件名与异常类名: str(exc) 常常带着服务端绝对
            # 路径（FileNotFoundError 就是），而这份摘要是要出网的（_scan_data_files 只放 path.name，
            # 同一条理由）。栈留在日志里，不吞。
            unreadable.append({"filename": data_path.name, "error": type(exc).__name__})
            logger.warning(
                f"[Alert] 数据文件读不开，本次巡检跳过这一份: file={data_path.name} "
                f"error={type(exc).__name__}: {exc}",
                exc_info=True,
            )
    if scan_summary is not None and data_paths:
        # 「评估了几份 / 跳了几份 / 为什么」这三格只在真有过读取尝试时长出来: 一份都没扫到时，
        # 上面 _scan_data_files 的 reason 已经把话说完，这里不许替它编一个假的 0。
        # evaluated_files 也从「扫到了哪些」收窄成「真读进来、真拿去判定了哪些」: 那才是这个名字的意思。
        scan_summary["evaluated_files"] = [dataset_name for dataset_name, _ in dfs]
        scan_summary["unreadable_files"] = unreadable
        if not dfs:
            # 有文件、却一份都没读成功: 这不叫「没有异常」，这是一次没做成的巡检。
            scan_summary["reason"] = ALL_DATA_FILES_UNREADABLE

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
                            **ALERT_DISPOSAL_DEFAULTS,
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
        except Exception as exc:
            # R345 同一格: 日报今天不改文案（那是另一枚单的口径），但不再一声不响地少一份数据。
            logger.warning(
                f"[Alert] 日报读不开这一份数据，本期不计入它: file={data_path.name} "
                f"error={type(exc).__name__}: {exc}",
                exc_info=True,
            )
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
    _require_ready_store("create_rule")
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
    with _migrations_first_at_http_exit("create_rule"):
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
    _require_ready_store("list_rules")
    if not _database_available():
        return {"rules": [dict(rule) for rule in _MEM_RULES]}
    with _migrations_first_at_http_exit("list_rules"):
        _ensure()
        with _conn() as conn:
            rows = conn.execute("SELECT * FROM alert_rules ORDER BY id").fetchall()
    return {"rules": [dict(r) for r in rows]}


@router.delete("/alerts/rules/{rule_id}")
async def delete_rule(rule_id: int, request: Request = None):
    _require_alert_management(request, ALERT_RULES_RESOURCE)
    _require_ready_store("delete_rule")
    if not _database_available():
        before = len(_MEM_RULES)
        _MEM_RULES[:] = [rule for rule in _MEM_RULES if rule["id"] != rule_id]
        return {"status": "ok" if len(_MEM_RULES) < before else "not_found"}
    with _migrations_first_at_http_exit("delete_rule"):
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

    R359 在此之前先过一道闸：生产环境而库不在 ⇒ 拒答。下面那一支回的空台账只属于开发态。
    """
    principal = _require_alert_management(request, ALERT_LEDGER_RESOURCE)
    _require_ready_store("list_alerts")
    if not _database_available():
        visible = list(
            islice(
                (
                    alert_ledger_row(alert)
                    for alert in reversed(_MEM_ALERTS)
                    if alert_row_visible(principal, alert)
                ),
                100,
            )
        )
        return {"alerts": visible}
    with _migrations_first_at_http_exit("list_alerts"):
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
    _require_ready_store("check_now")
    scan_scope: dict = {}
    triggered = evaluate_all(principal=principal, scan_summary=scan_scope)
    return {"triggered": triggered, "scan_scope": scan_scope}


# ==================== 处置闭环的 API（R251）====================

@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: int, request: Request):
    """详情读：处置之后在这儿读回**处置之后**的样子。

    门与列表完全同一条（资源级 ``_require_alert_management`` + 行级 ``alert_row_scope_sql``），
    所以「列表里没有这一条」与「详情说读不到」是同一句话。读不到一律 404
    ``resource_not_found``，不存在与不归你读答得一模一样，本件不用 403 去区分它们 ——
    一区分，别人就能拿状态码之差试出「这条告警在不在」。
    """
    principal = _require_alert_management(request, ALERT_LEDGER_RESOURCE)
    _require_ready_store("get_alert")
    if _database_available():
        with _migrations_first_at_http_exit("get_alert"):
            _ensure()
            with _conn() as conn:
                row = _alert_row_from_connection(conn, principal, alert_id)
    else:
        row = _alert_row_from_memory(principal, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail=ALERT_DISPOSAL_NOT_FOUND_CODE)
    return {"alert": alert_ledger_row(row)}


@router.post("/alerts/{alert_id}/ack")
async def acknowledge_alert(alert_id: int, request: Request):
    """确认：``open`` → ``acknowledged``，落确认人与确认时间。

    已经确认过的再点一次不合法的：那一格记的是「谁第一次认领了这条」，让它被后一次点击覆盖，
    等于把台账上唯一那句关于认领的话改成最后一个人的。要改的是转派，不是重写确认。
    """
    principal = _require_alert_management(request, ALERT_DISPOSAL_RESOURCE)
    with _migrations_first_at_http_exit("acknowledge_alert"):
        alert = _dispose_alert(principal, alert_id, ALERT_ACTION_ACK)
    return {"alert": alert}


@router.post("/alerts/{alert_id}/close")
async def close_alert(alert_id: int, request: Request):
    """关闭：``open`` / ``acknowledged`` → ``closed``（终态），落关闭人与关闭时间。

    没确认也能直接关：一条已经处置完的告警不需要先补一次「我看过了」才能销掉，那只会让人
    在台账上多写一笔他没做过的事。关完之后这一条就不再是任何动作的合法起点。
    """
    principal = _require_alert_management(request, ALERT_DISPOSAL_RESOURCE)
    with _migrations_first_at_http_exit("close_alert"):
        alert = _dispose_alert(principal, alert_id, ALERT_ACTION_CLOSE)
    return {"alert": alert}


@router.post("/alerts/{alert_id}/assign")
async def assign_alert(alert_id: int, data: AlertAssignCreate, request: Request):
    """转派：只换处置人，不动状态 —— 派出去说的是「现在归他」，不是「有人决定了」。

    目标必须自己两道门都过（能管告警、且这一条读得到），否则这一件是假闭环：他会连列表里
    都没有它。接手的本人仍然要自己确认一次，确认人才算落在他身上。
    """
    principal = _require_alert_management(request, ALERT_DISPOSAL_RESOURCE)
    with _migrations_first_at_http_exit("assign_alert"):
        alert = _dispose_alert(principal, alert_id, ALERT_ACTION_ASSIGN, data.assignee)
    return {"alert": alert}
