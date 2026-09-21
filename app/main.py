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
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request


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
            return JSONResponse(status_code=401, content={"detail": "authentication_required"})
        username = payload.get("sub", "")
        user = get_user(username) if username else None
        if not user:
            from fastapi.responses import JSONResponse
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
