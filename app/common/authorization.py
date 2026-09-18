from fastapi import HTTPException

from app.common.audit import record_audit
from app.common.identity import Principal
from app.common.policy import authorization_decision, is_administrator


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
        raise HTTPException(status_code=401, detail="authentication_required")
    try:
        return authorize(principal, action, resource, resource_name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

# A caller-named department that is not the caller's own is a refused request, not a
# scope to compute with. Kept as one constant so the audit trail and the response
# cannot drift apart over the name of the same judgment.
DEPARTMENT_SELF_REPORT_DENIED = "department_override_denied"


def verify_department_self_report(
    principal: Principal,
    claimed_department: str,
    *,
    action: str,
    resource_name: str = "",
) -> str:
    """Resolve the department a conclusion is reported for from the session, not the body.

    A caller may repeat its own department -- older clients still send one -- but may not
    name somebody else's: the conclusion would then be filed against a scope the caller
    has no standing for, which is a forged label even when the arithmetic is right. An
    administrator acts for the whole tenant, so naming a department is a lookup rather
    than a claim; that is the platform's one administrator test, the same one the
    resource policy applies, and no new definition of it is added here.

    Whatever is accepted is answered with the server's own value, so a request never
    supplies the label that ends up in the answer.
    """
    own = {str(principal.department or "")} | {
        str(value) for value in (principal.department_ids or [])
    }
    own.discard("")
    claimed = str(claimed_department or "").strip()
    if not claimed or claimed in own:
        return str(principal.department or "")
    if is_administrator(principal):
        return claimed
    record_audit(principal, action, "denied", resource_name, DEPARTMENT_SELF_REPORT_DENIED)
    raise HTTPException(
        status_code=403,
        detail={
            "code": DEPARTMENT_SELF_REPORT_DENIED,
            "message": "department must match the authenticated principal",
        },
    )
