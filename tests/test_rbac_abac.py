import pytest

from app.agents.contracts import AuthorizationDecision, ResourceScope
from app.common.audit import clear_audit_events, get_audit_events
from app.common.authorization import authorize, require_permission
from app.common.identity import Principal
from app.common.permissions import ACTION_ANALYZE, ACTION_DELETE, ACTION_VIEW, permissions_for_role
from app.common.policy import authorization_decision, authorize_resource


def principal(role="staff", department="finance", username="alice"):
    return Principal.from_user({"id": 1, "username": username, "role": role, "department": department})


def test_roles_have_explicit_function_permissions():
    assert ACTION_VIEW in permissions_for_role("staff")
    assert ACTION_ANALYZE in permissions_for_role("manager")
    assert ACTION_DELETE in permissions_for_role("admin")
    assert ACTION_DELETE not in permissions_for_role("staff")


def test_resource_policy_requires_department_and_clearance_scope():
    user = principal("staff", "finance")
    assert authorize_resource(user, {"classification": 1, "department": "finance"})
    assert not authorize_resource(user, {"classification": 2, "department": "finance"})
    assert not authorize_resource(user, {"classification": 1, "department": "hr"})


def test_resource_policy_accepts_frozen_resource_scope_with_internal_label():
    user = principal("manager", "finance")
    scope = ResourceScope(
        resource_type="document",
        resource_id="doc-1",
        department_ids=["finance"],
        classification="internal",
    )

    decision = authorization_decision(user, scope)

    assert decision.allowed
    assert decision.reason_code == "department_scope_match"


def test_resource_policy_returns_frozen_decision_with_rules_and_requires_scope():
    user = principal("manager", "finance")
    scope = ResourceScope(
        resource_type="document",
        resource_id="doc-1",
        department_ids=["finance"],
        classification="internal",
    )

    decision = authorization_decision(user, scope)

    assert isinstance(decision, AuthorizationDecision)
    assert decision.policy_version == "resource-policy-v2"
    assert decision.matched_rules == ["department_scope", "clearance"]
    assert not authorize_resource(user, None)


def test_resource_policy_rejects_unknown_resource_scope_classification():
    user = principal("admin", "finance")
    scope = ResourceScope(
        resource_type="document",
        resource_id="doc-1",
        department_ids=["finance"],
        classification="unclassified",
    )

    decision = authorization_decision(user, scope)

    assert not decision.allowed
    assert decision.reason_code == "resource_scope_invalid"


def test_resource_owner_can_view_own_low_clearance_resource():
    user = principal("staff", "finance", "alice")
    resource = {"classification": 1, "department": "hr", "owner_id": user.user_id}
    assert authorize_resource(user, resource, action=ACTION_VIEW)
    assert not authorize_resource(user, resource, action=ACTION_ANALYZE)


def test_admin_can_delete_and_staff_is_denied_with_audit_event():
    clear_audit_events()
    with pytest.raises(PermissionError):
        authorize(principal(), ACTION_DELETE)
    authorize(principal("admin", "", "root"), ACTION_DELETE)
    events = get_audit_events()
    assert events[0]["outcome"] == "denied"
    assert events[-1]["outcome"] == "allowed"


def test_require_permission_returns_callable_guard():
    guard = require_permission(ACTION_ANALYZE)
    assert guard(principal("manager", "finance")) is True


def test_resource_policy_denies_missing_scope_and_does_not_bypass_for_system_principal():
    system = Principal.from_user(
        {
            "id": "system-job",
            "username": "worker",
            "role": "admin",
            "is_system": True,
            "permissions": [ACTION_VIEW],
        }
    )
    assert not authorize_resource(system, {"classification": 1})
    assert not authorize_resource(system, {"department": "finance"})
