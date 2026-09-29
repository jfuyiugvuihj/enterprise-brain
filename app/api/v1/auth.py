"""Day 19: 登录 + 用户管理 API"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from app.common import audit as audit_log
from app.common import auth
from app.common.authorization import DEPARTMENT_SELF_REPORT_DENIED, authorize_request, principal_from_request
from app.common.permissions import ACTION_MANAGE_USERS
from app.common.rbac import clearance_for
from app.common.sso import extract_sso_identity, validate_sso_headers
from app.memory.profile import (
    ProfileStoreUnavailable,
    get_profile,
    require_ready_store,
    upsert_profile,
)

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
    """列出所有用户。

    R356：名册取不到时答 503 `storage_unavailable`，不答 `{"users": []}`。「这家公司没有
    用户」和「用户存储还没答话」是两件事，伪装成前者是一句假话。错误体逐字沿用仓里已有的
    那一枚码（`app/agents/contracts.py::ErrorEnvelope.code`），本单零新增错误码。

    闸的顺序一字未动：先 `authorize_request(..., ACTION_MANAGE_USERS)`，权限不过的人仍然
    拿原来那句 403，问不到名册的人才拿 503。响应体形状除新增的错误面之外也没动。
    """
    authorize_request(request, ACTION_MANAGE_USERS, resource_name="users")
    try:
        users = auth.list_users(denial=auth.DENIAL_RAISES)
    except auth.UserStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
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
    """``users`` 那一行 + 画像存储真读到的列，外加一枚**只读派生**的 ``clearance``（R494）。

    为什么补这一格：员工在界面上问「我能读到哪几级文档」，今天无处可查——检索闸门
    （``app/rag/filters.py`` 的 ``classification_levels``，取的就是 ``principal.clearance``）
    早就算得出这个数，只是从没交给界面。这一格只做「把已经算得出的事说出去」：值现场
    取自档位唯一真源 ``app/common/rbac.py::clearance_for(role)``，出口这一侧不写第二份
    档位表，也不换尺。

    ``role`` 取 ``base``（``auth.get_user`` 现取的 ``users`` 那一行），不取合并后的画像：
    画像那两腿（PG 的 SELECT、进程内内存表）只有 ``position`` / ``preferences`` /
    ``updated_at``，角色归属的事实源只有一处，跟着 ``base`` 走才不会让「谁说了算」变两本账。

    🔴 读不到 role 就整格不出现，绝不猜一枚 1。``clearance_for`` 的兜底是
    ``ROLE_CLEARANCE.get(role or "staff", 1)``（``tests/test_r357_single_role_roster.py`` 把它
    作为「不许顺手改成 raise」的现状钉着），所以空 role 喂进去**照样**回 1——那个 1 是给
    「知道这人是 staff」准备的缺省，不是给「根本读不到这人的角色」准备的答案。界面把它画成
    「你能读到第 1 级」就是句假话；``app/agents/contracts.py::Principal.from_user`` 也会把同一枚
    缺省冻进身份。所以本格的判据是「有没有读到 role」，不是「能不能凑出一个数」。
    """
    username = getattr(request.state, "username", "")
    base = auth.get_user(username) or {"username": username}
    profile = get_profile(username, fallback=base)
    role = str(base.get("role") or "").strip()
    if role:
        profile["clearance"] = clearance_for(role)
    return {"profile": profile}


@router.put("/profile")
async def update_my_profile(data: UpdateProfileRequest, request: Request):
    """存自己的职位与偏好；``department`` 在这一格是只读派生值，自助写不了。

    R296：部门归属的唯一事实源是 ``users`` 那一行，写入口是 R290 的
    ``PUT /api/v1/users/department``（只有持 ``users:manage`` 的管理员过得去，本人也过不去）。
    这一支过去把员工自报的部门存进 ``user_profiles.department``，而 ``get_profile`` 又拿它盖住
    权威值、再顺着画像块拼进 prompt——那是第二份真相。

    判据②：请求里**出现** ``department``（空串也算）就整发拒，不收下再丢，也不「其余字段照存、
    这一格当它不存在」。错误码复用 ``app/common/authorization.py`` 里已有的
    ``department_override_denied``，不新造裸码：那枚码的后端登记与前端归一本来就齐。
    """
    if "department" in data.model_fields_set:
        raise HTTPException(
            status_code=403,
            detail={
                "code": DEPARTMENT_SELF_REPORT_DENIED,
                "message": "画像里的 department 是只读派生值，员工自助改不了；"
                           "要挪部门请用 PUT /api/v1/users/department（需要 users:manage）",
            },
        )
    username = getattr(request.state, "username", "")
    # R383：两张存储的脸从此各自留名，不再共用下面那句「画像保存失败」。判定留在存储层
    # （``app/memory/profile.py::require_ready_store``），出口这一侧只做一次窄翻译，形状照 R356 的
    # ``except auth.UserStoreUnavailable``——路由不许自己反推存储状态，那是第二本账。
    # 顺序：department 的 403 在前（判据：权限的答案先于存储的答案），拒答在任何一次写之前。
    try:
        require_ready_store("profile write")
        ok = upsert_profile(
            username,
            position=data.position,
            preferences=data.preferences or [],
        )
    except ProfileStoreUnavailable as exc:
        raise HTTPException(status_code=503, detail="storage_unavailable") from exc
    if not ok:
        # 走到这里只剩一种可能：存储自报「就绪」，这一写却没成。只有这一格配得上那句「保存失败」。
        raise HTTPException(status_code=500, detail="画像保存失败")
    return {"status": "ok"}
