"""HTTP regression for raw table downloads; live account/PG checks remain separate."""
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.mark.parametrize("extension", ["csv", "xlsx"])
def test_raw_download_checks_all_rows_on_both_exits(monkeypatch, tmp_path, extension):
    from app.agents.contracts import Principal
    from app.api.v1 import chat, data
    from app.common.audit import get_audit_events
    from app.storage.datasets import DatasetRegistry

    own = pd.DataFrame({"部门": ["finance"], "金额": [200]})
    foreign = pd.DataFrame({"部门": ["sales"], "金额": [777]})
    path = tmp_path / f"scope.{extension}"
    if extension == "csv":
        pd.concat([own, foreign]).to_csv(path, index=False)
    else:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            own.to_excel(writer, sheet_name="finance", index=False)
            foreign.to_excel(writer, sheet_name="sales", index=False)
            writer.book["sales"].sheet_state = "hidden"
    original = path.read_bytes()
    principal = Principal.from_user(
        {"id": "manager", "username": "manager", "role": "manager", "department": "finance"}
    )
    registry = DatasetRegistry(root=tmp_path)
    record = registry.register(path, principal=principal)
    monkeypatch.setattr(data, "dataset_registry", registry)
    monkeypatch.setattr(chat, "list_document_versions", lambda *a, **k: [{
        "filename": path.name, "storage_path": str(path), "classification": "internal",
        "department": "finance", "owner_id": principal.user_id,
    }])
    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.principal = principal
        return await call_next(request)

    app.include_router(data.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    client = TestClient(app)
    preview = client.get(f"/api/v1/data-files/{path.name}/preview")
    assert preview.status_code == 200
    assert preview.json()["rows"] == [{"部门": "finance", "金额": 200}]
    for route in ("data-files", "documents"):
        for inline in (False, True):
            denied = client.get(f"/api/v1/{route}/{path.name}/file", params={"inline": inline})
            assert denied.status_code == 403, denied.text[:150]
            assert denied.json()["detail"] == "row_scope_denied"
            assert "777" not in denied.text
    audits = get_audit_events(action="resource:download", outcome="denied")
    assert any(e.get("resource") == record.dataset_id for e in audits)
    assert any(e.get("resource") == path.name for e in audits)
    principal = Principal.from_user(
        {"id": "admin", "username": "admin", "role": "admin", "department": "hq"}
    )
    for route in ("data-files", "documents"):
        allowed = client.get(f"/api/v1/{route}/{path.name}/file")
        assert allowed.status_code == 200
        assert allowed.content == original
    assert path.read_bytes() == original


def test_entirely_visible_csv_remains_downloadable(monkeypatch, tmp_path):
    from app.agents.contracts import Principal
    from app.api.v1 import data
    from app.storage.datasets import DatasetRegistry

    path = tmp_path / "own.csv"
    path.write_text("部门,金额\nfinance,200\n", encoding="utf-8")
    principal = Principal.from_user(
        {"id": "manager", "username": "manager", "role": "manager", "department": "finance"}
    )
    registry = DatasetRegistry(root=tmp_path)
    registry.register(path, principal=principal)
    monkeypatch.setattr(data, "dataset_registry", registry)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request, call_next):
        request.state.principal = principal
        return await call_next(request)

    app.include_router(data.router, prefix="/api/v1")
    response = TestClient(app).get("/api/v1/data-files/own.csv/file")
    assert response.status_code == 200
    assert response.content == path.read_bytes()
