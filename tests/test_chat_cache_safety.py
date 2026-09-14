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
        lambda _question, scope="": stale_answer,
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


def test_ask_caches_the_answer_under_the_callers_own_scope(monkeypatch, tmp_path):
    """/ask 接线证据：同一个问题，Alice 写下的缓存不会被 Carol 读走。

    这里不替换缓存层，让 /ask 真实落到进程内 Redis 上，所以测的是调用方有没有显式
    传作用域，而不只是键空间本身的形状。
    """
    from app.api.v1 import chat
    from app.common import cache
    from app.common.identity import Principal
    from app.storage.sessions import SessionRegistry

    # 本机未安装 fakeredis，get_redis() 会退回进程内实现；用同一形状替换单例。
    monkeypatch.setattr(cache, "_redis", cache._MemoryRedis())

    alice_answer = "只有 Alice 检索得到的那份答案。"
    fresh_answer = "这一轮真实生成的答案。"
    generated = [alice_answer, fresh_answer]

    def request_for(username):
        principal = Principal.from_user(
            {"id": username, "username": username, "role": "staff", "department": "finance"}
        )
        return type(
            "Request",
            (),
            {"state": type("State", (), {"principal": principal, "username": username})()},
        )()

    async def consume(response):
        chunks = [chunk async for chunk in response.body_iterator]
        return "".join(
            chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in chunks
        )

    def fake_stream(*_args, **_kwargs):
        answer = generated.pop(0)
        yield {
            "messages": [],
            "worker_results": {"doc": answer},
            "final_answer": answer,
        }

    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *_args: {})
    monkeypatch.setattr(chat, "_save_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda _session_id, message: message)
    monkeypatch.setattr(chat, "_session_database_available", lambda: False)
    monkeypatch.setattr(chat, "auth", type("AuthStub", (), {"get_user": staticmethod(lambda _u: None)}))
    monkeypatch.setattr("app.common.cache.check_rate_limit", lambda *_args, **_kwargs: (True, 9))
    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", fake_stream)
    monkeypatch.setattr(chat, "session_registry", SessionRegistry(tmp_path / "sessions.json"))

    question = "本项目预算明细是多少？"

    def ask_as(username):
        response = asyncio.run(
            chat.ask(chat.AskRequest(message=question), http_request=request_for(username))
        )
        return asyncio.run(consume(response))

    # 无 session_id 的兼容调用才允许使用问题级缓存，这里测的正是这条路径。
    assert ask_as("alice").count(alice_answer) == 1
    assert generated == [fresh_answer], "Alice 那一轮必须真的生成过一次"

    carol_body = ask_as("carol")
    assert alice_answer not in carol_body, "Carol 读到了 Alice 的作用域外的答案"
    assert fresh_answer in carol_body
    assert generated == [], "两个用户各自生成一次"

    # Alice 第二次问同一个问题：命中自己作用域下的缓存，不再触发生成。
    assert alice_answer in ask_as("alice")
    assert generated == [], "Alice 的第二次调用应当命中缓存而不是重新生成"
