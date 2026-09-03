import sys
if sys.platform == "win32":
    import asyncio, selectors
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.common.logger import setup_logging
setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import chat, data, auth, alerts


app = FastAPI(
    title="企业智脑",
    description="私有化部署的企业 AI 智能分析平台",
    version="0.1.0",
)

# D4: 前端用 Bearer token（非 cookie），不需要 credentials；*+True 是非法组合
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1", dependencies=[])
app.include_router(data.router, prefix="/api/v1", dependencies=[])
app.include_router(alerts.router, prefix="/api/v1")  # 阶段 4 告警

# 对所有 /api/v1/ 路径添加鉴权中间件（login 除外）
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # S3: 注册(/users)不再公开，必须登录后才能管理用户；仅 login 等公开
        if request.url.path in ("/api/v1/login", "/", "/docs", "/openapi.json"):
            return await call_next(request)
        if request.url.path.startswith("/static/"):
            return await call_next(request)

        from app.common.auth import get_token_from_request, verify_token
        token = get_token_from_request(request)
        payload = verify_token(token) if token else None
        if not token or not payload:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=401, content={"detail": "请先登录"})
        # 注入 username 供限流使用
        request.state.username = payload.get("sub", "unknown")
        return await call_next(request)


app.add_middleware(AuthMiddleware)

# 静态文件：图表 / 导出文件
app.mount("/static", StaticFiles(directory="static"), name="static")


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
    preload_pipeline()
    logger.info("[启动] 预加载完成")


@app.on_event("startup")
async def startup_scheduler():
    """阶段 4：启动定时巡检 + 日报"""
    from app.common.logger import logger
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
