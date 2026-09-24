import os
import sys
if sys.platform == "win32":
    import asyncio, selectors
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.common.logger import setup_logging
setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.api.v1 import artifacts, chat, data, auth, alerts, dashboard, feedback, intelligence, open_platform, observability


_PRODUCTION_ENVIRONMENTS = {"production", "prod"}


def _is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in _PRODUCTION_ENVIRONMENTS


def _cors_origins() -> list[str]:
    """Name the allowed origins; a wildcard is a development convenience only."""
    configured = os.getenv("CORS_ALLOW_ORIGINS", "")
    origins = [item.strip() for item in configured.split(",") if item.strip()]
    if origins:
        return origins
    if _is_production():
        raise RuntimeError("CORS_ALLOW_ORIGINS is required in production")
    return ["*"]


def _scheduler_enabled() -> bool:
    """Only one process per deployment may own scheduled side effects."""
    configured = os.getenv("SCHEDULER_ENABLED", "").strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    if configured in {"0", "false", "no", "off"}:
        return False
    return not _is_production()


def _verify_migration_catalog(directory=None) -> int:
    """启动期校验迁移清单：校验不过就不许起应用（fail closed）。

    此前只有 scripts/migrate.py:16 会导入 app.db.migrations，也就是说 SQL 与
    manifest.json 一旦脱节（漏登记、改内容不更新 digest、空文件、改名），应用照样起来，
    要等运维跑迁移才炸——而那时线上请求已经在打了。app/db/migrations.py 的校验本身早就
    是 fail-closed 的，缺的只是"应用也走一遍"。纯本地读文件，不开数据库连接，所以
    离线开发和测试不受影响。
    """
    from app.db.migrations import discover_migrations

    found = discover_migrations(directory) if directory else discover_migrations()
    return len(found)


_verify_migration_catalog()


app = FastAPI(
    title="企业智脑",
    description="私有化部署的企业 AI 智能分析平台",
    version="0.1.0",
)

# D4: 前端用 Bearer token（非 cookie），不需要 credentials；*+True 是非法组合
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1", dependencies=[])
app.include_router(data.router, prefix="/api/v1", dependencies=[])
app.include_router(artifacts.router, prefix="/api/v1", dependencies=[])
app.include_router(alerts.router, prefix="/api/v1")  # 阶段 4 告警
app.include_router(intelligence.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")  # R14-A1 总览聚合（只读）
app.include_router(open_platform.router, prefix="/api/v1")
app.include_router(observability.router, prefix="/api/v1")
app.include_router(open_platform.apps_router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")  # R46 活动信号出口（只落计数，不存内容）

# 对所有 /api/v1/ 路径添加鉴权中间件（login 除外）
from collections import OrderedDict
import threading
import time
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request


# ---------------------------------------------------------------------------
# R199：被门禁挡在门外的探测，也要在台账里留一笔
# ---------------------------------------------------------------------------
# 取证（tests/test_r199_anonymous_probe_audit.py 第 1 组用真 ASGI 栈钉着两向）：本文件的
# AuthMiddleware 在进路由之前就回 401，所以 R179 / R194 补在路由层的那些落账点对所有未登录
# 探测一个都不响 —— 客户的安全台账里看不见有人在扫自己。这里补的就是那一笔，走同一个
# app.common.audit.record_audit 出口、同一组键：主体取不到就用它自己的退化投影
# （username=anonymous / role=unknown，app/common/audit.py:541-542），reason 沿用出口自己
# 那句 detail（authentication_required），不新造码、不新造 logger、不新造第二张事件表。
#
# 为什么必须折叠（判据④）：中间件是全站的，一台扫描器几秒能打一万个 401；而每一笔账都是一次
# 带 fsync 的整档重写（app/storage/persistence.py:247），一万个 401 就是一万次磁盘同步 ——
# 那等于把「记录攻击」做成「替攻击者做拒绝服务」。规则与 app/common/audit.py::_log_repeated
# 同族：同一来源、同一出口，窗口内第一笔必记，其后按 2 的幂补记，每一行都带着该来源在这一窗
# 口内的累计笔数，所以折叠是看得见的，没有一笔被静默丢掉；窗口过期后同一枚探测重新长账。
# 来源取 socket 对端地址，不取 X-Forwarded-For：deploy/nginx.conf:58 用的是
# $proxy_add_x_forwarded_for，客户端可以自己塞第一跳，拿可伪造的头当去重键等于把闸门交给
# 攻击者。代价是反代之后所有来源共用一个窗口（要 per-attacker 粒度得运维显式开
# --proxy-headers，那是部署决定，不在这里替业主做）。
#
# 本单不碰 403 account_unavailable（app/main.py:133）：那一枚有主体，不是匿名探测。
_ANONYMOUS_PROBE_ACTION = "auth:unauthenticated"
_ANONYMOUS_PROBE_REASON = "authentication_required"
_ANONYMOUS_PROBE_WINDOW_SECONDS = 60.0
_ANONYMOUS_PROBE_STEP = 2
#: 一个来源在一窗之内最多值多少枚不同出口各起一行，超出的合并进该来源那一行。
_ANONYMOUS_PROBE_PATH_BUDGET = 8
#: 记账表自身的上限：扫路径的人不许把它撑爆（溢出按最旧的先丢）。
_ANONYMOUS_PROBE_MAX_KEYS = 1024
#: 只出现在键里的哨兵：永远不可能是 URL 路径，也永远不进台账。
_ANONYMOUS_PROBE_SOURCE_BUCKET = "\x00source"

_probe_state = OrderedDict()
_probe_lock = threading.Lock()
_probe_generation = 0
#: 时钟缝：测试桩走这里，生产就是 time.monotonic。
_anonymous_probe_clock = time.monotonic

from app.common.audit import record_audit  # noqa: E402 - 与上面的记账说明放在一起读
from app.common.logger import logger  # noqa: E402


def clear_anonymous_probe_windows() -> None:
    """Forget every open flood window. Tests and process restarts call this; nothing else does."""
    global _probe_generation
    with _probe_lock:
        _probe_state.clear()
        _probe_generation = 0


def _anonymous_probe_line(source: str, path: str, now: float) -> dict | None:
    """Decide whether this refusal earns a line, and what that line reports.

    ``None`` means the refusal folds into the window's earlier or later line; the folded
    total is exactly what every emitted line carries as ``refusals``, so a merge is always
    readable and never a silent drop.
    """
    global _probe_generation
    source_key = (source, _ANONYMOUS_PROBE_SOURCE_BUCKET)
    with _probe_lock:
        window = _probe_state.get(source_key)
        if window is None or now - window["since"] >= _ANONYMOUS_PROBE_WINDOW_SECONDS:
            _probe_generation += 1
            window = {
                "since": now,
                "generation": _probe_generation,
                "refusals": 0,
                "paths": 0,
                "overflow": 0,
                "overflow_next": 1,
                "first": path,
            }
            _probe_state.pop(source_key, None)
        _probe_state[source_key] = window
        window["refusals"] += 1

        path_key = (source, path)
        entry = _probe_state.get(path_key)
        capped = False
        if entry is not None and entry.get("generation") == window["generation"]:
            _probe_state.move_to_end(path_key)
            entry["count"] += 1
            emit = entry["count"] >= entry["next"]
            if emit:
                entry["next"] *= _ANONYMOUS_PROBE_STEP
            occurrences = entry["count"]
        elif window["paths"] < _ANONYMOUS_PROBE_PATH_BUDGET:
            window["paths"] += 1
            _probe_state[path_key] = {
                "generation": window["generation"],
                "count": 1,
                "next": _ANONYMOUS_PROBE_STEP,
            }
            emit = True
            occurrences = 1
        else:
            window["overflow"] += 1
            emit = window["overflow"] >= window["overflow_next"]
            if emit:
                window["overflow_next"] *= _ANONYMOUS_PROBE_STEP
            occurrences = window["overflow"]
            capped = True
        while len(_probe_state) > _ANONYMOUS_PROBE_MAX_KEYS:
            _probe_state.popitem(last=False)
        if not emit:
            return None
        return {
            "resource": window["first"] if capped else path,
            "summary": {
                "source": source,
                "occurrences": occurrences,
                "refusals": window["refusals"],
                "paths": window["paths"],
                "paths_capped": capped,
                "window_seconds": _ANONYMOUS_PROBE_WINDOW_SECONDS,
            },
        }


def _file_anonymous_denial(request: Request, credential: str) -> None:
    """One refused anonymous probe earns at most one line in the one existing journal.

    The answer to the probe is already decided by the caller and this function never touches
    it: a journal that cannot be written must not turn a 401 into a 500.
    """
    try:
        client = request.client
        source = str(client[0]) if client else ""
        line = _anonymous_probe_line(source, request.url.path, _anonymous_probe_clock())
        if line is None:
            return
        summary = dict(line["summary"])
        summary["credential"] = credential
        record_audit(
            None,
            _ANONYMOUS_PROBE_ACTION,
            "denied",
            line["resource"],
            _ANONYMOUS_PROBE_REASON,
            after_summary=summary,
        )
    except Exception as exc:  # noqa: BLE001 - 台账写坏了也不许改动已经决定的回话
        logger.warning(
            "[R199] 匿名拒绝落账失败（401 回话不受影响）: %s: %s", type(exc).__name__, exc
        )

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        open_platform_paths = {
            "/api/v1/open/query",
            "/api/v1/open/analyze",
            "/api/v1/open/insights",
            "/api/v1/open/approval/preview",
            "/api/v1/open/dashboard/summary",
            "/api/v1/open/provenance/summary",
        }
        # S3: 注册(/users)不再公开，必须登录后才能管理用户；仅 login 等公开
        if request.url.path in (
            "/api/v1/login",
            "/api/v1/health",
            "/api/v1/sso/login",
            "/api/v1/open",
            "/",
            "/docs",
            "/openapi.json",
        ) or request.url.path in open_platform_paths:
            return await call_next(request)

        from app.agents.contracts import Principal
        from app.common.auth import get_token_from_request, get_user, verify_token
        token = get_token_from_request(request)
        payload = verify_token(token) if token else None
        if not token or not payload:
            from fastapi.responses import JSONResponse
            # R199：拒由这一层作答，账也由这一层落（下面两枚出口同理）。
            _file_anonymous_denial(request, "absent" if not token else "invalid")
            return JSONResponse(status_code=401, content={"detail": "authentication_required"})
        username = payload.get("sub", "")
        user = get_user(username) if username else None
        if not user:
            from fastapi.responses import JSONResponse
            # 凭证在、人不在：仍然算匿名探测，主体走 record_audit 的退化投影。
            _file_anonymous_denial(request, "unknown_account")
            return JSONResponse(status_code=401, content={"detail": "authentication_required"})
        principal = Principal.from_user(user)
        if principal.status != "active":
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "account_unavailable"})
        request.state.username = principal.username
        request.state.principal = principal
        return await call_next(request)


app.add_middleware(AuthMiddleware)

class StaticFilesWithoutGeneratedArtifacts(StaticFiles):
    """Keep generated files behind Artifact routes even for authenticated callers."""

    async def get_response(self, path: str, scope):
        top_level = path.replace("\\", "/").split("/", 1)[0]
        if top_level in {"charts", "exports"}:
            return Response(status_code=404)
        return await super().get_response(path, scope)


# Generated charts and exports use `/api/v1/artifacts/{id}`. This mount remains
# only for non-Artifact assets that are still explicitly authenticated.
app.mount("/static", StaticFilesWithoutGeneratedArtifacts(directory="static"), name="static")


@app.on_event("startup")
async def startup_preload():
    """预加载 RAG pipeline（BM25索引/CrossEncoder），避免首个请求等待 10s+"""
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _preload_sync)


def _preload_sync():
    """同步预加载：耗时操作放线程池避免阻塞 event loop"""
    from app.agents.tools import preload_pipeline
    from app.common.logger import logger
    logger.info("[启动] 预加载 RAG pipeline (BM25/CrossEncoder)...")
    try:
        preload_pipeline()
        logger.info("[启动] 预加载完成")
    except Exception as e:  # noqa: BLE001 - 预加载是优化，缺依赖时降级而不是拒绝启动
        logger.warning(f"[启动] RAG 预加载失败，检索按需降级: {e}")


@app.on_event("startup")
async def startup_storage_guard():
    """Refuse to serve production traffic on a non-durable user store."""
    from app.common.logger import logger
    from app.common.monitoring import enforce_production_storage_guard

    enforce_production_storage_guard()
    logger.info("[startup] production storage guard passed")


@app.on_event("startup")
async def startup_scheduler():
    """阶段 4：启动定时巡检 + 日报"""
    from app.common.logger import logger
    if not _scheduler_enabled():
        logger.info("[启动] 进程内调度器已关闭，定时任务由独立 scheduler 进程负责")
        return
    try:
        from app.scheduler.jobs import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"[启动] 调度器启动失败: {e}")


@app.get("/")
async def root():
    return {"status": "ok", "service": "企业智脑"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
