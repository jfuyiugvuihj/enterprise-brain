"""Day 19: 登录 + 用户管理 API"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.common import audit as audit_log
from app.common import auth
from app.common.authorization import authorize_request, principal_from_request
from app.common.permissions import ACTION_MANAGE_USERS
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


class UpdateDepartmentRequest(BaseModel):
    """``department`` 缺席/为 null = 「这轮没说」，显式空串 = 「清空归属」。"""

    username: str
    department: str | None = None


class UpdateProfileRequest(BaseModel):
    department: str = ""
    position: str = ""
    preferences: list[str] | None = None


@router.get("/health")
async def health_check():
    return {"status": "ok"}


# R51: the ``performance`` block of this answer carries the stage ledger (P50/P95 per
# segment, plus how well the segments add up to one request). Everything the block used
# to say still reads the same; the stage numbers are added next to it.
#
# R79 criterion 1: the same answer grew a "hot_index" block -- switch state, hit / miss /
# invalidation counters, the resident chunk count, and the last bypass reason code. It is
# added inside build_health_snapshot rather than in this body on purpose: the shape of
# this route is pinned by a source-regex test (tests/test_compute_wiring.py), and the
# block belongs to the snapshot so every other reader of it sees the same numbers.
@router.get("/health/details")
async def health_details():
    from app.api.v1.chat import _ASK_STATS
    from app.common.monitoring import build_health_snapshot
    from app.common.stage_timing import with_stage_latency

    return build_health_snapshot(with_stage_latency(_ASK_STATS.report()))


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
async def list_users(request: Request):
    """列出所有用户"""
    authorize_request(request, ACTION_MANAGE_USERS, resource_name="users")
    users = auth.list_users()
    return {"users": users}


@router.post("/users")
async def create_user(data: CreateUserRequest, request: Request):
    """创建新用户"""
    authorize_request(request, ACTION_MANAGE_USERS, resource_name="users")
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
async def delete_user(user_id: int, request: Request):
    """删除用户"""
    authorize_request(request, ACTION_MANAGE_USERS, resource_name="users")
    ok = auth.delete_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"status": "ok"}


@router.put("/users/password")
async def change_password(data: ChangePasswordRequest, request: Request):
    """修改密码"""
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication_required")
    if data.username != principal.username and ACTION_MANAGE_USERS not in principal.permissions:
        raise HTTPException(status_code=403, detail="权限不足: users:manage")
    ok, msg = auth.change_password(data.username, data.old_password, data.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "message": msg}


# R290: 部门归属的写入口。形状照上一支（PUT /users/password，body 里带 username），
# 闸**不**照它抄 —— 见下面的 docstring，这一格差别就是本单存在的理由。
@router.put("/users/department")
async def update_user_department(data: UpdateDepartmentRequest, request: Request):
    """改一名员工的部门归属；只有 ``users:manage`` 改得动，本人改自己也一样拒。

    为什么不能自助（本单最重要的判据）：``app/common/authorization.py:47`` 造 Principal
    取的就是 ``users`` 这一行的 ``department``，而这一列正是切数据范围的那把尺——
    ``app/common/policy.py:204`` 的资源面与 ``app/rag/filters.py:130`` 的检索面都按它比。
    ``PUT /users/password`` 那半条 ``data.username != principal.username`` 的自助豁免
    （本文件 ``:129``）搬到部门上，等于任何员工一发请求就横向拿到别的部门的文档与数据。
    所以这里没有 "本人" 这一支：闸只问权限，不问是不是自己。

    无归属（清空）意味着什么也是现取的，不是推测：非管理员一旦 ``department`` 为空，
    ``app/rag/filters.py:135`` 直接 ``authorization_unavailable`` 拒掉整条检索，
    ``app/storage/artifacts.py:537`` 拒绝产出物，``app/common/policy.py:206`` 对任何带
    部门的资源都判 ``resource_scope_missing``——清空是把人关到门外，不是放开边界。
    """
    authorize_request(request, ACTION_MANAGE_USERS, resource_name="users")
    principal = principal_from_request(request)

    target = auth.get_user(data.username)
    if target is None:
        # 账号不存在也要留痕：有人拿别人的用户名为探针试这扇门，是本仓 R163 那族账在记的事。
        audit_log.record_audit(
            principal,
            ACTION_MANAGE_USERS,
            "failure",
            f"users:{data.username}",
            "user_not_found",
        )
        raise HTTPException(status_code=404, detail="用户不存在")

    before = str(target.get("department") or "")
    if data.department is None:
        # 「漏传字段」不等于「清空归属」：一个前端少发了一个 select，就把人从部门里踢出去、
        # 连带把检索与产出物全关掉，是本单要钉死的反面。这一支一个字都不写。
        return {
            "status": "ok",
            "username": data.username,
            "department": before,
            "changed": False,
            "message": "未提供 department，归属保持不变",
        }

    after = data.department.strip()
    ok, msg = auth.update_department(data.username, after or None)
    if not ok:
        if msg == auth.USER_NOT_FOUND:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    audit_log.record_audit(
        principal,
        ACTION_MANAGE_USERS,
        "allowed",
        f"users:{data.username}",
        "department_updated",
        before_summary={"department": before},
        after_summary={"department": after},
    )
    return {
        "status": "ok",
        "username": data.username,
        "department": after,
        "changed": after != before,
        "message": msg,
    }


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
