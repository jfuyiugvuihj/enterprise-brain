"""Document references are not routing intent, and an empty turn is not a success.

The browser E2E captured ``POST /api/v1/ask`` answering the question
``《e2eB_normal_policy.pdf》里设备折旧的残值率是多少？`` with
``worker_count: 0``, no ``text`` event at all and a ``request.completed`` terminal state.
The keyword fallback had matched ``pdf`` inside the file name and replaced the planner\'s
``doc`` step with ``export``. Both halves of that bug are pinned here: the routing decision
and the SSE terminal state.
"""

import json

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.orchestrator import _intent_text, route_main
from app.agents.planner import build_task_plan

QUESTION = "《e2eB_normal_policy.pdf》里设备折旧的残值率是多少？请给出原文片段和文件版本。"


def _nodes(result):
    if isinstance(result, str):
        return [result]
    return [getattr(item, "node", None) for item in result if hasattr(item, "node")]


def _routed(question, worker_results=None):
    return _nodes(
        route_main(
            {
                "messages": [HumanMessage(content=question), AIMessage(content="")],
                "plan": build_task_plan(question),
                "worker_results": worker_results or {},
            }
        )
    )


def test_file_name_in_the_question_is_not_an_export_request():
    assert _routed(QUESTION) == ["doc"]


def test_bare_file_extension_is_not_an_export_request():
    assert _routed("e2eB_normal_policy.pdf 里设备折旧的残值率是多少？") == ["doc"]


def test_a_real_report_request_still_reaches_export():
    question = "把住宿费的报销标准整理成一份PDF报告"
    assert _routed(question) == ["doc"]
    assert "export" in _routed(question, {"doc": "住宿费标准为每天 500 元。"})


def test_intent_text_strips_references_but_keeps_action_words():
    assert "pdf" not in _intent_text(QUESTION).lower()
    assert "报告" in _intent_text("把制度要点整理成一份报告")


def _events(body):
    events = []
    name = None
    for line in body.split("\n"):
        if line.startswith("event:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("data:") and name:
            events.append((name, json.loads(line.split(":", 1)[1].strip())))
    return events


def _ask(monkeypatch, streamed, pending):
    from fastapi.testclient import TestClient

    from app.api.v1 import chat
    from app.common.auth import create_token
    from app.main import app

    monkeypatch.setattr("app.agents.orchestrator.run_with_stream", lambda *a, **k: iter(streamed))
    monkeypatch.setattr("app.agents.orchestrator.check_interrupt", lambda thread_id: pending)
    monkeypatch.setattr(chat, "_rewrite_followup", lambda session_id, message: message)
    monkeypatch.setattr(chat, "_ensure_sessions_table", lambda: None)
    monkeypatch.setattr(chat, "_ensure_session", lambda *a, **k: {"id": "hitl-contract-test"})
    monkeypatch.setattr(chat.session_registry, "bind", lambda *a, **k: None)
    saved: list[tuple] = []
    monkeypatch.setattr(chat, "_save_message", lambda *a, **k: saved.append(a))

    response = TestClient(app).post(
        "/api/v1/ask",
        headers={"Authorization": f"Bearer {create_token('admin')}"},
        json={
            "message": "统计各区域营收并生成柱状图",
            "session_id": "hitl-contract-test",
        },
    )
    assert response.status_code == 200, response.text
    return _events(response.text), saved


def test_parked_turn_states_what_is_awaiting_confirmation(monkeypatch):
    events, saved = _ask(
        monkeypatch,
        [{"worker_results": {}, "final_answer": ""}],
        {"pending": ["chart"], "labels": ["\U0001f4c8 生成图表"]},
    )
    names = [name for name, _data in events]
    assert "request.completed" in names
    completed = next(data for name, data in events if name == "request.completed")
    assert completed["data"]["awaiting_hitl"] is True
    assert completed["data"]["awaiting_steps"] == ["chart"]
    texts = [data for name, data in events if name == "text"]
    assert texts and "\u751f\u6210\u56fe\u8868" in texts[0]["content"]
    assert names.index("text") < names.index("hitl")
    assert saved, "the streamed text and the stored session message must match"


def test_an_unproductive_turn_keeps_the_code_out_of_every_string_a_user_can_keep(monkeypatch):
    """R16：码走结构化字段，散文里不许再夹一遍。

    同一条失败要落到三个地方（跟进单 §12 的取证）：`_save_message` 的会话历史、legacy
    ``error`` 事件的 content、canonical ``request.failed.data.error_code``。前两个是
    "人会留下来反复看"的文本，第三个才是机器判据该待的地方。散文里那个
    ``（error_code=no_answer_produced）`` 与 canonical 字段完全重复，而它一旦入库就
    再也洗不掉——前端渲染期清洗救得了新消息，救不了历史行。
    """
    events, saved = _ask(
        monkeypatch,
        [{"worker_results": {}, "final_answer": ""}],
        None,
    )

    failed = next(data for name, data in events if name == "request.failed")
    assert failed["data"]["error_code"] == "no_answer_produced", "删冗余不许丢信息"

    stored = [str(args[2]) for args in saved]
    assert stored, "本轮失败仍要留下一条助手消息"
    joined = "\n".join(stored)
    assert "error_code=" not in joined
    assert "no_answer_produced" not in joined

    legacy = next(data for name, data in events if name == "error")
    assert legacy["content"] in stored, "legacy 事件与会话历史必须是同一句人话"
    assert "no_answer_produced" not in legacy["content"]


def test_unproductive_turn_fails_instead_of_completing(monkeypatch):
    events, _saved = _ask(
        monkeypatch,
        [{"worker_results": {}, "final_answer": ""}],
        None,
    )
    names = [name for name, _data in events]
    assert "request.failed" in names
    assert "request.completed" not in names
    failed = next(data for name, data in events if name == "request.failed")
    assert failed["data"]["error_code"] == "no_answer_produced"
