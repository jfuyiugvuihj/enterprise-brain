from fastapi.testclient import TestClient
from test_alert_scan_scope import alert_pg, calculation_postgres


def _headers(username: str) -> dict[str, str]:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _user(username: str, department: str) -> dict[str, str]:
    return {
        "id": username,
        "username": username,
        "role": "manager",
        "department": department,
    }


def _registry(monkeypatch, tmp_path):
    from app.api.v1 import data
    from app.storage import datasets
    from app.storage.datasets import DatasetRegistry

    registry = DatasetRegistry(
        root=tmp_path,
        metadata_path=tmp_path / "dataset-metadata.json",
    )
    monkeypatch.setattr(data, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(data, "dataset_registry", registry)
    monkeypatch.setattr(datasets, "dataset_registry", registry)
    return registry


def test_dataset_routes_enforce_registered_resource_scope(monkeypatch, tmp_path):
    from app.agents.contracts import Principal
    from app.common import auth
    from app.main import app

    registry = _registry(monkeypatch, tmp_path)
    data_file = tmp_path / "finance.csv"
    data_file.write_text("department,revenue\nfinance,100\n", encoding="utf-8")
    registry.register(
        data_file,
        principal=Principal.from_user(_user("finance-manager", "finance")),
    )
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: _user(username, "hr" if username == "hr-manager" else "finance"),
    )

    client = TestClient(app)
    finance_headers = _headers("finance-manager")
    hr_headers = _headers("hr-manager")

    owner_list = client.get("/api/v1/data-files", headers=finance_headers)
    assert owner_list.status_code == 200
    assert [item["filename"] for item in owner_list.json()["files"]] == ["finance.csv"]
    assert owner_list.json()["files"][0]["dataset_id"]
    assert client.get("/api/v1/data-files", headers=hr_headers).json()["files"] == []
    assert client.get(
        "/api/v1/data-files/finance.csv/preview",
        headers=finance_headers,
    ).status_code == 200
    assert client.get(
        "/api/v1/data-files/finance.csv/file",
        headers=finance_headers,
    ).status_code == 200
    assert client.get(
        "/api/v1/data-files/finance.csv/preview",
        headers=hr_headers,
    ).status_code == 403
    assert client.get(
        "/api/v1/data-files/finance.csv/file",
        headers=hr_headers,
    ).status_code == 403


def test_unregistered_dataset_files_are_not_exposed(monkeypatch, tmp_path):
    from app.common import auth
    from app.main import app

    _registry(monkeypatch, tmp_path)
    (tmp_path / "legacy.csv").write_text("name,value\nlegacy,1\n", encoding="utf-8")
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, "finance"))

    client = TestClient(app)
    headers = _headers("finance-manager")

    assert client.get("/api/v1/data-files", headers=headers).json()["files"] == []
    assert client.get(
        "/api/v1/data-files/legacy.csv/preview",
        headers=headers,
    ).status_code == 404
    assert client.get(
        "/api/v1/data-files/legacy.csv/file",
        headers=headers,
    ).status_code == 404


def test_failed_dataset_upload_does_not_publish_metadata(monkeypatch, tmp_path):
    from app.api.v1 import data
    from app.common import auth
    from app.main import app

    registry = _registry(monkeypatch, tmp_path)
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, "finance"))
    monkeypatch.setattr(
        data,
        "load_excel",
        lambda path: (_ for _ in ()).throw(ValueError("parse failed")),
    )

    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/upload-excel",
        headers=_headers("finance-manager"),
        files={"file": ("bad.csv", b"not,a,valid,dataset", "text/csv")},
    )

    assert response.status_code == 500
    assert registry.get_active_by_filename("bad.csv") is None
    assert not (tmp_path / "bad.csv").exists()


def test_upload_excel_refuses_a_departmentless_owner_with_a_stable_code(
    monkeypatch, tmp_path
):
    from app.common import auth
    from app.main import app

    _registry(monkeypatch, tmp_path)
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, ""))

    response = TestClient(app).post(
        "/api/v1/upload-excel",
        headers=_headers("nobody-admin"),
        files={"file": ("solo.csv", b"a,b\n1,2\n", "text/csv")},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "department_scope_required"
    assert not (tmp_path / "solo.csv").exists()


def test_reupload_without_a_completed_index_keeps_the_original_version(monkeypatch, tmp_path):
    import hashlib
    from app.api.v1 import data
    from app.common import auth
    from app.main import app

    registry = _registry(monkeypatch, tmp_path)
    monkeypatch.setattr(auth, "get_user", lambda username: _user(username, "finance"))

    async def skip_index(**kwargs):
        return {"status": "skipped"}

    monkeypatch.setattr(data, "index_dataset_copy", skip_index)
    client = TestClient(app)
    headers = _headers("finance-manager")
    first_bytes = b"department,revenue\nfinance,100\n"
    second_bytes = b"department,revenue\nfinance,2000\n"
    first = client.post(
        "/api/v1/upload-excel",
        headers=headers,
        data={"classification": "2"},
        files={"file": ("finance.csv", first_bytes, "text/csv")},
    )
    assert first.status_code == 200, first.text
    second = client.post(
        "/api/v1/upload-excel",
        headers=headers,
        data={"new_version": "true"},
        files={"file": ("finance.csv", second_bytes, "text/csv")},
    )
    assert second.status_code == 503, second.text
    assert second.json()['detail'] == 'dataset_update_not_published'
    downgrade = client.post(
        "/api/v1/upload-excel", headers=headers,
        data={"new_version": "true", "classification": "1"},
        files={"file": ("finance.csv", b"department,revenue\nfinance,50\n", "text/csv")},
    )
    assert downgrade.status_code == 400

    dataset_id = first.json()["dataset_id"]
    versions = registry.versions(dataset_id)
    assert [version.dataset_version_id for version in versions] == [
        first.json()["version_id"]
    ]
    assert len({version.storage_key for version in versions}) == 1
    for version, expected in zip(versions, (first_bytes,)):
        from pathlib import Path

        assert Path(version.storage_key).read_bytes() == expected
        assert version.content_sha256 == hashlib.sha256(expected).hexdigest()

    listed = client.get("/api/v1/data-files", headers=headers)
    assert listed.status_code == 200
    assert [(item["filename"], item["size"], item["version_id"]) for item in listed.json()["files"]] == [
        ("finance.csv", len(first_bytes), first.json()["version_id"])
    ]
    current = client.get("/api/v1/data-files/finance.csv/file", headers=headers)
    assert current.status_code == 200
    assert current.content == first_bytes


def test_first_upload_refuses_classification_above_clearance_without_storing_bytes(monkeypatch, tmp_path):
    from app.api.v1 import data
    from app.common import auth
    from app.main import app

    registry = _registry(monkeypatch, tmp_path)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {**_user(username, "finance"), "role": "staff"},
    )

    async def skip_index(**kwargs):
        return {"status": "skipped"}

    monkeypatch.setattr(data, "index_dataset_copy", skip_index)
    response = TestClient(app).post(
        "/api/v1/upload-excel",
        headers=_headers("finance-staff"),
        data={"classification": "internal"},
        files={"file": ("finance.csv", b"department,revenue\nfinance,100\n", "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_classification"
    assert registry.get_active_by_filename("finance.csv") is None
    assert list(tmp_path.rglob("*.csv")) == []


def test_staff_upload_without_classification_uses_the_accessible_default(monkeypatch, tmp_path):
    from app.api.v1 import data
    from app.common import auth
    from app.main import app

    registry = _registry(monkeypatch, tmp_path)
    monkeypatch.setattr(auth, "get_user", lambda username: {**_user(username, "finance"), "role": "staff"})
    async def skip_index(**kwargs):
        return {"status": "skipped"}
    monkeypatch.setattr(data, "index_dataset_copy", skip_index)
    response = TestClient(app).post(
        "/api/v1/upload-excel", headers=_headers("finance-staff"),
        files={"file": ("staff.csv", b"department,revenue\nfinance,100\n", "text/csv")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["classification"] == registry.get_active_by_filename("staff.csv").classification
    assert response.json()["classification"] == "1"


def test_data_agent_tools_only_read_authorized_registered_datasets(monkeypatch, tmp_path):
    from app.agents.contracts import Principal
    from app.agents.tools import analyze_data, query_data
    from app.storage import datasets, calculations
    from app.storage.datasets import DatasetRegistry

    registry = DatasetRegistry(
        root=tmp_path,
        metadata_path=tmp_path / "dataset-metadata.json",
    )
    data_file = tmp_path / "finance.csv"
    data_file.write_text("department,revenue\nfinance,100\n", encoding="utf-8")
    registry.register(
        data_file,
        principal=Principal.from_user(_user("finance-manager", "finance")),
    )
    monkeypatch.setattr(datasets, "dataset_registry", registry)
    monkeypatch.setattr(calculations, "dataset_registry", registry)
    monkeypatch.setattr(
        "app.agents.tools._llm_pandas_code",
        lambda df, query: "df['revenue'].max()",
    )

    finance_config = {
        "configurable": {
            "id": "finance-manager",
            "username": "finance-manager",
            "role": "manager",
            "department": "finance",
            "data_filename": "finance.csv",
        }
    }
    hr_config = {
        "configurable": {
            "id": "hr-manager",
            "username": "hr-manager",
            "role": "manager",
            "department": "hr",
            "data_filename": "finance.csv",
        }
    }

    assert "100" in analyze_data.invoke("最高营收", config=finance_config)
    assert "100" in query_data.invoke({"query": "最高营收"}, config=finance_config)
    assert "department_scope_denied" in analyze_data.invoke("最高营收", config=hr_config)
    assert "department_scope_denied" in query_data.invoke({"query": "最高营收"}, config=hr_config)
