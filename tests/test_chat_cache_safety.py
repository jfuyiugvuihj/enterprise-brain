import asyncio


def test_ask_does_not_return_stale_global_answer_cache(monkeypatch, tmp_path):
    from app.api.v1 import chat
    from app.common.identity import Principal
    from app.storage.sessions import SessionRegistry

    stale_answer = "根据差旅费报销细则，一线城市住宿费标准为500元/晚。"
    fresh_answer = "5000元由财务总监审批，20000元由总经理审批。"
    principal = Principal.from_user(
        {"id": "alice", "username": "alice", "role": "manager", "department": "finance"}
    )
    http_request = type(
        "Request",
        (),
        {"state": type("State", (), {"principal": principal, "username": "alice"})()},
    )()

    async def consume(response):
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return "".join(
            item.decode("utf-8") if isinstance(item, bytes) else item
            for item in chunks
        )

    def fake_stream(*_args, **_kwargs):
        yield {
            "messages": [],
            "worker_results": {"doc": fresh_answer},
            "final_answer": fresh_answer,
        }

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}))
    monkeypatch.setattr(
        "app.common.cache.check_rate_limit",
        lambda *_args, **_kwargs: (True, 9),
    )
    monkeypatch.setattr(
        "app.common.cache.get_cached_answer",
        lambda _question: stale_answer,
    )
    monkeypatch.setattr(
        "app.common.cache.cache_answer",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    response = asyncio.run(
        chat.ask(
            chat.AskRequest(
                message="单笔报销金额达到5000元和20000元时，分别需要谁审批？",
                session_id="cache-regression",
            ),
            http_request=http_request,
        )
    )
    body = asyncio.run(consume(response))

    assert fresh_answer in body
    assert stale_answer not in body
