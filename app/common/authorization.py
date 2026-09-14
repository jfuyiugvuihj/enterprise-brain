from fastapi import HTTPException

from app.common.audit import record_audit
from app.common.identity import Principal
from app.common.policy import authorization_decision


def authorize(
    principal: Principal,
    action: str,
    resource: dict | None = None,
    resource_name: str = "",
) -> bool:
    decision = authorization_decision(principal, resource, action=action)
    record_audit(
        principal,
        action,
        "allowed" if decision.allowed else "denied",
        resource_name,
        decision.reason_code,
    )
    if not decision.allowed:
        raise PermissionError(f"权限不足: {action} ({decision.reason_code})")
    return True


def require_permission(action: str):
    def guard(principal: Principal, resource: dict | None = None, resource_name: str = "") -> bool:
        return authorize(principal, action, resource, resource_name)

    return guard


def principal_from_request(request) -> Principal | None:
    principal = getattr(getattr(request, "state", None), "principal", None)
    if isinstance(principal, Principal):
        return principal
    username = getattr(getattr(request, "state", None), "username", "")
    if not username:
        return None
    from app.common import auth

    # A username in request state is only a lookup key, not proof of identity.
    user = auth.get_user(username)
    if not user:
        return None
    return Principal.from_user(user)


def authorize_request(request, action: str, resource: dict | None = None, resource_name: str = "") -> bool:
    principal = principal_from_request(request)
    if principal is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        return authorize(principal, action, resource, resource_name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
