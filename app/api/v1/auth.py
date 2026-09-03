"""Day 19: 登录 + 用户管理 API"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.common import auth
from app.common.sso import extract_sso_identity, validate_sso_headers
from app.memory.profile import get_profile, upsert_profile

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "staff"
    department: str = ""


class ChangePasswordRequest(BaseModel):
    username: str
    old_password: str
    new_password: str


class UpdateProfileRequest(BaseModel):
    department: str = ""
    position: str = ""
    preferences: list[str] | None = None


# ==================== 登录 ====================


@router.post("/login")
async def login(data: LoginRequest):
    """登录，返回 JWT"""
    if not auth.verify_password(data.username, data.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = auth.create_token(data.username)
    u = auth.get_user(data.username) or {}
    return {
        "token": token,
        "username": data.username,
        "role": u.get("role") or "staff",          # 阶段 2
        "department": u.get("department") or "",   # 阶段 2
        "expires_in": auth._EXPIRE_HOURS * 3600,
    }


# ==================== 用户管理 ====================


@router.get("/users")
async def list_users():
    """列出所有用户"""
    users = auth.list_users()
    return {"users": users}


@router.post("/users")
async def create_user(data: CreateUserRequest):
    """创建新用户"""
    ok, msg = auth.create_user(
        data.username,
        data.password,
        role=data.role,
        department=data.department or None,
    )
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


@router.post("/sso/login")
async def sso_login(request: Request):
    headers = dict(request.headers)
    if not validate_sso_headers(headers):
        raise HTTPException(status_code=401, detail="SSO 未启用或请求未通过验证")
    identity = extract_sso_identity(headers)
    if not identity:
        raise HTTPException(status_code=401, detail="缺少 SSO 身份头")
    ok, msg = auth.upsert_sso_user(
        identity["username"],
        role=identity["role"],
        department=identity["department"] or None,
    )
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    token = auth.create_token(identity["username"])
    return {
        "token": token,
        "username": identity["username"],
        "role": identity["role"],
        "department": identity["department"],
        "display_name": identity["display_name"],
        "expires_in": auth._EXPIRE_HOURS * 3600,
    }


@router.get("/profile")
async def get_my_profile(request: Request):
    username = getattr(request.state, "username", "")
    base = auth.get_user(username) or {"username": username}
    profile = get_profile(username, fallback=base)
    return {"profile": profile}


@router.put("/profile")
async def update_my_profile(data: UpdateProfileRequest, request: Request):
    username = getattr(request.state, "username", "")
    ok = upsert_profile(
        username,
        department=data.department,
        position=data.position,
        preferences=data.preferences or [],
    )
    if not ok:
        raise HTTPException(status_code=500, detail="画像保存失败")
    return {"status": "ok"}
