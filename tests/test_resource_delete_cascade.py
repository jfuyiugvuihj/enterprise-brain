"""R8 (backend batch C-2): the two missing DELETE routes, and what they really remove.

Everything here is a file this test wrote under ``tmp_path`` and removes again: the
registries are re-rooted, so no real ``data/`` or ``static/`` byte is in reach. The
decisions pinned below are the repository''s existing ones - who may delete, what a
foreign resource answers with, and that a half-finished cleanup is reported as a failure
rather than as a success - because this change adds routes, not permission semantics.
"""

import os

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

DATASET_DELETE_PATH = "/api/v1/data-files/{filename}"
ARTIFACT_DELETE_PATH = "/api/v1/artifacts/{artifact_id}"


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _account(username: str, department: str = "finance", role: str = "manager") -> dict[str, str]:
    return {"id": username, "username": username, "role": role, "department": department}


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def account(monkeypatch):
    from app.common import auth

    users: dict[str, dict] = {}
    monkeypatch.setattr(auth, "get_user", lambda username: users.get(username))

    def add(username: str, department: str = "finance", role: str = "manager") -> str:
        users[username] = _account(username, department, role)
        return username

    return add


@pytest.fixture()
def dataset_store(monkeypatch, tmp_path):
    """A dataset registry and a DATA_DIR that both point at tmp_path."""
    from app.api.v1 import data
    from app.storage import datasets
    from app.storage.datasets import DatasetRegistry

    registry = DatasetRegistry(root=tmp_path, metadata_path=tmp_path / "dataset-metadata.json")
    monkeypatch.setattr(data, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(data, "dataset_registry", registry)
    monkeypatch.setattr(datasets, "dataset_registry", registry)

    def store(filename: str, owner: str, department: str = "finance") -> str:
        from app.agents.contracts import Principal

        path = tmp_path / filename
        path.write_text("department,revenue\nfinance,100\n", encoding="utf-8")
        record = registry.register(path, principal=Principal.from_user(_account(owner, department)))
        return record.dataset_id

    store.registry = registry  # type: ignore[attr-defined]
    store.root = tmp_path  # type: ignore[attr-defined]
    return store


@pytest.fixture()
def artifact_store(monkeypatch, tmp_path):
    """An artifact registry rooted in tmp_path, exactly as the delivery tests root theirs."""
    from app.storage import artifacts
    from app.storage.artifacts import ArtifactRegistry

    registry = ArtifactRegistry(root=tmp_path, metadata_path=tmp_path / "artifact-metadata.json")
    monkeypatch.setattr(artifacts, "artifact_registry", registry)

    def store(filename: str, owner: str, department: str = "finance", **fields):
        from app.agents.contracts import Principal

        path = tmp_path / filename
        path.write_bytes(b"payload-" + filename.encode("utf-8"))
        principal = Principal.from_user(_account(owner, department))
        for key, value in fields.items():
            principal = principal.model_copy(update={key: value})
        return registry.register(path, artifact_type=fields.pop("artifact_type", "chart"), principal=principal)

    store.registry = registry  # type: ignore[attr-defined]
    store.root = tmp_path  # type: ignore[attr-defined]
    return store


def _capture(monkeypatch, module):
    """Collect the completion audits; the authorization audit is the route''s own business."""
    events: list[dict] = []

    def record(principal, action, outcome, resource="", reason="", **kwargs):
        events.append({"principal": principal.username, "action": action, "outcome": outcome, "resource": resource, "reason": reason, **kwargs})
        return dict(events[-1])

    monkeypatch.setattr(module, "record_audit", record)
    return events


# ============================================================== the two paths are published


def test_both_delete_paths_are_published(client):
    paths = client.get("/openapi.json").json()["paths"]

    # The keys are the route templates, so spelling one out is the assertion: a delete
    # that existed only as /data-files/something.csv would not be a route at all.
    assert "delete" in paths[DATASET_DELETE_PATH]
    assert "delete" in paths[ARTIFACT_DELETE_PATH]


# ============================================================================ datasets


def test_the_owner_deletes_a_dataset_and_its_bytes_go_with_it(client, account, dataset_store):
    from app.api.v1 import data

    account("finance-manager", "finance")
    dataset_id = dataset_store("finance.csv", "finance-manager")

    response = client.delete("/api/v1/data-files/finance.csv", headers=_headers("finance-manager"))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "ok",
        "filename": "finance.csv",
        "dataset_id": dataset_id,
        "file_removed": True,
        "record_status": "deleted",
    }
    assert not (dataset_store.root / "finance.csv").exists()
    assert dataset_store.registry.get(dataset_id).status == "deleted"
    assert client.get("/api/v1/data-files", headers=_headers("finance-manager")).json()["files"] == []
    assert client.get("/api/v1/data-files/finance.csv/preview", headers=_headers("finance-manager")).status_code == 404


def test_a_retired_dataset_frees_its_filename_for_a_fresh_upload(client, account, dataset_store):
    account("finance-manager", "finance")
    dataset_store("budget.csv", "finance-manager")
    client.delete("/api/v1/data-files/budget.csv", headers=_headers("finance-manager"))

    # The active lookup ignores retired rows, so the unique-filename rule can be satisfied
    # again - which is what a "delete then re-upload" recovery actually needs.
    again = dataset_store("budget.csv", "finance-manager")
    listed = client.get("/api/v1/data-files", headers=_headers("finance-manager")).json()["files"]

    assert [item["dataset_id"] for item in listed] == [again]
    assert listed[0]["filename"] == "budget.csv"


def test_a_foreign_dataset_is_refused_by_policy_and_its_bytes_survive(client, account, dataset_store):
    account("finance-manager", "finance")
    account("hr-manager", "hr")
    dataset_store("payroll.csv", "hr-manager", department="hr")

    response = client.delete("/api/v1/data-files/payroll.csv", headers=_headers("finance-manager"))

    # 403 with the reason the policy gave, never a 404 that pretends the file is absent.
    # ACTION_DELETE sits in _CONTROLLING_ACTIONS, so a foreign resource answers
    # permission_denied here while a foreign *view* would answer department_scope_denied:
    # the two are distinguishable in the audit''s matched_rules
    # ("department_scope_mismatch") but deliberately not in the client-visible code.
    assert response.status_code == 403
    assert response.json()["detail"] == "permission_denied"
    assert (dataset_store.root / "payroll.csv").is_file()
    assert client.get("/api/v1/data-files/payroll.csv/file", headers=_headers("hr-manager")).status_code == 200


def test_a_staff_member_in_the_same_department_may_not_delete_a_peers_dataset(client, account, dataset_store):
    from app.agents.contracts import Principal

    account("author", "finance")
    account("junior", "finance", role="staff")
    path = dataset_store.root / "shared.csv"
    path.write_text("department,revenue\nfinance,100\n", encoding="utf-8")
    dataset_store.registry.register(path, principal=Principal.from_user(_account("author", "finance")))

    response = client.delete("/api/v1/data-files/shared.csv", headers=_headers("junior"))

    assert response.status_code == 403
    assert response.json()["detail"] == "permission_denied"
    assert path.is_file()


def test_an_unknown_or_already_deleted_dataset_answers_404(client, account, dataset_store):
    account("finance-manager", "finance")
    dataset_store("gone.csv", "finance-manager")

    assert client.delete("/api/v1/data-files/never-uploaded.csv", headers=_headers("finance-manager")).status_code == 404
    client.delete("/api/v1/data-files/gone.csv", headers=_headers("finance-manager"))
    assert client.delete("/api/v1/data-files/gone.csv", headers=_headers("finance-manager")).status_code == 404


def test_an_anonymous_dataset_delete_is_refused_the_stable_code(client, dataset_store):
    dataset_store("anon.csv", "someone")

    response = client.delete("/api/v1/data-files/anon.csv")

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


def test_the_dataset_delete_is_audited_with_what_it_removed(client, account, dataset_store, monkeypatch):
    from app.api.v1 import data

    events = _capture(monkeypatch, data)
    account("finance-manager", "finance")
    dataset_id = dataset_store("audit.csv", "finance-manager")

    client.delete("/api/v1/data-files/audit.csv", headers=_headers("finance-manager"))

    completion = [event for event in events if event["reason"] == "dataset_deleted"]
    assert len(completion) == 1
    event = completion[0]
    assert event["action"] == "resource:delete"
    assert event["outcome"] == "allowed"
    assert event["resource"] == dataset_id
    assert event["after_summary"] == {"deleted": True, "stage": "completed", "file_removed": True, "record_status": "deleted"}
    assert event["before_summary"]["owner_id"] == "finance-manager"
    assert event["before_summary"]["size_bytes"] > 0


def test_bytes_that_cannot_be_removed_are_reported_and_the_row_stays_retryable(client, account, dataset_store, monkeypatch):
    from app.api.v1 import data

    events = _capture(monkeypatch, data)
    account("finance-manager", "finance")
    dataset_id = dataset_store("locked.csv", "finance-manager")

    def refuse(path):
        raise PermissionError("device or resource busy")

    # Known unknown, kept here rather than only in the handback: os.remove is patched on
    # the module object the route shares with the rest of the process, so for the length
    # of this case every other caller - including pytest unlinking a tmp_path it decides
    # to clean - sees the refusal. monkeypatch restores it at teardown and this case
    # deletes no real file, but the interaction has not been observed under a retained
    # --basetemp run.
    monkeypatch.setattr(os, "remove", refuse)
    response = client.delete("/api/v1/data-files/locked.csv", headers=_headers("finance-manager"))

    assert response.status_code == 500
    assert response.json()["detail"] == "internal_error"
    assert dataset_store.registry.get(dataset_id).status == "active"
    assert (dataset_store.root / "locked.csv").is_file()
    failed = [event for event in events if event["outcome"] == "failed"]
    assert [(event["reason"], event["after_summary"]["stage"]) for event in failed] == [("dataset_cleanup_incomplete", "physical_cleanup")]


def test_the_chart_route_still_refuses_a_departmentless_owner_with_the_same_constant(client, account):
    """The literal at data.py:278 became the file''s own constant: no behavior moved."""
    from app.agents.contracts import Principal
    from app.api.v1 import data

    assert data.OWNER_SCOPE_REQUIRED == "department_scope_required"
    without_department = Principal.from_user(_account("no-dept", "")).model_copy(update={"department": ""})

    with pytest.raises(HTTPException) as exc:
        data._require_artifact_scope(without_department)

    assert exc.value.status_code == 403
    assert exc.value.detail == "department_scope_required"


# ========================================================================== artifacts


def test_the_owner_deletes_their_artifact_and_the_bytes_and_the_listing_follow(client, account, artifact_store):
    account("owner-a", "finance")
    artifact = artifact_store("chart-a.png", "owner-a")

    response = client.delete(f"/api/v1/artifacts/{artifact.artifact_id}", headers=_headers("owner-a"))

    assert response.status_code == 200, response.text
    assert response.json()["record_status"] == "deleted"
    assert response.json()["artifact_id"] == artifact.artifact_id
    assert not (artifact_store.root / "chart-a.png").exists()
    assert artifact_store.registry.get(artifact.artifact_id).status == "deleted"
    assert client.get("/api/v1/artifacts", headers=_headers("owner-a")).json()["artifacts"] == []
    assert client.get(artifact.content_url, headers=_headers("owner-a")).status_code == 404


def test_a_same_department_peer_without_a_delete_grant_keeps_the_bytes(client, account, artifact_store):
    account("owner-b", "finance")
    account("peer-b", "finance")
    artifact = artifact_store("chart-b.png", "owner-b")

    response = client.delete(f"/api/v1/artifacts/{artifact.artifact_id}", headers=_headers("peer-b"))

    assert response.status_code == 403
    assert response.json()["detail"] == "permission_denied"
    assert (artifact_store.root / "chart-b.png").is_file()


def test_an_administrator_retires_another_accounts_artifact_without_new_grants(client, account, artifact_store):
    account("boss", "finance", role="admin")
    account("owner-c", "hr")
    artifact = artifact_store("chart-c.png", "owner-c", department="hr")

    response = client.delete(f"/api/v1/artifacts/{artifact.artifact_id}", headers=_headers("boss"))

    # Deleting is a controlling action, so cross-department reach here is the policy''s
    # existing administrator_scope plus the resource:delete grant, not a rule this route adds.
    assert response.status_code == 200
    assert artifact_store.registry.get(artifact.artifact_id).status == "deleted"


def test_an_unknown_or_retired_artifact_answers_404(client, account, artifact_store):
    account("owner-d", "finance")
    artifact = artifact_store("chart-d.png", "owner-d")

    assert client.delete("/api/v1/artifacts/00000000000000000000000000000000", headers=_headers("owner-d")).status_code == 404
    client.delete(f"/api/v1/artifacts/{artifact.artifact_id}", headers=_headers("owner-d"))
    assert client.delete(f"/api/v1/artifacts/{artifact.artifact_id}", headers=_headers("owner-d")).status_code == 404


def test_an_anonymous_artifact_delete_is_refused_the_stable_code(client, artifact_store):
    artifact = artifact_store("chart-e.png", "someone")

    response = client.delete(f"/api/v1/artifacts/{artifact.artifact_id}")

    assert response.status_code == 401
    assert response.json()["detail"] == "authentication_required"


def test_the_artifact_delete_is_audited_as_a_completion(client, account, artifact_store, monkeypatch):
    from app.api.v1 import artifacts as artifacts_api

    events = _capture(monkeypatch, artifacts_api)
    account("owner-f", "finance")
    artifact = artifact_store("chart-f.png", "owner-f")

    client.delete(f"/api/v1/artifacts/{artifact.artifact_id}", headers=_headers("owner-f"))

    completion = [event for event in events if event["reason"] == "artifact_deleted"]
    assert len(completion) == 1
    assert completion[0]["outcome"] == "allowed"
    assert completion[0]["resource"] == artifact.artifact_id
    assert completion[0]["before_summary"]["artifact_type"] == "chart"
    assert completion[0]["after_summary"]["file_removed"] is True


def test_a_registry_that_refuses_to_retire_is_reported_after_the_bytes_are_gone(client, account, artifact_store, monkeypatch):
    from app.api.v1 import artifacts as artifacts_api

    events = _capture(monkeypatch, artifacts_api)
    account("owner-g", "finance")
    artifact = artifact_store("chart-g.png", "owner-g")
    monkeypatch.setattr(artifact_store.registry, "soft_delete", lambda artifact_id: False)

    response = client.delete(f"/api/v1/artifacts/{artifact.artifact_id}", headers=_headers("owner-g"))

    # The honest answer is a failure: the record still says active while its file does not
    # exist, which is the residue this route exists to prevent. Nothing is reported as ok.
    assert response.status_code == 500
    assert response.json()["detail"] == "internal_error"
    assert artifact_store.registry.get(artifact.artifact_id).status == "active"
    assert not (artifact_store.root / "chart-g.png").exists()
    assert [(event["reason"], event["after_summary"]["stage"]) for event in events if event["outcome"] == "failed"] == [
        ("artifact_cleanup_incomplete", "registry")
    ]
