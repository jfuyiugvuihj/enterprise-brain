"""Route-level document authorization: who may list, open and remove a document.

The catalog used to carry no owner at all, so every document decision fell through to
the department intersection: an owner without a delete grant got ``permission_denied``
and an administrator without a department got ``department_scope_denied``. These tests
pin the repaired boundaries, including the reason codes, because the reason code is
what the audit journal and the upload view have to work with.
"""
from fastapi.testclient import TestClient


def _token_headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _user(username: str, department: str, role: str = "manager") -> dict[str, str]:
    user = {"id": username, "username": username, "role": role, "department": department}
    return user


def _accounts(monkeypatch, accounts: dict[str, dict]) -> None:
    """Serve fixed accounts through the lookup the authentication middleware uses."""
    from app.common import auth

    monkeypatch.setattr(auth, "get_user", lambda username: accounts.get(username))


def _stored(tmp_path, name: str, body: str = "protected") -> str:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return str(path)


def _probe_client():
    """A router-only client: the auth middleware is not part of these assertions."""
    from app.api.v1 import chat
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(chat.router, prefix="/api/v1")
    return TestClient(app)


def test_document_download_and_preview_deny_cross_department_principal(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.main import app

    stored_file = _stored(tmp_path, "document.txt")
    _accounts(monkeypatch, {"hr-manager": _user("hr-manager", "hr")})
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name, *args, **kwargs: [
            {
                "filename": name,
                "storage_path": stored_file,
                "classification": 2,
                "department": "finance",
                "owner_id": "finance-owner",
            }
        ],
    )

    client = TestClient(app)
    headers = _token_headers("hr-manager")

    download = client.get("/api/v1/documents/plan.txt/file", headers=headers)
    preview = client.get("/api/v1/documents/plan.txt/preview", headers=headers)

    assert download.status_code == 403
    assert preview.status_code == 403
    # Reading outside one's own department stays a scope answer: it is the one case
    # where department_scope_denied is still the honest final reason.
    assert download.json()["detail"] == "department_scope_denied"
    assert preview.json()["detail"] == "department_scope_denied"


def test_document_download_denies_metadata_without_resource_scope(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.main import app

    stored_file = _stored(tmp_path, "legacy.txt")
    _accounts(monkeypatch, {"finance-manager": _user("finance-manager", "finance")})
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name, *args, **kwargs: [{"filename": name, "storage_path": stored_file}],
    )

    response = TestClient(app).get(
        "/api/v1/documents/legacy.txt/file",
        headers=_token_headers("finance-manager"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "resource_scope_missing"


def test_document_download_and_preview_allow_matching_resource_scope(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.main import app

    stored_file = _stored(tmp_path, "finance.txt")
    _accounts(monkeypatch, {"finance-manager": _user("finance-manager", "finance")})
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name, *args, **kwargs: [
            {
                "filename": name,
                "storage_path": stored_file,
                "classification": 2,
                "department": "finance",
                "owner_id": "finance-owner",
            }
        ],
    )

    client = TestClient(app)
    headers = _token_headers("finance-manager")

    assert client.get("/api/v1/documents/finance.txt/file", headers=headers).status_code == 200
    assert client.get("/api/v1/documents/finance.txt/preview", headers=headers).status_code == 200


def test_owner_may_open_their_own_document_outside_the_resource_department(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.main import app

    stored_file = _stored(tmp_path, "own.txt")
    _accounts(monkeypatch, {"alice": _user("alice", "hr", role="staff")})
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name, *args, **kwargs: [
            {
                "filename": name,
                "storage_path": stored_file,
                "classification": 1,
                "department": "finance",
                "owner_id": "alice",
            }
        ],
    )

    response = TestClient(app).get(
        "/api/v1/documents/own.txt/file",
        headers=_token_headers("alice"),
    )

    assert response.status_code == 200
    assert response.text == "protected"


def test_administrator_without_a_department_opens_any_in_scope_document(monkeypatch, tmp_path):
    """The regression that made every document undeletable: an admin with no department.

    Before the explicit super-user rule an administrator shared the department
    requirement with everyone else, and an empty department set denied the request.
    """
    from app.api.v1 import chat
    from app.main import app

    stored_file = _stored(tmp_path, "ops.txt")
    _accounts(monkeypatch, {"root": _user("root", "", role="admin")})
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name, *args, **kwargs: [
            {
                "filename": name,
                "storage_path": stored_file,
                "classification": 2,
                "department": "finance",
                "owner_id": "someone-else",
            }
        ],
    )

    response = TestClient(app).get(
        "/api/v1/documents/ops.txt/file",
        headers=_token_headers("root"),
    )

    assert response.status_code == 200


def test_administrator_still_needs_the_clearance_for_a_document(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.main import app

    stored_file = _stored(tmp_path, "core.txt")
    _accounts(monkeypatch, {"root": {**_user("root", "", role="admin"), "clearance": 2}})
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name, *args, **kwargs: [
            {
                "filename": name,
                "storage_path": stored_file,
                "classification": 4,
                "department": "finance",
                "owner_id": "someone-else",
            }
        ],
    )

    response = TestClient(app).get(
        "/api/v1/documents/core.txt/file",
        headers=_token_headers("root"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "clearance_insufficient"


def test_document_catalog_hides_resources_outside_principal_scope(monkeypatch):
    from app.api.v1 import chat
    from app.main import app

    _accounts(monkeypatch, {"hr-manager": _user("hr-manager", "hr")})
    monkeypatch.setattr(
        chat,
        "current_documents",
        lambda: [
            {
                "filename": "finance.txt",
                "classification": 2,
                "department": "finance",
                "owner_id": "finance-owner",
            },
            {
                "filename": "hr.txt",
                "classification": 2,
                "department": "hr",
                "owner_id": "hr-owner",
            },
        ],
    )

    response = TestClient(app).get(
        "/api/v1/documents/catalog",
        headers=_token_headers("hr-manager"),
    )

    assert response.status_code == 200
    assert response.json()["documents"] == [
        {
            "filename": "hr.txt",
            "classification": 2,
            "department": "hr",
            "owner_id": "hr-owner",
            # R4: the catalog carries the lifecycle fields the upload view needs.
            "size_bytes": None,
            "parse_status": "pending",
            "ownership": "owned",
        }
    ]


def test_legacy_unowned_document_is_hidden_from_staff(monkeypatch):
    """An unowned row is legacy, never public (P0 acceptance item E)."""
    from app.api.v1 import chat
    from app.main import app

    _accounts(
        monkeypatch,
        {
            "alice": _user("alice", "finance", role="staff"),
            "root": _user("root", "", role="admin"),
        },
    )
    rows = [
        {
            "filename": "legacy.txt",
            "classification": 1,
            "department": "finance",
            "owner_id": None,
        }
    ]
    monkeypatch.setattr(chat, "current_documents", lambda: list(rows))

    staff = TestClient(app).get("/api/v1/documents/catalog", headers=_token_headers("alice"))
    administrator = TestClient(app).get("/api/v1/documents/catalog", headers=_token_headers("root"))

    assert staff.status_code == 200
    assert staff.json()["documents"] == []
    assert administrator.status_code == 200
    listed = administrator.json()["documents"]
    assert [row["filename"] for row in listed] == ["legacy.txt"]
    assert listed[0]["owner_id"] is None
    assert listed[0]["ownership"] == "legacy"


def test_document_version_history_denies_cross_department_principal(monkeypatch):
    from app.api.v1 import chat
    from app.main import app

    _accounts(monkeypatch, {"hr-manager": _user("hr-manager", "hr")})
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name, *args, **kwargs: [
            {
                "filename": name,
                "version": 1,
                "classification": 2,
                "department": "finance",
                "owner_id": "finance-owner",
            }
        ],
    )

    response = TestClient(app).get(
        "/api/v1/documents/finance.txt/versions",
        headers=_token_headers("hr-manager"),
    )

    assert response.status_code == 403


def test_anonymous_document_routes_answer_authentication_required():
    client = _probe_client()

    catalog = client.get("/api/v1/documents/catalog")
    download = client.get("/api/v1/documents/plan.txt/file")
    remove = client.delete("/api/v1/documents/plan.txt")

    for response in (catalog, download, remove):
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "authentication_required"


def test_cross_department_delete_is_not_answered_with_a_scope_code(monkeypatch, tmp_path):
    """Acceptance item C: a controlling action outside one's department is a plain
    lack of authority, not ``department_scope_denied``."""
    from app.api.v1 import chat
    from app.main import app

    _stored(tmp_path, "finance.txt")
    _accounts(
        monkeypatch,
        {
            "ops-lead": {
                "id": "ops-lead",
                "username": "ops-lead",
                "role": "manager",
                "department": "operations",
                "permissions": ["resource:view", "resource:delete"],
            },
            "alice": _user("alice", "operations", role="staff"),
        },
    )
    monkeypatch.setattr(
        chat,
        "list_document_versions",
        lambda name, *args, **kwargs: [
            {
                "filename": name,
                "storage_path": str(tmp_path / "finance.txt"),
                "classification": 1,
                "department": "finance",
                "owner_id": "finance-owner",
            }
        ],
    )

    client = TestClient(app)
    privileged = client.delete("/api/v1/documents/finance.txt", headers=_token_headers("ops-lead"))
    staff = client.delete("/api/v1/documents/finance.txt", headers=_token_headers("alice"))

    for response in (privileged, staff):
        assert response.status_code == 403, response.text
        assert response.json()["detail"] in {"permission_denied", "clearance_insufficient"}
        assert response.json()["detail"] != "department_scope_denied"