from types import SimpleNamespace
def test_generated_chart_is_readable_by_owner_with_primary_department(monkeypatch, tmp_path):
    from app.agents.contracts import Principal, ResourceScope
    from app.agents.tools import _start_calculation
    from app.storage import datasets
    from app.storage import calculations
    from app.storage.artifacts import ArtifactRegistry, artifact_sources_allowed
    principal = Principal.from_user({
        "id": "finance-owner", "username": "finance-owner", "role": "manager",
        "department": "finance", "department_ids": [],
    })
    dataset = SimpleNamespace(version_id="dataset:v1", classification="internal")
    source_scope = ResourceScope(resource_type="dataset", resource_id="dataset",
        owner_id=principal.user_id, department_ids=["finance"], classification="internal",
        version_id="dataset:v1")
    monkeypatch.setattr(datasets.dataset_registry, "get_active_by_filename", lambda _: dataset)
    monkeypatch.setattr(datasets.dataset_registry, "scope_for_version", lambda _: source_scope)
    saved = {}

    def start_run(**values):
        saved.update(values)
        return {"calculation_run_id": "calc-primary-department"}
    monkeypatch.setattr(calculations.calculation_storage, "start_run", start_run)
    monkeypatch.setattr(calculations.calculation_storage, "get", lambda _: {
        "calculation_run_id": "calc-primary-department", "owner_id": principal.user_id,
        "dataset_version_id": "dataset:v1", "status": "completed", "parameters": saved["parameters"],
    })
    run_id = _start_calculation({"configurable": {"principal": principal}}, "finance.csv", "按月分析", operation="analyze")
    chart_path = tmp_path / "finance-chart.png"
    chart_path.write_bytes(b"chart")
    chart = ArtifactRegistry(root=tmp_path).register(chart_path, artifact_type="chart",
        principal=principal, source_version_id="dataset:v1", calculation_run_ids=[run_id])
    assert artifact_sources_allowed(chart, principal)
    saved["parameters"]["scope"]["department_ids"] = []  # previously saved calculation
    assert artifact_sources_allowed(chart, principal)
    moved = Principal.from_user({"id": principal.user_id, "username": principal.username,
        "role": "manager", "department": "sales"})
    assert not artifact_sources_allowed(chart, moved)
