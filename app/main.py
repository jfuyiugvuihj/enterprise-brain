import sys
if sys.platform == "win32":
    import asyncio, selectors
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.common.logger import setup_logging
setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import chat, data, auth


app = FastAPI(
    title="企业智脑",
    description="私有化部署的企业 AI 智能分析平台",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1", dependencies=[])
app.include_router(data.router, prefix="/api/v1", dependencies=[])

# 对所有 /api/v1/ 路径添加鉴权中间件（login 除外）
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 跳过 login 和公开路径
        # 注册接口公开，登录接口公开
        if request.url.path == "/api/v1/users" and request.method == "POST":
            return await call_next(request)
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


@app.get("/")
async def root():
    return {"status": "ok", "service": "企业智脑"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
