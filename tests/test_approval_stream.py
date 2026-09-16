import json
import threading

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.common.auth import create_token
from app.main import app


def _event_payloads(body: str, event_name: str) -> list[dict]:
    payloads = []
    for block in body.split("\n\n"):
        lines = block.splitlines()
        if not lines or lines[0] != f"event: {event_name}":
            continue
        payloads.append(json.loads(lines[1].removeprefix("data: ")))
    return payloads


def _bind_session(chat_module, monkeypatch, tmp_path, session_id: str, username: str):
    """Register the fixture session for the caller the way POST /ask would."""
    from app.common import auth
    from app.common.identity import Principal
    from app.storage import sessions as sessions_module

    user = auth.get_user(username)
    assert user, f"the test subject {username} must resolve to a user"
    registry = sessions_module.SessionRegistry(tmp_path / "session-registry.json")
    registry.bind(session_id, Principal.from_user(user))
    monkeypatch.setattr(chat_module, "session_registry", registry)
    return registry

def test_approve_stream_emits_worker_result_when_no_plain_ai_message(monkeypatch, tmp_path):
    from app.api.v1 import chat as chat_module

    _bind_session(
        chat_module, monkeypatch, tmp_path, "approval-worker-result-test", "admin"
    )

    seen = {}

    def fake_run_interrupt_stream(
        thread_id: str, approved: bool, user=None, cancel_event=None
    ):
        seen["thread_id"] = thread_id
        seen["user"] = user
        # /approve 必须把取消标记交给编排，否则工作线程永远停不下来（R12）。
        seen["cancel_event"] = cancel_event
        yield {"messages": [AIMessage(content="需要确认后生成图表")]}
        yield {
            "messages": [AIMessage(content="【chart Agent 返回】\n图表已生成：/static/chart.png")],
            "worker_results": {"chart": "图表已生成：/static/chart.png"},
        }

    monkeypatch.setattr(
        "app.agents.orchestrator.run_interrupt_stream",
        fake_run_interrupt_stream,
    )
    monkeypatch.setattr("app.api.v1.chat._save_message", lambda *args, **kwargs: None)

    client = TestClient(app)
    response = client.post(
        "/api/v1/approve",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
        json={"session_id": "approval-worker-result-test", "approved": True},
    )

    assert response.status_code == 200
    text_events = _event_payloads(response.text, "text")
    assert [event["content"] for event in text_events] == [
        "图表已生成：/static/chart.png"
    ]


    # Resuming without the caller principal runs the approved action as nobody, and
    # every tool then refuses with authorization_required.
    assert seen["thread_id"] == "approval-worker-result-test"
    assert isinstance(seen["cancel_event"], threading.Event)
    principal = seen["user"]["principal"]
    assert principal.username == "admin"
    assert principal.user_id


def test_run_interrupt_stream_config_carries_the_caller_principal(monkeypatch):
    from app.agents import orchestrator
    from app.common.identity import Principal

    captured = {}

    class FakeGraph:
        def stream(self, payload, config, **kwargs):
            captured["config"] = config
            yield {"messages": []}

    monkeypatch.setattr(orchestrator, "multi_agent_graph", FakeGraph())
    principal = Principal(
        user_id="7", username="tester", roles=["staff"], department="finance"
    )
    list(
        orchestrator.run_interrupt_stream(
            "thread-1", True, {"username": "tester", "principal": principal}
        )
    )

    configurable = captured["config"]["configurable"]
    assert configurable["thread_id"] == "thread-1"
    assert configurable["principal"] is principal
    assert configurable["request_id"].startswith("req-")
    assert configurable["trace_id"].startswith("trace-")


def test_export_worker_fallback_replaces_static_url_with_controlled_artifact(monkeypatch):
    from app.agents import orchestrator

    observed = {}

    def fake_export_report(report_title, sections_json, config, include_charts=""):
        observed["config"] = config
        return "报告已生成: [下载报告](/api/v1/artifacts/artifact-1/download)"

    monkeypatch.setattr(
        orchestrator,
        "export_report",
        fake_export_report,
    )

    result = orchestrator._fallback_export_result(
        "把当前分析整理成PDF，给管理层看的那种",
        "报告已生成: [下载报告](/static/exports/report_test.pdf)",
        config={
            "configurable": {
                "id": "finance-manager",
                "username": "finance-manager",
                "role": "manager",
                "department": "finance",
            }
        },
    )

    assert "/api/v1/artifacts/artifact-1/download" in result
    assert observed["config"]["configurable"]["username"] == "finance-manager"
def test_a_declined_action_is_recorded_so_it_cannot_run_again(monkeypatch):
    """Rejecting a parked action must not let supervisor dispatch that node again.

    Skipping the node alone left it in the plan, so the action the user declined ran
    anyway and the session parked a second time.
    """
    from app.agents import orchestrator

    captured = {}

    class FakeGraph:
        def update_state(self, config, values):
            captured["update"] = values

        def stream(self, payload, config, **kwargs):
            captured["payload"] = payload
            yield {"messages": []}

    monkeypatch.setattr(orchestrator, "multi_agent_graph", FakeGraph())
    monkeypatch.setattr(
        orchestrator, "check_interrupt", lambda thread_id: {"pending": ["chart"], "labels": ["📈 生成图表"]}
    )

    list(orchestrator.run_interrupt_stream("thread-2", False, {"username": "tester"}))

    update = captured["update"]
    assert update["worker_results"]["chart"] == "已取消，未执行：📈 生成图表"
    assert str(update["messages"][0].content) == "已取消，未执行：📈 生成图表"
    assert captured["payload"].goto == "supervisor"


def test_an_approved_action_is_not_marked_cancelled(monkeypatch):
    from app.agents import orchestrator

    captured = {}

    class FakeGraph:
        def update_state(self, config, values):
            captured["update"] = values

        def stream(self, payload, config, **kwargs):
            captured["payload"] = payload
            yield {"messages": []}

    monkeypatch.setattr(orchestrator, "multi_agent_graph", FakeGraph())
    monkeypatch.setattr(
        orchestrator, "check_interrupt", lambda thread_id: {"pending": ["chart"], "labels": ["📈 生成图表"]}
    )

    list(orchestrator.run_interrupt_stream("thread-3", True, {"username": "tester"}))

    assert "update" not in captured
    assert captured["payload"].resume == {"approved": True}
