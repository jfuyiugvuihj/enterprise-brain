import importlib
from pathlib import Path


def test_local_model_settings_support_internal_openai_compatible_server(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", "http://10.0.0.8:8000/v1")
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen3.6-27b")
    monkeypatch.setenv("LOCAL_MODEL_API_KEY", "internal-token")

    from app.common import model_config

    importlib.reload(model_config)
    settings = model_config.get_local_model_settings()

    assert settings.base_url == "http://10.0.0.8:8000/v1"
    assert settings.model_name == "qwen3.6-27b"
    assert settings.api_key == "internal-token"


def test_model_handler_uses_configured_local_model(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", "http://10.0.0.9:9000")
    monkeypatch.setenv("LOCAL_MODEL_NAME", "internal-model")
    monkeypatch.setenv("LOCAL_MODEL_API_KEY", "internal-token")

    from app.common.model_handler import ModelHandler

    handler = ModelHandler()

    assert handler.local_model == "internal-model"
    assert str(handler.local_client.base_url) == "http://10.0.0.9:9000/v1/"


def test_local_model_failure_only_uses_offline_reply():
    from app.common.model_handler import ModelHandler, ModelSource

    class BrokenCompletions:
        def create(self, **kwargs):
            raise RuntimeError("local provider unavailable")

    class BrokenClient:
        chat = type("Chat", (), {"completions": BrokenCompletions()})()

    handler = ModelHandler()
    handler.ollama_client = BrokenClient()

    response = handler.chat(
        [{"role": "user", "content": "hello"}],
        source=ModelSource.LOCAL,
        stream=False,
    )

    assert "离线模式" in response


def test_external_model_entry_points_are_removed():
    from app.common.model_handler import ModelSource
    from app.api.v1.chat import ChatRequest

    assert not hasattr(ModelSource, "DEEPSEEK")
    assert not hasattr(ChatRequest(message="你好"), "model_source")

    project_root = Path(__file__).parents[1]
    checked_files = [
        project_root / "app" / "common" / "model_handler.py",
        project_root / "app" / "api" / "v1" / "chat.py",
        project_root / "frontend" / "src" / "components" / "ChatPanel.vue",
        project_root / ".env.example",
        project_root / "pyproject.toml",
    ]
    for path in checked_files:
        text = path.read_text(encoding="utf-8")
        assert "deepseek" not in text.lower()


def test_agent_model_factory_uses_local_model(monkeypatch):
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", "http://10.0.0.10:9100/v1")
    monkeypatch.setenv("LOCAL_MODEL_NAME", "internal-agent")
    monkeypatch.setenv("LOCAL_MODEL_API_KEY", "internal-token")

    from app.agents import nodes

    model = nodes._make_model()

    assert model.model_name == "internal-agent"
    assert str(model.root_client.base_url) == "http://10.0.0.10:9100/v1/"


def test_query_rewriter_uses_local_model_source(monkeypatch):
    from app.rag import retrieval_pipeline
    from app.common.model_handler import ModelSource

    calls = []

    def fake_chat(*, messages, source, stream):
        calls.append(source)
        return '{"rewrites":["local rewrite"],"sub_questions":[]}'

    monkeypatch.setattr(retrieval_pipeline.model, "chat", fake_chat)

    result = retrieval_pipeline.QueryRewriter.rewrite("查询制度")

    assert result["rewrites"] == ["local rewrite"]
    assert calls == [ModelSource.LOCAL]


def test_legacy_chat_defaults_to_local_model():
    from app.api.v1.chat import ChatRequest

    assert not hasattr(ChatRequest(message="你好"), "model_source")
