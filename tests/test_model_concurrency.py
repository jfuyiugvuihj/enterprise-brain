from app.common.model_handler import ModelHandler, ModelSource


class _Chunk:
    choices = [type("Choice", (), {"delta": type("Delta", (), {"content": "ok"})()})()]


class _StreamingCompletions:
    def create(self, *, stream, **kwargs):
        if stream:
            return iter([_Chunk()])
        message = type("Message", (), {"content": "ok"})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class _StreamingClient:
    chat = type("Chat", (), {"completions": _StreamingCompletions()})()


def test_streaming_model_call_holds_and_releases_concurrency_budget(monkeypatch):
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "1")
    handler = ModelHandler()
    handler.ollama_client = _StreamingClient()

    first_stream = handler.chat(
        [{"role": "user", "content": "first"}],
        source=ModelSource.LOCAL,
        stream=True,
    )
    rejected = handler.chat(
        [{"role": "user", "content": "second"}],
        source=ModelSource.LOCAL,
        stream=False,
    )

    assert "error_code=rate_limited" in rejected
    assert [chunk.choices[0].delta.content for chunk in first_stream] == ["ok"]
    assert handler.chat(
        [{"role": "user", "content": "third"}],
        source=ModelSource.LOCAL,
        stream=False,
    ) == "ok"


def test_model_concurrency_budget_accepts_configured_parallel_calls(monkeypatch):
    monkeypatch.setenv("MODEL_MAX_CONCURRENCY", "2")
    handler = ModelHandler()
    handler.ollama_client = _StreamingClient()

    first_stream = handler.chat(
        [{"role": "user", "content": "first"}],
        source=ModelSource.LOCAL,
        stream=True,
    )
    assert handler.chat(
        [{"role": "user", "content": "second"}],
        source=ModelSource.LOCAL,
        stream=False,
    ) == "ok"
    assert list(first_stream)
