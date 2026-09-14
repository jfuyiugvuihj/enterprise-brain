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


def test_answer_cache_is_not_shared_between_users(monkeypatch):
    """同部门同角色的两个用户也不能共用一条答案缓存。

    缓存内容取决于调用者可检索到的文档（含 owner_id 与密级），而这些授权输入无法
    由“角色 + 部门”等价推断，所以作用域按用户隔离。这里直接测键空间，不依赖 /ask
    的接线；接线后调用方必须显式传 scope。
    """
    from app.common import cache
    from app.common.identity import Principal

    # 本机未安装 fakeredis，get_redis() 会退回进程内实现；这里直接用同一形状替换单例。
    monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())

    alice = Principal.from_user(
        {"id": "alice", "username": "alice", "role": "admin", "department": "finance"}
    )
    carol = Principal.from_user(
        {"id": "carol", "username": "carol", "role": "admin", "department": "finance"}
    )
    question = "本项目预算明细是多少？"
    answer = "只有 Alice 可读到的那份答案"

    cache.cache_answer(question, answer, scope=cache.answer_cache_scope(alice))

    assert cache.get_cached_answer(question, scope=cache.answer_cache_scope(carol)) is None
    assert cache.get_cached_answer(question, scope=cache.answer_cache_scope(alice)) == answer
    # 作用域缺失时落在历史键上，不会被任何带作用域的写入污染
    assert cache.get_cached_answer(question) is None
    assert cache.answer_cache_scope(alice) != cache.answer_cache_scope(carol)
    assert cache.answer_cache_scope(None, "anonymous") == "user:anonymous"
