"""Run inside the backend container against real PG; remove only UUID-owned fixtures."""
import json
from uuid import uuid4

from app.agents.contracts import Principal
from app.storage.artifacts import artifact_registry
from app.storage.calculations import CalculationStorage, calculation_storage as storage
from app.storage.datasets import dataset_registry

uid = "v2-calculation-check-" + uuid4().hex
owner = Principal.from_user({"username": uid, "role": "manager", "department": "财务", "department_ids": ["财务"]})
admin = Principal.from_user({"username": uid + "-admin", "role": "admin", "department": "财务", "department_ids": ["财务"]})
peer = owner.model_copy(update={"user_id": uid + "-peer", "username": uid + "-peer"})
sales = owner.model_copy(update={"department": "销售", "department_ids": ["销售"]})
source = dataset_registry.root / (uid + ".csv")
output = artifact_registry.root / (uid + ".txt")
created, dataset, artifact = [], None, None
checks = {}


def check(name, condition):
    checks[name] = bool(condition)
    assert condition, name


def start(request="request-one"):
    row = storage.start_run(owner.user_id, dataset.version_id, request, {
        "session_id": uid + ":data", "trace_id": uid, "filename": source.name,
        "query": "仅统计已通过费用", "scope": {"department_ids": ["财务"], "classification": "internal"},
        "role": owner.role, "department": owner.department, "clearance": owner.clearance,
        "authorization_department_ids": sorted(owner.department_ids),
    })
    created.append(row["calculation_run_id"])
    return row["calculation_run_id"]


try:
    source.write_text("部门,金额\n财务,120\n财务,80\n", encoding="utf-8")
    dataset = dataset_registry.register(source, principal=admin, visibility="department")
    run_id = start()
    check("running_is_persisted", CalculationStorage().get(run_id)["status"] == "running")
    result = {"rows": 2, "numeric_statistics": [{"name": "金额", "sum": 200}], "filter_note": "已通过"}
    storage.complete_run(run_id, result)
    check("fresh_reader_preserves_result", CalculationStorage().get(run_id)["result"] == result)
    check("same_finish_is_idempotent", storage.complete_run(run_id, result)["result"] == result)
    refused = False
    try:
        storage.complete_run(run_id, {"rows": 99})
    except ValueError:
        refused = True
    check("finished_result_is_immutable", refused and storage.get(run_id)["result"] == result)
    check("owner_and_admin_can_read", storage.can_view(storage.get(run_id), owner) and storage.can_view(storage.get(run_id), admin))
    check("same_department_peer_is_denied", not storage.can_view(storage.get(run_id), peer))
    check("changed_department_is_denied", not storage.can_view(storage.get(run_id), sales))
    check("changed_role_is_denied", not storage.can_view(storage.get(run_id), owner.model_copy(update={"roles": ["staff"], "clearance": 1})))
    check("trace_and_request_filter", [r["calculation_run_id"] for r in storage.list_for(owner, trace_id=uid, request_id="request-one")] == [run_id])
    output.write_text("verified amount: 200", encoding="utf-8")
    artifact = artifact_registry.register(output, artifact_type="report", principal=owner,
        session_id=uid + ":export", request_id="request-one", calculation_run_ids=[run_id])
    check("explicit_artifact_link", storage.with_artifacts(storage.get(run_id), owner)["artifacts"][0]["artifact_id"] == artifact.artifact_id)
    artifact_registry.soft_delete(artifact.artifact_id)
    check("retired_artifact_is_unavailable", storage.with_artifacts(storage.get(run_id), owner)["artifacts"] == [])
    failed = start("request-failed")
    storage.fail_run(failed, "validation_error")
    check("failure_has_terminal_reason", storage.get(failed)["status"] == "failed" and storage.get(failed)["error_code"] == "validation_error")
    with artifact_registry.persistence.connection_factory() as conn:
        conn.execute("UPDATE datasets SET classification='confidential' WHERE dataset_id=%s", (dataset.dataset_id,))
        conn.commit()
    check("tightened_source_scope_is_enforced", not storage.can_view(storage.get(run_id), owner))
    with artifact_registry.persistence.connection_factory() as conn:
        conn.execute("UPDATE datasets SET classification='internal' WHERE dataset_id=%s", (dataset.dataset_id,))
        conn.commit()
    dataset_registry.soft_delete(dataset.dataset_id)
    check("historical_calculation_survives_input_retirement", storage.can_view(storage.get(run_id), owner) and storage.get(run_id)["result"] == result)
    print(json.dumps({"checks": checks, "ok": all(checks.values())}, ensure_ascii=False))
finally:
    with artifact_registry.persistence.connection_factory() as conn:
        if artifact:
            conn.execute("DELETE FROM artifacts WHERE artifact_id=%s", (artifact.artifact_id,))
        if created:
            conn.execute("DELETE FROM calculation_runs WHERE calculation_run_id=ANY(%s)", (created,))
        if dataset:
            conn.execute("UPDATE datasets SET current_version_id=NULL WHERE dataset_id=%s", (dataset.dataset_id,))
            conn.execute("DELETE FROM dataset_versions WHERE dataset_id=%s", (dataset.dataset_id,))
            conn.execute("DELETE FROM datasets WHERE dataset_id=%s", (dataset.dataset_id,))
        conn.commit()
    source.unlink(missing_ok=True)
    output.unlink(missing_ok=True)
