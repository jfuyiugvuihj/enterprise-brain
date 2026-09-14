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

from app.api.v1 import artifacts, chat, data, auth, alerts, intelligence, open_platform, observability


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


app = FastAPI(
    title="浼佷笟鏅鸿剳",
    description="绉佹湁鍖栭儴缃茬殑浼佷笟 AI 鏅鸿兘鍒嗘瀽骞冲彴",
    version="0.1.0",
)

# D4: 鍓嶇鐢?Bearer token锛堥潪 cookie锛夛紝涓嶉渶瑕?credentials锛?+True 鏄潪娉曠粍鍚?
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
app.include_router(alerts.router, prefix="/api/v1")  # 闃舵 4 鍛婅
app.include_router(intelligence.router, prefix="/api/v1")
app.include_router(open_platform.router, prefix="/api/v1")
app.include_router(observability.router, prefix="/api/v1")
app.include_router(open_platform.apps_router, prefix="/api/v1")

# 瀵规墍鏈?/api/v1/ 璺緞娣诲姞閴存潈涓棿浠讹紙login 闄ゅ锛?
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
            return JSONResponse(status_code=401, content={"detail": "请先登录"})
        username = payload.get("sub", "")
        user = get_user(username) if username else None
        if not user:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=401, content={"detail": "请先登录"})
        principal = Principal.from_user(user)
        if principal.status != "active":
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "账号不可用"})
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
    """棰勫姞杞?RAG pipeline锛圔M25绱㈠紩/CrossEncoder锛夛紝閬垮厤棣栦釜璇锋眰绛夊緟 10s+"""
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _preload_sync)


def _preload_sync():
    """鍚屾棰勫姞杞斤細鑰楁椂鎿嶄綔鏀剧嚎绋嬫睜閬垮厤闃诲 event loop"""
    from app.agents.tools import preload_pipeline
    from app.common.logger import logger
    logger.info("[鍚姩] 棰勫姞杞?RAG pipeline (BM25/CrossEncoder)...")
    preload_pipeline()
    logger.info("[启动] 预加载完成")


@app.on_event("startup")
async def startup_storage_guard():
    """Refuse to serve production traffic on a non-durable user store."""
    from app.common.logger import logger
    from app.common.monitoring import enforce_production_storage_guard

    enforce_production_storage_guard()
    logger.info("[startup] production storage guard passed")


@app.on_event("startup")
async def startup_scheduler():
    """闃舵 4锛氬惎鍔ㄥ畾鏃跺贰妫€ + 鏃ユ姤"""
    from app.common.logger import logger
    if not _scheduler_enabled():
        logger.info("[启动] 进程内调度器已关闭，定时任务由独立 scheduler 进程负责")
        return
    try:
        from app.scheduler.jobs import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"[鍚姩] 璋冨害鍣ㄥ惎鍔ㄥけ璐? {e}")


@app.get("/")
async def root():
    return {"status": "ok", "service": "浼佷笟鏅鸿剳"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
