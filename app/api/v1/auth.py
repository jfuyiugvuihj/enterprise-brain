"""Day 19: 登录 + 用户管理 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.common import auth

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    username: str
    old_password: str
    new_password: str


# ==================== 登录 ====================


@router.post("/login")
async def login(data: LoginRequest):
    """登录，返回 JWT"""
    if not auth.verify_password(data.username, data.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = auth.create_token(data.username)
    return {"token": token, "username": data.username, "expires_in": auth._EXPIRE_HOURS * 3600}


# ==================== 用户管理 ====================


@router.get("/users")
async def list_users():
    """列出所有用户"""
    users = auth.list_users()
    return {"users": users}


@router.post("/users")
async def create_user(data: CreateUserRequest):
    """创建新用户"""
    ok, msg = auth.create_user(data.username, data.password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int):
    """删除用户"""
    ok = auth.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"status": "ok"}


@router.put("/users/password")
async def change_password(data: ChangePasswordRequest):
    """修改密码"""
    ok, msg = auth.change_password(data.username, data.old_password, data.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}
