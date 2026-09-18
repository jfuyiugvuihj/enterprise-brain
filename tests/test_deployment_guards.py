import json

from pathlib import Path


def test_deployment_files_use_private_model_and_local_services_only():
    compose_files = [Path("docker-compose.yml"), Path("deploy/docker-compose.server.yml"), Path("deploy/.env.server.example"), Path(".env.example")]
    texts = "\n".join(path.read_text(encoding="utf-8") for path in compose_files if path.exists())

    assert "OPENAI_API_KEY" not in texts
    assert "ANTHROPIC_API_KEY" not in texts
    assert "http://ollama:11434" in texts or "http://host.docker.internal:11434" in texts
    assert "postgres" in texts.lower()
    assert "redis" in texts.lower()


def test_deployment_example_does_not_expose_public_model_provider_name():
    text = Path("deploy/.env.server.example").read_text(encoding="utf-8")
    assert "gpt-4" not in text.lower()
    assert "claude" not in text.lower()


# ----------------------------------------------------------------------------------
# S6: memory fallback and multi-instance boundaries (docs/deployment/memory-fallback.md)
# ----------------------------------------------------------------------------------
from pathlib import Path

import pytest


def _durable(mode):
    return {
        "storage_mode": mode,
        "durable": True,
        "shared_across_processes": True,
        "protection": "none",
        "detail": "simulated persistent backend",
    }


def _offline_probes(monkeypatch):
    """Never open a socket from a guard test: the probes are simulated instead."""
    from app.common import monitoring

    monkeypatch.setattr(monitoring, "_probe_ollama", lambda: {"status": "ok"})
    monkeypatch.setattr(monitoring, "_probe_postgres", lambda: {"status": "not_configured"})
    monkeypatch.setattr(monitoring, "_probe_redis", lambda: {"status": "not_configured"})


def _without_database(monkeypatch):
    """Point every subsystem at the process-local store it would actually be using."""
    from app.common import auth, open_platform
    from app.memory import long_term, profile

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("KNOWLEDGE_GRAPH_STORE_PATH", "")
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", "")
    monkeypatch.setattr(auth, "psycopg", None, raising=False)
    monkeypatch.setattr(auth, "_db_ready", False)
    monkeypatch.setattr(auth, "_MEM_USERS", {"admin": {"id": 1, "username": "admin", "password_hash": "x", "role": "admin", "department": ""}})
    monkeypatch.setattr(long_term, "psycopg", None, raising=False)
    monkeypatch.setattr(profile, "_database_available", lambda: False, raising=False)
    open_platform.configure_app_store("")


def _in_memory_stores(monkeypatch, environment):
    """Simulate an install without PostgreSQL, in either environment."""
    from app.common import auth, open_platform
    from app.memory import long_term, profile

    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("KNOWLEDGE_GRAPH_STORE_PATH", "")
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", "")
    monkeypatch.setattr(auth, "psycopg", None, raising=False)
    monkeypatch.setattr(auth, "_db_ready", False)
    monkeypatch.setattr(long_term, "psycopg", None, raising=False)
    monkeypatch.setattr(profile, "_database_available", lambda: False, raising=False)
    open_platform.configure_app_store("")


def _persistent_production(monkeypatch):
    """Simulate a production install whose durable stores are all reachable."""
    from app.common import auth, monitoring, open_platform
    from app.knowledge_graph import service as graph_service
    from app.memory import long_term, profile

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(auth, "user_storage_state", lambda: _durable("postgres"), raising=False)
    monkeypatch.setattr(long_term, "memory_storage_state", lambda: _durable("postgres"), raising=False)
    monkeypatch.setattr(profile, "profile_storage_state", lambda: _durable("postgres"), raising=False)
    monkeypatch.setattr(graph_service, "knowledge_graph_storage_state", lambda: _durable("json"), raising=False)
    monkeypatch.setattr(open_platform, "app_registry_storage_state", lambda: _durable("json"), raising=False)
    monkeypatch.setattr(monitoring, "queue_storage_state", lambda: _durable("redis"), raising=False)


def test_health_snapshot_reports_a_storage_mode_for_every_subsystem(monkeypatch):
    from app.common.monitoring import build_health_snapshot

    _offline_probes(monkeypatch)
    subsystems = build_health_snapshot()["storage"]["subsystems"]

    assert set(subsystems) == {
        "queue",
        "users",
        "memories",
        "user_profiles",
        "knowledge_graph",
        "open_platform_apps",
    }
    for name, state in subsystems.items():
        assert state["storage_mode"] in {"postgres", "json", "redis", "memory", "unavailable"}, name
        assert isinstance(state["durable"], bool), name
        assert isinstance(state["shared_across_processes"], bool), name
        assert state["detail"], name


def test_production_without_a_database_is_never_reported_ok(monkeypatch):
    from app.common.monitoring import build_health_snapshot

    _offline_probes(monkeypatch)
    _without_database(monkeypatch)
    snapshot = build_health_snapshot()

    assert snapshot["status"] != "ok"
    assert snapshot["environment"] == "production"
    assert "users_store_not_persistent" in snapshot["problems"]
    assert {"memories_read_only", "user_profiles_read_only"} <= set(snapshot["problems"])
    assert {"knowledge_graph_read_only", "open_platform_apps_read_only"} <= set(snapshot["problems"])
    assert "postgres_not_configured" in snapshot["problems"]
    assert snapshot["storage"]["durable"] == []
    for name in ("users", "memories", "user_profiles", "knowledge_graph", "open_platform_apps"):
        assert snapshot["storage"]["subsystems"][name]["storage_mode"] == "unavailable", name


def test_production_with_persistent_stores_reports_ok(monkeypatch):
    from app.common.monitoring import build_health_snapshot

    monkeypatch.setattr(
        "app.common.monitoring._probe_postgres",
        lambda: {"status": "ok", "pgvector": True, "migration_ledger": True},
    )
    monkeypatch.setattr("app.common.monitoring._probe_ollama", lambda: {"status": "ok"})
    monkeypatch.setattr("app.common.monitoring._probe_redis", lambda: {"status": "ok"})
    _persistent_production(monkeypatch)
    snapshot = build_health_snapshot()

    assert snapshot["problems"] == []
    assert snapshot["status"] == "ok"


class _TagsResponse:
    def __init__(self, models):
        self.status = 200
        self._body = json.dumps({"models": models}).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _probe_local_models(monkeypatch, models):
    """Serve a fixed Ollama registry to the probe without opening a socket."""
    from app.common import monitoring

    monkeypatch.setattr(
        monitoring, "urlopen", lambda url, timeout=None: _TagsResponse(models)
    )


def test_a_pinned_model_that_was_never_pulled_is_reported_as_a_fault(monkeypatch):
    from app.common.monitoring import build_health_snapshot

    _persistent_production(monkeypatch)
    monkeypatch.setattr(
        "app.common.monitoring._probe_postgres",
        lambda: {"status": "ok", "pgvector": True, "migration_ledger": True},
    )
    monkeypatch.setattr("app.common.monitoring._probe_redis", lambda: {"status": "ok"})
    _probe_local_models(monkeypatch, [{"name": "nomic-embed-text:latest"}])
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen2.5:14b")

    snapshot = build_health_snapshot()

    assert snapshot["dependencies"]["ollama"]["status"] == "ok"
    assert snapshot["dependencies"]["ollama"]["model_present"] is False
    assert "model_not_available" in snapshot["problems"]
    assert snapshot["status"] == "degraded"


def test_a_pinned_model_that_is_present_keeps_the_health_report_clean(monkeypatch):
    from app.common.monitoring import build_health_snapshot

    _persistent_production(monkeypatch)
    monkeypatch.setattr(
        "app.common.monitoring._probe_postgres",
        lambda: {"status": "ok", "pgvector": True, "migration_ledger": True},
    )
    monkeypatch.setattr("app.common.monitoring._probe_redis", lambda: {"status": "ok"})
    # R21 (dbd19c2) 之后，"报告干净"还要求向量模型本身在位：只桩聊天模型会让
    # _embedding_state() 如实报 embedding_model_missing。补桩而不放宽任何断言。
    _probe_local_models(
        monkeypatch,
        [{"name": "qwen2.5:14b"}, {"name": "nomic-embed-text:latest"}],
    )
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen2.5")

    snapshot = build_health_snapshot()

    assert snapshot["dependencies"]["ollama"]["model_present"] is True
    assert snapshot["problems"] == []
    assert snapshot["status"] == "ok"


def test_an_unpinned_model_choice_is_not_claimed_missing(monkeypatch):
    from app.common.monitoring import build_health_snapshot

    _persistent_production(monkeypatch)
    monkeypatch.setattr(
        "app.common.monitoring._probe_postgres",
        lambda: {"status": "ok", "pgvector": True, "migration_ledger": True},
    )
    monkeypatch.setattr("app.common.monitoring._probe_redis", lambda: {"status": "ok"})
    _probe_local_models(monkeypatch, [])
    monkeypatch.delenv("LOCAL_MODEL_NAME", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    snapshot = build_health_snapshot()

    assert "model_present" not in snapshot["dependencies"]["ollama"]
    assert "model_not_available" not in snapshot["problems"]


def test_development_memory_fallback_stays_available_but_is_labelled_as_memory(monkeypatch):
    from app.common.monitoring import build_health_snapshot

    _offline_probes(monkeypatch)
    _in_memory_stores(monkeypatch, "development")
    snapshot = build_health_snapshot()

    assert snapshot["status"] == "ok"
    memory = set(snapshot["storage"]["single_instance_only"])
    assert {"users", "memories", "user_profiles", "knowledge_graph", "open_platform_apps"} <= memory
    for name in memory:
        state = snapshot["storage"]["subsystems"][name]
        assert state["durable"] is False and state["shared_across_processes"] is False


def test_guard_refuses_startup_without_a_user_store_but_degrades_the_rest(monkeypatch):
    from app.common.monitoring import enforce_production_storage_guard

    _without_database(monkeypatch)
    with pytest.raises(RuntimeError, match="refused startup"):
        enforce_production_storage_guard()

    monkeypatch.setattr("app.common.auth.user_storage_state", lambda: _durable("postgres"))
    report = enforce_production_storage_guard()

    assert report["enforced"] is True
    assert report["refused"] == []
    # The reliable queue already fails closed instead of degrading, so it is reported as
    # disabled rather than read-only protected.
    assert report["disabled"] == ["queue"]
    assert set(report["read_only"]) == {"memories", "user_profiles", "knowledge_graph", "open_platform_apps"}


def test_guard_is_a_no_op_in_development(monkeypatch):
    from app.common.monitoring import enforce_production_storage_guard

    monkeypatch.setenv("APP_ENV", "development")
    report = enforce_production_storage_guard()

    assert report["enforced"] is False


def test_production_user_table_denies_identity_operations(monkeypatch):
    from app.common import auth

    _without_database(monkeypatch)

    assert auth.user_storage_state()["protection"] == "refuse_start"
    assert auth.verify_password("admin", "x") is False
    assert auth.get_user("admin") is None
    assert auth.list_users() == []
    assert auth.create_user("ghost", "secret123") == (False, "production_user_store_unavailable")
    assert auth.upsert_sso_user("ghost") == (False, "production_user_store_unavailable")
    assert auth.delete_user(1) is False


def test_development_user_table_still_authenticates(monkeypatch):
    from app.common import auth

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(auth, "psycopg", None, raising=False)
    monkeypatch.setattr(auth, "_db_ready", False)
    monkeypatch.setattr(auth, "_MEM_USERS", {})
    assert auth.user_storage_state()["storage_mode"] == "memory"
    ok, _ = auth.create_user("dev-user", "dev-secret", role="staff")
    assert ok is True
    assert auth.get_user("dev-user")["role"] == "staff"


def test_public_paths_are_not_widened_and_anonymous_requests_are_rejected():
    from app.common.auth import PUBLIC_PATHS

    for path in ("/api/v1/apps", "/api/v1/health/details", "/api/v1/users", "/api/v1/knowledge-graph/relations"):
        assert path not in PUBLIC_PATHS

    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    for path in ("/api/v1/users", "/api/v1/health/details", "/api/v1/knowledge-graph/relations", "/api/v1/apps"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/v1/apps", json={"app_name": "x", "allowed_actions": ["query"]}).status_code == 401


def test_health_details_exposes_the_storage_block(monkeypatch):
    from fastapi.testclient import TestClient

    from app.common import auth, monitoring
    from app.main import app

    _offline_probes(monkeypatch)
    client = TestClient(app)
    response = client.get("/api/v1/health/details", headers={"Authorization": f"Bearer {auth.create_token('admin')}"})

    assert response.status_code == 200
    body = response.json()
    assert set(body["storage"]["subsystems"]) >= {"users", "memories", "user_profiles", "knowledge_graph", "open_platform_apps", "queue"}
    assert body["queue"]["storage_mode"] == monitoring.queue_storage_state()["storage_mode"]


def _principal(role="admin", username=None):
    from app.agents.contracts import Principal

    username = username or f"user-{role}"
    return Principal.from_user({"id": username, "username": username, "role": role, "department": "it"})


def _request_for(principal):
    from types import SimpleNamespace

    return SimpleNamespace(state=SimpleNamespace(username=principal.username, principal=principal), headers={})


def test_app_registration_requires_an_admin_and_is_audited(monkeypatch, tmp_path):
    import asyncio
    from pathlib import Path as _Path

    from fastapi import HTTPException

    from app.api.v1 import open_platform as routes
    from app.common import audit, open_platform

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", str(tmp_path / "apps.json"))
    open_platform.configure_app_store(str(tmp_path / "apps.json"))
    audit.clear_audit_events()
    try:
        with pytest.raises(HTTPException) as denied:
            asyncio.run(
                routes.register_open_application(
                    routes.ApplicationRegisterRequest(app_name="oa", allowed_actions=["query"]),
                    _request_for(_principal("staff", "carol")),
                )
            )
        assert denied.value.status_code == 403

        issued = asyncio.run(
            routes.register_open_application(
                routes.ApplicationRegisterRequest(app_name="oa", allowed_actions=["query"]),
                _request_for(_principal("admin", "root")),
            )
        )
        assert issued["app_id"] and issued["secret"]
        assert issued["storage_mode"] == "json"

        with pytest.raises(HTTPException) as invalid:
            asyncio.run(
                routes.register_open_application(
                    routes.ApplicationRegisterRequest(app_name="oa", allowed_actions=[]),
                    _request_for(_principal("admin", "root")),
                )
            )
        assert invalid.value.status_code == 400

        actions = [(event["action"], event["outcome"]) for event in audit.get_audit_events()]
        assert ("open_platform:app_register", "denied") in actions
        assert ("open_platform:app_register", "allowed") in actions
        assert ("users:manage", "denied") in actions

        listed = asyncio.run(routes.list_open_applications(_request_for(_principal("admin", "root"))))
        assert [item["app_name"] for item in listed["applications"]] == ["oa"]
        assert "secret" not in listed["applications"][0]
    finally:
        audit.clear_audit_events()
        open_platform.configure_app_store("")


def test_open_platform_registration_is_persisted_and_shared_across_instances(monkeypatch, tmp_path):
    from app.common import open_platform
    from app.common.monitoring import ProductionReadOnlyProtection

    store = tmp_path / "apps.json"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", str(store))
    open_platform.configure_app_store(str(store))
    try:
        issued = open_platform.register_application("crm", allowed_actions=["query", "dashboard"])
        # A second worker starts with an empty cache and must still accept the secret.
        open_platform.clear_app_registry()
        assert [item["app_name"] for item in open_platform.list_applications()] == ["crm"]
        assert open_platform.app_registry_storage_state()["shared_across_processes"] is True

        timestamp = str(int(__import__("time").time()))
        body = "{}"
        headers = {
            "x-open-app-id": issued["app_id"],
            "x-open-timestamp": timestamp,
            "x-open-signature": open_platform.build_request_signature(issued["app_id"], issued["secret"], body, timestamp),
        }
        principal, record = open_platform.verify_open_request(headers, body, required_action="query")
        assert record["app_name"] == "crm"
        assert principal.username == "crm"
    finally:
        open_platform.configure_app_store("")

    monkeypatch.setenv("OPEN_PLATFORM_APP_STORE_PATH", "")
    open_platform.configure_app_store("")
    assert open_platform.app_registry_storage_state()["protection"] == "read_only"
    with pytest.raises(ProductionReadOnlyProtection):
        open_platform.register_application("crm", allowed_actions=["query"])


def test_knowledge_graph_relations_are_shared_through_the_durable_store(tmp_path, monkeypatch):
    from app.knowledge_graph.service import KnowledgeGraph

    monkeypatch.setenv("APP_ENV", "development")
    store = str(tmp_path / "relations.json")
    author = _principal("staff", "graph-author")
    first = KnowledgeGraph(store_path=store)
    second = KnowledgeGraph(store_path=store)

    record = first.add_relation("travel", "caps", "800", "policy.pdf p3", principal=author)
    assert first.storage_state()["storage_mode"] == "json"
    assert [item["relation_id"] for item in second.query("travel", principal=author)] == [record.relation_id]
    assert second.confirm(record.relation_id, principal=author) is True
    assert first.query("travel", principal=author)[0]["status"] == "confirmed"
    assert Path(store).exists()


def test_knowledge_graph_refuses_an_in_memory_write_in_production(monkeypatch, tmp_path):
    from app.knowledge_graph.service import KnowledgeGraph
    from app.common.monitoring import ProductionReadOnlyProtection

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("KNOWLEDGE_GRAPH_STORE_PATH", "")
    graph = KnowledgeGraph()

    with pytest.raises(ProductionReadOnlyProtection):
        graph.add_relation("a", "b", "c", "doc.pdf p1", principal=_principal("staff", "graph-author"))
    assert graph._relations == {}
    assert graph.storage_state() == {
        "storage_mode": "unavailable",
        "durable": False,
        "shared_across_processes": False,
        "protection": "read_only",
        "detail": "KNOWLEDGE_GRAPH_STORE_PATH is not configured; relation writes are refused",
    }


def test_long_term_memory_refuses_the_process_local_table_in_production(
    monkeypatch, offline_ollama_embeddings
):
    # R56：long_term.remember() 会经 app/memory/long_term.py:131 构造 OllamaEmbeddings，
    # 打的是 localhost:11434。fixture 把它钉成同一条零向量兜底，测试期不开 socket。
    from app.common import auth
    from app.memory import long_term, profile

    _without_database(monkeypatch)

    with pytest.raises(RuntimeError, match="psycopg is required in production"):
        long_term._ensure()
    assert long_term.remember("u-1", "prefers bar charts") is False
    assert long_term._MEMORY == {}
    assert long_term.recall("u-1", "bar charts") == []
    assert profile.upsert_profile("u-1", department="it") is False
    assert profile._MEM_PROFILES == {}
    assert long_term.memory_storage_state()["protection"] == "read_only"
    assert profile.profile_storage_state()["protection"] == "read_only"


def test_development_long_term_memory_still_uses_its_dictionary(
    monkeypatch, offline_ollama_embeddings
):
    # R56：development 分支同样会经 app/memory/long_term.py:131 打 localhost:11434 要
    # embedding。fixture 只是把结果钉成它本来在离线机上拿到的零向量，向量内容不变。
    from app.memory import long_term, profile

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(long_term, "psycopg", None, raising=False)
    monkeypatch.setattr(long_term, "_initialized", False)
    monkeypatch.setattr(long_term, "_MEMORY", {})
    monkeypatch.setattr(profile, "_database_available", lambda: False, raising=False)
    monkeypatch.setattr(profile, "_MEM_PROFILES", {})

    assert long_term.remember("dev-user", "prefers bar charts") is True
    assert long_term.recall("dev-user", "bar charts")
    assert profile.upsert_profile("dev-user", department="it") is True
    assert long_term.memory_storage_state()["storage_mode"] == "memory"
    assert profile.profile_storage_state()["storage_mode"] == "memory"


def test_legacy_blpop_queue_is_not_referenced_by_production_code():
    sources = [Path("app"), Path("deploy")]
    hits = [
        path
        for root in sources
        for path in root.rglob("*.py")
        if "common.queue" in path.read_text(encoding="utf-8-sig", errors="ignore")
    ]
    assert hits == []


def test_startup_hooks_refuse_production_traffic_before_the_scheduler():
    """S6 的守卫只有真挂在启动链上才算数，且必须排在调度器前面。"""
    import io
    from pathlib import Path

    from app.main import app

    source = io.open(
        str(Path(__file__).resolve().parents[1] / "app" / "main.py"), encoding="utf-8-sig"
    ).read()
    handler_names = [handler.__name__ for handler in app.router.on_startup]

    assert "startup_storage_guard" in handler_names, handler_names
    assert handler_names.index("startup_storage_guard") < handler_names.index("startup_scheduler")
    assert "enforce_production_storage_guard" in source
    # 路由存在性以 OpenAPI 表徵为准：新版 Starlette 把子路由收进 _IncludedRouter，
    # 它既没有 .path 也不再暴露 .routes，直接遍历 app.routes 会漏掉已挂载的路由。
    assert "/api/v1/apps" in app.openapi()["paths"]


def test_image_ships_a_cjk_font_that_the_code_actually_looks_for():
    """容器里曾经一个字体都没有，图表中文全是方框、PDF 无法嵌入字体。

    断言的不是"装了某个包"，而是装的包正好被两处消费方认出来：chart.py 的偏好列表
    与 export.py 在 Linux 上唯一探测的路径。
    """
    from pathlib import Path

    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    chart_source = Path("app/tools/chart.py").read_text(encoding="utf-8")
    export_source = Path("app/tools/export.py").read_text(encoding="utf-8")

    assert "fonts-wqy-microhei" in dockerfile, "镜像必须自带中文字体"
    assert "WenQuanYi Micro Hei" in chart_source, "chart.py 的字体偏好要包含镜像里的字体族"
    assert "wqy-microhei.ttc" in export_source, "export.py 必须探测镜像安装的字体路径"


def test_rag_preload_cannot_abort_the_application_startup(monkeypatch):
    """预加载是优化，不是启动前提：缺模型/缺外网时服务仍要能起来。

    容器门第一次实跑就是因为这里抛错，uvicorn 直接 "Application startup failed"。
    """
    import app.main as main_module
    import app.agents.tools as tools_module

    def _boom():
        raise OSError("huggingface.co unreachable")

    monkeypatch.setattr(tools_module, "preload_pipeline", _boom)
    main_module._preload_sync()  # 不得抛出
