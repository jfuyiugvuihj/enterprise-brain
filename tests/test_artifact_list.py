"""R2 (backend batch C-2): ``GET /api/v1/artifacts`` lists what the caller may open.

The invariant these cases hold is the one the handoff asked for and nothing more: a row is
listed exactly when the content route would serve it. The access rule is not restated here
- it is ``app.common.policy.authorization_decision`` with ``ACTION_VIEW``, the same call
``_authorized_artifact`` makes - so a change in the policy shows up as a change in the
list, never as a disagreement between the two. Every artifact lives under ``tmp_path``:
nothing in this file can touch a real ``static/`` byte.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

LIST_PATH = "/api/v1/artifacts"


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _account(username: str, department: str = "finance", role: str = "manager") -> dict[str, str]:
    return {"id": username, "username": username, "role": role, "department": department}


@pytest.fixture()
def registry(monkeypatch, tmp_path):
    """The real registry class, rooted in tmp_path."""
    from app.storage import artifacts
    from app.storage.artifacts import ArtifactRegistry

    instance = ArtifactRegistry(root=tmp_path, metadata_path=tmp_path / "artifact-metadata.json")
    monkeypatch.setattr(artifacts, "artifact_registry", instance)
    return instance


@pytest.fixture()
def account(monkeypatch):
    """An in-memory user table behind ``principal_from_request``."""
    from app.common import auth

    users: dict[str, dict] = {}
    monkeypatch.setattr(auth, "get_user", lambda username: users.get(username))

    def add(username: str, department: str = "finance", role: str = "manager") -> str:
        users[username] = _account(username, department, role)
        return username

    return add


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


def _store(registry, username: str, filename: str, **fields):
    """Register one artifact as if ``username`` had generated it."""
    from app.agents.contracts import Principal

    account = _account(username, fields.pop("department", "finance"), fields.pop("role", "manager"))
    path = registry.root / filename
    path.write_bytes(b"payload-" + filename.encode("utf-8"))
    return registry.register(path, artifact_type=fields.pop("artifact_type", "chart"), principal=Principal.from_user(account), **fields)


def _ids(body) -> list[str]:
    return [row["artifact_id"] for row in body["artifacts"]]


# ------------------------------------------------------------- the path is published


def test_the_list_path_is_published_in_the_openapi_document(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"][LIST_PATH]["get"]

    assert operation["tags"] == ["artifacts"]
    assert {item["name"] for item in operation["parameters"]} >= {"artifact_type", "limit", "offset"}


# --------------------------------------------------------- membership is the policy's answer


def test_the_list_returns_only_artifacts_of_scopes_the_caller_can_see(client, registry, account):
    account("finance-manager", "finance")
    account("hr-manager", "hr")
    mine = _store(registry, "finance-manager", "finance-chart.png")
    _store(registry, "hr-manager", "hr-chart.png", department="hr")

    body = client.get(LIST_PATH, headers=_headers("finance-manager")).json()

    assert _ids(body) == [mine.artifact_id]
    assert body["total"] == 1


def test_an_artifact_is_listed_exactly_when_the_content_route_serves_it(client, registry, account):
    """The promise and the delivery are one decision, so they cannot drift apart."""
    account("owner-a", "finance")
    account("peer-a", "finance")
    account("outsider", "hr")
    artifact = _store(registry, "owner-a", "owned.png")

    assert _ids(client.get(LIST_PATH, headers=_headers("peer-a")).json()) == [artifact.artifact_id]
    assert client.get(artifact.content_url, headers=_headers("peer-a")).status_code == 200

    assert _ids(client.get(LIST_PATH, headers=_headers("outsider")).json()) == []
    assert client.get(artifact.content_url, headers=_headers("outsider")).status_code == 403


def test_an_anonymous_caller_is_refused_the_stable_code(client, registry):
    response = client.get(LIST_PATH)

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


def test_an_administrator_crosses_departments_and_a_low_clearance_caller_does_not(client, registry, account):
    """e2 semantics reused, not re-invented: the list widens departments, never the ceiling.

    Levels are ``public`` = 1, ``internal`` = 2, ``confidential`` = 3 (``app/common/policy.py``),
    and staff clearance is 1, so the department-less refusal and the ceiling refusal below
    are two different rules. Pinning both is the point: a future change that dropped the
    classification check would still pass a department-only test.
    """
    account("boss", "finance", role="admin")
    account("hr-manager", "hr")
    account("junior", "hr", role="staff")
    public = _store(registry, "hr-manager", "public-view.png", department="hr", classification="public")
    internal = _store(registry, "hr-manager", "internal-view.png", department="hr")
    confidential = _store(registry, "hr-manager", "confidential.png", department="hr", classification="confidential")

    rows = _ids(client.get(LIST_PATH, headers=_headers("boss")).json())
    assert set(rows) == {public.artifact_id, internal.artifact_id, confidential.artifact_id}

    junior_rows = _ids(client.get(LIST_PATH, headers=_headers("junior")).json())
    assert junior_rows == [public.artifact_id]
    assert client.get(internal.content_url, headers=_headers("junior")).status_code == 403
    assert client.get(confidential.content_url, headers=_headers("junior")).status_code == 403


def test_the_owner_of_an_artifact_keeps_it_even_below_its_classification(client, registry, account):
    """Pinned, not endorsed: ``owner_match`` is evaluated before the ceiling in policy.py."""
    account("author", "finance", role="staff")
    artifact = _store(registry, "author", "author-secret.png", role="staff", classification="confidential")

    assert _ids(client.get(LIST_PATH, headers=_headers("author")).json()) == [artifact.artifact_id]
    assert client.get(artifact.content_url, headers=_headers("author")).status_code == 200


# ------------------------------------------------------------------ shape and paging


def test_paging_neither_repeats_nor_drops_a_row(client, registry, account):
    account("owner-b", "finance")
    made = [_store(registry, "owner-b", f"chart-{index}.png") for index in range(3)]

    first = client.get(f"{LIST_PATH}?limit=2&offset=0", headers=_headers("owner-b")).json()
    second = client.get(f"{LIST_PATH}?limit=2&offset=2", headers=_headers("owner-b")).json()

    assert (first["total"], first["returned"], first["has_more"]) == (3, 2, True)
    assert (second["total"], second["returned"], second["has_more"]) == (3, 1, False)
    assert len(set(_ids(first) + _ids(second))) == len(made) == 3


def test_the_limit_is_clamped_and_a_negative_offset_floors_at_zero(client, registry, account):
    account("owner-c", "finance")
    _store(registry, "owner-c", "one.png")

    body = client.get(f"{LIST_PATH}?limit=1000&offset=-5", headers=_headers("owner-c")).json()

    assert body["limit"] == 100
    assert body["offset"] == 0
    assert body["returned"] == 1


def test_the_type_filter_narrows_the_list_without_touching_scope(client, registry, account):
    account("owner-d", "finance")
    chart = _store(registry, "owner-d", "chart.png", artifact_type="chart")
    _store(registry, "owner-d", "report.pdf", artifact_type="report")

    charts = client.get(f"{LIST_PATH}?artifact_type=chart", headers=_headers("owner-d")).json()
    unknown = client.get(f"{LIST_PATH}?artifact_type=spreadsheet", headers=_headers("owner-d")).json()

    assert _ids(charts) == [chart.artifact_id]
    assert charts["artifact_type"] == "chart"
    assert (unknown["artifacts"], unknown["total"]) == ([], 0)


def test_a_row_carries_the_delivery_urls_and_the_scope_but_no_server_path(client, registry, account):
    account("owner-e", "finance")
    artifact = _store(registry, "owner-e", "chart.png")

    row = client.get(LIST_PATH, headers=_headers("owner-e")).json()["artifacts"][0]

    assert row["artifact_id"] == artifact.artifact_id
    assert row["content_url"] == f"/api/v1/artifacts/{artifact.artifact_id}/content"
    assert row["download_url"] == f"/api/v1/artifacts/{artifact.artifact_id}/download"
    assert row["filename"] == "chart.png"
    assert row["owner_id"] == "owner-e"
    assert row["department_ids"] == ["finance"]
    assert row["classification"] == "internal"
    assert row["created_at"] == artifact.created_at
    assert "storage_path" not in row
    assert "content_sha256" not in row


# ------------------------------------------------- the registry refuses rows it cannot deliver


def test_a_retired_expired_or_vanished_artifact_is_never_listed(client, registry, account):
    account("owner-f", "finance")
    live = _store(registry, "owner-f", "live.png")
    retired = _store(registry, "owner-f", "retired.png")
    _store(registry, "owner-f", "expired.png", expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
    vanished = _store(registry, "owner-f", "vanished.png")
    (registry.root / "vanished.png").unlink()

    registry.soft_delete(retired.artifact_id)
    body = client.get(LIST_PATH, headers=_headers("owner-f")).json()

    # ``live`` is the positive control: an empty list on its own would prove nothing.
    assert _ids(body) == [live.artifact_id]
    assert body["total"] == 1
    assert retired.artifact_id not in _ids(body)
    assert vanished.artifact_id not in _ids(body)
    assert client.get(vanished.content_url, headers=_headers("owner-f")).status_code == 404


def test_the_registry_query_is_not_a_second_access_rule_of_its_own(registry, account):
    """``list_active`` returns every live row; who may see it stays the policy's answer."""
    account("owner-g", "finance")
    account("other-g", "hr")
    mine = _store(registry, "owner-g", "mine.png")
    theirs = _store(registry, "other-g", "theirs.png", department="hr")

    assert {row.artifact_id for row in registry.list_active()} == {mine.artifact_id, theirs.artifact_id}
    assert [row.artifact_id for row in registry.list_active(owner_id="owner-g")] == [mine.artifact_id]
    assert registry.list_active(artifact_type="report") == []