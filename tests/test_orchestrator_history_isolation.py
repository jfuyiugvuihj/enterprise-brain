from langchain_core.messages import HumanMessage


def test_supervisor_only_receives_current_user_message(monkeypatch):
    from app.agents import orchestrator

    captured = {}

    class DummyResp:
        content = "ok"
        tool_calls = []

    class DummyModel:
        def invoke(self, messages, **kwargs):
            captured["messages"] = messages
            return DummyResp()

    monkeypatch.setattr(orchestrator, "main_model", DummyModel())

    state = {
        "messages": [
            HumanMessage(content="一线城市住宿费标准是多少？"),
            HumanMessage(content="2026年1到6月营业收入总和是多少？"),
        ],
        "memory": {},
    }

    orchestrator.main_agent_node(state)

    assert len(captured["messages"]) == 2
    assert captured["messages"][-1].content == "2026年1到6月营业收入总和是多少？"
