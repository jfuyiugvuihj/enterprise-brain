"""Resource-level authorization with explicit default-deny behavior."""

from typing import Any

from app.agents.contracts import AuthorizationDecision, ResourceScope
from app.common.identity import Principal
from app.common.permissions import ACTION_VIEW

_POLICY_VERSION = "resource-policy-v2"
_CLASSIFICATION_LEVELS = {
    "public": 1,
    "internal": 2,
    "confidential": 3,
    "secret": 3,
    "core": 4,
}


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
    if action not in principal.permissions:
        return _decision(False, "permission_denied")
    if resource is None:
        if require_resource_scope:
            return _decision(False, "resource_scope_missing")
        return _decision(True, "permission_granted", ("action_permission",))
    resource = _resource_attributes(resource)

    # Protected resources need explicit classification and department metadata.
    # Missing scope is not treated as public or globally visible.
    if "classification" not in resource or resource.get("classification") in (None, ""):
        return _decision(False, "resource_scope_missing")
    if "department" not in resource and "department_ids" not in resource:
        return _decision(False, "resource_scope_missing")

    classification = _classification_level(resource["classification"])
    if classification is None:
        return _decision(False, "resource_scope_invalid")
    if classification > principal.clearance:
        return _decision(False, "clearance_insufficient")

    owner_id = resource.get("owner_id")
    if owner_id is not None and str(owner_id) == str(principal.user_id) and action == ACTION_VIEW:
        return _decision(True, "owner_match", ("owner_match",))

    resource_departments = resource.get("department_ids")
    if resource_departments is None:
        department = str(resource.get("department") or "")
        resource_departments = [department] if department else []
    resource_departments = {str(value) for value in resource_departments if str(value)}

    principal_departments = {str(principal.department), *(str(value) for value in principal.department_ids)}
    principal_departments.discard("")
    if not resource_departments:
        return _decision(False, "resource_scope_missing")
    if not resource_departments.intersection(principal_departments):
        return _decision(False, "department_scope_denied")

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


