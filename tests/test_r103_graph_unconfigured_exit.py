"""R103 判据（跟进单 §44.1 / 业主裁定 D6）：图谱未部署不许谎报成存储故障。

四条钉子，全部走 TestClient 打真路由，不 grep 源码字符串：

* 未配 KNOWLEDGE_GRAPH_STORE_PATH 的生产进程，POST /api/v1/knowledge-graph/relations
  必须 409 且 detail 精确等于 knowledge_graph_unconfigured，不再 503 storage_read_only；
* 审计理由要能分辨「没配 / 权限不足 / 真只读」三件事，record_audit 最后一个参数不再通抄一枚；
* /api/v1/health/details 的图谱节与路由用同一个词（同一个 reason 值，而不是各写一份文案）；
* 对照用例：PermissionError 仍 403、ValueError 仍 400、开发态不得因此变 409，
  而真存储写失败仍须 503 —— 本单要求的是语义与事实相符，不是消灭 503。

全程离线：模型端口由 tests/conftest.py 的 R56 闸门拦下，健康快照的三个探针在本文件里换成
桩（与 tests/test_deployment_guards.py 同法），图谱与开放平台的存储落在 tmp_path。
"""
import pytest
from fastapi.testclient import TestClient

RELATIONS_PATH = "/api/v1/knowledge-graph/relations"
APPS_PATH = "/api/v1/apps"
HEALTH_PATH = "/api/v1/health/details"

#: A body the service accepts: every field carries a real source locator.
RELATION_BODY = {
    "source_entity": "制度",
    "relation": "规定",
    "target": "住宿费",
    "source": "制度.pdf 第3页",
}


def _headers(username: str) -> dict:
    from app.common.auth import create_token

    return {"Authorization": f"Bearer {create_token(username)}"}


def _offline_probes(monkeypatch) -> None:
    """Never open a socket from a health read: the probes are simulated instead."""
    from app.common import monitoring

    monkeypatch.setattr(monitoring, "_probe_ollama", lambda: {"status": "ok"})
    monkeypatch.setattr(monitoring, "_probe_postgres", lambda: {"status": "not_configured"})
    monkeypatch.setattr(monitoring, "_probe_redis", lambda: {"status": "not_configured"})


@pytest.fixture()
def client(monkeypatch):
    """A TestClient over the real app, with one account that may upload a relation."""
    from app.common import auth
    from app.main import app

    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": f"u-{username}",
            "username": username,
            "role": "staff",
            "department": "finance",
        },
    )
    return TestClient(app)


@pytest.fixture()
def audit_calls(monkeypatch):
    """Every audit line the intelligence routes record, in call order."""
    from app.api.v1 import intelligence

    calls: list[tuple] = []
    monkeypatch.setattr(intelligence, "record_audit", lambda *args, **kwargs: calls.append(args))
    return calls


def _denied_reasons(calls) -> list[str]:
    """The audit reasons behind refusals only; an allowed request is not evidence."""
    return [call[4] for call in calls if call[2] == "denied"]


def _mount_graph(monkeypatch, graph):
    """Swap in a graph built under this test environment, and hand it back.

    The route keeps a module-level KnowledgeGraph resolved at import time, so a test that
    only set the environment would still be answering from whatever the host shell happened
    to export. Every case below owns its instance instead.
    """
    from app.api.v1 import intelligence

    monkeypatch.setattr(intelligence, "_graph", graph)
    return graph


def _production_without_a_store(monkeypatch):
    """The D6 shape: production, and KNOWLEDGE_GRAPH_STORE_PATH never configured."""
    from app.knowledge_graph.service import KnowledgeGraph

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("KNOWLEDGE_GRAPH_STORE_PATH", raising=False)
    graph = _mount_graph(monkeypatch, KnowledgeGraph())
    assert graph._store_path is None and graph._store is None
    return graph


def _development_without_a_store(monkeypatch):
    """The same missing store, in a process that is allowed to keep a dictionary."""
    from app.knowledge_graph.service import KnowledgeGraph

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("KNOWLEDGE_GRAPH_STORE_PATH", raising=False)
    graph = _mount_graph(monkeypatch, KnowledgeGraph())
    assert graph._store_path is None and graph._store is None
    return graph


def _store_that_cannot_be_written(monkeypatch, tmp_path):
    """Production with a durable store named, and that store refusing the write."""
    from app.knowledge_graph.service import KnowledgeGraph

    def fail_upsert(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("KNOWLEDGE_GRAPH_STORE_PATH", str(tmp_path / "relations.json"))
    graph = _mount_graph(monkeypatch, KnowledgeGraph())
    assert graph._store is not None, "the durable store must be the one under test"
    monkeypatch.setattr(graph._store, "upsert", fail_upsert)
    return graph


def test_an_unconfigured_deployment_answers_409_with_a_code_of_its_own(client, monkeypatch, audit_calls):
    _production_without_a_store(monkeypatch)

    response = client.post(RELATIONS_PATH, json=RELATION_BODY, headers=_headers("r103-staff"))

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "knowledge_graph_unconfigured"
    # The outage stamp is gone from everything a caller can read: no 503, and no
    # "storage_read_only" to send an operator off to check a disk that is fine.
    assert "storage_read_only" not in response.text
    assert _denied_reasons(audit_calls) == ["knowledge_graph_unconfigured"]


def test_a_configured_store_that_fails_to_write_still_answers_503(client, monkeypatch, tmp_path, audit_calls):
    """The 503 that tells the truth survives this ticket."""
    _store_that_cannot_be_written(monkeypatch, tmp_path)

    response = client.post(RELATIONS_PATH, json=RELATION_BODY, headers=_headers("r103-staff"))

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "storage_read_only"
    assert _denied_reasons(audit_calls) == ["storage_read_only"]


def test_a_permission_refusal_keeps_403_and_the_audit_names_the_permission(client, monkeypatch, audit_calls):
    """The exit mapping is under test here; the service's own judgment is pinned by
    tests/test_knowledge_graph.py and tests/test_knowledge_graph_verification.py."""
    graph = _development_without_a_store(monkeypatch)

    def refuse(*args, **kwargs):
        # The literal add_relation raises when a writer carries no identity.
        raise PermissionError("authentication_required")

    monkeypatch.setattr(graph, "add_relation", refuse)

    response = client.post(RELATIONS_PATH, json=RELATION_BODY, headers=_headers("r103-staff"))

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "permission_denied"
    # The response keeps one stable code while the trail keeps the permission that was
    # missing, which is the half of "storage_read_only" that never used to be recorded.
    assert _denied_reasons(audit_calls) == ["authentication_required"]


def test_a_relation_without_a_source_still_answers_400(client, monkeypatch, audit_calls):
    _development_without_a_store(monkeypatch)

    response = client.post(
        RELATIONS_PATH, json={**RELATION_BODY, "source": "   "}, headers=_headers("r103-staff")
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "relation_source_required"
    assert _denied_reasons(audit_calls) == []


def test_development_keeps_its_in_memory_write_and_never_answers_409(client, monkeypatch):
    _development_without_a_store(monkeypatch)

    response = client.post(RELATIONS_PATH, json=RELATION_BODY, headers=_headers("r103-staff"))

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "candidate"


def test_health_details_and_the_route_answer_with_the_same_word(client, monkeypatch):
    _production_without_a_store(monkeypatch)
    _offline_probes(monkeypatch)

    health = client.get(HEALTH_PATH, headers=_headers("r103-staff"))
    assert health.status_code == 200, health.text
    section = health.json()["storage"]["subsystems"]["knowledge_graph"]

    posted = client.post(RELATIONS_PATH, json=RELATION_BODY, headers=_headers("r103-staff"))
    assert posted.status_code == 409, posted.text

    # One fact, one word: the reason the route emits is the reason health reports, and
    # both are read out of the same state object rather than written out twice.
    assert section["reason"] == posted.json()["detail"] == "knowledge_graph_unconfigured"
    assert section["durable"] is False


def test_the_three_refusals_leave_three_different_audit_reasons(client, monkeypatch, tmp_path, audit_calls):
    """判据 2: whoever reads the trail has to be able to tell the cases apart."""
    _production_without_a_store(monkeypatch)
    assert client.post(RELATIONS_PATH, json=RELATION_BODY, headers=_headers("r103-staff")).status_code == 409

    graph = _development_without_a_store(monkeypatch)

    def refuse(*args, **kwargs):
        raise PermissionError("permission_denied")

    monkeypatch.setattr(graph, "add_relation", refuse)
    assert client.post(RELATIONS_PATH, json=RELATION_BODY, headers=_headers("r103-staff")).status_code == 403

    _store_that_cannot_be_written(monkeypatch, tmp_path)
    assert client.post(RELATIONS_PATH, json=RELATION_BODY, headers=_headers("r103-staff")).status_code == 503

    reasons = _denied_reasons(audit_calls)
    assert reasons == ["knowledge_graph_unconfigured", "permission_denied", "storage_read_only"]
    assert len(set(reasons)) == 3


def test_open_platform_registration_keeps_503_for_a_real_store_failure(client, monkeypatch, tmp_path):
    """判据 2 的核对结论钉成用例：那枚 503 说的是真话，本单不动它。"""
    from app.common import auth, open_platform

    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": f"u-{username}",
            "username": username,
            "role": "admin",
            "department": "",
        },
    )
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", str(tmp_path / "apps.json"))
    open_platform.configure_app_store(str(tmp_path / "apps.json"))
    store = open_platform._STORE["store"]
    assert store is not None

    def fail_upsert(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(store, "upsert", fail_upsert)
    try:
        response = client.post(
            APPS_PATH,
            json={"app_name": "r103-probe", "allowed_actions": ["query"]},
            headers=_headers("r103-admin"),
        )
    finally:
        # Leave the registry where the suite expects it: an empty value falls back to
        # memory, which is what every other case here assumes.
        open_platform.configure_app_store("")

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "storage_read_only"
