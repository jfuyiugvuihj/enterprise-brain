"""Resource-level authorization with explicit default-deny behavior."""

from typing import Any

from app.agents.contracts import AuthorizationDecision, ResourceScope
from app.common.identity import Principal
from app.common.permissions import (
    ACTION_ANALYZE,
    ACTION_APPROVE,
    ACTION_DELETE,
    ACTION_DOWNLOAD,
    ACTION_EXPORT,
    ACTION_MANAGE_ALERTS,
    ACTION_MANAGE_USERS,
    ACTION_UPLOAD,
    ACTION_VIEW,
)

_POLICY_VERSION = "resource-policy-v2"
_CLASSIFICATION_LEVELS = {
    "public": 1,
    "internal": 2,
    "confidential": 3,
    "secret": 3,
    "core": 4,
}

# An unowned document row is a legacy row, never a public document.
_DOCUMENT_RESOURCE_TYPE = "document"

# Actions a subject always holds over a resource that belongs to them: they can open
# it, take it back down and remove it. Functional capabilities are not ownership
# rights -- analyzing, exporting or approving content is granted by a role, and
# owning one document must never confer an administrative capability, so the
# manage/audit actions are absent from this set as well.
_OWNER_CONTROLLED_ACTIONS = frozenset({ACTION_VIEW, ACTION_DOWNLOAD, ACTION_DELETE})

# Actions that change a resource or move it out of the platform. A department
# mismatch on one of these is not a scope question: the caller has no authority
# over the resource at all, so it is reported with the ordinary lack-of-authority
# code instead of a scope code.
_CONTROLLING_ACTIONS = frozenset({ACTION_UPLOAD, ACTION_EXPORT, ACTION_APPROVE, ACTION_DELETE})

_ADMINISTRATOR_ROLES = frozenset({"admin"})
_MANAGEMENT_ROLES = frozenset({"admin", "manager"})
_MANAGEMENT_ACTIONS = frozenset({ACTION_MANAGE_USERS, ACTION_MANAGE_ALERTS})


def _decision(
    allowed: bool,
    reason_code: str,
    matched_rules: tuple[str, ...] = (),
) -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=allowed,
        reason_code=reason_code,
        policy_version=_POLICY_VERSION,
        matched_rules=list(matched_rules),
    )


def _resource_attributes(resource: dict[str, Any] | ResourceScope) -> dict[str, Any]:
    if isinstance(resource, ResourceScope):
        return {
            "resource_type": resource.resource_type,
            "resource_id": resource.resource_id,
            "owner_id": resource.owner_id,
            "department_ids": resource.department_ids,
            "classification": resource.classification,
            "visibility": resource.visibility,
            "version_id": resource.version_id,
            "status": resource.status,
        }
    return resource


def _classification_level(value: Any) -> int | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _CLASSIFICATION_LEVELS:
            return _CLASSIFICATION_LEVELS[normalized]
        value = normalized
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _roles_of(principal: Principal) -> set[str]:
    return {str(role) for role in (principal.roles or ()) if str(role)}


def _is_administrator(principal: Principal, permissions: set[str]) -> bool:
    """The account acts for the whole tenant rather than for one department."""
    return ACTION_MANAGE_USERS in permissions or bool(_roles_of(principal) & _ADMINISTRATOR_ROLES)


def is_administrator(principal: Principal) -> bool:
    """The platform''s one administrator test, for callers outside this module.

    Retrieval used to keep its own rule (an account without a department was refused,
    whatever it was), which is how the same document became readable through the
    resource chain and unfindable through a question. Any chain that has to ask
    "does this subject act for the whole tenant" calls this and nothing else, so a
    fourth definition cannot drift in.
    """
    return _is_administrator(principal, set(principal.permissions or ()))


def _is_management_principal(principal: Principal, permissions: set[str]) -> bool:
    """Management level: an administrator, or an account holding a manage grant."""
    return (
        _is_administrator(principal, permissions)
        or bool(_roles_of(principal) & _MANAGEMENT_ROLES)
        or bool(permissions & _MANAGEMENT_ACTIONS)
    )


def _owner_id_of(resource: dict[str, Any] | None) -> Any:
    return None if resource is None else resource.get("owner_id")


def _is_unowned(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def authorization_decision(
    principal: Principal | None,
    resource: dict[str, Any] | ResourceScope | None,
    action: str = ACTION_VIEW,
    *,
    require_resource_scope: bool = False,
) -> AuthorizationDecision:
    """Evaluate a resource request without silently widening its scope."""
    if principal is None:
        return _decision(False, "authentication_required")
    if principal.status != "active":
        return _decision(False, "principal_inactive")

    permissions = set(principal.permissions or ())
    resource_attributes = None if resource is None else _resource_attributes(resource)
    owner_id = _owner_id_of(resource_attributes)
    administrator = _is_administrator(principal, permissions)

    # Ownership is a property of the resource, not of a single action. The subject a
    # document belongs to may view, download, analyze, export and delete it, so this
    # rule is no longer limited to ACTION_VIEW and is evaluated before the role
    # gate: otherwise an owner without a delete grant could never clean up their own
    # content, which is what blocked the whole document lifecycle.
    if (
        not _is_unowned(owner_id)
        and str(owner_id) == str(principal.user_id)
        and action in _OWNER_CONTROLLED_ACTIONS
    ):
        return _decision(True, "owner_match", ("owner_match",))

    if action not in permissions:
        return _decision(False, "permission_denied")
    if resource is None:
        if require_resource_scope:
            return _decision(False, "resource_scope_missing")
        return _decision(True, "permission_granted", ("action_permission",))
    resource = resource_attributes

    # Documents written before the owner column exist carry no owner at all. They are
    # not public: ordinary staff cannot see or open them, and only the management
    # level that has to review and retire them keeps access. Ownership is resolved by
    # re-uploading the file or by an explicit ownership-claim operation, never by
    # widening this rule.
    if (
        _is_unowned(owner_id)
        and str(resource.get("resource_type") or "") == _DOCUMENT_RESOURCE_TYPE
        and not (administrator or _is_management_principal(principal, permissions))
    ):
        return _decision(False, "permission_denied", ("legacy_ownership",))

    # Protected resources need explicit classification and department metadata.
    # Missing scope is not treated as public or globally visible, and an
    # administrator does not get to guess what an undocumented resource holds.
    if "classification" not in resource or resource.get("classification") in (None, ""):
        return _decision(False, "resource_scope_missing")
    if "department" not in resource and "department_ids" not in resource:
        return _decision(False, "resource_scope_missing")

    classification = _classification_level(resource["classification"])
    if classification is None:
        return _decision(False, "resource_scope_invalid")
    if classification > principal.clearance:
        return _decision(False, "clearance_insufficient")

    resource_departments = resource.get("department_ids")
    if resource_departments is None:
        department = str(resource.get("department") or "")
        resource_departments = [department] if department else []
    resource_departments = {str(value) for value in resource_departments if str(value)}

    if administrator:
        # Explicit super-user semantics. Clearance still applies, but an
        # administrator is not required to share a department with the resource, and
        # the decision keeps its own reason code so an override is never recorded as
        # an ordinary department match in the audit trail.
        return _decision(True, "administrator_scope", ("clearance", "administrator_scope"))

    principal_departments = {str(principal.department), *(str(value) for value in principal.department_ids)}
    principal_departments.discard("")
    if not resource_departments:
        return _decision(False, "resource_scope_missing")
    if not resource_departments.intersection(principal_departments):
        if action in _CONTROLLING_ACTIONS:
            return _decision(False, "permission_denied", ("department_scope_mismatch",))
        return _decision(False, "department_scope_denied", ("department_scope",))

    return _decision(True, "department_scope_match", ("department_scope", "clearance"))


def authorize_resource(
    principal: Principal,
    resource: dict[str, Any] | ResourceScope | None,
    action: str = ACTION_VIEW,
) -> bool:
    """Backward-compatible boolean policy API."""
    return authorization_decision(
        principal,
        resource,
        action=action,
        require_resource_scope=True,
    ).allowed

