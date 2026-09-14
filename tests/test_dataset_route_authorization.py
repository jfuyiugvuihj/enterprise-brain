from fastapi.testclient import TestClient


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


def test_data_agent_tools_only_read_authorized_registered_datasets(monkeypatch, tmp_path):
    from app.agents.contracts import Principal
    from app.agents.tools import analyze_data, query_data
    from app.storage import datasets
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
