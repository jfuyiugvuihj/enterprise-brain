"""跟进单 R21 判据③④：/health/details 必须看得见缺失的 embedding 模型。

钉死的口径：模型不在本机 Ollama 注册表里时 problems 给出稳定码
embedding_model_missing；模型就位时不得给出；注册表没读到过的时候不得凭空指认；
这些结论全部来自 /api/tags 那**一次**已有的读取，健康检查不得为 embedding 另开 socket、
更不得真去调 /api/embeddings（那会把模型加载成本压进健康探针）。
"""
import json

import pytest

from app.common import monitoring
from app.rag import retriever as retriever_module


class _TagsResponse:
    """冒充一次 /api/tags 的成功响应，并记下被请求的 URL 与次数。"""

    def __init__(self, models, recorder):
        self.status = 200
        self._body = json.dumps({"models": models}).encode("utf-8")
        self._recorder = recorder

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _serve_registry(monkeypatch, models):
    urls = []

    def fake_urlopen(url, timeout=None):
        urls.append(url)
        return _TagsResponse(models, urls)

    monkeypatch.setattr(monitoring, "urlopen", fake_urlopen)
    return urls


def _production_with_durable_stores(monkeypatch):
    """把除 ollama 之外的所有问题源都掐掉，problems 里剩下什么就只取决于 embedding 探测。"""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("LOCAL_MODEL_NAME", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.setattr(monitoring, "_probe_postgres", lambda: {"status": "ok"})
    monkeypatch.setattr(monitoring, "_probe_redis", lambda: {"status": "ok"})

    baseline = monitoring.storage_snapshot()
    subsystems = {
        name: {**state, "durable": True, "protection": "none",
               "storage_mode": "redis" if name == "queue" else "postgres"}
        for name, state in baseline["subsystems"].items()
    }
    storage = {
        **baseline,
        "subsystems": subsystems,
        "durable": sorted(subsystems),
        "read_only_protected": [],
        "refuses_startup": [],
        "single_instance_only": [],
    }
    monkeypatch.setattr(monitoring, "storage_snapshot", lambda: storage)


def _chat_model_only():
    return [{"name": "qwen2.5:14b"}]


def _chat_and_embedding_models():
    return [{"name": "qwen2.5:14b"}, {"name": f"{retriever_module.EMBED_MODEL}:latest"}]


def test_a_registry_that_never_served_the_embedding_model_reports_a_stable_code(monkeypatch):
    _production_with_durable_stores(monkeypatch)
    _serve_registry(monkeypatch, _chat_model_only())

    snapshot = monitoring.build_health_snapshot()

    assert snapshot["dependencies"]["ollama"]["embedding_model"] == retriever_module.EMBED_MODEL
    assert snapshot["dependencies"]["ollama"]["embedding_model_present"] is False
    assert snapshot["problems"] == ["embedding_model_missing"]
    assert snapshot["status"] == "degraded"


def test_a_registry_that_has_the_embedding_model_keeps_the_report_clean(monkeypatch):
    _production_with_durable_stores(monkeypatch)
    _serve_registry(monkeypatch, _chat_and_embedding_models())

    snapshot = monitoring.build_health_snapshot()

    assert snapshot["dependencies"]["ollama"]["embedding_model_present"] is True
    assert "embedding_model_missing" not in snapshot["problems"]
    assert snapshot["problems"] == []
    assert snapshot["status"] == "ok"


def test_a_tagged_embedding_model_matches_the_pinned_name(monkeypatch):
    """ollama 注册表里的名字带 :latest 后缀，稳定码不得因此误报。"""
    _production_with_durable_stores(monkeypatch)
    _serve_registry(
        monkeypatch, [{"name": f"{retriever_module.EMBED_MODEL}:latest"}]
    )

    snapshot = monitoring.build_health_snapshot()

    assert snapshot["dependencies"]["ollama"]["embedding_model_present"] is True
    assert snapshot["problems"] == []


def test_a_registry_that_was_never_read_is_not_claimed_missing(monkeypatch):
    """探针只说它看见的事：没读到注册表就是 unknown，不是"模型没装"。"""
    _production_with_durable_stores(monkeypatch)
    monkeypatch.setattr(monitoring, "_probe_ollama", lambda: {"status": "ok"})

    snapshot = monitoring.build_health_snapshot()

    assert "embedding_model_present" not in snapshot["dependencies"]["ollama"]
    assert "embedding_model_missing" not in snapshot["problems"]
    assert snapshot["problems"] == []


def test_an_unreachable_model_server_is_reported_as_unavailable_not_as_a_missing_model(
    monkeypatch,
):
    """两个不同的事实：服务没起 ≠ 模型没装，稳定码也不得混用。"""
    _production_with_durable_stores(monkeypatch)

    def refuse(url, timeout=None):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(monitoring, "urlopen", refuse)

    snapshot = monitoring.build_health_snapshot()

    assert snapshot["dependencies"]["ollama"]["status"] == "unavailable"
    assert "ollama_unavailable" in snapshot["problems"]
    assert "embedding_model_missing" not in snapshot["problems"]


def test_the_embedding_check_opens_no_extra_socket_and_never_calls_the_embeddings_api(
    monkeypatch,
):
    """判据③的硬闸：embedding 结论必须复用同一次 /api/tags 读取。"""
    _production_with_durable_stores(monkeypatch)
    urls = _serve_registry(monkeypatch, _chat_and_embedding_models())

    snapshot = monitoring.build_health_snapshot()

    assert snapshot["dependencies"]["ollama"]["embedding_model_present"] is True
    assert urls == [f"{urls[0].rstrip('/').rsplit('/api/tags')[0]}/api/tags"], (
        "一次健康快照只允许一次注册表请求，不得为 embedding 另开 socket"
    )
    assert all("/api/embeddings" not in url for url in urls), "健康探针不得触发模型加载"


def test_the_probe_follows_the_model_name_the_retriever_will_actually_call(monkeypatch):
    """EMBED_MODEL 改名后探针必须跟着改，否则它就是个装饰性的绿灯。"""
    _production_with_durable_stores(monkeypatch)
    monkeypatch.setattr(retriever_module, "EMBED_MODEL", "bge-m3")
    _serve_registry(monkeypatch, _chat_model_only())

    missing = monitoring.build_health_snapshot()

    assert missing["dependencies"]["ollama"]["embedding_model"] == "bge-m3"
    assert missing["problems"] == ["embedding_model_missing"]

    _serve_registry(monkeypatch, [{"name": "qwen2.5:14b"}, {"name": "bge-m3:latest"}])

    present = monitoring.build_health_snapshot()

    assert present["dependencies"]["ollama"]["embedding_model_present"] is True
    assert present["problems"] == []


def test_the_health_details_endpoint_surfaces_the_code(monkeypatch):
    """判据③写在接口上：/health/details 的 problems 里要看得见这个码。"""
    from fastapi.testclient import TestClient

    from app.common import auth
    from app.main import app

    _production_with_durable_stores(monkeypatch)
    _serve_registry(monkeypatch, _chat_model_only())
    # 中间件只认 get_user 交回来的账号，这里给一个在册 admin，测试的是探针而不是登录
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda username: {
            "id": 1,
            "username": username,
            "password_hash": "x",
            "role": "admin",
            "department": "",
            "status": "active",
        },
    )
    client = TestClient(app)

    response = client.get(
        "/api/v1/health/details",
        headers={"Authorization": f"Bearer {auth.create_token('admin')}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "embedding_model_missing" in body["problems"]
    assert body["dependencies"]["ollama"]["embedding_model_present"] is False
    assert body["status"] == "degraded"
