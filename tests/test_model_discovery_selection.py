"""Model selection must come from configuration or local discovery, never from a guess."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clean_model_environment(monkeypatch):
    from app.common import model_config

    for name in ("LOCAL_MODEL_NAME", "OLLAMA_MODEL", "LOCAL_MODEL_BASE_URL", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    model_config.reset_model_discovery_cache()
    yield
    model_config.reset_model_discovery_cache()


def _registry(*models):
    def fetch(_url):
        return {"models": list(models)}

    return fetch


def test_an_explicitly_configured_model_wins_over_discovery(monkeypatch) -> None:
    from app.common import model_config

    monkeypatch.setenv("LOCAL_MODEL_NAME", "board-chat")
    calls = []

    def discover(_base_url):
        calls.append(_base_url)
        return "discovered-chat"

    settings = model_config.get_local_model_settings(discover=discover)

    assert settings.model_name == "board-chat"
    assert settings.model_source == "configured"
    assert calls == []


def test_an_unconfigured_model_is_taken_from_the_local_registry() -> None:
    from app.common import model_config

    settings = model_config.get_local_model_settings(
        discover=lambda base_url: model_config.discover_chat_model(base_url, fetch=_registry({"name": "llama3.1:8b"}))
    )

    assert settings.model_name == "llama3.1:8b"
    assert settings.model_source == "discovered"


def test_discovery_reaches_the_registry_url_without_the_openai_suffix(monkeypatch) -> None:
    from app.common import model_config

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    requested = []

    def fetch(url):
        requested.append(url)
        return {"models": [{"name": "qwen3:8b"}]}

    settings = model_config.get_local_model_settings(
        discover=lambda base_url: model_config.discover_chat_model(base_url, fetch=fetch)
    )

    assert settings.model_name == "qwen3:8b"
    assert requested == ["http://127.0.0.1:11434/api/tags"]


def test_an_embedding_only_registry_does_not_provide_a_chat_model() -> None:
    from app.common import model_config

    assert (
        model_config.discover_chat_model("http://127.0.0.1:11434", fetch=_registry({"name": "nomic-embed-text"}))
        == ""
    )


def test_nothing_is_invented_when_the_registry_is_unreachable() -> None:
    from app.common import model_config

    def failing_fetch(_url):
        raise ConnectionError("ollama is offline")

    assert model_config.discover_chat_model("http://127.0.0.1:11434", fetch=failing_fetch) == ""
    settings = model_config.get_local_model_settings(discover=lambda _base_url: "")
    assert settings.model_name == ""
    assert settings.model_source == "none"


def test_health_snapshot_reports_the_resolved_model_source(monkeypatch) -> None:
    from app.common import model_config, monitoring

    # R56：本用例只看 snapshot["model"]，但 build_health_snapshot 还会顺手探一次
    # Ollama（app/common/monitoring.py:236 自己 urlopen /api/tags，不经过 model_config）。
    # 按 test_deployment_guards.py:142 的既有惯例把探针换成离线值，测试期不开 socket。
    monkeypatch.setattr(monitoring, "_probe_ollama", lambda: {"status": "ok"})
    model_config.reset_model_discovery_cache()
    monkey = model_config
    original = monkey._cached_discovery
    monkey._cached_discovery = lambda _base_url: ""
    try:
        snapshot = monitoring.build_health_snapshot()["model"]
    finally:
        monkey._cached_discovery = original

    assert snapshot["name"] is None
    assert snapshot["source"] == "none"


def test_the_agent_model_degrades_honestly_without_a_model_name(monkeypatch) -> None:
    from app.agents import nodes
    from app.common.model_config import LocalModelSettings

    monkeypatch.setattr(
        nodes,
        "get_local_model_settings",
        lambda: LocalModelSettings(
            base_url="http://127.0.0.1:11434/v1", model_name="", api_key="local", model_source="none"
        ),
    )

    assert isinstance(nodes._make_model(), nodes._OfflineModel)