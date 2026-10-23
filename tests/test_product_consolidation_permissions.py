"""Permission outcomes fixed by the 2026-10-14 consolidation plan.

These are the cells a user can see: what an ordinary employee may download or
export, that an uploader cannot use ownership to escape a document's department
or clearance, and that level-1 enterprise publication reaches both departments
without opening levels 2 or 3.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.contracts import Principal
from app.common.permissions import (
    ACTION_ANALYZE,
    ACTION_AUDIT,
    ACTION_DELETE,
    ACTION_DOWNLOAD,
    ACTION_EXPORT,
    ACTION_MANAGE_USERS,
    ACTION_VIEW,
    permissions_for_role,
)
from app.common.policy import authorization_decision


def _principal(username: str, department: str = "finance", role: str = "staff") -> Principal:
    return Principal.from_user(
        {"id": username, "username": username, "role": role, "department": department}
    )


def _document(**overrides) -> dict:
    resource = {
        "resource_type": "document",
        "resource_id": "doc-1",
        "owner_id": "someone-else",
        "department": "finance",
        "classification": 1,
        "visibility": "private",
        "status": "active",
    }
    resource.update(overrides)
    return resource


def test_staff_may_download_and_export_but_not_delete_or_audit():
    permissions = permissions_for_role("staff")

    assert {ACTION_VIEW, ACTION_DOWNLOAD, ACTION_EXPORT, ACTION_ANALYZE} <= permissions
    assert ACTION_DELETE not in permissions
    assert ACTION_AUDIT not in permissions
    assert ACTION_MANAGE_USERS not in permissions


def test_auditor_reads_at_the_same_clearance_as_an_administrator():
    auditor = _principal("auditor", "finance", role="auditor")
    admin = _principal("admin", "", role="admin")

    assert auditor.clearance == admin.clearance == 3
    assert authorization_decision(
        auditor, _document(classification=3), ACTION_VIEW
    ).allowed is True


def test_enterprise_shared_level_one_reaches_another_department():
    sales = _principal("sales-staff", "sales", role="staff")

    decision = authorization_decision(
        sales,
        _document(department="finance", visibility="enterprise_shared"),
        ACTION_VIEW,
    )

    assert decision.allowed is True
    assert decision.reason_code == "enterprise_shared"


@pytest.mark.parametrize("level", [2, 3])
def test_enterprise_sharing_never_unlocks_restricted_levels(level):
    sales = _principal("sales-staff", "sales", role="staff")

    decision = authorization_decision(
        sales,
        _document(department="finance", classification=level, visibility="enterprise_shared"),
        ACTION_VIEW,
    )

    assert decision.allowed is False
    assert decision.reason_code == "clearance_insufficient"


def test_enterprise_sharing_still_needs_an_assigned_department():
    no_department = _principal("floating", "", role="staff")

    decision = authorization_decision(
        no_department,
        _document(department="finance", visibility="enterprise_shared"),
        ACTION_VIEW,
    )

    assert decision.allowed is False
    assert decision.reason_code == "authorization_unavailable"


def test_owner_never_deletes_their_own_document_without_the_grant():
    owner = _principal("alice", "finance", role="staff")

    decision = authorization_decision(
        owner, _document(owner_id="alice"), ACTION_DELETE
    )

    assert decision.allowed is False
    assert decision.reason_code == "permission_denied"


@pytest.mark.parametrize(
    ("department", "classification", "reason"),
    [("sales", 1, "department_scope_denied"), ("finance", 3, "clearance_insufficient")],
)
def test_dataset_owner_cannot_bypass_current_department_or_clearance(
    department, classification, reason
):
    owner = _principal("alice", department, role="staff")
    resource = {
        "resource_type": "dataset", "resource_id": "expenses.csv", "owner_id": "alice",
        "department": "finance", "classification": classification,
    }

    decision = authorization_decision(owner, resource, ACTION_DOWNLOAD)

    assert decision.allowed is False
    assert decision.reason_code == reason


@pytest.mark.parametrize("classification", [0, -1, 4])
def test_invalid_classification_never_becomes_a_readable_level(classification):
    decision = authorization_decision(
        _principal("root", "", role="admin"),
        _document(classification=classification),
        ACTION_VIEW,
    )
    assert decision.allowed is False


def test_enterprise_publication_without_resource_department_is_not_readable():
    decision = authorization_decision(
        _principal("sales-staff", "sales"),
        _document(department=None, visibility="enterprise_shared"),
        ACTION_VIEW,
    )
    assert decision.allowed is False
    assert decision.reason_code == "resource_scope_missing"


@pytest.fixture()
def role_client(monkeypatch):
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(auth, "_MEM_USERS", {})
    assert auth.create_user("root", "secret", role="admin", department=None)[0]
    assert auth.create_user("casey", "secret", role="staff", department="finance")[0]

    def headers(username: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {auth.create_token(username)}"}

    return TestClient(app), headers


def test_administrator_changes_a_role_and_the_next_request_sees_it(role_client):
    client, headers = role_client

    changed = client.put(
        "/api/v1/users/role",
        json={"username": "casey", "role": "manager"},
        headers=headers("root"),
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["role"] == "manager"
    assert changed.json()["clearance"] == 2

    profile = client.get("/api/v1/profile", headers=headers("casey"))
    assert profile.status_code == 200, profile.text
    assert profile.json()["profile"]["role"] == "manager"
    assert profile.json()["profile"]["clearance"] == 2


def test_role_change_rejects_an_unknown_role(role_client):
    client, headers = role_client

    response = client.put(
        "/api/v1/users/role",
        json={"username": "casey", "role": "owner"},
        headers=headers("root"),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_role"


def test_staff_cannot_change_roles(role_client):
    client, headers = role_client

    response = client.put(
        "/api/v1/users/role",
        json={"username": "casey", "role": "admin"},
        headers=headers("casey"),
    )

    assert response.status_code == 403
