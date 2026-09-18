import asyncio


def test_model_handler_ignores_invalid_no_proxy_environment(monkeypatch):
    from app.common.model_handler import ModelHandler, _OfflineChatClient

    monkeypatch.setenv("NO_PROXY", "::1")

    handler = ModelHandler()

    assert not isinstance(handler.ollama_client, _OfflineChatClient)


def test_model_handler_disables_provider_retries():
    from app.common.model_handler import ModelHandler

    handler = ModelHandler()

    assert handler.ollama_client.max_retries == 0


def test_model_handler_uses_ollama_base_url_and_ipv4_loopback(monkeypatch):
    from app.common.model_handler import ModelHandler

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    handler = ModelHandler()

    assert str(handler.ollama_client.base_url) == "http://127.0.0.1:11434/v1/"


def test_model_handler_returns_offline_reply_when_provider_request_fails():
    from app.common.model_handler import ModelHandler, ModelSource

    class BrokenCompletions:
        def create(self, **kwargs):
            raise RuntimeError("provider unavailable")

    class BrokenClient:
        chat = type("Chat", (), {"completions": BrokenCompletions()})()

    handler = ModelHandler()
    handler.ollama_client = BrokenClient()

    response = handler.chat(
        [{"role": "user", "content": "hello"}],
        source=ModelSource.OLLAMA,
        stream=False,
    )

    assert "离线模式" in response


def test_agent_model_falls_back_when_provider_invoke_fails(monkeypatch):
    from app.agents import nodes
    from langchain_core.messages import HumanMessage

    class BrokenModel:
        def invoke(self, messages, **kwargs):
            raise RuntimeError("provider unavailable")

        def bind_tools(self, tools):
            return self

    monkeypatch.setattr(nodes, "ChatOpenAI", lambda **kwargs: BrokenModel())

    response = nodes._make_model().invoke(
        [HumanMessage(content="公司报销流程是什么")]
    )

    assert response.content
    assert "离线" in response.content or "报销" in response.content


def test_sessions_remain_available_without_postgres(monkeypatch):
    from app.api.v1 import chat

    monkeypatch.setattr(chat, "_session_database_available", lambda: False, raising=False)
    chat._MEM_SESSIONS.clear()
    chat._MEM_SESSION_MESSAGES.clear()

    chat._ensure_session("offline-session")
    chat._save_message("offline-session", "user", "offline question")

    sessions = chat._list_sessions()

    assert sessions[0]["id"] == "offline-session"
    assert sessions[0]["msg_count"] == 1
    assert chat._get_session_messages("offline-session")[0]["content"] == "offline question"

    chat._delete_session("offline-session")
    assert chat._list_sessions() == []


def test_profile_save_and_load_fallback_to_memory_without_postgres(monkeypatch):
    from app.memory import profile

    monkeypatch.setattr(profile, "_database_available", lambda: False, raising=False)
    profile._MEM_PROFILES.clear()

    assert profile.upsert_profile(
        "offline-user",
        department="QA",
        position="tester",
        preferences=["concise"],
    )

    saved = profile.get_profile("offline-user", fallback={"username": "offline-user"})

    assert saved["department"] == "QA"
    assert saved["position"] == "tester"
    assert saved["preferences"] == ["concise"]


def test_alert_rule_crud_fallback_to_memory_without_postgres(monkeypatch):
    from app.api.v1 import alerts

    monkeypatch.setattr(alerts, "_database_available", lambda: False, raising=False)
    alerts._MEM_RULES.clear()
    alerts._MEM_ALERTS.clear()
    alerts._MEM_NEXT_RULE_ID = 1

    created = asyncio.run(
        alerts.create_rule(
            alerts.RuleCreate(name="offline rule", metric="revenue", op="lt", threshold=1)
        )
    )
    listed = asyncio.run(alerts.list_rules())

    assert created["status"] == "ok"
    assert listed["rules"][0]["name"] == "offline rule"
    assert asyncio.run(alerts.delete_rule(created["id"]))["status"] == "ok"


def test_pending_steps_are_completed_when_ask_stream_finishes():
    from app.api.v1.chat import _complete_pending_steps

    steps = [
        {"tool": "doc", "label": "搜索知识库", "status": "running", "elapsed": None},
        {"tool": "data", "label": "分析数据", "status": "done", "elapsed": 1.2},
    ]

    completed = _complete_pending_steps(steps, elapsed=3.4)

    assert completed == [
        {"tool": "doc", "label": "搜索知识库", "status": "done", "elapsed": 3.4},
    ]
    assert all(step["status"] == "done" for step in steps)


def test_offline_supervisor_emits_dispatch_tool_call():
    from app.agents.nodes import _OfflineModel

    model = _OfflineModel().bind_tools([type("DispatchTool", (), {"name": "dispatch"})()])
    result = model.invoke([{"role": "user", "content": "请查文档中的差旅报销制度"}])

    assert result.tool_calls
    assert result.tool_calls[0]["name"] == "dispatch"
    assert result.tool_calls[0]["args"]["workers"] == ["doc"]


def test_offline_doc_worker_emits_search_tool_call():
    from app.agents.nodes import _OfflineModel

    model = _OfflineModel().bind_tools([type("SearchTool", (), {"name": "search_docs"})()])
    result = model.invoke([{"role": "user", "content": "差旅报销制度里住宿费标准是多少？"}])

    assert result.tool_calls
    assert result.tool_calls[0]["name"] == "search_docs"
    assert result.tool_calls[0]["args"]["query"]


def test_offline_model_returns_tool_output_without_replanning():
    from app.agents.nodes import _OfflineModel

    model = _OfflineModel().bind_tools([type("SearchTool", (), {"name": "search_docs"})()])
    result = model.invoke([
        {"role": "user", "content": "查文档"},
        {"role": "tool", "content": "住宿费标准为500元"},
    ])

    assert not result.tool_calls
    assert "500" in result.content


def test_document_retriever_persists_documents_without_chromadb(
    tmp_path, monkeypatch, offline_ollama_embeddings
):
    # R56：add_document/search 各会打一次 localhost:11434 的 embedding API；本用例断的是
    # 无 chromadb 时的 JSON 落盘与关键词召回，向量本来就走的零向量兜底，钉成离线不开 socket。
    from app.rag import retriever

    monkeypatch.setattr(retriever, "chromadb", None)
    first = retriever.DocumentRetriever(str(tmp_path))
    added, _ = first.add_document("policy.txt", "住宿费标准为500元")

    second = retriever.DocumentRetriever(str(tmp_path))

    assert added is True
    assert second.list_documents() == ["policy.txt"]
    results = second.search("住宿费标准")
    assert results
    assert "500" in results[0]["content"]
