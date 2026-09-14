from app.common.model_capabilities import discover_ollama_models, infer_capabilities


def test_capabilities_distinguish_chat_and_embedding_models():
    chat = infer_capabilities({"name": "local-chat:latest", "details": {"parameter_size": "14B"}})
    embedding = infer_capabilities({"name": "company-embed:latest", "details": {"family": "embedding"}})

    assert chat.chat is True
    assert chat.embedding is False
    assert embedding.embedding is True
    assert embedding.chat is False


def test_discovery_uses_injected_transport_and_filters_by_purpose():
    calls = []

    def fetch(url):
        calls.append(url)
        return {"models": [{"name": "chat-model"}, {"name": "text-embed", "details": {"family": "embedding"}}]}

    result = discover_ollama_models(fetch, "http://127.0.0.1:11434")

    assert calls == ["http://127.0.0.1:11434/api/tags"]
    assert [item.name for item in result.for_purpose("chat")] == ["chat-model"]
    assert [item.name for item in result.for_purpose("embedding")] == ["text-embed"]


def test_discovery_returns_structured_unavailable_state():
    result = discover_ollama_models(lambda _: (_ for _ in ()).throw(ConnectionError("offline")), "http://local")

    assert result.available is False
    assert result.error_code == "model_unavailable"
    assert result.models == []
